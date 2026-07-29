"""
Compute news sentiment from GDELT geopolitical articles.
Scores headlines per instrument using bullish/bearish keyword lists.
No API key required.
"""
import os, json
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = {
    "Gold":   ["gold", "precious metal", "gld", "xau", "commodity"],
    "NAS100": ["nasdaq", "tech", "semiconductor", "qqq", "big tech", "ai", "software"],
    "EURUSD": ["euro", "ecb", "european", "fxe", "eur", "germany", "france", "dax"],
}

BULLISH_WORDS = ["surge", "rally", "jump", "soar", "gain", "bullish", "upgrade", "outperform",
                 "positive", "growth", "boom", "breakout", "upside", "beat", "strong", "recovery"]
BEARISH_WORDS = ["plunge", "crash", "drop", "slump", "decline", "bearish", "downgrade",
                 "underperform", "negative", "loss", "slowdown", "fear", "selloff", "weak",
                 "cut", "warning", "recession", "fall", "tumble", "crisis", "sanction", "war"]


def score_headlines(articles, instrument_terms):
    relevant = []
    for art in articles:
        txt = (art.get("title", "") + " " + art.get("seentext", "")).lower()
        if any(t in txt for t in instrument_terms):
            relevant.append(art.get("title", ""))

    if not relevant:
        return None, "no relevant articles"

    bullish = 0
    bearish = 0
    for h in relevant:
        h_lower = h.lower()
        b = sum(1 for w in BULLISH_WORDS if w in h_lower)
        be = sum(1 for w in BEARISH_WORDS if w in h_lower)
        if b > be:
            bullish += 1
        elif be > b:
            bearish += 1

    total = len(relevant)
    bp = round(bullish / total * 100, 1)
    bep = round(bearish / total * 100, 1)
    net = bp - bep

    if net > 15:
        sig = "BULLISH"
    elif net < -15:
        sig = "BEARISH"
    else:
        sig = "NEUTRAL"
    return sig, f"bullish {bp}% vs bearish {bep}% (net {net:+.0f}%, {total} articles)"


def run():
    geo_path = os.path.join(DATA_DIR, "geopolitical.json")
    if not os.path.exists(geo_path):
        print("No geopolitical.json found — skipping sentiment")
        return False

    with open(geo_path) as f:
        geo = json.load(f)

    articles = geo.get("articles", [])
    if not articles:
        print("No articles in geopolitical.json — outputting neutral signals")
        results = {instr: {"signal": "NEUTRAL", "detail": "no articles available", "source": "gdelt"} for instr in INSTRUMENTS}
        out_path = os.path.join(DATA_DIR, "sentiment.json")
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
        print(f"  Saved neutral sentiment to {out_path}")
        return True

    print("Computing news sentiment from GDELT articles...")
    results = {}
    for instr, terms in INSTRUMENTS.items():
        sig, detail = score_headlines(articles, terms)
        results[instr] = {"signal": sig, "detail": detail, "source": "gdelt"}
        print(f"  {instr}: {sig} — {detail}")

    out_path = os.path.join(DATA_DIR, "sentiment.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True


if __name__ == "__main__":
    run()
