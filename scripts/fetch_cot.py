"""
Fetch CFTC Commitments of Traders positioning from the CFTC's public
reporting API, with ~3 years of weekly history per market.

Speculator group per market:
  - Gold:          Legacy report, Non-Commercial (088691, COMEX gold)
  - EURUSD:        Traders in Financial Futures, Leveraged Funds (099741, CME Euro FX)
  - NAS100:        Traders in Financial Futures, Leveraged Funds (209742, CME E-mini Nasdaq-100)
  - SPX500:        Traders in Financial Futures, Leveraged Funds (13874A, CME E-mini S&P 500)
  - US2000:        Traders in Financial Futures, Leveraged Funds (239742, CME Russell 2000 E-mini)
  - USDJPY:        Traders in Financial Futures, Leveraged Funds (097741, CME Japanese Yen).
                   The contract is JPY/USD, so the score is inverted: crowded
                   long yen is a contrarian case for USD/JPY going UP.

Markets are looked up by contract code, not name — CFTC renames markets
(e.g. "NASDAQ-100 STOCK INDEX (MINI)" became "NASDAQ MINI" in 2022), and a
name match silently returns the last report under the old name.

The signal is "extremes only": speculator net positioning (% of open
interest) is ranked against its own 3-year history. Only a crowded extreme
scores, and it scores contrarian — a structurally long market like gold
isn't penalised just for being long.
"""
import os, json
from datetime import datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
API = "https://publicreporting.cftc.gov/resource/{}.json"
HISTORY_WEEKS = 156

MARKETS = {
    "Gold": {
        "dataset": "6dca-aqww", "code": "088691",
        "long": "noncomm_positions_long_all", "short": "noncomm_positions_short_all",
        "group": "Non-Commercial (speculators)",
    },
    "EURUSD": {
        "dataset": "gpe5-46if", "code": "099741",
        "long": "lev_money_positions_long", "short": "lev_money_positions_short",
        "group": "Leveraged Funds (speculators)",
    },
    "NAS100": {
        "dataset": "gpe5-46if", "code": "209742",
        "long": "lev_money_positions_long", "short": "lev_money_positions_short",
        "group": "Leveraged Funds (speculators)",
    },
    "SPX500": {
        "dataset": "gpe5-46if", "code": "13874A",
        "long": "lev_money_positions_long", "short": "lev_money_positions_short",
        "group": "Leveraged Funds (speculators)",
    },
    "US2000": {
        "dataset": "gpe5-46if", "code": "239742",
        "long": "lev_money_positions_long", "short": "lev_money_positions_short",
        "group": "Leveraged Funds (speculators)",
    },
    "USDJPY": {
        "dataset": "gpe5-46if", "code": "097741",
        "long": "lev_money_positions_long", "short": "lev_money_positions_short",
        "group": "Leveraged Funds in yen futures", "invert": True,
    },
}

# Percentile-rank thresholds for "crowded" (contrarian) readings.
EXTREME = 90
VERY_EXTREME = 97


def fetch_rows(cfg):
    params = {
        "cftc_contract_market_code": cfg["code"],
        "$select": f"report_date_as_yyyy_mm_dd,market_and_exchange_names,{cfg['long']},{cfg['short']},open_interest_all",
        "$order": "report_date_as_yyyy_mm_dd DESC",
        "$limit": HISTORY_WEEKS,
    }
    r = requests.get(API.format(cfg["dataset"]), params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def percentile_rank(values, x):
    """Share of history at or below x, 0-100."""
    if not values:
        return None
    return round(sum(1 for v in values if v <= x) / len(values) * 100, 1)


def analyse(cfg, rows):
    hist = []
    for row in reversed(rows):  # chronological
        try:
            oi = float(row["open_interest_all"])
            long_, short = float(row[cfg["long"]]), float(row[cfg["short"]])
        except (KeyError, TypeError, ValueError):
            continue
        if oi <= 0:
            continue
        hist.append({"date": row["report_date_as_yyyy_mm_dd"][:10], "long": long_, "short": short,
                     "net": long_ - short, "net_pct": round((long_ - short) / oi * 100, 1), "oi": oi})
    if len(hist) < 52:
        return {"error": f"only {len(hist)} weeks of history"}

    latest, prior = hist[-1], hist[-2]
    rank = percentile_rank([h["net_pct"] for h in hist], latest["net_pct"])
    if rank >= VERY_EXTREME:
        signal, score = "CROWDED_LONG", -2
    elif rank >= EXTREME:
        signal, score = "CROWDED_LONG", -1
    elif rank <= 100 - VERY_EXTREME:
        signal, score = "CROWDED_SHORT", 2
    elif rank <= 100 - EXTREME:
        signal, score = "CROWDED_SHORT", 1
    else:
        signal, score = "NEUTRAL", 0

    if cfg.get("invert"):
        score = -score
    return {
        "date": latest["date"],
        "inverted": bool(cfg.get("invert")),
        "market": rows[0].get("market_and_exchange_names", ""),
        "group": cfg["group"],
        "open_interest": latest["oi"],
        "spec_long": latest["long"],
        "spec_short": latest["short"],
        "spec_net": latest["net"],
        "spec_net_pct": latest["net_pct"],
        "wow_change": latest["net"] - prior["net"],
        "pct_rank_3y": rank,
        "weeks": len(hist),
        "signal": signal,
        "score": score,
        "history": [{"date": h["date"], "net_pct": h["net_pct"]} for h in hist[-52:]],
    }


def run():
    print("Fetching CFTC COT data...")
    results = {}
    for instr, cfg in MARKETS.items():
        try:
            res = analyse(cfg, fetch_rows(cfg))
        except Exception as e:
            res = {"error": str(e)}
        results[instr] = res
        if "error" in res:
            print(f"  {instr}: ERROR {res['error']}")
        else:
            print(f"  {instr}: {res['date']} spec net {res['spec_net_pct']}% OI, "
                  f"{res['pct_rank_3y']}th pct of {res['weeks']}w → {res['signal']} ({res['score']:+d})")

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "cot_data.json"), "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    return all("error" not in r for r in results.values())


if __name__ == "__main__":
    run()
