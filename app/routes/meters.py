from typing import Optional
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_service
from app.models import (
    ErrorResponse,
    InstallStatus,
    MeterDetail,
    MeterSummary,
    MeterConsumptionResponse,
    PaginatedResponse,
    PhaseType,
)
from app.service import MeterService

router = APIRouter(prefix="/api/v1/meters", tags=["Meters"])


@router.get(
    "",
    response_model=PaginatedResponse[MeterSummary],
    responses={502: {"model": ErrorResponse, "description": "Upstream communication error"}},
    summary="List and filter smart meters",
    description="Retrieve a paginated list of smart meters with optional filtering by query, DT code, phase, status, or make.",
)
async def list_meters(
    q: Optional[str] = Query(None, description="Free text search across ID, serial number, make, or DT code"),
    dt_code: Optional[str] = Query(None, description="Filter by Distribution Transformer code (e.g. DT-001)"),
    phase: Optional[PhaseType] = Query(None, description="Filter by electrical phase"),
    status_filter: Optional[InstallStatus] = Query(None, alias="status", description="Filter by operational status"),
    make: Optional[str] = Query(None, description="Filter by meter manufacturer (e.g. HPL, L&T, Genus, Secure, Allied)"),
    page: int = Query(1, ge=1, description="Page number (1-indexed)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    service: MeterService = Depends(get_service),
):
    return await service.list_meters(
        query=q,
        dt_code=dt_code,
        phase=phase.value if phase else None,
        status=status_filter.value if status_filter else None,
        make=make,
        page=page,
        page_size=page_size,
    )


@router.get(
    "/{meter_id}",
    response_model=MeterDetail,
    responses={
        404: {"model": ErrorResponse, "description": "Meter not found"},
        502: {"model": ErrorResponse, "description": "Upstream communication error"},
    },
    summary="Get meter details",
    description="Retrieve full details for a single meter, including normalized geo coordinates and full 7-level electrical hierarchy.",
)
async def get_meter(
    meter_id: str,
    service: MeterService = Depends(get_service),
):
    return await service.get_meter(meter_id)


@router.get(
    "/{meter_id}/consumption",
    response_model=MeterConsumptionResponse,
    responses={
        404: {"model": ErrorResponse, "description": "Meter not found"},
        502: {"model": ErrorResponse, "description": "Upstream communication error"},
    },
    summary="Get interval energy consumption",
    description=(
        "Retrieve 30-minute interval readings for a meter. "
        "Calculates delta active consumption (kWh) per interval and provides aggregate statistics."
    ),
)
async def get_meter_consumption(
    meter_id: str,
    from_date: Optional[str] = Query(
        None,
        alias="from",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="Start date in YYYY-MM-DD format (e.g., 2026-06-25)",
    ),
    to_date: Optional[str] = Query(
        None,
        alias="to",
        pattern=r"^\d{4}-\d{2}-\d{2}$",
        description="End date in YYYY-MM-DD format (e.g., 2026-06-26)",
    ),
    service: MeterService = Depends(get_service),
):
    return await service.get_meter_consumption(
        meter_id=meter_id,
        from_date=from_date,
        to_date=to_date,
    )
