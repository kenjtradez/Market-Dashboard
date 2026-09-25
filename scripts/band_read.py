"""
Band Read: where each instrument sits against today's vol bands, what it
did at the 10:00 London checkpoint, and what history says happens next.

Definitions match scripts/build_band_calibration.py, which builds the
probability tables in calibration/band_tables.json from 10 years of
minute data. This script only looks today's position up in those tables.

  - Session: 17:00 New York to 17:00 New York.
  - Bands: session open +/- the median / 75th-percentile up and down moves
    (from vol_range.json: the trailing 75 sessions, as in the indicator).
  - Position: 0 = at the open, 1 = at the next band not reached yet.
  - Extended at 10:00: the 10:00 London price was >= 75% of the way to a
    median band, and further than toward the other side.
Intraday prices: Yahoo 5-minute bars (about 15 minutes delayed for
futures). Gold futures are rescaled to live spot; NAS100 is shown in NQ
futures terms; EUR/USD and USD/JPY are spot feeds already.
"""
import os, json, math
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import yfinance as yf

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA_DIR = os.path.join(ROOT, "data")
TABLES = os.path.join(ROOT, "calibration", "band_tables.json")
NY, UK = ZoneInfo("America/New_York"), ZoneInfo("Europe/London")
FEEDS = {"Gold": "GC=F", "NAS100": "NQ=F", "SPX500": "ES=F", "US2000": "RTY=F", "EURUSD": "EURUSD=X", "USDJPY": "JPY=X"}
NAMES = {"Gold": "Gold", "NAS100": "NAS100", "SPX500": "S&P 500", "US2000": "Russell 2000", "EURUSD": "EUR/USD", "USDJPY": "USD/JPY"}
DECIMALS = {"Gold": 2, "NAS100": 1, "SPX500": 1, "US2000": 1, "EURUSD": 5, "USDJPY": 3}
RESCALE_TO_SPOT = {"Gold"}
MIN_N = 30          # below this many historical cases a figure is not shown
Z = 1.96


