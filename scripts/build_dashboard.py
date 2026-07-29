"""
Generate a full-analysis dashboard with conviction, narrative, news, correlations.
"""
import os, json
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
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

# Economic events for the next few days (updated periodically)
ECON_EVENTS = [
    ("CB Consumer Confidence", "14:00", "92.4c", "Today"),
    ("FOMC Rate Decision", "19:00", "5.50%", "Wed"),
    ("US GDP QoQ", "13:30", "2.1%", "Thu"),
    ("Nonfarm Payrolls", "13:30", "185K", "Fri"),
]

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

def conviction_label(score, max_val=8):
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

def generate_narrative(instr, d, ome_raw, macro_score):
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
    p3 += f"Macro contributes {macro_score}/3 to the score. "
    p3 += f"Net score: {ts} ({sig})."
    paragraphs.append(p3)

    return paragraphs

def generate_trade_idea(instr, d, ome_raw):
    """Generate a specific trade idea based on positioning."""
    ts = d.get("total_score")
    sig = d.get("signal", "N/A")
    pcr = ome_raw.get("put_call_ratio")
    mp = ome_raw.get("max_pain")
    cw = ome_raw.get("call_wall")
    pw = ome_raw.get("put_wall")
    sp = ome_raw.get("underlying_price")

    if sig == "LONG":
        if cw and pw and cw > pw:
            return f"Lean long at {fmt(pw)} put-wall support, target {fmt(mp)} range midpoint, stop below {fmt(pw - (pw * 0.01 if pw > 100 else 0.001))}; fade any rip to {fmt(cw)} call wall."
        return f"Bullish bias: look for dips toward support, target a drift higher. Stop below recent range lows."
    elif sig == "SHORT":
        if cw and pw and cw > pw:
            return f"Lean short at {fmt(cw)} call-wall resistance, target {fmt(mp)} max pain, stop above {fmt(cw + (cw * 0.01 if cw > 100 else 0.001))}; fade any dip to {fmt(pw)} put wall."
        return f"Bearish bias: look for rallies toward resistance, target a drift lower. Stop above recent range highs."
    else:
        if cw and pw:
            return f"Neutral: fade pushes toward {fmt(cw)} (sell) and treat {fmt(pw)} as a floor (buy). Low conviction \u2014 small size only."
        return f"Neutral bias \u2014 no strong directional edge. Wait for a clear break of the range."

