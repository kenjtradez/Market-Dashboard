# Market Dashboard

Daily market dashboard, options levels tracker, and Telegram brief for **Gold, NAS100 and EUR/USD**.
One pipeline, one scoring model, and every output reads the same data files.

- Dashboard: https://kenjtradez.github.io/Market-Dashboard/
- Options tracker: https://kenjtradez.github.io/Market-Dashboard/tracker/

## Schedule (weekdays)

| UK time | What runs |
|---|---|
| 06:41 | Full build + Telegram brief |
| 12:41 | Full build + Telegram brief |
| 19:23 BST / 18:23 GMT | Full build, no Telegram. Captures option open interest, which Yahoo only publishes during US hours |

Pushes to `main` rebuild and deploy without sending Telegram. Use **Actions → Build Market Dashboard → Run workflow** to run it by hand, and tick *Send the Telegram brief* if you want the message too.

GitHub cron is UTC-only. Each brief has a BST cron and a GMT cron, and the first workflow step skips whichever one doesn't match the current UK offset.

## Pipeline (`scripts/run_all.py`)

| Step | Script | Source |
|---|---|---|
| Macro | `fetch_fred.py` | FRED (yields, breakevens, VIX/VXN/GVZ, Fed funds, broad USD) and Yahoo (DXY, SKEW). Also writes the 90-day history the tracker's Macro tab uses |
| Options levels | `fetch_options_yf.py` | Yahoo option chains for GLD / QQQ / FXE: highest-OI expiry within 3–45 days, scaled to XAU/USD, NDX and EUR/USD. Thin or pre-market chains are rejected and the last good snapshot is kept |
| COT | `fetch_cot.py` | CFTC public API, queried by contract code, with 3 years of weekly history |
| Vol & range | `calc_vol_range.py` | 105-day realised ranges from GC=F / NQ=F / 6E=F, calibrated to the Vol & Range Pine script |
| Calendar | `fetch_events.py` | ForexFactory weekly feed, shown in UK time |
| Headlines | `fetch_geopolitical.py`, `fetch_sentiment.py` | BBC, CNBC and FXStreet RSS. Display only, not scored |
| Score | `compute_scores.py` | See below |
| Build | `build_dashboard.py` | Writes `index.html`. `tracker/index.html` is static and reads `data/*.json` |
| Telegram | `send_telegram.py` | One consolidated brief. `--dry-run` prints it instead of sending |

`data/` and `index.html` are generated (git-ignored) and carried between runs by the Actions cache.

## Scoring model

| Component | Range | Rule |
|---|---|---|
| Positioning | ±4 | PCR < 0.7 → +2, > 1.3 → −2 · ATM IV skew ±5% → ±1 · magnet above/below spot → ±1. Scores 0 without a usable snapshot (≤ 96 h old) |
| Macro | ±5 | Instrument vol index (GVZ / VXN; EUR has none since EVZ was discontinued) · DXY < 100 / > 107 · 2s10s ±0.5% · SKEW > 145 / < 120 · 5Y breakeven > 3% / < 1.5%. Stale series are skipped |
| COT | ±2 | Extremes only, contrarian: speculator net % of OI ranked against 3 years. ≥ 90th pct → −1, ≥ 97th → −2, mirrored at the low end |

**Signal:** LONG or SHORT only when |total| ≥ 2 (out of ±11), otherwise NEUTRAL. "High-probability" needs components that agree *and* |total| ≥ 4.

This is a heuristic model. It is not backtested and not financial advice.

## Secrets

| Secret | Used by |
|---|---|
| `FRED_API_KEY` | Macro step |
| `TELEGRAM_BOT_TOKEN`, `TELEGRAM_CHAT_ID` | Telegram brief |

The tracker's live candles use a Twelve Data key that you enter in the page. It's stored in your browser and sent only to Twelve Data.

## Local run

```bash
pip install -r requirements.txt
export FRED_API_KEY=your_key            # optional; FRED-only series are skipped without it
python scripts/run_all.py
python scripts/send_telegram.py --dry-run
python -m http.server 8000              # then open http://localhost:8000/
```

`scripts/backtest_reversal.py` (manual workflow **Reversal Backtest**) is a separate research script and isn't part of the scheduled build.
