import time
from fastapi import APIRouter, Depends, HTTPException, status

from app.client import UrjaClient
from app.dependencies import get_client, get_service
from app.models import HealthResponse
from app.service import MeterService

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Check the health of the API service, cache sync state, and upstream portal connectivity.",
)
async def health_check(
    service: MeterService = Depends(get_service),
    client: UrjaClient = Depends(get_client),
):
    is_authed = bool(client._client.cookies.get("__Secure-better-auth.session_token"))
    uptime = round(time.time() - service.started_at, 1)

    return HealthResponse(
        status="healthy",
        uptime_seconds=uptime,
        portal_authenticated=is_authed,
        cached_meters_count=len(service._meters),
        cached_transformers_count=len(service._transformers),
        last_sync_timestamp=service.last_synced_at_iso,
    )


@router.post(
    "/api/v1/sync",
    summary="Trigger cache synchronization",
    description="Force a sync of meters and transformers metadata from the upstream portal.",
)
async def trigger_sync(
    service: MeterService = Depends(get_service),
):
    try:
        await service.ensure_synced(force=True)
        return {
            "status": "success",
            "message": "Data synchronized successfully from Urja portal.",
            "meters_synced": len(service._meters),
            "transformers_synced": len(service._transformers),
            "synced_at": service.last_synced_at_iso,
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to synchronize data from upstream portal: {str(e)}",
        )
