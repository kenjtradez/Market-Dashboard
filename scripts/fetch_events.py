"""
Fetch economic calendar events from ForexFactory free JSON feed.
"""
import os, json, requests
from datetime import datetime, timezone, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Countries/currencies relevant to our instruments
RELEVANT_COUNTRIES = {"USD", "EUR", "GBP", "JPY", "CHF", "AUD", "CAD", "NZD", "CNY"}

IMPACT_ORDER = {"High": 0, "Medium": 1, "Low": 2}

def load_events():
    url = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
    try:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"  ERROR fetching events: {e}")
        return []

def filter_and_sort(events):
    now = datetime.now(timezone.utc)
    # Only future events (up to 7 days ahead)
    start = now
    end = now + timedelta(days=7)

    filtered = []
    for ev in events:
        try:
            dt_str = ev.get("date", "")
            if not dt_str:
                continue
            ev_dt = datetime.fromisoformat(dt_str)
            if not (start <= ev_dt <= end):
                continue
        except:
            continue

        country = ev.get("country", "")
        if country not in RELEVANT_COUNTRIES:
            continue

        filtered.append({
            "title": ev.get("title", ""),
            "country": country,
            "date": dt_str,
            "impact": ev.get("impact", "Low"),
            "forecast": ev.get("forecast", ""),
            "previous": ev.get("previous", ""),
        })

    filtered.sort(key=lambda x: (x["date"], IMPACT_ORDER.get(x["impact"], 99)))
    return filtered

def run():
    print("Fetching economic calendar events...")
    raw = load_events()
    if not raw:
        print("  No events fetched")
        return False

    events = filter_and_sort(raw)
    print(f"  Loaded {len(raw)} raw, filtered to {len(events)} relevant events")

    out_path = os.path.join(DATA_DIR, "events.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "events": events}, f, indent=2)
    print(f"  Saved to {out_path}")
    return True

if __name__ == "__main__":
    run()
