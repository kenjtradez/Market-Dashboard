"""
Use Groq API (free tier, Llama vision) to extract OME options-wall
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

API_URL = "https://api.groq.com/openai/v1/chat/completions"
MODEL = "llama-3.2-90b-vision-preview"

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

def extract_from_screenshot(image_path, api_key):
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = Path(image_path).suffix.lower()
    mime = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}.get(ext.lstrip("."), "image/png")
    data_url = f"data:{mime};base64,{b64}"

    payload = {
        "model": MODEL,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "text", "text": PROMPT},
                {"type": "image_url", "image_url": {"url": data_url}}
            ]
        }],
        "temperature": 0.1,
        "max_tokens": 500,
    }

    resp = requests.post(
        API_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=30,
    )
    if resp.status_code != 200:
        return {"error": f"HTTP {resp.status_code}: {resp.text[:500]}"}

    data = resp.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "")

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
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        print("ERROR: GROQ_API_KEY not set — skipping OME extraction.")
        print("Get a free key at https://console.groq.com")
        return False

    print(f"  Using model: {MODEL}")
    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"  Screenshots dir: {screenshot_dir.resolve()}")
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
            print(f"  {instr}: SKIPPING {image_path.name} (not an image)")
            results[instr] = {"error": "no screenshot"}
            continue

        file_size = os.path.getsize(image_path)
        print(f"  {instr}: processing {image_path.name} ({file_size} bytes)...")
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
