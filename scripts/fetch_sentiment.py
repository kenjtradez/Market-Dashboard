"""
Headline sentiment per instrument, from the RSS headlines collected by
fetch_geopolitical.py. Display only — not part of the score.

The bearish word list deliberately excludes the geopolitical terms (war,
crisis, sanction) used to build the risk list: counting them again here
biased every reading bearish, and they are often bullish for gold anyway.
"""
import os, json, re
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
INSTRUMENTS = ["Gold", "NAS100", "SPX500", "US2000", "EURUSD", "USDJPY"]
MIN_HEADLINES = 3

BULLISH_WORDS = ["surge", "surges", "rally", "rallies", "jump", "jumps", "soar", "soars", "gain", "gains",
                 "rise", "rises", "climb", "climbs", "bullish", "upgrade", "outperform", "record high",
                 "breakout", "upside", "beat", "beats", "rebound", "rebounds", "recovery", "firmer"]
BEARISH_WORDS = ["plunge", "plunges", "crash", "drop", "drops", "slump", "slumps", "decline", "declines",
                 "bearish", "downgrade", "underperform", "loss", "losses", "selloff", "sell-off", "weak",
                 "weaker", "fall", "falls", "tumble", "tumbles", "slide", "slides", "retreat", "retreats"]


def has_term(text, term):
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def score(headlines):
    bull = bear = 0
    for h in headlines:
        t = h.lower()
        b = sum(has_term(t, w) for w in BULLISH_WORDS)
        s = sum(has_term(t, w) for w in BEARISH_WORDS)
        bull += b > s
        bear += s > b
    total = len(headlines)
    net = (bull - bear) / total * 100
    sig = "BULLISH" if net > 15 else "BEARISH" if net < -15 else "NEUTRAL"
    return sig, f"{bull} bullish / {bear} bearish of {total} headlines (net {net:+.0f}%)"


def run():
    path = os.path.join(DATA_DIR, "geopolitical.json")
    if not os.path.exists(path):
        print("No geopolitical.json — skipping sentiment")
        return False
    with open(path) as f:
        headlines = json.load(f).get("headlines", [])

    results = {}
    for instr in INSTRUMENTS:
        rel = [h["title"] for h in headlines if instr in h.get("instruments", [])]
        if len(rel) < MIN_HEADLINES:
            results[instr] = {"signal": None, "detail": f"only {len(rel)} relevant headlines", "source": "RSS headlines"}
        else:
            sig, detail = score(rel)
            results[instr] = {"signal": sig, "detail": detail, "source": "RSS headlines"}
        print(f"  {instr}: {results[instr]['signal']} — {results[instr]['detail']}")

    with open(os.path.join(DATA_DIR, "sentiment.json"), "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    return True


if __name__ == "__main__":
    run()
