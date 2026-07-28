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

def color_for(val, kind="score"):
    if val is None:
        return "var(--muted)"
    if kind == "score":
        return "var(--long)" if val > 0 else ("var(--short)" if val < 0 else "var(--muted)")
    return "var(--muted)"

def arrow_for(val):
    if val is None:
        return "→"
    if val > 0:
        return "▲"
    if val < 0:
        return "▼"
    return "→"

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
    for instr in INSTRUMENTS:
        d = instruments.get(instr, {})
        ts = d.get("total_score")
        sig = d.get("signal", "N/A")
        cls = "long" if sig == "LONG" else ("short" if sig == "SHORT" else "neutral")
        sig_color = "var(--long)" if sig == "LONG" else ("var(--short)" if sig == "SHORT" else "var(--muted)")
        arr = arrow_for(ts)
        ps = d.get("positioning_score", "—")
        ome_raw = d.get("ome_data", {})
        pcr = ome_raw.get("put_call_ratio", "—")
        mp = ome_raw.get("max_pain", "—")
        cw = ome_raw.get("call_wall", "—")
        pw = ome_raw.get("put_wall", "—")
        rows += f"""
        <tr>
          <td><strong>{instr}</strong></td>
          <td style="color:{sig_color};font-weight:600">{arr} {sig}</td>
          <td style="color:{color_for(ts)}">{ts if ts is not None else "—"}</td>
          <td>{ps}</td>
          <td>{macro_score}</td>
          <td>{pcr}</td>
          <td>{mp}</td>
          <td>{cw} / {pw}</td>
        </tr>"""

    macro_rows = ""
    for label in ["10Y Yield", "2Y Yield", "5Y Breakeven", "VIX", "Dollar Index", "Fed Funds"]:
        d = fred.get(label, {})
        val = d.get("value", "—")
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
<title>Market Dashboard — OME + Macro</title>
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
  .badge {{ display: inline-block; padding: 0.12rem 0.5rem; border-radius: 3px; font-size: 0.62rem; font-weight: 600; letter-spacing: 0.08em; }}
  .badge.long {{ background: rgba(0,200,150,0.15); color: var(--long); }}
  .badge.short {{ background: rgba(255,77,109,0.12); color: var(--short); }}
  .badge.neutral {{ background: rgba(90,96,112,0.15); color: var(--muted); }}
  .pos {{ color: var(--long); }} .neg {{ color: var(--short); }}
  footer {{ margin-top: 1.5rem; font-size: 0.68rem; color: var(--muted); text-align: center; font-family: 'IBM Plex Mono', monospace; }}
  @media (max-width: 800px) {{ .grid {{ grid-template-columns: 1fr 1fr; }} body {{ padding: 1rem; }} }}
</style>
</head>
<body>

<header>
  <h1>Market Dashboard &mdash; OME + Macro</h1>
  <span>Generated {gen_display}</span>
</header>

<div class="grid">

  <div class="card overall">
    <div class="big-arrow">{overall_arrow}</div>
    <div class="big-text">
      <div class="label">Overall Market Signal</div>
      <div class="value">{overall_signal}</div>
      <div class="sub">Composite score: {overall_score if overall_score is not None else "—"} &nbsp;|&nbsp; Blended positioning + macro</div>
    </div>
  </div>

  <div class="card">
    <div class="label">Macro Score</div>
    <div class="value" style="color:{macro_color}">{macro_score if macro_score is not None else "—"}</div>
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
    <div class="sub">Macro via API &bull; Positioning via vision</div>
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
  Screenshots &rarr; Claude Vision &rarr; FRED API &rarr; Scoring &rarr; Static Site &nbsp;|&nbsp;
  Upload screenshots to trigger rebuild
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
