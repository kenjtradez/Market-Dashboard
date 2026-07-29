"""
Extract OME options-wall data from PDF reports or screenshots
via Tesseract OCR (free, no API key needed).
"""
import os
import json
import re
import io
from datetime import datetime
from pathlib import Path

INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}

# Regex patterns to find values in OCR text (case-insensitive)
PATTERNS = {
    "max_pain": [
        r"(?:max\s*pain|maximum\s*pain)\s*:?\s*([\d,]+(?:\.\d+)?)",
        r"(?:max\s*pain|maximum\s*pain)\s*:?\s*\$?([\d,]+(?:\.\d+)?)",
    ],
    "put_call_ratio": [
        r"(?:put\s*[/\\]?\s*call\s*ratio|pcr|put\s*call\s*ratio)\s*:?\s*([\d.]+)",
    ],
    "call_wall": [
        r"(?:call\s*wall|call\s*resistance)\s*:?\s*([\d,]+(?:\.\d+)?)",
    ],
    "put_wall": [
        r"(?:put\s*wall|put\s*support)\s*:?\s*([\d,]+(?:\.\d+)?)",
    ],
    "magnet_strike": [
        r"(?:magnet\s*strike|magnet)\s*:?\s*([\d,]+(?:\.\d+)?)",
    ],
    "skew_percent": [
        r"(?:skew|volatility\s*skew)\s*:?\s*([\d.]+)\s*%?",
    ],
    "total_oi": [
        r"(?:total\s*oi|open\s*interest|total\s*open\s*interest)\s*:?\s*([\d,]+)",
    ],
}

def ocr_image(image_bytes):
    import pytesseract
    from PIL import Image as PILImage
    img = PILImage.open(io.BytesIO(image_bytes))
    text = pytesseract.image_to_string(img)
    return text

def parse_ocr_text(text):
    result = {key: None for key in PATTERNS}
    result["notes"] = ""
    text_lower = text.lower()
    for key, patterns in PATTERNS.items():
        for pat in patterns:
            m = re.search(pat, text_lower, re.IGNORECASE)
            if m:
                raw = m.group(1).replace(",", "")
                try:
                    if "." in raw:
                        result[key] = float(raw)
                    else:
                        result[key] = int(raw)
                except ValueError:
                    pass
                break
    return result

def process_page(image_bytes):
    text = ocr_image(image_bytes)
    print(f"      OCR text (first 600 chars): {text[:600]}")
    return parse_ocr_text(text)

def process_image(image_path):
    try:
        from PIL import Image as PILImage
        img = PILImage.open(image_path)
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return process_page(buf.getvalue())
    except Exception as e:
        return {"error": str(e)}

def process_pdf(image_path):
    import fitz
    doc = fitz.open(str(image_path))
    combined = {"instrument": None, "max_pain": None, "put_call_ratio": None,
                 "call_wall": None, "put_wall": None, "magnet_strike": None,
                 "skew_percent": None, "total_oi": None, "notes": ""}
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        data = process_page(img_bytes)
        if "error" in data:
            combined["notes"] += f"Page {page_num+1}: {data['error']}. "
            continue
        for key in combined:
            if key == "notes":
                continue
            val = data.get(key)
            if val is not None:
                if combined[key] is None:
                    combined[key] = val
                elif key not in ("instrument", "notes"):
                    combined[key] = val
        if data.get("notes"):
            combined["notes"] += f"Page {page_num+1}: {data['notes']}. "
    doc.close()
    combined["notes"] = combined["notes"].strip() or None
    return combined

def run():
    has_fitz = False
    has_tesseract = False
    try:
        import fitz
        has_fitz = True
    except ImportError:
        pass
    try:
        import pytesseract
        from PIL import Image
        has_tesseract = True
    except ImportError:
        pass

    if not has_tesseract:
        print("ERROR: pytesseract or Pillow not installed.")
        print("Run: pip install pytesseract Pillow")
        return False

    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"  OCR engine: Tesseract")
    print(f"  Screenshots dir: {screenshot_dir.resolve()}")
    print(f"  Dir exists: {screenshot_dir.exists()}")
    print(f"  PDF support: {'yes' if has_fitz else 'no (pip install PyMuPDF)'}")

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
                if not has_fitz:
                    results[instr] = {"error": "PyMuPDF not installed"}
                    print(f"    ERROR: PyMuPDF not installed")
                    continue
                data = process_pdf(str(file_path))
            else:
                data = process_image(str(file_path))
            results[instr] = data
            print(f"    max_pain={data.get('max_pain')}, PCR={data.get('put_call_ratio')}")
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