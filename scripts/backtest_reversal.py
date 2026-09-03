"""
Backtest: reversal rate at forecast levels (Proj H/L Median/75th/90th).

This answers a genuinely different question from anything else in this
pipeline: not "how far does price typically travel" (that's what
calc_vol_range.py and the Pine script's Proj H/L levels measure — an
EXCURSION FREQUENCY stat) but "once price gets near a projected level, how
often does it then turn back rather than continue through" (a REVERSAL
PROBABILITY stat). These are not the same thing and one cannot be inferred
from the other — a level can be reached often and still get broken through
more often than not.

Definition used (per user spec):
  - "Touched": that day's High (for upside levels) or Low (for downside
    levels) came within TOLERANCE of the projected level.
  - "Reversed": having touched, the day's CLOSE finished back on the near
    side of the level (didn't hold beyond it) — i.e. price reacted to the
    level and pulled back rather than sustaining a break through it.
  - reversal_rate = reversed_count / touched_count, per level tier, per
    instrument, per direction.

Walk-forward, no lookahead: each day's projected levels are computed ONLY
from the trailing LOOKBACK days strictly BEFORE that day (same percentile
methodology as calc_vol_range.py / the Pine script — (High-Open)/Open and
(Open-Low)/Open as separate distributions). The day being tested is never
included in its own level calculation.

Standalone analysis script — not part of the scheduled dashboard pipeline
(this is a one-off/occasional research run, not something that needs to run
2x/day). Run manually: python scripts/backtest_reversal.py
"""
import os, json
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Long-history tickers — gold-api.com (used for live spot) has no historical
# endpoint, so this uses the same futures/index tickers that already have
# ample yfinance history. Day-to-day RANGE (which is what this backtest
# actually measures — High/Low/Close relative to Open) tracks almost
# identically between spot and futures, so this doesn't introduce the kind
# of error the live spot-price fix was solving for.
TICKERS = {
    "Gold":   "GC=F",
    "NAS100": "^NDX",
    "EURUSD": "EURUSD=X",
}

TOLERANCE = {
    "Gold":   5.0,       # $5
    "NAS100": 3.0,       # 3 index points
    "EURUSD": 0.0003,    # 3 pips
}

LOOKBACK = 60       # trailing days used to compute each day's projected levels
HISTORY_YEARS = 5   # how much history to pull per instrument
TIERS = ["median", "p75", "p90"]
PERCENTILES = {"median": 50, "p75": 75, "p90": 90}


def _extract_ohlc(df, ticker, i):
    row = df.iloc[i]
    if isinstance(df.columns, pd.MultiIndex):
        return (float(row[("Open", ticker)]), float(row[("High", ticker)]),
                float(row[("Low", ticker)]), float(row[("Close", ticker)]))
    return (float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"]))


def backtest_instrument(instr, ticker, tolerance):
    print(f"  {instr} ({ticker})...", end=" ", flush=True)
    end = datetime.now()
    start = end - timedelta(days=int(365.25 * HISTORY_YEARS))
    try:
        df = yf.download(ticker, start=start.strftime("%Y-%m-%d"), end=end.strftime("%Y-%m-%d"), progress=False)
    except Exception as e:
        print(f"ERROR: {e}")
        return None
    if df.empty or len(df) < LOOKBACK + 20:
        print(f"ERROR: insufficient data ({len(df)} rows)")
        return None

    n = len(df)
    # counts[direction][tier] = {"touched": int, "reversed": int}
    counts = {
        "up": {t: {"touched": 0, "reversed": 0} for t in TIERS},
        "down": {t: {"touched": 0, "reversed": 0} for t in TIERS},
    }

    for i in range(LOOKBACK, n):
        # Trailing window strictly BEFORE day i — no lookahead.
        up_exc, down_exc = [], []
        for j in range(i - LOOKBACK, i):
            o, h, l, c = _extract_ohlc(df, ticker, j)
            if o == 0:
                continue
            up_exc.append((h - o) / o * 100)
            down_exc.append((o - l) / o * 100)
        if not up_exc or not down_exc:
            continue

        o_today, h_today, l_today, c_today = _extract_ohlc(df, ticker, i)
        if o_today == 0:
            continue

        for tier in TIERS:
            pctl = PERCENTILES[tier]
            up_level = o_today * (1 + np.percentile(up_exc, pctl) / 100)
            down_level = o_today * (1 - np.percentile(down_exc, pctl) / 100)

            # Upside level: touched if High got within tolerance of it or beyond
            if h_today >= up_level - tolerance:
                counts["up"][tier]["touched"] += 1
                if c_today < up_level:
                    counts["up"][tier]["reversed"] += 1

            # Downside level: touched if Low got within tolerance of it or beyond
            if l_today <= down_level + tolerance:
                counts["down"][tier]["touched"] += 1
                if c_today > down_level:
                    counts["down"][tier]["reversed"] += 1

    result = {"total_days_tested": n - LOOKBACK, "tolerance": tolerance, "levels": {}}
    for direction in ("up", "down"):
        for tier in TIERS:
            c = counts[direction][tier]
            rate = round(c["reversed"] / c["touched"] * 100, 1) if c["touched"] > 0 else None
            result["levels"][f"{direction}_{tier}"] = {
                "touched_count": c["touched"],
                "reversed_count": c["reversed"],
                "reversal_rate_pct": rate,
            }
    print(f"OK — {result['total_days_tested']} days tested")
    return result


def run():
    print("Backtesting reversal rates at forecast levels...")
    print(f"Definition: touch within tolerance, then close back on the near side = reversal.")
    print(f"Lookback for level calc: {LOOKBACK}d (walk-forward, no lookahead). History pulled: {HISTORY_YEARS}y.\n")

    results = {}
    for instr, ticker in TICKERS.items():
        r = backtest_instrument(instr, ticker, TOLERANCE[instr])
        if r:
            results[instr] = r

    print("\n" + "=" * 70)
    print("RESULTS")
    print("=" * 70)
    for instr, r in results.items():
        print(f"\n{instr} — {r['total_days_tested']} days tested, tolerance {r['tolerance']}")
        for level_key, v in r["levels"].items():
            direction, tier = level_key.split("_")
            label = f"{direction.upper():4s} {tier:6s}"
            if v["reversal_rate_pct"] is None:
                print(f"  {label}: never touched in this sample")
            else:
                print(f"  {label}: touched {v['touched_count']:4d}x, reversed {v['reversed_count']:4d}x "
                      f"-> {v['reversal_rate_pct']}% reversal rate")

    out_path = os.path.join(DATA_DIR, "reversal_backtest.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"generated": datetime.now().isoformat(), "results": results}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return True


if __name__ == "__main__":
    run()
