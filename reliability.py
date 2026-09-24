"""
Model-year reliability scoring, backed by NHTSA's public complaint and
recall APIs (no key required, no rate limit published).

The raw complaint count is not usable on its own: it tracks sales volume
and vehicle age as much as it tracks defects. So we score a model-year
*relative to the other years of the same model*, which cancels out most
of the volume effect, then apply an age correction and a curated overlay
for defects that are known to be expensive rather than merely annoying.

Results are cached to cache/nhtsa.json so daily runs cost one API call
per model-year per week.
"""

import concurrent.futures
import datetime
import json
import os
import threading
import time
import statistics
import urllib.parse
import urllib.request

_CACHE_LOCK = threading.Lock()

CACHE_PATH = os.path.join(os.path.dirname(__file__), "cache", "nhtsa.json")
CACHE_TTL = 7 * 24 * 3600
API = "https://api.nhtsa.gov"

# Components whose failures are drivetrain-expensive. A complaint here is
# weighted far more heavily than, say, a rattling trim panel.
EXPENSIVE = {
    "POWER TRAIN": 3.0,
    "ENGINE": 3.0,
    "ENGINE AND ENGINE COOLING": 3.0,
    "SERVICE BRAKES": 2.0,
    "ELECTRICAL SYSTEM": 1.5,
    "FUEL/PROPULSION SYSTEM": 2.0,
    "FUEL SYSTEM": 2.0,
    "STEERING": 2.0,
    "AIR BAGS": 1.5,
    "STRUCTURE": 1.5,
}
DEFAULT_WEIGHT = 1.0

# Curated penalties for defects where the complaint count understates the
# repair bill. Keyed (make, model, year) -> (penalty_points, reason).
# Sourced from NHTSA complaint bodies + recall records; see README.
KNOWN_DEFECTS = {
    ("toyota", "prius", y): (45, "Gen 3: EGR clogging -> head gasket failure; brake actuator (DTC C1391) ~$2-3k")
    for y in range(2010, 2016)
}
def _span(make, model, lo, hi, penalty, reason):
    return {(make, model, y): (penalty, reason) for y in range(lo, hi + 1)}


KNOWN_DEFECTS.update({
    ("toyota", "prius", 2016): (15, "First year of Gen 4: windshield cracking, brake booster, hot-weather power loss"),
    ("toyota", "rav4", 2019): (50, "First year XA50: transmission shudder/loss of propulsion, coolant bypass valve, liftgate hinges"),
    ("toyota", "rav4", 2020): (20, "Carryover XA50 transmission and coolant bypass valve complaints"),
    ("toyota", "rav4", 2021): (15, "Passenger airbag occupancy sensor, power-seat gear failure (~$1.5k)"),
    ("toyota", "rav4", 2017): (8, "Battery hold-down/terminal fire recall 23V-734 - verify it was performed"),
    ("toyota", "rav4", 2013): (12, "Early XA40 torque-converter shudder"),
    ("toyota", "yaris", 2019): (10, "Denso low-pressure fuel pump recall - verify it was performed"),
    ("toyota", "yaris ia", 2017): (5, "Mazda2 mechanicals, few complaints; thin resale market is the real cost"),
    ("toyota", "yaris ia", 2018): (5, "Mazda2 mechanicals, few complaints; thin resale market is the real cost"),
    ("toyota", "yaris", 2020): (10, "Denso low-pressure fuel pump recall - verify it was performed"),
    ("mazda", "mazda3", 2019): (18, "BP gen 2.5L excessive oil consumption; i-Activsense false emergency braking"),
    ("mazda", "mazda3", 2020): (18, "BP gen 2.5L excessive oil consumption"),
    ("mazda", "mazda3", 2021): (15, "2.5L oil consumption reports at low mileage"),
    ("mazda", "mazda3", 2018): (8, "Rearview camera recall 23V-487; infotainment 'ghost touch'"),
    ("mazda", "mazda3", 2014): (12, "Early BM infotainment and clutch-slave-cylinder complaints"),
})

# --- Honda 1.5L turbo oil dilution ------------------------------------
# Fuel washes past the rings and thins the oil. Honda extended the warranty
# on 2016-2018 Civics and never shipped a real fix. It is materially worse
# in cold climates and San Diego is about the friendliest place in the
# country to own one, so this is a caution rather than a disqualifier --
# but only the turbo trims are affected, so check which engine the car has.
_DILUTION = "1.5L turbo oil dilution - warm climate helps; confirm it is not the turbo trim"
KNOWN_DEFECTS.update(_span("honda", "civic", 2016, 2022, 10, _DILUTION))
KNOWN_DEFECTS.update(_span("honda", "civic hatchback", 2017, 2022, 12,
                           "All hatchback trims are the 1.5T - " + _DILUTION))
