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
def _find_first_float(rows: Iterable[RawVariable], names: list[str], contains: list[str] | None = None) -> float | None:
    for row in rows:
        name = (row.variable_name or "")
        uri = (row.variable_uri or "")
        if name in names:
            return row.float_value
        if contains and any(token in uri for token in contains):
            return row.float_value
    return None


# Utility to find first matching string variable by substring.
def _find_string_contains(rows: Iterable[RawVariable], needle: str) -> str | None:
    for row in rows:
        target = " ".join(filter(None, [row.variable_name, row.variable_uri, row.string_value]))
        if needle in target and row.string_value:
            return row.string_value
    return None


# Build curated profile points for a named profile family.
def extract_profile_points(upload_id: str, rows: list[RawVariable], group: str, stem: str, count_name: str, y_unit: str, x_unit: str | None = None) -> tuple[list[ProfilePoint], float | None]:
    count = None
    for r in rows:
        if (r.variable_name or "") == count_name and r.int_value is not None:
            count = max(0, r.int_value)
            break
    points: list[tuple[int, float]] = []
    pattern = re.compile(re.escape(stem) + r"\[(\d+)\]")
    for r in rows:
        n = r.variable_name or ""
        m = pattern.search(n)
        if m and r.float_value is not None:
            points.append((int(m.group(1)), r.float_value))
    points.sort(key=lambda x: x[0])
    active = points[:count] if count else points
    out: list[ProfilePoint] = []
    for idx, (_, y) in enumerate(active):
        out.append(ProfilePoint(upload_id=upload_id, profile_group=group, profile_source=stem, point_index=idx, active_point_count=count, x_value=float(idx) if x_unit else None, y_value=y, x_label="point_index" if x_unit else None, y_label=f"{group}_value", x_unit=x_unit, y_unit=y_unit, interpretation="active operator profile", confidence="medium"))
    primary = active[0][1] if active else None
    return out, primary


# Main curated mapping entrypoint.
def build_curated_setup(upload_id: str, parser_version: str, rows: list[RawVariable], properties: dict[str, str]) -> tuple[CuratedSetup, list[ProfilePoint]]:
    curated = CuratedSetup(upload_id=upload_id, parser_version=parser_version)

    curated.material_number = properties.get("material_number") or _find_string_contains(rows, "sv_sMaterialNumber")
    curated.mould_number = properties.get("mould_number") or _find_string_contains(rows, "sv_sMoldNumber")
    curated.machine_number = properties.get("machine_number") or _find_string_contains(rows, "sv_sMachineNumber")
    curated.machine_type = properties.get("machine_type")
    curated.machine_id = properties.get("machine_id")
    curated.setup_author = properties.get("author")

    setup_created = properties.get("setup_created_at")
    if setup_created:
        try:
            curated.setup_created_at = dateparser.parse(setup_created)
        except (ValueError, TypeError, OverflowError):
            curated.setup_created_at = None

    curated.barrel_zone_1_c = _find_first_float(rows, ["APPL.Heating.sv_Zone2.rSetValue"], ["TemperingZone1", "p.SetValue"])
    curated.barrel_zone_2_c = _find_first_float(rows, ["APPL.Heating.sv_Zone3.rSetValue"], ["TemperingZone2", "p.SetValue"])
    curated.barrel_zone_3_c = _find_first_float(rows, ["APPL.Heating.sv_Zone4.rSetValue"], ["TemperingZone3", "p.SetValue"])
    curated.barrel_zone_4_c = _find_first_float(rows, ["APPL.Heating.sv_Zone5.rSetValue"], ["TemperingZone4", "p.SetValue"])
    curated.barrel_zone_5_c = _find_first_float(rows, ["APPL.Heating.sv_Zone6.rSetValue"])

    curated.cooling_time_s = _find_first_float(rows, ["APPL.system.sv_CoolingTime.rSetVal"])
    curated.holding_time_s = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rPostPressureTime"])
    curated.dosing_volume_cm3 = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rPlastStopVol"])
    curated.decompression_after_plast_cm3 = _find_first_float(rows, ["APPL.InjectionUnit1.sv_rDecAfterPlastVol"])
    curated.switchover_position = _find_first_float(rows, ["APPL.InjectionUnit1.sv_InjCutOffCriterionStroke.rSetVal"])
    curated.switchover_pressure_bar = _find_first_float(rows, ["APPL.InjectionUnit1.sv_InjCutOffCriterionHydPress.rSetVal"])

    profiles: list[ProfilePoint] = []
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
