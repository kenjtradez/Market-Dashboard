"""
Fetch options chains from Yahoo Finance using ETF proxies:
  Gold   -> GLD  (SPDR Gold Trust)
  NAS100 -> QQQ  (Invesco QQQ Trust)
  EURUSD -> FXE  (Invesco CurrencyShares Euro Trust)

The options CHAIN itself has to come from these ETFs — there's no free
retail-accessible spot-gold or spot-index options chain. But the price used
to scale strikes/walls/spot up to "real" terms previously targeted GC=F
(COMEX gold FUTURES) and NQ=F (Nasdaq-100 FUTURES), not the actual spot
price — futures carry a basis that's a different number from true spot.

Gold price sourcing tries multiple candidates in order, since a single
untested ticker guess already failed once (yfinance's "XAUUSD=X" returns a
clean 404 — confirmed via a real workflow run, not just theory):
  1. gold-api.com — a dedicated free spot-gold API, no key required. This is
     the SAME source the abandoned gold-forecast.html tool used successfully
     for its live price, so it's proven to work, just never wired into this
     pipeline before now.
  2. yfinance "XAU=X" — a plausible alternate Yahoo spot-gold ticker format,
     unverified but worth trying since it costs nothing to attempt.
  3. yfinance "GC=F" (COMEX futures) — the original, CONFIRMED-working
     fallback. Not true spot (carries a small futures basis) but far better
     than nothing if both spot sources fail.
Each candidate is tried in order; first one that returns a price wins.
NAS100 and EURUSD keep a simpler two-candidate chain (spot ticker, then the
original futures/FX fallback).

Selects the expiry with highest total open interest.
Computes PCR, max pain, put/call walls, magnet.
"""
import os, json, sys
from datetime import datetime

import requests
import yfinance as yf

# Each instrument's price candidates, tried in order. ("yf", ticker) uses
# yfinance; ("http_json", url, json_key) does a plain GET and reads a key
# from the JSON response — used for gold-api.com, which isn't a yfinance
# ticker at all.
PRICE_CANDIDATES = {
    "Gold": [
        ("http_json", "https://api.gold-api.com/price/XAU", "price"),
        ("yf", "XAU=X"),
        ("yf", "GC=F"),
    ],
    "NAS100": [
        ("yf", "^NDX"),
        ("yf", "NQ=F"),
    ],
    "EURUSD": [
        ("yf", "EURUSD=X"),
    ],
}

INSTRUMENTS = {
    "Gold":   {"ticker": "GLD", "note": "ETF proxy for Gold, scaled to spot XAU/USD"},
    "NAS100": {"ticker": "QQQ", "note": "ETF proxy for NAS100, scaled to spot NDX index"},
    "EURUSD": {"ticker": "FXE", "note": "ETF proxy for EURUSD, scaled to spot EUR/USD"},
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


def _fetch_price_yf(ticker):
    try:
        info = yf.Ticker(ticker).info
        return info.get("regularMarketPrice") or info.get("ask") or info.get("bid") or info.get("previousClose")
    except Exception as e:
        print(f"    yfinance {ticker} failed: {e}")
        return None


def _fetch_price_http_json(url, json_key, timeout=10):
    try:
        r = requests.get(url, timeout=timeout)
        r.raise_for_status()
        val = r.json().get(json_key)
        return float(val) if val is not None else None
    except Exception as e:
        print(f"    HTTP {url} failed: {e}")
        return None


def _fetch_price_candidates(candidates):
    """Try each (type, ...) candidate in order, return (price, source_label)
    for the first one that succeeds, or (None, None) if all fail."""
    for cand in candidates:
        kind = cand[0]
        if kind == "yf":
            price = _fetch_price_yf(cand[1])
            if price:
                return price, cand[1]
        elif kind == "http_json":
            price = _fetch_price_http_json(cand[1], cand[2])
            if price:
                return price, cand[1]
    return None, None


def scale_to_futures(data, etf_ticker, candidates):
    """Scale ETF strikes/prices to real-instrument levels, trying each price
    candidate in order (see PRICE_CANDIDATES) until one succeeds. Spot
    sources are preferred but a futures-based scale is still far better than
    leaving the data unscaled entirely."""
    if "error" in data:
        return data
    etf_price = data.get("underlying_price")
    if not etf_price:
        return data

    real_price, used_source = _fetch_price_candidates(candidates)
    if not real_price:
        return data
    ratio = real_price / etf_price

    scaled = dict(data)
    scaled["underlying_price"] = round(real_price, 2)
    scaled["proxy_for"] = etf_ticker
    scaled["proxy_note"] = f"ETF proxy for {used_source}, scaled by {ratio:.2f}x"
    scaled["scale_ratio"] = round(ratio, 4)
    scaled["scale_source"] = used_source

    for field in ["max_pain", "call_wall", "put_wall", "magnet_strike"]:
        val = data.get(field)
        if val is not None:
            scaled_val = val * ratio
            scaled[field] = round(scaled_val, 4) if abs(scaled_val) < 100 else round(scaled_val)

    raw_strikes = data.get("strikes", [])
    if raw_strikes:
        scaled["strikes"] = [round(s * ratio, 4) if abs(ratio * s) < 100 else round(s * ratio) for s in raw_strikes]

    # Add raw (unscaled) data for reference
    scaled["raw_price"] = round(etf_price, 2)
    scaled["raw_strikes"] = raw_strikes
    return scaled


def run():
    print("Fetching options data from Yahoo Finance...")
    results = {}
    all_ok = True
    for instr, cfg in INSTRUMENTS.items():
        ticker = cfg["ticker"]
        print(f"  {instr} ({ticker})...", end=" ", flush=True)
        expiry, chain, err = best_expiry(ticker)
        if err:
            results[instr] = {"error": err}
            print(f"ERROR: {err}")
            all_ok = False
            continue
        data = compute_metrics(ticker, expiry, chain)
        data["proxy_for"] = ticker
        data["proxy_note"] = cfg["note"]
        # Scale ETF strikes to real-instrument levels, trying each price
        # candidate in order (spot sources preferred, futures as last resort)
        if "error" not in data:
            data = scale_to_futures(data, ticker, PRICE_CANDIDATES[instr])
        results[instr] = data
        sp = data.get("underlying_price", "?")
        src = data.get("scale_source", "unscaled")
        print(f"OK — expiry={expiry}, OI={data['total_oi_used']}, PCR={data['put_call_ratio']}, spot={sp} (via {src})")

    out_path = os.path.join(DATA_DIR, "ome_data.json")
    if not all_ok and os.path.exists(out_path):
        existing = json.load(open(out_path))
        # merge: keep existing data for failed instruments
        for instr in INSTRUMENTS:
            if instr in results and "error" in results[instr]:
                if instr in existing.get("instruments", {}) and "error" not in existing["instruments"][instr]:
                    results[instr] = existing["instruments"][instr]
                    print(f"  Kept existing data for {instr}")
                else:
                    del results[instr]
        if not results:
            print("  All instruments failed, preserving existing file")
            return True
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return True


if __name__ == "__main__":
    run()
