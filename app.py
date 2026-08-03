from fastapi import FastAPI, UploadFile, File, HTTPException, Depends, Query, Header
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import os
import secrets
from typing import Optional
import shutil
from pydantic import BaseModel
from card_types import load_roles, resolve_card_type
from confbadger import createBadge, read_data_file, get_data_from_ticket_numbers
from generate_stickers import generate_stickers
from print_label import print_via_cups, QUEUE, LABEL
import csv
from datetime import datetime, timezone
import logging
import glob
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.DEBUG)

# ---------- shared-key auth ----------
# The check-in server runs on the venue WiFi, where anyone can reach it. A
# single shared key gates every data/action endpoint. Volunteers get it once,
# in the URL (http://<host>:8000/checkin?key=...), just like the sponsor
# scanner. The key is read from the environment so it is never committed; if
# it is not set we mint a random one at startup and log it, rather than ever
# defaulting to "open".
CHECKIN_KEY = (os.environ.get("CHECKIN_KEY") or "").strip()
if not CHECKIN_KEY:
    CHECKIN_KEY = secrets.token_urlsafe(9)
    logger.warning("CHECKIN_KEY not set — generated a temporary key: %s", CHECKIN_KEY)


def require_key(
    key: Optional[str] = Query(default=None),
    x_checkin_key: Optional[str] = Header(default=None),
):
    """Accept the shared key from either the ?key= query param (so a volunteer
    can bookmark the whole URL) or an X-Checkin-Key header (what the page sends
    on its fetches). Constant-time compare to avoid leaking the key by timing."""
    supplied = x_checkin_key or key or ""
    if not secrets.compare_digest(supplied, CHECKIN_KEY):
        raise HTTPException(status_code=401, detail="Invalid or missing key")


# CORS: no cookies are used (auth is the shared key, sent explicitly), so we
# don't allow credentials. A cross-origin site still can't read anything
# without the key.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create necessary directories if they don't exist
os.makedirs("badges", exist_ok=True)
os.makedirs("codes", exist_ok=True)
os.makedirs("temp", exist_ok=True)

@app.on_event("startup")
async def clean_temp_folder():
    for file_path in glob.glob("temp/*.csv"):
        try:
            os.remove(file_path)
        except Exception as e:
            print(f"Failed to delete {file_path}: {e}")


@app.on_event("startup")
async def announce_checkin_url():
    # Print the volunteers' link once, so it's easy to copy from the terminal.
    # Replace <mac-ip> with the Mac's LAN address (System Settings → Network).
    logger.info("Check-in ready. Share this with volunteers (swap in the Mac's LAN IP):")
    logger.info("    http://<mac-ip>:8000/checkin?key=%s", CHECKIN_KEY)

# /upload-results-hash and /list-directories were removed — on the venue WiFi
# they let anyone enumerate files or overwrite scan results. /upload-csv is kept
# but now requires the shared key, so only an operator can replace the attendee
# data. See check-in-security-review.md.

