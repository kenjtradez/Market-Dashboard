"""Check live events on dashboard"""
import urllib.request, re

r = urllib.request.urlopen("https://kenjtradez.github.io/Market-Dashboard/")
html = r.read().decode()

# Find events section
idx = html.find("Economic Calendar")
if idx < 0:
    print("No Economic Calendar section found")
else:
    chunk = html[idx:idx+3000]
    # Extract event rows
    for m in re.finditer(r'<tr class="[^"]+-row">(.*?)</tr>', chunk, re.DOTALL):
        row = m.group(1)
        time_m = re.search(r'ev-time">([^<]+)', row)
        day_m = re.search(r'ev-day">([^<]+)', row)
        title_m = re.search(r'ev-title">([^<]+)', row)
        fc_m = re.search(r'ev-fc">([^<]+)', row)
        prev_m = re.search(r'ev-prev">([^<]+)', row)
        t = title_m.group(1) if title_m else "?"
        print(f"  {time_m.group(1) if time_m else '?'} {t[:50]:50s} fc={fc_m.group(1) if fc_m else '?'} prev={prev_m.group(1) if prev_m else '?'}")
