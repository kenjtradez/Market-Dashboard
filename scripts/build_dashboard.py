"""
Generate a morning-brief static HTML dashboard from scores and raw data.
"""
import os
import json
from datetime import datetime

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..")
INSTRUMENTS = ["Gold", "NAS100", "EURUSD"]

def load_json(path):
    if os.path.exists(path):
        with open(path) as f:
            return json.load(f)
    return {}

def color_for(val):
    if val is None:
        return "var(--muted)"
    return "var(--long)" if val > 0 else ("var(--short)" if val < 0 else "var(--muted)")

def arrow_for(val):
    if val is None:
        return "\u2192"
    if val > 0:
        return "\u25b2"
    if val < 0:
        return "\u25bc"
    return "\u2192"

def fmt(v):
    if v is None or v == "\u2014":
        return "\u2014"
    try:
        if isinstance(v, float):
            if v < 10:
                return f"{v:.4f}"
            return f"{v:,.1f}" if v == int(v) else f"{v:,.2f}"
        if isinstance(v, int):
            return f"{v:,}"
        return str(v)
    except:
        return str(v)

def generate_brief(instr, d, ome_raw, macro_score):
    ts = d.get("total_score")
    sig = d.get("signal", "N/A")
    pcr = ome_raw.get("put_call_ratio")
    mp = ome_raw.get("max_pain")
    cw = ome_raw.get("call_wall")
    pw = ome_raw.get("put_wall")
    sp = ome_raw.get("underlying_price")

    parts = []
    if pcr is not None:
        if pcr > 1.3:
            parts.append(f"PCR at {pcr:.2f} shows heavy puts.")
        elif pcr < 0.7:
            parts.append(f"PCR at {pcr:.2f} shows call dominance.")
        else:
            parts.append(f"PCR at {pcr:.2f} is neutral.")

    if mp is not None and sp is not None:
        diff = ((mp - sp) / sp) * 100
        if abs(diff) < 0.5:
            parts.append(f"Max pain ({fmt(mp)}) is near price.")
        elif diff < 0:
            parts.append(f"Max pain ({fmt(mp)}) is {abs(diff):.1f}% below price \u2014 downside pull.")
        else:
            parts.append(f"Max pain ({fmt(mp)}) is {diff:.1f}% above price \u2014 upside pull.")

    if cw is not None and pw is not None:
        if cw > pw:
            parts.append(f"Call wall ({fmt(cw)}) above put wall ({fmt(pw)}). Resistance dominates.")
        elif cw < pw:
            parts.append(f"Put wall ({fmt(pw)}) below call wall ({fmt(cw)}). Support dominates.")
        else:
            parts.append(f"Both walls at {fmt(cw)} \u2014 key battleground.")

    parts.append(f"Score: {ts} ({sig}).")
    return " ".join(parts)

