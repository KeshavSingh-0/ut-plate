"""Scrape J2, JCL and Kins Dining menus and nutrition labels from UT FoodPro into data/menu.json.

Runs daily in GitHub Actions. Keeps vegetarian/vegan items (Veggie or Vegan icon) plus meat-free desserts
and caches nutrition labels by recipe+portion so repeat items are fetched once.
Usage:  python scrape.py            # normal run
        python scrape.py --debug    # also saves raw HTML to debug/ for troubleshooting
"""
import html
import json
import os
import re
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import urljoin, parse_qs, urlparse

import requests

BASE = "https://hf-foodpro.austin.utexas.edu/foodpro/"
# (display name, FoodPro locationNum, FoodPro locationName) — from the FoodPro location page
LOCATIONS = [
    ("J2 Dining", "12", "J2+Dining"),
    ("JCL Dining", "12(a)", "JCL+Dining"),
    ("Kins Dining", "03", "Kins+Dining"),
]


def start_url(num, name):
    return (BASE + "shortmenu.aspx?sName=University+Housing+and+Dining"
            f"&locationNum={num}&locationName={name}&naFlag=1")
OUT = "data/menu.json"
CACHE = "data/labels_cache.json"
DEBUG = "--debug" in sys.argv
KEEP_DAYS_BACK = 1          # keep yesterday so late-night checks still work
VEG_ICONS = {"veggie", "vegan"}
MEAT_ICONS = {"beef", "pork", "fish", "shellfish", "poultry", "chicken"}


def is_dessert_station(station):
    return "dessert" in station.lower()


def keep_item(it):
    """Vegetarian/vegan icon, or a dessert with no meat flag (UT leaves the Veggie icon off many desserts)."""
    icons = set(it["icons"])
    if VEG_ICONS & icons:
        return True
    return is_dessert_station(it["station"]) and not (MEAT_ICONS & icons)

S = requests.Session()
S.headers["User-Agent"] = "ut-plate personal meal planner (student project)"


def get(url):
    for attempt in range(3):
        try:
            r = S.get(url, timeout=30)
            r.raise_for_status()
            time.sleep(0.4)                     # be polite to the server
            return r.text
        except requests.RequestException as e:
            print(f"  retry {attempt + 1}: {e}")
            time.sleep(3)
    raise RuntimeError(f"failed to fetch {url}")


def save_debug(name, text):
    if DEBUG:
        os.makedirs("debug", exist_ok=True)
        with open(os.path.join("debug", name), "w", encoding="utf-8") as f:
            f.write(text)


def text_of(fragment):
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", fragment, flags=re.S | re.I)
    t = re.sub(r"<[^>]+>", " ", t)
    return re.sub(r"\s+", " ", html.unescape(t)).strip()


def links(page, pattern):
    out = []
    for m in re.finditer(r"""href\s*=\s*["']([^"']*%s[^"']*)["']""" % pattern, page, re.I):
        out.append(urljoin(BASE, html.unescape(m.group(1))))
    return out


def qs(url, key):
    v = parse_qs(urlparse(url).query).get(key)
    return v[0] if v else None


def to_iso(mdy):
    m, d, y = [int(x) for x in mdy.split("/")]
    return f"{y:04d}-{m:02d}-{d:02d}"


# ---------- menu pages ----------
def parse_longmenu(page):
    """Return [{rec, name, station, icons}] in page order."""
    anchors = list(re.finditer(
        r"""<a[^>]+href\s*=\s*["']([^"']*label\.aspx[^"']*)["'][^>]*>(.*?)</a>""", page, re.I | re.S))
    stations = [(m.start(), m.group(1).strip()) for m in re.finditer(r"(?<![!\-])--\s*([^<>\-][^<>]*?)\s*--(?!>)", page)]
    items = []
    for i, a in enumerate(anchors):
        href = html.unescape(a.group(1))
        rec = qs(urljoin(BASE, href), "RecNumAndPort")
        if not rec:
            continue
        end = anchors[i + 1].start() if i + 1 < len(anchors) else len(page)
        tail = page[a.end():end]
        icons = {m.lower() for m in re.findall(r"LegendImages/([A-Za-z_]+)\.(?:png|gif|jpg)", tail, re.I)}
        icons |= {m.lower() for m in re.findall(r"""alt\s*=\s*["']([A-Za-z_]+) Icon""", tail, re.I)}
        station = ""
        for pos, name in stations:
            if pos < a.start():
                station = name
            else:
                break
        items.append({"rec": rec, "href": urljoin(BASE, href), "name": text_of(a.group(2)), "station": station,
                      "icons": sorted(icons)})
    return items


