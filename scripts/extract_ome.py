"""
Extract OME options-wall data from PDF reports or screenshots
via Hugging Face Inference API (free tier).
"""
import os
import json
import re
import io
import requests
from datetime import datetime
from pathlib import Path

INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")

HF_MODEL = "Salesforce/blip2-flan-t5-xl"
HF_API = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

PROMPT = """Read all numbers from this financial options page. Return JSON with:
- instrument: name if visible
- max_pain: number or null
- put_call_ratio: number or null
- call_wall: number or null
- put_wall: number or null
- magnet_strike: number or null
- skew_percent: number or null
- total_oi: number or null
Return ONLY valid JSON."""

SUPPORTED_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".pdf"}

def process_page(image_bytes, api_key):
    resp = requests.post(
        HF_API,
        headers={"Authorization": f"Bearer {api_key}"},
        data=image_bytes,
        timeout=60,
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}
    result = resp.json()
    text = ""
    if isinstance(result, list):
        for item in result:
            if isinstance(item, dict):
                text += item.get("generated_text", "")
    elif isinstance(result, dict):
        text = result.get("generated_text", "")
    if not text:
        return {"error": "empty response", "raw": result}
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            return json.loads(text[json_start:json_end])
        except json.JSONDecodeError:
            pass
    return {"error": "No JSON found", "raw": text}

def process_image(image_path, api_key):
    with open(image_path, "rb") as f:
        return process_page(f.read(), api_key)

def process_pdf(image_path, api_key):
    import fitz
    doc = fitz.open(str(image_path))
    combined = {"instrument": None, "max_pain": None, "put_call_ratio": None,
                 "call_wall": None, "put_wall": None, "magnet_strike": None,
                 "skew_percent": None, "total_oi": None, "notes": ""}
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(dpi=200)
        img_bytes = pix.tobytes("png")
        result = process_page(img_bytes, api_key)
        if "error" in result:
            combined["notes"] += f"Page {page_num+1}: {result['error']}. "
            continue
        for key in combined:
            if key == "notes":
                continue
            val = result.get(key)
            if val is not None:
                if combined[key] is None:
                    combined[key] = val
                elif key not in ("instrument", "notes"):
                    combined[key] = val
        if result.get("notes"):
            combined["notes"] += f"Page {page_num+1}: {result['notes']}. "
    doc.close()
    combined["notes"] = combined["notes"].strip() or None
    return combined

def run():
    api_key = os.environ.get("HF_API_KEY")
    if not api_key:
        print("ERROR: HF_API_KEY not set — skipping OME extraction.")
        print("Get a free key at https://huggingface.co/settings/tokens")
        return False

    has_fitz = False
    try:
        import fitz
        has_fitz = True
    except ImportError:
        pass

    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"  Model: {HF_MODEL}")
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
                    print(f"    ERROR: PyMuPDF not installed — pip install PyMuPDF")
                    continue
                data = process_pdf(str(file_path), api_key)
            else:
                data = process_image(str(file_path), api_key)
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
