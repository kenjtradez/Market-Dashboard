"""
Fetch news sentiment from Finnhub for tracked instruments.
Uses the news-sentiment endpoint for aggregate bullish/bearish scores.
Ticker mapping: Gold->GLD, NAS100->QQQ, EURUSD->FXE
"""
import os, json
from datetime import datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
BASE = "https://finnhub.io/api/v1"

TICKER_MAP = {
    "Gold":   "GLD",
    "NAS100": "QQQ",
    "EURUSD": "FXE",
}

def fetch_sentiment(ticker, api_key):
    url = f"{BASE}/news-sentiment"
    params = {"symbol": ticker, "token": api_key}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}

def compute_signal(sent):
    """Convert Finnhub sentiment dict to a simple signal."""
    if "error" in sent:
        return None, sent.get("error")
    s = sent.get("sentiment", {})
    bp = s.get("bullishPercent", 50)
    bear = s.get("bearishPercent", 50)
    if bp is None or bear is None or (bp + bear) == 0:
        return None, "no sentiment data"

    net = bp - bear
    if net > 10:
        return "BULLISH", f"bullish {bp:.0f}% vs bearish {bear:.0f}% (net {net:+.0f}%)"
    elif net < -10:
        return "BEARISH", f"bullish {bp:.0f}% vs bearish {bear:.0f}% (net {net:+.0f}%)"
    else:
        return "NEUTRAL", f"bullish {bp:.0f}% vs bearish {bear:.0f}% (mixed)"

def run():
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        print("ERROR: FINNHUB_API_KEY env var not set")
        return False

    print("Fetching Finnhub news sentiment...")
    results = {}
    for instr, ticker in TICKER_MAP.items():
        sent = fetch_sentiment(ticker, api_key)
        sig, detail = compute_signal(sent)
        results[instr] = {
            "ticker": ticker,
            "signal": sig,
            "detail": detail,
            "bullish_pct": sent.get("sentiment", {}).get("bullishPercent"),
            "bearish_pct": sent.get("sentiment", {}).get("bearishPercent"),
            "company_news_score": sent.get("companyNewsScore"),
            "buzz": sent.get("buzz", {}).get("buzz"),
        }
        print(f"  {instr} ({ticker}): {sig} — {detail}")

    out_path = os.path.join(DATA_DIR, "sentiment.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True

if __name__ == "__main__":
    run()
