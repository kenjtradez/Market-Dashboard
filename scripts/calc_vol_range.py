"""
Calculate Vol & Range Forecast.
Priority: 1) forecast_history.csv in screenshots/  2) yfinance auto-calc
"""
import os, json, csv
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
SCREENSHOT_DIR = os.path.join(os.path.dirname(__file__), "..", "screenshots")

TICKERS = {
    "Gold":   {"ticker": "GC=F",   "name": "Gold Futures"},
    "NAS100": {"ticker": "NQ=F",   "name": "NASDAQ 100 Futures"},
    "EURUSD": {"ticker": "6E=F",   "name": "Euro FX Futures"},
}

ASSET_ALIASES = {
    "gold": "Gold", "GOLD": "Gold", "Gold": "Gold",
    "nas100": "NAS100", "NAS100": "NAS100", "NQ": "NAS100", "nq": "NAS100",
    "eurusd": "EURUSD", "EURUSD": "EURUSD",
}

def parse_csv(csv_path):
    """Parse forecast_history.csv, return latest row per instrument."""
    results = {}
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            asset_raw = row.get("asset", "").strip()
            asset = ASSET_ALIASES.get(asset_raw)
            if not asset:
                continue
            try:
                entry = {
                    "date": row.get("date", "").strip(),
                    "volatility_annualized": float(row.get("volatility", 0)),
                    "high_low_range_median": float(row.get("high_to_low_median", 0)),
                    "high_low_range_p75": float(row.get("high_to_low_75th", 0)),
                    "open_close_median": float(row.get("open_to_close_median", 0)),
                    "open_close_p75": float(row.get("open_to_close_75th", 0)),
                }
                if asset not in results:
                    results[asset] = entry
                else:
                    existing_date = results[asset].get("date", "")
                    if entry["date"] > existing_date:
                        results[asset] = entry
            except (ValueError, KeyError):
                continue
    return results

def calc_from_yfinance():
    """Fallback: compute from yfinance 20-day rolling window."""
    print("  Falling back to yfinance calculation...")
    today = datetime.now()
    start_date = (today - timedelta(days=60)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    instruments = {}
    for instr, info in TICKERS.items():
        ticker = info["ticker"]
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        except Exception as e:
            print(f"    ERROR: {e}")
            continue

        if df.empty:
            continue

        df = df.tail(20)
        if len(df) < 5:
            continue

        hl_ranges, oc_moves, daily_returns = [], [], []
        for i in range(len(df)):
            row = df.iloc[i]
            if isinstance(df.columns, pd.MultiIndex):
                o = float(row[("Open", ticker)])
                h = float(row[("High", ticker)])
                l = float(row[("Low", ticker)])
                c = float(row[("Close", ticker)])
            else:
                o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
            if o == 0:
                continue
            hl_ranges.append((h - l) / o * 100)
            oc_moves.append(abs(c - o) / o * 100)
            if i > 0:
                prev_row = df.iloc[i-1]
                if isinstance(df.columns, pd.MultiIndex):
                    prev_c = float(prev_row[("Close", ticker)])
                else:
                    prev_c = float(prev_row["Close"])
                if prev_c != 0:
                    daily_returns.append((c - prev_c) / prev_c)

        hl_median = float(np.median(hl_ranges)) if hl_ranges else None
        hl_p75 = float(np.percentile(hl_ranges, 75)) if hl_ranges else None
        oc_median = float(np.median(oc_moves)) if oc_moves else None
        oc_p75 = float(np.percentile(oc_moves, 75)) if oc_moves else None
        vol = float(np.std(daily_returns, ddof=1) * np.sqrt(252) * 100) if len(daily_returns) > 1 else None

        instruments[instr] = {
            "volatility_annualized": round(vol, 2) if vol else None,
            "high_low_range_median": round(hl_median, 2) if hl_median else None,
            "high_low_range_p75": round(hl_p75, 2) if hl_p75 else None,
            "open_close_median": round(oc_median, 2) if oc_median else None,
            "open_close_p75": round(oc_p75, 2) if oc_p75 else None,
        }
    return instruments

def run():
    print("Calculating Vol & Range Forecast...")

    csv_path = os.path.join(SCREENSHOT_DIR, "forecast_history.csv")
    if os.path.exists(csv_path):
        print(f"  Found {csv_path} — parsing CSV...")
        instruments = parse_csv(csv_path)
        if instruments:
            print(f"  Loaded from CSV: {list(instruments.keys())}")
            for instr, v in instruments.items():
                print(f"    {instr}: Vol={v['volatility_annualized']}% HL={v['high_low_range_median']}%/{v['high_low_range_p75']}%")
        else:
            instruments = calc_from_yfinance()
    else:
        instruments = calc_from_yfinance()

    today = datetime.now()
    weekday = today.strftime("%A").upper()
    date_str = today.strftime("%B %d, %Y")

    output = {
        "date": today.strftime("%Y-%m-%d"),
        "session": f"{weekday}, {date_str}",
        "instruments": instruments,
    }

    out_path = os.path.join(DATA_DIR, "vol_range.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\nSaved to {out_path}")
    return True

if __name__ == "__main__":
    run()