KNOWN_DEFECTS.update(_span("honda", "cr-v", 2017, 2022, 12, _DILUTION))
KNOWN_DEFECTS.update(_span("honda", "accord", 2018, 2022, 8, _DILUTION))

# --- Nissan CVT --------------------------------------------------------
# Long, well-documented history of judder, overheating and outright
# failure, with replacement often exceeding the value of the car. The 2020
# redesigns are meaningfully better but carry the same architecture.
_CVT = "Nissan CVT history - replacement can exceed the car's value"
KNOWN_DEFECTS.update(_span("nissan", "sentra", 2013, 2019, 22, _CVT))
KNOWN_DEFECTS.update(_span("nissan", "sentra", 2020, 2022, 10, _CVT + " (improved 2020 redesign)"))
KNOWN_DEFECTS.update(_span("nissan", "versa", 2013, 2019, 22, _CVT))
KNOWN_DEFECTS.update(_span("nissan", "versa", 2020, 2022, 10, _CVT + " (improved 2020 redesign)"))
KNOWN_DEFECTS.update(_span("nissan", "kicks", 2018, 2022, 12, _CVT))

# --- Subaru FB oil consumption ----------------------------------------
KNOWN_DEFECTS.update(_span("subaru", "impreza", 2012, 2016, 14,
                           "FB-series oil consumption; 2017+ redesign is the one to buy"))
KNOWN_DEFECTS.update(_span("subaru", "crosstrek", 2013, 2017, 14,
                           "FB-series oil consumption; check consumption history"))

# --- Volkswagen --------------------------------------------------------
KNOWN_DEFECTS.update(_span("volkswagen", "golf", 2015, 2018, 12,
                           "Timing-chain tensioner and DSG mechatronic history; parts cost more"))
KNOWN_DEFECTS.update(_span("volkswagen", "jetta", 2015, 2018, 14,
                           "Pre-MQB: timing-chain tensioner history"))

# --- Lexus CT 200h = Gen 3 Prius drivetrain ---------------------------
KNOWN_DEFECTS.update(_span("lexus", "ct 200h", 2011, 2017, 22,
                           "Shares the Gen 3 Prius 2ZR-FXE - same EGR clogging and head gasket risk"))

# --- Toyota Prius v shares the Gen 3 engine ---------------------------
KNOWN_DEFECTS.update(_span("toyota", "prius v", 2012, 2017, 18,
                           "Gen 3 engine family - ask for EGR circuit service records"))

# --- Mazda 2.5 oil consumption carried across the range ---------------
KNOWN_DEFECTS.update(_span("mazda", "cx-5", 2019, 2021, 12,
                           "2.5L oil-consumption reports at low mileage"))
KNOWN_DEFECTS.update(_span("mazda", "mazda6", 2018, 2021, 10,
                           "2.5L oil-consumption reports"))

# --- Hyundai / Kia: the Theta II engines are NOT in these models -------
# Sonata, Santa Fe, Tucson, Optima, Sorento and Sportage 2011-2019 carry the
# Theta II 2.0T/2.4L GDI, whose rod-bearing failures drove a multi-billion
# dollar recall. They are deliberately absent from config.TARGETS. If anyone
# adds them later, these penalties make sure they cannot quietly win.
for _mk, _md in (("hyundai", "sonata"), ("hyundai", "santa fe"),
                 ("hyundai", "santa fe sport"), ("hyundai", "tucson"),
                 ("kia", "optima"), ("kia", "sorento"), ("kia", "sportage")):
    KNOWN_DEFECTS.update(_span(_mk, _md, 2011, 2019, 45,
                               "Theta II 2.0T/2.4L GDI rod-bearing failure - "
                               "multi-billion-dollar recall and settlement"))


def _load_cache():
    try:
        with open(CACHE_PATH) as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def _save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    tmp = CACHE_PATH + ".tmp"
    with open(tmp, "w") as fh:
        json.dump(cache, fh)
    os.replace(tmp, CACHE_PATH)


