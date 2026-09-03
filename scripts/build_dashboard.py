"""
Generate a full-analysis dashboard with conviction, narrative, news, correlations.
"""
import os, json
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..")
INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]
DASH = "\u2014"

CORRELATIONS = {
    "Gold":    {"moves_with": {"Silver": 0.87, "Platinum": 0.76, "EUR/USD": 0.61},
                "hedges":     {"USD/ZAR": -0.50, "USD/CHF": -0.50, "USD/JPY": -0.45},
                "driven_by":  "US dollar, rates, risk (VIX)"},
    "NAS100":  {"moves_with": {"S&P 500": 0.95, "Tech": 0.92, "USD/JPY": 0.55},
                "hedges":     {"Gold": -0.30, "USD/CHF": -0.25, "VIX": -0.70},
                "driven_by":  "Tech earnings, rates, USD"},
    "EURUSD":  {"moves_with": {"GBP/USD": 0.85, "Gold": 0.61, "AUD/USD": 0.78},
                "hedges":     {"USD/CHF": -0.90, "USD/JPY": -0.65, "DXY": -0.95},
                "driven_by":  "ECB/Fed differential, risk sentiment, USD"},
}

# Populated from events.json at build time
ECON_EVENTS = []

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def color_for(val):
    if val is None: return "var(--muted)"
    return "var(--long)" if val > 0 else ("var(--short)" if val < 0 else "var(--muted)")

def arrow_for(val):
    if val is None: return "\u2192"
    if val > 0: return "\u25b2"
    if val < 0: return "\u25bc"
    return "\u2192"

def fmt(v):
    if v is None or v == DASH: return DASH
    try:
        if isinstance(v, float):
            if v < 10: return f"{v:.4f}"
            return f"{v:,.1f}" if v == int(v) else f"{v:,.2f}"
        if isinstance(v, int): return f"{v:,}"
        return str(v)
    except: return str(v)

def conviction_label(score, max_val=12):
    if score is None: return "N/A", 0
    raw = abs(score)
    if max_val <= 0: return "N/A", 0
    pct = min(raw / max_val, 1.0)
    stars = round(pct * 10)
    if pct < 0.3: return "Low conviction", stars
    if pct < 0.6: return "Medium conviction", stars
    return "High conviction", stars

def range_pct(sp, cw, pw):
    """How far price is from nearest wall as % of wall spread."""
    try:
        sp_f = float(sp)
        hi = float(cw) if cw not in (None, DASH) else None
        lo = float(pw) if pw not in (None, DASH) else None
    except: return None
    if hi is None or lo is None or hi == lo: return None
    pct = (hi - sp_f) / (hi - lo) * 100
    return max(0, min(100, pct))

def generate_narrative(instr, d, ome_raw, macro_score, cot=None):
    ts = d.get("total_score")
    sig = d.get("signal", "N/A")
    ps = d.get("positioning_score", 0)
    pcr = ome_raw.get("put_call_ratio")
    mp = ome_raw.get("max_pain")
    cw = ome_raw.get("call_wall")
    pw = ome_raw.get("put_wall")
    mg = ome_raw.get("magnet_strike")
    sp = ome_raw.get("underlying_price")

    paragraphs = []

    # First paragraph: where price is pinned
    p1 = f"{instr} at {fmt(sp)} is pinned between two key options reference points"
    if cw not in (None, DASH) and pw not in (None, DASH):
        p1 += f" \u2014 the call wall at {fmt(cw)} and put wall at {fmt(pw)}"
    p1 += ". "
    p1 += f"The PCR of {pcr:.2f}" if isinstance(pcr, (int, float)) else ""
    if isinstance(pcr, (int, float)) and pcr > 1.3:
        p1 += " signals heavy put positioning, with options traders loading up on downside protection."
    elif isinstance(pcr, (int, float)) and pcr < 0.7:
        p1 += " shows call dominance, traders positioning for upside."
    elif isinstance(pcr, (int, float)):
        p1 += " is balanced."
    paragraphs.append(p1)

    # Second paragraph: max pain dynamics
    p2 = ""
    if mp is not None and sp is not None:
        diff_pct = (mp - sp) / sp * 100
        if abs(diff_pct) < 0.5:
            p2 = f"Max pain at {fmt(mp)} sits very close to the current price \u2014 minimal gravitational pull toward max pain."
        elif diff_pct < 0:
            p2 = f"Max pain at {fmt(mp)} is {abs(diff_pct):.1f}% below the current price. Price is stretched above max pain and may drift lower toward it."
        else:
            p2 = f"Max pain at {fmt(mp)} is {diff_pct:.1f}% above the current price. Price is below max pain and may drift higher toward it."

    if cw is not None and pw is not None:
        if cw > pw:
            p2 += f" The call wall at {fmt(cw)} towers above the put wall at {fmt(pw)} \u2014 resistance overhead is the dominant structural level."
        elif cw < pw:
            p2 += f" The put wall at {fmt(pw)} dominates below the call wall at {fmt(cw)} \u2014 support has a stronger footing than resistance."
        else:
            p2 += f" Both put and call walls converge at {fmt(cw)} \u2014 a major battleground."
    if p2:
        paragraphs.append(p2)

    # Third paragraph: magnet + macro context
    p3 = ""
    if mg is not None:
        p3 += f"The magnet at {fmt(mg)} holds the highest total OI concentration, acting as a price attractor. "
    p3 += f"Macro contributes {macro_score}/5 to the score. "
    cot_score = d.get("cot_score", 0)
    if cot is not None and "error" not in cot:
        p3 += f"COT: specs {cot.get('noncomm_net_pct')}% net, commercials {cot.get('comm_net_pct')}% net (score {cot_score:+d}). "
    p3 += f"Net score: {ts} ({sig})."
    paragraphs.append(p3)

    return paragraphs

def generate_bottom_line(instr, d, ome_raw=None):
    """One-sentence, plain-English takeaway. This is what gets shown up front
    (dashboard) or as the whole message (Telegram) — the multi-paragraph
    narrative is detail for people who want to dig, not the headline read.
    Explicitly checks whether Positioning/Macro/COT AGREE, not just whether
    the total score is high, since a high total can hide real disagreement
    between components (e.g. bullish options positioning but bearish COT)."""
    ts = d.get("total_score")
    sig = d.get("signal", "N/A")
    if ts is None:
        return f"{instr}: no data available."

    components = {
        "Positioning": d.get("positioning_score", 0),
        "Macro": d.get("macro_score", 0),
        "COT": d.get("cot_score", 0),
    }
    nonzero = {k: v for k, v in components.items() if v}

    if len(nonzero) >= 2 and (all(v > 0 for v in nonzero.values()) or all(v < 0 for v in nonzero.values())):
        agree_str = ", ".join(nonzero.keys())
        return f"{sig} (net {ts:+d}) — {agree_str} all agree. Higher-conviction setup."

    if nonzero:
        pos_side = [k for k, v in nonzero.items() if v > 0]
        neg_side = [k for k, v in nonzero.items() if v < 0]
        pos_str = "/".join(pos_side) if pos_side else "nothing"
        neg_str = "/".join(neg_side) if neg_side else "nothing"
        return f"{sig} lean (net {ts:+d}), but mixed — {pos_str} bullish vs {neg_str} bearish. Lower conviction, size accordingly."

    return f"{sig} (net {ts:+d}) — components are flat or missing data. Low conviction."

