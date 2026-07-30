"""
Fetch macro-economic data from FRED API, with yfinance fallback.
Core series: DGS10, DGS2, T5YIE, VIXCLS, DTWEXBGS, FEDFUNDS
CBOE volatility: VXNCLS (Nasdaq), GVZCLS (Gold), EVZCLS (Euro), SKEW (tail risk)
Inflation: T10YIE (10Y breakeven)
When FRED_API_KEY is missing, falls back to yfinance tickers.
"""
import os
import json
import requests
from datetime import datetime

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
SERIES = {
    "10Y Yield":       "DGS10",
    "2Y Yield":        "DGS2",
    "5Y Breakeven":    "T5YIE",
    "10Y Breakeven":   "T10YIE",
    "VIX":             "VIXCLS",
    "VXN":             "VXNCLS",
    "GVZ":             "GVZCLS",
    "EVZ":             "EVZCLS",
    "SKEW":            "SKEW",
    "Dollar Index":    "DTWEXBGS",
    "Fed Funds":       "FEDFUNDS",
}
YF_FALLBACK = {
    "10Y Yield":     "^TNX",
    "VIX":           "^VIX",
    "VXN":           "^VXN",
    "GVZ":           "^GVZ",
    "EVZ":           "^EVZ",
    "SKEW":          "^SKEW",
    "Dollar Index":  "DX-Y.NYB",
}
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

def fetch_series(series_id, api_key):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": 2,
        "observation_start": "2024-01-01",
    }
    r = requests.get(FRED_BASE, params=params, timeout=15)
    if r.status_code == 400:
        err_data = r.json()
        msg = err_data.get("error_message", "")
        if "api_key" in msg.lower() or "key" in msg.lower():
            raise Exception(f"INVALID FRED API KEY — get a free key at https://fred.stlouisfed.org/docs/api/api_key.html")
        raise Exception(f"Bad request: {msg[:200]}")
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

def fetch_yfinance(label, ticker):
    import yfinance as yf
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d")
        if hist.empty:
            return None
        val = hist["Close"].iloc[-1]
        # ^TNX yields percent (e.g. 4.25 = 4.25%), DX-Y.NYB is the index level
        return {"date": hist.index[-1].strftime("%Y-%m-%d"), "value": round(float(val), 2)}
    except Exception as e:
        print(f"    yfinance error for {ticker}: {e}")
        return None

def run():
    api_key = os.environ.get("FRED_API_KEY")
    use_yfinance = not api_key
    if use_yfinance:
        print("FRED_API_KEY not set — using yfinance fallback")

    results = {}
    for label, sid in SERIES.items():
        if use_yfinance:
            yf_ticker = YF_FALLBACK.get(label)
            if yf_ticker:
                result = fetch_yfinance(label, yf_ticker)
                if result:
                    results[label] = result
                    print(f"  {label}: {result['value']} (yfinance)")
                    continue
            results[label] = {"date": None, "value": None}
            if label in YF_FALLBACK:
                print(f"  {label}: no yfinance data")
            else:
                print(f"  {label}: no fallback available")
            continue
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