@app.post("/upload-csv", dependencies=[Depends(require_key)])
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")

    logger.info(f"Received file upload: {file.filename}")

    # Basename only — never let an uploaded filename escape temp/.
    safe_name = os.path.basename(file.filename)
    temp_file_path = f"temp/{safe_name}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    logger.info(f"Saved uploaded file to {temp_file_path}")

    try:
        # Read the CSV to validate it
        df = read_data_file(temp_file_path)
        required_columns = ["Ticket number", "First Name", "Last Name", "Email", "Company", "Title", "Ticket title"]

        logger.info(f"CSV columns: {', '.join(df.columns)}")

        if not all(col in df.columns for col in required_columns):
            missing = [col for col in required_columns if col not in df.columns]
            error_msg = f"CSV missing required columns: {', '.join(missing)}"
            logger.error(error_msg)
            raise HTTPException(status_code=400, detail=error_msg)

        # Move the file to the main directory
        shutil.move(temp_file_path, "data.csv")
        logger.info("Moved temp file to data.csv")

        # Generate badges
        logger.info("Calling createBadge with save_path='codes'")
        try:
            badge_count = createBadge(save_path="codes")
            logger.info(f"createBadge returned: {badge_count} badges created")
        except Exception as e:
            logger.error(f"Error using createBadge with save_path='codes': {str(e)}")
            logger.info("Trying with default parameters...")
            try:
                badge_count = createBadge()
                logger.info(f"Success with default parameters: {badge_count} badges created")
            except Exception as e2:
                logger.error(f"Error using createBadge with default parameters: {str(e2)}")
                # As a last resort, try running the script directly
                logger.info("Trying with command line execution...")
                try:
                    os.system("python3 confbadger.py --data data.csv")
                    logger.info("Command line execution completed")
                    badge_count = len(os.listdir("badges"))
                except Exception as e3:
                    logger.error(f"Command line execution failed: {str(e3)}")
                    raise HTTPException(status_code=500, detail=f"Failed to generate badges: {str(e)} -> {str(e2)} -> {str(e3)}")

        # Check if badges were created
        badge_count = len(os.listdir("badges"))
        logger.info(f"Badge generation complete. {badge_count} badges in badges/")
        code_count = len(os.listdir("codes"))
        logger.info(f"QR code generation complete. {code_count} QR codes in codes/")

        return {"message": f"Badges generated successfully. {badge_count} badges created."}
    except Exception as e:
        logger.error(f"Error during badge generation: {str(e)}")
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/search-attendees", dependencies=[Depends(require_key)])
async def search_attendees(
    name: Optional[str] = None,
    title: Optional[str] = None,
    company: Optional[str] = None,
    ticket_type: Optional[str] = None
):
    try:
        df = read_data_file("data.csv")
        # Apply filters
        if name:
            # Convert name to lowercase for case-insensitive search
            name = name.lower()
            # Create a mask for first name or last name containing the search term
            name_mask = (
                df["First Name"].str.lower().str.contains(name, na=False) |
                df["Last Name"].str.lower().str.contains(name, na=False)
            )
            df = df[name_mask]
            
        if title:
            df = df[df["Title"].str.contains(title, case=False, na=False)]
        if company:
            df = df[df["Company"].str.contains(company, case=False, na=False)]
        if ticket_type:
            df = df[df["Ticket title"].str.contains(ticket_type, case=False, na=False)]
        
        ret = df.to_dict(orient="records")
        logger.debug(f"Search ret: {ret}")
        return df.to_dict(orient="records")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/badge/{filename}", dependencies=[Depends(require_key)])
async def get_badge(filename: str):
    # Guard against path traversal: only a bare filename inside badges/ is
    # allowed. (Starlette normalises most traversal today, but validate here
    # too so the handler is safe regardless of routing quirks.)
    if filename != os.path.basename(filename) or filename in ("", ".", ".."):
        raise HTTPException(status_code=400, detail="Invalid filename")
    badge_path = os.path.join("badges", filename)
    if not os.path.exists(badge_path):
        raise HTTPException(status_code=404, detail="Badge not found")
    return FileResponse(badge_path)

