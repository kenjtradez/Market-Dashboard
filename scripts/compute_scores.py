"""
Blend OME positioning data + FRED macro data into a bullish/bearish score
per instrument and an overall market score.
"""
import os
import json
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]

def score_positioning(ome):
    score = 0
    details = {}

    pcr = ome.get("put_call_ratio")
    if pcr is not None:
        if pcr < 0.7:
            score += 2
            details["pcr"] = f"{pcr:.2f} (bearish puts light, +2)"
        elif pcr > 1.3:
            score -= 2
            details["pcr"] = f"{pcr:.2f} (bearish puts heavy, -2)"
        else:
            details["pcr"] = f"{pcr:.2f} (neutral)"

    skew = ome.get("skew_percent")
    if skew is not None:
        if skew > 5:
            score += 1
            details["skew"] = f"{skew:.1f}% (calls favoured, +1)"
        elif skew < -5:
            score -= 1
            details["skew"] = f"{skew:.1f}% (puts favoured, -1)"
        else:
            details["skew"] = f"{skew:.1f}% (neutral)"

    magnet = ome.get("magnet_strike")
    spot = ome.get("spot", ome.get("underlying_price"))
    if magnet and spot:
        dist = (magnet - spot) / spot * 100
        if dist > 0:
            score += 1
            details["magnet"] = f"magnet {magnet} above spot (+1)"
        else:
            score -= 1
            details["magnet"] = f"magnet {magnet} below spot (-1)"
    else:
        details["magnet"] = "N/A"

    call_wall = ome.get("call_wall")
    put_wall = ome.get("put_wall")
    if call_wall and put_wall:
        if call_wall > put_wall:
            score += 1
            details["walls"] = f"C{call_wall} > P{put_wall} (+1)"
        elif call_wall < put_wall:
            score -= 1
            details["walls"] = f"C{call_wall} < P{put_wall} (-1)"
        else:
            details["walls"] = f"C{call_wall} = P{put_wall} (neutral)"
    else:
        details["walls"] = "N/A"

    max_pain = ome.get("max_pain")
    if max_pain:
        details["max_pain"] = max_pain

    return score, details

def score_macro(macro, instr=None):
    """Score macro environment. If instr is given, scores against its relevant volatility index."""
    score = 0
    details = {}

    vol_idx_map = {
        "Gold":   {"series": "GVZ", "label": "GVZ"},
        "NAS100": {"series": "VXN", "label": "VXN"},
        "EURUSD": {"series": "EVZ", "label": "EVZ"},
    }

    # Instrument-specific volatility index
    if instr and instr in vol_idx_map:
        vs = vol_idx_map[instr]
        vol = macro.get(vs["series"], {}).get("value")
        if vol is not None:
            if vol < 15:
                score += 1; details[f"{vs['label']}"] = f"{vol} (low fear, +1)"
            elif vol > 30:
                score -= 1; details[f"{vs['label']}"] = f"{vol} (high fear, -1)"
            else:
                details[f"{vs['label']}"] = f"{vol} (neutral)"
    else:
        # Fallback: VIX for general / unknown instruments
        vix = macro.get("VIX", {}).get("value")
        if vix is not None:
            if vix < 15:
                score += 1; details["VIX"] = f"{vix} (low fear, +1)"
            elif vix > 25:
                score -= 1; details["VIX"] = f"{vix} (high fear, -1)"
            else:
                details["VIX"] = f"{vix} (neutral)"

    dxy = macro.get("Dollar Index", {}).get("value")
    if dxy is not None:
        if dxy < 100:
            score += 1; details["dxy"] = f"{dxy} (weak USD bullish, +1)"
        elif dxy > 107:
            score -= 1; details["dxy"] = f"{dxy} (strong USD bearish, -1)"
        else:
            details["dxy"] = f"{dxy} (neutral)"

    curve = macro.get("10Y Yield", {}).get("value")
    short = macro.get("2Y Yield", {}).get("value")
    if curve is not None and short is not None:
        spread = curve - short
        if spread > 0.5:
            score += 1; details["curve"] = f"{spread:.2f}% (steep, +1)"
        elif spread < -0.5:
            score -= 1; details["curve"] = f"{spread:.2f}% (inverted, -1)"
        else:
            details["curve"] = f"{spread:.2f}% (neutral)"

    # SKEW (tail risk)
    skew = macro.get("SKEW", {}).get("value")
    if skew is not None:
        if skew > 145:
            score -= 1; details["skew"] = f"{skew} (tail risk high, -1)"
        elif skew < 120:
            score += 1; details["skew"] = f"{skew} (tail risk low, +1)"
        else:
            details["skew"] = f"{skew} (neutral)"

    # Breakeven inflation
    be5 = macro.get("5Y Breakeven", {}).get("value")
    if be5 is not None:
        if be5 > 3.0:
            score -= 1; details["be5"] = f"{be5}% (high inflation, -1)"
        elif be5 < 1.5:
            score += 1; details["be5"] = f"{be5}% (low inflation, +1)"
        else:
            details["be5"] = f"{be5}% (neutral)"

    return score, details