# ---------- nutrition labels ----------
NUTRIENTS = [  # (key, regex) — order matches the Food sheet columns
    ("cal", r"Calories\s*([\d.]+)\s*kcal"),
    ("fat", r"Total Fat\s*<?\s*([\d.]+)\s*g"),
    ("sfa", r"Saturated Fat\s*<?\s*([\d.]+)\s*g"),
    ("tfa", r"Trans\s*Fat(?:ty Acid)?\s*<?\s*([\d.]+)\s*g"),
    ("chol", r"Cholesterol\s*<?\s*([\d.]+)\s*mg"),
    ("sod", r"Sodium\s*<?\s*([\d.]+)\s*mg"),
    ("carb", r"Total Carbohydrate\.?\s*<?\s*([\d.]+)\s*g"),
    ("fib", r"Dietary Fiber\s*<?\s*([\d.]+)\s*g"),
    ("sug", r"Total Sugars\s*<?\s*([\d.]+)\s*g"),
    ("add", r"Added Sugars?\s*<?\s*([\d.]+)\s*g"),
    ("pro", r"Protein\s*<?\s*([\d.]+)\s*g"),
    ("vitd", r"Vitamin D\s*-\s*mcg\s*([\d.]+)\s*mcg"),
    ("calc", r"Calcium\s*([\d.]+)\s*mg"),
    ("iron", r"Iron\s*([\d.]+)\s*mg"),
    ("pot", r"Potassium\s*([\d.]+)\s*mg"),
]
FALLBACK = {"cal": r"Calories per serving\s*\|?\s*([\d.]+)", "fat": r"\bFat\s*([\d.]+)\s*g",
            "carb": r"Carbohydrates\s*([\d.]+)\s*g"}


def parse_label(page):
    t = text_of(page)
    nut = {}
    for key, rx in NUTRIENTS:
        m = re.search(rx, t, re.I) or (re.search(FALLBACK[key], t, re.I) if key in FALLBACK else None)
        nut[key] = round(float(m.group(1)), 2) if m else 0.0
    serving = re.search(r"Serving size\s*(.*?)\s*Calories", t, re.I)
    return {"serving": serving.group(1).strip() if serving else "", "n": [nut[k] for k, _ in NUTRIENTS],
            "ok": sum(1 for k, _ in NUTRIENTS if nut[k]) >= 2}


def main():
    os.makedirs("data", exist_ok=True)
    cache = json.load(open(CACHE)) if os.path.exists(CACHE) else {}
    old = json.load(open(OUT)) if os.path.exists(OUT) else {"days": {}, "items": {}}

    days, items = {}, {}
    for loc, num, name in LOCATIONS:
        try:
            start = get(start_url(num, name))
        except RuntimeError as e:
            print(f"skipping {loc}: {e}")
            continue
        save_debug(f"{num}_shortmenu.html", start)
        date_links = list(dict.fromkeys(l for l in links(start, "dtdate=") if "shortmenu.aspx" in l))
        print(f"{loc}: found {len(date_links)} dates")
        for dl in date_links:
            day_page = get(dl)
            iso = to_iso(qs(dl, "dtdate"))
            meals = list(dict.fromkeys(links(day_page, "longmenu.aspx")))
            for ml in meals:
                meal = qs(ml, "mealName") or "Meal"
                page = get(ml)
                save_debug(f"{num}_{iso}_{meal}.html", page)
                entries = []
                for it in parse_longmenu(page):
                    if not keep_item(it):
                        continue
                    rec = it["rec"]
                    if rec not in cache or not cache[rec].get("ok"):
                        lab = get(it["href"])
                        if DEBUG and len(cache) < 3:
                            save_debug(f"label_{rec.replace('*', '_').replace('/', '-')}.html", lab)
                        cache[rec] = parse_label(lab)
                    items[rec] = {"name": it["name"], "icons": it["icons"], **cache[rec]}
                    if is_dessert_station(it["station"]):
                        items[rec]["dessert"] = True
                    entries.append({"id": rec, "station": it["station"]})
                if entries:
                    days.setdefault(iso, {}).setdefault(loc, {})[meal] = entries
                print(f"{iso} {loc} {meal}: {len(entries)} vegetarian items")

    # keep yesterday's data if the site already rolled it off
    cutoff = (datetime.now(timezone.utc).date() - timedelta(days=KEEP_DAYS_BACK)).isoformat()
    for iso, halls in old.get("days", {}).items():
        if iso in days or iso < cutoff or not isinstance(halls, dict):
            continue
        for loc, meals in halls.items():
            if not isinstance(meals, dict):
                continue
            days.setdefault(iso, {})[loc] = meals
            for m in meals.values():
                for e in m:
                    if e["id"] in old.get("items", {}):
                        items.setdefault(e["id"], old["items"][e["id"]])

    if not items:
        raise SystemExit("No items parsed — run with --debug and check debug/*.html")
    out = {"updated": datetime.now(timezone.utc).isoformat(timespec="minutes"),
           "locations": [l[0] for l in LOCATIONS],
           "nutrients": [k for k, _ in NUTRIENTS],
           "days": dict(sorted(days.items())), "items": items}
    json.dump(out, open(OUT, "w"), separators=(",", ":"))
    json.dump(cache, open(CACHE, "w"), separators=(",", ":"))
    print(f"wrote {OUT}: {len(days)} days, {len(items)} items")


if __name__ == "__main__":
    main()
