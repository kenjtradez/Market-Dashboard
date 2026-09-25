"""
Fetch options chains from Yahoo Finance via ETF proxies and derive levels:
  Gold   -> GLD, scaled to spot XAU/USD
  NAS100 -> QQQ, scaled to the NDX index
  EURUSD -> FXE, scaled to spot EUR/USD

Expiry: the highest-open-interest expiry within 3-45 days (the front-month
window). Picking the highest-OI expiry overall selected LEAPS months out,
whose walls sit far from where price trades day to day.

Outputs, per instrument: PCR, max pain, call/put walls (largest OI strike),
magnet (largest combined OI), ATM IV skew, 5%-OTM skew, a gamma-flip level
(only if cumulative dealer GEX actually crosses zero), net GEX, a 1-day
expected range from ATM IV, and the full OI-by-strike profile. All price
levels are scaled from ETF to instrument terms using a spot price fetched
at the same time.
"""
import os, json, math
from datetime import datetime, date

import requests
import yfinance as yf

PRICE_CANDIDATES = {
    "Gold":   [("http_json", "https://api.gold-api.com/price/XAU", "price"), ("yf", "GC=F")],
    "NAS100": [("yf", "^NDX"), ("yf", "NQ=F")],
    "EURUSD": [("yf", "EURUSD=X")],
}
INSTRUMENTS = {"Gold": "GLD", "NAS100": "QQQ", "EURUSD": "FXE"}
# Instruments with no usable options proxy (FXY is thinner than FXE): only a
# spot price is recorded so price-based sections still work.
PRICE_ONLY = {"USDJPY": [("yf", "JPY=X")]}
MIN_DTE, MAX_DTE = 3, 45
RISK_FREE = 0.05
DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Yahoo zeroes most open interest outside US market hours, so a chain is
# only trusted when enough strikes carry OI and the total is meaningful.
# Otherwise the previous good snapshot is kept (see run()). Minimums are per
# ETF, sized to each market: a normal front-month GLD chain carries ~500k OI
# and QQQ ~900k. FXE's entire chain is a few thousand contracts, so it
# effectively never passes. A PCR of 13 on 5.6k contracts once drove EUR/USD
# to SHORT on noise.
MIN_OI_COVERAGE = 0.25
MIN_TOTAL_OI = {"GLD": 100_000, "QQQ": 200_000, "FXE": 50_000}


def pick_expiry(t):
    """Return (expiry, chain, dte) for the highest-OI trustworthy expiry in the front-month window."""
    today = date.today()
    dates = list(t.options or [])
    if not dates:
        raise RuntimeError("no option expirations")
    window = [d for d in dates if MIN_DTE <= (date.fromisoformat(d) - today).days <= MAX_DTE]
    best, best_seen = None, 0
    for d in window:
        try:
            chain = t.option_chain(d)
        except Exception:
            continue
        oi_col = [chain.calls["openInterest"].fillna(0), chain.puts["openInterest"].fillna(0)]
        n_rows = sum(len(c) for c in oi_col)
        oi = int(sum(c.sum() for c in oi_col))
        coverage = sum(int((c > 0).sum()) for c in oi_col) / n_rows if n_rows else 0
        best_seen = max(best_seen, oi)
        if coverage < MIN_OI_COVERAGE:
            continue
        if best is None or oi > best[3]:
            best = (d, chain, (date.fromisoformat(d) - today).days, oi)
    min_oi = MIN_TOTAL_OI.get(t.ticker, 100_000)
    if best is None or best[3] < min_oi:
        raise RuntimeError(f"open interest too thin or unpublished (max {best_seen} in {MIN_DTE}-{MAX_DTE}d window, need {min_oi:,})")
    return best[0], best[1], max(best[2], 0.5)


