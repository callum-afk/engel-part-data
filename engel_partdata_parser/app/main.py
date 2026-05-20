"""Cloud Run service entrypoint and CLI runner for partdata parsing."""

from __future__ import annotations

import argparse
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from cloudevents.http import from_http
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.bigquery_writer import BigQueryWriter
from app.filename_utils import extract_processing_code
from app.models import UploadRecord
from app.parser import parse_partdata
from app.storage import StorageClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("engel_partdata_parser")

PROJECT_ID = os.getenv("PROJECT_ID", "notpla-machine-data")
DATASET_ID = os.getenv("DATASET_ID", "engel_partdata")
RAW_BUCKET = os.getenv("RAW_BUCKET", "notpla-engel-partdata-raw")
PROCESSED_BUCKET = os.getenv("PROCESSED_BUCKET", "notpla-engel-partdata-processed")
FAILED_BUCKET = os.getenv("FAILED_BUCKET", "notpla-engel-partdata-failed")
BQ_LOCATION = os.getenv("BQ_LOCATION", "europe-west2")
PARSER_VERSION = os.getenv("PARSER_VERSION", "0.1.4")
FORCE_REPARSE = os.getenv("FORCE_REPARSE", "false").lower() == "true"

app = FastAPI(title="Engel Partdata Parser")


def build_upload_id(file_sha256: str) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{file_sha256[:16]}_{ts}"
def process_one_file(source_bucket: str, source_object: str, local_input: Path | None = None, write_bigquery: bool = True, force_reparse: bool = False) -> dict:
    storage_client = StorageClient(PROJECT_ID)
    bq = BigQueryWriter(PROJECT_ID, DATASET_ID, BQ_LOCATION)

    if not source_object.endswith(".partdata"):
        return {"status": "ignored", "source_bucket": source_bucket, "source_object": source_object, "parse_status": "ignored_non_partdata"}

    # Keep a canonical basename used for upload metadata and processing code extraction.
    file_name = Path(source_object).name
    # Derive processing code once per file and reuse for all downstream writes.
    processing_code = extract_processing_code(file_name)

    local_path = local_input or Path("/tmp") / file_name
    file_size = local_path.stat().st_size if local_input else storage_client.download_object(source_bucket, source_object, local_path)

    bundle, file_sha256 = parse_partdata("temp", PARSER_VERSION, local_path, Path("/tmp"))
    upload_id = build_upload_id(file_sha256)
    bundle, _ = parse_partdata(upload_id, PARSER_VERSION, local_path, Path("/tmp"))

    # Allow explicit bypass of already_parsed guard using env or function flag.
    effective_force_reparse = force_reparse or FORCE_REPARSE
    if write_bigquery and not effective_force_reparse and bq.already_parsed(file_sha256):
        return {"status": "already_parsed", "upload_id": upload_id, "source_bucket": source_bucket, "source_object": source_object, "raw_variable_count": 0, "curated_fields_populated": 0, "profile_point_count": 0, "parse_status": "already_parsed"}

    try:
        # Propagate processing code to curated setup row before writing.
        bundle.curated_setup.processing_code = processing_code

        upload = UploadRecord(upload_id=upload_id, source_bucket=source_bucket, source_object=source_object, file_name=file_name, processing_code=processing_code, file_size_bytes=file_size, file_sha256=file_sha256, uploaded_at=datetime.now(timezone.utc), parser_version=PARSER_VERSION, parse_status="success", machine_type=bundle.curated_setup.machine_type, machine_id=bundle.curated_setup.machine_id, machine_number=bundle.curated_setup.machine_number, mould_number=bundle.curated_setup.mould_number, material_number=bundle.curated_setup.material_number, author=bundle.curated_setup.setup_author, setup_created_at=bundle.curated_setup.setup_created_at)

        if write_bigquery:
            # Apply additive schema migration for processing_code columns.
            bq.ensure_processing_code_columns()
            bq.load_json_rows("partdata_raw_variables", [r.model_dump(mode="json") for r in bundle.raw_variables])
            bq.load_json_rows("partdata_curated_setups", [bundle.curated_setup.model_dump(mode="json")])
            bq.load_json_rows("partdata_profiles", [p.model_dump(mode="json") for p in bundle.profile_points])
            bq.load_json_rows("partdata_uploads", [upload.model_dump(mode="json")])

        if source_bucket and source_object and source_bucket == RAW_BUCKET:
            storage_client.copy_object(source_bucket, source_object, PROCESSED_BUCKET, source_object)

        curated_fields_populated = sum(1 for v in bundle.curated_setup.model_dump().values() if v is not None)
        logger.info("Parsed upload_id=%s raw=%s curated=%s profiles=%s", upload_id, len(bundle.raw_variables), curated_fields_populated, len(bundle.profile_points))
        return {"status": "ok", "upload_id": upload_id, "source_bucket": source_bucket, "source_object": source_object, "raw_variable_count": len(bundle.raw_variables), "curated_fields_populated": curated_fields_populated, "profile_point_count": len(bundle.profile_points), "parse_status": "success"}
    except Exception as exc:
        if write_bigquery:
            failed = UploadRecord(upload_id=upload_id, source_bucket=source_bucket, source_object=source_object, file_name=file_name, processing_code=processing_code, file_size_bytes=file_size, file_sha256=file_sha256, uploaded_at=datetime.now(timezone.utc), parser_version=PARSER_VERSION, parse_status="failed", parse_error=str(exc))
            bq.load_json_rows("partdata_uploads", [failed.model_dump(mode="json")])
        if source_bucket and source_object and source_bucket == RAW_BUCKET:
            storage_client.copy_object(source_bucket, source_object, FAILED_BUCKET, source_object)
        return {"status": "error", "upload_id": upload_id, "source_bucket": source_bucket, "source_object": source_object, "raw_variable_count": 0, "curated_fields_populated": 0, "profile_point_count": 0, "parse_status": "failed", "parse_error": str(exc)}


@app.get("/")
async def health() -> dict:
    return {"status": "ok", "service": "engel-partdata-parser"}


@app.post("/eventarc")
async def eventarc(request: Request) -> JSONResponse:
    headers = dict(request.headers)
    body = await request.body()
    event = from_http(headers, body)
    data = event.data or {}
    result = process_one_file(data.get("bucket", ""), data.get("name", ""), write_bigquery=True)
    return JSONResponse(result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", required=True)
    parser.add_argument("--project", default=PROJECT_ID)
    parser.add_argument("--dataset", default=DATASET_ID)
    parser.add_argument("--write-bigquery", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force-reparse", action="store_true")
    args = parser.parse_args()

    PROJECT_ID = args.project
    DATASET_ID = args.dataset
    resp = process_one_file(RAW_BUCKET, Path(args.input).name, local_input=Path(args.input), write_bigquery=args.write_bigquery and not args.dry_run, force_reparse=args.force_reparse)
    print(resp)
