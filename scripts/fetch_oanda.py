"""
Fetch live spot prices from Oanda v20 API.
Falls back to Yahoo Finance if Oanda is unavailable.
"""
import os, json
from datetime import datetime

import requests
import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = {
    "Gold":   {"oanda": "XAU_USD", "yf": "GLD"},
    "NAS100": {"oanda": "US100_USD", "yf": "QQQ"},
    "EURUSD": {"oanda": "EUR_USD", "yf": "FXE"},
}


def fetch_oanda(api_key, account_id, env, oanda_name):
    base = "https://api-fxpractice.oanda.com/v3" if env == "practice" else "https://api-fxtrade.oanda.com/v3"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    resp = requests.get(
        f"{base}/accounts/{account_id}/pricing",
        params={"instruments": oanda_name},
        headers=headers,
        timeout=15,
    )
    if resp.status_code != 200:
        return None, f"Oanda HTTP {resp.status_code}"
    data = resp.json()
    prices = data.get("prices", [])
    if not prices:
        return None, "Oanda: no prices in response"
    p = prices[0]
    bid = float(p.get("bids", [{}])[0].get("price", 0)) if p.get("bids") else None
    ask = float(p.get("asks", [{}])[0].get("price", 0)) if p.get("asks") else None
    mid = round((bid + ask) / 2, 5) if bid and ask else (bid or ask)
    return {"bid": bid, "ask": ask, "mid": mid, "time": p.get("time", "")}, None


def fetch_yfinance(ticker):
    try:
        t = yf.Ticker(ticker)
        info = t.info
        price = info.get("regularMarketPrice") or info.get("ask") or info.get("bid") or info.get("previousClose")
        if price:
            return {"mid": round(price, 5), "source": "yfinance"}, None
        return None, "yfinance: no price"
    except Exception as e:
        return None, f"yfinance: {e}"


def run():
    api_key = os.environ.get("OANDA_API_KEY", "")
    account_id = os.environ.get("OANDA_ACCOUNT_ID", "")
    env = os.environ.get("OANDA_ENV", "practice")
    use_oanda = bool(api_key and account_id)

    print(f"Fetching prices {'(Oanda + yfinance fallback)' if use_oanda else '(yfinance only)'}...")
    results = {}
    for instr, cfg in INSTRUMENTS.items():
        result = None
        src = ""

        if use_oanda:
            result, err = fetch_oanda(api_key, account_id, env, cfg["oanda"])
            if result:
                src = "oanda"
            else:
                print(f"  {instr}: {err}, falling back to yfinance")

        if not result:
            result, err = fetch_yfinance(cfg["yf"])
            if result:
                src = "yfinance"
            else:
                results[instr] = {"error": err}
                print(f"  {instr}: ERROR {err}")
                continue
            result["source"] = "yfinance"

        result["instrument"] = cfg["oanda"]
        results[instr] = result
        print(f"  {instr}: mid={result.get('mid')} ({src})")

    out_path = os.path.join(DATA_DIR, "oanda_prices.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True


if __name__ == "__main__":
    run()
