from datetime import datetime, timezone, timedelta
import pytest
from app.normalization import (
    parse_ist_timestamp,
    normalize_coordinates,
    normalize_hierarchy,
    normalize_meter,
    process_energy_readings,
    IST,
)


def test_parse_ist_timestamp():
    dt = parse_ist_timestamp("25/06/2026 14:30")
    assert dt.year == 2026
    assert dt.month == 6
    assert dt.day == 25
    assert dt.hour == 14
    assert dt.minute == 30
    assert dt.tzinfo == IST
    assert dt.utcoffset() == timedelta(hours=5, minutes=30)


def test_normalize_coordinates_from_floats():
    coords = normalize_coordinates({"lat": 26.938961, "lng": 75.830957})
    assert coords is not None
    assert coords.latitude == 26.938961
    assert coords.longitude == 75.830957


def test_normalize_coordinates_from_strings():
    coords = normalize_coordinates({"latitude": "26.938961002479868", "longitude": "75.83095696146852"})
    assert coords is not None
    assert coords.latitude == 26.938961
    assert coords.longitude == 75.830957


def test_normalize_coordinates_invalid():
    assert normalize_coordinates(None) is None
    assert normalize_coordinates({}) is None
    assert normalize_coordinates({"lat": "invalid", "lng": "data"}) is None


def test_normalize_hierarchy_with_substation_variation():
    raw_h = {
        "zone": {"code": "Z-01", "name": "Jaipur Zone 1"},
        "Sub Station": {"code": "SS-01", "name": "Substation 1"},
        "dt": {"code": "DT-001", "name": "Malviya Nagar DT 1"},
    }
    h = normalize_hierarchy(raw_h)
    assert h is not None
    assert h.zone.code == "Z-01"
    assert h.substation.code == "SS-01"
    assert h.substation.name == "Substation 1"
    assert h.circle is None


def test_normalize_meter():
    raw = {
        "meterId": "J100000",
        "serialNo": "SE33962",
        "make": "HPL",
        "phaseType": "single",
        "installStatus": "Installed",
        "installType": "Whole Current",
        "build": "legacy",
        "dtCode": "DT-001",
        "geo": {"lat": 26.9389, "lng": 75.8309},
        "hierarchy": {"dt": {"code": "DT-001", "name": "DT 1"}},
    }
    meter = normalize_meter(raw)
    assert meter.id == "J100000"
    assert meter.serial_number == "SE33962"
    assert meter.make == "HPL"
    assert meter.phase == "single"
    assert meter.coordinates.latitude == 26.9389


def test_process_energy_readings_delta_calculation():
    raw_readings = [
        {"timestamp": "25/06/2026 00:00", "kwh": "100.00", "kvah": "110.00", "voltR": "230"},
        {"timestamp": "25/06/2026 00:30", "kwh": "100.50", "kvah": "110.55", "voltR": "232"},
        {"timestamp": "25/06/2026 01:00", "kwh": "101.25", "kvah": "111.40", "voltR": "228"},
    ]
    readings, summary = process_energy_readings(raw_readings)

    assert len(readings) == 3
    # First reading has no predecessor, so consumption is None
    assert readings[0].consumption_kwh is None
    assert readings[0].kwh_reading == 100.0

    # Second reading delta = 100.50 - 100.00 = 0.50
    assert readings[1].consumption_kwh == 0.5
    # Third reading delta = 101.25 - 100.50 = 0.75
    assert readings[2].consumption_kwh == 0.75

    # Summary
    assert summary.total_consumption_kwh == 1.25
    assert summary.max_interval_kwh == 0.75
    assert summary.min_interval_kwh == 0.50
    assert summary.average_voltage == 230.0
    assert summary.reading_count == 3


def test_process_energy_readings_empty():
    readings, summary = process_energy_readings([])
    assert readings == []
    assert summary.total_consumption_kwh == 0.0
    assert summary.reading_count == 0
