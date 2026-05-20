"""BigQuery data access and load job utilities."""

from __future__ import annotations

from google.cloud import bigquery


# Wrapper class around BigQuery operations used by the ingestion workflow.
class BigQueryWriter:
    def __init__(self, project_id: str, dataset_id: str, location: str):
        self.project_id = project_id
        self.dataset_id = dataset_id
        self.location = location
        self.client = bigquery.Client(project=project_id, location=location)

    def _table(self, name: str) -> str:
        return f"{self.project_id}.{self.dataset_id}.{name}"

    def ensure_processing_code_columns(self) -> None:
        # Add processing_code to uploads if it does not exist yet.
        self.client.query(
            f"""
            ALTER TABLE `{self._table('partdata_uploads')}`
            ADD COLUMN IF NOT EXISTS processing_code STRING
            """
        ).result()
        # Add processing_code to curated setups if it does not exist yet.
        self.client.query(
            f"""
            ALTER TABLE `{self._table('partdata_curated_setups')}`
            ADD COLUMN IF NOT EXISTS processing_code STRING
            """
        ).result()

    def already_parsed(self, file_sha256: str) -> bool:
        query = f"""
        SELECT COUNT(1) AS c
        FROM `{self._table('partdata_uploads')}`
        WHERE file_sha256 = @sha AND parse_status = 'success'
        """
        cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("sha", "STRING", file_sha256)])
        result = list(self.client.query(query, job_config=cfg).result())
        return bool(result and result[0]["c"] > 0)

    def load_json_rows(self, table_name: str, rows: list[dict]) -> None:
        if not rows:
            return
        cfg = bigquery.LoadJobConfig(write_disposition=bigquery.WriteDisposition.WRITE_APPEND)
        job = self.client.load_table_from_json(rows, self._table(table_name), job_config=cfg)
        job.result()
