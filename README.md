# Urja Meter Ops API

A REST API wrapper around the legacy Urja Meter Ops portal (`https://urja-ops.flockenergy.tech`). It exposes clean JSON endpoints for smart meter metadata, 30-minute interval energy consumption, and the electrical distribution tree.

## Documentation links

- [PROTOCOL.md](PROTOCOL.md): How the portal works, endpoints, auth, and quirks.
- [openapi.json](openapi.json): OpenAPI 3.1 specification for this API.
- [REFLECTION.md](REFLECTION.md): Five-question engineering reflection.
- Interactive docs: available at `http://127.0.0.1:8000/docs` (Swagger UI) and `http://127.0.0.1:8000/redoc`.

## What I built and how it is structured

I built a service that logs into the portal, pulls the full meter list through the bulk export endpoint, caches it in memory, and calculates consumption deltas for interval telemetry.

- `app/config.py`: Loads environment settings (`URJA_PORTAL_URL`, credentials, cache TTL).
- `app/exceptions.py`: Custom error types for auth failures, upstream errors, missing resources, and sync rate limits.
- `app/client.py`: Async HTTP client for the portal. It handles SvelteKit form login, manages the session cookie, refreshes auth before the 60-minute mark, and signs bulk export requests with HMAC-SHA256. It uses an async lock to prevent duplicate logins, but has no request rate-limiting or concurrency queue for outgoing requests.
- `app/models.py`: Pydantic schemas with enums for phase/status, error responses, interval readings, and typed hierarchy trees.
- `app/normalization.py`: Parses un-offset timestamps into IST (+05:30), computes interval consumption deltas (`kwh_t - kwh_{t-1}`), converts coordinate formats, and flags repaired hierarchy data in `data_quality_flags`.
- `app/service.py`: In-memory store that caches the 403 meters and 20 distribution transformers (DTs), handles search and filtering, enforces a 60-second cooldown on manual sync, and builds the grid tree.
- `app/routes/`: Route handlers split into `health.py` (`/health` root probe and `/api/v1/sync`), `meters.py` (`/api/v1/meters`), `transformers.py` (`/api/v1/transformers`), and `hierarchy.py` (`/api/v1/hierarchy`).
- `app/main.py`: FastAPI entrypoint, lifespan startup sync, CORS restricted to localhost, and unified error handlers.
- `tests/`: 24 offline pytest tests (`test_client.py`, `test_normalization.py`, `test_api.py`) backed by fixtures.
- `export_openapi.py`: Script to regenerate `openapi.json` from FastAPI route metadata via `python export_openapi.py`.

## Setup and running

### 1. Requirements and install
Requires Python 3.11+ (tested on Python 3.11.4).
```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# Linux/macOS:
source .venv/bin/activate

pip install -r requirements.txt
pip install -r requirements-dev.txt   # for running tests
```

### 2. Configure credentials
Copy the template file:
```bash
cp .env.example .env
```
Fill in the credentials provided in the take-home assignment brief:
```env
URJA_PORTAL_URL=https://urja-ops.flockenergy.tech
URJA_USERNAME=your_username
URJA_PASSWORD=your_password
CACHE_TTL_SECONDS=900
```

