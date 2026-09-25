"""
Blend options positioning, macro and COT into one score per instrument.
This is the single scoring model: the dashboard, the tracker tab and the
Telegram brief all read scores.json rather than scoring on their own.

Components (max magnitude):
  Positioning  ±4  PCR ±2, ATM IV skew ±1, magnet vs spot ±1
  Macro        ±5  instrument vol index, DXY, 2s10s curve, SKEW, 5Y breakeven
  COT          ±2  speculator positioning, only at 3-year extremes (contrarian)

Signal: LONG / SHORT only when |total| >= SIGNAL_THRESHOLD, else NEUTRAL.
"""
import os
import json
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = ["Gold", "NAS100", "SPX500", "US2000", "EURUSD", "USDJPY"]
MAX_POSITIONING, MAX_MACRO, MAX_COT = 4, 5, 2
MAX_SCORE = MAX_POSITIONING + MAX_MACRO + MAX_COT
SIGNAL_THRESHOLD = 2
# "High-probability" needs components to agree AND a total of at least this.
CONFLUENCE_MIN = 4
OPTIONS_MAX_AGE_HOURS = 96
# PCR is judged against the ETF's own history: index ETFs are structurally
# put-heavy (hedging) and GLD call-heavy, so fixed 0.7 / 1.3 levels scored
# NAS100 -2 and gold +2 almost every day. Needs this many daily readings.
PCR_MIN_HISTORY = 20
PCR_EXTREME_PCT = 20  # OI is published once a day; a weekend-old snapshot is still usable

# Instrument-specific implied-vol index. EURUSD has none since CBOE retired EVZ.
VOL_INDEX = {"Gold": "GVZ", "NAS100": "VXN", "SPX500": "VIX", "US2000": "RVX", "EURUSD": None, "USDJPY": None}
# (low-fear, high-fear) levels per vol index. RVX runs structurally higher.
VOL_LEVELS = {"VIX": (15, 25), "VXN": (15, 30), "GVZ": (15, 30), "RVX": (18, 32)}
# USD/JPY rises when the dollar is strong, so the DXY point flips sign for it.
USD_BASE = {"USDJPY"}


def load(name):
    path = os.path.join(DATA_DIR, name)
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}


def signal_for(total):
    if total is None:
        return "N/A"
    if total >= SIGNAL_THRESHOLD:
        return "LONG"
    if total <= -SIGNAL_THRESHOLD:
        return "SHORT"
    return "NEUTRAL"


def options_age_hours(ome):
    try:
        return (datetime.now() - datetime.fromisoformat(ome["as_of"])).total_seconds() / 3600
    except (KeyError, TypeError, ValueError):
        return None


def options_usable(ome):
    age = options_age_hours(ome or {})
    return bool(ome) and "error" not in ome and age is not None and age <= OPTIONS_MAX_AGE_HOURS


def percentile_rank(values, x):
    return sum(1 for v in values if v <= x) / len(values) * 100


def score_positioning(ome, pcr_hist=None):
    if not options_usable(ome):
        why = (ome or {}).get("error") or f"no usable snapshot (last {(ome or {}).get('as_of', 'never')})"
        return 0, {"options": why}

    score, details = 0, {}
    pcr = ome.get("put_call_ratio")
    if pcr is not None:
        today = str(ome.get("as_of", ""))[:10]
        past = [r["pcr"] for r in (pcr_hist or []) if r["date"] != today]
        if len(past) < PCR_MIN_HISTORY:
            details["pcr"] = f"{pcr:.2f} (building history {len(past)}/{PCR_MIN_HISTORY}, not scored)"
        else:
            rank = percentile_rank(past, pcr)
            if rank <= PCR_EXTREME_PCT:
                score += 2; details["pcr"] = f"{pcr:.2f}, {rank:.0f}th pct of its {len(past)}d history (call-heavy, +2)"
            elif rank >= 100 - PCR_EXTREME_PCT:
                score -= 2; details["pcr"] = f"{pcr:.2f}, {rank:.0f}th pct of its {len(past)}d history (put-heavy, -2)"
            else:
                details["pcr"] = f"{pcr:.2f}, {rank:.0f}th pct of its {len(past)}d history (neutral)"

    skew = ome.get("skew_percent")
    if skew is not None:
        if skew > 5:
            score += 1; details["skew"] = f"{skew:.1f}% (calls bid, +1)"
        elif skew < -5:
            score -= 1; details["skew"] = f"{skew:.1f}% (puts bid, -1)"
        else:
            details["skew"] = f"{skew:.1f}% (neutral)"

    magnet, spot = ome.get("magnet_strike"), ome.get("underlying_price")
    if magnet and spot:
        dist = (magnet - spot) / spot * 100
        if dist > 0.25:
            score += 1; details["magnet"] = f"{magnet} is {dist:.1f}% above spot (+1)"
        elif dist < -0.25:
            score -= 1; details["magnet"] = f"{magnet} is {abs(dist):.1f}% below spot (-1)"
        else:
            details["magnet"] = f"{magnet} at spot (neutral)"
    return score, details


