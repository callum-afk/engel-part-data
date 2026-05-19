"""Curated variable mapping and profile extraction logic."""

from __future__ import annotations

# Imports for regex and datetime parsing.
import re
from datetime import datetime
from typing import Iterable

# Date parser handles mixed date formats from properties files.
from dateutil import parser as dateparser

# Local model imports.
from app.models import CuratedSetup, ProfilePoint, RawVariable


# Utility to find first matching variable from candidate names.
# Locate the first matching float variable by exact name or URI contains tokens.
def _find_first_float(rows: Iterable[RawVariable], names: list[str], contains: list[str] | None = None) -> float | None:
    for row in rows:
        name = (row.variable_name or "")
        uri = (row.variable_uri or "")
        if name in names:
            return row.float_value
        if contains and any(token in uri for token in contains):
            return row.float_value
    return None


# Locate a float from a specific source file using strict SetValue matching for heating zones.
def _find_tempering_setvalue(rows: Iterable[RawVariable], zone_idx: int, appl_name: str) -> float | None:
    # Build the exact URI fragment that corresponds only to SetValue (not SetValLow/Startup/etc).
    set_value_fragment = f"TemperingZone{zone_idx}/v/p.SetValue"
    # Iterate in record order and return the first valid match from the tempering float file.
    for row in rows:
        # Only temperature values from tempering floatvalues.dat are valid for this mapping.
        if (row.source_file or "") != "partdata/imm/tempering/floatvalues.dat":
            continue
        # Match either the exact appl_name fallback or a URI containing the strict SetValue path.
        uri = row.variable_uri or ""
        if row.appl_name == appl_name or set_value_fragment in uri:
            return row.float_value
    # Return None when no matching SetValue row exists.
    return None


# Utility to find first matching string variable by substring.
# Utility to find first matching string variable by substring.
def _find_string_contains(rows: Iterable[RawVariable], needle: str) -> str | None:
    for row in rows:
        target = " ".join(filter(None, [row.variable_name, row.variable_uri, row.string_value]))
        if needle in target and row.string_value:
            return row.string_value
    return None


# Resolve the first available metadata string from property keys and string variable hints.
def _resolve_metadata_value(properties: dict[str, str], rows: Iterable[RawVariable], property_keys: list[str], needles: list[str]) -> str | None:
    # First preference: any populated property value from the provided canonical/legacy keys.
    for key in property_keys:
        value = properties.get(key)
        if value:
            return value
    # Second preference: search string rows by known naming conventions and URI/app-name tokens.
    for row in rows:
        if not row.string_value:
            continue
        target = " ".join(filter(None, [row.variable_name, row.variable_uri, row.appl_name]))
        if any(needle in target for needle in needles):
            return row.string_value
    # No metadata found.
    return None


# Build curated profile points for a named profile family.
def extract_profile_points(upload_id: str, rows: list[RawVariable], group: str, stem: str, count_name: str, y_unit: str, x_unit: str | None = None) -> tuple[list[ProfilePoint], float | None]:
    # Read profile point count, when available, to limit emitted active points.
    count = None
    for r in rows:
        if (r.variable_name or "") == count_name and r.int_value is not None:
            count = max(0, r.int_value)
            break
    # Collect independent X-axis and Y-setpoint maps from profile rows.
    x_map: dict[int, float] = {}
    y_map: dict[int, float] = {}
    # Match the exact profile suffixes to avoid mixing rX/rY semantics.
    x_pattern = re.compile(re.escape(stem) + r"\[(\d+)\]\.rX$")
    y_pattern = re.compile(re.escape(stem) + r"\[(\d+)\]\.rY$")
    for r in rows:
        n = r.variable_name or ""
        if r.float_value is None:
            continue
        xm = x_pattern.search(n)
        if xm:
            x_map[int(xm.group(1))] = r.float_value
            continue
        ym = y_pattern.search(n)
        if ym:
            y_map[int(ym.group(1))] = r.float_value
    # Use the Y map as the canonical profile setpoint sequence for curated primaries.
    y_points = sorted(y_map.items(), key=lambda item: item[0])
    active = y_points[:count] if count else y_points
    out: list[ProfilePoint] = []
    # Emit points with x_value from rX when present, preserving y_value from rY.
    for idx, (point_no, y) in enumerate(active):
        out.append(ProfilePoint(upload_id=upload_id, profile_group=group, profile_source=stem, point_index=idx, active_point_count=count, x_value=x_map.get(point_no), y_value=y, x_label="profile_axis" if x_map.get(point_no) is not None else None, y_label=f"{group}_value", x_unit=x_unit, y_unit=y_unit, interpretation="active operator profile", confidence="medium"))
    primary = active[0][1] if active else None
    return out, primary


