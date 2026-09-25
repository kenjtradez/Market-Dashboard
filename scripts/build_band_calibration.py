"""
Build the Band Read probability tables from 1-minute price history.

Not part of the scheduled pipeline: it needs years of minute data that
isn't in this repo. Run it locally when you want to refresh the tables:

    python scripts/build_band_calibration.py "C:/path/to/raw data"

and commit calibration/band_tables.json.

Definitions (shared with scripts/band_read.py):
  - Session: 17:00 New York to 17:00 New York (the FX/CFD trading day).
  - Bands: session open +/- the median and 75th percentile of the up
    excursion (High-Open)/Open and down excursion (Open-Low)/Open over the
    previous 75 sessions (the indicator default). Walk-forward: a session never sees itself.
  - Slots: 30-minute steps from the session start, labelled by the London
    clock time at the END of the slot ("10:00" = everything up to 10:00).
  - Next band: the first band on that side that the session's running
    extreme has NOT reached yet (median, then 75th).
  - Position p: where the slot's closing price sits between the open (0)
    and the next band (1). Below 0 means price is back through the open.
  - Extended at 10:00: at the 10:00 London close, p toward that side's
    median band >= EXTENDED_P and further than toward the other side.

Tables, per instrument / side / London slot (each cell [n, hits]):
  reach[band][bucket]      P(`band` is reached before the session ends | not reached yet, position bucket)
  reach_base[band]         the same, whatever the position (a "normal day" at that time)
  reach_ext[band][bucket]  as reach, only for sessions extended toward this side at 10:00;
                           slots from 10:00 onward only (earlier would be look-ahead)
  extreme_in[bucket]       P(this side's session extreme has already printed | position vs median band)
"""
import os, sys, json
from datetime import datetime

import numpy as np
import pandas as pd

LOOKBACK = 75   # same as the KenJTradez indicator default
EXTENDED_P = 0.75
SLOT_MIN = 30
# Bucket upper edges. Bucket 0 = back through the open (p < 0); the last
# bucket (p >= 1) only occurs in extreme_in.
EDGES = [0.0, 0.25, 0.5, 0.75, 1.0]
N_BUCKETS = len(EDGES) + 1
PROJ_Q = [10, 25, 50, 75, 90]
FILES = {
    "Gold": "xauusd_m1.parquet",
    "NAS100": "nas100_usd_m1.parquet",
    "SPX500": "spx500_m1.parquet",
    "US2000": "us2000_m1.parquet",
    "EURUSD": "eurusd_m1.parquet",
    "USDJPY": "usdjpy_m1.parquet",
}
OUT = os.path.join(os.path.dirname(__file__), "..", "calibration", "band_tables.json")


def bucket(p):
    return int(np.searchsorted(EDGES, p, side="right"))


