"""
Generate a static HTML dashboard from scores.json and the latest raw data.
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

    parts = []
    parts.append(f"The overall signal for {instr} is **{sig}** (score {ts}).")

    if pcr is not None:
        if pcr > 1.3:
            parts.append(f"The put/call ratio of **{pcr:.2f}** signals heavy put positioning \u2014 options traders are loading up on downside protection, a bearish sign.")
        elif pcr < 0.7:
            parts.append(f"The put/call ratio of **{pcr:.2f}** shows call dominance \u2014 traders are positioning for upside, a bullish sign.")
        else:
            parts.append(f"The put/call ratio of **{pcr:.2f}** is balanced.")

    if mp is not None and sp is not None and sp != "\u2014":
        diff_pct = (mp - sp) / sp * 100
        if abs(diff_pct) < 0.5:
            parts.append(f"Max pain at **{mp}** sits very close to the current price ({sp:.4f}), so minimal gravitational pull toward max pain.")
        elif diff_pct < 0:
            parts.append(f"Max pain at **{mp}** is **{abs(diff_pct):.1f}%** below the current price ({sp:.4f}) \u2014 price is stretched above max pain and may drift lower toward it.")
        else:
            parts.append(f"Max pain at **{mp}** is **{diff_pct:.1f}%** above the current price ({sp:.4f}) \u2014 price is below max pain and may drift higher toward it.")
    elif mp is not None:
        parts.append(f"Max pain is at **{mp}**.")

    if cw is not None and pw is not None:
        if cw > pw:
            parts.append(f"The call wall at **{cw:,}** towers above the put wall at **{pw:,}**, meaning resistance overhead is the dominant structural level.")
        elif cw < pw:
            parts.append(f"The put wall at **{pw:,}** dominates below the call wall at **{cw:,}**, giving support a stronger footing than resistance.")
        else:
            parts.append(f"Both put and call walls converge at **{cw:,}** \u2014 a major battleground where the most open interest sits.")

    if mg is not None:
        parts.append(f"The magnet strike at **{mg:,}** holds the highest total open interest concentration, acting as a price attractor.")

    parts.append(f"Macro contributes **{macro_score}/3**. Net score: **{ts}** ({sig}).")

    return " ".join(parts)

def build_tabs(tabs_data, macro_score):
    labels_html = ""
    panels_html = ""
    for i, td in enumerate(tabs_data):
        checked = "checked" if i == 0 else ""
        active = "tab-active" if i == 0 else ""
        visible = "tab-visible" if i == 0 else ""

        labels_html += f'<input type="radio" name="tabs" id="tab{i}" class="tab-input" {checked}>\n'
        labels_html += f'<label for="tab{i}" class="tab-label {active}">{td["name"]}</label>\n'

        sig_color = td["sig_color"]
        arr = td["arr"]
        sig = td["sig"]
        ts = td["ts"]
        ps = td["ps"]
        macro_color = td["macro_color"]
        mp = td["mp"]
        sp = td["sp"]
        pcr = td["pcr"]
        cw = td["cw"]
        pw = td["pw"]
        mg = td["mg"]
        oi = td["oi"]
        narrative = td["narrative"]

        pcr_label = "Bearish" if isinstance(pcr, (int, float)) and pcr > 1.3 else ("Bullish" if isinstance(pcr, (int, float)) and pcr < 0.7 else "Neutral")

        panels_html += f"""
        <div class="tab-panel {visible}">
          <div class="tab-grid">
            <div class="tab-card signal" style="border-color:{sig_color}">
              <span class="tab-card-label">Signal</span>
              <span class="tab-card-value" style="color:{sig_color}">{arr} {sig}</span>
              <span class="tab-card-sub">Score: {ts if ts is not None else "\u2014"}</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Positioning</span>
              <span class="tab-card-value" style="color:{color_for(ps)}">{ps}</span>
              <span class="tab-card-sub">/ 5 possible</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Macro</span>
              <span class="tab-card-value" style="color:{macro_color}">{macro_score}</span>
              <span class="tab-card-sub">/ 3 possible</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Max Pain</span>
              <span class="tab-card-value">{mp}</span>
              <span class="tab-card-sub">Underlying: {sp}</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">P/C Ratio</span>
              <span class="tab-card-value">{pcr}</span>
              <span class="tab-card-sub">{pcr_label}</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Walls</span>
              <span class="tab-card-value" style="font-size:0.85rem">C: {cw} / P: {pw}</span>
              <span class="tab-card-sub">Call / Put</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Magnet</span>
              <span class="tab-card-value">{mg}</span>
              <span class="tab-card-sub">Highest OI concentration</span>
            </div>
            <div class="tab-card">
              <span class="tab-card-label">Total OI</span>
              <span class="tab-card-value" style="font-size:0.85rem">{oi}</span>
              <span class="tab-card-sub">Open Interest</span>
            </div>
          </div>
          <div class="narrative">
            <div class="narrative-label">What's Happening</div>
            <p>{narrative}</p>
          </div>
        </div>"""

    return labels_html, panels_html

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

    rows = ""
    tabs_data = []
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
        rows += f"""
        <tr>
          <td><strong>{instr}</strong></td>
          <td style="color:{sig_color};font-weight:600">{arr} {sig}</td>
          <td style="color:{color_for(ts)}">{ts if ts is not None else "\u2014"}</td>
          <td>{ps}</td>
          <td>{macro_score}</td>
          <td>{pcr}</td>
          <td>{mp}</td>
          <td>{cw} / {pw}</td>
        </tr>"""

        narrative = generate_narrative(instr, d, ome_raw, macro_score)

        mg = ome_raw.get("magnet_strike", "\u2014")
        sp = ome_raw.get("underlying_price", "\u2014")
        oi_val = ome_raw.get("total_oi", "\u2014")
        try:
            oi_display = f"{oi_val:,}"
        except:
            oi_display = str(oi_val)

        tabs_data.append({
            "name": instr,
            "sig_color": sig_color,
            "arr": arr,
            "sig": sig,
            "ts": ts,
            "ps": ps,
            "macro_color": macro_color,
            "mp": mp,
            "sp": sp,
            "pcr": pcr,
            "cw": cw,
            "pw": pw,
            "mg": mg,
            "oi": oi_display,
            "narrative": narrative,
        })

    tab_labels_html, tab_panels_html = build_tabs(tabs_data, macro_score)

    macro_rows = ""
    for label in ["10Y Yield", "2Y Yield", "5Y Breakeven", "VIX", "Dollar Index", "Fed Funds"]:
        d = fred.get(label, {})
        val = d.get("value", "\u2014")
        dt = d.get("date", "")
        macro_rows += f"""
        <tr>
          <td>{label}</td>
          <td>{val}</td>
          <td style="color:var(--muted);font-size:0.72rem">{dt}</td>
        </tr>"""

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Market Dashboard \u2014 OME + Macro</title>
<style>
  @import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=IBM+Plex+Sans:wght@300;400;600&display=swap');
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg: #0d0f14; --surface: #161a22; --border: #252b38;
    --text: #c8cdd8; --muted: #5a6070;
    --long: #00c896; --short: #ff4d6d; --accent: #4a8fff;
  }}
  body {{ background: var(--bg); color: var(--text); font-family: 'IBM Plex Sans', sans-serif; font-weight: 300; min-height: 100vh; padding: 1.5rem; }}
  header {{ display: flex; justify-content: space-between; align-items: baseline; border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.5rem; }}
  header h1 {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.95rem; font-weight: 600; letter-spacing: 0.12em; text-transform: uppercase; color: white; }}
  header span {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; color: var(--muted); }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 0.85rem; margin-bottom: 1.5rem; }}
  .card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 6px; padding: 1.25rem; }}
  .card.overall {{ grid-column: 1 / -1; display: flex; align-items: center; gap: 2rem; padding: 1.5rem 2rem; border-color: {overall_color}; }}
  .card.overall .big-arrow {{ font-size: 2.8rem; color: {overall_color}; line-height: 1; }}
  .card.overall .big-text .label {{ font-size: 0.65rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.3rem; }}
  .card.overall .big-text .value {{ font-size: 1.8rem; font-weight: 600; color: {overall_color}; }}
  .card.overall .big-text .sub {{ font-size: 0.8rem; color: var(--muted); margin-top: 0.3rem; }}
  .card .label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.6rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.4rem; }}
  .card .value {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.6rem; font-weight: 600; color: white; }}
  .card .sub {{ font-size: 0.72rem; color: var(--muted); margin-top: 0.2rem; }}
  .full {{ grid-column: 1 / -1; }}
  table {{ width: 100%; border-collapse: collapse; font-family: 'IBM Plex Mono', monospace; font-size: 0.78rem; }}
  th {{ text-align: left; color: var(--muted); font-weight: 400; font-size: 0.62rem; letter-spacing: 0.12em; text-transform: uppercase; padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); }}
  td {{ padding: 0.5rem 0.6rem; border-bottom: 1px solid var(--border); color: var(--text); }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: rgba(255,255,255,0.02); }}
  footer {{ margin-top: 1.5rem; font-size: 0.68rem; color: var(--muted); text-align: center; font-family: 'IBM Plex Mono', monospace; }}

  /* Tabs */
  .tabs {{ grid-column: 1 / -1; background: var(--surface); border: 1px solid var(--border); border-radius: 6px; overflow: hidden; }}
  .tab-input {{ display: none; }}
  .tab-labels {{ display: flex; border-bottom: 1px solid var(--border); background: var(--bg); }}
  .tab-label {{ padding: 0.75rem 1.25rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--muted); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.15s; }}
  .tab-label:hover {{ color: var(--text); background: rgba(255,255,255,0.03); }}
  .tab-input:checked + .tab-label {{ color: white; border-bottom-color: var(--accent); background: var(--surface); }}
  .tab-panel {{ display: none; padding: 1.25rem; }}
  .tab-visible {{ display: block; }}
  .tab-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 0.75rem; margin-bottom: 1.25rem; }}
  .tab-card {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 0.85rem; display: flex; flex-direction: column; }}
  .tab-card.signal {{ border-width: 1px; border-style: solid; }}
  .tab-card-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--muted); margin-bottom: 0.3rem; }}
  .tab-card-value {{ font-family: 'IBM Plex Mono', monospace; font-size: 1.2rem; font-weight: 600; color: white; }}
  .tab-card-sub {{ font-size: 0.65rem; color: var(--muted); margin-top: 0.15rem; }}
  .narrative {{ background: var(--bg); border: 1px solid var(--border); border-radius: 4px; padding: 1rem; }}
  .narrative-label {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.55rem; letter-spacing: 0.15em; text-transform: uppercase; color: var(--accent); margin-bottom: 0.5rem; }}
  .narrative p {{ font-size: 0.82rem; line-height: 1.7; color: var(--text); }}

  @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} .tab-grid {{ grid-template-columns: 1fr 1fr; }} body {{ padding: 1rem; }} }}
</style>
</head>
<body>

<header>
  <h1>Market Dashboard \u2014 OME + Macro</h1>
  <span>Generated {gen_display}</span>
</header>

<div class="grid">

  <div class="card overall">
    <div class="big-arrow">{overall_arrow}</div>
    <div class="big-text">
      <div class="label">Overall Market Signal</div>
      <div class="value">{overall_signal}</div>
      <div class="sub">Composite score: {overall_score if overall_score is not None else "\u2014"} &nbsp;|&nbsp; Blended positioning + macro</div>
    </div>
  </div>

  <div class="card">
    <div class="label">Macro Score</div>
    <div class="value" style="color:{macro_color}">{macro_score if macro_score is not None else "\u2014"}</div>
    <div class="sub">Rates &bull; VIX &bull; Dollar &bull; Curve</div>
  </div>

  <div class="card">
    <div class="label">Instruments Tracked</div>
    <div class="value">3</div>
    <div class="sub">Gold &bull; NAS100 &bull; EUR/USD</div>
  </div>

  <div class="card">
    <div class="label">Data Sources</div>
    <div class="value" style="font-size:1rem">FRED + OME</div>
    <div class="sub">Macro via API &bull; OI via CME PDF extracts</div>
  </div>

  <div class="card">
    <div class="label">Status</div>
    <div class="value" style="font-size:1rem;color:var(--accent)">LIVE</div>
    <div class="sub">Auto-updated daily</div>
  </div>

  <!-- Instrument Table -->
  <div class="card full">
    <div class="label" style="margin-bottom:0.8rem">Per-Instrument Scores</div>
    <table>
      <thead>
        <tr>
          <th>Instrument</th>
          <th>Signal</th>
          <th>Total</th>
          <th>Positioning</th>
          <th>Macro</th>
          <th>P/C Ratio</th>
          <th>Max Pain</th>
          <th>Walls (C/P)</th>
        </tr>
      </thead>
      <tbody>
        {rows}
      </tbody>
    </table>
  </div>

  <!-- Instrument Tabs -->
  <div class="tabs full">
    <div class="tab-labels">
      {tab_labels_html}
    </div>
    {tab_panels_html}
  </div>

  <!-- Macro Table -->
  <div class="card full">
    <div class="label" style="margin-bottom:0.8rem">FRED Macro Data</div>
    <table>
      <thead>
        <tr>
          <th>Series</th>
          <th>Value</th>
          <th>Date</th>
        </tr>
      </thead>
      <tbody>
        {macro_rows}
      </tbody>
    </table>
  </div>

</div>

<footer>
  OME reports &rarr; PDF extraction &rarr; FRED API &rarr; Scoring &rarr; Static Site &nbsp;|&nbsp;
  Upload reports to trigger rebuild
</footer>

</body>
</html>"""

    out_path = os.path.join(OUTPUT_DIR, "index.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Dashboard written to {out_path}")
    return True

if __name__ == "__main__":
    run()
