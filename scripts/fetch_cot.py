"""
Fetch CFTC Commitment of Traders (COT) data for tracked instruments.
Sources:
  - Gold (088691): https://www.cftc.gov/dea/futures/deacmxsf.htm
  - NAS100 / EURUSD: https://www.cftc.gov/dea/futures/financial_lf.htm
Parses fixed-width <pre> blocks to extract non-commercial and commercial positioning.
"""
import os, json, re
from datetime import datetime

import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

# Market code -> (page_url, market_name_keyword)
COT_SOURCES = {
    "Gold": {
        "url": "https://www.cftc.gov/dea/futures/deacmxsf.htm",
        "code": "088691",
    },
    "NAS100": {
        "url": "https://www.cftc.gov/dea/futures/financial_lf.htm",
        "code": "209747",
    },
    "EURUSD": {
        "url": "https://www.cftc.gov/dea/futures/financial_lf.htm",
        "code": "099741",
    },
}

def parse_cot_block(lines, market_code):
    """Find the COT data block for a given market code and extract values.
    Handles both Short Format (SF — COMEX, 9 values) and Long Format (LF — Financial, 14 values)."""
    header_idx = None
    for i, line in enumerate(lines):
        if f"Code-{market_code}" in line or f"Code #{market_code}" in line:
            header_idx = i
            break
    if header_idx is None:
        return None

    # Determine format: SF has "COMMITMENTS" on its own line; LF has "Positions" on its own line
    fmt = None
    for offset in range(1, 12):
        idx = header_idx + offset
        if idx >= len(lines): break
        line = lines[idx].strip()
        if line.upper() == "COMMITMENTS":
            fmt = "SF"
            break
        if line.upper() == "POSITIONS":
            fmt = "LF"
            break

    # Find the data line (the one after COMMITMENTS / Positions with 9+ numbers for SF, 14+ for LF)
    data_idx = None
    expected_min = 9 if fmt == "SF" else 14
    for offset in range(1, 12):
        check_idx = header_idx + offset
        if check_idx >= len(lines):
            break
        parts = lines[check_idx].strip().split()
        clean_nums = []
        for p in parts:
            try:
                clean_nums.append(int(p.replace(",", "")))
            except ValueError:
                pass
        if len(clean_nums) >= expected_min:
            data_idx = check_idx
            break

    if data_idx is None:
        return None

    # Parse the data line
    parts = lines[data_idx].strip().split()
    nums = []
    for p in parts:
        try:
            nums.append(int(p.replace(",", "")))
        except ValueError:
            pass

    # Find OI — look for "OPEN INTEREST is" (LF) or "OPEN INTEREST:" (SF)
    oi = None
    for offset in range(-2, 10):
        idx = header_idx + offset
        if idx >= 0 and idx < len(lines):
            m = re.search(r"OPEN INTEREST\s*(?:is|:)\s*([\d,]+)", lines[idx], re.IGNORECASE)
            if m:
                oi = int(m.group(1).replace(",", ""))
                break

    # Get date
    date_str = ""
    for j in range(max(0, header_idx - 1), header_idx + 4):
        if j < len(lines):
            m = re.search(r"AS OF\s+(\d{2}/\d{2}/\d{2,4})", lines[j], re.IGNORECASE)
            if m:
                date_str = m.group(1)
                break

    if fmt == "SF":
        # SF: noncomm_long, noncomm_short, noncomm_spread, comm_long, comm_short,
        #      total_long, total_short, nonrep_long, nonrep_short
        if len(nums) < 9:
            return None
        return {
            "format": "SF",
            "date": date_str,
            "open_interest": oi,
            "noncomm_long": nums[0],
            "noncomm_short": nums[1],
            "noncomm_spread": nums[2],
            "comm_long": nums[3],
            "comm_short": nums[4],
            "total_long": nums[5],
            "total_short": nums[6],
            "nonrep_long": nums[7],
            "nonrep_short": nums[8],
        }
    else:
        # LF: noncomm_long, noncomm_short, noncomm_spread,
        #     dealer_long, dealer_short, dealer_spread,
        #     asset_mgr_long, asset_mgr_short, asset_mgr_spread,
        #     lev_funds_long, lev_funds_short, lev_funds_spread,
        #     nonrep_long, nonrep_short
        if len(nums) < 14:
            return None
        # Commercial = dealer + asset manager + leveraged funds
        comm_long = nums[3] + nums[6] + nums[9]
        comm_short = nums[4] + nums[7] + nums[10]
        total_long = nums[0] + nums[3] + nums[6] + nums[9] + nums[12]
        total_short = nums[1] + nums[4] + nums[7] + nums[10] + nums[13]
        return {
            "format": "LF",
            "date": date_str,
            "open_interest": oi,
            "noncomm_long": nums[0],
            "noncomm_short": nums[1],
            "noncomm_spread": nums[2],
            "comm_long": comm_long,
            "comm_short": comm_short,
            "total_long": total_long,
            "total_short": total_short,
            "nonrep_long": nums[12],
            "nonrep_short": nums[13],
        }

