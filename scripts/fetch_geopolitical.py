"""
Fetch geopolitical risk news via GDELT Project API.
Single-query approach. No API key required.
"""
import os, json, re, time
from datetime import datetime
import requests

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

QUERY = "war crisis sanctions tariff conflict nuclear attack protest riot coup"
INSTRUMENTS = {
    "Gold":   ["gold", "precious metal", "gld", "xau"],
    "NAS100": ["nasdaq", "tech", "semiconductor", "qqq", "big tech"],
    "EURUSD": ["euro", "ecb", "european", "fxe", "eur", "germany", "france"],
}
SOURCES = ["reuters", "bloomberg", "ft.com", "wsj", "ap.org", "cnbc", "bbc", "economist", "foreignpolicy", "nytimes"]


def score_article(title, seentext, domain, tone_str):
    text = (title + " " + seentext).lower()
    score = 0
    tags = []
    severity = {
        "war": 3, "conflict": 2, "crisis": 3, "sanction": 2, "invasion": 3,
        "attack": 2, "nuclear": 3, "tariff": 2, "trade war": 3, "default": 3,
        "coup": 3, "collapse": 2, "emergency": 2, "protest": 1,
        "embargo": 2, "disruption": 2, "riot": 2, "shutdown": 2,
    }
    for word, pts in severity.items():
        if word in text:
            score += pts
            tags.append(word)
    if tone_str is not None:
        try:
            t = float(tone_str)
            if t < -5:
                score += 2
            elif t < -2:
                score += 1
        except (ValueError, TypeError):
            pass
    if any(s in domain for s in SOURCES):
        score += 1
    return min(score, 10), tags


def run():
    print("Fetching geopolitical risk news from GDELT...")

    params = {
        "query": QUERY,
        "mode": "ArtList",
        "format": "json",
        "maxrecords": 25,
        "sort": "DateDesc",
        "timespan": "72",
    }

    headers = {"User-Agent": "MarketDashboard/1.0"}
    data = None
    for attempt in range(3):
        try:
            resp = requests.get("https://api.gdeltproject.org/api/v2/doc/doc", params=params, timeout=25, headers=headers)
            if resp.status_code == 429 and attempt < 2:
                wait = 5 * (attempt + 1)
                print(f"  Rate limited, retrying in {wait}s...")
                time.sleep(wait)
                continue
            if resp.status_code != 200:
                print(f"  GDELT returned HTTP {resp.status_code}: {resp.text[:200]}")
            else:
                data = resp.json()
            break
        except Exception as e:
            print(f"  GDELT attempt {attempt+1} error: {e}")
            if attempt < 2:
                time.sleep(3)
            else:
                break

    all_articles = []
    seen = set()

    if data and "articles" in data:
        for art in data["articles"]:
            url = art.get("url", "")
            if not url or url in seen:
                continue
            seen.add(url)
            title = art.get("title", "")
            seentext = art.get("seentext", "")
            domain = art.get("domain", "")
            tone = art.get("tone")
            relevance, tags = score_article(title, seentext, domain, tone)
            if relevance >= 2:
                all_articles.append({
                    "title": title,
                    "url": url,
                    "domain": domain,
                    "seentext": seentext[:300],
                    "relevance": relevance,
                    "tags": tags,
                    "tone": tone,
                    "date": art.get("seendate", ""),
                })
    elif data:
        print(f"  Unexpected response keys: {list(data.keys())[:5]}")
    else:
        print("  No data returned from GDELT")

    all_articles.sort(key=lambda x: x["relevance"], reverse=True)
    top = all_articles[:15]

    instr_risk = {}
    for instr, terms in INSTRUMENTS.items():
        count = 0
        total_rel = 0
        for art in top:
            txt = (art["title"] + " " + art["seentext"]).lower()
            if any(t in txt for t in terms):
                count += 1
                total_rel += art["relevance"]
        instr_risk[instr] = {
            "article_count": count,
            "avg_relevance": round(total_rel / count, 1) if count else 0,
            "risk_level": "HIGH" if count >= 3 and total_rel / max(count, 1) >= 5 else "MODERATE" if count >= 1 else "LOW",
        }

    out = {
        "fetched": datetime.now().isoformat(),
        "total_articles": len(all_articles),
        "articles": top,
        "instrument_risk": instr_risk,
        "global_risk_score": round(sum(a["relevance"] for a in top) / max(len(top), 1), 1),
    }

    out_path = os.path.join(DATA_DIR, "geopolitical.json")
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(out_path, "w") as f:
        json.dump(out, f, indent=2)
    print(f"  Saved {len(top)} articles to {out_path}")
    print(f"  Global risk score: {out['global_risk_score']}")
    for instr, v in instr_risk.items():
        print(f"  {instr}: {v['risk_level']} ({v['article_count']} articles)")
    return True


if __name__ == "__main__":
    run()
