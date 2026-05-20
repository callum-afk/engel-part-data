"""Pydantic models and typed containers used across parsing and writing layers."""

from __future__ import annotations

# Standard library imports for datetime handling and typing annotations.
from datetime import datetime, timezone
from typing import Any, Optional

# Pydantic is used for robust request/response and row modeling.
from pydantic import BaseModel, Field


# Helper function to create UTC timestamps consistently.
def utc_now() -> datetime:
    """Return the current timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


# Model for a decoded raw variable row destined for BigQuery.
class RawVariable(BaseModel):
    upload_id: str
    source_file: str
    record_index: int
    variable_uri: Optional[str] = None
    appl_name: Optional[str] = None
    variable_name: Optional[str] = None
    variable_type: str
    float_value: Optional[float] = None
    int_value: Optional[int] = None
    bool_value: Optional[bool] = None
    string_value: Optional[str] = None
    raw_value_string: Optional[str] = None
    parse_confidence: str = "medium"
    parser_note: Optional[str] = None
    created_at: datetime = Field(default_factory=utc_now)


# Model for top-level upload status row.
class UploadRecord(BaseModel):
    upload_id: str
    source_bucket: str
    source_object: str
    file_name: str
    # Processing code extracted from setupfile_<CODE>.partdata filenames.
    processing_code: Optional[str] = None
    file_size_bytes: int
    file_sha256: str
    uploaded_at: datetime
    parsed_at: datetime = Field(default_factory=utc_now)
    parser_version: str
    parse_status: str
    parse_error: Optional[str] = None
    machine_type: Optional[str] = None
    machine_id: Optional[str] = None
    machine_number: Optional[str] = None
    mould_number: Optional[str] = None
    material_number: Optional[str] = None
    author: Optional[str] = None
    setup_created_at: Optional[datetime] = None


# Model for curated scalar setup fields.
class CuratedSetup(BaseModel):
    upload_id: str
    # Processing code extracted from setupfile_<CODE>.partdata filenames.
    processing_code: Optional[str] = None
    machine_type: Optional[str] = None
    machine_id: Optional[str] = None
    machine_number: Optional[str] = None
    mould_number: Optional[str] = None
    material_number: Optional[str] = None
    setup_author: Optional[str] = None
    setup_created_at: Optional[datetime] = None
    barrel_zone_1_c: Optional[float] = None
    barrel_zone_2_c: Optional[float] = None
    barrel_zone_3_c: Optional[float] = None
    barrel_zone_4_c: Optional[float] = None
    barrel_zone_5_c: Optional[float] = None
    nozzle_temp_c: Optional[float] = None
    injection_speed_primary: Optional[float] = None
    injection_speed_unit: Optional[str] = None
    plasticising_speed_primary: Optional[float] = None
    plasticising_speed_unit: Optional[str] = None
    dosing_volume_cm3: Optional[float] = None
    decompression_after_plast_cm3: Optional[float] = None
    back_pressure_bar: Optional[float] = None
    holding_pressure_bar: Optional[float] = None
    holding_time_s: Optional[float] = None
    cooling_time_s: Optional[float] = None
    switchover_position: Optional[float] = None
    switchover_pressure_bar: Optional[float] = None
    parser_version: str
    curated_confidence: str = "medium"
    created_at: datetime = Field(default_factory=utc_now)


# Model for each curated profile point row.
class ProfilePoint(BaseModel):
    upload_id: str
    profile_group: str
    profile_source: str
    point_index: int
    active_point_count: Optional[int] = None
    x_value: Optional[float] = None
    y_value: Optional[float] = None
    x_label: Optional[str] = None
    y_label: Optional[str] = None
    x_unit: Optional[str] = None
    y_unit: Optional[str] = None
    interpretation: Optional[str] = None
    confidence: str = "medium"
    created_at: datetime = Field(default_factory=utc_now)


# Model for parser output carried from parse layer to write layer.
class ParseBundle(BaseModel):
    raw_variables: list[RawVariable]
    curated_setup: CuratedSetup
    profile_points: list[ProfilePoint]
    properties: dict[str, str]
    stats: dict[str, Any]
