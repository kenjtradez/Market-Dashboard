"""
Fetch macro-economic data from FRED API.
Series: DGS10 (10Y yield), DGS2 (2Y yield), T5YIE (5Y breakeven),
        VIXCLS (VIX), DTWEXBGS (dollar index), FEDFUNDS (rate)
"""
import os
import json
import requests
from datetime import datetime

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {
    "10Y Yield":     "DGS10",
    "2Y Yield":      "DGS2",
    "5Y Breakeven":  "T5YIE",
    "VIX":           "VIXCLS",
    "Dollar Index":  "DTWEXBGS",
    "Fed Funds":     "FEDFUNDS",
}
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def fetch_series(series_id, api_key):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 2,
        "observation_start": datetime.now().strftime("%Y-%m-%d") if False else "20240101",
    }
    r = requests.get(FRED_BASE, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    obs = data.get("observations", [])
    if not obs:
        return None
    latest = obs[0]
    if latest.get("value") in (".", ""):
        if len(obs) > 1:
            latest = obs[1]
        else:
            return None
    return {
        "date": latest["date"],
        "value": float(latest["value"]),
    }

def run():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("ERROR: FRED_API_KEY environment variable not set.")
        return False

    results = {}
    for label, sid in SERIES.items():
        try:
            result = fetch_series(sid, api_key)
            if result:
                results[label] = result
                print(f"  {label}: {result['value']} ({result['date']})")
            else:
                results[label] = {"date": None, "value": None}
                print(f"  {label}: no data")
        except Exception as e:
            results[label] = {"date": None, "value": None}
            print(f"  {label}: ERROR {e}")

    out_path = os.path.join(OUTPUT_DIR, "fred_macro.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "series": results}, f, indent=2)
    print(f"\nSaved FRED data to {out_path}")
    return True

if __name__ == "__main__":
    run()