@app.get("/list-badges", dependencies=[Depends(require_key)])
async def list_badges():
    try:
        badges = os.listdir("badges")
        return {"badges": badges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def stickers_enabled():
    try:
        with open("config.yaml") as f:
            config_data = yaml.safe_load(f) or {}
    except Exception as e:
        logger.warning("Could not load config.yaml: %s. Assuming stickers enabled.", e)
        return True
    return config_data.get("sticker-labels", {}).get("enabled", True)


def require_stickers_enabled():
    if not stickers_enabled():
        raise HTTPException(status_code=403, detail="Sticker sheet generation is disabled")


@app.get("/features")
async def features():
    return {"stickers": stickers_enabled()}


@app.post("/generate-stickers", dependencies=[Depends(require_key)])
async def generate_stickers_endpoint(
    since: Optional[str] = None,
    after: Optional[str] = None
):
    """Generate stickers PDF from uploaded CSV with optional date/order filters"""
    require_stickers_enabled()
    try:
        csv_file = "data.csv"
        if not os.path.exists(csv_file):
            raise HTTPException(status_code=404, detail="No CSV file uploaded yet")
        
        # Generate output filename based on input
        csv_basename = os.path.splitext(os.path.basename(csv_file))[0]
        output_file = f"{csv_basename}-stickers.pdf"
        
        logger.info(f"Generating stickers: csv={csv_file}, output={output_file}, since={since}, after={after}")
        
        # Generate stickers
        generate_stickers(
            csv_file=csv_file,
            output_file=output_file,
            config_file="config.yaml",
            debug=False,
            since=since,
            after=after
        )
        
        if not os.path.exists(output_file):
            raise HTTPException(status_code=500, detail="Failed to generate stickers PDF")
        
        logger.info(f"Stickers generated successfully: {output_file}")
        return {"message": "Stickers generated successfully", "filename": output_file}
    
    except Exception as e:
        logger.error(f"Error generating stickers: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download-stickers/{filename}", dependencies=[Depends(require_key)])
async def download_stickers(filename: str):
    """Download the generated stickers PDF"""
    require_stickers_enabled()
    # Only a bare filename with the expected suffix — no path traversal.
    if filename != os.path.basename(filename) or not filename.endswith("-stickers.pdf"):
        raise HTTPException(status_code=400, detail="Invalid stickers filename")

    if not os.path.exists(filename):
        raise HTTPException(status_code=404, detail="Stickers file not found")
    
    return FileResponse(
        filename,
        media_type="application/pdf",
        filename=filename
    )

# ---------- check-in endpoints (Phase 4 Stage 2) ----------

#: Label stock loaded on the QL-810W. "62x29" = DK-11209 die-cut (production);
#: "62" = DK-22205 continuous (stand-in). print_via_cups maps this to the right
#: CUPS PageSize, so the endpoint and the print_label.py CLI stay in lockstep.
_CHECKIN_LABEL = LABEL          # "62x29" — DK-11209 die-cut
_CUPS_QUEUE = QUEUE             # "Brother_QL_810W"

DATA_CSV = "data.csv"

#: Append-only check-in log. One row is written the moment a label is
#: successfully sent to the printer (the operator has tapped Print), so this is
#: the record of who showed up. Re-prints append another row; the export
#: endpoint dedupes by ticket number, keeping the first (earliest) check-in.
CHECKINS_CSV = "checkins.csv"
_CHECKINS_HEADER = ["ticket_number", "first_name", "checked_in_at"]


def _record_checkin(ticket_number: str, first_name: str) -> None:
    """Append a check-in row with an ISO-8601 UTC timestamp. Best-effort: a
    logging failure must never stop a badge from printing, so callers wrap this
    so the attendee still gets their label if the disk write hiccups."""
    new_file = not os.path.exists(CHECKINS_CSV)
    with open(CHECKINS_CSV, "a", newline="", encoding="utf-8") as fh:
        writer = csv.writer(fh)
        if new_file:
            writer.writerow(_CHECKINS_HEADER)
        writer.writerow([
            ticket_number,
            first_name,
            datetime.now(timezone.utc).isoformat(timespec="seconds"),
        ])


class PrintRequest(BaseModel):
    first_name: str
    ticket_number: str


@app.get("/checkin")
async def checkin_page():
    return FileResponse(os.path.join(_HERE, "checkin.html"))


def _ticket_exists(ticket_number: str) -> bool:
    """True if the ticket number is present in the loaded attendee data. Used to
    reject forged/garbage check-ins so nobody can inject fake attendees into the
    Bevy export or spew labels for tickets that don't exist."""
    if not os.path.exists(DATA_CSV):
        return False
    df = read_data_file(DATA_CSV)
    wanted = ticket_number.strip()
    return (df["Ticket number"].astype(str).str.strip() == wanted).any()


#: Below this length an email substring is noise rather than a search: two
#: characters match most of the room, burying the name matches the operator
#: actually wanted and handing a key holder a bulk listing for free.
_EMAIL_SEARCH_MIN = 3


def _mask_email(raw: str) -> str:
    """First character of the local part, then a fixed run of dots, then the
    domain: j...@worlduni.com.

    Enough for an operator to tell two John Smiths apart while reading it off a
    screen, without putting a working address list in front of everyone holding
    the shared key — the PII dump this endpoint was hardened against. The run of
    dots is a fixed length so it doesn't leak how long the local part is.
    """
    addr = (raw or "").strip()
    if "@" not in addr:
        return ""
    local, _, domain = addr.partition("@")
    if not local or not domain:
        return ""
    return f"{local[0]}...@{domain}"


@app.get("/checkin/search", dependencies=[Depends(require_key)])
async def checkin_search(q: str = ""):
    q = q.strip()
    if not q:
        return []
    if not os.path.exists(DATA_CSV):
        raise HTTPException(status_code=503, detail="No attendee data loaded — upload data.csv first")
    df = read_data_file(DATA_CSV)
    ql = q.lower()
    mask = (
        df["First Name"].str.lower().str.contains(ql, na=False, regex=False)
        | df["Last Name"].str.lower().str.contains(ql, na=False, regex=False)
    )
    # Two people share a name often enough that the desk has to ask for an
    # email, so the address is searchable — but it is only ever returned masked.
    if len(ql) >= _EMAIL_SEARCH_MIN:
        mask |= df["Email"].astype(str).str.lower().str.contains(ql, na=False, regex=False)
    rows = df[mask].head(20)
    # Re-read on every search: roles.csv gets corrected during the morning as
    # late volunteers are added, and an edit must take effect without a restart.
    roles = load_roles()
    return [
        {
            "ticket_number": str(row["Ticket number"]),
            "first_name": str(row["First Name"]).strip(),
            "last_name": str(row["Last Name"]).strip(),
            "company": str(row.get("Company", "") or "").strip(),
            "card_type": resolve_card_type(row, roles),
            "email_masked": _mask_email(str(row.get("Email", "") or "")),
        }
        for _, row in rows.iterrows()
    ]


@app.post("/checkin/print", dependencies=[Depends(require_key)])
async def checkin_print(req: PrintRequest):
    if not req.first_name.strip():
        raise HTTPException(status_code=400, detail="first_name is required")
    if not req.ticket_number.strip():
        raise HTTPException(status_code=400, detail="ticket_number is required")
    # Only print for a ticket that actually exists in the attendee data. This
    # stops a forged POST from printing a bogus label or writing a fake
    # check-in row that would corrupt the Bevy upload.
    if not _ticket_exists(req.ticket_number):
        raise HTTPException(status_code=404, detail="Unknown ticket number")
    try:
        # Reuse the one print path proven on our unit (PRINTER_HANDOFF.md): render
        # the true-size bitmap and hand it to CUPS at ppi=300 so the QR lands 1:1.
        job = print_via_cups(
            req.first_name.strip(),
            req.ticket_number.strip(),
            label=_CHECKIN_LABEL,
            queue=_CUPS_QUEUE,
        )
    except Exception as exc:
        logger.error("print failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc))
    # The label is out; record the check-in. Never let a log write failure
    # surface as a print error — the attendee already has their badge.
    try:
        _record_checkin(req.ticket_number.strip(), req.first_name.strip())
    except Exception as exc:
        logger.error("check-in log write failed for %s: %s", req.ticket_number, exc)
    return {"ok": True, "job": job}


def _deduped_checkins():
    """Read the append-only log and collapse re-prints to one row per ticket,
    keeping the earliest check-in time. Rows are returned newest-first."""
    if not os.path.exists(CHECKINS_CSV):
        return []
    first_seen = {}
    with open(CHECKINS_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            ticket = (row.get("ticket_number") or "").strip()
            if not ticket:
                continue
            ts = (row.get("checked_in_at") or "").strip()
            existing = first_seen.get(ticket)
            # Keep the earliest timestamp for each ticket.
            if existing is None or (ts and ts < existing["checked_in_at"]):
                first_seen[ticket] = {
                    "ticket_number": ticket,
                    "first_name": (row.get("first_name") or "").strip(),
                    "checked_in_at": ts,
                }
    return sorted(
        first_seen.values(), key=lambda r: r["checked_in_at"], reverse=True
    )


@app.get("/checkin/list", dependencies=[Depends(require_key)])
async def checkin_list():
    """JSON list of checked-in attendees (deduped), plus a count."""
    rows = _deduped_checkins()
    return {"count": len(rows), "checkins": rows}


def _csv_safe(value: str) -> str:
    """Neutralise spreadsheet formula injection. Names come from public Bevy
    registration, so a value like =cmd|... would execute if the export is
    opened in Excel/Sheets. Prefix any cell starting with a formula trigger
    with an apostrophe so the spreadsheet treats it as text."""
    s = "" if value is None else str(value)
    if s and s[0] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + s
    return s


@app.get("/checkin/export", dependencies=[Depends(require_key)])
async def checkin_export():
    """Download the checked-in attendees as a CSV for upload to Bevy. One row
    per ticket number, earliest check-in time."""
    rows = _deduped_checkins()
    out_path = "checkins-export.csv"
    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=_CHECKINS_HEADER)
        writer.writeheader()
        writer.writerows(
            {k: _csv_safe(v) for k, v in row.items()} for row in rows
        )
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    return FileResponse(
        out_path,
        media_type="text/csv",
        filename=f"kcd-checkins-{stamp}.csv",
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)