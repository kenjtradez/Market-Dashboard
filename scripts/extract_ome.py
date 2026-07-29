"""
Extract OME options-wall data from CME Open Interest Matrix PDFs
using pdfplumber for table extraction, then compute metrics.
"""
import os
import json
import re
from datetime import datetime
from pathlib import Path

INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}

def is_number(s):
    s = s.replace(",", "")
    try:
        float(s)
        return True
    except ValueError:
        return False

def parse_row_numbers(words, c_x_positions, p_x_positions):
    """Parse a row of words into (strike, call_oi, put_oi)."""
    strike = None
    call_val = 0
    put_val = 0
    for w in words:
        txt = w["text"].replace(",", "")
        if not is_number(txt):
            continue
        val = float(txt) if "." in txt else int(txt)
        x0 = w["x0"]
        # Check if this value is at a C column position
        matched = False
        for cx in c_x_positions:
            if abs(x0 - cx) < 8:
                call_val += val
                matched = True
                break
        if matched:
            continue
        for px in p_x_positions:
            if abs(x0 - px) < 8:
                put_val += val
                matched = True
                break
        if not matched:
            # If it's near the strike position
            if abs(x0 - 40) < 25:
                strike = val
    return strike, call_val, put_val

def get_column_positions(page):
    """Find C and P column x0 positions from the header row."""
    words = page.extract_words()
    c_positions = []
    p_positions = []
    # Find the row with "C" and "P" alternating
    for w in words:
        if w["text"] == "C" and 110 < w["top"] < 130:
            c_positions.append(w["x0"])
        elif w["text"] == "P" and 110 < w["top"] < 130:
            p_positions.append(w["x0"])
    # Try to match C and P positions as alternating pairs
    all_cp = sorted(c_positions + p_positions)
    return c_positions, p_positions

def process_pdf_pages(pdf):
    """Process all pages of a PDF and return aggregated OI data."""
    total_call_oi = 0
    total_put_oi = 0
    strike_data = {}  # strike -> {call: int, put: int}

    underlying = None

    for page in pdf.pages:
        c_x, p_x = get_column_positions(page)
        if not c_x or not p_x:
            continue

        words = page.extract_words()
        # Group words by row (y-position)
        rows = {}
        for w in words:
            if w["text"].replace(",", "").lstrip("-").replace(".", "").isdigit() or w["text"] == "STRIKE":
                row_key = round(w["top"] / 10) * 10
                if row_key not in rows:
                    rows[row_key] = []
                rows[row_key].append(w)

        for row_key in sorted(rows.keys()):
            row_words = rows[row_key]
            # Skip header rows
            texts = [w["text"] for w in row_words]
            if any(t in ["STRIKE", "C", "P", "CALL", "PUT"] for t in texts):
                continue

            strike, call_oi, put_oi = parse_row_numbers(row_words, c_x, p_x)
            if strike is not None:
                if strike not in strike_data:
                    strike_data[strike] = {"call": 0, "put": 0}
                strike_data[strike]["call"] += call_oi
                strike_data[strike]["put"] += put_oi
                total_call_oi += call_oi
                total_put_oi += put_oi

    # Find underlying price from the first page header
    first_page = pdf.pages[0]
    header_words = [w for w in first_page.extract_words() if w["top"] < 120]
    num_counts = {}
    for w in header_words:
        t = w["text"].replace(",", "")
        if is_number(t):
            val = round(float(t), 5)
            num_counts[val] = num_counts.get(val, 0) + 1
    if num_counts:
        # Most frequent number in header = underlying
        underlying = max(num_counts, key=num_counts.get)

    return strike_data, total_call_oi, total_put_oi, underlying

def compute_pcr(total_call_oi, total_put_oi):
    if total_call_oi == 0:
        return None
    return round(total_put_oi / total_call_oi, 4)

def compute_max_pain(strike_data):
    """Max Pain: strike with minimum total option value at expiration."""
    if not strike_data:
        return None
    strikes = sorted(strike_data.keys())
    best_strike = None
    best_value = float("inf")

    for k in strikes:
        total_value = 0
        for s in strikes:
            if s > k:
                total_value += (s - k) * strike_data[s]["call"]
            elif s < k:
                total_value += (k - s) * strike_data[s]["put"]
        if total_value < best_value:
            best_value = total_value
            best_strike = k

    return best_strike

