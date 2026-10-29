from contextlib import asynccontextmanager
import logging
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.dependencies import get_client, get_service
from app.exceptions import PortalAuthError, PortalRequestError, ResourceNotFoundError
from app.models import ErrorResponse
from app.routes import health_router, hierarchy_router, meters_router, transformers_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("urja_api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: attempt initial sync from portal
    service = get_service()
    try:
        logger.info("Initializing Urja Meter API and attempting initial data synchronization...")
        await service.ensure_synced()
        logger.info(f"Sync complete. Indexed {len(service._meters)} meters and {len(service._transformers)} DTs.")
    except Exception as e:
        logger.warning(f"Initial sync failed on startup ({e}). Will retry on demand.")

    yield

    # Shutdown: cleanly close HTTP client connections
    client = get_client()
    await client.aclose()
    logger.info("Urja API service shut down cleanly.")


app = FastAPI(
    title="Urja Meter Ops Clean API",
    description=(
        "REST API wrapper over the legacy Urja Meter Ops portal. "
        "Normalizes meter telemetry, calculates 30-minute interval consumption deltas, "
        "and reconstructs the distribution grid hierarchy."
    ),
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    responses={
        422: {"model": ErrorResponse, "description": "Validation error"},
    },
)

# Restrict CORS to local development origins (no wildcard)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:8000",
        "http://localhost:8000",
        "http://127.0.0.1:3000",
        "http://localhost:3000",
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


# Exception handlers
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = exc.errors()
    msg = "; ".join(
        f"{'.'.join(str(loc) for loc in err.get('loc', []))}: {err.get('msg', '')}"
        for err in errors
    )
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"error": "validation_error", "message": msg},
    )


@app.exception_handler(ResourceNotFoundError)
async def resource_not_found_handler(request: Request, exc: ResourceNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"error": "not_found", "message": str(exc)},
    )


@app.exception_handler(PortalAuthError)
async def portal_auth_error_handler(request: Request, exc: PortalAuthError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "upstream_auth_failure", "message": str(exc)},
    )


@app.exception_handler(PortalRequestError)
async def portal_request_error_handler(request: Request, exc: PortalRequestError):
    return JSONResponse(
        status_code=status.HTTP_502_BAD_GATEWAY,
        content={"error": "upstream_request_failure", "message": str(exc)},
    )


# Register routes
app.include_router(health_router)
app.include_router(meters_router)
app.include_router(transformers_router)
app.include_router(hierarchy_router)
