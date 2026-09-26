"""
Deal scoring.

The car is being bought to be resold in about eight months, so the thing
being minimised is not the sticker price -- it is the total cost of
holding it:

    (price + California fees) - resale value + expected repairs

That single change reorders everything. A cheap high-mileage car is not
cheap if it crosses 150,000 miles during the hold and the instant-offer
buyers decline it. A dealer car is roughly $1,500-2,000 worse than the
same car bought privately, because you pay the spread on the way in and
again on the way out. See resale.py for the model.

  net cost    (35)  projected 8-month cost, the number that actually matters
  reliability (22)  NHTSA complaint record for that exact model-year
  liquidity   (14)  how readily this car sells again in San Diego
  value       (12)  asking price vs. comparable live listings
  outlay      ( 6)  capital fronted up front
  body        ( 6)  hatchback > sedan > small SUV
  mileage     ( 5)  headroom under the cap

Hard filters (red, wrong body style, over budget, over mileage now or at
the projected sale, branded title) reject before any of that runs, so they
are never traded off against a low price.
"""

import statistics

import resale as rs

WEIGHTS = {"net_cost": 35, "reliability": 22, "liquidity": 14,
           "value": 12, "outlay": 6, "body": 6, "mileage": 5}

# Typical marginal depreciation for economy Toyotas/Mazdas, $ per mile.
# Used only as a fallback when a cohort is too small to regress.
DEPRECIATION_PER_MILE = 0.055

BRANDED = ("salvage", "rebuilt", "lemon", "flood", "junk", "reconstruct")


def hard_filter(listing, cfg):
    """Return a rejection reason, or None if the listing survives."""
    if listing.source == "manual":
        return None     # typed in by hand: always show it, however it scores
    if listing.price is None:
        return None if listing.source == "craigslist" else "no price"
    if listing.price > cfg.PRICE_MAX:
        return f"over budget (${listing.price:,})"
    if listing.price < cfg.PRICE_MIN:
        return f"suspiciously cheap (${listing.price:,})"

    if listing.miles is not None:
        if listing.miles > cfg.MAX_MILES:
            return f"too many miles ({listing.miles:,})"
        at_sale = listing.miles + cfg.HOLD_MONTHS * cfg.MILES_PER_MONTH
        if at_sale > cfg.MAX_MILES_AT_SALE:
            return (f"crosses {cfg.MAX_MILES_AT_SALE:,} during the hold "
                    f"({listing.miles:,} -> {at_sale:,})")

    color = (listing.color or "").lower()
    for bad in cfg.EXCLUDE_COLORS:
        if bad in color:
            return f"excluded color ({listing.color})"

    if listing.body and listing.body not in cfg.BODY_PREFERENCE:
        return f"body style ({listing.body})"

    if listing.year and listing.year < getattr(cfg, "MIN_YEAR", 0):
        return f"too old ({listing.year})"

    if cfg.REQUIRE_CLEAN_TITLE:
        ts = (listing.title_status or "").lower()
        if any(b in ts for b in BRANDED):
            return f"branded title ({listing.title_status})"

    return None


def build_market(listings):
    """
    Fit an asking-price model per (make, model) from the listings we just
    pulled, so "good value" is measured against this market this week
    rather than a book value that lags it.

    Returns {(make, model): predictor(year, miles) -> expected_price or None}
    """
    cohorts = {}
    for l in listings:
        if l.price and l.miles is not None:
            cohorts.setdefault((l.make.lower(), l.model.lower()), []).append(l)

    market = {}
    for key, group in cohorts.items():
        n = len(group)
        if len(group) >= 8:
            # least squares on price ~ a + b*year + c*miles
            fit = _fit(group)
            if fit:
                market[key] = (fit, n)
                continue
        med_price = statistics.median(l.price for l in group)
        med_miles = statistics.median(l.miles for l in group)
        med_year = statistics.median(l.year for l in group)
        yr_lo, yr_hi = min(l.year for l in group), max(l.year for l in group)
        mi_lo, mi_hi = min(l.miles for l in group), max(l.miles for l in group)

        def predictor(year, miles, _p=med_price, _m=med_miles, _y=med_year,
                      _yl=yr_lo, _yh=yr_hi, _ml=mi_lo, _mh=mi_hi):
            year = min(max(year, _yl), _yh)
            miles = min(max(miles, _ml), _mh)
            est = _p - (miles - _m) * DEPRECIATION_PER_MILE
            est += (year - _y) * 700
            return max(est, 1000)

        market[key] = (predictor, n)
    return market


