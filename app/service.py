import asyncio
import time
from typing import Any, Dict, List, Optional, Tuple

from app.client import UrjaClient
from app.config import settings
from app.exceptions import ResourceNotFoundError
from app.models import (
    DistributionTransformer,
    DistributionTransformerDetail,
    MeterDetail,
    MeterSummary,
    MeterConsumptionResponse,
    PaginatedResponse,
)
from app.normalization import (
    normalize_meter,
    process_energy_readings,
)


class MeterService:
    """Service layer managing caching, indexing, filtering, and data aggregation."""

    def __init__(self, client: UrjaClient):
        self.client = client
        self._meters: Dict[str, MeterDetail] = {}
        self._transformers: Dict[str, DistributionTransformerDetail] = {}
        self._last_synced_at: Optional[float] = None
        self._sync_lock = asyncio.Lock()
        self.started_at: float = time.time()

    @property
    def is_synced(self) -> bool:
        return bool(self._meters)

    @property
    def last_synced_at_iso(self) -> Optional[str]:
        if not self._last_synced_at:
            return None
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(self._last_synced_at))

    async def ensure_synced(self, force: bool = False):
        """Synchronize meters and transformers cache if expired or empty."""
        async with self._sync_lock:
            now = time.time()
            if not force and self._last_synced_at and (now - self._last_synced_at) < settings.cache_ttl_seconds:
                return

            raw_meters = await self.client.export_all_meters()
            raw_dts = await self.client.get_transformers()

            # Index meters
            meters_map: Dict[str, MeterDetail] = {}
            dt_to_meters: Dict[str, List[str]] = {}

            for raw_m in raw_meters:
                detail = normalize_meter(raw_m)
                meters_map[detail.id] = detail
                if detail.dt_code:
                    dt_to_meters.setdefault(detail.dt_code, []).append(detail.id)

            # Index transformers and attach connected meters
            dts_map: Dict[str, DistributionTransformerDetail] = {}
            for raw_dt in raw_dts:
                code = raw_dt.get("code") or ""
                assigned_meter_ids = sorted(dt_to_meters.get(code, []))
                dts_map[code] = DistributionTransformerDetail(
                    code=code,
                    name=raw_dt.get("name") or code,
                    feeder_code=raw_dt.get("feederCode") or "",
                    capacity_kva=float(raw_dt.get("capacityKva", 0.0)),
                    assigned_meters_count=len(assigned_meter_ids),
                    meter_ids=assigned_meter_ids,
                )

            self._meters = meters_map
            self._transformers = dts_map
            self._last_synced_at = now

    async def list_meters(
        self,
        query: Optional[str] = None,
        dt_code: Optional[str] = None,
        phase: Optional[str] = None,
        status: Optional[str] = None,
        make: Optional[str] = None,
        page: int = 1,
        page_size: int = 20,
    ) -> PaginatedResponse[MeterSummary]:
        await self.ensure_synced()

        meters = list(self._meters.values())

        # Filtering
        if query:
            q = query.strip().lower()
            meters = [
                m for m in meters
                if q in m.id.lower() or q in m.serial_number.lower() or q in m.dt_code.lower() or q in m.make.lower()
            ]

        if dt_code:
            dt_clean = dt_code.strip().upper()
            meters = [m for m in meters if m.dt_code.upper() == dt_clean]

        if phase:
            phase_clean = phase.strip().lower()
            meters = [m for m in meters if m.phase.lower() == phase_clean]

        if status:
            status_clean = status.strip().lower()
            meters = [m for m in meters if m.install_status.lower() == status_clean]

        if make:
            make_clean = make.strip().lower()
            meters = [m for m in meters if m.make.lower() == make_clean]

        meters.sort(key=lambda m: m.id)

        total = len(meters)
        total_pages = max(1, (total + page_size - 1) // page_size)
        start_idx = (page - 1) * page_size
        end_idx = start_idx + page_size

        items = [MeterSummary(**m.model_dump(exclude={"hierarchy"})) for m in meters[start_idx:end_idx]]

        return PaginatedResponse(
            items=items,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        )

    async def get_meter(self, meter_id: str) -> MeterDetail:
        await self.ensure_synced()

        meter = self._meters.get(meter_id)
        if not meter:
            raise ResourceNotFoundError(f"Meter with ID '{meter_id}' not found.")
        return meter

    async def list_transformers(self, feeder_code: Optional[str] = None) -> List[DistributionTransformer]:
        await self.ensure_synced()

        transformers = list(self._transformers.values())
        if feeder_code:
            f_clean = feeder_code.strip().upper()
            transformers = [t for t in transformers if t.feeder_code.upper() == f_clean]

        transformers.sort(key=lambda t: t.code)
        return [DistributionTransformer(**t.model_dump(exclude={"meter_ids"})) for t in transformers]

    async def get_transformer(self, code: str) -> DistributionTransformerDetail:
        await self.ensure_synced()

        dt = self._transformers.get(code)
        if not dt:
            raise ResourceNotFoundError(f"Distribution Transformer with code '{code}' not found.")
        return dt

    async def get_meter_consumption(
        self,
        meter_id: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
    ) -> MeterConsumptionResponse:
        # Verify meter exists
        await self.get_meter(meter_id)

        raw_readings = await self.client.get_meter_energy(meter_id, from_date=from_date, to_date=to_date)
        readings, summary = process_energy_readings(raw_readings)

        return MeterConsumptionResponse(
            meter_id=meter_id,
            from_date=from_date,
            to_date=to_date,
            summary=summary,
            readings=readings,
        )

    async def get_hierarchy_tree(self) -> Dict[str, Any]:
        """Construct a complete nested tree of the distribution network down to meters."""
        await self.ensure_synced()

        tree: Dict[str, Any] = {}

        for meter in self._meters.values():
            h = meter.hierarchy
            if not h:
                continue

            z_code = h.zone.code if h.zone else "UNKNOWN_ZONE"
            z_name = h.zone.name if h.zone else "Unknown Zone"

            c_code = h.circle.code if h.circle else "UNKNOWN_CIRCLE"
            c_name = h.circle.name if h.circle else "Unknown Circle"

            d_code = h.division.code if h.division else "UNKNOWN_DIV"
            d_name = h.division.name if h.division else "Unknown Division"

            sd_code = h.subdivision.code if h.subdivision else "UNKNOWN_SUBDIV"
            sd_name = h.subdivision.name if h.subdivision else "Unknown Subdivision"

            ss_code = h.substation.code if h.substation else "UNKNOWN_SS"
            ss_name = h.substation.name if h.substation else "Unknown Substation"

            f_code = h.feeder.code if h.feeder else "UNKNOWN_F"
            f_name = h.feeder.name if h.feeder else "Unknown Feeder"

            dt_code = h.dt.code if h.dt else meter.dt_code
            dt_name = h.dt.name if h.dt else meter.dt_code

            # Navigate / build hierarchy branches
            zone_node = tree.setdefault(z_code, {"code": z_code, "name": z_name, "circles": {}})
            circle_node = zone_node["circles"].setdefault(c_code, {"code": c_code, "name": c_name, "divisions": {}})
            div_node = circle_node["divisions"].setdefault(d_code, {"code": d_code, "name": d_name, "subdivisions": {}})
            subdiv_node = div_node["subdivisions"].setdefault(sd_code, {"code": sd_code, "name": sd_name, "substations": {}})
            ss_node = subdiv_node["substations"].setdefault(ss_code, {"code": ss_code, "name": ss_name, "feeders": {}})
            feeder_node = ss_node["feeders"].setdefault(f_code, {"code": f_code, "name": f_name, "transformers": {}})
            dt_node = feeder_node["transformers"].setdefault(dt_code, {"code": dt_code, "name": dt_name, "meters": []})

            dt_node["meters"].append(meter.id)

        # Convert dictionaries to nested lists for clean JSON consumption
        def format_node(node: Dict[str, Any], child_key: Optional[str]) -> Dict[str, Any]:
            result = {"code": node["code"], "name": node["name"]}
            if child_key and child_key in node:
                next_child_map = {
                    "circles": "divisions",
                    "divisions": "subdivisions",
                    "subdivisions": "substations",
                    "substations": "feeders",
                    "feeders": "transformers",
                    "transformers": None,
                }
                result[child_key] = [
                    format_node(child, next_child_map.get(child_key))
                    for child in sorted(node[child_key].values(), key=lambda x: x["code"])
                ]
            elif "meters" in node:
                result["meters"] = sorted(node["meters"])
                result["meter_count"] = len(node["meters"])
            return result

        formatted_zones = [
            format_node(z, "circles") for z in sorted(tree.values(), key=lambda x: x["code"])
        ]
        return {"zones": formatted_zones}
