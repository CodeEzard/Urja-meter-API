# PROTOCOL.md

How the Urja Meter Ops portal (`https://urja-ops.flockenergy.tech`) works, as I found it. Findings are tagged **[OBSERVED]** (verified with curl or tests) or **[INFERRED]** (deduced from evidence, not directly verified).

Meter data appears synthetic; no real credentials, session cookies, or signing secrets are in this repository.

## What the portal offers

The portal has three main sections:
- **Meters page:** Search box and a table of 403 meters (20 per page). Opening a meter shows its nameplate, coordinates, a 7-level hierarchy, and 30-minute interval readings.
- **Transformers page:** A table of 20 distribution transformers (DTs) with code, name, feeder, and capacity.
- **Export button:** A button on the Transformers page that downloads all 403 meters in one file.

## Access and authentication

- **Architecture [OBSERVED]:** The frontend is SvelteKit. Route definitions (`/login`, `/meters`, `/meters/[id]`, `/transformers`) are visible in the public JS bundle (`/_app/immutable/entry/start...js`).
- **Login [OBSERVED]:** POST to `/login` with `Origin: https://urja-ops.flockenergy.tech` and `x-sveltekit-action: true`. Payload is form-encoded `email` and `password`.
- **Session cookie [OBSERVED]:** Returns 200 with JSON `{"type":"redirect","status":303,"location":"/meters"}` and sets an HttpOnly cookie named `__Secure-better-auth.session_token` with `Max-Age=3600`.
- **Session lifecycle [INFERRED]:** The cookie indicates a 60-minute lifetime. Server-side revocation at 3600 seconds is inferred. An invalid cookie returns 401 `{"error":"unauthorized","message":"A valid session is required."}` **[OBSERVED]**.
- **Concurrent sessions [INFERRED]:** Whether a second login revokes the first session is untested.

## Endpoint reference

All JSON endpoints live under `/portal/` and require the session cookie.

| Method | Path | Auth / Headers | Returns | Notes |
| :--- | :--- | :--- | :--- | :--- |
| `POST` | `/login` | `Origin`, `x-sveltekit-action: true` | `200` + session cookie | Form POST. Redirects to `/meters`. |
| `GET` | `/portal/meters/search` | Session cookie | JSON (`data`, `total`: 403) | 20 meters/page (`q=`, `page=1..21`). Case-insensitive partial search. |
| `GET` | `/portal/meters/{id}/geo` | Session cookie | JSON (`latitude`, `longitude`) | Coordinates as strings. Returns 404 for missing meter. |
| `GET` | `/portal/meters/{id}/energy` | Session cookie | JSON (`data`: cumulative rows) | Query params `from` and `to` (`YYYY-MM-DD`). Max 1440 rows. |
| `GET` | `/portal/dts` | Session cookie | JSON (`data`: 20 DTs) | Code, name, feederCode, capacityKva. |
| `GET` | `/portal/keys` | Session cookie | JSON (`data.signingSecret`) | Returns HMAC signing secret for export. |
| `GET` | `/portal/export` | Cookie, `x-timestamp`, `x-signature` | JSON (`data`: 403 meters) | Returns all 403 meters with coordinates and hierarchy. |
| `GET` | `/meters/{id}/__data.json` | Session cookie | SvelteKit JSON | Frontend loader. Returns 200 with error object on 404. |

## Formats and units

- **Cumulative registers [OBSERVED]:** `kwh` and `kvah` are cumulative register totals as decimal strings. Interval consumption is the difference between two readings: `kwh_t - kwh_{t-1}`. On meter J100000 across 336 intervals, no delta was negative, and every apparent energy delta was greater than or equal to the real energy delta. The first delta in any window is null because it lacks an earlier baseline. Behavior across all other 402 meters is inferred **[INFERRED]**.
- **Timestamps [INFERRED]:** Strings formatted as `DD/MM/YYYY HH:mm` at interval end. Local time is inferred to be IST (+05:30) because the meters are in Jaipur.
- **Voltage [INFERRED]:** `voltR` is inferred to be Volts RMS on the R-phase based on the observed ~220-240V range.
- **Date ranges [OBSERVED]:** `from` and `to` require `YYYY-MM-DD`. The `to` parameter is inclusive through 23:30 (requesting one day returns 48 rows, two days returns 96 rows). Non-ISO dates fallback silently to the 7-day default.
- **Coordinates [OBSERVED]:** Strings on `/geo` (`latitude`, `longitude`), numbers on `/export` (`lat`, `lng`).
- **Hierarchy [OBSERVED]:** Casing varies (`Sub Station` vs `substation`), some names are blank, and Substation 16 has two distinct codes.

