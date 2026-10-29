from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple

from app.models import (
    Coordinates,
    HierarchyNode,
    MeterHierarchy,
    MeterDetail,
    EnergyReading,
    ConsumptionSummary,
    PhaseType,
    InstallStatus,
)

# Urja meters are located in Jaipur, India (IST: UTC +05:30)
IST = timezone(timedelta(hours=5, minutes=30))


def parse_ist_timestamp(ts_str: str) -> datetime:
    """Parse 'DD/MM/YYYY HH:MM' into a timezone-aware IST datetime."""
    dt = datetime.strptime(ts_str.strip(), "%d/%m/%Y %H:%M")
    return dt.replace(tzinfo=IST)


def normalize_coordinates(raw_geo: Optional[Dict[str, Any]]) -> Optional[Coordinates]:
    """Normalize coordinates from either /geo (latitude/longitude strings) or /export (lat/lng numbers)."""
    if not raw_geo or not isinstance(raw_geo, dict):
        return None

    lat_val = raw_geo.get("lat") or raw_geo.get("latitude")
    lng_val = raw_geo.get("lng") or raw_geo.get("longitude")

    if lat_val is None or lng_val is None:
        return None

    try:
        return Coordinates(
            latitude=round(float(lat_val), 6),
            longitude=round(float(lng_val), 6),
        )
    except (ValueError, TypeError):
        return None


def _normalize_hierarchy_node(raw_node: Optional[Dict[str, Any]]) -> Optional[HierarchyNode]:
    if not raw_node or not isinstance(raw_node, dict):
        return None

    code = str(raw_node.get("code", "")).strip()
    name = str(raw_node.get("name", "")).strip()

    if not code and not name:
        return None

    flags = []
    if not code:
        flags.append("missing_code_fallback")
        code = "UNKNOWN"
    if not name:
        flags.append("missing_name_fallback")
        name = code or "Unknown Node"

    return HierarchyNode(code=code, name=name, data_quality_flags=flags)


def normalize_hierarchy(raw_h: Optional[Dict[str, Any]]) -> Optional[MeterHierarchy]:
    """Normalize the 7-level electrical grid hierarchy handling key discrepancies and missing fields."""
    if not raw_h or not isinstance(raw_h, dict):
        return None

    # Handle casing variants like 'substation', 'Sub Station', 'sub_station'
    substation_raw = raw_h.get("substation") or raw_h.get("Sub Station") or raw_h.get("sub_station")

    return MeterHierarchy(
        zone=_normalize_hierarchy_node(raw_h.get("zone")),
        circle=_normalize_hierarchy_node(raw_h.get("circle")),
        division=_normalize_hierarchy_node(raw_h.get("division")),
        subdivision=_normalize_hierarchy_node(raw_h.get("subdivision")),
        substation=_normalize_hierarchy_node(substation_raw),
        feeder=_normalize_hierarchy_node(raw_h.get("feeder")),
        dt=_normalize_hierarchy_node(raw_h.get("dt")),
    )


def normalize_meter(raw: Dict[str, Any]) -> MeterDetail:
    """Transform raw portal meter dict into a typed MeterDetail model."""
    meter_id = raw.get("meterId") or raw.get("id") or ""
    serial_no = raw.get("serialNo") or raw.get("serial_number") or ""
    make = raw.get("make") or ""
    phase_raw = str(raw.get("phaseType") or raw.get("phase") or "single").lower()
    status_raw = raw.get("installStatus") or raw.get("install_status") or "Unknown"
    install_type = raw.get("installType") or raw.get("install_type")
    build = raw.get("build")
    dt_code = raw.get("dtCode") or raw.get("dt_code") or ""

    coords = normalize_coordinates(raw.get("geo"))
    hierarchy = normalize_hierarchy(raw.get("hierarchy"))

    flags: List[str] = []
    if hierarchy:
        for level in ("zone", "circle", "division", "subdivision", "substation", "feeder", "dt"):
            node = getattr(hierarchy, level, None)
            if node and node.data_quality_flags:
                flags.extend(f"{level}:{f}" for f in node.data_quality_flags)

    phase_enum = PhaseType.SINGLE
    if phase_raw in ("single", "three"):
        phase_enum = PhaseType(phase_raw)
    else:
        phase_enum = PhaseType.UNKNOWN
        flags.append(f"unrecognized_phase:{phase_raw}")

    status_enum = InstallStatus.UNKNOWN
    for s in InstallStatus:
        if s.value.lower() == str(status_raw).lower():
            status_enum = s
            break
    if status_enum == InstallStatus.UNKNOWN:
        flags.append(f"unrecognized_status:{status_raw}")

    return MeterDetail(
        id=str(meter_id),
        serial_number=str(serial_no),
        make=str(make),
        phase=phase_enum,
        install_status=status_enum,
        install_type=str(install_type) if install_type else None,
        build=str(build) if build else None,
        dt_code=str(dt_code),
        coordinates=coords,
        hierarchy=hierarchy,
        data_quality_flags=flags,
    )


def process_energy_readings(raw_data: List[Dict[str, Any]]) -> Tuple[List[EnergyReading], ConsumptionSummary]:
    """
    Process raw interval energy readings:
    - Sort chronologically
    - Parse timestamps to IST
    - Compute interval delta consumption (kWh_t - kWh_{t-1})
    - Calculate aggregate summary metrics
    """
    if not raw_data:
        empty_summary = ConsumptionSummary(
            total_consumption_kwh=0.0,
            max_interval_kwh=0.0,
            min_interval_kwh=0.0,
            average_voltage=None,
            reading_count=0,
        )
        return [], empty_summary

    parsed_items = []
    for item in raw_data:
        try:
            ts = parse_ist_timestamp(item["timestamp"])
            kwh = float(item["kwh"])
            kvah = float(item["kvah"])
            volt = float(item["voltR"]) if "voltR" in item and item["voltR"] is not None else None
            parsed_items.append((ts, kwh, kvah, volt))
        except (KeyError, ValueError, TypeError):
            continue

    parsed_items.sort(key=lambda x: x[0])

    readings: List[EnergyReading] = []
    deltas: List[float] = []
    voltages: List[float] = []

    for i, (ts, kwh, kvah, volt) in enumerate(parsed_items):
        consumption_kwh: Optional[float] = None
        if i > 0:
            prev_kwh = parsed_items[i - 1][1]
            diff = kwh - prev_kwh
            # Register values are monotonically increasing; handle potential rollover or zero delta
            if diff >= 0:
                consumption_kwh = round(diff, 4)
                deltas.append(consumption_kwh)

        if volt is not None:
            voltages.append(volt)

        readings.append(
            EnergyReading(
                timestamp=ts,
                kwh_reading=round(kwh, 4),
                kvah_reading=round(kvah, 4),
                consumption_kwh=consumption_kwh,
                voltage_r=volt,
            )
        )

    total_consumed = round(sum(deltas), 4) if deltas else 0.0
    max_consumed = max(deltas) if deltas else 0.0
    min_consumed = min(deltas) if deltas else 0.0
    avg_voltage = round(sum(voltages) / len(voltages), 2) if voltages else None

    summary = ConsumptionSummary(
        total_consumption_kwh=total_consumed,
        max_interval_kwh=max_consumed,
        min_interval_kwh=min_consumed,
        average_voltage=avg_voltage,
        reading_count=len(readings),
    )

    return readings, summary
