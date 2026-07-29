"""
Fetch geopolitical risk news from RSS feeds.
No API key required. Falls back gracefully if a feed is unavailable.
"""
import os, json, time
from datetime import datetime

import requests
from xml.etree import ElementTree

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

FEEDS = [
    ("Reuters", "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best&best-sectors=geopolitical"),
    ("BBC", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("CNBC", "https://www.cnbc.com/id/100727362/device/rss/rss.html"),
    ("AP", "https://rsshub.app/apnews/topics/apf-topnews"),
]

KEYWORDS = [
    "war", "conflict", "crisis", "sanction", "invasion", "attack", "nuclear",
    "tariff", "trade war", "default", "coup", "collapse", "emergency",
    "protest", "riot", "embargo", "shutdown", "disruption", "restriction",
]

INSTRUMENTS = {
    "Gold":   ["gold", "commodity", "precious metal", "gld", "xau"],
    "NAS100": ["nasdaq", "tech", "semiconductor", "qqq", "big tech", "ai", "software"],
    "EURUSD": ["euro", "ecb", "european", "fxe", "eur", "germany", "france", "dax"],
}


def parse_rss(url, timeout=15):
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "MarketDashboard/1.0"})
        if resp.status_code != 200:
            return []
        root = ElementTree.fromstring(resp.content)
        items = []
        for item in root.iter("item"):
            title = item.findtext("title", "")
            link = item.findtext("link", "")
            desc = item.findtext("description", "")
            pubdate = item.findtext("pubDate", "")
            items.append({"title": title, "url": link, "description": desc, "date": pubdate})
        return items
    except Exception as e:
        print(f"  RSS error for {url}: {e}")
        return []


def score_article(title, desc):
    text = (title + " " + desc).lower()
    score = 0
    tags = []
    severity = {
        "war": 3, "conflict": 2, "crisis": 3, "sanction": 2, "invasion": 3,
        "attack": 2, "nuclear": 3, "tariff": 2, "trade war": 3, "default": 3,
        "coup": 3, "collapse": 2, "emergency": 2, "protest": 1,
        "embargo": 2, "disruption": 2, "riot": 2, "shutdown": 2, "restriction": 2,
    }
    for word, pts in severity.items():
        if word in text:
            score += pts
            tags.append(word)
    return min(score, 10), tags


def run():
    print("Fetching geopolitical risk news from RSS feeds...")

    all_articles = []
    seen = set()

    for source_name, url in FEEDS:
        items = parse_rss(url)
        print(f"  {source_name}: {len(items)} items")
        for art in items:
            link = art.get("url", "")
            if not link or link in seen:
                continue
            seen.add(link)
            title = art.get("title", "")
            desc = art.get("description", "")
            relevance, tags = score_article(title, desc)
            if relevance >= 2:
                all_articles.append({
                    "title": title,
                    "url": link,
                    "domain": source_name.lower(),
                    "seentext": desc[:300],
                    "relevance": relevance,
                    "tags": tags,
                    "date": art.get("date", ""),
                })

    all_articles.sort(key=lambda x: x["relevance"], reverse=True)
    top = all_articles[:20]

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