def _fit(group):
    """Tiny 3-parameter OLS via normal equations. No numpy dependency.

    The returned predictor clamps its inputs to the range the cohort
    actually spans. A straight line fitted to 2016-2020 listings says
    something ridiculous about a 2013 with 140k miles, and an outlier that
    far outside the data should not be scored as a $4k bargain.
    """
    n = len(group)
    ys = [float(l.year) for l in group]
    ms = [float(l.miles) / 10000.0 for l in group]
    ps = [float(l.price) for l in group]
    y0 = sum(ys) / n
    m0 = sum(ms) / n
    p0 = sum(ps) / n
    ys = [v - y0 for v in ys]
    ms = [v - m0 for v in ms]
    ps = [v - p0 for v in ps]

    syy = sum(v * v for v in ys)
    smm = sum(v * v for v in ms)
    sym = sum(a * b for a, b in zip(ys, ms))
    syp = sum(a * b for a, b in zip(ys, ps))
    smp = sum(a * b for a, b in zip(ms, ps))

    det = syy * smm - sym * sym
    if abs(det) < 1e-9:
        return None
    b = (smm * syp - sym * smp) / det          # $ per model year
    c = (syy * smp - sym * syp) / det          # $ per 10k miles

    # Sanity: newer should not be worth less, more miles should not be worth
    # more. If the fit says otherwise the cohort is too noisy -- bail out.
    if b < 0 or c > 0:
        return None

    yr_lo = min(l.year for l in group)
    yr_hi = max(l.year for l in group)
    mi_lo = min(l.miles for l in group)
    mi_hi = max(l.miles for l in group)

    def predictor(year, miles, _b=b, _c=c, _y0=y0, _m0=m0, _p0=p0,
                  _yl=yr_lo, _yh=yr_hi, _ml=mi_lo, _mh=mi_hi):
        year = min(max(year, _yl), _yh)
        miles = min(max(miles, _ml), _mh)
        est = _p0 + _b * (year - _y0) + _c * (miles / 10000.0 - _m0)
        return max(est, 1000)

    return predictor


def _budget_score(price, sweet, ceiling):
    """100 at or below the sweet spot, decaying to 0 at the ceiling."""
    if price <= sweet:
        return 100.0
    span = max(ceiling - sweet, 1)
    return max(0.0, 100.0 * (1.0 - ((price - sweet) / span) ** 0.85))


def _ramp(x, good, bad):
    """100 at or better than `good`, 0 at or worse than `bad`, linear between."""
    if x is None:
        return 50.0
    if x <= good:
        return 100.0
    if x >= bad:
        return 0.0
    return 100.0 * (bad - x) / float(bad - good)