def bs_gamma(S, K, T, sigma):
    if not (S > 0 and K > 0 and T > 0 and sigma and sigma > 0):
        return None
    d1 = (math.log(S / K) + (RISK_FREE + sigma * sigma / 2) * T) / (sigma * math.sqrt(T))
    return math.exp(-d1 * d1 / 2) / math.sqrt(2 * math.pi) / (S * sigma * math.sqrt(T))


def rows(df, kind):
    out = []
    for _, r in df.iterrows():
        oi = r.get("openInterest")
        oi = 0 if oi is None or oi != oi else int(oi)
        iv = r.get("impliedVolatility")
        iv = None if iv is None or iv != iv or iv <= 0.0001 else float(iv)
        out.append({"strike": round(float(r["strike"]), 2), "type": kind, "oi": oi, "iv": iv})
    return out


def compute_metrics(chain, spot, dte):
    contracts = rows(chain.calls, "call") + rows(chain.puts, "put")
    by_strike = {}
    for c in contracts:
        if c["oi"] > 0:
            by_strike.setdefault(c["strike"], {"call": 0, "put": 0})[c["type"]] += c["oi"]
    if not by_strike:
        raise RuntimeError("no strikes with open interest")
    strikes = sorted(by_strike)
    call_oi = sum(v["call"] for v in by_strike.values())
    put_oi = sum(v["put"] for v in by_strike.values())

    max_pain = min(strikes, key=lambda k: sum(
        (s - k) * v["call"] if s > k else (k - s) * v["put"] for s, v in by_strike.items()))
    call_wall = max(strikes, key=lambda s: by_strike[s]["call"])
    put_wall = max(strikes, key=lambda s: by_strike[s]["put"])
    magnet = max(strikes, key=lambda s: by_strike[s]["call"] + by_strike[s]["put"])

    def nearest_iv(kind, target, n=1):
        pool = sorted((c for c in contracts if c["type"] == kind and c["iv"]), key=lambda c: abs(c["strike"] - target))
        pool = pool[:n]
        return sum(c["iv"] for c in pool) / len(pool) if pool else None

    atm_call, atm_put = nearest_iv("call", spot, 5), nearest_iv("put", spot, 5)
    skew_pct = round((atm_call - atm_put) / atm_put * 100, 2) if atm_call and atm_put else None
    otm_call, otm_put = nearest_iv("call", spot * 1.05), nearest_iv("put", spot * 0.95)
    otm_skew = round(otm_call - otm_put, 4) if otm_call and otm_put else None

    # Dealer GEX sign convention: dealers long calls / short puts.
    T = dte / 365
    gex = {}
    for c in contracts:
        g = bs_gamma(spot, c["strike"], T, c["iv"])
        if g is None or not c["oi"]:
            continue
        v = g * c["oi"] * 100 * spot * spot * 0.01
        gex[c["strike"]] = gex.get(c["strike"], 0) + (v if c["type"] == "call" else -v)
    flip, cum = None, 0.0
    for s in sorted(gex):
        prev, cum = cum, cum + gex[s]
        if flip is None and prev < 0 <= cum:
            flip = s

    atm_iv = nearest_iv("call", spot) or nearest_iv("put", spot)
    move = spot * atm_iv * math.sqrt(1 / 365) if atm_iv else None

    return {
        "total_oi_used": call_oi + put_oi,
        "put_call_ratio": round(put_oi / call_oi, 4) if call_oi else None,
        "max_pain": max_pain, "call_wall": call_wall, "put_wall": put_wall, "magnet_strike": magnet,
        "gamma_flip": flip, "net_gex": round(sum(gex.values())) if gex else None,
        "skew_percent": skew_pct, "otm_skew": otm_skew,
        "exp_high": spot + move if move else None, "exp_low": spot - move if move else None,
        "strikes": strikes,
        "call_oi": [by_strike[s]["call"] for s in strikes],
        "put_oi": [by_strike[s]["put"] for s in strikes],
    }


