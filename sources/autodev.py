"""
Auto.dev Vehicle Listings API.

Free tier: 1,000 calls/month, 5 req/sec. Aggregates franchise and
independent dealer inventory nationwide, which is the same pool that
feeds Cars.com / Autotrader / CarGurus search pages -- but through a
documented API instead of a scraper that breaks every time they ship a
redesign.

Get a key at https://www.auto.dev/  ->  set AUTODEV_API_KEY.
"""

import datetime
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from . import Listing

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
USAGE_PATH = os.path.join(_ROOT, "out", "api_usage.json")
SAMPLE_PATH = os.path.join(_ROOT, "out", "autodev_sample.json")
DEBUG_PATH = os.path.join(_ROOT, "out", "autodev_debug.json")

BASE = "https://api.auto.dev/listings"
NAME = "auto.dev"
PAGE_SIZE = 20          # the API ignores `limit`; a page is always 20

BODY_MAP = {
    # auto.dev reports vehicle.type: "Hatchback" / "Sedan" / "SUV" / ...
    # It ALSO reports vehicle.bodyStyle, but that is "Car" for every
    # passenger car, which is why an earlier version of this file rejected
    # every Prius, Mazda3 and Yaris and let only the RAV4s through.
    "hatchback": "hatchback", "liftback": "hatchback", "wagon": "hatchback",
    "5-door hatchback": "hatchback", "4dr hatchback": "hatchback",
    "4dr hatchback (1.5l 4cyl gas/electric hybrid cvt)": "hatchback",
    "sedan": "sedan", "4dr sedan": "sedan",
    "suv": "small_suv", "sport utility": "small_suv", "crossover": "small_suv",
    "minivan": "van", "van": "van", "pickup": "truck", "truck": "truck",
    "coupe": "coupe", "convertible": "convertible",
    "car": "",          # useless -- means "not a truck". Fall through.
}


def _norm_body(s):
    """Map a reported body description onto our vocabulary.

    Returns "" when the source told us nothing useful, so the caller can
    fall back rather than invent a body style that fails the filter.
    """
    s = (s or "").strip().lower()
    if not s:
        return ""
    if s in BODY_MAP:
        return BODY_MAP[s]
    # "4dr Hatchback (1.5L 4cyl ...)" and friends
    for token, mapped in (("hatchback", "hatchback"), ("liftback", "hatchback"),
                          ("wagon", "hatchback"), ("sedan", "sedan"),
                          ("suv", "small_suv"), ("crossover", "small_suv"),
                          ("minivan", "van"), ("van", "van"),
                          ("pickup", "truck"), ("truck", "truck"),
                          ("convertible", "convertible"), ("coupe", "coupe")):
        if token in s:
            return mapped
    return ""


def _dig(obj, *names, default=None):
    """
    Pull the first matching key out of a nested dict, trying several spellings.

    The response schema is not fully published, so rather than assume a shape
    and fail silently, this accepts any of the plausible names at any depth.
    If none of them hit, --probe prints what the API actually returned.
    """
    if not isinstance(obj, dict):
        return default
    lowered = {}
    def walk(d, depth=0):
        if depth > 3 or not isinstance(d, dict):
            return
        for k, v in d.items():
            lowered.setdefault(k.lower().replace("_", ""), v)
            if isinstance(v, dict):
                walk(v, depth + 1)
    walk(obj)
    for n in names:
        v = lowered.get(n.lower().replace("_", ""))
        if v not in (None, "", []):
            return v
    return default


def _find_color(obj):
    """Any key that looks like an exterior colour, whatever it is called."""
    best = None
    def walk(d, depth=0):
        nonlocal best
        if depth > 3 or not isinstance(d, dict):
            return
        for k, v in d.items():
            kl = k.lower()
            if isinstance(v, str) and v.strip() and "color" in kl or \
               (isinstance(v, str) and v.strip() and "colour" in kl):
                if "interior" in kl or "inside" in kl:
                    continue
                # prefer an explicitly exterior one
                if "exterior" in kl or "ext" in kl:
                    best = v.strip()
                elif best is None:
                    best = v.strip()
            elif isinstance(v, dict):
                walk(v, depth + 1)
    walk(obj)
    return best or ""


