"""
Use Hugging Face Inference API (free tier) to extract OME options-wall
data from screenshots of Gold, NAS100, and EUR/USD.
"""
import os
import json
import re
import base64
import requests
from datetime import datetime
from pathlib import Path

INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Uses Salesforce/blip2-flan-t5-xl for vision-language understanding
HF_MODEL = "Salesforce/blip2-flan-t5-xl"
HF_API = f"https://api-inference.huggingface.co/models/{HF_MODEL}"

PROMPT = """Read all numbers from this financial options screenshot. Return JSON with:
- max_pain: number or null
- put_call_ratio: number or null
- call_wall: number or null
- put_wall: number or null
- magnet_strike: number or null
- skew_percent: number or null
- total_oi: number or null
Return ONLY valid JSON."""

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}

def is_image_file(path):
    return Path(path).suffix.lower() in IMAGE_EXTENSIONS

def extract_from_screenshot(image_path, api_key):
    with open(image_path, "rb") as f:
        img_bytes = f.read()

    resp = requests.post(
        HF_API,
        headers={"Authorization": f"Bearer {api_key}"},
        data=img_bytes,
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
        return {"error": "empty response from model", "raw": result}

    json_start = text.find("{")
    json_end = text.rfind("}") + 1
    if json_start >= 0 and json_end > json_start:
        try:
            return json.loads(text[json_start:json_end])
        except json.JSONDecodeError:
            pass
    return {"error": "No JSON found", "raw": text}

def run():
    api_key = os.environ.get("HF_API_KEY")
    if not api_key:
        print("ERROR: HF_API_KEY not set — skipping OME extraction.")
        print("Get a free key at https://huggingface.co/settings/tokens")
        return False

    screenshot_dir = Path(SCREENSHOT_DIR)
    print(f"  Model: {HF_MODEL}")
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
