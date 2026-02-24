import os
import json
import uuid
import re
from pathlib import Path
from datetime import datetime
from typing import Optional, List

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Header, Depends
from fastapi.staticfiles import StaticFiles
from fastapi.responses import Response
from pydantic import BaseModel
import pytesseract
from PIL import Image
import dateparser
from dotenv import load_dotenv

try:
    import numpy as np
    _NUMPY = True
except ImportError:
    _NUMPY = False

load_dotenv()

# --- Tesseract path (required on Windows) ---
tesseract_path = os.getenv("TESSERACT_PATH", "")
if tesseract_path:
    pytesseract.pytesseract.tesseract_cmd = tesseract_path

# Use user-local tessdata dir if it exists (supports best-quality Romanian model)
_user_tessdata = Path.home() / ".tessdata"
if _user_tessdata.exists():
    os.environ["TESSDATA_PREFIX"] = str(_user_tessdata)

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")
EVENTS_FILE = Path("events.json")
UPLOADS_DIR = Path("uploads")
UPLOADS_DIR.mkdir(exist_ok=True)

app = FastAPI(title="Science Calendar API")


# --- Storage ---

def load_events() -> List[dict]:
    if EVENTS_FILE.exists():
        return json.loads(EVENTS_FILE.read_text(encoding="utf-8"))
    return []