def score_listing(listing, cfg, market, reliability):
    parts = {}

    prof = reliability.get((listing.make.lower(), listing.model.lower()), {}).get(listing.year)
    rel_score = prof["score"] if prof else 50.0
    parts["reliability"] = rel_score

    # --- the main event: what does eight months of this car cost? ---------
    proj = rs.project(listing.price, listing.miles, listing.year,
                      listing.make, listing.model, listing.seller_type,
                      hold_months=cfg.HOLD_MONTHS,
                      miles_per_month=cfg.MILES_PER_MONTH,
                      accidents=getattr(listing, "accidents", None))
    cost = rs.total_cost(proj, rel_score, listing.miles, listing.year,
                         private_sale_confidence=cfg.PRIVATE_SALE_CONFIDENCE,
                         hold_months=cfg.HOLD_MONTHS,
                         make=listing.make, model=listing.model, cfg=cfg)
    walk = rs.walk_away_price(
        getattr(cfg, "TARGET_COST", 4000), listing.miles, listing.year,
        listing.make, listing.model, listing.seller_type, rel_score, cfg,
        hold_months=cfg.HOLD_MONTHS, miles_per_month=cfg.MILES_PER_MONTH,
        accidents=getattr(listing, "accidents", None),
        private_sale_confidence=cfg.PRIVATE_SALE_CONFIDENCE)
    parts["net_cost"] = _ramp(cost["total"] if cost else None,
                              cfg.COST_GOOD, cfg.COST_BAD)
    parts["liquidity"] = (proj["liquidity"] * 100.0) if proj else 50.0

    # --- value vs. this week's market -------------------------------------
    expected = None
    entry = market.get((listing.make.lower(), listing.model.lower()))
    cohort_n = 0
    if entry and listing.price and listing.miles is not None:
        pred, cohort_n = entry
        expected = pred(listing.year, listing.miles)
    too_good = False
    if expected and expected > 0:
        # to the dollar, so the browser (which only receives the rounded
        # figure) computes the identical value score
        expected = float(rs._r(expected))
        delta = (expected - listing.price) / expected     # + means underpriced
        # A car priced a third under its own comparables is usually not a
        # bargain -- it is a branded title, an odometer discrepancy, an
        # accident, or a listing error. Flag it for verification rather than
        # letting it win the ranking on price alone.
        if delta > 0.30 and cohort_n >= 3:
            too_good = True
        # A comp built from four cars is a rumour, not a market. Shrink the
        # value signal toward neutral until the cohort is big enough to mean
        # something, so a thin sample can nudge the ranking but never drive it.
        confidence = min(1.0, cohort_n / 20.0)
        if too_good:
            # cap the credit an unverified outlier can earn
            delta = min(delta, 0.15)
        parts["value"] = max(0.0, min(100.0, 50.0 + delta * 250.0 * confidence))
    else:
        parts["value"] = 50.0

    # --- capital fronted --------------------------------------------------
    parts["outlay"] = _ramp(listing.price, cfg.PRICE_SWEET_SPOT, cfg.PRICE_MAX)

    if listing.miles is None:
        parts["mileage"] = 50.0
    else:
        parts["mileage"] = max(0.0, 100.0 * (1.0 - listing.miles / float(cfg.MAX_MILES)))

    try:
        rank = cfg.BODY_PREFERENCE.index(listing.body)
        parts["body"] = 100.0 - rank * (100.0 / max(len(cfg.BODY_PREFERENCE), 1))
    except ValueError:
        parts["body"] = 50.0

    total = sum(parts[k] * WEIGHTS[k] for k in WEIGHTS) / sum(WEIGHTS.values())

    return {
        "total": round(total, 1),
        # rounded for display; parts_exact is what the report's JavaScript
        # port is checked against, since rounding at different points is
        # exactly how two implementations quietly drift apart
        "parts": {k: round(v, 1) for k, v in parts.items()},
        "parts_exact": dict(parts),
        "total_exact": total,
        "expected_price": round(expected) if expected else None,
        "under_market": (round(expected - listing.price)
                         if expected and listing.price else None),
        "cohort_n": cohort_n,
        "too_good": too_good,
        "reliability_note": (prof or {}).get("why", ""),
        "complaints": (prof or {}).get("complaints"),
        "recalls": (prof or {}).get("recalls"),
        "rel_checked": bool((prof or {}).get("checked")),
        "projection": proj,
        "cost": cost,
        "walk_away": walk,
    }