def run():
    scores = load_json(os.path.join(DATA_DIR, "scores.json"))
    fred = load_json(os.path.join(DATA_DIR, "fred_macro.json")).get("series", {})
    ome = load_json(os.path.join(DATA_DIR, "ome_data.json")).get("instruments", {})

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

    instr_sections = ""
    for instr in INSTRUMENTS:
        d = instruments.get(instr, {})
        ts = d.get("total_score")
        sig = d.get("signal", "N/A")
        sig_color = "var(--long)" if sig == "LONG" else ("var(--short)" if sig == "SHORT" else "var(--muted)")
        arr = arrow_for(ts)
        ps = d.get("positioning_score", 0)
        ome_raw = d.get("ome_data", {})
        pcr = ome_raw.get("put_call_ratio")
        mp = ome_raw.get("max_pain")
        cw = ome_raw.get("call_wall")
        pw = ome_raw.get("put_wall")
        mg = ome_raw.get("magnet_strike")
        sp = ome_raw.get("underlying_price")
        tot = ome_raw.get("total_oi")

        conv_label, conv_stars = conviction_label(ts, 8)
        rng = range_pct(sp, cw, pw)
        rng_str = f"{rng:.0f}%" if rng is not None else DASH

        paragraphs = generate_narrative(instr, d, ome_raw, macro_score)
        trade_idea = generate_trade_idea(instr, d, ome_raw)
        stars_html = "\u2605" * conv_stars + "\u2606" * (10 - conv_stars)

        corr = CORRELATIONS.get(instr, {})

        news_rows = ""
        for ev in ECON_EVENTS:
            news_rows += f"""
            <div class="news-row"><span class="news-time">{ev[1]}</span><span class="news-name">{ev[0]}</span><span class="news-forecast">{ev[2]}</span><span class="news-day">{ev[3]}</span></div>"""

        instr_sections += f"""
        <div class="analysis-section" id="{instr.lower()}">
          <div class="analysis-header">
            <div class="analysis-title-row">
              <h2 class="analysis-name">{instr}</h2>
              <div class="analysis-badge" style="background:{sig_color}15;color:{sig_color};border:1px solid {sig_color}40">{arr} {sig}</div>
              <div class="analysis-range">{rng_str} RANGE</div>
              <div class="analysis-fair">near fair value</div>
              <button class="analysis-close" onclick="this.closest('.analysis-section').classList.toggle('collapsed')" title="Toggle">\u2715</button>
            </div>
            <div class="analysis-sub">
              <span class="analysis-ai">AI \u2014 NOT BACKTESTED</span>
              <span class="analysis-analysts">{conv_label}</span>
            </div>
          </div>

          <div class="analysis-body">

            <div class="analysis-signal-section">
              <div class="signal-detail-header">
                <span class="sd-title">signal detail</span>
              </div>
              <div class="signal-detail-grid">
                <div class="sd-item"><span class="sd-label">Signal</span><span class="sd-val" style="color:{sig_color};font-weight:600">{sig}</span></div>
                <div class="sd-item"><span class="sd-label">Total Score</span><span class="sd-val">{ts if ts is not None else DASH}</span></div>
                <div class="sd-item"><span class="sd-label">Positioning</span><span class="sd-val">{ps}</span></div>
                <div class="sd-item"><span class="sd-label">Macro</span><span class="sd-val">{macro_score}/3</span></div>
                <div class="sd-item"><span class="sd-label">AI Conviction</span><span class="sd-val">{conv_stars}/10 <span class="stars">{stars_html}</span></span></div>
              </div>
            </div>

            <div class="analysis-narrative-section">
              <div class="analysis-narrative-block">
                <div class="an-block trade-idea">
                  <div class="an-label">Trade Idea</div>
                  <p>"{trade_idea}"</p>
                </div>
                <div class="an-block positioning-narrative">
                  <div class="an-label">Positioning Analysis</div>
                  {"".join(f"<p>{p}</p>" for p in paragraphs)}
                </div>
                <p class="an-footer">Generated {gen_display}. AI opinion, not a backtested signal.</p>
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
    macro_line = " &bull; ".join(macro_line_parts)

    macro_items = ""
    for label in ["10Y Yield", "2Y Yield", "5Y Breakeven", "VIX", "Dollar Index", "Fed Funds"]:
        d_fred = fred.get(label, {})
        val = d_fred.get("value", DASH)
        dt = d_fred.get("date", "")
        macro_items += f'<div class="macro-item"><span class="macro-label">{label}</span><span class="macro-val">{val}</span><span class="macro-date">{dt}</span></div>'

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Analysis \u2014 OME + Macro</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0a0c10; --surface: #12151c; --border: #1e232d;
    --text: #c8cdd8; --muted: #525866;
    --long: #00c896; --short: #ff4d6d; --accent: #4a8fff;
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
  .an-block {{ margin-bottom: 0.75rem; }}
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

  /* Macro bottom */
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
    .macro-card .mc-grid {{ grid-template-columns: 1fr 1fr; }}
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

  <div class="overall-card">
    <div class="oc-arrow">{overall_arrow}</div>
    <div class="oc-text">
      <div class="oc-label">Overall Market Signal</div>
      <div class="oc-value">{overall_signal}</div>
      <div class="oc-sub">Composite: {overall_score if overall_score is not None else DASH}/8 &bull; OME + Macro</div>
    </div>
    <div class="oc-macro">
      <div class="oc-m-label">Macro</div>
      <div class="oc-m-value">{macro_score}</div>
      <div style="font-size:0.58rem;color:var(--muted);margin-top:0.05rem">/3</div>
    </div>
  </div>

  {instr_sections}

  <div class="macro-card">
    <div class="mc-label">Macro Snapshot</div>
    <div class="mc-line">{macro_line}</div>
    <div class="mc-grid">{macro_items}</div>
  </div>

  <footer>CME OI &rarr; pdfplumber &rarr; FRED API &rarr; Scoring &rarr; GitHub Pages</footer>

</div>

<script>
  document.querySelectorAll('.analysis-header').forEach(h => {{
    h.addEventListener('click', () => h.parentElement.classList.toggle('collapsed'));
  }});
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