### 3. Run the service
```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

### 4. Run tests and regenerate docs
```bash
pytest -v
python export_openapi.py   # regenerates openapi.json
```

### Security and error handling
- **Security:** This service has no incoming authentication. It binds to `127.0.0.1` by default and restricts CORS to local development origins. `POST /api/v1/sync` enforces a 60-second cooldown to prevent abuse.
- **Unified errors:** All errors (404, 422, 429, 502) return a consistent shape: `{"error": "<error_code>", "message": "<human_description>"}`.

## Sample requests

### List meters (paginated)
```bash
curl -s "http://127.0.0.1:8000/api/v1/meters?phase=single&page=1&page_size=2"
```
```json
{
  "items": [
    {
      "id": "J100000",
      "serial_number": "SE33962",
      "make": "HPL",
      "phase": "single",
      "install_status": "Decommissioned",
      "install_type": "Whole Current",
      "build": "legacy",
      "dt_code": "DT-001",
      "coordinates": {
        "latitude": 26.938961,
        "longitude": 75.830957
      }
    },
    {
      "id": "J100001",
      "serial_number": "GE84132",
      "make": "L&T",
      "phase": "single",
      "install_status": "Installed",
      "install_type": "CT Operated",
      "build": "legacy",
      "dt_code": "DT-002",
      "coordinates": {
        "latitude": 26.822137,
        "longitude": 75.907182
      }
    }
  ],
  "total": 312,
  "page": 1,
  "page_size": 2,
  "total_pages": 156
}
```

### Interval energy consumption
Computes 30-minute interval deltas from cumulative registers:
```bash
curl -s "http://127.0.0.1:8000/api/v1/meters/J100000/consumption?from=2026-06-25&to=2026-06-25"
```
```json
{
  "meter_id": "J100000",
  "from": "2026-06-25",
  "to": "2026-06-25",
  "summary": {
    "total_consumption_kwh": 20.29,
    "max_interval_kwh": 0.43,
    "min_interval_kwh": 0.41,
    "average_voltage": 228.67,
    "reading_count": 48
  },
  "readings": [
    {
      "timestamp": "2026-06-25T00:00:00+05:30",
      "kwh_reading": 48459.45,
      "kvah_reading": 52336.21,
      "consumption_kwh": null,
      "voltage_r": 226.0
    },
    {
      "timestamp": "2026-06-25T00:30:00+05:30",
      "kwh_reading": 48459.87,
      "kvah_reading": 52336.66,
      "consumption_kwh": 0.42,
      "voltage_r": 222.0
    }
  ]
}
```

## Assumptions

- **Timezone:** Assumed to be IST (+05:30) because the portal gives no timezone and the meters sit in Jaipur (see [PROTOCOL.md](PROTOCOL.md)).
- **Voltage unit:** Inferred `voltR` is RMS Volts on the R-phase based on the observed 220-240V values.
- **Register deltas:** Cumulative readings are assumed not to decrease. The first interval delta is null because there is no earlier reading in the queried window.
- **Date ranges:** The `to` query parameter was confirmed to be inclusive through 23:30 (48 readings per day). If `from` and `to` are omitted, the portal defaults to the 7 days preceding the latest data (23/06/2026 to 30/06/2026).
- **Portal account:** Assumed a single shared operator account can serve all downstream queries without session collisions.

## Design decisions and trade-offs

- **Bulk export vs paginated search:** `/portal/meters/search` omits coordinates and electrical hierarchy. Fetching the full dataset without `/portal/export` requires 21 search requests plus 403 SvelteKit page loader requests (424 HTTP requests total), taking over 7 minutes at 1 req/sec. The signed `/portal/export` endpoint returns all 403 meters with coordinates and hierarchy in 1 request.
- **In-memory cache vs external database:** 403 meters take under 2 MB in memory. Adding PostgreSQL or Redis introduces setup friction and external failure points with no performance gain at this scale. A 15-minute TTL was chosen because meter metadata changes on slow maintenance cycles.
- **Interval calculations:** Cumulative register strings force downstream consumers to do delta math and timezone parsing. Computing interval consumption deltas at the API boundary gives consumers ready-to-use numbers.
- **Auth encapsulation:** The client handles SvelteKit form login, session cookie storage, and HMAC signing internally so consumers do not need portal credentials or session cookies.

## Data quality and failure behaviour

- **Blank hierarchy names:** If a node has a code but no name, the service sets the name to the code and tags it with `missing_name_fallback`; if both are missing, it sets code to `"UNKNOWN"` and name to `"Unknown Node"` with `missing_code_fallback`.
- **Duplicate substation codes:** The service preserves codes in meter models. In the hierarchy tree builder, identical codes under the same parent merge, while identical codes under different parents remain separate branches.
- **Missing export on startup:** If `/portal/export` fails when the app starts, the service logs a warning and starts with an empty cache.
- **Missing export at runtime:** If a request requires a cache refresh and the export fails, the service returns HTTP 502 with `{"error": "upstream_request_failure", "message": "..."}`.

## What I skipped

- **Persistent database:** At 403 meters, in-memory caching is sufficient.
- **Write endpoints:** The portal is read-only for field operations; no meter mutation endpoints exist.
- **Downstream authentication:** The service is an internal integration adapter, so user management was omitted.

## What I would improve

- Run a live test past 60 minutes to observe server-side cookie invalidation.
- Add an automated check on `/portal/keys` and export signing to detect upstream changes.
- Add an outgoing queue to throttle live energy requests and protect the portal during bursts.
- Move metadata to PostgreSQL if the meter count exceeds in-memory limits (tens of thousands).

## How I used AI

I used Claude and Antigravity to generate the repetitive parts: the Pydantic models, FastAPI route handlers, offline test fixtures and scaffolding, and the OpenAPI export script. I also used Claude to plan the work, review my documents for gaps and contradictions.

The investigation and the decisions were mine. I explored the portal in the browser and with curl, found the HMAC signing code in the SvelteKit JavaScript bundle, debugged the 401 signature error by tracing the 10-digit epoch seconds in the Network tab, verified that `/portal/meters/search` lacks coordinates and hierarchy entirely, and checked that interval register deltas never decrease on meter J100000. The architectural decisions were also mine: using the signed bulk export instead of hundreds of crawl requests, choosing an in-memory cache at 403 meters, computing interval consumption deltas at the API boundary.

I read the code, ran the tests, and reviewed each AI-written part before keeping it. I rejected suggestions to add heavy extras like an external database or a frontend map dashboard, removed speculative claims like "page drift" that were not backed by my own testing. I can explain how the service works end to end.