def score_cot(cot):
    if not cot or "error" in cot:
        return 0, {"cot": (cot or {}).get("error", "no COT data")}
    s = cot.get("score", 0)
    rank, pct = cot.get("pct_rank_3y"), cot.get("spec_net_pct")
    if cot.get("inverted"):
        side = {"CROWDED_LONG": "crowded long yen", "CROWDED_SHORT": "crowded short yen"}.get(cot.get("signal"))
        text = (f"yen specs {pct}% net, {rank}th pct of 3y ({side}, {s:+d} for USD/JPY)" if side
                else f"yen specs {pct}% net, {rank}th pct of 3y (not extreme, 0)")
        return s, {"cot": text}
    if cot.get("signal") == "CROWDED_LONG":
        text = f"specs {pct}% net long, {rank}th pct of 3y (crowded long, {s:+d})"
    elif cot.get("signal") == "CROWDED_SHORT":
        text = f"specs {pct}% net, {rank}th pct of 3y (crowded short, {s:+d})"
    else:
        text = f"specs {pct}% net, {rank}th pct of 3y (not extreme, 0)"
    return s, {"cot": text}


def live(macro, key):
    """Latest value of a macro series, or None if missing or stale."""
    entry = macro.get(key, {})
    if entry.get("stale") or entry.get("value") is None:
        return None
    return entry["value"]


def score_macro(macro, instr=None):
    score, details = 0, {}

    vol_key = VOL_INDEX.get(instr) if instr else "VIX"
    if vol_key:
        vol = live(macro, vol_key)
        lo, hi = VOL_LEVELS[vol_key]
        if vol is not None:
            if vol < lo:
                score += 1; details[vol_key] = f"{vol} (low fear, +1)"
            elif vol > hi:
                score -= 1; details[vol_key] = f"{vol} (high fear, -1)"
            else:
                details[vol_key] = f"{vol} (neutral)"
    else:
        details["vol"] = "no live vol index for this pair"

    dxy = live(macro, "Dollar Index")
    if dxy is not None:
        sign = -1 if instr in USD_BASE else 1
        if dxy < 100:
            score += sign; details["dxy"] = f"DXY {dxy} (weak USD, {sign:+d})"
        elif dxy > 107:
            score -= sign; details["dxy"] = f"DXY {dxy} (strong USD, {-sign:+d})"
        else:
            details["dxy"] = f"DXY {dxy} (neutral)"

    y10, y2 = live(macro, "10Y Yield"), live(macro, "2Y Yield")
    if y10 is not None and y2 is not None:
        spread = y10 - y2
        if spread > 0.5:
            score += 1; details["curve"] = f"{spread:.2f}% (steep, +1)"
        elif spread < -0.5:
            score -= 1; details["curve"] = f"{spread:.2f}% (inverted, -1)"
        else:
            details["curve"] = f"{spread:.2f}% (neutral)"

    skew = live(macro, "SKEW")
    if skew is not None:
        if skew > 145:
            score -= 1; details["skew"] = f"{skew} (tail risk high, -1)"
        elif skew < 120:
            score += 1; details["skew"] = f"{skew} (tail risk low, +1)"
        else:
            details["skew"] = f"{skew} (neutral)"

    be5 = live(macro, "5Y Breakeven")
    if be5 is not None:
        if be5 > 3.0:
            score -= 1; details["be5"] = f"{be5}% (high inflation, -1)"
        elif be5 < 1.5:
            score += 1; details["be5"] = f"{be5}% (low inflation, +1)"
        else:
            details["be5"] = f"{be5}% (neutral)"

    return score, details


def run():
    macro_data = load("fred_macro.json").get("series", {})
    ome_all = load("ome_data.json").get("instruments", {})
    cot_all = load("cot_data.json").get("instruments", {})
    pcr_hist = load("pcr_history.json")

    general_score, general_details = score_macro(macro_data)
    print(f"General macro: {general_score} {general_details}")

    per_instrument = {}
    for instr in INSTRUMENTS:
        ome = ome_all.get(instr, {})
        pos, pos_d = score_positioning(ome, pcr_hist.get(instr))
        mac, mac_d = score_macro(macro_data, instr)
        cot, cot_d = score_cot(cot_all.get(instr))
        total = pos + mac + cot
        per_instrument[instr] = {
            "ome_data": ome,
            "options_ok": options_usable(ome),
            "positioning_score": pos, "positioning_details": pos_d,
            "macro_score": mac, "macro_details": mac_d,
            "cot_score": cot, "cot_details": cot_d,
            "total_score": total,
            "signal": signal_for(total),
        }
        print(f"{instr}: pos {pos:+d} + macro {mac:+d} + cot {cot:+d} = {total:+d} ({signal_for(total)})")
        for k, v in {**pos_d, **mac_d, **cot_d}.items():
            print(f"    {k}: {v}")

    totals = [v["total_score"] for v in per_instrument.values()]
    avg = sum(totals) / len(totals)
    output = {
        "generated": datetime.now().isoformat(),
        "model": {"max_score": MAX_SCORE, "max_positioning": MAX_POSITIONING, "max_macro": MAX_MACRO,
                  "max_cot": MAX_COT, "signal_threshold": SIGNAL_THRESHOLD,
                  "confluence_min": CONFLUENCE_MIN},
        "macro": {"score": general_score, "details": general_details},
        "instruments": per_instrument,
        "overall": {"avg_score": round(avg, 1), "signal": signal_for(avg)},
    }
    with open(os.path.join(DATA_DIR, "scores.json"), "w") as f:
        json.dump(output, f, indent=2)
    print(f"Overall: {output['overall']['signal']} ({output['overall']['avg_score']})")
    return True


if __name__ == "__main__":
    run()
