from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import get_service
from app.exceptions import ResourceNotFoundError
from app.models import DistributionTransformer, DistributionTransformerDetail
from app.service import MeterService

router = APIRouter(prefix="/api/v1/transformers", tags=["Transformers"])


@router.get(
    "",
    response_model=List[DistributionTransformer],
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
    summary="Get transformer details",
    description="Retrieve details for a specific distribution transformer, including all assigned meter IDs.",
)
async def get_transformer(
    code: str,
    service: MeterService = Depends(get_service),
):
    return await service.get_transformer(code)