def fetch_price(candidates):
    for cand in candidates:
        try:
            if cand[0] == "yf":
                info = yf.Ticker(cand[1]).info
                p = info.get("regularMarketPrice") or info.get("previousClose")
            else:
                r = requests.get(cand[1], timeout=10)
                r.raise_for_status()
                p = r.json().get(cand[2])
            if p:
                return float(p), cand[1]
        except Exception as e:
            print(f"    price source {cand[1]} failed: {e}")
    return None, None


def scale(value, ratio):
    if value is None:
        return None
    v = value * ratio
    return round(v, 5) if abs(v) < 100 else round(v, 1)


def fetch_instrument(instr, etf):
    t = yf.Ticker(etf)
    info = t.info
    etf_px = info.get("regularMarketPrice") or info.get("previousClose")
    if not etf_px:
        raise RuntimeError(f"no {etf} price")
    expiry, chain, dte = pick_expiry(t)
    m = compute_metrics(chain, float(etf_px), dte)
    # Sparse OI puts max pain and the walls far from price; a front-month
    # max pain more than 20% away means the chain isn't trustworthy.
    if abs(m["max_pain"] / etf_px - 1) > 0.20:
        raise RuntimeError(f"max pain {m['max_pain']} is >20% from {etf} {etf_px}; chain looks unreliable")

    real_px, src = fetch_price(PRICE_CANDIDATES[instr])
    ratio = real_px / etf_px if real_px else 1.0
    out = {
        "as_of": datetime.now().isoformat(timespec="minutes"),
        "expiry": expiry, "dte": dte, "proxy_for": etf,
        "raw_price": round(etf_px, 2),
        "underlying_price": round(real_px, 5 if real_px and real_px < 100 else 2) if real_px else round(etf_px, 2),
        "scale_ratio": round(ratio, 6), "scale_source": src or "unscaled",
        "total_oi_used": m["total_oi_used"], "put_call_ratio": m["put_call_ratio"],
        "skew_percent": m["skew_percent"], "otm_skew": m["otm_skew"], "net_gex": m["net_gex"],
        "raw_strikes": m["strikes"], "call_oi": m["call_oi"], "put_oi": m["put_oi"],
    }
    for k in ("max_pain", "call_wall", "put_wall", "magnet_strike", "gamma_flip", "exp_high", "exp_low"):
        out[k] = scale(m[k], ratio)
    out["strikes"] = [scale(s, ratio) for s in m["strikes"]]
    return out


def run():
    print("Fetching options data from Yahoo Finance...")
    out_path = os.path.join(DATA_DIR, "ome_data.json")
    previous = {}
    if os.path.exists(out_path):
        with open(out_path) as f:
            previous = json.load(f).get("instruments", {})

    results, ok = {}, True
    for instr, etf in INSTRUMENTS.items():
        try:
            results[instr] = fetch_instrument(instr, etf)
            d = results[instr]
            print(f"  {instr} ({etf}): exp {d['expiry']} ({d['dte']}d), OI {d['total_oi_used']}, PCR {d['put_call_ratio']}, "
                  f"walls C{d['call_wall']}/P{d['put_wall']}, spot {d['underlying_price']} via {d['scale_source']}")
        except Exception as e:
            ok = False
            print(f"  {instr} ({etf}): ERROR {e}")
            prev = previous.get(instr, {})
            if "error" not in prev and prev.get("as_of") and prev.get("total_oi_used", 0) >= MIN_TOTAL_OI.get(etf, 100_000):
                results[instr] = dict(prev, carried_over=True)
                print(f"    kept previous snapshot from {prev['as_of']}")
            else:
                # Keep a spot price even without options so price-based
                # sections (vol/range ideas) still work.
                px, src = fetch_price(PRICE_CANDIDATES[instr])
                results[instr] = {"error": str(e), "underlying_price": px, "scale_source": src}

    for instr, candidates in PRICE_ONLY.items():
        px, src = fetch_price(candidates)
        results[instr] = {"error": "no liquid options proxy", "underlying_price": px, "scale_source": src}

    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    return ok


if __name__ == "__main__":
    run()
