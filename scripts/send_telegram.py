"""
Send one consolidated Telegram brief built from the pipeline's data files.
Replaces both the old 6-message morning brief and the separate
options-tracker alert bot, so there is one signal source.
"""
import os, sys, json, urllib.request, urllib.error, urllib.parse
from datetime import datetime
from html import escape
from zoneinfo import ZoneInfo

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
from build_dashboard import generate_bottom_line  # shared wording with the dashboard

DATA_DIR = os.path.join(SCRIPT_DIR, "..", "data")
UK = ZoneInfo("Europe/London")
INSTRUMENTS = [("Gold", "XAU/USD", 2), ("NAS100", "NAS100", 1), ("SPX500", "S&amp;P 500", 1), ("US2000", "Russell 2000", 1),
               ("EURUSD", "EUR/USD", 5), ("USDJPY", "USD/JPY", 3)]
MAX_LEN = 4000  # Telegram limit is 4096
ARROW = {"LONG": "▲", "SHORT": "▼", "NEUTRAL": "◆"}


def load(name):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def num(v, d):
    return "—" if v is None else f"{v:,.{d}f}"


def instrument_block(instr, label, dec, s, vr, model, band):
    ts = s.get("total_score")
    sig = s.get("signal", "N/A")
    ome = s.get("ome_data", {})
    lines = [f"<b>{ARROW.get(sig, '')} {label} — {sig} ({ts:+d})</b>  {num(ome.get('underlying_price'), dec)}" if ts is not None
             else f"<b>{label}</b> — no data"]
    if ts is None:
        return "\n".join(lines)
    lines.append(f"Pos {s.get('positioning_score', 0):+d} · Macro {s.get('macro_score', 0):+d} · COT {s.get('cot_score', 0):+d}")
    lines.append(escape(generate_bottom_line(instr, s, ome, model.get("confluence_min", 4))))
    if s.get("options_ok"):
        lines.append(f"Walls C {num(ome.get('call_wall'), dec)} / P {num(ome.get('put_wall'), dec)} · "
                     f"max pain {num(ome.get('max_pain'), dec)} · PCR {num(ome.get('put_call_ratio'), 2)} "
                     f"({escape(str(ome.get('proxy_for')))} {escape(str(ome.get('expiry')))})")
    else:
        lines.append("Options levels: no usable snapshot")
    v = vr.get(instr) or {}
    spot = ome.get("underlying_price")
    if spot and v.get("up_median") is not None and v.get("down_median") is not None:
        lines.append(f"Typical day: +{v['up_median']:.2f}% / −{v['down_median']:.2f}% "
                     f"→ {num(spot * (1 + v['up_median'] / 100), dec)} / {num(spot * (1 - v['down_median'] / 100), dec)}")
    cot = s.get("cot_details", {}).get("cot")
    if cot:
        lines.append(f"COT: {escape(cot)}")
    br = band.get(instr) or {}
    if br.get("verdict"):
        v = br["verdict"]
        sd = br["sides"][v["side"]]
        line = f"Bands {escape(br['as_of'][11:16])}: <b>{escape(v['status'])}</b>"
        if sd.get("extreme_in"):
            line += f" \u00b7 new {'high' if v['side'] == 'up' else 'low'} later on {100 - sd['extreme_in']['p']}% of similar days"
        if sd.get("reach") and sd.get("base"):
            name = "median" if sd["next_band"] == "med" else "75th"
            line += (f" \u00b7 reach {'upper' if v['side'] == 'up' else 'lower'} {name} {num(sd['level'], dec)}: "
                     f"{sd['reach']['p']}% (normal day {sd['base']['p']}%)")
        elif sd.get("next_band") is None:
            line += f" \u00b7 already through the {'upper' if v['side'] == 'up' else 'lower'} 75th"
        lines.append(line)
    return "\n".join(lines)


def build_message(page_url):
    scores = load("scores.json")
    if not scores.get("instruments"):
        return None
    model = scores.get("model", {})
    vr = load("vol_range.json").get("instruments", {})
    band = load("band_read.json").get("instruments", {})
    now = datetime.now(UK)

    parts = [f"<b>\U0001f4ca Market Brief</b> — {now:%a %d %b %H:%M} UK",
             f"Signal needs |score| ≥ {model.get('signal_threshold', 2)} of ±{model.get('max_score', 11)}", ""]
    for instr, label, dec in INSTRUMENTS:
        parts.append(instrument_block(instr, label, dec, scores["instruments"].get(instr, {}), vr, model, band))
        parts.append("")

    events = []
    for ev in load("events.json").get("events", []):
        if ev.get("impact") != "High":
            continue
        try:
            dt = datetime.fromisoformat(ev["date"]).astimezone(UK)
        except (KeyError, ValueError):
            continue
        if dt >= now and dt.date() == now.date():
            events.append(f"  ⚠ {dt:%H:%M} {escape(ev.get('country', ''))} {escape(ev.get('title', ''))}")
    parts.append("\U0001f4c5 <b>High-impact today (UK time)</b>")
    parts.extend(events[:6] or ["  none"])

    if page_url:
        parts.append(f"\n<a href=\"{escape(page_url, quote=True)}\">Dashboard</a> · "
                     f"<a href=\"{escape(page_url.rstrip('/') + '/tracker/', quote=True)}\">Options tracker</a>")
    parts.append("<i>Heuristic model output, not financial advice.</i>")
    return "\n".join(parts)


def send(token, chat_id, text):
    data = urllib.parse.urlencode({"chat_id": chat_id, "text": text, "parse_mode": "HTML",
                                   "disable_web_page_preview": "true"}).encode()
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendMessage", data=data, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read()).get("ok", False)
    except urllib.error.HTTPError as e:
        print(f"Telegram API error {e.code}: {e.read().decode()}")
        return False


def chunks(text):
    while len(text) > MAX_LEN:
        cut = text.rfind("\n\n", 0, MAX_LEN)
        cut = cut if cut > 0 else text.rfind("\n", 0, MAX_LEN)
        yield text[:cut]
        text = text[cut:].strip()
    yield text


def run():
    token = os.environ.get("TG_TOKEN") or os.environ.get("TELEGRAM_BOT_TOKEN")
    chat_id = os.environ.get("TG_CHAT") or os.environ.get("TELEGRAM_CHAT_ID")
    msg = build_message(os.environ.get("PAGE_URL", ""))
    if msg is None:
        print("No scores data — cannot build brief")
        return False
    if "--dry-run" in sys.argv or not token or not chat_id:
        print("Dry run or no Telegram secrets — printing instead:\n")
        print(msg)
        return True
    sent = sum(send(token, chat_id, part) for part in chunks(msg))
    print(f"Sent {sent} Telegram message(s)")
    return sent > 0


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