def _find_url(obj):
    """Any http(s) string, preferring keys that look like a detail link."""
    hits = []
    def walk(d, depth=0):
        if depth > 3 or not isinstance(d, dict):
            return
        for k, v in d.items():
            if isinstance(v, str) and v.startswith("http"):
                kl = k.lower()
                rank = 0
                for i, token in enumerate(("vdp", "detail", "listingurl",
                                           "url", "link", "href", "permalink")):
                    if token in kl:
                        rank = 10 - i
                        break
                if "image" in kl or "photo" in kl or "thumb" in kl or "logo" in kl:
                    continue
                hits.append((rank, v))
            elif isinstance(v, dict):
                walk(v, depth + 1)
    walk(obj)
    if not hits:
        return ""
    hits.sort(key=lambda t: -t[0])
    return hits[0][1]


CG_IDS = {("toyota", "prius"): "d15", ("toyota", "prius prime"): "d2418",
          ("toyota", "yaris"): "d827", ("toyota", "yaris ia"): "d2566",
          ("mazda", "mazda3"): "d214", ("toyota", "rav4"): "d306"}


def _fallback_url(make, model):
    """Never emit a listing with no link at all -- fall back to the model's
    San Diego search page, which at least lands somewhere useful."""
    cg = CG_IDS.get((make.lower(), model.lower()))
    if cg:
        slug = f"{make}-{model}".replace(" ", "-")
        return (f"https://www.cargurus.com/Cars/l-Used-{slug}"
                f"-San-Diego-{cg}_L2362?maxPrice=20000&maxMileage=150000"
                f"&distance=75&sortType=PRICE_ASC")
    return ""


def _usage_load():
    try:
        with open(USAGE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _usage_bump(n=1):
    """Track calls per calendar month so a daily schedule cannot quietly burn
    through a 1,000-call allowance."""
    month = datetime.date.today().strftime("%Y-%m")
    u = _usage_load()
    u[month] = u.get(month, 0) + n
    os.makedirs(os.path.dirname(USAGE_PATH), exist_ok=True)
    with open(USAGE_PATH, "w") as fh:
        json.dump(u, fh, indent=1)
    return u[month]


def used_this_month():
    return _usage_load().get(datetime.date.today().strftime("%Y-%m"), 0)


def _get(params, key):
    url = BASE + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {key}",
        "Accept": "application/json",
        "User-Agent": "car-deal-finder/1.0",
    })
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            body = json.load(resp)
    finally:
        # count the call whether or not it parsed -- the quota was spent
        _usage_bump()
    return body


def _calls_allowed(cfg):
    """
    How many calls this run may spend.

    Rather than a fixed per-run cost, take a share of what is left in the
    month divided by the days still to come. An early-month run can pull
    full coverage; a late-month one throttles itself instead of hitting the
    cap and going dark.
    """
    cap = getattr(cfg, "MAX_API_CALLS_PER_MONTH", 800)
    used = used_this_month()
    remaining = max(cap - used, 0)
    if remaining <= 0:
        return 0, used, cap

    today = datetime.date.today()
    if today.month == 12:
        last = datetime.date(today.year, 12, 31)
    else:
        last = datetime.date(today.year, today.month + 1, 1) - datetime.timedelta(days=1)
    days_left = max((last - today).days + 1, 1)

    share = remaining // days_left
    lo = getattr(cfg, "API_MIN_CALLS_PER_RUN", 6)
    hi = getattr(cfg, "API_MAX_CALLS_PER_RUN", 60)
    # The floor must never outrank what is actually left -- with 3 calls
    # remaining a minimum of 6 would march straight through the cap.
    return min(remaining, max(lo, min(hi, share))), used, cap


def _groups(cfg):
    """Turn config.QUERY_GROUPS into (makes, models, targets-by-model)."""
    out = []
    for makes in getattr(cfg, "QUERY_GROUPS", None) or [[t["make"]] for t in cfg.TARGETS]:
        mk = set(makes)
        targets = [t for t in cfg.TARGETS if t["make"] in mk]
        if not targets:
            continue
        models = sorted({t["model"] for t in targets})
        years = [y for t in targets for y in t["good_years"]]
        out.append({
            "makes": makes,
            "models": models,
            # Never ask for years hard_filter will reject anyway -- every
            # pre-MIN_YEAR row costs page space a keepable car could use.
            "year_lo": max(min(years) - 1, getattr(cfg, "MIN_YEAR", 0)),
            "year_hi": max(years) + 1,
            "by_model": {t["model"].lower(): t for t in targets},
        })
    return out