# NHTSA's model vocabulary is not auto.dev's. Where they disagree, this maps
# our name onto theirs. Verified against api.nhtsa.gov/products/vehicle/models.
NHTSA_ALIASES = {
    ("lexus", "ct 200h"): "CT200H",            # no space in their catalogue
    ("hyundai", "ioniq"): "IONIQ HEV",         # plain "IONIQ" returns nothing
    ("toyota", "corolla hatchback"): "COROLLA",  # not a separate model there
    ("honda", "civic hatchback"): "CIVIC",     # they split HATCH / HATCHBACK
    ("toyota", "yaris hatchback"): "YARIS HATCHBACK",
}


def nhtsa_model(make, model):
    return NHTSA_ALIASES.get((make.lower(), model.lower()), model)


def _get(path, **params):
    url = path + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "car-deal-finder/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def fetch_nhtsa(make, model, year, cache=None):
    """Complaint + recall summary for one model-year. Cached for a week."""
    key = f"{make}|{model}|{year}".lower()
    cache = _load_cache() if cache is None else cache
    hit = cache.get(key)
    if hit and time.time() - hit.get("_fetched", 0) < CACHE_TTL:
        return hit

    rec = _fetch_one(make, model, year)
    with _CACHE_LOCK:
        cache[key] = rec
        _save_cache(cache)
    return rec


def _fetch_one(make, model, year):
    """The network half: one model-year, no cache handling."""
    # complaints/recalls start as None, not 0. A failed lookup must never
    # be reported as "zero complaints" -- that reads as a verified clean
    # record when it actually means nobody checked.
    rec = {"_fetched": time.time(), "complaints": None, "weighted": None,
           "recalls": None, "top_components": [], "error": None}
    try:
        c = _get(f"{API}/complaints/complaintsByVehicle",
                 make=make, model=nhtsa_model(make, model), modelYear=year)
        results = c.get("results") or []
        rec["complaints"] = c.get("count", len(results))
        counts = {}
        weighted = 0.0
        for item in results:
            comp = (item.get("components") or "UNKNOWN").upper()
            # a complaint can list several components, comma separated
            parts = [p.strip() for p in comp.split(",") if p.strip()]
            best = max((EXPENSIVE.get(p, DEFAULT_WEIGHT) for p in parts),
                       default=DEFAULT_WEIGHT)
            weighted += best
            for p in parts:
                counts[p] = counts.get(p, 0) + 1
        rec["weighted"] = weighted
        rec["top_components"] = sorted(counts.items(), key=lambda kv: -kv[1])[:3]
    except Exception as exc:                      # network / API hiccup
        rec["error"] = f"{type(exc).__name__}: {exc}"
        rec["complaints"] = None
        rec["weighted"] = None

    try:
        r = _get(f"{API}/recalls/recallsByVehicle",
                 make=make, model=nhtsa_model(make, model), modelYear=year)
        rec["recalls"] = r.get("Count", len(r.get("results") or []))
    except Exception:
        pass

    return rec


def prefetch(jobs, workers=12, progress=None):
    """
    Warm the cache for many (make, model, year) triples at once.

    A 44-model list is several hundred model-years on a cold cache, which is
    minutes of sequential HTTP. These are independent read-only requests, so
    they parallelise cleanly. Results are merged under a lock and written
    once at the end rather than per call.
    """
    cache = _load_cache()
    now = time.time()
    todo = [j for j in jobs
            if now - cache.get(f"{j[0]}|{j[1]}|{j[2]}".lower(), {}).get("_fetched", 0)
            >= CACHE_TTL]
    if not todo:
        return cache

    done = [0]

    def work(job):
        make, model, year = job
        rec = _fetch_one(make, model, year)
        with _CACHE_LOCK:
            cache[f"{make}|{model}|{year}".lower()] = rec
            done[0] += 1
            if progress and done[0] % 25 == 0:
                progress(done[0], len(todo))
        return rec

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(work, todo))

    _save_cache(cache)
    if progress:
        progress(len(todo), len(todo))
    return cache


