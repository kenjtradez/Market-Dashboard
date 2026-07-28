"""
Use Google Gemini REST API (vision, free tier) to extract OME options-wall
data from screenshots of Gold, NAS100, GER40, and EUR/USD.
"""
import os
import json
import re
import base64
import requests
from datetime import datetime
from pathlib import Path

INSTRUMENTS = ["Gold", "NAS100", "GER40", "EURUSD"]
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TEXT_API = "https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent"

PROMPT = """You are looking at an OME (Options Market Event) panel for a financial instrument.

Read ALL visible numbers from this screenshot and return them as a JSON object with these exact keys:
- instrument (string): the name of the instrument if visible
- max_pain (number or null)
- put_call_ratio (number or null)
- call_wall (number or null)
- put_wall (number or null)
- magnet_strike (number or null)
- skew_percent (number or null) — the call/put skew percentage if shown
- total_oi (number or null) — total open interest if shown
- notes (string): any other relevant numbers or observations you can read

Return ONLY valid JSON, no explanation."""

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

def is_image_file(path):
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS

def gemini_request(payload, api_key):
    resp = requests.post(f"{TEXT_API}?key={api_key}", json=payload, timeout=30)
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}
    return resp.json()

def call_gemini_text(api_key):
    payload = {"contents": [{"parts": [{"text": "Say OK"}]}]}
    data = gemini_request(payload, api_key)
    if "error" in data:
        return data
    text = ""
    for c in data.get("candidates", []):
        for p in c.get("content", {}).get("parts", []):
            text += p.get("text", "")
    return {"text": text}

def call_gemini_vision(image_path, api_key):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")

    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}}
            ]
        }]
    }

    data = gemini_request(payload, api_key)
    if "error" in data:
        return data

    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")

    if not text:
        return {"error": "empty response from model", "raw": data}

    text = re.sub(r'^```(?:json)?\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text)
    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        return json.loads(text[json_start:json_end])
    return {"error": "No JSON found in response", "raw": text}

def run():
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("ERROR: GEMINI_API_KEY not set — skipping OME extraction.")
        return False

    print("  Testing Gemini API key with text-only call...")
    test = call_gemini_text(api_key)
    if "error" in test:
        print(f"  API KEY TEST FAILED: {test['error']}")
        print("  Your GEMINI_API_KEY may be invalid — check https://aistudio.google.com/apikey")
    else:
        print(f"  API key OK — response: {test.get('text', '?')}")

    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"\n  Screenshots dir: {screenshot_dir.resolve()}")
    print(f"  Dir exists: {screenshot_dir.exists()}")

    all_files = []
    if screenshot_dir.exists():
        all_files = list(screenshot_dir.iterdir())
    print(f"  All files: {[f.name for f in all_files]}")

    results = {}
    for instr in INSTRUMENTS:
        candidates = []
        if screenshot_dir.exists():
            candidates = list(screenshot_dir.glob(f"{instr}.*")) + list(screenshot_dir.glob(f"{instr.lower()}.*"))
            candidates += list(screenshot_dir.glob(f"*{instr}*"))
        print(f"  {instr} candidates: {[c.name for c in candidates]}")

        if not candidates:
            print(f"  {instr}: no screenshot found")
            results[instr] = {"error": "no screenshot"}
            continue

        image_path = candidates[0]
        if not is_image_file(image_path):
            print(f"  {instr}: SKIPPING {image_path.name} (not a valid image file)")
            results[instr] = {"error": "no screenshot"}
            continue

        file_size = os.path.getsize(image_path)
        print(f"  {instr}: processing {image_path.name} ({file_size} bytes)...")
        try:
            data = call_gemini_vision(str(image_path), api_key)
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
