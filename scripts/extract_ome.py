import os, json, sys
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INSTRUMENTS = ["Gold", "NAS100", "GER40", "EURUSD"]

def run():
    api_key = os.environ.get("GROQ_API_KEY", "")
    print(f"GROQ_API_KEY set: {'yes' if api_key else 'no'}")

    import requests
    print("Testing Groq API...")
    try:
        r = requests.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"model": "llama-3.2-11b-vision-preview", "messages": [{"role": "user", "content": "Say OK"}], "max_tokens": 10},
            timeout=15,
        )
        print(f"Groq response: {r.status_code}")
        if r.status_code != 200:
            print(f"  Body: {r.text[:300]}")
        else:
            print(f"  OK: {r.json()['choices'][0]['message']['content']}")
    except Exception as e:
        print(f"Groq error: {e}")

    out = {"fetched": datetime.now().isoformat(), "instruments": {i: {"error": "no screenshot"} for i in INSTRUMENTS}}
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "ome_data.json"), "w") as f:
        json.dump(out, f, indent=2)
    print("Done — wrote ome_data.json placeholder")
    return True

if __name__ == "__main__":
    run()