def compute_cot_metrics(data):
    """Derive positioning metrics from raw COT numbers."""
    if not data:
        return None
    oi = data.get("open_interest")
    if not oi or oi == 0:
        return None

    nc_long = data["noncomm_long"]
    nc_short = data["noncomm_short"]
    c_long = data["comm_long"]
    c_short = data["comm_short"]

    nc_net = nc_long - nc_short
    c_net = c_long - c_short

    # Net spec positioning as % of OI
    nc_net_pct = round(nc_net / oi * 100, 1) if oi else 0

    # Commercial net as % of OI
    c_net_pct = round(c_net / oi * 100, 1) if oi else 0

    # Speculator crowding: noncomm net position magnitude
    # The historical extremes for most markets are around +/- 30% of OI
    # Score: extreme net spec long is bearish (crowded), extreme net spec short is bullish
    spec_signal = "NEUTRAL"
    if nc_net_pct > 15:
        spec_signal = "BEARISH"
    elif nc_net_pct < -15:
        spec_signal = "BULLISH"

    # Commercial positioning (smart money)
    comm_signal = "NEUTRAL"
    if c_net_pct > 10:
        comm_signal = "BULLISH"
    elif c_net_pct < -10:
        comm_signal = "BEARISH"

    return {
        "date": data["date"],
        "open_interest": oi,
        "noncomm_net": nc_net,
        "noncomm_net_pct": nc_net_pct,
        "noncomm_long": data["noncomm_long"],
        "noncomm_short": data["noncomm_short"],
        "comm_net": c_net,
        "comm_net_pct": c_net_pct,
        "comm_long": data["comm_long"],
        "comm_short": data["comm_short"],
        "spec_signal": spec_signal,
        "comm_signal": comm_signal,
    }

def fetch_page(url):
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return resp.text

def get_pre_lines(html):
    """Extract lines from the <pre> block."""
    m = re.search(r"<pre[^>]*>(.*?)</pre>", html, re.DOTALL | re.IGNORECASE)
    if m:
        return m.group(1).splitlines()
    return html.splitlines()

def run():
    print("Fetching CFTC COT data...")
    results = {}

    # Group by URL to avoid double-fetching
    url_cache = {}
    for instr, cfg in COT_SOURCES.items():
        url = cfg["url"]
        if url not in url_cache:
            try:
                html = fetch_page(url)
                url_cache[url] = get_pre_lines(html)
                print(f"  Fetched {url} ({len(url_cache[url])} lines)")
            except Exception as e:
                print(f"  ERROR fetching {url}: {e}")
                url_cache[url] = None

        if url_cache[url] is None:
            results[instr] = {"error": "fetch failed"}
            continue

        lines = url_cache[url]
        data = parse_cot_block(lines, cfg["code"])
        if data is None:
            results[instr] = {"error": f"market code {cfg['code']} not found or failed to parse"}
            print(f"  {instr}: NOT FOUND (code {cfg['code']})")
        else:
            metrics = compute_cot_metrics(data)
            results[instr] = metrics
            if metrics:
                print(f"  {instr}: spec_net={metrics['noncomm_net_pct']}%, comm_net={metrics['comm_net_pct']}%, spec_signal={metrics['spec_signal']}")
            else:
                print(f"  {instr}: parsed but metrics failed")

    out_path = os.path.join(DATA_DIR, "cot_data.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump({"fetched": datetime.now().isoformat(), "instruments": results}, f, indent=2)
    print(f"\nSaved to {out_path}")
    return True

if __name__ == "__main__":
    run()
