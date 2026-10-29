# Reflection

## What assumptions did you make?

Three guesses I couldn't verify: timestamps are IST (+05:30) because the meters are in Jaipur, `voltR` is volts because values sit near 220–240, and one shared account can serve all queries. Two things I checked: kWh never decreased over a week of readings for J100000 (other meters untested), and `to` includes the whole day (48 readings for one day, 96 for two).

## Which part was the most difficult, and how did you get unstuck?

The export kept returning 401 `signature_invalid` even though I had copied the signing formula from the portal's JavaScript. Comparing my request with the browser's Network tab showed the portal sent a 10-digit timestamp in `x-timestamp`, while my Python sent 13-digit milliseconds. Switching to integer seconds fixed it, and one call returned all 403 meters.

## If you had another day, what would you improve?

I'd tackle what I left unverified: run a test past 60 minutes to see whether sessions end server-side or slide, and add a scheduled (not per-push) check that compares `/portal/keys` and one export page against saved fixtures. I'd also measure latency at low request rates, cap concurrent energy calls, and tidy the hierarchy edge cases.

## What mistake did you make while solving this (there's always one)?

I called the hierarchy strict too early: the UI shows seven fixed levels, so I assumed a clean tree. The export had blank names, mixed casing (`Sub Station` vs `substation`) and Substation 16 with two codes, which crashed my first builder. I rewrote the normalizer to fall back to codes, unify casing and merge duplicates. Now I inspect raw data before modelling.

## If you were reviewing your own submission, what would you criticise?

Three weaknesses. The one-hour session expiry is inferred from the cookie's Max-Age, not tested. The service depends on a hidden export route and an exposed signing secret that the utility could change. Energy queries go straight to the portal with no concurrency cap. In-memory storage is fine for thousands of meters, at tens of thousands I'd move to PostgreSQL.