def run():
    scores = load_json(os.path.join(DATA_DIR, "scores.json"))
    fred = load_json(os.path.join(DATA_DIR, "fred_macro.json")).get("series", {})
    ome = load_json(os.path.join(DATA_DIR, "ome_data.json")).get("instruments", {})

    overall = scores.get("overall", {})
    macro = scores.get("macro", {})
    instruments = scores.get("instruments", {})

    gen_time = scores.get("generated", datetime.now().isoformat())
    gen_display = datetime.fromisoformat(gen_time).strftime("%d %b %Y  %H:%M")

    overall_signal = overall.get("signal", "NEUTRAL")
    overall_score = overall.get("avg_score")
    overall_color = color_for(overall_score)
    overall_arrow = arrow_for(overall_score)

    macro_score = macro.get("score", 0)
    macro_color = color_for(macro_score)
    macro_details = macro.get("details", {})

    instr_cards = ""
    for instr in INSTRUMENTS:
        d = instruments.get(instr, {})
        ts = d.get("total_score")
        sig = d.get("signal", "N/A")
        sig_color = "var(--long)" if sig == "LONG" else ("var(--short)" if sig == "SHORT" else "var(--muted)")
        arr = arrow_for(ts)
        ps = d.get("positioning_score", "\u2014")
        ome_raw = d.get("ome_data", {})
        pcr = ome_raw.get("put_call_ratio", "\u2014")
        mp = ome_raw.get("max_pain", "\u2014")
        cw = ome_raw.get("call_wall", "\u2014")
        pw = ome_raw.get("put_wall", "\u2014")
        mg = ome_raw.get("magnet_strike", "\u2014")
        sp = ome_raw.get("underlying_price", "\u2014")
        tot_oi = ome_raw.get("total_oi", "\u2014")
        brief = generate_brief(instr, d, ome_raw, macro_score)

        try:
            oi_display = f"{tot_oi:,}"
        except:
            oi_display = str(tot_oi)

        instr_cards += f"""
        <div class="brief-card" style="border-left-color:{sig_color}">
          <div class="brief-header">
            <div class="brief-name">{instr}</div>
            <div class="brief-badge" style="background:{sig_color}15;color:{sig_color}">{arr} {sig}</div>
          </div>
          <div class="brief-metrics">
            <div class="metric"><span class="metric-label">Price</span><span class="metric-val">{fmt(sp)}</span></div>
            <div class="metric"><span class="metric-label">PCR</span><span class="metric-val">{pcr}</span></div>
            <div class="metric"><span class="metric-label">Max Pain</span><span class="metric-val">{fmt(mp)}</span></div>
            <div class="metric"><span class="metric-label">Call Wall</span><span class="metric-val">{fmt(cw)}</span></div>
            <div class="metric"><span class="metric-label">Put Wall</span><span class="metric-val">{fmt(pw)}</span></div>
            <div class="metric"><span class="metric-label">Magnet</span><span class="metric-val">{fmt(mg)}</span></div>
            <div class="metric"><span class="metric-label">Total OI</span><span class="metric-val">{oi_display}</span></div>
            <div class="metric"><span class="metric-label">Pos. Score</span><span class="metric-val">{ps}</span></div>
          </div>
          <div class="brief-narrative">{brief}</div>
        </div>"""

    macro_items = ""
    for label in ["10Y Yield", "2Y Yield", "5Y Breakeven", "VIX", "Dollar Index", "Fed Funds"]:
        d = fred.get(label, {})
        val = d.get("value", "\u2014")
        dt = d.get("date", "")
        macro_items += f"""<div class="macro-item"><span class="macro-label">{label}</span><span class="macro-val">{val}</span><span class="macro-date">{dt}</span></div>"""

    vix = fred.get("VIX", {}).get("value")
    dxy = fred.get("Dollar Index", {}).get("value")
    macro_line_parts = []
    if vix:
        macro_line_parts.append(f"VIX: {vix}")
    if dxy:
        macro_line_parts.append(f"DXY: {dxy}")
    curve_y10 = fred.get("10Y Yield", {}).get("value")
    curve_y2 = fred.get("2Y Yield", {}).get("value")
    if curve_y10 and curve_y2:
        spread = float(curve_y10) - float(curve_y2)
        macro_line_parts.append(f"2-10 spread: {spread:.2f}%")
    macro_line = "  |  ".join(macro_line_parts)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Morning Brief \u2014 OME + Macro</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0d0f14; --surface: #161a22; --border: #252b38;
    --text: #c8cdd8; --muted: #5a6070;
    --long: #00c896; --short: #ff4d6d; --accent: #4a8fff;
    --gold: #f0b429;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: 'IBM Plex Sans', sans-serif; font-weight: 300; min-height: 100vh; }}
  .container {{ max-width: 900px; margin: 0 auto; padding: 2rem 1.5rem; }}

  /* Masthead */
  .masthead {{ border-bottom: 1px solid var(--border); padding-bottom: 1.25rem; margin-bottom: 1.5rem; }}
  .masthead-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.2em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.3rem; }}
  .masthead h1 {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.4rem; font-weight: 600; color: white; letter-spacing: -0.02em; }}
  .masthead .date {{ font-size: 0.78rem; color: var(--muted); margin-top: 0.2rem; }}

  /* Overall signal */
  .overall {{ display: flex; align-items: center; gap: 1.25rem; background: var(--surface); border: 1px solid {overall_color}; border-radius: 8px; padding: 1.25rem 1.5rem; margin-bottom: 1.25rem; }}
  .overall-arrow {{ font-size: 2.2rem; color: {overall_color}; line-height: 1; }}
  .overall-text {{ flex: 1; }}
  .overall-text .label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.15rem; }}
  .overall-text .value {{ font-size: 1.5rem; font-weight: 600; color: {overall_color}; }}
  .overall-text .sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.2rem; }}
  .overall-macro {{ text-align: right; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--muted); padding-left: 1rem; border-left: 1px solid var(--border); }}
  .overall-macro .macro-score {{ font-size: 1.1rem; font-weight: 600; color: {macro_color}; }}

  /* Instrument brief cards */
  .brief-card {{ background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--muted); border-radius: 6px; padding: 1.15rem 1.25rem; margin-bottom: 0.85rem; }}
  .brief-header {{ display: flex; align-items: center; gap: 0.75rem; margin-bottom: 0.6rem; }}
  .brief-name {{ font-family: 'IBM Plex Mono', monospace; font-size: 1rem; font-weight: 600; color: white; }}
  .brief-badge {{ padding: 0.15rem 0.6rem; border-radius: 3px; font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; font-weight: 600; letter-spacing: 0.05em; }}
  .brief-metrics {{ display: flex; flex-wrap: wrap; gap: 0.35rem 0.85rem; margin-bottom: 0.55rem; }}
  .metric {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; }}
  .metric-label {{ color: var(--muted); margin-right: 0.25rem; }}
  .metric-val {{ color: var(--text); font-weight: 400; }}
  .brief-narrative {{ font-size: 0.8rem; line-height: 1.6; color: var(--text); border-top: 1px solid var(--border); padding-top: 0.55rem; }}

  /* Macro section */
  .macro-section {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1rem 1.25rem; margin-top: 1rem; }}
  .macro-section .macro-label-header {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.6rem; }}
  .macro-section .macro-line {{ font-size: 0.78rem; color: var(--muted); margin-bottom: 0.6rem; font-family: 'IBM Plex Mono', monospace; }}
  .macro-grid {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 0.4rem; }}
  .macro-item {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; display: flex; gap: 0.4rem; align-items: baseline; }}
  .macro-item .macro-label {{ color: var(--muted); }}
  .macro-item .macro-val {{ color: var(--text); font-weight: 400; }}
  .macro-item .macro-date {{ color: var(--muted); font-size: 0.62rem; margin-left: auto; }}

  footer {{ margin-top: 1.25rem; font-size: 0.65rem; color: var(--muted); text-align: center; font-family: 'IBM Plex Mono', monospace; border-top: 1px solid var(--border); padding-top: 1rem; }}

  @media (max-width: 600px) {{ .container {{ padding: 1rem; }} .overall {{ flex-direction: column; text-align: center; }} .overall-macro {{ border-left: none; border-top: 1px solid var(--border); padding-left: 0; padding-top: 0.5rem; width: 100%; text-align: center; }} .macro-grid {{ grid-template-columns: 1fr 1fr; }} .brief-metrics {{ gap: 0.25rem 0.6rem; }} }}
