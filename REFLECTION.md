# Reflection

## What assumptions did you make?

Three of my choices are assumptions I could not verify. The portal timestamps have no timezone, so I treat them as Indian Standard Time (+05:30) because the meters sit in Jaipur. I read voltR as RMS volts on the R-phase because the values sit around 220–240 V. I also assume the shared operator account can serve all downstream queries without the portal limiting concurrent sessions. Two other points I did check: kWh readings never decreased across the 336 intervals I pulled for meter J100000 (I assume the other 402 meters behave the same, and the first delta in any window is null because it lacks an earlier reading), and the "to" date includes the whole day, since one day returns 48 readings and two days return 96.

## Which part was the most difficult, and how did you get unstuck?

Getting the bulk export HMAC signature to validate was the trickiest hurdle. Initial calls to /portal/export returned a 401 signature error despite matching the canonical string extracted from the SvelteKit JavaScript bundle. What pointed me to the fix was inspecting the raw Network tab in Chrome while clicking the export button on the Transformers page. The browser sent a 10-digit integer in x-timestamp (like 1793226769), whereas my client was sending standard 13-digit millisecond timestamps from epoch math. Switching the timestamp format and HMAC digest input to integer seconds immediately resolved the 401 and let the export return all 403 meters in one request.

## If you had another day, what would you improve?

Given more time, I would address specific unverified behaviors rather than adding new features. I would run an automated test past the 60-minute mark to observe whether the portal invalidates the session server-side or supports a sliding window. I would also add a scheduled check that pulls /portal/keys and one signed export page and compares the schema against saved fixtures, alerting if the utility changes the contract while staying gentle on the server. To protect the portal, I would measure upstream latency at low request rates and add an outgoing queue to cap how many energy queries run at once. Finally, I would harden hierarchy cleanup for missing names and duplicate substation codes.

## What mistake did you make while solving this (there's always one)?

I called the hierarchy strict too early. The portal UI shows every meter with the same seven levels, Zone down to DT, and in my initial notes I treated that as a fixed, reliable tree. When I inspected the export data, several nodes had empty string names, labels differed across routes (Sub Station versus substation), and Substation 16 appeared with two distinct codes. My first tree builder crashed with a KeyError on missing names, then split Substation 16 into duplicate branches. I had to rewrite the normalizer to fall back to node codes for missing names, standardize casing, and merge identical codes under the same parent. Since then, I check raw data before modeling it.

## If you were reviewing your own submission, what would you criticise?

I would criticize three real weaknesses in this submission. My claim that sessions expire after one hour is inferred only from the cookie's Max-Age header, not verified by waiting out the clock. Second, the entire service depends on a hidden export route and an exposed signing secret that the utility could change or remove without notice. Third, while meter metadata is cached in memory, energy queries pass directly through to the portal without a concurrency queue to protect the legacy server during batch requests. In-memory storage is fine at 403 meters and would stay fine for thousands. At tens of thousands, I would move metadata and time-series storage to PostgreSQL.
