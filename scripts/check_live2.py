"""Full check of live dashboard data"""
import urllib.request, re

r = urllib.request.urlopen("https://kenjtradez.github.io/Market-Dashboard/")
html = r.read().decode()

# Date
m = re.search(r'<span class="date">([^<]+)</span>', html)
print("Generated:", m.group(1) if m else "N/A")

# Options
m = re.search(r'id="inlineData"[^>]*>(.*?)</script>', html, re.DOTALL)
if m:
    import json
    d = json.loads(m.group(1).strip())
    print(f"Options: expiry={d.get('expiry')}, strikes={len(d.get('strikes',[]))}, PCR={d.get('put_call_ratio')}")

# News - check article titles
for a in re.finditer(r'geo-art-title"[^>]*>([^<]+)', html):
    print(f"  News: {a.group(1)[:80]}")

# Signal
m = re.search(r'oc-value">([^<]+)', html)
if m:
    print(f"Signal: {m.group(1)}")