def slot_frame(path):
    df = pd.read_parquet(path, columns=["open", "high", "low", "close"])
    idx = df.index if df.index.tz is not None else df.index.tz_localize("UTC")
    ny = idx.tz_convert("America/New_York")
    sess_date = (ny - pd.Timedelta(hours=17)).normalize().tz_localize(None)
    sess_start = (sess_date + pd.Timedelta(hours=17)).tz_localize("America/New_York", ambiguous="NaT", nonexistent="shift_forward")
    k = ((ny - sess_start).total_seconds() // (SLOT_MIN * 60)).astype(int)
    df = pd.DataFrame({"open": df["open"].values, "high": df["high"].values, "low": df["low"].values,
                       "close": df["close"].values, "sess": sess_date.values, "k": np.asarray(k)})
    g = df.groupby(["sess", "k"], sort=True).agg(open=("open", "first"), high=("high", "max"),
                                                 low=("low", "min"), close=("close", "last"))
    return g.reset_index()


def empty_side():
    return {"reach": {"med": [[0, 0] for _ in range(N_BUCKETS)], "p75": [[0, 0] for _ in range(N_BUCKETS)]},
            "reach_base": {"med": [0, 0], "p75": [0, 0]},
            "reach_ext": {"med": [[0, 0] for _ in range(N_BUCKETS)], "p75": [[0, 0] for _ in range(N_BUCKETS)]},
            "extreme_in": [[0, 0] for _ in range(N_BUCKETS)]}


def build(path):
    s = slot_frame(path)
    s = s[(s.k >= 0) & (s.k < 48)]
    counts = s.groupby("sess").k.nunique()
    s = s[s.sess.isin(counts[counts >= 40].index)].copy()   # drop holiday / partial sessions

    sess = s.groupby("sess").agg(o=("open", "first"), H=("high", "max"), L=("low", "min"), C=("close", "last"))
    sess["up"] = (sess.H - sess.o) / sess.o
    sess["dn"] = (sess.o - sess.L) / sess.o
    for side in ("up", "dn"):
        roll = sess[side].shift(1).rolling(LOOKBACK, min_periods=LOOKBACK)
        sess[f"{side}_med"] = roll.median()
        sess[f"{side}_p75"] = roll.quantile(0.75)
    sess = sess.dropna()
    s = s[s.sess.isin(sess.index)].copy()
    s["cumH"] = s.groupby("sess").high.cummax()
    s["cumL"] = s.groupby("sess").low.cummin()
    s = s.join(sess, on="sess")

    end = (pd.to_datetime(s.sess).dt.tz_localize("America/New_York") + pd.Timedelta(hours=17)
           + pd.to_timedelta((s.k + 1) * SLOT_MIN, unit="m"))
    s["label"] = end.dt.tz_convert("Europe/London").dt.strftime("%H:%M")
    after10 = s.label.map(lambda lab: "10:00" <= lab < "21:00").values

    # Running extreme and current position, both as a fraction of the open
    s["run_up"] = (s.cumH - s.o) / s.o
    s["run_dn"] = (s.o - s.cumL) / s.o
    s["now_up"] = (s.close - s.o) / s.o
    s["now_dn"] = (s.o - s.close) / s.o

    chk = s[s.label == "10:00"].set_index("sess")
    p_up10, p_dn10 = chk.now_up / chk.up_med, chk.now_dn / chk.dn_med
    ext = {"up": chk.index[(p_up10 >= EXTENDED_P) & (p_up10 > p_dn10)].values,
           "dn": chk.index[(p_dn10 >= EXTENDED_P) & (p_dn10 > p_up10)].values}

    tables = {}
    for side in ("up", "dn"):
        run, now, final = s[f"run_{side}"].values, s[f"now_{side}"].values, s[side].values
        med, p75 = s[f"{side}_med"].values, s[f"{side}_p75"].values
        labels = s.label.values
        is_ext = np.isin(s.sess.values, ext[side]) & after10
        side_t = {}
        for i in range(len(s)):
            t = side_t.get(labels[i])
            if t is None:
                t = side_t[labels[i]] = empty_side()
            band = "med" if run[i] < med[i] else ("p75" if run[i] < p75[i] else None)
            if band:
                level = med[i] if band == "med" else p75[i]
                b = bucket(now[i] / level)
                hit = int(final[i] >= level)
                t["reach"][band][b][0] += 1; t["reach"][band][b][1] += hit
                t["reach_base"][band][0] += 1; t["reach_base"][band][1] += hit
                if is_ext[i]:
                    t["reach_ext"][band][b][0] += 1; t["reach_ext"][band][b][1] += hit
            bx = bucket(now[i] / med[i])
            t["extreme_in"][bx][0] += 1
            t["extreme_in"][bx][1] += int(final[i] <= run[i] + 1e-12)
        tables[side] = side_t

    # Projected range: from each slot, where the session closed and how far
    # beyond the high/low so far it stretched,
    # in units of that day's typical move m = mean(up median, down median).
    # Quantiles only; no direction is implied (the median close move is ~0).
    m = (s["up_med"] + s["dn_med"]) / 2 * s["o"]
    s["mv_close"] = (s["C"] - s["close"]) / m
    # Extra distance beyond the high / low made so far (0 if never exceeded)
    s["mv_high"] = (s["H"] - s["cumH"]).clip(lower=0) / m
    s["mv_low"] = (s["cumL"] - s["L"]).clip(lower=0) / m
    proj = {}
    for lab, g in s.groupby("label"):
        proj[lab] = {"n": int(len(g))}
        for col in ("mv_close", "mv_high", "mv_low"):
            proj[lab][col] = [round(float(v), 4) for v in np.percentile(g[col], PROJ_Q)]
    return {"projection": proj, "sessions": int(len(sess)), "first": str(sess.index.min().date()), "last": str(sess.index.max().date()),
            "extended_at_10": {"up": len(ext["up"]), "dn": len(ext["dn"])}, "tables": tables}


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else "."
    out = {"built": datetime.now().isoformat(timespec="minutes"), "lookback": LOOKBACK, "slot_minutes": SLOT_MIN,
           "extended_p": EXTENDED_P, "edges": EDGES, "proj_quantiles": PROJ_Q, "instruments": {}}
    for instr, fname in FILES.items():
        res = build(os.path.join(src, fname))
        out["instruments"][instr] = res
        print(f"{instr}: {res['sessions']} sessions {res['first']} \u2192 {res['last']}, extended at 10:00 up/down {res['extended_at_10']}", flush=True)
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w") as f:
        json.dump(out, f, separators=(",", ":"))
    print(f"Saved {OUT} ({os.path.getsize(OUT) // 1024} KB)")


if __name__ == "__main__":
    main()