def generate_forecast_trade_table(ome_raw, vr):
    """The dashboard equivalent of the Pine script's 'Trade Idea' table —
    both a long path (toward the asymmetric UP excursion percentiles) and a
    short path (toward the asymmetric DOWN excursion percentiles) at once,
    rather than picking one direction from the signal. Same underlying math
    as generate_forecast_trade_idea() but shown as a 4-row table so both
    sides are visible together, matching what's now on the TradingView
    indicator. Uses the genuinely asymmetric up_median/up_p75/down_median/
    down_p75 fields (added to calc_vol_range.py alongside this feature) —
    NOT the symmetric high_low_range_median, which would incorrectly show
    identical distances for both directions.
    Returns None if there isn't enough data to build it."""
    sp = ome_raw.get("underlying_price")
    up_med = vr.get("up_median")
    up_75 = vr.get("up_p75")
    down_med = vr.get("down_median")
    down_75 = vr.get("down_p75")
    atr_pct = vr.get("atr14_pct")

    if not sp or up_med is None or down_med is None or atr_pct is None:
        return None

    stop_dist = sp * (atr_pct / 100) * 1.5
    long_sl = sp - stop_dist
    short_sl = sp + stop_dist

    rows = [("Long \u2192 Med", sp * (1 + up_med / 100), long_sl, "var(--long)")]
    if up_75 is not None:
        rows.append(("Long \u2192 75p", sp * (1 + up_75 / 100), long_sl, "var(--long)"))
    rows.append(("Short \u2192 Med", sp * (1 - down_med / 100), short_sl, "var(--short)"))
    if down_75 is not None:
        rows.append(("Short \u2192 75p", sp * (1 - down_75 / 100), short_sl, "var(--short)"))

    return {"stop_dist": stop_dist, "rows": rows}

def generate_forecast_trade_idea(instr, d, ome_raw, vr):
    """A second, independent trade idea derived from the Vol & Range
    Forecast tool (calc_vol_range.py's median/75th percentile daily move
    projections) rather than options positioning — a genuinely different
    methodology, not just a rephrasing of generate_trade_idea(). Stop-loss
    is sized at 1.5x ATR(14), not a fixed percentage, so it actually adapts
    to how volatile the instrument currently is.

    Uses atr14_pct (ATR expressed as % of price) rather than the raw
    ATR14 dollar figure to size the stop, since ATR is computed from
    futures OHLC (calc_vol_range.py's TICKERS) while `sp` here is the
    instrument's spot price — day-to-day $ range is nearly identical
    between spot and futures (basis is roughly constant), but converting
    through % sidesteps any scale mismatch entirely rather than relying on
    that being true.
    """
    sig = d.get("signal", "N/A")
    sp = ome_raw.get("underlying_price")
    hl_med = vr.get("high_low_range_median")
    hl_75 = vr.get("high_low_range_p75")
    atr_pct = vr.get("atr14_pct")

    if not sp or hl_med is None or atr_pct is None:
        return None  # not enough forecast data to build this idea

    stop_dist = sp * (atr_pct / 100) * 1.5

    if sig == "LONG":
        target_med = sp * (1 + hl_med / 100)
        stop = sp - stop_dist
        line = f"Long from {fmt(sp)}, targeting {fmt(target_med)} (median forecast move, {hl_med:.2f}%)"
        if hl_75 is not None:
            target_stretch = sp * (1 + hl_75 / 100)
            line += f", stretch target {fmt(target_stretch)} (75th pct, {hl_75:.2f}%)"
        line += f", stop {fmt(stop)} (1.5x ATR14 = {stop_dist:.2f})."
        return line
    elif sig == "SHORT":
        target_med = sp * (1 - hl_med / 100)
        stop = sp + stop_dist
        line = f"Short from {fmt(sp)}, targeting {fmt(target_med)} (median forecast move, {hl_med:.2f}%)"
        if hl_75 is not None:
            target_stretch = sp * (1 - hl_75 / 100)
            line += f", stretch target {fmt(target_stretch)} (75th pct, {hl_75:.2f}%)"
        line += f", stop {fmt(stop)} (1.5x ATR14 = {stop_dist:.2f})."
        return line
    else:
        upper = sp * (1 + hl_med / 100)
        lower = sp * (1 - hl_med / 100)
        return f"No directional edge — forecast puts the typical range between {fmt(lower)} and {fmt(upper)} ({hl_med:.2f}% median move each way). Range-trade only, stop {stop_dist:.2f} (1.5x ATR14) beyond either edge."

def generate_trade_idea(instr, d, ome_raw):
    """Generate a specific trade idea based on positioning."""
    ts = d.get("total_score")
    sig = d.get("signal", "N/A")
    pcr = ome_raw.get("put_call_ratio")
    mp = ome_raw.get("max_pain")
    cw = ome_raw.get("call_wall")
    pw = ome_raw.get("put_wall")
    sp = ome_raw.get("underlying_price")

    # True range midpoint, used as a fallback target whenever max_pain would
    # collide with the entry level (e.g. max_pain == put_wall == call_wall),
    # which previously produced trade ideas with an entry equal to its own target.
    midpoint = (cw + pw) / 2 if (cw and pw) else None

    if sig == "LONG":
        if cw and pw and cw > pw:
            target = mp if (mp and midpoint and abs(mp - pw) > abs(midpoint - pw) * 0.05) else midpoint
            return f"Lean long at {fmt(pw)} put-wall support, target {fmt(target)} {'max pain' if target == mp else 'range midpoint'}, stop below {fmt(pw - (pw * 0.01 if pw > 100 else 0.001))}; fade any rip to {fmt(cw)} call wall."
        return f"Bullish bias: look for dips toward support, target a drift higher. Stop below recent range lows."
    elif sig == "SHORT":
        if cw and pw and cw > pw:
            target = mp if (mp and midpoint and abs(mp - cw) > abs(midpoint - cw) * 0.05) else midpoint
            return f"Lean short at {fmt(cw)} call-wall resistance, target {fmt(target)} {'max pain' if target == mp else 'range midpoint'}, stop above {fmt(cw + (cw * 0.01 if cw > 100 else 0.001))}; fade any dip to {fmt(pw)} put wall."
        return f"Bearish bias: look for rallies toward resistance, target a drift lower. Stop above recent range highs."
    else:
        if cw and pw:
            return f"Neutral: fade pushes toward {fmt(cw)} (sell) and treat {fmt(pw)} as a floor (buy). Low conviction \u2014 small size only."
        return f"Neutral bias \u2014 no strong directional edge. Wait for a clear break of the range."

def staleness_badge(generated_str, max_age_days=1.5):
    """gold-forecast.html is a static file with no regeneration step in the
    pipeline (nothing in scripts/ or the GH Actions workflow writes to it),
    so it can silently go stale while the rest of the dashboard refreshes
    2x/day. Surface its true age instead of presenting it as live."""
    if not generated_str:
        return "\u26a0 unknown age", "var(--red)"
    try:
        gen_dt = datetime.fromisoformat(generated_str)
        age_days = (datetime.now() - gen_dt).total_seconds() / 86400
        if age_days <= max_age_days:
            return f"\u2713 live ({age_days:.1f}d old)", "var(--long)"
        return f"\u26a0 STALE ({age_days:.0f}d old) \u2014 not auto-refreshed", "var(--short)"
    except (ValueError, TypeError):
        return "\u26a0 unknown age", "var(--red)"

def load_gold_forecast():
    """Prefer gold-forecast.html's richer HAR-IV output, but that file is a
    static artifact nothing in the pipeline regenerates (confirmed: no script
    or workflow step writes to it), so it can silently freeze indefinitely.
    Fall back to vol_range.json — which calc_vol_range.py DOES regenerate
    every run — whenever the HAR-IV file is missing, unparseable, or stale."""
    path = os.path.join(OUTPUT_DIR, "gold-forecast.html")
    result = {}
    if os.path.exists(path):
        import re
        with open(path, encoding="utf-8") as f:
            content = f.read()
        m = re.search(r'const DATA\s*=\s*({.*?});', content, re.DOTALL)
        if m:
            try:
                data = json.loads(m.group(1))
                base = data.get("base", data)
                result = {
                    "daily_vol": base.get("forecast_daily_pct"),
                    "annual_vol": base.get("forecast_annual_pct"),
                    "hl_median": base.get("hl", {}).get("median"),
                    "oc_median": base.get("oc", {}).get("median"),
                    "generated": data.get("generated", ""),
                    "source": "har-iv",
                }
            except json.JSONDecodeError:
                pass

    is_stale = True
    if result.get("generated"):
        try:
            age_days = (datetime.now() - datetime.fromisoformat(result["generated"])).total_seconds() / 86400
            is_stale = age_days > 1.5
        except (ValueError, TypeError):
            pass

    if not result or is_stale:
        vr = load_json(os.path.join(DATA_DIR, "vol_range.json"))
        gold_vr = vr.get("instruments", {}).get("Gold")
        if gold_vr and gold_vr.get("volatility_annualized") is not None:
            result = {
                "daily_vol": gold_vr.get("volatility_annualized", 0) / (252 ** 0.5) if gold_vr.get("volatility_annualized") is not None else None,
                "annual_vol": gold_vr.get("volatility_annualized"),
                "hl_median": gold_vr.get("high_low_range_median"),
                "oc_median": gold_vr.get("open_close_median"),
                "generated": vr.get("date", "") + "T00:00:00" if vr.get("date") else "",
                "source": "vol_range",
            }
    return result

