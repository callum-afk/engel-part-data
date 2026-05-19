"""Parser smoke tests."""

from pathlib import Path

from app.mappings import build_curated_setup
from app.models import RawVariable
from app.parser import _decode_cstr


def test_decode_cstr():
    assert _decode_cstr(b"hello\x00world") == "hello"


def test_curated_mapping_uses_tempering_setvalue_and_profile_ry():
    # Build representative raw rows for tempering temperatures and profile rX/rY pairs.
    rows = [
        RawVariable(upload_id="u", source_file="partdata/imm/tempering/floatvalues.dat", record_index=6, variable_uri="/TemperingZone1/v/p.SetValue", appl_name="APPL.Heating.sv_Zone2.rSetValue", variable_name="APPL.Heating.sv_Zone2.rSetValue", variable_type="float", float_value=170.0),
        RawVariable(upload_id="u", source_file="partdata/imm/tempering/floatvalues.dat", record_index=14, variable_uri="/TemperingZone2/v/p.SetValue", appl_name="APPL.Heating.sv_Zone3.rSetValue", variable_name="APPL.Heating.sv_Zone3.rSetValue", variable_type="float", float_value=170.0),
        RawVariable(upload_id="u", source_file="partdata/imm/tempering/floatvalues.dat", record_index=22, variable_uri="/TemperingZone3/v/p.SetValue", appl_name="APPL.Heating.sv_Zone4.rSetValue", variable_name="APPL.Heating.sv_Zone4.rSetValue", variable_type="float", float_value=170.0),
        RawVariable(upload_id="u", source_file="partdata/imm/tempering/floatvalues.dat", record_index=30, variable_uri="/TemperingZone4/v/p.SetValue", appl_name="APPL.Heating.sv_Zone5.rSetValue", variable_name="APPL.Heating.sv_Zone5.rSetValue", variable_type="float", float_value=155.0),
        RawVariable(upload_id="u", source_file="partdata/imm/tempering/floatvalues.dat", record_index=31, variable_uri="/TemperingZone4/v/p.SetValLow", appl_name="", variable_name="", variable_type="float", float_value=99.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=1, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointPreInjVStored[1].rX", variable_type="float", float_value=42.5),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=2, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointPreInjVStored[1].rY", variable_type="float", float_value=40.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=3, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointPlastVStored[1].rX", variable_type="float", float_value=0.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=4, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointPlastVStored[1].rY", variable_type="float", float_value=0.4),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=5, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointBackPStored[1].rY", variable_type="float", float_value=30.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=6, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_ProfPointPostInjPStored[1].rY", variable_type="float", float_value=500.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=7, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_rPlastStopVol", variable_type="float", float_value=42.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=8, variable_uri="", appl_name="", variable_name="APPL.InjectionUnit1.sv_rPostPressureTime", variable_type="float", float_value=3.0),
        RawVariable(upload_id="u", source_file="partdata/imm/process/floatvalues.dat", record_index=9, variable_uri="", appl_name="", variable_name="APPL.system.sv_CoolingTime.rSetVal", variable_type="float", float_value=25.0),
    ]

    # Run curated setup mapping with metadata seeded from properties.
    curated, _profiles = build_curated_setup("u", "0.1.2", rows, {"material_number": "PR 0833", "mould_number": "Notpla ISO 527-A1", "machine_number": "195604"})

    # Assert temperature mapping uses SetValue rows and ignores SetValLow alternatives.
    assert curated.barrel_zone_1_c == 170.0
    assert curated.barrel_zone_2_c == 170.0
    assert curated.barrel_zone_3_c == 170.0
    assert curated.barrel_zone_4_c == 155.0
    # Assert curated primaries come from rY setpoints, not rX axis values.
    assert curated.injection_speed_primary == 40.0
    assert curated.plasticising_speed_primary == 0.4
    assert curated.back_pressure_bar == 30.0
    assert curated.holding_pressure_bar == 500.0
    # Assert additional expected setup scalar values are mapped.
    assert curated.dosing_volume_cm3 == 42.0
    assert curated.holding_time_s == 3.0
    assert curated.cooling_time_s == 25.0
    # Assert metadata extraction keeps expected identifiers populated.
    assert curated.material_number == "PR 0833"
    assert curated.mould_number == "Notpla ISO 527-A1"
    assert curated.machine_number == "195604"