# Main curated mapping entrypoint.
def build_curated_setup(upload_id: str, parser_version: str, rows: list[RawVariable], properties: dict[str, str]) -> tuple[CuratedSetup, list[ProfilePoint]]:
    curated = CuratedSetup(upload_id=upload_id, parser_version=parser_version)

    # Map setup metadata from properties/string variables with broader key coverage.
    curated.material_number = _resolve_metadata_value(properties, rows, ["material_number", "materialNumber", "MaterialNumber"], ["sv_sMaterialNumber", "MaterialNumber"])
    curated.mould_number = _resolve_metadata_value(properties, rows, ["mould_number", "mold_number", "moldNumber", "MoldNumber", "MouldNumber"], ["sv_sMoldNumber", "sv_sMouldNumber", "MoldNumber", "MouldNumber"])
    curated.machine_number = _resolve_metadata_value(properties, rows, ["machine_number", "machineNumber", "MachineNumber"], ["sv_sMachineNumber", "MachineNumber"])
    curated.machine_type = properties.get("machine_type")
    curated.machine_id = properties.get("machine_id")
    curated.setup_author = properties.get("author")

    setup_created = properties.get("setup_created_at")
    if setup_created:
        try:
            curated.setup_created_at = dateparser.parse(setup_created)
        except (ValueError, TypeError, OverflowError):
            curated.setup_created_at = None

    # Map barrel temperatures from strict tempering SetValue rows (URI path or known appl_name fallback).
    curated.barrel_zone_1_c = _find_tempering_setvalue(rows, 1, "APPL.Heating.sv_Zone2.rSetValue")
    curated.barrel_zone_2_c = _find_tempering_setvalue(rows, 2, "APPL.Heating.sv_Zone3.rSetValue")
    curated.barrel_zone_3_c = _find_tempering_setvalue(rows, 3, "APPL.Heating.sv_Zone4.rSetValue")
    curated.barrel_zone_4_c = _find_tempering_setvalue(rows, 4, "APPL.Heating.sv_Zone5.rSetValue")
    curated.barrel_zone_5_c = _find_first_float(rows, ["APPL.Heating.sv_Zone6.rSetValue"])

    curated.cooling_time_s = _find_first_float(rows, ["APPL.system.sv_CoolingTime.rSetVal"])
    curated.holding_time_s = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rPostPressureTime"])
    curated.dosing_volume_cm3 = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rPlastStopVol"])
    curated.decompression_after_plast_cm3 = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rDecAfterPlastVol"])
    curated.switchover_position = _find_first_float(rows, ["APPL.InjectionUnit1.sv_InjCutOffCriterionStroke.rSetVal"])
    curated.switchover_pressure_bar = _find_first_float(rows, ["APPL.InjectionUnit1.sv_InjCutOffCriterionHydPress.rSetVal"])

    profiles: list[ProfilePoint] = []
    # Extract profile tables (partdata_profiles) unchanged: x stays rX axis and y stays rY setpoint.
    inj, inj_p = extract_profile_points(upload_id, rows, "injection_speed", "APPL.InjectionUnit1.sv_ProfPointPreInjVStored", "APPL.InjectionUnit1.sv_ProfBeforeCalcPreInjV.uNoOfPoints", "cm3/s")
    pla, pla_p = extract_profile_points(upload_id, rows, "plasticising_speed", "APPL.InjectionUnit1.sv_ProfPointPlastVStored", "APPL.InjectionUnit1.sv_ProfBeforeCalcPlastV.uNoOfPoints", "m/s")
    bp, bp_p = extract_profile_points(upload_id, rows, "back_pressure", "APPL.InjectionUnit1.sv_ProfPointBackPStored", "APPL.InjectionUnit1.sv_ProfBeforeCalcBackP.uNoOfPoints", "bar")
    hp, hp_p = extract_profile_points(upload_id, rows, "holding_pressure", "APPL.InjectionUnit1.sv_ProfPointPostInjPStored", "APPL.InjectionUnit1.sv_ProfBeforeCalcPostInjP.uNoOfPoints", "bar", x_unit="s")
    profiles.extend(inj + pla + bp + hp)

    curated.injection_speed_primary = inj_p
    curated.injection_speed_unit = "cm3/s" if inj_p is not None else None
    curated.plasticising_speed_primary = pla_p
    curated.plasticising_speed_unit = "m/s" if pla_p is not None else None
    if bp_p is not None and bp_p < 200:
        curated.back_pressure_bar = bp_p
    curated.holding_pressure_bar = hp_p

    populated = sum(1 for v in curated.model_dump().values() if v is not None)
    curated.curated_confidence = "high" if populated >= 12 else "medium"
    return curated, profiles
