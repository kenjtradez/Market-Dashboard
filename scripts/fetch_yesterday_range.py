"""Fetch yesterday's max % move from open and project onto today's price."""
import os, json
from datetime import datetime, timedelta, timezone

import yfinance as yf

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
OUT_PATH = os.path.join(DATA_DIR, "yesterday_range.json")

INSTRUMENTS = {
    "Gold":        ("GLD", "XAU/USD"),
    "NAS100":      ("QQQ", "US100"),
    "EURUSD":      ("FXE", "EUR/USD"),
}

def fetch():
    results = {}
    for name, (ticker, label) in INSTRUMENTS.items():
        try:
            t = yf.Ticker(ticker)
            hist = t.history(period="4d")
            if len(hist) < 2:
                results[name] = {"error": "not enough history"}
                continue
            yesterday = hist.iloc[-2]
            today = hist.iloc[-1]
            y_open = yesterday["Open"]
            y_high = yesterday["High"]
            y_low = yesterday["Low"]
            t_open = today["Open"]
            t_close = today.get("Close", t_open)

            up_pct = ((y_high - y_open) / y_open) * 100
            dn_pct = ((y_low - y_open) / y_open) * 100
            max_pct = max(abs(up_pct), abs(dn_pct))
            direction = "high" if abs(up_pct) >= abs(dn_pct) else "low"

            results[name] = {
                "ticker": ticker,
                "label": label,
                "date": str(yesterday.name.date()),
                "y_open": round(y_open, 2),
                "y_high": round(y_high, 2),
                "y_low": round(y_low, 2),
                "up_pct": round(up_pct, 2),
                "dn_pct": round(dn_pct, 2),
                "max_pct": round(max_pct, 2),
                "direction": direction,
                "t_open": round(t_open, 2),
                "t_close": round(t_close, 2),
                "projected_up": round(t_open * (1 + max_pct / 100), 2),
                "projected_down": round(t_open * (1 - max_pct / 100), 2),
                "generated": datetime.now(timezone.utc).isoformat(),
            }
        except Exception as e:
            results[name] = {"error": str(e)}

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"Yesterday range written to {OUT_PATH}")

if __name__ == "__main__":
    fetch()