def load(name, base=DATA_DIR):
    p = os.path.join(base, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def wilson(cell):
    """[n, hits] -> (p, lo, hi, n) in percent, or None if too few cases."""
    n, k = cell
    if n < MIN_N:
        return None
    p = k / n
    den = 1 + Z * Z / n
    mid = (p + Z * Z / (2 * n)) / den
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / den
    return {"p": round(100 * p), "lo": round(100 * max(0, mid - half)), "hi": round(100 * min(1, mid + half)), "n": n}


def bucket(p, edges):
    return sum(1 for e in edges if p >= e)


def session_start(now_ny):
    start = now_ny.replace(hour=17, minute=0, second=0, microsecond=0)
    return start if now_ny >= start else start - timedelta(days=1)


def slot_label(ts_uk):
    """London label of the last completed 30-minute slot at time ts."""
    m = (ts_uk.minute // 30) * 30
    return ts_uk.replace(minute=m, second=0, microsecond=0).strftime("%H:%M")


def compare(cond, base):
    if not cond or not base:
        return "unknown"
    if cond["lo"] > base["p"]:
        return "above"
    if cond["hi"] < base["p"]:
        return "below"
    return "in line"


def read_instrument(instr, ticker, vr, spot, cal, edges, ext_p):
    bars = yf.download(ticker, period="5d", interval="5m", progress=False, multi_level_index=False)
    if bars.empty:
        return {"error": f"no intraday data from {ticker}"}
    idx = bars.index.tz_convert(NY) if bars.index.tz is not None else bars.index.tz_localize("UTC").tz_convert(NY)
    bars.index = idx
    last_ts = idx[-1]
    start = session_start(last_ts)
    day = bars[bars.index >= start]
    if len(day) < 3:
        return {"error": "current session has barely started"}

    # Rescale futures quotes onto the dashboard's spot price
    # Only where the spot quote is live at the same moment (gold-api). The
    # NDX cash index is stale outside US hours, so NAS100 stays in NQ terms.
    ratio = spot / float(day["Close"].iloc[-1]) if (spot and instr in RESCALE_TO_SPOT) else 1.0
    o = float(day["Open"].iloc[0]) * ratio
    px = float(day["Close"].iloc[-1]) * ratio
    hi, lo = float(day["High"].max()) * ratio, float(day["Low"].min()) * ratio

    b = {k: vr.get(k) for k in ("up_median", "up_p75", "down_median", "down_p75")}
    if any(v is None for v in b.values()):
        return {"error": "no vol bands"}
    bands = {"up_med": o * (1 + b["up_median"] / 100), "up_p75": o * (1 + b["up_p75"] / 100),
             "dn_med": o * (1 - b["down_median"] / 100), "dn_p75": o * (1 - b["down_p75"] / 100)}

    def position(price, side, band):
        level = bands[f"{side}_{band}"]
        return (price - o) / (level - o)

    now_uk = last_ts.astimezone(UK)
    label = slot_label(now_uk)
    tables = cal["tables"]

    # 10:00 London checkpoint
    chk_time = datetime.combine(now_uk.date(), datetime.min.time(), tzinfo=UK).replace(hour=10)
    checkpoint = {"available": False}
    if chk_time.astimezone(NY) > start and last_ts >= chk_time:
        at = day[day.index <= chk_time]
        if len(at):
            cp = float(at["Close"].iloc[-1]) * ratio
            pu, pd_ = position(cp, "up", "med"), position(cp, "dn", "med")
            ext = "up" if pu >= ext_p and pu > pd_ else ("dn" if pd_ >= ext_p and pd_ > pu else None)
            checkpoint = {"available": True, "price": cp, "p_up": round(pu, 2), "p_dn": round(pd_, 2), "extended": ext}

    sides = {}
    for side in ("up", "dn"):
        run = hi if side == "up" else lo
        reached_med = (run >= bands["up_med"]) if side == "up" else (run <= bands["dn_med"])
        reached_p75 = (run >= bands["up_p75"]) if side == "up" else (run <= bands["dn_p75"])
        band = None if reached_p75 else ("p75" if reached_med else "med")
        t = tables[side].get(label)
        entry = {"next_band": band, "reached_med": reached_med, "reached_p75": reached_p75}
        if band and t:
            p = position(px, side, band)
            bk = bucket(p, edges)
            entry.update({
                "level": bands[f"{side}_{band}"], "position": round(p, 2),
                "reach": wilson(t["reach"][band][bk]),
                "base": wilson(t["reach_base"][band]),
            })
            if checkpoint.get("extended") == side:
                entry["reach_ext"] = wilson(t["reach_ext"][band][bk])
            entry["vs_normal"] = compare(entry["reach"], entry["base"])
        if t:
            entry["extreme_in"] = wilson(t["extreme_in"][bucket(position(px, side, "med"), edges)])
        sides[side] = entry

    return {"session_start": start.isoformat(), "as_of": now_uk.isoformat(timespec="minutes"), "slot": label,
            "open": o, "price": px, "high": hi, "low": lo, "bands": bands, "feed": ticker,
            "checkpoint": checkpoint, "sides": sides, "verdict": verdict(instr, checkpoint, sides, now_uk, bands, px, o),
            "projection": projection(cal, label, o, px, hi, lo, b)}


def projection(cal, label, o, px, hi, lo, b):
    """Projected range to the session close (17:00 New York), from how
    similar days moved from this time on. A range, not a direction: the
    middle of the close range is normally within a whisker of the price now.
    Distances are scaled by today's typical move (mean of the median up and
    down bands), so they adapt to the current volatility."""
    p = cal.get("projection", {}).get(label)
    if not p:
        return None
    m = (b["up_median"] + b["down_median"]) / 2 / 100 * o
    q = dict(zip((10, 25, 50, 75, 90), zip(p["mv_close"], p["mv_high"], p["mv_low"])))
    return {
        "n": p["n"],
        "close": {str(k): px + v[0] * m for k, v in q.items()},
        "high": {str(k): hi + v[1] * m for k, v in q.items()},   # session high: the high so far, plus any further stretch
        "low": {str(k): lo - v[2] * m for k, v in q.items()},
    }


def verdict(instr, cp, sides, now_uk, bands, px, o):
    """Plain-English read. Leads with what history says happens next, then
    the band odds against a normal day. The status only describes the
    morning; it is not a forecast."""
    arrow = {"up": "↑", "dn": "↓"}
    word = {"up": "upper", "dn": "lower"}
    extreme = {"up": "high", "dn": "low"}
    name = NAMES.get(instr, instr)
    focus = cp.get("extended") or max(("up", "dn"), key=lambda s: sides[s].get("position") or -9)
    s = sides[focus]
    if not cp.get("available"):
        status = "BEFORE 10:00 CHECKPOINT"
        head = "Before the 10:00 London checkpoint — no morning read yet."
    elif cp.get("extended"):
        held = (s.get("position") or 0) >= 0.5 or s.get("next_band") is None
        status = f"STRETCHED {arrow[focus]} AT 10:00" if held else f"10:00 MOVE {arrow[focus]} PULLED BACK"
        head = (f"{name} was stretched {arrow[focus]} at 10:00 London and is still near there." if held
                else f"{name} was stretched {arrow[focus]} at 10:00 London and has since pulled back. "
                     f"That describes the morning, not a forecast.")
    else:
        status = "NO 10:00 STRETCH"
        head = f"No stretch at 10:00 London — a normal-day read for {name}."

    parts = []
    xin = s.get("extreme_in")
    if xin:
        # extreme_in is the share of similar days that made NO further high
        # (or low); say it the other way round, as the share that did.
        parts.append(f"On {100 - xin['p']}% [{100 - xin['hi']}–{100 - xin['lo']}] of similar days "
                     f"{name} made a new {extreme[focus]} later in the session.")
    if s.get("next_band") is None:
        parts.append(f"It is already through the {word[focus]} 75th band today, so the bands give no further target on that side.")
    elif s.get("reach") and s.get("base"):
        r, b = s["reach"], s["base"]
        band = "median" if s["next_band"] == "med" else "75th"
        rel = {"above": "better than", "below": "worse than", "in line": "about the same as",
               "unknown": "compared with"}[s["vs_normal"]]
        parts.append(f"Reaching the {word[focus]} {band} band ({s['level']:,.{DECIMALS[instr]}f}): "
                     f"{r['p']}% [{r['lo']}–{r['hi']}], {rel} a normal day at this time ({b['p']}%).")
        if cp.get("extended") and s["vs_normal"] == "in line":
            parts.append("No edge from the morning move.")
    else:
        parts.append("Not enough history for this position and time.")
    return {"status": status, "headline": head, "text": " ".join(parts), "side": focus}

def run():
    cal = load("band_tables.json", os.path.join(ROOT, "calibration"))
    if not cal:
        print("No calibration/band_tables.json — skipping Band Read")
        return False
    edges = cal["edges"]
    vr = load("vol_range.json").get("instruments", {})
    ome = load("ome_data.json").get("instruments", {})

    out = {}
    for instr, ticker in FEEDS.items():
        try:
            spot = (ome.get(instr) or {}).get("underlying_price")
            res = read_instrument(instr, ticker, vr.get(instr, {}), spot, cal["instruments"][instr], edges, cal.get("extended_p", 0.75))
        except Exception as e:
            res = {"error": str(e)}
        if "error" not in res:
            res["history"] = {k: cal["instruments"][instr][k] for k in ("sessions", "first", "last")}
        out[instr] = res
        print(f"  {instr}: " + (res.get("error") or f"{res['verdict']['status']} — {res['verdict']['text']}"))

    with open(os.path.join(DATA_DIR, "band_read.json"), "w") as f:
        json.dump({"generated": datetime.now(UK).isoformat(timespec="minutes"), "tables_built": cal.get("built"),
                   "instruments": out}, f, indent=2)
    return all("error" not in v for v in out.values())


if __name__ == "__main__":
    run()
