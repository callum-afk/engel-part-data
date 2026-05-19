"""Raw partdata archive parsing utilities."""

from __future__ import annotations

import gzip
import hashlib
import os
import struct
import tarfile
from pathlib import Path

from app.mappings import build_curated_setup
from app.models import ParseBundle, RawVariable


# Decode null-terminated bytes into cleaned UTF-8 string.
def _decode_cstr(raw: bytes) -> str:
    return raw.split(b"\x00", 1)[0].decode("utf-8", errors="ignore").strip()


# Parse key-value properties files.
def parse_properties_file(path: Path) -> dict[str, str]:
    props: dict[str, str] = {}
    for line in path.read_text(errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, val = line.split("=", 1)
        props[key.strip()] = val.strip()
    normalized = {
        "material_number": props.get("material_number") or props.get("materialNumber"),
        "mould_number": props.get("mould_number") or props.get("moldNumber"),
        "machine_number": props.get("machine_number") or props.get("machineNumber"),
        "author": props.get("author") or props.get("createdBy"),
        "setup_created_at": props.get("setup_created_at") or props.get("createdAt"),
        "machine_type": props.get("machine_type"),
        "machine_id": props.get("machine_id"),
    }
    return {**props, **{k: v for k, v in normalized.items() if v}}


def parse_fixed_records(upload_id: str, source_file: str, blob: bytes, header: int, size: int, var_type: str) -> list[RawVariable]:
    rows: list[RawVariable] = []
    recs = (len(blob) - header) // size if len(blob) > header else 0
    for i in range(recs):
        rec = blob[header + i * size: header + (i + 1) * size]
        uri = _decode_cstr(rec[0:256])
        appl = _decode_cstr(rec[256:512])
        name = appl or uri
        kwargs = dict(upload_id=upload_id, source_file=source_file, record_index=i, variable_uri=uri, appl_name=appl, variable_name=name, variable_type=var_type)
        if var_type == "float":
            v = struct.unpack("<f", rec[-4:])[0]
            rows.append(RawVariable(**kwargs, float_value=float(v), raw_value_string=str(v)))
        elif var_type == "integer":
            v = struct.unpack("<i", rec[-8:-4])[0]
            rows.append(RawVariable(**kwargs, int_value=int(v), raw_value_string=str(v)))
        elif var_type == "boolean":
            v = bool(rec[-1])
            rows.append(RawVariable(**kwargs, bool_value=v, raw_value_string=str(v).lower()))
        else:
            v = _decode_cstr(rec[512:])
            rows.append(RawVariable(**kwargs, string_value=v, raw_value_string=v))
    return rows


# Ensure tar extraction does not allow path traversal.
def safe_extract_tar(tar_path: Path, output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(tar_path, "r:gz") as tf:
        for member in tf.getmembers():
            target = (output_dir / member.name).resolve()
            if not str(target).startswith(str(output_dir.resolve())):
                raise ValueError(f"Unsafe tar path: {member.name}")
        tf.extractall(path=output_dir)


# Compute SHA256 for idempotency and traceability.
def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def parse_partdata(upload_id: str, parser_version: str, partdata_path: Path, work_dir: Path) -> tuple[ParseBundle, str]:
    # Validate gzip magic bytes before extraction.
    with partdata_path.open("rb") as f:
        magic = f.read(2)
    if magic != b"\x1f\x8b":
        raise ValueError("Input is not a gzip file")

    extract_dir = work_dir / f"extract_{upload_id}"
    safe_extract_tar(partdata_path, extract_dir)

    raw_vars: list[RawVariable] = []
    merged_props: dict[str, str] = {}
    for fp in extract_dir.rglob("*"):
        if not fp.is_file():
            continue
        rel = str(fp.relative_to(extract_dir))
        blob = fp.read_bytes()
        if fp.name == "floatvalues.dat":
            raw_vars.extend(parse_fixed_records(upload_id, rel, blob, 1608, 520, "float"))
        elif fp.name == "integervalues.dat":
            raw_vars.extend(parse_fixed_records(upload_id, rel, blob, 1608, 524, "integer"))
        elif fp.name == "booleanvalues.dat":
            raw_vars.extend(parse_fixed_records(upload_id, rel, blob, 1608, 517, "boolean"))
        elif fp.name == "stringvalues.dat":
            raw_vars.extend(parse_fixed_records(upload_id, rel, blob, 1608, 772, "string"))
        elif fp.suffix == ".properties":
            merged_props.update(parse_properties_file(fp))

    curated, profiles = build_curated_setup(upload_id, parser_version, raw_vars, merged_props)
    bundle = ParseBundle(raw_variables=raw_vars, curated_setup=curated, profile_points=profiles, properties=merged_props, stats={"extracted_dir": str(extract_dir), "raw_variable_count": len(raw_vars), "profile_point_count": len(profiles)})
    return bundle, sha256_file(partdata_path)
