"""Check live dashboard data"""
import urllib.request, re

r = urllib.request.urlopen("https://kenjtradez.github.io/Market-Dashboard/")
html = r.read().decode()

m = re.search(r'<span class="date">([^<]+)</span>', html)
print("Generated date:", m.group(1) if m else "NOT FOUND")

m = re.search(r'id="inlineData"[^>]*>(.*?)</script>', html, re.DOTALL)
if m:
    import json
    d = json.loads(m.group(1).strip())
    print(f"Inline data: expiry={d.get('expiry')}, strikes={len(d.get('strikes',[]))}, underlying={d.get('underlying_price')}")

m = re.search(r'id="gfData"[^>]*>(.*?)</script>', html, re.DOTALL)
if m:
    import json
    d = json.loads(m.group(1).strip())
    print(f"GF data: {d.get('symbol')}, model={d.get('model')}")

geos = html.count("geo-art-title")
print(f"Geopolitical articles: {geos}")

for name in ["Gold", "NAS100", "EURUSD"]:
    idx = html.find(f'analysis-name">{name}<')
    if idx > 0:
        chunk = html[idx:idx+300]
        m2 = re.search(r'analysis-price">(\$[0-9,.]+)', chunk)
        if m2:
            print(f"{name}: {m2.group(1)}")