def compute_walls(strike_data, underlying):
    """Call wall: strike with highest call OI near the money.
       Put wall: strike with highest put OI near the money."""
    if not strike_data or underlying is None:
        return None, None

    best_call_strike = None
    best_call_oi = 0
    best_put_strike = None
    best_put_oi = 0

    for strike, data in strike_data.items():
        if data["call"] > best_call_oi:
            best_call_oi = data["call"]
            best_call_strike = strike
        if data["put"] > best_put_oi:
            best_put_oi = data["put"]
            best_put_strike = strike

    return best_call_strike, best_put_strike

def compute_magnet(strike_data, underlying):
    """Magnet strike: highest total OI concentration."""
    if not strike_data:
        return None
    best_strike = None
    best_oi = 0
    for strike, data in strike_data.items():
        total = data["call"] + data["put"]
        if total > best_oi:
            best_oi = total
            best_strike = strike
    return best_strike

def process_pdf(file_path):
    import pdfplumber
    pdf = pdfplumber.open(str(file_path))
    try:
        strike_data, total_call_oi, total_put_oi, underlying = process_pdf_pages(pdf)
    finally:
        pdf.close()

    if not strike_data:
        return {"error": "could not parse PDF"}

    call_wall, put_wall = compute_walls(strike_data, underlying)
    total_oi = total_call_oi + total_put_oi

    print(f"      Underlying: {underlying}")
    print(f"      Total call OI: {total_call_oi}")
    print(f"      Total put OI: {total_put_oi}")
    print(f"      Strikes parsed: {len(strike_data)}")

    result = {
        "instrument": None,
        "max_pain": compute_max_pain(strike_data),
        "put_call_ratio": compute_pcr(total_call_oi, total_put_oi),
        "call_wall": call_wall,
        "put_wall": put_wall,
        "magnet_strike": compute_magnet(strike_data, underlying),
        "skew_percent": None,
        "total_oi": total_oi,
        "underlying_price": underlying,
        "notes": None,
    }
    return result

def run():
    has_pdfplumber = False
    try:
        import pdfplumber
        has_pdfplumber = True
    except ImportError:
        pass

    if not has_pdfplumber:
        print("ERROR: pdfplumber not installed. Run: pip install pdfplumber")
        return False

    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"  Engine: pdfplumber (direct PDF table extraction)")
    print(f"  Screenshots dir: {screenshot_dir.resolve()}")
    print(f"  Dir exists: {screenshot_dir.exists()}")
    print(f"  PDF support: yes")

    all_files = []
    if screenshot_dir.exists():
        all_files = list(screenshot_dir.iterdir())
    print(f"  All files: {[f'{f.name} ({f.suffix})' for f in all_files]}")

    results = {}
    all_dir_files = list(screenshot_dir.iterdir()) if screenshot_dir.exists() else []
    for instr in INSTRUMENTS:
        candidates = []
        if screenshot_dir.exists():
            for ext in SUPPORTED_EXTS:
                candidates.extend(screenshot_dir.glob(f"{instr}{ext}"))
                candidates.extend(screenshot_dir.glob(f"{instr.lower()}{ext}"))
            candidates.extend(screenshot_dir.glob(f"*{instr}*"))
            for f in all_dir_files:
                if instr.lower() in f.name.lower() and f.suffix.lower() in SUPPORTED_EXTS:
                    candidates.append(f)
        seen = set()
        unique = []
        for c in candidates:
            if c.name not in seen:
                seen.add(c.name)
                unique.append(c)
        candidates = unique
        print(f"  {instr} candidates: {[c.name for c in candidates]}")

        if not candidates:
            print(f"  {instr}: no file found")
            results[instr] = {"error": "no file"}
            continue

        file_path = candidates[0]
        ext = file_path.suffix.lower()
        file_size = os.path.getsize(file_path)
        print(f"  {instr}: processing {file_path.name} ({file_size} bytes)...")

        try:
            if ext == ".pdf":
                data = process_pdf(str(file_path))
            else:
                print(f"    Skipping non-PDF (use PDF format)")
                data = {"error": "non-PDF file"}
            results[instr] = data
            if "error" not in data:
                print(f"    max_pain={data.get('max_pain')}, PCR={data.get('put_call_ratio')}")
                print(f"    call_wall={data.get('call_wall')}, put_wall={data.get('put_wall')}")
        except Exception as e:
            results[instr] = {"error": str(e)}
            print(f"    ERROR: {e}")

    out_path = os.path.join(DATA_DIR, "ome_data.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"\nSaved OME data to {out_path}")
    return True

if __name__ == "__main__":
    run()
