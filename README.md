# Market Dashboard — OME + Macro

Automated daily market dashboard that blends **options positioning data** (from OME screenshots via Groq/Llama vision) with **macro-economic data** (from FRED API) into a single bullish/bearish score per instrument.

**Instruments:** Gold, NAS100, GER40, EUR/USD  
**Output:** Static HTML site, auto-deployed to GitHub Pages

## How It Works

```
You upload 4 screenshots ─┐
                           ▼
  ┌──────────────────────────────┐
  │  GitHub Actions (daily cron  │
  │  or triggered by uploads)    │
  │                              │
  │  1. Fetch FRED macro data    │
  │     (VIX, yields, dollar,    │
  │      breakeven, fed funds)   │
  │                              │
  │  2. Llama Vision reads OME   │
  │     numbers from screenshots │
  │                              │
  │  3. Score engine blends      │
  │     positioning + macro      │
  │                              │
  │  4. Build static HTML        │
  └──────────┬───────────────────┘
             ▼
  ┌──────────────────────────────┐
  │  GitHub Pages                │
  │  → yourname.github.io/...    │
  └──────────────────────────────┘
             ▼
    You open the URL → daily signal
```

## Setup (one-time, ~15 minutes)

### 1. Create a GitHub repository

Create a new **private** or **public** repo on GitHub, then push this folder to it.

### 2. Get a free FRED API key

1. Go to https://fred.stlouisfed.org/docs/api/api_key.html
2. Click "Request an API Key" (instant, no approval)
3. Copy the key

### 3. Get a free Groq API key (for screenshot vision)

1. Go to https://console.groq.com → Sign up (free, no credit card)
2. Create an API key
3. Copy the key

### 4. Add GitHub secrets

In your repo → Settings → Secrets and variables → Actions → add:

| Secret | Value |
|--------|-------|
| `FRED_API_KEY` | Your FRED API key |
| `GROQ_API_KEY` | Your Groq API key (free, from https://console.groq.com) |

### 5. Enable GitHub Pages

In your repo → Settings → Pages → Source: **GitHub Actions**

### 6. Trigger your first build

- Go to your repo → Actions → **Build Market Dashboard** → **Run workflow**
- Or: wait for the 07:30 UTC cron, or push screenshots

## Daily Workflow (30 seconds)

1. Take 4 OME screenshots (Gold, NAS100, GER40, EURUSD)
2. Upload them to the `screenshots/` folder via GitHub web UI
3. The Action runs automatically and updates the dashboard
4. Bookmark the GitHub Pages URL — check it each morning

No terminal needed. No server to maintain. Zero cost.

## Screenshot naming

Name your files so the script can find them:

```
screenshots/Gold.png
screenshots/NAS100.png
screenshots/GER40.png
screenshots/EURUSD.png
```

PNG or JPG, any size.

## Local testing (optional)

```bash
cd market-dashboard
pip install -r requirements.txt
export FRED_API_KEY=your_key
export GROQ_API_KEY=your_key
python scripts/run_all.py
```

## Scoring Logic

| Component | Weight | Source |
|-----------|--------|--------|
| Put/Call Ratio | 2pts | OME screenshot |
| Skew | 1pt | OME screenshot |
| Magnet / Spot | 1pt | OME screenshot |
| Call/Put Walls | 1pt | OME screenshot |
| VIX | 1pt | FRED |
| Dollar Index | 1pt | FRED |
| Yield Curve | 1pt | FRED |
| **Max** | **±7** | |

Signal: **LONG** (total > 0), **SHORT** (total < 0), **NEUTRAL** (= 0)

## Files

```
market-dashboard/
├── .github/workflows/build.yml   # Auto-build on schedule or upload
├── scripts/
│   ├── fetch_fred.py              # FRED API fetcher
│   ├── extract_ome.py             # Groq/Llama Vision screenshot reader
│   ├── compute_scores.py          # Bullish/bearish scoring engine
│   ├── build_dashboard.py         # Static HTML generator
│   └── run_all.py                 # Orchestrator (run everything)
├── screenshots/                   # Drop your daily OME screenshots here
├── data/                          # Cached JSON (not committed usually)
├── dashboard.html                 # Generated dashboard
└── requirements.txt
```
