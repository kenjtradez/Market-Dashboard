"""
Fetch live spot prices from Oanda v20 API for Gold (XAU/USD), NAS100 (US100/USD), EURUSD.
Uses practice/demo environment by default.
"""
import os, json
from datetime import datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = {
    "Gold":   "XAU_USD",
    "NAS100": "US100_USD",
    "EURUSD": "EUR_USD",
}

def run():
    api_key = os.environ.get("OANDA_API_KEY")
    if not api_key:
        print("ERROR: OANDA_API_KEY env var not set")
        return False

    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    env = os.environ.get("OANDA_ENV", "practice")
    base = f"https://api-fxpractice.oanda.com/v3" if env == "practice" else "https://api-fxtrade.oanda.com/v3"

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    print(f"Fetching Oanda prices ({env})...")
    results = {}
    for instr, oanda_name in INSTRUMENTS.items():
        try:
            resp = requests.get(f"{base}/accounts/{account_id}/pricing", params={"instruments": oanda_name}, headers=headers, timeout=15)
            if resp.status_code != 200:
                results[instr] = {"error": f"HTTP {resp.status_code}", "detail": resp.text[:200]}
                print(f"  {instr}: ERROR {resp.status_code}")
                continue
            data = resp.json()
            prices = data.get("prices", [])
            if not prices:
                results[instr] = {"error": "no prices in response"}
                print(f"  {instr}: no prices")
                continue
            p = prices[0]
            bid = float(p.get("bids", [{}])[0].get("price", 0)) if p.get("bids") else None
            ask = float(p.get("asks", [{}])[0].get("price", 0)) if p.get("asks") else None
            mid = round((bid + ask) / 2, 5) if bid and ask else (bid or ask)
            results[instr] = {
                "bid": bid,
                "ask": ask,
                "mid": mid,
                "time": p.get("time", ""),
                "instrument": oanda_name,
            }
            print(f"  {instr} ({oanda_name}): mid={mid}")
        except Exception as e:
            results[instr] = {"error": str(e)}
            print(f"  {instr}: ERROR {e}")

    out_path = os.path.join(DATA_DIR, "oanda_prices.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True

if __name__ == "__main__":
    run()
