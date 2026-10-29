from fastapi import APIRouter, Depends

from app.dependencies import get_service
from app.models import ErrorResponse, GridHierarchyResponse
from app.service import MeterService

router = APIRouter(prefix="/api/v1/hierarchy", tags=["Hierarchy"])


@router.get(
    "",
    response_model=GridHierarchyResponse,
    responses={502: {"model": ErrorResponse, "description": "Upstream sync failure"}},
    summary="Get distribution grid hierarchy",
    description="Retrieve the complete reconstructed electrical grid hierarchy from Zone down to Feeder, Transformer, and Meters.",
)
async def get_grid_hierarchy(
    service: MeterService = Depends(get_service),
) -> GridHierarchyResponse:
    return await service.get_hierarchy_tree()
