"""
Fetch news from Finnhub free /news endpoint.
Computes bullish/bearish signal by keyword scoring on headlines.
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

BULLISH_WORDS = ["surge", "rally", "jump", "soar", "gain", "bullish", "upgrade", "outperform",
                 "positive", "growth", "boom", "breakout", "upside", "beat", "strong"]
BEARISH_WORDS = ["plunge", "crash", "drop", "slump", "decline", "bearish", "downgrade",
                 "underperform", "negative", "loss", "slowdown", "fear", "selloff", "weak",
                 "cut", "warning", "recession", "fall", "tumble"]


def fetch_news(ticker, api_key):
    url = f"{BASE}/company-news"
    params = {"symbol": ticker, "from": "2026-07-27", "to": "2026-07-29", "token": api_key}
    try:
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            return {"error": f"HTTP {resp.status_code}"}
    except Exception as e:
        return {"error": str(e)}


def score_headlines(articles):
    if not isinstance(articles, list):
        return None, "no articles"
    bullish = 0
    bearish = 0
    neutral = 0
    for art in articles[:50]:
        headline = (art.get("headline", "") or "").lower()
        if not headline:
            continue
        b = sum(1 for w in BULLISH_WORDS if w in headline)
        be = sum(1 for w in BEARISH_WORDS if w in headline)
        if b > be:
            bullish += 1
        elif be > b:
            bearish += 1
        else:
            neutral += 1
    total = bullish + bearish + neutral
    if total == 0:
        return None, "no articles with headlines"
    bp = round(bullish / total * 100, 1)
    bep = round(bearish / total * 100, 1)
    net = bp - bep
    if net > 15:
        sig = "BULLISH"
    elif net < -15:
        sig = "BEARISH"
    else:
        sig = "NEUTRAL"
    return sig, f"bullish {bp}% vs bearish {bep}% (net {net:+.0f}% across {total} articles)"


def run():
    api_key = os.environ.get("FINNHUB_API_KEY")
    if not api_key:
        print("ERROR: FINNHUB_API_KEY env var not set")
        return False

    print("Fetching Finnhub news sentiment...")
    results = {}
    for instr, ticker in TICKER_MAP.items():
        news = fetch_news(ticker, api_key)
        if isinstance(news, dict) and "error" in news:
            results[instr] = {"ticker": ticker, "signal": None, "detail": news["error"]}
            print(f"  {instr} ({ticker}): ERROR — {news['error']}")
            continue
        sig, detail = score_headlines(news)
        results[instr] = {
            "ticker": ticker,
            "signal": sig,
            "detail": detail,
            "n_articles": len(news) if isinstance(news, list) else 0,
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
