"""
Daily bias written by Claude from everything the pipeline has collected:
model scores, Band Read, COT, macro, options levels, vol ranges, the
calendar and headlines. Output is data/daily_bias.json, shown on the
dashboard and in the Telegram brief.

Only runs when RUN_DAILY_BIAS=true (the workflow sets it on brief runs) or
with --force, and needs ANTHROPIC_API_KEY. `--dry-run` builds and prints
the request without calling the API.
"""
import os, sys, json
from datetime import datetime
from zoneinfo import ZoneInfo

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
UK = ZoneInfo("Europe/London")
MODEL = "claude-opus-5"
INSTRUMENTS = ["Gold", "NAS100", "SPX500", "US2000", "EURUSD", "USDJPY"]

SYSTEM = """You are the desk analyst for a personal trading dashboard covering Gold, NAS100, S&P 500, Russell 2000, EUR/USD and USD/JPY. Each run you receive everything the dashboard's pipeline collected, as JSON, and write the bias for the rest of the current session (the session ends 17:00 New York, 22:00 UK in summer).

Ground rules:
- Use only the data provided. Do not add outside news, prices or events; if something matters but is missing, say it is missing.
- The trader reads this on a phone before trading. Be direct and brief; name concrete levels from the data (bands, walls, projected close range) where they help.
- None of these inputs is a backtested signal. The model score is a heuristic; Band Read and the projected range are historical base rates; the trader's own tests found no edge in price-only intraday rules. So: say "Neutral" when evidence is mixed or weak, and reserve "High" confidence for cases where several independent inputs (options positioning, COT extreme, macro, Band Read versus a normal day) point the same way and are not marginal. Most days most instruments should be Neutral or Mild with Low confidence; that is the honest answer, not a failure.
- COT only matters at extremes and is read contrarian (crowded long is a headwind). USD/JPY's COT is inverted (crowded long yen is a tailwind for USD/JPY).
- Band Read numbers depend on the time of day in `now_uk`; the projected close range is a spread, not a target.
- Mention scheduled high-impact events still ahead today, since they can override everything else."""

SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string", "description": "Two or three sentences on the backdrop and the day's main theme."},
        "instruments": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "instrument": {"type": "string", "enum": INSTRUMENTS},
                    "bias": {"type": "string", "enum": ["Up", "Mild up", "Neutral", "Mild down", "Down"]},
                    "confidence": {"type": "string", "enum": ["Low", "Medium", "High"]},
                    "reason": {"type": "string", "description": "One or two sentences citing the inputs that drive the bias."},
                    "levels": {"type": "string", "description": "Key levels to watch today, from the data."},
                },
                "required": ["instrument", "bias", "confidence", "reason", "levels"],
                "additionalProperties": False,
            },
        },
        "events": {"type": "string", "description": "High-impact events still ahead today, or 'None left today'."},
    },
    "required": ["overall", "instruments", "events"],
    "additionalProperties": False,
}


def load(name):
    p = os.path.join(DATA_DIR, name)
    if os.path.exists(p):
        with open(p) as f:
            return json.load(f)
    return {}


def slim_bundle():
    """The pipeline's data, minus bulky arrays the analysis doesn't need
    (OI by strike, 52-week COT history, full headline lists)."""
    scores = load("scores.json")
    for v in scores.get("instruments", {}).values():
        ome = v.pop("ome_data", {}) or {}
        v["options"] = {k: ome.get(k) for k in ("as_of", "expiry", "dte", "underlying_price", "put_call_ratio",
                                                "call_wall", "put_wall", "max_pain", "magnet_strike",
                                                "gamma_flip", "exp_high", "exp_low", "error")
                        if ome.get(k) is not None}
    cot = load("cot_data.json").get("instruments", {})
    for v in cot.values():
        v.pop("history", None)
    band = load("band_read.json").get("instruments", {})
    for v in band.values():
        for s in (v.get("sides") or {}).values():
            s.pop("reached_med", None), s.pop("reached_p75", None)
    geo = load("geopolitical.json")
    now = datetime.now(UK)
    events = [e for e in load("events.json").get("events", [])
              if e.get("impact") in ("High", "Medium")]
    return {
        "now_uk": now.strftime("%A %d %B %Y, %H:%M"),
        "scores": scores,
        "band_read": band,
        "cot": cot,
        "macro": load("fred_macro.json").get("series", {}),
        "vol_range": load("vol_range.json").get("instruments", {}),
        "calendar_next_7_days_ny_time": events[:25],
        "headlines": {
            "risk_articles": [a["title"] for a in geo.get("articles", [])[:10]],
            "by_instrument": {i: [h["title"] for h in geo.get("headlines", []) if i in h.get("instruments", [])][:5]
                              for i in INSTRUMENTS},
        },
        "headline_sentiment": load("sentiment.json").get("instruments", {}),
    }


def request(bundle):
    return dict(
        model=MODEL,
        max_tokens=16000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",   # re-run on Anthropic's recommended model if Opus 5 declines
        output_config={"effort": "medium",
                       "format": {"type": "json_schema", "schema": SCHEMA}},
        system=SYSTEM,
        messages=[{"role": "user", "content": "Pipeline data for this run:\n\n" + json.dumps(bundle, default=str)}],
    )


def run():
    forced = "--force" in sys.argv or "--dry-run" in sys.argv
    if not forced and os.environ.get("RUN_DAILY_BIAS") != "true":
        print("Daily bias: not a brief run — skipped")
        return True
    req = request(slim_bundle())
    if "--dry-run" in sys.argv:
        print(f"Dry run: {len(req['messages'][0]['content']):,} characters of data; model {MODEL}")
        print(req["messages"][0]["content"][:1500])
        return True
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Daily bias: ANTHROPIC_API_KEY not set — skipped")
        return False

    import anthropic
    client = anthropic.Anthropic()
    try:
        resp = client.beta.messages.create(**req)
    except anthropic.RateLimitError as e:
        print(f"Daily bias: rate limited ({e.message})")
        return False
    except anthropic.APIStatusError as e:
        print(f"Daily bias: API error {e.status_code}: {e.message}")
        return False
    except anthropic.APIConnectionError as e:
        print(f"Daily bias: connection error: {e}")
        return False

    if resp.stop_reason != "end_turn":
        print(f"Daily bias: stopped with {resp.stop_reason} — not saved (request {resp._request_id})")
        return False
    text = next((b.text for b in resp.content if b.type == "text"), None)
    if not text:
        print("Daily bias: no text in response — not saved")
        return False
    out = json.loads(text)
    out.update({"generated": datetime.now(UK).isoformat(timespec="minutes"), "model": resp.model,
                "usage": {"input_tokens": resp.usage.input_tokens, "output_tokens": resp.usage.output_tokens}})
    with open(os.path.join(DATA_DIR, "daily_bias.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"Daily bias written by {resp.model} ({resp.usage.input_tokens} in / {resp.usage.output_tokens} out tokens)")
    for i in out["instruments"]:
        print(f"  {i['instrument']}: {i['bias']} ({i['confidence']})")
    return True


if __name__ == "__main__":
    sys.exit(0 if run() else 1)