</style>
</head>
<body>
<div class="container">

  <div class="masthead">
    <div class="masthead-label">Daily Briefing</div>
    <h1>Market Dashboard</h1>
    <div class="date">{gen_display}  &nbsp;|&nbsp; OME + Macro</div>
  </div>

  <div class="overall">
    <div class="overall-arrow">{overall_arrow}</div>
    <div class="overall-text">
      <div class="label">Overall Market Signal</div>
      <div class="value">{overall_signal}</div>
      <div class="sub">Composite: {overall_score if overall_score is not None else "\u2014"} / 8  &nbsp;|&nbsp; Instruments: Gold, NAS100, EUR/USD</div>
    </div>
    <div class="overall-macro">
      <div style="font-size:0.55rem;letter-spacing:0.15em;text-transform:uppercase;margin-bottom:0.1rem">Macro</div>
      <div class="macro-score">{macro_score}</div>
      <div style="font-size:0.62rem;margin-top:0.1rem">/ 3</div>
    </div>
  </div>

  {instr_cards}

  <div class="macro-section">
    <div class="macro-label-header">Macro Snapshot</div>
    <div class="macro-line">{macro_line}</div>
    <div class="macro-grid">
      {macro_items}
    </div>
  </div>

  <footer>
    CME OI PDFs &rarr; pdfplumber &rarr; FRED API &rarr; Scoring &rarr; GitHub Pages
  </footer>

</div>
</body>
</html>"""

    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")
    return True

if __name__ == "__main__":
    run()
