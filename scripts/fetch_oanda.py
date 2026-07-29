"""
Fetch spot prices via Yahoo Finance.
No API key required. Serves as drop-in replacement for Oanda pricing.
"""
import os, json
from datetime import datetime

import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = {
    "Gold":   "GLD",
    "NAS100": "QQQ",
    "EURUSD": "FXE",
}


def fetch_price(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price = info.get("regularMarketPrice") or info.get("ask") or info.get("bid") or info.get("previousClose")
        if price:
            return {"mid": round(price, 5), "source": "yfinance"}, None
        return None, "no price found"
    except Exception as e:
        return None, str(e)


def run():
    print("Fetching prices via Yahoo Finance...")
    results = {}
    for instr, ticker in INSTRUMENTS.items():
        result, err = fetch_price(ticker)
        if result:
            results[instr] = result
            print(f"  {instr} ({ticker}): mid={result['mid']}")
        else:
            results[instr] = {"error": err}
            print(f"  {instr} ({ticker}): ERROR {err}")

    out_path = os.path.join(DATA_DIR, "oanda_prices.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True


if __name__ == "__main__":
    run()