def save_events(events: List[dict]):
    EVENTS_FILE.write_text(
        json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# --- Auth ---

def require_admin(x_admin_password: str = Header(...)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Parolă incorectă")


# --- Models ---

class Event(BaseModel):
    id: Optional[str] = None
    title: str
    date: str
    end_date: Optional[str] = ""
    description: Optional[str] = ""
    location: Optional[str] = ""


class EventUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    end_date: Optional[str] = None
    description: Optional[str] = None
    location: Optional[str] = None


# --- Public endpoints ---

@app.get("/events")
def get_events():
    return load_events()


@app.get("/events/{event_id}/export")
def export_ics(event_id: str):
    events = load_events()
    event = next((e for e in events if e["id"] == event_id), None)
    if not event:
        raise HTTPException(status_code=404, detail="Evenimentul nu există")
    return Response(
        content=_generate_ics(event),
        media_type="text/calendar",
        headers={"Content-Disposition": 'attachment; filename="eveniment.ics"'},
    )


# --- Admin endpoints ---

@app.post("/admin/verify")
def verify_admin(x_admin_password: str = Header(...)):
    if x_admin_password != ADMIN_PASSWORD:
        raise HTTPException(status_code=401, detail="Parolă incorectă")
    return {"ok": True}


@app.post("/admin/upload")
async def upload_image(
    file: UploadFile = File(...),
    year: Optional[int] = Form(None),
    _: None = Depends(require_admin),
):
    suffix = Path(file.filename or "img.jpg").suffix.lower()
    if suffix not in {".jpg", ".jpeg", ".png"}:
        raise HTTPException(status_code=400, detail="Doar JPG/PNG sunt acceptate")

    temp_path = UPLOADS_DIR / f"{uuid.uuid4()}{suffix}"
    try:
        temp_path.write_bytes(await file.read())
        image = Image.open(temp_path)
        W, H = image.size

        # For landscape images (W > H), try grid calendar extraction first
        if _NUMPY and W > H:
            events = _extract_calendar_grid(image, forced_year=year)
            if len(events) >= 10:
                months_found = len(set(e["date"][:7] for e in events))
                detected_year = events[0]["date"][:4]
                summary = (
                    f"Calendar anual detectat ({W}×{H}px). "
                    f"{len(events)} intrări extrase din {months_found} luni "
                    f"(an: {detected_year})."
                )
                return {"raw_text": summary, "events": events}

        # Simple poster: full-image OCR + date-pattern extraction
        try:
            text = pytesseract.image_to_string(image, lang="ron+eng")
        except pytesseract.TesseractError:
            text = pytesseract.image_to_string(image, lang="eng")

        events = _extract_events(text)
        return {"raw_text": text, "events": events}

    finally:
        temp_path.unlink(missing_ok=True)


@app.post("/admin/events")
def create_event(event: Event, _: None = Depends(require_admin)):
    events = load_events()
    event.id = str(uuid.uuid4())
    events.append(event.model_dump())
    save_events(events)
    return event


@app.put("/admin/events/{event_id}")
def update_event(
    event_id: str, update: EventUpdate, _: None = Depends(require_admin)
):
    events = load_events()
    for i, e in enumerate(events):
        if e["id"] == event_id:
            for k, v in update.model_dump(exclude_none=True).items():
                events[i][k] = v
            save_events(events)
            return events[i]
    raise HTTPException(status_code=404, detail="Evenimentul nu există")


@app.delete("/admin/events/{event_id}")
def delete_event(event_id: str, _: None = Depends(require_admin)):
    events = load_events()
    new_events = [e for e in events if e["id"] != event_id]
    if len(new_events) == len(events):
        raise HTTPException(status_code=404, detail="Evenimentul nu există")
    save_events(new_events)
    return {"ok": True}


# Mount static files last so API routes take precedence
app.mount("/", StaticFiles(directory="static", html=True), name="static")


# ═══════════════════════════════════════════════════════════════
# OCR — Simple poster (dates written in full, e.g. "15 martie 2025")
# ═══════════════════════════════════════════════════════════════

_DATE_PATTERNS = [
    r"\b\d{1,2}[.\-/]\d{1,2}[.\-/]\d{2,4}\b",
    r"\b\d{1,2}\s+(?:ianuarie|februarie|martie|aprilie|mai|iunie|iulie|august"
    r"|septembrie|octombrie|noiembrie|decembrie)\s+\d{4}\b",
    r"\b(?:january|february|march|april|may|june|july|august|september"
    r"|october|november|december)\s+\d{1,2},?\s+\d{4}\b",
    r"\b\d{4}[.\-/]\d{1,2}[.\-/]\d{1,2}\b",
]
_DATE_RE = re.compile("|".join(_DATE_PATTERNS), re.IGNORECASE)


def _extract_events(text: str) -> List[dict]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    events = []

    for i, line in enumerate(lines):
        match = _DATE_RE.search(line)
        if not match:
            continue

        parsed = dateparser.parse(match.group(), languages=["ro", "en"])
        if not parsed:
            continue

        remainder = (line[: match.start()] + line[match.end():]).strip(" –—:-|")
        context = [remainder] if remainder else []
        if i + 1 < len(lines) and not _DATE_RE.search(lines[i + 1]):
            context.append(lines[i + 1])

        title = " — ".join(p for p in context if p) or "Eveniment"
        events.append({
            "id": str(uuid.uuid4()),
            "title": title,
            "date": parsed.strftime("%Y-%m-%d"),
            "end_date": "",
            "description": "",
            "location": "",
        })

    return events


# ═══════════════════════════════════════════════════════════════
# OCR — Annual calendar grid (6×2 layout, one month per cell)
# Format: "{day} {day_abbrev} {description} ({historical_year})"
# ═══════════════════════════════════════════════════════════════

_MONTHS_RO  = ["Ianuarie","Februarie","Martie","Aprilie","Mai","Iunie",
               "Iulie","August","Septembrie","Octombrie","Noiembrie","Decembrie"]
_DAY_LINE   = re.compile(r'^(\d{1,2})\s+[LMJVSDlji]{1,2}[\.\s]+(.*)')
_HIST_YEAR  = re.compile(r'\((\d{4})\)\s*$')
_YEAR_IN_TITLE = re.compile(r'\b(20\d{2}|19\d{2})\b')


def _days_in_month(month: int, year: int) -> int:
    if month == 2:
        return 29 if (year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)) else 28
    return [31,28,31,30,31,30,31,31,30,31,30,31][month - 1]


def _detect_year(image: Image.Image) -> int:
    """Extract calendar year from the title area (top 10% of image)."""
    W, H = image.size
    title_crop = image.crop((0, 0, W, int(H * 0.10)))
    title_crop = title_crop.resize((title_crop.width, title_crop.height * 2), Image.LANCZOS)
    try:
        text = pytesseract.image_to_string(title_crop, lang="ron+eng")
    except Exception:
        text = ""
    # Look for a year that appears as a standalone token (surrounded by spaces/newlines)
    standalone = re.findall(r'(?<!\d)(20\d{2})(?!\d)', text)
    candidates = [int(y) for y in standalone if 2024 <= int(y) <= 2035]
    if candidates:
        # Most frequent standalone year in the title area is the calendar year
        from collections import Counter
        return Counter(candidates).most_common(1)[0][0]
    return datetime.now().year + 1


def _detect_col_separators(arr, y0: int, y1: int, W: int) -> List[int]:
    """Find x-positions of the 5 vertical separators between 6 month columns."""
    col_bright = arr[y0:y1, :].mean(axis=0)
    window = 20
    smoothed = np.convolve(col_bright, np.ones(window) / window, mode="same")
    min_dist = W // 9
    candidates = []
    for x in range(min_dist, W - min_dist):
        lo, hi = max(0, x - min_dist), x + min_dist
        if smoothed[x] == smoothed[lo:hi].max() and smoothed[x] > 200:
            candidates.append((x, float(smoothed[x])))
    candidates.sort(key=lambda p: -p[1])
    return sorted(p[0] for p in candidates[:5])


def _parse_month_text(text: str, month_num: int, year: int) -> List[dict]:
    """Parse OCR text from a single month column into event dicts."""
    max_day = _days_in_month(month_num, year)
    events: List[dict] = []
    current_day: Optional[int] = None
    current_desc: List[str] = []

    def flush():
        if current_day is None:
            return
        desc = " ".join(current_desc)
        yr_m = _HIST_YEAR.search(desc)
        hist_yr = yr_m.group(1) if yr_m else ""
        title = _HIST_YEAR.sub("", desc).strip(" ()–—")
        title = re.sub(r"\s+", " ", title)[:140]
        if len(title) >= 6:
            events.append({
                "id": str(uuid.uuid4()),
                "title": title,
                "date": f"{year}-{month_num:02d}-{current_day:02d}",
                "end_date": "",
                "description": f"An: {hist_yr}" if hist_yr else "",
                "location": "",
            })

    for line in text.splitlines():
        line = line.strip()
        m = _DAY_LINE.match(line)
        if m:
            day = int(m.group(1))
            if 1 <= day <= max_day:
                flush()
                current_day = day
                current_desc = [m.group(2).strip()]
                continue
        if current_day is not None and line:
            current_desc.append(line)

    flush()
    return events


def _extract_calendar_grid(image: Image.Image, forced_year: Optional[int] = None) -> List[dict]:
    """
    Extract events from a landscape annual calendar poster with a 6×2 month grid.
    Automatically detects grid boundaries using image brightness analysis.
    """
    W, H = image.size
    arr = np.array(image.convert("L"))
    year = forced_year if forced_year else _detect_year(image)

    # Detect horizontal separator between top row (months 1-6) and bottom row (7-12)
    y_band = arr[int(H * 0.40): int(H * 0.60), int(W * 0.1): int(W * 0.9)]
    mid_y = int(H * 0.40) + int(y_band.mean(axis=1).argmax())

    rows = [
        (int(H * 0.130), max(int(H * 0.130) + 10, mid_y - int(H * 0.015))),
        (min(mid_y + int(H * 0.010), int(H * 0.95)), int(H * 0.900)),
    ]

    all_events: List[dict] = []

    for row_idx, (y0, y1) in enumerate(rows):
        separators = _detect_col_separators(arr, y0, y1, W)

        if len(separators) == 5:
            xs = [int(W * 0.025)] + separators + [int(W * 0.975)]
        else:
            # Fallback: equal-width columns
            cw = (int(W * 0.975) - int(W * 0.025)) // 6
            xs = [int(W * 0.025) + i * cw for i in range(7)]

        for col_idx in range(6):
            month_num = row_idx * 6 + col_idx + 1
            x0, x1 = xs[col_idx], xs[col_idx + 1]

            crop = image.crop((x0, y0, x1, y1))
            # 2× upscale improves OCR accuracy on small text
            crop = crop.resize((crop.width * 2, crop.height * 2), Image.LANCZOS)

            try:
                text = pytesseract.image_to_string(crop, lang="ron+eng")
            except pytesseract.TesseractError:
                text = pytesseract.image_to_string(crop, lang="eng")

            all_events.extend(_parse_month_text(text, month_num, year))

    return all_events


# ═══════════════════════════════════════════════════════════════
# ICS export
# ═══════════════════════════════════════════════════════════════

def _generate_ics(event: dict) -> str:
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    start = (event.get("date") or "").replace("-", "")
    end = (event.get("end_date") or event.get("date") or "").replace("-", "") or start

    def fold(line: str) -> str:
        out, chunk = [], line
        while len(chunk.encode()) > 75:
            out.append(chunk[:75])
            chunk = " " + chunk[75:]
        out.append(chunk)
        return "\r\n".join(out)

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Science Calendar//RO",
        "CALSCALE:GREGORIAN",
        "BEGIN:VEVENT",
        f"UID:{event['id']}@sciencecalendar",
        f"DTSTAMP:{now}",
        f"DTSTART;VALUE=DATE:{start}",
        f"DTEND;VALUE=DATE:{end}",
        fold(f"SUMMARY:{event.get('title', '')}"),
        fold(f"DESCRIPTION:{event.get('description', '')}"),
        fold(f"LOCATION:{event.get('location', '')}"),
        "END:VEVENT",
        "END:VCALENDAR",
    ]
    return "\r\n".join(lines)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
