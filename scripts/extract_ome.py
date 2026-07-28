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

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"

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

def extract_from_screenshot(image_path, api_key):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    mime = "image/png" if str(image_path).lower().endswith(".png") else "image/jpeg"

    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": mime, "data": b64}}
            ]
        }]
    }

    resp = requests.post(
        f"{API_URL}?key={api_key}",
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    text = ""
    for candidate in data.get("candidates", []):
        for part in candidate.get("content", {}).get("parts", []):
            text += part.get("text", "")

    if not text:
        return {"error": "empty response", "raw": data}

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

    results = {}
    screenshot_dir = Path(SCREENSHOT_DIR)
    for instr in INSTRUMENTS:
        candidates = list(screenshot_dir.glob(f"{instr}.*")) + list(screenshot_dir.glob(f"{instr.lower()}.*"))
        candidates += list(screenshot_dir.glob(f"*{instr}*"))
        if not candidates:
            print(f"  {instr}: no screenshot found (looked for {instr}.*)")
            results[instr] = {"error": "no screenshot"}
            continue

        image_path = candidates[0]
        print(f"  {instr}: extracting from {image_path.name}...")
        try:
            data = extract_from_screenshot(str(image_path), api_key)
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