## Why use the export endpoint

The search endpoint (`/portal/meters/search`) only returns basic nameplate fields. It omits coordinates and electrical hierarchy entirely. No `/portal/` hierarchy endpoint exists; hierarchy only appears in SvelteKit's `__data.json` loaders.

Fetching the full dataset without `/portal/export` requires:
- 21 search requests to collect meter IDs
- 403 requests to `/meters/{id}/__data.json` for hierarchy and coordinates

That is 424 HTTP requests. Paced at 1 request per second, it takes over 7 minutes. In contrast, the signed `/portal/export` endpoint returns all 403 meters with coordinates and hierarchy in 1 request[OBSERVED].

## Quirks and implementation notes

- **HMAC signature [OBSERVED]:** `/portal/export` requires `x-timestamp` and `x-signature` headers:
```
HMAC-SHA256(key=data.signingSecret, data="GET\n/portal/export\npage=1\n" + timestamp)
```
The timestamp must be integer UNIX epoch seconds (10 digits). Millisecond timestamps return 401 `signature_invalid`.
- **Export ignores page [OBSERVED]:** Calling `/portal/export?page=2` returns the exact same 403 meters as `page=1`.
- **Open signing key [OBSERVED]:** `/portal/keys` gives the secret to any authenticated session.
- **Missing resources [OBSERVED]:** Nonexistent meters on `/geo` and `/energy` return 404 JSON `{"error":"not_found","message":"Meter not found"}`. SvelteKit `__data.json` returns 200 with an error payload. The portal has no `/portal/dts/{code}` route; calling one returns SvelteKit's default HTML 404 page.

## Open questions

1. Whether the server revokes the session after 3600 seconds or allows a sliding window.
2. How often `signingSecret` rotates, if ever.
3. The server's clock-skew tolerance on `x-timestamp`.

## How to reproduce

Set `$BASE="https://urja-ops.flockenergy.tech"` and export `$URJA_USERNAME` and `$URJA_PASSWORD`. All calls used IDs the portal gave me, apart from one deliberately invalid ID to test 404 responses.

```bash
# 1. Login and get session cookie
curl -si -X POST "$BASE/login" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -H "Origin: $BASE" \
  -H "x-sveltekit-action: true" \
  -d "email=$URJA_USERNAME&password=$URJA_PASSWORD"

# 2. Get signing secret, calculate signature, and export all meters
SECRET=$(curl -s "$BASE/portal/keys" -H "Cookie: __Secure-better-auth.session_token=$COOKIE" | jq -r '.data.signingSecret')
TS=$(date +%s)
SIG=$(printf "GET\n/portal/export\npage=1\n$TS" | openssl dgst -sha256 -hmac "$SECRET" | awk '{print $2}')

curl -s "$BASE/portal/export?page=1" \
  -H "Cookie: __Secure-better-auth.session_token=$COOKIE" \
  -H "x-timestamp: $TS" \
  -H "x-signature: $SIG"

# 3. Fetch 30-minute energy intervals
curl -s "$BASE/portal/meters/J100000/energy?from=2026-06-25&to=2026-06-26" \
  -H "Cookie: __Secure-better-auth.session_token=$COOKIE"

# 4. Verify 404 on missing meter
curl -si "$BASE/portal/meters/NONEXISTENT_999999/energy" \
  -H "Cookie: __Secure-better-auth.session_token=$COOKIE"
```
