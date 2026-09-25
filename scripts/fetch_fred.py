"""
Fetch macro data used for scoring (latest value per series) plus a 90-day
history of the tracker's macro-panel series.

Each series lists its sources in priority order: ("fred", SERIES_ID) or
("yf", TICKER). FRED needs FRED_API_KEY; yfinance needs nothing.

Notes on specific series:
  - Dollar Index is the real ICE DXY (yfinance DX-Y.NYB). FRED has no DXY —
    its DTWEXBGS is the Fed's *broad* trade-weighted index, which sits ~20
    points higher (~120 vs ~100). Scoring thresholds are DXY levels, so the
    broad index is kept separately as "Broad USD" for display only.
  - SKEW does not exist on FRED; it comes straight from yfinance.
  - EVZ (CBOE EuroCurrency vol) was discontinued in 2025 and is not fetched.
  - Fed Funds uses DFF (daily effective rate), not the monthly FEDFUNDS.
"""
import os
import json
import requests
from datetime import datetime

FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

SERIES = {
    "10Y Yield":     [("fred", "DGS10"), ("yf", "^TNX")],
    "2Y Yield":      [("fred", "DGS2")],
    "5Y Breakeven":  [("fred", "T5YIE")],
    "10Y Breakeven": [("fred", "T10YIE")],
    "VIX":           [("fred", "VIXCLS"), ("yf", "^VIX")],
    "VXN":           [("fred", "VXNCLS"), ("yf", "^VXN")],
    "GVZ":           [("fred", "GVZCLS"), ("yf", "^GVZ")],
    "SKEW":          [("yf", "^SKEW")],
    "Dollar Index":  [("yf", "DX-Y.NYB")],
    "Broad USD":     [("fred", "DTWEXBGS")],
    "Fed Funds":     [("fred", "DFF")],
}

# Series shown with sparklines on the tracker's Macro tab. "bias" is the
# textbook sign of each instrument's reaction when the series RISES.
HISTORY_SERIES = [
    {"id": "DFF",      "label": "Fed funds rate",          "decimals": 2, "note": "Sets the front end of the curve for all three.",   "bias": {"XAUUSD": -1, "EURUSD": -1, "NAS100": -1}},
    {"id": "DGS10",    "label": "10Y Treasury yield",      "decimals": 2, "note": "Discount rate, risk sentiment.",                   "bias": {"XAUUSD": -1, "EURUSD": -1, "NAS100": -1}},
    {"id": "DFII10",   "label": "10Y real yield (TIPS)",   "decimals": 2, "note": "Key gold driver — inverse relationship.",     "bias": {"XAUUSD": -1, "EURUSD": -1, "NAS100": -1}},
    {"id": "T10YIE",   "label": "10Y breakeven inflation", "decimals": 2, "note": "Inflation expectations.",                          "bias": {"XAUUSD": 1,  "EURUSD": 0,  "NAS100": 0}},
    {"id": "DTWEXBGS", "label": "Trade-weighted USD index", "decimals": 2, "note": "Broad dollar strength, moves EUR/USD and gold.",   "bias": {"XAUUSD": -1, "EURUSD": -1, "NAS100": -1}},
    {"id": "VIXCLS",   "label": "VIX",                     "decimals": 2, "note": "Risk-off gauge, pressures Nasdaq.",                "bias": {"XAUUSD": 1,  "EURUSD": -1, "NAS100": -1}},
    {"id": "UNRATE",   "label": "Unemployment rate",       "decimals": 1, "note": "Monthly, moves Fed policy expectations.",          "bias": {"XAUUSD": 1,  "EURUSD": 1,  "NAS100": 0}},
]

MAX_AGE_DAYS = {
    # Daily market series: 10 days covers weekends and holidays.
    "default": 10,
}


def fetch_fred(series_id, api_key, limit=2):
    params = {
        "series_id": series_id,
        "api_key": api_key,
        "file_type": "json",
        "sort_order": "desc",
        "limit": limit,
    }
    r = requests.get(FRED_BASE, params=params, timeout=15)
    if r.status_code == 400:
        msg = r.json().get("error_message", "")
        if "api_key" in msg.lower():
            raise Exception("INVALID FRED API KEY")
        raise Exception(f"Bad request: {msg[:200]}")
    r.raise_for_status()
    return [o for o in r.json().get("observations", []) if o.get("value") not in (".", "")]


def fetch_fred_latest(series_id, api_key):
    obs = fetch_fred(series_id, api_key, limit=5)
    if not obs:
        return None
    return {"date": obs[0]["date"], "value": float(obs[0]["value"])}


def fetch_yf_latest(ticker):
    import yfinance as yf
    try:
        hist = yf.Ticker(ticker).history(period="5d")
        if hist.empty:
            return None
        return {"date": hist.index[-1].strftime("%Y-%m-%d"), "value": round(float(hist["Close"].iloc[-1]), 2)}
    except Exception as e:
        print(f"    yfinance error for {ticker}: {e}")
        return None


def flag_staleness(results):
    """Mark any series whose latest observation is older than its threshold,
    so scoring can ignore it instead of treating a frozen value as live."""
    today = datetime.now().date()
    for label, entry in results.items():
        max_age = MAX_AGE_DAYS.get(label, MAX_AGE_DAYS["default"])
        date_str = entry.get("date")
        if not date_str:
            entry["stale"], entry["age_days"] = True, None
            continue
        age = (today - datetime.strptime(date_str, "%Y-%m-%d").date()).days
        entry["age_days"] = age
        entry["stale"] = age > max_age
    return results


def fetch_history(api_key):
    out = []
    for s in HISTORY_SERIES:
        rec = dict(s)
        try:
            obs = fetch_fred(s["id"], api_key, limit=90)
            rec["obs"] = [{"date": o["date"], "value": float(o["value"])} for o in reversed(obs)]
        except Exception as e:
            rec["obs"], rec["error"] = [], str(e)
        out.append(rec)
    return out


def run():
    api_key = os.environ.get("FRED_API_KEY")
    if not api_key:
        print("FRED_API_KEY not set — FRED-only series will be empty")

    results = {}
    for label, sources in SERIES.items():
        result, used = None, None
        for kind, ident in sources:
            if kind == "fred":
                if not api_key:
                    continue
                try:
                    result = fetch_fred_latest(ident, api_key)
                except Exception as e:
                    print(f"  {label}: FRED ERROR {e}")
            else:
                result = fetch_yf_latest(ident)
            if result:
                used = f"{kind}:{ident}"
                break
        if result:
            result["source"] = used
            results[label] = result
            print(f"  {label}: {result['value']} ({result['date']}) via {used}")
        else:
            results[label] = {"date": None, "value": None}
            print(f"  {label}: no data from any source")

    flag_staleness(results)
    for label, entry in results.items():
        if entry.get("stale"):
            print(f"  WARNING: {label} is stale ({entry.get('age_days')} days old, or fetch failed) — excluded from scoring")

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "fred_macro.json"), "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "series": results}, f, indent=2)

    if api_key:
        history = fetch_history(api_key)
        with open(os.path.join(OUTPUT_DIR, "fred_history.json"), "w") as f:
            json.dump({"fetched": datetime.now().isoformat(), "series": history}, f)
        print(f"  Saved {len(history)} macro history series")

    print("\nSaved macro data")
    return True


if __name__ == "__main__":
    run()
