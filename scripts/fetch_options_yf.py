"""
Fetch options chains from Yahoo Finance using ETF proxies:
  Gold   -> GLD  (SPDR Gold Trust)
  NAS100 -> QQQ  (Invesco QQQ Trust)
  EURUSD -> FXE  (Invesco CurrencyShares Euro Trust)

Selects the expiry with highest total open interest.
Computes PCR, max pain, put/call walls, magnet.
"""
import os, json, sys
from datetime import datetime

import yfinance as yf

INSTRUMENTS = {
    "Gold":   {"ticker": "GLD",  "note": "ETF proxy for Gold"},
    "NAS100": {"ticker": "QQQ",  "note": "ETF proxy for NAS100"},
    "EURUSD": {"ticker": "FXE",  "note": "ETF proxy for EURUSD"},
}
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")


def best_expiry(ticker):
    """Return the expiry date string with highest total open interest."""
    t = yf.Ticker(ticker)
    try:
        dates = t.options
    except Exception:
        return None, None, "no options data"
    if not dates:
        return None, None, "no option expirations"

    best_date = None
    best_chain = None
    best_oi = 0
    for d in dates:
        try:
            chain = t.option_chain(d)
        except Exception:
            continue
        tc = chain.calls["openInterest"].sum() if not chain.calls.empty else 0
        tp = chain.puts["openInterest"].sum() if not chain.puts.empty else 0
        total = int(tc) + int(tp)
        if total > best_oi:
            best_oi = total
            best_date = d
            best_chain = chain

    if best_date is None or best_oi == 0:
        return None, None, "zero open interest across all expiries"
    return best_date, best_chain, None


def compute_metrics(ticker, expiry, chain):
    calls = chain.calls
    puts = chain.puts

    spot = None
    t = yf.Ticker(ticker)
    info = {}
    try:
        info = t.info
    except Exception:
        pass
    spot = info.get("regularMarketPrice") or info.get("ask") or info.get("bid") or info.get("previousClose")

    # Total OI
    total_call_oi = int(calls["openInterest"].sum()) if not calls.empty and calls["openInterest"].notna().any() else 0
    total_put_oi = int(puts["openInterest"].sum()) if not puts.empty and puts["openInterest"].notna().any() else 0
    pcr = round(total_put_oi / total_call_oi, 4) if total_call_oi > 0 else None

    # Build strike_data from non-zero OI rows
    strike_data = {}
    for _, row in calls.iterrows():
        oi = row["openInterest"]
        if not oi or oi != oi or oi <= 0:
            continue
        s = int(row["strike"])
        strike_data.setdefault(s, {"call": 0, "put": 0})["call"] += int(oi)
    for _, row in puts.iterrows():
        oi = row["openInterest"]
        if not oi or oi != oi or oi <= 0:
            continue
        s = int(row["strike"])
        strike_data.setdefault(s, {"call": 0, "put": 0})["put"] += int(oi)

    # Max pain
    max_pain = None
    if strike_data:
        strikes = sorted(strike_data.keys())
        best_strike = None
        best_value = float("inf")
        for k in strikes:
            total_value = 0
            for s in strikes:
                if s > k:
                    total_value += (s - k) * strike_data[s]["call"]
                elif s < k:
                    total_value += (k - s) * strike_data[s]["put"]
            if total_value < best_value:
                best_value = total_value
                best_strike = k
        max_pain = best_strike

    # Walls
    call_wall = max(strike_data, key=lambda s: strike_data[s]["call"]) if strike_data else None
    put_wall = max(strike_data, key=lambda s: strike_data[s]["put"]) if strike_data else None

    # Magnet
    magnet = max(strike_data, key=lambda s: strike_data[s]["call"] + strike_data[s]["put"]) if strike_data else None

    # Skew (ATM implied vol skew)
    skew = None
    if spot and not calls.empty and not puts.empty:
        near_calls = calls.iloc[(calls["strike"] - spot).abs().argsort()[:5]]
        near_puts = puts.iloc[(puts["strike"] - spot).abs().argsort()[:5]]
        ac = near_calls["impliedVolatility"].mean()
        ap = near_puts["impliedVolatility"].mean()
        if ap and ap > 0:
            skew = round((ac - ap) / ap * 100, 2)
        else:
            skew = 0.0

    # Build full strike arrays for charting
    strikes_list = sorted(strike_data.keys()) if strike_data else []
    call_oi_list = [strike_data[s]["call"] for s in strikes_list]
    put_oi_list = [strike_data[s]["put"] for s in strikes_list]

    return {
        "expiry": expiry,
        "total_oi_used": total_call_oi + total_put_oi,
        "underlying_price": round(spot, 2) if spot else None,
        "put_call_ratio": pcr,
        "max_pain": max_pain,
        "call_wall": call_wall,
        "put_wall": put_wall,
        "magnet_strike": magnet,
        "skew_percent": skew,
        "n_calls_used": len(strike_data),
        "strikes": strikes_list,
        "call_oi": call_oi_list,
        "put_oi": put_oi_list,
    }


def run():
    print("Fetching options data from Yahoo Finance...")
    results = {}
    for instr, cfg in INSTRUMENTS.items():
        ticker = cfg["ticker"]
        print(f"  {instr} ({ticker})...", end=" ", flush=True)
        expiry, chain, err = best_expiry(ticker)
        if err:
            results[instr] = {"error": err}
            print(f"ERROR: {err}")
            continue
        data = compute_metrics(ticker, expiry, chain)
        data["proxy_for"] = ticker
        data["proxy_note"] = cfg["note"]
        results[instr] = data
        print(f"OK — expiry={expiry}, OI={data['total_oi_used']}, PCR={data['put_call_ratio']}, spot={data['underlying_price']}")

    out_path = os.path.join(DATA_DIR, "ome_data.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return True


if __name__ == "__main__":
    run()
