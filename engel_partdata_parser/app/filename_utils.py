"""Filename parsing helpers for partdata ingestion metadata."""

from __future__ import annotations

import re
from pathlib import Path


def extract_processing_code(file_name: str) -> str | None:
    # Ensure regex matching is applied to basename only.
    name = Path(file_name).name
    # Support both setupfile_<CODE>.partdata and <prefix>_setupfile_<CODE>.partdata.
    match = re.search(r"(?:^|_)setupfile_([A-Za-z0-9]+)\.partdata$", name, re.IGNORECASE)
    # Return NULL-like value when pattern is not present.
    if not match:
        return None
    # Normalize code to uppercase for consistency in BigQuery.
    return match.group(1).upper()