def run():
    scores = load_json(os.path.join(DATA_DIR, "scores.json"))
    fred = load_json(os.path.join(DATA_DIR, "fred_macro.json")).get("series", {})
    ome = load_json(os.path.join(DATA_DIR, "ome_data.json")).get("instruments", {})
    cot_data = load_json(os.path.join(DATA_DIR, "cot_data.json")).get("instruments", {})
    sentiment = load_json(os.path.join(DATA_DIR, "sentiment.json")).get("instruments", {})
    oanda = load_json(os.path.join(DATA_DIR, "oanda_prices.json")).get("instruments", {})
    geopolitical = load_json(os.path.join(DATA_DIR, "geopolitical.json"))

    overall = scores.get("overall", {})
    macro = scores.get("macro", {})
    instruments = scores.get("instruments", {})

    gen_time = scores.get("generated", datetime.now().isoformat())
    gen_dt = datetime.fromisoformat(gen_time)
    gen_display = gen_dt.strftime("%d/%m/%Y, %H:%M")

    overall_signal = overall.get("signal", "NEUTRAL")
    overall_score = overall.get("avg_score")
    overall_color = color_for(overall_score)
    overall_arrow = arrow_for(overall_score)

    macro_score = macro.get("score", 0)

    # Options OI inline sections for all instruments
    all_oi_data = {}
    oi_section = ""
    for instr in INSTRUMENTS:
        ome_i = ome.get(instr, {})
        strikes_i = ome_i.get("strikes", [])
        if strikes_i:
            tag = instr.lower().replace(" ", "")
            all_oi_data[instr] = {"strikes": strikes_i, "call_oi": ome_i.get("call_oi", []), "put_oi": ome_i.get("put_oi", []),
                                  "total_oi_used": ome_i.get("total_oi_used"), "put_call_ratio": ome_i.get("put_call_ratio"),
                                  "max_pain": ome_i.get("max_pain"), "call_wall": ome_i.get("call_wall"), "put_wall": ome_i.get("put_wall"),
                                  "magnet_strike": ome_i.get("magnet_strike"), "underlying_price": ome_i.get("underlying_price"),
                                  "expiry": ome_i.get("expiry",""), "proxy_for": ome_i.get("proxy_for","")}
            oi_section += f"""
        <div class="analysis-section" id="{tag}-oi">
          <div class="analysis-header">
            <div class="analysis-title-row">
              <h2 class="analysis-name">{instr} Options OI</h2>
              <div class="analysis-badge" style="background:var(--accent)15;color:var(--accent);border:1px solid var(--accent)40">{ome_i.get("proxy_for",instr)}</div>
              <button class="analysis-close" onclick="this.closest('.analysis-section').classList.toggle('collapsed')" title="Toggle">\u2715</button>
            </div>
            <div class="analysis-sub">
              <span class="analysis-ai">Expiry {ome_i.get("expiry","")} &middot; {len(strikes_i)} strikes</span>
            </div>
          </div>
          <div class="analysis-body">
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px">
              <div class="extra-card"><div class="chart-wrap-oi"><canvas id="{tag}OiBarChart"></canvas></div></div>
              <div class="extra-card"><div class="chart-wrap-oi"><canvas id="{tag}OiNetChart"></canvas></div></div>
            </div>
            <div class="extra-card" style="margin-bottom:12px"><div class="chart-wrap-oi" style="height:280px"><canvas id="{tag}OiPainChart"></canvas></div></div>
            <div class="extra-card"><div class="chart-wrap-oi"><canvas id="{tag}OiPcrChart"></canvas></div></div>
          </div>
        </div>"""

    # Gold Vol Forecast Detail (HAR-IV interactive gauge) removed — it depended
    # entirely on gold-forecast.html's embedded DATA blob, which is produced by
    # a separate, more sophisticated standalone tool (HAR-IV model + intraday
    # revision grid matched against historical comparable days + ATM IV/GVZ
    # comparison) that lives outside this repo and has no generator script
    # here to wire into the pipeline. Rather than keep shipping a panel that
    # can only ever show a frozen snapshot, it's gone. The "Gold Next-Day Vol
    # Forecast" summary card above still works — it now sources from the live,
    # daily-regenerated vol_range.json instead.

    # Geopolitical Risk card
    geo_section = ""
    if geopolitical.get("articles"):
        arts = geopolitical["articles"][:8]
        ir = geopolitical.get("instrument_risk", {})
        gs = geopolitical.get("global_risk_score", 0)
        geo_color = "var(--red)" if gs >= 5 else ("var(--amber)" if gs >= 3 else "var(--green)")
        geo_rows = ""
        for a in arts:
            tags = "".join(f'<span class="geo-art-tag">{t}</span>' for t in a.get("tags", []))
            geo_rows += f'<div class="geo-art"><a class="geo-art-title" href="{a["url"]}" target="_blank" rel="noopener">{a["title"]}</a> <span class="geo-art-domain">{a.get("domain","")}</span>{tags}</div>'
        instr_rows = ""
        for instr in INSTRUMENTS:
            v = ir.get(instr, {})
            lvl = v.get("risk_level", "LOW")
            lvl_color = {"HIGH": "var(--red)", "MODERATE": "var(--amber)", "LOW": "var(--green)"}.get(lvl, "var(--muted)")
            instr_rows += f'<div class="geo-instr"><span class="geo-instr-name">{instr}</span><span class="geo-instr-level" style="background:{lvl_color}15;color:{lvl_color};border:1px solid {lvl_color}40">{lvl}</span></div>'
        geo_section = f"""
        <div class="geo-card">
          <div class="geo-header">
            <span class="geo-label">Geopolitical Risk</span>
            <span class="geo-score" style="color:{geo_color}">{gs}/10</span>
          </div>
          <div class="geo-body">{instr_rows}</div>
          <div class="geo-articles">{geo_rows}</div>
        </div>"""

    # Gold Forecast card
    gf = load_gold_forecast()
    gold_forecast_section = ""
    if gf.get("daily_vol") is not None:
        stale_txt, stale_color = staleness_badge(gf.get("generated"))
        model_label = "HAR-IV model" if gf.get("source") == "har-iv" else "20-day realized vol (fallback — HAR-IV file is stale)"
        gold_forecast_section = f"""
        <div class="gold-forecast-card">
          <div class="gold-fc-header">
            <span class="gold-fc-label">Gold Next-Day Vol Forecast</span>
            <span class="gold-fc-source">{model_label}</span>
            <span class="gold-fc-source" style="color:{stale_color}">{stale_txt}</span>
          </div>
          <div class="gold-fc-body">
            <div class="gold-fc-metric">
              <span class="gold-fc-k">Daily Vol</span>
              <span class="gold-fc-v">{gf["daily_vol"]:.3f}%</span>
            </div>
            <div class="gold-fc-metric">
              <span class="gold-fc-k">HL Range (median)</span>
              <span class="gold-fc-v">{gf["hl_median"]:.2f}%</span>
            </div>
            <div class="gold-fc-metric">
              <span class="gold-fc-k">OC Move (median)</span>
              <span class="gold-fc-v">{gf["oc_median"]:.2f}%</span>
            </div>
            <div class="gold-fc-metric">
              <span class="gold-fc-k">Annualised Vol</span>
              <span class="gold-fc-v">{gf["annual_vol"]:.1f}%</span>
            </div>
          </div>
          <div class="gold-fc-footer">
            <span class="gold-fc-note">Inline sections below &darr;</span>
            <span class="gold-fc-date">{gf.get("generated","")}</span>
          </div>
        </div>"""

    # Vol & Range Forecast (check data/ then screenshots/)
    vol_range = load_json(os.path.join(DATA_DIR, "vol_range.json"))
    if not vol_range:
        vol_range = load_json(os.path.join(SCREENSHOT_DIR, "vol_range.json"))
    vol_date = vol_range.get("date", "")
    vol_session = vol_range.get("session", "")
    vol_rows = ""
    for instr in INSTRUMENTS:
        v = vol_range.get("instruments", {}).get(instr, {})
        if not v:
            continue
        vol = v.get("volatility_annualized", DASH)
        hl_m = v.get("high_low_range_median", DASH)
        hl_p = v.get("high_low_range_p75", DASH)
        oc_m = v.get("open_close_median", DASH)
        oc_p = v.get("open_close_p75", DASH)
        vol_rows += f"""<div class="vol-block">
          <div class="vol-block-head">&mdash;&mdash;&mdash;&mdash; {instr} &mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;&mdash;</div>
          <div class="vol-block-line">Volatility (annualized) : <strong>{vol}%</strong></div>
          <div class="vol-block-line">High to Low range       : <strong>{hl_m}%</strong> median &middot; <strong>{hl_p}%</strong> 75th Percentile</div>
          <div class="vol-block-line">Open to Close move      : <strong>{oc_m}%</strong> median &middot; <strong>{oc_p}%</strong> 75th Percentile</div>
        </div>"""

    vol_section = ""
    if vol_rows:
        vol_section = f"""
        <div class="vol-card">
          <div class="vol-header">
            <span class="vol-label">Vol &amp; Range Forecast</span>
            <span class="vol-session">For session: {vol_session}</span>
          </div>
          <div class="vol-body">{vol_rows}</div>
        </div>"""

    # Economic Events
    events_data = load_json(os.path.join(DATA_DIR, "events.json")).get("events", [])

    # Currencies actually relevant to each instrument — previously ECON_EVENTS was
    # one global top-4 list (no currency filter) reused verbatim under every
    # instrument's "News for This Pair" section, so Gold/NAS100/EURUSD all showed
    # identical events (e.g. RBNZ, CHF CPI) regardless of relevance.
    INSTRUMENT_CURRENCIES = {
        "Gold":   {"USD"},
        "NAS100": {"USD"},
        "EURUSD": {"USD", "EUR"},
    }

    def build_econ_list(events_data, currencies=None, limit=4):
        econ_list = []
        now = datetime.now()
        for ev in events_data:
            imp = ev.get("impact", "")
            if imp not in ("High", "Medium"):
                continue
            if currencies is not None and ev.get("country") not in currencies:
                continue
            try:
                ev_dt = datetime.fromisoformat(ev["date"])
                if ev_dt < now:
                    continue
                ev_time = ev_dt.strftime("%H:%M")
                ev_day = "Today" if ev_dt.strftime("%Y-%m-%d") == now.strftime("%Y-%m-%d") else ev_dt.strftime("%a")
            except:
                ev_time = ev["date"][11:16] if len(ev["date"]) > 16 else ev["date"]
                ev_day = ""
            econ_list.append((ev["title"], ev_time, ev.get("forecast", ""), ev_day))
        return econ_list[:limit]

    ECON_EVENTS = build_econ_list(events_data)  # unfiltered top-4, kept for any general use
    events_section = ""
    if events_data:
        event_rows = ""
        row_count = 0
        now_dt = datetime.now()
        today = now_dt.strftime("%Y-%m-%d")
        for ev in events_data:
            if row_count >= 30:
                break
            try:
                ev_dt = datetime.fromisoformat(ev["date"])
                if ev_dt < now_dt:
                    continue
                ev_time = ev_dt.strftime("%H:%M")
                ev_day = "Today" if ev_dt.strftime("%Y-%m-%d") == today else ev_dt.strftime("%a")
            except:
                ev_time = ev["date"][11:16] if len(ev["date"]) > 16 else ev["date"]
                ev_day = ""
            imp = ev.get("impact", "Low")
            if imp not in ("High", "Medium"):
                continue
            imp_cls = "imp-high" if imp == "High" else "imp-med"
            row_count += 1
            event_rows += f"""
          <tr class="{imp_cls}-row">
            <td class="ev-time">{ev_time}</td>
            <td class="ev-day">{ev_day}</td>
            <td class="ev-flag">{ev.get("country","")}</td>
            <td class="ev-title">{ev.get("title","")}</td>
            <td class="ev-impact"><span class="imp-badge {imp_cls}">{imp}</span></td>
            <td class="ev-fc">{ev.get("forecast","")}</td>
            <td class="ev-prev">{ev.get("previous","")}</td>
          </tr>"""
        events_section = f"""
        <div class="events-card">
          <div class="events-header">
            <span class="events-label">Economic Calendar</span>
            <span class="events-source">ForexFactory</span>
          </div>
          <table class="events-table">
            <thead>
              <tr>
                <th>Time</th>
                <th>Day</th>
                <th>Curr</th>
                <th>Event</th>
                <th>Impact</th>
                <th>Forecast</th>
                <th>Previous</th>
              </tr>
            </thead>
            <tbody>
              {event_rows}
            </tbody>
          </table>
          <div class="events-note">Upcoming events &bull; High impact highlighted</div>
        </div>"""

    # Snapshot scoreboard (pre-pass to collect instrument data)
    snapshot_rows = ""
    instr_sections = ""
    for instr in INSTRUMENTS:
        d = instruments.get(instr, {})
        ts = d.get("total_score")
        sig = d.get("signal", "N/A")
        sig_color = "var(--long)" if sig == "LONG" else ("var(--short)" if sig == "SHORT" else "var(--muted)")
        sent = sentiment.get(instr, {})
        sent_sig = sent.get("signal")
        sent_label = f"News: {sent_sig}" if sent_sig else ""
        sent_color = "var(--long)" if sent_sig == "BULLISH" else ("var(--short)" if sent_sig == "BEARISH" else "")
        oanda_instr = oanda.get(instr, {})
        oanda_price = oanda_instr.get("mid")
        oanda_note = f"Proxy quote ({oanda_instr.get('ticker', 'ETF')}): {oanda_price}" if oanda_price else ""
        arr = arrow_for(ts)
        # Use THIS instrument's own macro contribution (the one actually summed
        # into total_score), not the cross-instrument average — using the average
        # here previously made the displayed Positioning+COT+Macro not sum to the
        # displayed Total Score.
        instr_macro_score = d.get("macro_score", 0)
        ps = d.get("positioning_score", 0)
        ome_raw = d.get("ome_data", {})
        pcr = ome_raw.get("put_call_ratio")
        mp = ome_raw.get("max_pain")
        cw = ome_raw.get("call_wall")
        pw = ome_raw.get("put_wall")
        mg = ome_raw.get("magnet_strike")
        sp = ome_raw.get("underlying_price")
        tot = ome_raw.get("total_oi")

        conv_label, conv_stars = conviction_label(ts, 12)  # true max: pos(5)+macro(5)+cot(2)=12
        rng = range_pct(sp, cw, pw)
        rng_str = f"{rng:.0f}%" if rng is not None else DASH

        # High-probability confluence: all three sub-signals (positioning, macro,
        # COT) agreeing in direction is a stronger signal than a high total score
        # alone, since a high total can come from one extreme component while the
        # others disagree or sit neutral. Require at least 2 of the 3 components
        # to be non-zero and none of the non-zero ones to conflict in sign.
        _components = [ps, instr_macro_score, d.get("cot_score", 0)]
        _nonzero = [c for c in _components if c]
        is_confluence = len(_nonzero) >= 2 and (all(c > 0 for c in _nonzero) or all(c < 0 for c in _nonzero))
        hp_lightning = "\u26a1"
        hp_snap_tag = f'<div class="snap-hp-tag">{hp_lightning} HIGH PROB</div>' if is_confluence else ''
        hp_badge = f'<div class="analysis-badge" style="background:var(--gold)15;color:var(--gold);border:1px solid var(--gold)40">{hp_lightning} High-Probability Setup</div>' if is_confluence else ''

        # Compute dynamic fair value distance
        fair_str = DASH
        if cw not in (None, DASH) and pw not in (None, DASH) and sp not in (None, DASH):
            try:
                cwf = float(cw)
                pwf = float(pw)
                spf = float(sp)
                fair_mid = (cwf + pwf) / 2
                fair_pct = (spf - fair_mid) / fair_mid * 100
                if abs(fair_pct) < 2:
                    fair_str = "near fair value"
                elif fair_pct > 0:
                    fair_str = f"{fair_pct:+.1f}% above fair value"
                else:
                    fair_str = f"{fair_pct:+.1f}% below fair value"
            except (TypeError, ValueError):
                pass

        paragraphs = generate_narrative(instr, d, ome_raw, instr_macro_score, cot_data.get(instr, {}))
        bottom_line = generate_bottom_line(instr, d, ome_raw)
        trade_idea = generate_trade_idea(instr, d, ome_raw)
        forecast_trade_idea = generate_forecast_trade_idea(instr, d, ome_raw, vol_range.get("instruments", {}).get(instr, {}))
        forecast_table = generate_forecast_trade_table(ome_raw, vol_range.get("instruments", {}).get(instr, {}))
        forecast_table_html = ""
        if forecast_table:
            rows_html = "".join(
                f'<tr><td style="color:{color}">{label}</td>'
                f'<td>{fmt(tp)}</td>'
                f'<td>{fmt(sl)}</td></tr>'
                for label, tp, sl, color in forecast_table["rows"]
            )
            forecast_table_html = f'''<div class="an-block trade-idea forecast-idea">
                  <div class="an-label" style="color:var(--gold)">Trade Ideas (Vol/Range Forecast Table, 1.5x ATR14 = {forecast_table["stop_dist"]:.2f})</div>
                  <table class="forecast-idea-table">
                    <tr><th></th><th>Target</th><th>Stop</th></tr>
                    {rows_html}
                  </table>
                </div>'''
        stars_html = "\u2605" * conv_stars + "\u2606" * (10 - conv_stars)

        # Snapshot card
        score_bar_pct = min(abs(ts) / 12 * 100, 100) if ts is not None else 0  # true max score is 12, not 8
        bar_color = "var(--long)" if (ts or 0) > 0 else "var(--short)"
        snap_highlight_style = f"border:1.5px solid {sig_color};box-shadow:0 0 0 1px {sig_color}30" if is_confluence else ""
        snapshot_rows += f"""
        <div class="snap-card" style="{snap_highlight_style}" onclick="document.getElementById('{instr.lower()}').scrollIntoView({{behavior:'smooth'}})">
          {hp_snap_tag}
          <div class="snap-name">{instr}</div>
          <div class="snap-signal" style="color:{sig_color}">{arr} {sig}</div>
          <div class="snap-score">{ts if ts is not None else DASH}</div>
          <div class="snap-bar"><div class="snap-bar-fill" style="width:{score_bar_pct:.0f}%;background:{bar_color}"></div></div>
          <div class="snap-price">{fmt(sp) if sp else DASH}</div>
        </div>"""

        corr = CORRELATIONS.get(instr, {})

        news_rows = ""
        for ev in build_econ_list(events_data, INSTRUMENT_CURRENCIES.get(instr)):
            news_rows += f"""
            <div class="news-row"><span class="news-time">{ev[1]}</span><span class="news-name">{ev[0]}</span><span class="news-forecast">{ev[2]}</span><span class="news-day">{ev[3]}</span></div>"""

        instr_sections += f"""
        <div class="analysis-section{' hp-confluence' if is_confluence else ''}" id="{instr.lower()}">
          <div class="analysis-header">
            <div class="analysis-title-row">
              <h2 class="analysis-name">{instr}</h2>
              <div class="analysis-badge" style="background:{sig_color}15;color:{sig_color};border:1px solid {sig_color}40">{arr} {sig}</div>
              {hp_badge}
              <div class="analysis-range">{rng_str} RANGE</div>
              <div class="analysis-fair">{fair_str}</div>
              <button class="analysis-close" onclick="this.closest('.analysis-section').classList.toggle('collapsed')" title="Toggle">\u2715</button>
            </div>
            <div class="analysis-sub">
              <span class="analysis-ai">AI \u2014 NOT BACKTESTED</span>
              <span class="analysis-analysts">{conv_label}</span>
              {'<span class="analysis-analysts" style="color:var(--gold)">Positioning + Macro + COT all agree</span>' if is_confluence else ''}
            </div>
          </div>

          <div class="analysis-body">

            <div class="bottom-line-banner" style="border-left-color:{sig_color}">
              <span class="bl-label">Bottom Line</span>
              <span class="bl-text">{bottom_line}</span>
            </div>

            <div class="analysis-signal-section">
              <div class="signal-detail-header">
                <span class="sd-title">signal detail</span>
              </div>
              <div class="signal-detail-grid">
                <div class="sd-item"><span class="sd-label">Signal</span><span class="sd-val" style="color:{sig_color};font-weight:600">{sig}</span></div>
                <div class="sd-item"><span class="sd-label">Total Score</span><span class="sd-val">{ts if ts is not None else DASH}</span></div>
                <div class="sd-item"><span class="sd-label">Positioning</span><span class="sd-val">{ps}</span></div>
                <div class="sd-item"><span class="sd-label">COT</span><span class="sd-val">{d.get("cot_score", "N/A")}</span></div>
                <div class="sd-item"><span class="sd-label">Macro</span><span class="sd-val">{instr_macro_score}/5</span></div>
                <div class="sd-item"><span class="sd-label">AI Conviction</span><span class="sd-val">{conv_stars}/10 <span class="stars">{stars_html}</span></span></div>
                {"".join(f'<div class="sd-item"><span class="sd-label">{sent_label}</span><span class="sd-val" style="color:{sent_color}">{sent_sig}</span></div>' for _ in [1] if sent_sig)}
              </div>
            </div>

            <div class="analysis-narrative-section">
              <div class="analysis-narrative-block">
                <div class="an-block trade-idea">
                  <div class="an-label">Trade Idea (Options Positioning)</div>
                  <p>"{trade_idea}"</p>
                </div>
                {f'''<div class="an-block trade-idea forecast-idea">
                  <div class="an-label" style="color:var(--gold)">Trade Idea (Vol/Range Forecast, 1.5x ATR14 stop)</div>
                  <p>"{forecast_trade_idea}"</p>
                </div>''' if forecast_trade_idea else ''}
                {forecast_table_html}
                <div class="an-block positioning-narrative">
                  <details class="pos-analysis-details">
                    <summary class="an-label" style="cursor:pointer">Positioning Analysis (click to expand)</summary>
                    {"".join(f"<p>{p}</p>" for p in paragraphs)}
                  </details>
                </div>
                <p class="an-footer">Generated {gen_display}. AI opinion, not a backtested signal.{' | ' + oanda_note if oanda_note else ''}</p>
              </div>
            </div>

            <div class="analysis-extra">
              <div class="extra-col">
                <div class="extra-card">
                  <div class="extra-label">Today's News for This Pair</div>
                  <div class="extra-sub">Next event that may widen the range</div>
                  {news_rows}
                </div>
              </div>
              <div class="extra-col">
                <div class="extra-card">
                  <div class="extra-label">Correlations, Hedges &amp; Beta</div>
                  <div class="corr-grid">
                    <div class="corr-group">
                      <div class="corr-group-label">Moves with</div>
                      {''.join(f'<div class="corr-item"><span>{k}</span><span class="corr-val" style="color:{"var(--long)" if v>0 else "var(--short)"}">{v:+.2f}</span></div>' for k, v in corr.get("moves_with", {}).items())}
                    </div>
                    <div class="corr-group">
                      <div class="corr-group-label">Natural hedge</div>
                      {''.join(f'<div class="corr-item"><span>{k}</span><span class="corr-val" style="color:{"var(--long)" if v>0 else "var(--short)"}">{v:+.2f}</span></div>' for k, v in corr.get("hedges", {}).items())}
                    </div>
                    <div class="corr-group">
                      <div class="corr-group-label">Driven by</div>
                      <div class="corr-driven">{corr.get("driven_by", "")}</div>
                    </div>
                  </div>
                  <div class="corr-footer">10-day rolling window &bull; context only, not a signal</div>
                </div>
              </div>
            </div>

          </div>
        </div>"""

    dxy = fred.get("Dollar Index", {}).get("value")
    vix = fred.get("VIX", {}).get("value")
    y10 = fred.get("10Y Yield", {}).get("value")
    y2 = fred.get("2Y Yield", {}).get("value")
    macro_line_parts = []
    if vix: macro_line_parts.append(f"VIX: {vix}")
    if dxy: macro_line_parts.append(f"DXY: {dxy}")
    if y10 and y2: macro_line_parts.append(f"2-10: {float(y10)-float(y2):.2f}%")
    # CBOE volatility indices
    for label, key in [("VXN", "VXN"), ("GVZ", "GVZ"), ("EVZ", "EVZ"), ("SKEW", "SKEW")]:
        v = fred.get(key, {}).get("value")
        if v: macro_line_parts.append(f"{label}: {v}")
    # Breakeven inflation
    be = fred.get("10Y Breakeven", {}).get("value")
    if be: macro_line_parts.append(f"BE10: {be}%")
    macro_line = " &bull; ".join(macro_line_parts)

    macro_items = ""
    for label in ["10Y Yield", "2Y Yield", "5Y Breakeven", "10Y Breakeven", "VIX", "VXN", "GVZ", "EVZ", "SKEW", "Dollar Index", "Fed Funds"]:
        d_fred = fred.get(label, {})
        val = d_fred.get("value", DASH)
        dt = d_fred.get("date", "")
        is_stale = d_fred.get("stale", False)
        val_str = f"{val} \u26a0" if (is_stale and val != DASH) else str(val)
        val_color = "color:var(--short)" if is_stale else ""
        macro_items += f'<div class="macro-item" title="{"STALE / source may be discontinued" if is_stale else ""}"><span class="macro-label">{label}</span><span class="macro-val" style="{val_color}">{val_str}</span><span class="macro-date">{dt}</span></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Analysis \u2014 OME + Macro</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1/dist/chart.umd.min.js"></script>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0c10; --surface: #12151c; --border: #1e232d;
    --text: #c8cdd8; --muted: #525866;
    --long: #00c896; --short: #ff4d6d; --accent: #4a8fff; --gold: #e5b13a; --line: #1e232d; --gold2: #e5b13a; --red: #ff4d6d; --green: #00c896; --amber: #f0b429; --blue: #4a8fff;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: 'IBM Plex Sans', sans-serif; font-weight: 300; min-height: 100vh; }}
  .container {{ max-width: 960px; margin: 0 auto; padding: 1.5rem; }}

  .masthead {{ border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.25rem; display: flex; justify-content: space-between; align-items: baseline; }}
  .masthead h1 {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.1rem; font-weight: 600; color: white; letter-spacing: -0.02em; }}
  .masthead .date {{ font-size: 0.72rem; color: var(--muted); }}

  .overall-card {{ display: flex; align-items: center; gap: 1.25rem; background: var(--surface); border: 1px solid {overall_color}; border-radius: 8px; padding: 1rem 1.5rem; margin-bottom: 1.25rem; }}
  .overall-card .oc-arrow {{ font-size: 1.8rem; color: {overall_color}; }}
  .overall-card .oc-text {{ flex: 1; }}
  .overall-card .oc-text .oc-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); }}
  .overall-card .oc-text .oc-value {{ font-size: 1.3rem; font-weight: 600; color: {overall_color}; }}
  .overall-card .oc-text .oc-sub {{ font-size: 0.68rem; color: var(--muted); margin-top: 0.15rem; }}
  .overall-card .oc-macro {{ text-align: right; font-family: 'IBM Plex Mono', monospace; padding-left: 1rem; border-left: 1px solid var(--border); }}
  .overall-card .oc-macro .oc-m-label {{ font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); }}
  .overall-card .oc-macro .oc-m-value {{ font-size: 1rem; font-weight: 600; color: {color_for(macro_score)}; }}

  /* Analysis Sections */
  .analysis-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 8px; margin-bottom: 1rem; overflow: hidden; transition: all 0.15s; }}
  .analysis-section.collapsed .analysis-body {{ display: none; }}
  .analysis-section.collapsed .analysis-close {{ transform: rotate(45deg); }}

  .analysis-header {{ padding: 1rem 1.25rem; cursor: pointer; }}
  .analysis-title-row {{ display: flex; align-items: center; gap: 0.6rem; flex-wrap: wrap; }}
  .analysis-name {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.1rem; font-weight: 600; color: white; }}
  .analysis-badge {{ padding: 0.1rem 0.5rem; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; font-weight: 600; letter-spacing: 0.05em; }}
  .analysis-range {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--accent); letter-spacing: 0.1em; margin-left: 0.5rem; }}
  .analysis-fair {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--muted); }}
  .analysis-close {{ margin-left: auto; background: none; border: none; color: var(--muted); cursor: pointer; font-size: 0.8rem; font-family: inherit; transition: 0.15s; }}
  .analysis-close:hover {{ color: var(--text); }}
  .analysis-sub {{ display: flex; gap: 0.75rem; margin-top: 0.3rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: var(--muted); }}
  .analysis-ai {{ color: var(--muted); }}

  .analysis-body {{ padding: 0 1.25rem 1.25rem; }}

  /* Signal detail */
  .analysis-signal-section {{ margin-bottom: 1rem; }}
  .signal-detail-header {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem; }}
  .signal-detail-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 0.5rem; }}
  .sd-item {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.5rem 0.6rem; }}
  .sd-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); display: block; margin-bottom: 0.15rem; }}
  .sd-val {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.95rem; font-weight: 600; color: white; }}
  .stars {{ font-size: 0.65rem; margin-left: 0.15rem; letter-spacing: 0.05em; }}

  /* Narrative */
  .analysis-narrative-section {{ margin-bottom: 1rem; }}
  .analysis-narrative-block {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.85rem 1rem; }}
  .an-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); margin-bottom: 0.35rem; }}
  .bottom-line-banner {{ background: var(--bg); border: 1px solid var(--border); border-left: 3px solid var(--accent); border-radius: 6px; padding: 0.7rem 0.9rem; margin: 0.75rem 1rem 0; display: flex; gap: 0.6rem; align-items: baseline; flex-wrap: wrap; }}
  .bottom-line-banner .bl-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); flex-shrink: 0; }}
  .bottom-line-banner .bl-text {{ font-size: 0.85rem; font-weight: 500; color: var(--text); line-height: 1.4; }}
  .pos-analysis-details summary {{ list-style: none; }}
  .pos-analysis-details summary::-webkit-details-marker {{ display: none; }}
  .pos-analysis-details summary:hover {{ color: var(--accent); }}
  .pos-analysis-details[open] summary {{ margin-bottom: 0.35rem; }}
  .an-block {{ margin-bottom: 0.75rem; }}
  .an-block.trade-idea {{ border-left: 3px solid var(--accent); padding-left: 0.6rem; }}
  .an-block.trade-idea.forecast-idea {{ border-left-color: var(--gold); }}
  .forecast-idea-table {{ width: 100%; border-collapse: collapse; font-size: 0.75rem; margin-top: 0.3rem; }}
  .forecast-idea-table th {{ text-align: left; color: var(--muted); font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.08em; text-transform: uppercase; padding: 0.2rem 0.5rem; border-bottom: 1px solid var(--border); }}
  .forecast-idea-table td {{ padding: 0.25rem 0.5rem; border-bottom: 1px solid var(--border); font-family: 'IBM Plex Mono', monospace; }}
  .forecast-idea-table tr:last-child td {{ border-bottom: none; }}
  .an-block p {{ font-size: 0.78rem; line-height: 1.65; color: var(--text); }}
  .trade-idea p {{ color: var(--text); font-style: italic; }}
  .an-footer {{ font-size: 0.62rem; color: var(--muted); font-family: 'IBM Plex Mono', monospace; margin-top: 0.5rem; padding-top: 0.5rem; border-top: 1px solid var(--border); }}

  /* Extra columns */
  .analysis-extra {{ display: grid; grid-template-columns: 1fr 1.5fr; gap: 0.75rem; }}
  .extra-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.75rem; }}
  .extra-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.15rem; }}
  .extra-sub {{ font-size: 0.62rem; color: var(--muted); margin-bottom: 0.5rem; }}

  .news-row {{ display: flex; gap: 0.4rem; align-items: baseline; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; padding: 0.3rem 0; border-bottom: 1px solid var(--border); }}
  .news-row:last-child {{ border-bottom: none; }}
  .news-time {{ color: var(--accent); min-width: 3rem; }}
  .news-name {{ color: var(--text); flex: 1; }}
  .news-forecast {{ color: var(--muted); }}
  .news-day {{ color: var(--muted); font-size: 0.6rem; }}

  .corr-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.5rem; margin-bottom: 0.4rem; }}
  .corr-group-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.48rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.2rem; }}
  .corr-item {{ display: flex; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; padding: 0.1rem 0; }}
  .corr-val {{ font-weight: 600; }}
  .corr-driven {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--muted); line-height: 1.4; }}
  .corr-footer {{ font-size: 0.55rem; color: var(--muted); font-family: 'IBM Plex Mono', monospace; grid-column: 1 / -1; padding-top: 0.3rem; border-top: 1px solid var(--border); }}
  .chart-wrap-oi {{ position: relative; width: 100%; height: 240px; }}

  /* Macro bottom */
  .vol-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }}
  .vol-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }}
  .vol-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); }}
  .vol-session {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--accent); }}
  .vol-body {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; }}
  .vol-block {{ margin-bottom: 0.6rem; }}
  .vol-block:last-child {{ margin-bottom: 0; }}
  .vol-block-head {{ color: var(--accent); font-weight: 600; margin-bottom: 0.1rem; }}
  .vol-block-line {{ color: var(--text); line-height: 1.6; }}
  .vol-block-line strong {{ color: white; }}
  .events-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }}
  .events-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }}
  .events-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); }}
  .events-source {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: var(--muted); }}
  .events-table {{ width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; }}
  .events-table th {{ text-align: left; color: var(--muted); font-weight: 400; font-size: 0.52rem; letter-spacing: 0.1em; text-transform: uppercase; padding: 0.3rem 0.35rem; border-bottom: 1px solid var(--border); }}
  .events-table td {{ padding: 0.3rem 0.35rem; border-bottom: 1px solid var(--border); color: var(--text); }}
  .events-table tr:last-child td {{ border-bottom: none; }}
  .ev-time {{ color: var(--accent); white-space: nowrap; }}
  .ev-day {{ color: var(--muted); font-size: 0.6rem; }}
  .ev-flag {{ color: var(--muted); font-weight: 500; }}
  .ev-title {{ color: var(--text); }}
  .imp-badge {{ padding: 0.05rem 0.35rem; border-radius: 2px; font-size: 0.55rem; font-weight: 500; }}
  .imp-high {{ background: rgba(255,77,109,0.15); color: var(--short); }}
  .imp-med {{ background: rgba(74,143,255,0.15); color: var(--accent); }}
  .imp-low {{ background: rgba(90,96,112,0.15); color: var(--muted); }}
  .ev-fc, .ev-prev {{ color: var(--muted); font-size: 0.6rem; }}
  .events-note {{ font-size: 0.55rem; color: var(--muted); font-family: 'IBM Plex Mono', monospace; margin-top: 0.35rem; padding-top: 0.35rem; border-top: 1px solid var(--border); }}
  .gold-forecast-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }}
  .gold-fc-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }}
  .gold-fc-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); }}
  .gold-fc-source {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: var(--muted); }}
  .gold-fc-body {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.5rem; margin-bottom: 0.5rem; }}
  .gold-fc-metric {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.5rem 0.6rem; text-align: center; }}
  .gold-fc-k {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.48rem; letter-spacing: 0.12em; text-transform: uppercase; color: var(--muted); display: block; }}
  .gold-fc-v {{ font-family: 'IBM Plex Mono', monospace; font-size: 1rem; font-weight: 600; color: var(--gold); margin-top: 0.15rem; }}
  .gold-fc-footer {{ display: flex; justify-content: space-between; align-items: baseline; padding-top: 0.4rem; border-top: 1px solid var(--border); }}
  .gold-fc-link {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; color: var(--accent); text-decoration: none; }}
  .gold-fc-link:hover {{ text-decoration: underline; }}
  .gold-fc-date {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; color: var(--muted); }}
  .gold-fc-note {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.58rem; color: var(--muted); }}
  .snap-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-bottom: 1rem; }}
  .snap-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.6rem 0.8rem; cursor: pointer; transition: border-color 0.15s; position: relative; }}
  .snap-hp-tag {{ position: absolute; top: -0.5rem; right: 0.5rem; background: var(--gold); color: #000; font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; font-weight: 700; letter-spacing: 0.05em; padding: 0.12rem 0.4rem; border-radius: 3px; }}
  .analysis-section.hp-confluence {{ border: 1.5px solid var(--gold); box-shadow: 0 0 0 1px var(--gold)25; }}
  .snap-card:hover {{ border-color: var(--accent); }}
  .snap-name {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }}
  .snap-signal {{ font-size: 0.85rem; font-weight: 600; margin: 0.1rem 0; }}
  .snap-score {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--muted); }}
  .snap-bar {{ height: 3px; background: var(--border); border-radius: 2px; margin: 0.3rem 0; overflow: hidden; }}
  .snap-bar-fill {{ height: 100%; border-radius: 2px; transition: width 0.3s; }}
  .snap-price {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; color: var(--text); }}
  .geo-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.85rem 1rem; margin-bottom: 0.75rem; }}
  .geo-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 0.5rem; }}
  .geo-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); }}
  .geo-score {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.9rem; font-weight: 600; }}
  .geo-body {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.5rem; margin-bottom: 0.5rem; }}
  .geo-instr {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.4rem 0.6rem; display: flex; justify-content: space-between; align-items: center; }}
  .geo-instr-name {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--text); }}
  .geo-instr-level {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; padding: 0.1rem 0.4rem; border-radius: 3px; font-weight: 600; }}
  .geo-articles {{ max-height: 220px; overflow-y: auto; }}
  .geo-art {{ padding: 0.35rem 0; border-bottom: 1px solid var(--border); font-size: 0.68rem; line-height: 1.4; }}
  .geo-art:last-child {{ border-bottom: none; }}
  .geo-art-title {{ color: var(--text); text-decoration: none; }}
  .geo-art-title:hover {{ color: var(--accent); }}
  .geo-art-domain {{ color: var(--muted); font-size: 0.55rem; }}
  .geo-art-tags {{ display: inline-flex; gap: 0.2rem; flex-wrap: wrap; margin-left: 0.3rem; }}
  .geo-art-tag {{ background: rgba(74,143,255,0.12); color: var(--accent); font-size: 0.5rem; padding: 0.05rem 0.3rem; border-radius: 2px; text-transform: uppercase; }}
  .macro-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 0.85rem 1rem; margin-top: 0.5rem; }}
  .macro-card .mc-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.5rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem; }}
  .macro-card .mc-line {{ font-size: 0.72rem; color: var(--muted); font-family: 'IBM Plex Mono', monospace; margin-bottom: 0.4rem; }}
  .macro-card .mc-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.3rem; }}
  .macro-card .macro-item {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; display: flex; gap: 0.3rem; align-items: baseline; }}

  footer {{ margin-top: 1rem; font-size: 0.6rem; color: var(--muted); text-align: center; font-family: 'IBM Plex Mono', monospace; padding-top: 0.75rem; border-top: 1px solid var(--border); }}



  @media (max-width: 700px) {{
    .analysis-extra {{ grid-template-columns: 1fr; }}
    .signal-detail-grid {{ grid-template-columns: repeat(2, 1fr); }}
    .corr-grid {{ grid-template-columns: 1fr; }}
    .gold-fc-body {{ grid-template-columns: repeat(2, 1fr); }}
    .geo-body {{ grid-template-columns: 1fr; }}
    .macro-card .mc-grid {{ grid-template-columns: 1fr 1fr; }}
    .snap-grid {{ grid-template-columns: 1fr; }}
    .container {{ padding: 0.75rem; }}
  }}