def fetch(cfg, verbose=True):
    key = os.environ.get("AUTODEV_API_KEY")
    if not key:
        if verbose:
            print("  [auto.dev] AUTODEV_API_KEY not set - skipping")
        return []

    budget, used, cap = _calls_allowed(cfg)
    if budget <= 0:
        if verbose:
            print(f"  [auto.dev] monthly cap reached ({used}/{cap}) - skipping. "
                  f"Raise MAX_API_CALLS_PER_MONTH in config.py to override.")
        return []

    groups = _groups(cfg)
    max_pages = getattr(cfg, "API_MAX_PAGES_PER_GROUP", 15)
    # Spread the run's allowance evenly, so an early group cannot starve a
    # later one; leftovers get redistributed as groups finish early.
    per_group = max(1, budget // max(len(groups), 1))

    out = []
    debug = {"ran": datetime.datetime.now().isoformat(timespec="seconds"),
             "budget": budget, "groups": []}

    for gi, g in enumerate(groups):
        remaining_groups = len(groups) - gi
        allow = min(max_pages, max(per_group, budget // max(remaining_groups, 1)))
        params = {
            "zip": cfg.ZIP,
            "distance": cfg.RADIUS_MILES,
            "vehicle.make": ",".join(g["makes"]),
            "vehicle.model": ",".join(g["models"]),
            "vehicle.year": f"{g['year_lo']}-{g['year_hi']}",
            "retailListing.price": f"{cfg.PRICE_MIN}-{cfg.PRICE_MAX}",
            # NOTE: vehicle.miles is accepted and then ignored -- a 231,000
            # mile Camry comes back from a 0-150000 query. Mileage is
            # enforced client-side in score.hard_filter instead.
            # No sort either: sorting by price ascending front-loads the
            # cheap high-mileage cars that the mileage filter would have
            # removed, so the early pages fill with rows we then discard.
            "includes": "total",
        }
        gdebug = {"makes": g["makes"], "models": len(g["models"]),
                  "pages": 0, "records": 0, "total": None, "error": None}
        debug["groups"].append(gdebug)

        page = 1
        while page <= allow and budget > 0:
            params["page"] = page
            budget -= 1
            try:
                data = _get(params, key)
            except Exception as exc:
                gdebug["error"] = f"{type(exc).__name__}: {exc}"
                if verbose:
                    print(f"  [auto.dev] {'/'.join(g['makes'])}: {exc}")
                break

            records = (data.get("records") or data.get("data")
                       or data.get("results") or data.get("listings") or [])
            if isinstance(records, dict):
                records = records.get("items") or list(records.values())

            if page == 1:
                gdebug["total"] = data.get("total") or data.get("totalCount")
                if records:
                    gdebug["sample"] = records[0]
            gdebug["pages"] = page
            gdebug["records"] += len(records)

            for r in records:
                v = r.get("vehicle") or {}
                rl = r.get("retailListing") or {}
                hist = r.get("history") or {}

                model_name = v.get("model") or ""
                target = g["by_model"].get(model_name.lower())
                if target is None:
                    # the API matched a model we did not ask for (e.g. a
                    # "Civic Type R" against "Civic"); keep it, and let the
                    # scoring decide, but we have no body hint for it
                    target = {"body": "", "make": v.get("make") or "",
                              "model": model_name}

                try:
                    year = int(v.get("year") or 0)
                except (TypeError, ValueError):
                    continue
                if not year:
                    continue

                body = (_norm_body(v.get("type"))
                        or _norm_body(v.get("style"))
                        or _norm_body(v.get("bodyStyle"))
                        or target.get("body", ""))

                out.append(Listing(
                    source=NAME,
                    listing_id=str(r.get("vin") or _dig(r, "id", "listingId", default="")),
                    vin=r.get("vin") or v.get("vin"),
                    year=year,
                    make=v.get("make") or target.get("make", ""),
                    model=model_name or target.get("model", ""),
                    trim=(v.get("series") or v.get("style") or "")[:60],
                    price=_int(rl.get("price")),
                    miles=_int(rl.get("miles")),
                    color=(v.get("exteriorColor") or _find_color(r)),
                    body=body,
                    title_status=_dig(r, "titleStatus", default="clean"),
                    seller_type="dealer",
                    dealer=(rl.get("dealer") or ""),
                    city=rl.get("city") or "",
                    state=rl.get("state") or "",
                    url=(rl.get("vdp") or _find_url(r)
                         or _fallback_url(v.get("make") or "", model_name)),
                    accidents=hist.get("accidentCount"),
                    one_owner=bool(hist.get("oneOwner")),
                    carfax_url=rl.get("carfaxUrl") or "",
                    raw=r,
                ))

            if len(records) < PAGE_SIZE:
                break
            page += 1
            time.sleep(0.22)          # stay under 5 req/sec

    try:
        os.makedirs(os.path.dirname(DEBUG_PATH), exist_ok=True)
        with open(DEBUG_PATH, "w") as fh:
            json.dump(debug, fh, indent=1, default=str)
    except OSError:
        pass

    if verbose:
        for g in debug["groups"]:
            note = g["error"] or (f"{g['records']} of {g['total']} "
                                  f"in {g['pages']} page(s)")
            print(f"  [auto.dev] {'/'.join(g['makes']):<26} {note}")
        u = used_this_month()
        print(f"  [auto.dev] {len(out)} listings "
              f"({u}/{cap} calls this month, {max(cap - u, 0)} left)")
    return out


def _int(x):
    try:
        return int(float(str(x).replace(",", "").replace("$", "")))
    except (TypeError, ValueError):
        return None


def probe():
    """
    Hit the API once and print exactly what came back, so a schema mismatch
    is a thirty-second fix instead of a silent empty report.

        python -m sources.autodev
    """
    import pprint
    key = os.environ.get("AUTODEV_API_KEY")
    if not key:
        print("AUTODEV_API_KEY is not set.")
        print('Set it with:  setx AUTODEV_API_KEY "your-key-here"')
        print("Then open a NEW terminal -- setx does not affect the current one.")
        return 1

    params = {"zip": "92101", "distance": 75, "vehicle.make": "Toyota",
              "vehicle.model": "Prius", "retailListing.price": "3000-20000",
              "limit": 2, "page": 1}
    print(f"GET {BASE}?{urllib.parse.urlencode(params)}\n")
    try:
        data = _get(params, key)
    except urllib.error.HTTPError as exc:
        print(f"FAILED: HTTP {exc.code} from api.auto.dev")
        if exc.code in (401, 403):
            print("-> the API rejected the key. Check it was copied whole.")
        elif exc.code == 429:
            print("-> rate limited or out of quota for the month.")
        else:
            print(f"-> {exc.reason}")
        return 1
    except urllib.error.URLError as exc:
        msg = str(exc)
        print(f"FAILED: could not reach api.auto.dev - {msg}")
        if "Tunnel connection failed" in msg or "proxy" in msg.lower():
            print("-> this is a NETWORK/proxy refusal, not a bad key. No quota was")
            print("   spent. Run this on a normal internet connection.")
        return 1

    print("Top-level keys:", list(data.keys()))
    recs = (data.get("records") or data.get("data") or data.get("results")
            or data.get("listings") or [])
    print(f"Records returned: {len(recs)}\n")
    if recs:
        print("First record, verbatim:")
        pprint.pprint(recs[0], width=100)
        print()
        cfg = type("cfg", (), {"TARGETS": [{"make": "Toyota", "model": "Prius",
                                            "body": "hatchback",
                                            "good_years": (2017, 2022)}],
                               "ZIP": "92101", "RADIUS_MILES": 75,
                               "PRICE_MIN": 3000, "PRICE_MAX": 20000})
        got = fetch(cfg, verbose=False)
        if got:
            l = got[0]
            print("Parsed as:")
            for f in ("year", "make", "model", "trim", "price", "miles",
                      "color", "body", "city", "url"):
                v = getattr(l, f)
                mark = "  " if v not in (None, "", 0) else "??"
                print(f"  {mark} {f:<8} {v!r}")
            print("\nAny '??' above means that field did not map -- send me this "
                  "output and I'll fix the mapping.")
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(probe())
