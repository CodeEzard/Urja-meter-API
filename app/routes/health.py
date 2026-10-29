import time
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import JSONResponse

from app.client import UrjaClient
from app.config import settings
from app.dependencies import get_client, get_service
from app.exceptions import SyncRateLimitError
from app.models import ErrorResponse, HealthResponse, SyncResponse
from app.service import MeterService

router = APIRouter(tags=["System"])


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Service health check",
    description="Check the health of the API service, cache sync state, freshness, and upstream portal connectivity.",
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
        is_stale=service.is_stale,
        cache_ttl_seconds=settings.cache_ttl_seconds,
    )


@router.post(
    "/api/v1/sync",
    response_model=SyncResponse,
    responses={
        429: {"model": ErrorResponse, "description": "Cooldown period active (60s minimum interval)"},
        502: {"model": ErrorResponse, "description": "Upstream sync failure"},
    },
    summary="Trigger cache synchronization",
    description="Force a sync of meters and transformers metadata from the upstream portal. Capped to at most once per 60 seconds.",
)
async def trigger_sync(
    service: MeterService = Depends(get_service),
):
    try:
        await service.ensure_synced(force=True)
        return SyncResponse(
            status="success",
            message="Data synchronized successfully from Urja portal.",
            meters_synced=len(service._meters),
            transformers_synced=len(service._transformers),
            synced_at=service.last_synced_at_iso,
        )
    except SyncRateLimitError as e:
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={"error": "rate_limited", "message": str(e)},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Failed to synchronize data from upstream portal: {str(e)}",
        )