</style>
</head>
<body>
<div class="container">

  <div class="masthead">
    <h1>Market Analysis</h1>
    <span class="date">{gen_display}</span>
  </div>

  <div class="snap-grid">{snapshot_rows}</div>

  {instr_sections}

  {gold_forecast_section}

  {oi_section}

  {vol_section}

  {events_section}

  {geo_section}

  <div class="macro-card">
    <div class="mc-label">Macro Snapshot</div>
    <div class="mc-line">{macro_line}</div>
    <div class="mc-grid">{macro_items}</div>
  </div>

  <footer>Yahoo Finance &rarr; Scoring &rarr; GitHub Pages &bull; Data updates 2x daily</footer>

</div>

<script>
(() => {{
  const ALLOI = {json.dumps(all_oi_data or {})};
  const fmt = x => x.toLocaleString('en-US',{{minimumFractionDigits:2,maximumFractionDigits:2}});
  const pct = x => (x>=0?'+':'')+x.toFixed(2)+'%';
  console.log('DBG ChartJS:',typeof Chart!=='undefined','OI keys:',Object.keys(ALLOI).join(','));

  // OI Charts — one set per instrument
  const INSTR_TAGS = {{Gold:'gold',NAS100:'nas100',EURUSD:'eurusd'}};
  const commonChart = {{
    responsive:true, maintainAspectRatio:false,
    plugins:{{legend:{{labels:{{color:'#525866',font:{{size:10}},boxWidth:12}}}}}},
    scales:{{
      x:{{ticks:{{color:'#525866',font:{{size:9}}}},grid:{{color:'#1e232d'}}}},
      y:{{ticks:{{color:'#525866',font:{{size:9}}}},grid:{{color:'#1e232d'}}}}
    }}
  }};
  Object.keys(INSTR_TAGS).forEach(instr => {{
    const OI = ALLOI[instr];
    if (!OI || !OI.strikes || !OI.strikes.length) return;
    const tag = INSTR_TAGS[instr], s = OI.strikes, co = OI.call_oi, po = OI.put_oi;
    const bar1 = document.getElementById(tag+'OiBarChart');
    const netC = document.getElementById(tag+'OiNetChart');
    const painC = document.getElementById(tag+'OiPainChart');
    const pcrC = document.getElementById(tag+'OiPcrChart');
    if (!bar1 || !netC || !painC || !pcrC) return;

    try {{
      new Chart(bar1, {{type:'bar', data:{{labels:s,datasets:[
        {{label:'Call OI',data:co,backgroundColor:'rgba(88,166,255,0.7)',borderColor:'#58a6ff',borderWidth:1}},
        {{label:'Put OI',data:po,backgroundColor:'rgba(218,54,51,0.7)',borderColor:'#da3633',borderWidth:1}}
      ]}}, options:{{...commonChart,plugins:{{...commonChart.plugins,title:{{display:true,text:'Open Interest by Strike',color:'#525866',font:{{size:11}}}}}}}}
      }});
    }} catch(e){{console.log('OI bar err:',e,'for',instr)}}
    const net = s.map((_,i)=> (po[i]||0)-(co[i]||0));
    new Chart(netC, {{type:'bar', data:{{labels:s,datasets:[{{label:'Net OI (Put-Call)',data:net,
      backgroundColor:net.map(d=>d>=0?'rgba(218,54,51,0.7)':'rgba(88,166,255,0.7)'),
      borderColor:net.map(d=>d>=0?'#da3633':'#58a6ff'),borderWidth:1
    }}]}}, options:{{...commonChart,plugins:{{...commonChart.plugins,title:{{display:true,text:'Net OI (bearish / bullish)',color:'#525866',font:{{size:11}}}}}}}}
    }});
    // Max Pain
    const pain = []; let mpStrike=null, mpVal=Infinity;
    const idxMap = new Map(s.map((v,i)=>[v,i]));
    for(const k of s){{ let t=0; for(const st of s){{ const ci=co[idxMap.get(st)]||0, pi=po[idxMap.get(st)]||0; if(st>k) t+=(st-k)*ci; else if(st<k) t+=(k-st)*pi; }} if(t<mpVal){{ mpVal=t; mpStrike=k; }} pain.push({{x:k,y:t}}); }}
    new Chart(painC, {{type:'line', data:{{datasets:[{{label:'Seller P&L at expiry',data:pain,borderColor:'#e5b13a',
      backgroundColor:'rgba(229,177,58,0.08)',fill:true,tension:0.3,pointRadius:2,pointBackgroundColor:'#e5b13a'}}]}},
      options:{{...commonChart,plugins:{{...commonChart.plugins,title:{{display:true,text:'Max Pain Profile — min at $'+fmt(mpStrike),color:'#525866',font:{{size:11}}}}}},
        scales:{{...commonChart.scales,x:{{...commonChart.scales.x,type:'linear',title:{{display:true,text:'Strike',color:'#525866',font:{{size:10}}}}}},
          y:{{...commonChart.scales.y,title:{{display:true,text:'Total payout',color:'#525866',font:{{size:10}}}}}}}}
    }}}});
    // PCR by strike
    const pcr = s.map((_,i)=> {{ const c=co[i]||0, p=po[i]||0; return c+p>0 ? p/c : 0; }});
    new Chart(pcrC, {{type:'bar', data:{{labels:s,datasets:[{{label:'Put/Call OI',data:pcr,
      backgroundColor:pcr.map(d=>d>1?'rgba(218,54,51,0.7)':'rgba(88,166,255,0.7)'),
      borderColor:pcr.map(d=>d>1?'#da3633':'#58a6ff'),borderWidth:1
    }}]}}, options:{{...commonChart,plugins:{{...commonChart.plugins,title:{{display:true,text:'Put/Call Ratio by Strike',color:'#525866',font:{{size:11}}}}}}}}
    }});
  }});

  // Gold Forecast detail panel removed (relied on an externally-generated
  // file this pipeline can't regenerate) — see build_dashboard.py comments.

  // Collapse toggle
  document.querySelectorAll('.analysis-header').forEach(h => {{
    h.addEventListener('click', () => h.parentElement.classList.toggle('collapsed'));
  }});
}})();
</script>
</body>
</html>"""

    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")
    return True

if __name__ == "__main__":
    run()
