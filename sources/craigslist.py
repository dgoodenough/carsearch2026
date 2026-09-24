"""
Craigslist private-party listings (San Diego + Orange County + Inland Empire).

Craigslist has no official API. This uses the long-standing RSS output of
the search pages, which is lightweight and polite -- one request per
model per region, throttled. It is best-effort by nature: if Craigslist
changes or blocks the feed, this source returns nothing and the run
carries on with dealer inventory.

Two practical notes:
  * Run this from a home IP. Craigslist blocks datacenter ranges, so it
    will return nothing from a cloud VM.
  * RSS gives title, price and link but not mileage or color. Those are
    parsed out of the title where possible and otherwise left None, which
    the scorer treats as "unknown" rather than "fails the filter".
"""

import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from . import Listing

NAME = "craigslist"
REGIONS = ["sandiego", "orangecounty", "inlandempire"]
NS = {"dc": "http://purl.org/dc/elements/1.1/",
      "rdf": "http://www.w3.org/1999/02/22-rdf-syntax-ns#"}

MILES_RE = re.compile(r"(\d{1,3})[,.]?(\d{3})\s*(?:mi|miles|k\b)", re.I)
KMILES_RE = re.compile(r"\b(\d{1,3})\s*k\s*(?:mi|miles)?\b", re.I)
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")

COLORS = ["white", "black", "silver", "gray", "grey", "blue", "red", "green",
          "sea glass", "pearl", "beige", "gold", "brown", "champagne"]


def _fetch_region(region, query, price_max, timeout=12):
    params = {
        "format": "rss",
        "query": query,
        "max_price": price_max,
        "auto_title_status": 1,      # clean title only
        "purveyor": "owner",         # private party
        "srchType": "T",
    }
    url = f"https://{region}.craigslist.org/search/cta?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"),
        "Accept": "application/rss+xml, application/xml;q=0.9, */*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _parse_miles(text):
    m = MILES_RE.search(text)
    if m:
        return int(m.group(1) + m.group(2))
    m = KMILES_RE.search(text)
    if m:
        n = int(m.group(1))
        return n * 1000 if n < 400 else None
    return None


def _parse_color(text):
    low = text.lower()
    for c in COLORS:
        if c in low:
            return c
    return ""


def fetch(cfg, verbose=True):
    """
    Query by MAKE, not by model.

    Querying each model separately meant 44 models x 3 regions = 132 slow,
    throttled requests -- over twenty minutes of wall clock, which is how a
    scheduled run ended up being killed by its own time limit before it
    could write a report. Craigslist's free-text search happily returns
    every Toyota for "Toyota", so nine makes x 3 regions = 27 requests
    covers the same ground, and the model filter happens here.

    There is a hard wall-clock budget on top of that. This source is a
    bonus -- private-party listings the API cannot see -- and it must never
    be able to stop the run from producing its report.
    """
    budget = getattr(cfg, "CRAIGSLIST_TIME_BUDGET", 150)
    started = time.monotonic()

    by_make = {}
    for t in cfg.TARGETS:
        by_make.setdefault(t["make"], []).append(t)

    out = []
    seen = set()
    stopped_early = False

    for make, targets in by_make.items():
        models = {t["model"].lower(): t for t in targets}
        lo = min(t["good_years"][0] for t in targets)
        hi = max(t["good_years"][1] for t in targets)
        query = make
        for region in REGIONS:
            if time.monotonic() - started > budget:
                stopped_early = True
                break
            try:
                blob = _fetch_region(region, query, cfg.PRICE_MAX)
                root = ET.fromstring(blob)
            except Exception as exc:
                if verbose:
                    print(f"  [craigslist] {region}/{query}: {type(exc).__name__} - skipping")
                time.sleep(1.0)
                continue

            for item in root.iter("{http://purl.org/rss/1.0/}item"):
                title = (item.findtext("{http://purl.org/rss/1.0/}title") or "").strip()
                link = (item.findtext("{http://purl.org/rss/1.0/}link") or "").strip()
                if not link or link in seen:
                    continue
                seen.add(link)

                ym = YEAR_RE.search(title)
                if not ym:
                    continue
                year = int(ym.group(1))
                if not (lo - 4 <= year <= hi + 4):
                    continue

                # a make-wide query returns the whole marque, so pick out the
                # models we actually asked for -- longest name first, so
                # "Prius Prime" wins over "Prius"
                low = title.lower()
                target = None
                for name in sorted(models, key=len, reverse=True):
                    if name in low:
                        target = models[name]
                        break
                if target is None:
                    continue

                pm = re.search(r"\$\s?([\d,]+)", title)
                price = int(pm.group(1).replace(",", "")) if pm else None

                out.append(Listing(
                    source=NAME,
                    listing_id=link.rsplit("/", 1)[-1].split(".")[0],
                    vin=None,
                    year=year,
                    make=target["make"],
                    model=target["model"],
                    price=price,
                    miles=_parse_miles(title),
                    color=_parse_color(title),
                    body=target["body"],
                    seller_type="private",
                    city=region,
                    state="CA",
                    url=link,
                    raw={"title": title},
                ))
            time.sleep(1.0)                     # be a good citizen
        if stopped_early:
            break

    if verbose:
        el = time.monotonic() - started
        note = f" (stopped at the {budget}s budget)" if stopped_early else ""
        print(f"  [craigslist] {len(out)} listings in {el:.0f}s{note}")
    return out
