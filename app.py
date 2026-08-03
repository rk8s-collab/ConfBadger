from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import os
from typing import Optional
import shutil
from pydantic import BaseModel
from confbadger import createBadge, read_data_file, get_data_from_ticket_numbers
from generate_stickers import generate_stickers
from print_label import print_via_cups, QUEUE, LABEL
import logging
import glob
import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI()
logger = logging.getLogger("uvicorn")
logger.setLevel(logging.DEBUG)

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
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

@app.post("/upload-csv")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    logger.info(f"Received file upload: {file.filename}")
    
    # Save the uploaded file temporarily
    temp_file_path = f"temp/{file.filename}"
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

@app.get("/search-attendees")
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

@app.get("/badge/{filename}")
async def get_badge(filename: str):
    badge_path = f"badges/{filename}"
    if not os.path.exists(badge_path):
        raise HTTPException(status_code=404, detail="Badge not found")
    return FileResponse(badge_path)

@app.get("/list-badges")
async def list_badges():
    try:
        badges = os.listdir("badges")
        return {"badges": badges}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload-results-hash")
async def upload_csv(file: UploadFile = File(...)):
    if not file.filename.endswith('.csv'):
        raise HTTPException(status_code=400, detail="File must be a CSV")
    
    # Save the uploaded file temporarily
    temp_file_path = f"temp/{file.filename}"
    with open(temp_file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
    shutil.move(temp_file_path, "post-scan-ticket-numbers.csv")
    df = get_data_from_ticket_numbers()
    os.remove("post-scan-ticket-numbers.csv")
    return {"participantdata": df.to_dict(orient="records")}

@app.get("/list-directories")
async def list_directories():
    try:
        badges_files = os.listdir("badges")
        codes_files = os.listdir("codes")
        files_in_root = os.listdir(".")
        return {
            "badges": badges_files,
            "codes": codes_files,
            "root_csv_files": [f for f in files_in_root if f.endswith('.csv')],
            "badge_count": len(badges_files),
            "code_count": len(codes_files)
        }
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


@app.post("/generate-stickers")
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

@app.get("/download-stickers/{filename}")
async def download_stickers(filename: str):
    """Download the generated stickers PDF"""
    require_stickers_enabled()
    if not filename.endswith("-stickers.pdf"):
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


def _normalise_type(raw: str) -> str:
    """Map Discount field values to a human label. KCD volunteers use an access
    code rather than a readable name, so we normalise them here."""
    s = (raw or "").strip()
    if "volunteer" in s.lower():
        return "Volunteer"
    return s


class PrintRequest(BaseModel):
    first_name: str
    ticket_number: str


@app.get("/checkin")
async def checkin_page():
    return FileResponse(os.path.join(_HERE, "checkin.html"))


@app.get("/checkin/search")
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
    rows = df[mask].head(20)
    return [
        {
            "ticket_number": str(row["Ticket number"]),
            "first_name": str(row["First Name"]).strip(),
            "last_name": str(row["Last Name"]).strip(),
            "company": str(row.get("Company", "") or "").strip(),
            "attendee_type": _normalise_type(str(row.get("Discount", "") or "")),
        }
        for _, row in rows.iterrows()
    ]


@app.post("/checkin/print")
async def checkin_print(req: PrintRequest):
    if not req.first_name.strip():
        raise HTTPException(status_code=400, detail="first_name is required")
    if not req.ticket_number.strip():
        raise HTTPException(status_code=400, detail="ticket_number is required")
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
    return {"ok": True, "job": job}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)