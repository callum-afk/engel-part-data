"""Cloud Storage helper methods for download and copy/move flows."""

from __future__ import annotations

from pathlib import Path

from google.cloud import storage


# Storage wrapper to isolate GCS operations from application logic.
class StorageClient:
    def __init__(self, project_id: str):
        self.client = storage.Client(project=project_id)

    def download_object(self, bucket: str, obj: str, local_path: Path) -> int:
        local_path.parent.mkdir(parents=True, exist_ok=True)
        blob = self.client.bucket(bucket).blob(obj)
        blob.download_to_filename(str(local_path))
        return int(blob.size or local_path.stat().st_size)

    def copy_object(self, src_bucket: str, src_obj: str, dst_bucket: str, dst_obj: str) -> None:
        src = self.client.bucket(src_bucket)
        dst = self.client.bucket(dst_bucket)
        blob = src.blob(src_obj)
        src.copy_blob(blob, dst, dst_obj)

    def delete_object(self, bucket: str, obj: str) -> None:
        self.client.bucket(bucket).blob(obj).delete()
