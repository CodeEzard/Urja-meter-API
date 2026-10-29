from typing import List, Optional
from fastapi import APIRouter, Depends, Query

from app.dependencies import get_service
from app.models import DistributionTransformer, DistributionTransformerDetail, ErrorResponse
from app.service import MeterService

router = APIRouter(prefix="/api/v1/transformers", tags=["Transformers"])


@router.get(
    "",
    response_model=List[DistributionTransformer],
    responses={502: {"model": ErrorResponse, "description": "Upstream communication error"}},
    summary="List distribution transformers",
    description="Retrieve distribution transformers (DTs), including capacity, feeder association, and count of connected meters.",
)
async def list_transformers(
    feeder_code: Optional[str] = Query(None, description="Filter by upstream feeder code (e.g. F-001)"),
    service: MeterService = Depends(get_service),
):
    return await service.list_transformers(feeder_code=feeder_code)


@router.get(
    "/{code}",
    response_model=DistributionTransformerDetail,
    responses={
        404: {"model": ErrorResponse, "description": "Distribution transformer not found"},
        502: {"model": ErrorResponse, "description": "Upstream communication error"},
    },
    summary="Get transformer details",
    description="Retrieve details for a specific distribution transformer, including all assigned meter IDs.",
)
async def get_transformer(
    code: str,
    service: MeterService = Depends(get_service),
):
    return await service.get_transformer(code)
