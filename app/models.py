from datetime import datetime
from enum import Enum
from typing import Generic, List, Optional, TypeVar
from pydantic import BaseModel, ConfigDict, Field

T = TypeVar("T")


class PhaseType(str, Enum):
    SINGLE = "single"
    THREE = "three"
    UNKNOWN = "unknown"


class InstallStatus(str, Enum):
    INSTALLED = "Installed"
    FAULTY = "Faulty"
    DECOMMISSIONED = "Decommissioned"
    UNKNOWN = "Unknown"


class ErrorResponse(BaseModel):
    error: str = Field(..., description="Machine-readable error identifier", json_schema_extra={"example": "not_found"})
    message: str = Field(..., description="Human-readable description of error", json_schema_extra={"example": "Meter not found."})


class Coordinates(BaseModel):
    latitude: float = Field(..., description="Latitude in decimal degrees", json_schema_extra={"example": 26.938961})
    longitude: float = Field(..., description="Longitude in decimal degrees", json_schema_extra={"example": 75.830957})


class HierarchyNode(BaseModel):
    code: str = Field(..., description="Identifier code for this node", json_schema_extra={"example": "DT-001"})
    name: str = Field(..., description="Human-readable name", json_schema_extra={"example": "Malviya Nagar DT 1"})
    data_quality_flags: List[str] = Field(default_factory=list, description="Quality flags indicating repaired or fallback values")


class MeterHierarchy(BaseModel):
    zone: Optional[HierarchyNode] = None
    circle: Optional[HierarchyNode] = None
    division: Optional[HierarchyNode] = None
    subdivision: Optional[HierarchyNode] = None
    substation: Optional[HierarchyNode] = None
    feeder: Optional[HierarchyNode] = None
    dt: Optional[HierarchyNode] = None


class MeterSummary(BaseModel):
    model_config = ConfigDict(use_enum_values=True)

    id: str = Field(..., description="Unique meter identifier", json_schema_extra={"example": "J100000"})
    serial_number: str = Field(..., description="Manufacturer serial number", json_schema_extra={"example": "SE33962"})
    make: str = Field(..., description="Manufacturer brand", json_schema_extra={"example": "HPL"})
    phase: PhaseType = Field(..., description="Electrical phase: single or three", json_schema_extra={"example": "single"})
    install_status: InstallStatus = Field(..., description="Operational status: Installed, Faulty, Decommissioned", json_schema_extra={"example": "Installed"})
    install_type: Optional[str] = Field(None, description="Physical installation type", json_schema_extra={"example": "Whole Current"})
    build: Optional[str] = Field(None, description="Hardware revision or build tag from portal (unconfirmed by portal documentation)", json_schema_extra={"example": "legacy"})
    dt_code: str = Field(..., description="Distribution transformer code", json_schema_extra={"example": "DT-001"})
    coordinates: Optional[Coordinates] = None


class MeterDetail(MeterSummary):
    hierarchy: Optional[MeterHierarchy] = None
    data_quality_flags: List[str] = Field(default_factory=list, description="Quality flags for anomalies found in portal record")


class EnergyReading(BaseModel):
    timestamp: datetime = Field(..., description="End of 30-minute interval in ISO-8601 IST (+05:30)", json_schema_extra={"example": "2026-06-25T00:30:00+05:30"})
    kwh_reading: float = Field(..., description="Cumulative active energy register reading in kWh", json_schema_extra={"example": 48459.87})
    kvah_reading: float = Field(..., description="Cumulative apparent energy register reading in kVAh", json_schema_extra={"example": 52336.66})
    consumption_kwh: Optional[float] = Field(None, description="Calculated energy consumption during this 30-minute interval (kWh)", json_schema_extra={"example": 0.42})
    voltage_r: Optional[float] = Field(None, description="Inferred R-phase voltage in volts RMS", json_schema_extra={"example": 222.0})


class ConsumptionSummary(BaseModel):
    total_consumption_kwh: float = Field(..., description="Total active energy consumed over the queried period in kWh")
    max_interval_kwh: float = Field(..., description="Peak interval consumption in kWh")
    min_interval_kwh: float = Field(..., description="Lowest interval consumption in kWh")
    average_voltage: Optional[float] = Field(None, description="Average R-phase voltage across all intervals")
    reading_count: int = Field(..., description="Number of interval readings received")


class MeterConsumptionResponse(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    meter_id: str
    from_date: Optional[str] = Field(None, alias="from", description="Query start date")
    to_date: Optional[str] = Field(None, alias="to", description="Query end date")
    summary: ConsumptionSummary
    readings: List[EnergyReading]


class DistributionTransformer(BaseModel):
    code: str = Field(..., description="Unique transformer code", json_schema_extra={"example": "DT-001"})
    name: str = Field(..., description="Transformer location/name", json_schema_extra={"example": "Malviya Nagar DT 1"})
    feeder_code: str = Field(..., description="Upstream feeder code", json_schema_extra={"example": "F-001"})
    capacity_kva: float = Field(..., description="Rated transformer capacity in kVA", json_schema_extra={"example": 100.0})
    assigned_meters_count: int = Field(0, description="Total meters connected to this transformer")


class DistributionTransformerDetail(DistributionTransformer):
    meter_ids: List[str] = Field(default_factory=list, description="IDs of all meters assigned to this DT")


class PaginatedResponse(BaseModel, Generic[T]):
    items: List[T]
    total: int
    page: int
    page_size: int
    total_pages: int


class HealthResponse(BaseModel):
    status: str
    uptime_seconds: float
    portal_authenticated: bool
    cached_meters_count: int
    cached_transformers_count: int
    last_sync_timestamp: Optional[str] = None
    is_stale: bool = Field(False, description="Whether cached data exceeds configured TTL")
    cache_ttl_seconds: int = Field(900, description="Configured cache TTL in seconds")


class SyncResponse(BaseModel):
    status: str = Field(..., json_schema_extra={"example": "success"})
    message: str = Field(..., json_schema_extra={"example": "Data synchronized successfully from Urja portal."})
    meters_synced: int = Field(..., json_schema_extra={"example": 403})
    transformers_synced: int = Field(..., json_schema_extra={"example": 20})
    synced_at: Optional[str] = Field(None, json_schema_extra={"example": "2026-10-29T12:00:00Z"})


# Typed hierarchy tree models
class HierarchyDTNode(BaseModel):
    code: str
    name: str
    meters: List[str]
    meter_count: int


class HierarchyFeederNode(BaseModel):
    code: str
    name: str
    transformers: List[HierarchyDTNode]


class HierarchySubstationNode(BaseModel):
    code: str
    name: str
    feeders: List[HierarchyFeederNode]


class HierarchySubdivisionNode(BaseModel):
    code: str
    name: str
    substations: List[HierarchySubstationNode]


class HierarchyDivisionNode(BaseModel):
    code: str
    name: str
    subdivisions: List[HierarchySubdivisionNode]


class HierarchyCircleNode(BaseModel):
    code: str
    name: str
    divisions: List[HierarchyDivisionNode]


class HierarchyZoneNode(BaseModel):
    code: str
    name: str
    circles: List[HierarchyCircleNode]


class GridHierarchyResponse(BaseModel):
    zones: List[HierarchyZoneNode]