def build_profile(make, model, year_lo, year_hi, extra_years=(), cache=None):
    """
    Score every year of one model against its own siblings.
    Returns {year: {"score": 0-100, "why": str, ...}}.
    """
    years = sorted(set(range(year_lo, year_hi + 1)) | set(extra_years))
    cache = _load_cache() if cache is None else cache
    raw = {}
    for y in years:
        raw[y] = fetch_nhtsa(make, model, y, cache=cache)

    # If nothing came back for this model, say so rather than scoring it as
    # though every year had a spotless record.
    if all(r.get("weighted") is None for r in raw.values()):
        return build_profile_offline(make, model, year_lo, year_hi, extra_years)

    # A model with literally zero complaints in every year it was sold is not
    # a flawless car -- it is a name this API does not recognise, and the
    # query came back 200 with an empty result. Scoring that as perfect would
    # float unknown models to the top of the board. NHTSA_ALIASES fixes the
    # mismatches we know about; this catches the ones we do not.
    seen = [r.get("complaints") for r in raw.values() if r.get("complaints") is not None]
    if seen and max(seen) == 0:
        prof = build_profile_offline(make, model, year_lo, year_hi, extra_years)
        for y in prof:
            prof[y]["why"] = (prof[y]["why"] or
                              "NHTSA returned no records under this model name - "
                              "reliability not verified")
        return prof

    this_year = datetime.date.today().year
    # Age-normalise: an older car has had more years to accumulate reports.
    norm = {}
    for y, rec in raw.items():
        age = max(this_year - y, 1)
        norm[y] = (rec["weighted"] or 0.0) / age

    # A year with almost no records next to siblings carrying hundreds is
    # far more likely to be a gap in the database -- a sub-model filed under
    # another name, a year NHTSA indexes differently -- than a flawless
    # production run. Left alone, the relative scoring rewards the gap with a
    # perfect 100 and floats it to the top of the board. Treat those years as
    # not comparable and score them from the model's own median instead.
    counts = [r["complaints"] for r in raw.values() if r.get("complaints") is not None]
    median_count = statistics.median(counts) if counts else 0
    sparse = set()
    if median_count > 60:
        for y, rec in raw.items():
            c = rec.get("complaints")
            if c is not None and c < 15 and c < 0.1 * median_count:
                sparse.add(y)

    vals = [v for y, v in norm.items() if v > 0 and y not in sparse]
    if vals:
        lo, hi = min(vals), max(vals)
    else:
        lo = hi = 0.0

    median_norm = statistics.median(vals) if vals else 0.0

    profile = {}
    for y in years:
        if y in sparse:
            # score it as a typical year of this model, not a perfect one
            base = 100.0 * (hi - median_norm) / (hi - lo) if hi > lo else 75.0
            penalty, reason = KNOWN_DEFECTS.get((make.lower(), model.lower(), y), (0, ""))
            profile[y] = {
                "score": round(max(0.0, min(100.0, base - penalty)), 1),
                "complaints": raw[y]["complaints"], "recalls": raw[y]["recalls"],
                "top_components": raw[y]["top_components"], "checked": False,
                "penalty": penalty,
                "why": reason or (f"only {raw[y]['complaints']} NHTSA records against a "
                                  f"model median of {int(median_count)} - treated as a "
                                  f"data gap, not a clean year"),
                "error": "sparse",
            }
            continue
        if hi > lo:
            # invert: fewer age-normalised weighted complaints -> higher score
            base = 100.0 * (hi - norm[y]) / (hi - lo)
        else:
            base = 75.0
        penalty, reason = KNOWN_DEFECTS.get((make.lower(), model.lower(), y), (0, ""))
        score = max(0.0, min(100.0, base - penalty))
        profile[y] = {
            "score": round(score, 1),
            "complaints": raw[y]["complaints"],
            "recalls": raw[y]["recalls"],
            "checked": raw[y].get("error") is None,
            "top_components": raw[y]["top_components"],
            "penalty": penalty,
            "why": reason,
            "error": raw[y]["error"],
        }
    return profile


def build_profile_offline(make, model, year_lo, year_hi, extra_years=()):
    """
    Same shape as build_profile but with no network: every year starts from
    a neutral 75 and only the curated known-defect penalties apply. Used for
    --demo and as the automatic fallback when NHTSA is unreachable, so a
    network blip degrades the scoring instead of breaking the run.
    """
    years = sorted(set(range(year_lo, year_hi + 1)) | set(extra_years))
    profile = {}
    for y in years:
        penalty, reason = KNOWN_DEFECTS.get((make.lower(), model.lower(), y), (0, ""))
        profile[y] = {
            "score": round(max(0.0, 75.0 - penalty), 1),
            "complaints": None, "recalls": None, "top_components": [],
            "checked": False,
            "penalty": penalty, "why": reason, "error": "offline",
        }
    return profile
