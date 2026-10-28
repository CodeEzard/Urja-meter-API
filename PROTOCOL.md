# PROTOCOL.md

How the Urja Meter Ops portal (`https://urja-ops.flockenergy.tech`) actually works, as I found it. I kept to about 1 request per second, used read requests only after login, and used IDs the portal gave me.

`$BASE` is the portal URL and `$TOKEN` is the session cookie value from a fresh login.

## Part 1: Exploring the platform

- **Meters page:** a search box and a table of 403 meters (20 per page: ID, serial, make, phase, install status, DT code). Opening a meter shows its nameplate, location, a 7-level hierarchy (Zone down to DT) and a table of 30-minute consumption readings.
- **Transformers page:** a table of DTs (code, name, feeder, capacity in kVA).
- **Export:** the Transformers page has an "Export all meters" button that downloads every meter in one go.

## Part 2: What I saw in the Network tab

- **Before logging in,** the `/login` page already gives away the architecture. Its HTML loads the SvelteKit entry bundles (`/_app/immutable/entry/start...js` and `app...js`), and the route map inside lists every page: `/login`, `/meters`, `/meters/[id]` and `/transformers`. I got this without any cookie (`curl -s "$BASE/login"`).
- The pages load their data from a JSON API under `/portal/...`: `meters/search`, `meters/{id}/geo`, `meters/{id}/energy`, `dts`, `keys` and `export`. The meter detail page also uses a SvelteKit loader (`/meters/{id}/__data.json`).
- Login is a form POST to `/login`. It sets an HttpOnly cookie, `__Secure-better-auth.session_token`, with `Max-Age=3600`. It isn't a JWT.
- The meter list is fixed at 20 rows per page, and there are no sort controls.
- "Export all meters" first fetches a signing secret from `/portal/keys`, then calls `/portal/export` with `x-timestamp` and `x-signature` headers. I worked out the signature from the portal's JS: HMAC-SHA256 over `GET\n/portal/export\npage=1\n{timestamp}`.
- Numbers arrive as strings, and timestamps look like `23/06/2026 23:30` with no timezone.

## Part 3: Confirming with curl

Login (needs `Origin` and `x-sveltekit-action`):
```bash
curl -si -X POST "$BASE/login" -H "Content-Type: application/x-www-form-urlencoded" -H "Origin: $BASE" -H "x-sveltekit-action: true" -d "email=$URJA_EMAIL&password=$URJA_PASSWORD"
```
Returns 200 with a redirect inside the JSON and the session cookie. Reads only need that cookie.

Search and pagination:
```bash
curl -s "$BASE/portal/meters/search?q=&page=1" -H "Cookie: __Secure-better-auth.session_token=$TOKEN"
```
403 meters, 20 per page, sorted by ID, no gaps or duplicates across 21 pages. Search is case-insensitive and partial.

Energy readings:
```bash
curl -s "$BASE/portal/meters/J100000/energy?from=2026-06-25&to=2026-06-26" -H "Cookie: __Secure-better-auth.session_token=$TOKEN"
```
30-minute cumulative readings, 7 days by default and 1440 at most. `from`/`to` only work as `YYYY-MM-DD` and anything else is silently ignored.

Bulk export (signed):
```bash
curl -s "$BASE/portal/export?page=1" -H "Cookie: __Secure-better-auth.session_token=$TOKEN" -H "x-timestamp: $TS" -H "x-signature: $SIG"
```
One call returns all 403 meters with hierarchy and coordinates, and an invalid signature gives 401.

Not found:
```bash
curl -si "$BASE/portal/meters/NONEXISTENT_METER_999999/geo" -H "Cookie: __Secure-better-auth.session_token=$TOKEN"
```
404 JSON here, but the `__data.json` route returns 200 with the error inside.

## Energy data and what I assume it means

```json
{"data":[{"timestamp":"23/06/2026 23:30","kwh":"48438.74","kvah":"52313.84","voltR":"226"}]}
```
- `kwh` and `kvah` are cumulative register readings, so usage in an interval is the difference between two readings. I checked that they only go up and that the differences add up (48580.79 - 48438.74 = 142.05 kWh).
- The timestamp is local time (IST, +05:30) at the end of the interval. The portal doesn't say so, I'm assuming it because the meters are in Jaipur and no offset is given.

## Quirks that surprised me

- `/portal/keys` hands the export signing secret to any logged-in user, so the signature doesn't really protect anything.
- Geo is `latitude`/`longitude` strings from `/geo` but `lat`/`lng` numbers in the export. Hierarchy labels differ too (`Sub Station` vs `substation`).
- The hierarchy data is messy: some nodes have an empty name or code, and `Substation 16` appears with two codes.
- Page size overrides and non-ISO dates are ignored silently, with no error.

## Not checked yet

What happens after the one-hour session, whether sign-out kills the cookie, and whether the 7-day and 30-day windows are measured from the latest data or from today.
