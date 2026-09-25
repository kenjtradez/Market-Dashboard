"""
Fetch headlines from RSS feeds (no API key) and derive:
  - a geopolitical risk list (headlines with war/sanction/tariff-type terms)
  - per-instrument headline sets, matched across ALL headlines, which
    fetch_sentiment.py scores.

Instrument matching runs over every headline, not just the risk list —
matching only the top risk headlines meant almost nothing ever matched.
"""
import os, json, re
from datetime import datetime

import requests
from xml.etree import ElementTree

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")

FEEDS = [
    ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
    ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
    ("CNBC", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=100727362"),
    ("CNBC Economy", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=20910258"),
    ("CNBC Investing", "https://search.cnbc.com/rs/search/combinedcms/view.xml?partnerId=wrss01&id=15839069"),
    ("FXStreet", "https://www.fxstreet.com/rss/news"),
]

SEVERITY = {
    "war": 3, "conflict": 2, "crisis": 3, "sanction": 2, "sanctions": 2, "invasion": 3,
    "attack": 2, "nuclear": 3, "tariff": 2, "tariffs": 2, "trade war": 3, "default": 3,
    "coup": 3, "collapse": 2, "emergency": 2, "protest": 1, "embargo": 2,
    "disruption": 2, "riot": 2, "shutdown": 2, "restriction": 2,
}

INSTRUMENT_TERMS = {
    "Gold":   ["gold", "xau", "xau/usd", "bullion", "precious metal", "precious metals"],
    "NAS100": ["nasdaq", "nasdaq 100", "tech stocks", "big tech", "semiconductor", "chip stocks", "qqq"],
    "EURUSD": ["euro", "eur/usd", "eurusd", "ecb", "eurozone", "lagarde"],
    "SPX500": ["s&p 500", "s&p", "wall street", "spx", "spy"],
    "US2000": ["russell 2000", "russell", "small caps", "small-cap", "small cap", "iwm"],
    "USDJPY": ["yen", "usd/jpy", "usdjpy", "boj", "bank of japan", "ueda"],
}


def has_term(text, term):
    return re.search(r"\b" + re.escape(term) + r"\b", text) is not None


def parse_feed(url, timeout=20):
    try:
        resp = requests.get(url, timeout=timeout, headers={"User-Agent": "Mozilla/5.0 (compatible; MarketDashboard/1.0)"})
        if resp.status_code != 200:
            return []
        root = ElementTree.fromstring(resp.content)
    except Exception as e:
        print(f"  Feed error for {url}: {e}")
        return []
    items = []
    for item in root.iter("item"):
        link = (item.findtext("link") or "").strip()
        items.append({"title": (item.findtext("title") or "").strip(), "url": link,
                      "description": re.sub(r"<[^>]+>", " ", item.findtext("description") or "")[:400],
                      "date": item.findtext("pubDate") or ""})
    return items


def risk_score(text):
    score, tags = 0, []
    for word, pts in SEVERITY.items():
        if has_term(text, word):
            score += pts
            tags.append(word)
    return min(score, 10), tags


def run():
    print("Fetching headlines from RSS feeds...")
    items, seen = [], set()
    for source, url in FEEDS:
        feed = parse_feed(url)
        print(f"  {source}: {len(feed)} items")
        for it in feed:
            # Only http(s) links are kept; they end up as hrefs on a public page.
            if not it["url"].startswith(("https://", "http://")) or it["url"] in seen:
                continue
            seen.add(it["url"])
            text = (it["title"] + " " + it["description"]).lower()
            rel, tags = risk_score(text)
            items.append({"title": it["title"], "url": it["url"], "source": source, "date": it["date"],
                          "summary": it["description"][:300], "relevance": rel, "tags": tags,
                          "instruments": [i for i, terms in INSTRUMENT_TERMS.items() if any(has_term(text, t) for t in terms)]})

    risk = sorted((i for i in items if i["relevance"] >= 2), key=lambda x: x["relevance"], reverse=True)[:20]
    instr_risk = {}
    for instr in INSTRUMENT_TERMS:
        hits = [a for a in risk if instr in a["instruments"]]
        avg = sum(a["relevance"] for a in hits) / len(hits) if hits else 0
        instr_risk[instr] = {
            "article_count": len(hits),
            "avg_relevance": round(avg, 1),
            "risk_level": "HIGH" if len(hits) >= 3 and avg >= 5 else "MODERATE" if hits else "LOW",
        }

    out = {
        "fetched": datetime.now().isoformat(),
        "total_headlines": len(items),
        "articles": risk,
        "headlines": items,
        "instrument_risk": instr_risk,
        "global_risk_score": round(sum(a["relevance"] for a in risk) / max(len(risk), 1), 1),
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(os.path.join(DATA_DIR, "geopolitical.json"), "w") as f:
        json.dump(out, f, indent=2)
    print(f"  {len(items)} headlines, {len(risk)} risk-tagged, global risk {out['global_risk_score']}")
    for instr, v in instr_risk.items():
        n = sum(1 for i in items if instr in i["instruments"])
        print(f"  {instr}: {n} relevant headlines, risk {v['risk_level']}")
    return True


if __name__ == "__main__":
    run()
