# Check-in server — security review and hardening

The check-in server runs on the venue WiFi so volunteer iPads/phones can reach
it. That means anyone on the same network can reach it too. This note records
what an unauthenticated attacker on that network could do against the app as it
stood, and the fixes applied.

## Threat model

The app is served with `python3 app.py` on the check-in Mac, port 8000 open
through the firewall for the LAN. Attacker = anyone able to reach
`http://<mac-ip>:8000`. No credentials or cookies are involved.

## Findings (before hardening)

- **Attendee list + QR join keys were world-readable.** `GET /checkin/search`
  needed no auth and returned each person's `ticket_number` — the exact value
  the QR encodes and the hydration join key. Looping over letters dumped every
  name + ticket number, enough to forge QR codes and impersonate attendees in
  the sponsor PWA.
- **Full PII dump.** The admin `GET /search-attendees` returned complete
  records (name, email, title, company, discount) with no auth.
- **Check-in forgery / label DoS.** `POST /checkin/print` accepted any ticket
  number, including fabricated ones — marking no-shows present, poisoning the
  Bevy export, and firing a real print job each call (label/paper exhaustion).
- **Attendee-data overwrite.** `POST /upload-csv` was unauthenticated; anyone
  could replace `data.csv` and trigger badge regeneration.
- **CSV / formula injection.** Names come from public Bevy registration. A
  registration name like `=cmd|'/c calc'!A1` flowed unescaped into
  `checkins.csv` and the export, executing when opened in Excel/Sheets.
- **Info disclosure.** `GET /list-directories` listed files in the app root;
  several handlers returned `detail=str(e)` leaking internal paths.
- **CORS `*` with credentials.** Allowed cross-origin reads of responses.
- Path traversal on `/badge/{filename}` and `/download-stickers/{filename}`
  was blocked by Starlette's path normalisation, but the handlers did no
  validation of their own.

## Fixes applied

- **Shared-key auth** on every data/action endpoint via a `require_key`
  dependency. The key is read from the `CHECKIN_KEY` environment variable (never
  committed); if unset, a random key is generated at startup and logged rather
  than defaulting to open. Volunteers open `.../checkin?key=<KEY>`; the page
  sends it as an `X-Checkin-Key` header on every request. Constant-time compare.
- **Removed** `/upload-csv`, `/upload-results-hash`, and `/list-directories`.
  The CSV is now imported by hand, so these were pure attack surface.
- **Forged check-ins rejected.** `/checkin/print` now 404s for any ticket
  number not present in `data.csv`, so no bogus labels or fake check-in rows.
- **CSV injection neutralised.** Export cells beginning with a formula trigger
  (`= + - @` / control chars) are prefixed with an apostrophe.
- **Path-traversal guards** added to `/badge` and `/download-stickers`
  (basename-only) as defence in depth.
- **CORS** no longer allows credentials (none are used).

## Operating notes

- Set the key when starting: `CHECKIN_KEY=<something-long> python3 app.py`.
  The volunteer URL, with the key, is printed to the log at startup.
- The key gates the admin endpoints too (`/search-attendees`, `/badge`,
  `/list-badges`, `/generate-stickers`, `/download-stickers`), so the
  pre-event badge-generation UI needs the same key.
- Residual risk: the key is shared and travels in the URL, so treat it like the
  scanner key — rotate it if it leaks, and prefer a fresh key per event.
