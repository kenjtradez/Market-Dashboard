"""
Fetch macro-economic data from FRED API, with yfinance fallback.
Core series: DGS10, DGS2, T5YIE, VIXCLS, DTWEXBGS, FEDFUNDS
CBOE volatility: VXNCLS (Nasdaq), GVZCLS (Gold), EVZCLS (Euro), SKEW (tail risk)
Inflation: T10YIE (10Y breakeven)
When FRED_API_KEY is missing, falls back to yfinance tickers.

NOTE on EVZ: CBOE discontinued the EuroCurrency ETF Volatility Index (EVZ) in
2025. FRED's EVZCLS series will keep returning its last-ever observation
forever — this is not a fetch bug, the source has gone dark. A staleness flag
is added below (max_age_days) so this shows clearly as dead rather than being
silently treated as a live macro input.
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

def _flag_staleness(results):
    """Mark any series whose latest observation is older than its expected
    threshold. Prevents dead/discontinued FRED series (e.g. EVZ) or silent
    fetch failures from being displayed as current without any signal that
    they're not — while respecting series that are legitimately low-frequency
    (e.g. Fed Funds is monthly, so 30+ days old is normal, not stale)."""
    today = datetime.now().date()
    for label, entry in results.items():
        max_age = MAX_AGE_DAYS.get(label, MAX_AGE_DAYS["default"])
        date_str = entry.get("date")
        if not date_str:
            entry["stale"] = True
            entry["age_days"] = None
            continue
        try:
            d = datetime.strptime(date_str, "%Y-%m-%d").date()
            age = (today - d).days
            entry["age_days"] = age
            entry["stale"] = age > max_age
        except ValueError:
            entry["stale"] = True
            entry["age_days"] = None
    return results

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

MAX_AGE_DAYS = {
    # Most CBOE/market series are daily — 10 days catches genuine staleness
    # without false alarms over a normal weekend/holiday gap.
    "default": 10,
    # Fed Funds (FEDFUNDS) is a MONTHLY series — 25-35 days old is completely
    # normal for it, not stale. A flat 10-day threshold was flagging it as
    # stale on every single run regardless of whether the fetch was healthy.
    "Fed Funds": 45,
}

def run():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("FRED_API_KEY not set — using yfinance for all series")

    results = {}
    for label, sid in SERIES.items():
        result = None
        used_source = None

        if api_key:
            try:
                result = fetch_series(sid, api_key)
                if result:
                    used_source = "FRED"
                else:
                    print(f"  {label}: no data from FRED")
            except Exception as e:
                print(f"  {label}: FRED ERROR {e}")

        # Fall back to yfinance for THIS series if FRED didn't return
        # anything — previously this fallback only ever fired when the API
        # key was missing entirely, so a single dead/renamed FRED series
        # (e.g. SKEW, which FRED now rejects with "series does not exist")
        # had no way to recover even though a working yfinance ticker (^SKEW)
        # was defined for exactly this case and simply never got tried.
        if not result:
            yf_ticker = YF_FALLBACK.get(label)
            if yf_ticker:
                result = fetch_yfinance(label, yf_ticker)
                if result:
                    used_source = "yfinance"

        if result:
            results[label] = result
            print(f"  {label}: {result['value']} ({result['date']}) via {used_source}")
        else:
            results[label] = {"date": None, "value": None}
            print(f"  {label}: no data from any source")

    results = _flag_staleness(results)
    for label, entry in results.items():
        if entry.get("stale"):
            age = entry.get("age_days")
            print(f"  WARNING: {label} is stale ({age if age is not None else 'unknown'} days old, or fetch failed)")

    out_path = os.path.join(OUTPUT_DIR, "fred_macro.json")
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "series": results}, f, indent=2)
    print(f"\nSaved FRED data to {out_path}")
    return True

if __name__ == "__main__":
    run()