def run():
    # Load FRED macro
    macro_path = os.path.join(DATA_DIR, "fred_macro.json")
    macro_data = {}
    if os.path.exists(macro_path):
        with open(macro_path) as f:
            macro_data = json.load(f).get("series", {})
        print(f"Loaded FRED macro data ({len(macro_data)} series)")
    else:
        print("WARNING: No FRED data found — skipping macro scores")

    macro_score, macro_details = score_macro(macro_data)
    print(f"\nGeneral macro score: {macro_score}")
    for k, v in macro_details.items():
        print(f"  {k}: {v}")

    # Load OME data
    ome_path = os.path.join(DATA_DIR, "ome_data.json")
    ome_instruments = {}
    if os.path.exists(ome_path):
        with open(ome_path) as f:
            ome_instruments = json.load(f).get("instruments", {})
        print(f"\nLoaded OME data ({len(ome_instruments)} instruments)")
    else:
        print("WARNING: No OME data found")

    per_instrument = {}
    for instr in INSTRUMENTS:
        ome = ome_instruments.get(instr, {})
        if "error" in ome:
            per_instrument[instr] = {"error": ome["error"], "total_score": None}
            continue

        pos_score, pos_details = score_positioning(ome)
        instr_macro_score, instr_macro_details = score_macro(macro_data, instr)
        total = pos_score + instr_macro_score
        per_instrument[instr] = {
            "ome_data": {k: v for k, v in ome.items() if k != "raw"},
            "positioning_score": pos_score,
            "positioning_details": pos_details,
            "macro_score": instr_macro_score,
            "macro_details": instr_macro_details,
            "total_score": total,
            "signal": "LONG" if total > 0 else ("SHORT" if total < 0 else "NEUTRAL"),
        }
        print(f"\n{instr}: pos={pos_score} + macro={instr_macro_score} = {total} ({per_instrument[instr]['signal']})")
        for k, v in instr_macro_details.items():
            print(f"  macro.{k}: {v}")

    # Overall market score
    valid = {k: v for k, v in per_instrument.items() if v.get("total_score") is not None}
    avg = sum(v["total_score"] for v in valid.values()) / len(valid) if valid else 0

    # Aggregate macro for dashboard display (general macro)
    macro_details = per_instrument.get("Gold", {}).get("macro_details", {})
    # Also merge in the macro_score as the average across instruments
    macro_score_avg = sum(v["macro_score"] for v in valid.values()) / len(valid) if valid else 0

    output = {
        "generated": datetime.now().isoformat(),
        "macro": {"score": round(macro_score_avg, 1), "details": macro_details, "raw": macro_data},
        "instruments": per_instrument,
        "overall": {"avg_score": round(avg, 1), "signal": "LONG" if avg > 0 else ("SHORT" if avg < 0 else "NEUTRAL")},
    }

    out_path = os.path.join(OUTPUT_DIR, "scores.json")
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved scores to {out_path}")
    print(f"Overall: {output['overall']['signal']} ({output['overall']['avg_score']})")
    return output

if __name__ == "__main__":
    run()
