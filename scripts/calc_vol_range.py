"""
Calculate Vol & Range Forecast from 1 year of daily OHLC data.
Uses yfinance for futures prices.
"""
import os, json, sys
import pandas as pd
import yfinance as yf
import numpy as np
from datetime import datetime, timedelta

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

TICKERS = {
    "Gold":   {"ticker": "GC=F",   "name": "Gold Futures"},
    "NAS100": {"ticker": "NQ=F",   "name": "NASDAQ 100 Futures"},
    "EURUSD": {"ticker": "6E=F",   "name": "Euro FX Futures"},
}

def annualized_vol(daily_returns):
    """Annualized volatility from daily returns."""
    if len(daily_returns) < 2:
        return None
    return float(np.std(daily_returns, ddof=1) * np.sqrt(252) * 100)

def percentile_stats(values):
    """Return median and 75th percentile of a list of percentages."""
    if not values:
        return None, None
    arr = np.array(values)
    return float(np.median(arr)), float(np.percentile(arr, 75))

def run():
    print("Calculating Vol & Range Forecast from 1 year of daily data...")

    today = datetime.now()
    start_date = (today - timedelta(days=400)).strftime("%Y-%m-%d")
    end_date = today.strftime("%Y-%m-%d")

    instruments = {}
    for instr, info in TICKERS.items():
        ticker = info["ticker"]
        print(f"  Fetching {ticker} ({instr})...")
        try:
            df = yf.download(ticker, start=start_date, end=end_date, progress=False)
        except Exception as e:
            print(f"    ERROR downloading {ticker}: {e}")
            continue

        if df.empty:
            print(f"    No data for {ticker}")
            continue

        # Use last 365 trading days
        df = df.tail(365)
        if len(df) < 20:
            print(f"    Insufficient data: {len(df)} rows")
            continue

        # Daily HL range %
        hl_ranges = []
        oc_moves = []
        daily_returns = []

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

        hl_median, hl_p75 = percentile_stats(hl_ranges)
        oc_median, oc_p75 = percentile_stats(oc_moves)
        vol = annualized_vol(daily_returns)

        instruments[instr] = {
            "volatility_annualized": round(vol, 2) if vol is not None else None,
            "high_low_range_median": round(hl_median, 2) if hl_median is not None else None,
            "high_low_range_p75": round(hl_p75, 2) if hl_p75 is not None else None,
            "open_close_median": round(oc_median, 2) if oc_median is not None else None,
            "open_close_p75": round(oc_p75, 2) if oc_p75 is not None else None,
        }
        print(f"    Vol={instruments[instr]['volatility_annualized']}%  HL={instruments[instr]['high_low_range_median']}%/{instruments[instr]['high_low_range_p75']}%  OC={instruments[instr]['open_close_median']}%/{instruments[instr]['open_close_p75']}%")

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
    print(f"\nSaved Vol & Range forecast to {out_path}")
    return True

if __name__ == "__main__":
    run()
