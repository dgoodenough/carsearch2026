"""
Resale modelling -- the part that actually decides this purchase.

The car is being bought to be sold again in roughly eight months, so the
number that matters is not the sticker. It is:

    net cost  =  (price + California fees)  -  what it sells for later

Two things dominate that number, and neither is "is this car cheap":

1. **The buy/sell spread.** Buying at dealer retail and exiting through a
   CarMax or Carvana instant offer pays a spread twice. CarMax's own FY2026
   filings put their gross profit at $2,253 per retail unit, and instant
   offers land roughly 15-20% under private-party value, widening on older
   and higher-mileage cars because that is where the reconditioning bill
   grows. Buying private and selling private avoids both halves.

2. **Mileage thresholds at the exit.** Value does not decay smoothly across
   100k and 150k miles -- demand steps down at those numbers, and past
   roughly 150k the instant-offer buyers start declining the car outright,
   which forces a distressed sale. A car bought at 140k miles crosses 150k
   during the hold. That is the whole problem with the Poway Yaris.

Time-based depreciation, by contrast, barely matters here. A Prius already
5-9 years old sheds only about 4-6% of its current value per year, so eight
months of calendar time costs a few hundred dollars. The spread costs
thousands. Optimising for a low sticker while ignoring the exit is how you
lose money on a "cheap" car.

Sources are listed in README.md.
"""

import datetime
import math


def _r(x):
    """
    Round half UP, the way JavaScript's Math.round does.

    Python's built-in round() rounds halves to even, so round(2.5) is 2 while
    Math.round(2.5) is 3. Every figure in this module is recomputed in the
    browser when a slider moves (see report_js.py), and a car whose numbers
    land on a .5 boundary would otherwise show one cost in the table and a
    different one after a slider nudge. Same convention on both sides.
    """
    return int(math.floor(x + 0.5))

# ---------------------------------------------------------------- California
CA_SALES_TAX = 0.0775          # San Diego County combined rate
CA_DOC_FEE = 85                # California caps dealer doc fees at $85
CA_SMOG_TRANSFER = 37
PRIVATE_PARTY_FEE_SAVING = CA_DOC_FEE + CA_SMOG_TRANSFER


def ca_registration(price):
    """Registration, title and VLF. The VLF is 0.65% of value; the rest is
    largely flat. Close enough for ranking purposes."""
    return 180 + 0.0065 * price


def acquisition_cost(price, seller_type):
    """Everything you pay on top of the agreed price to drive it away."""
    fees = price * CA_SALES_TAX + ca_registration(price)
    if seller_type != "private":
        fees += CA_DOC_FEE + CA_SMOG_TRANSFER
    return _r(fees)


# ------------------------------------------------------------- depreciation
# Annual loss as a share of *current* value for a car already several years
# old. Derived from CarEdge residual curves; hybrids hold hardest.
ANNUAL_DEPRECIATION = {
    ("toyota", "prius"): 0.050,
    ("toyota", "prius prime"): 0.055,
    ("toyota", "rav4"): 0.055,
    ("toyota", "yaris"): 0.075,
    ("toyota", "yaris ia"): 0.075,
    ("mazda", "mazda3"): 0.080,
}
DEFAULT_ANNUAL_DEPRECIATION = 0.075

# Dollars of value lost per mile driven, by price tier.
def _per_mile(price):
    if price is None:
        return 0.055
    if price < 9000:
        return 0.035
    if price < 14000:
        return 0.050
    return 0.070


# --------------------------------------------------------------- liquidity
# How readily this car sells again in San Diego specifically. A Prius in
# Southern California has an unusually deep private-party bid -- commuters
# and rideshare drivers -- which is worth real money at the exit.
LIQUIDITY = {
    ("toyota", "prius"): 1.00,
    ("toyota", "prius prime"): 0.90,
    ("toyota", "rav4"): 0.95,
    ("toyota", "yaris"): 0.70,
    ("toyota", "yaris ia"): 0.62,
    ("mazda", "mazda3"): 0.80,
}
DEFAULT_LIQUIDITY = 0.75


def mileage_liquidity(miles_at_sale):
    """Demand steps down at the round numbers, hard."""
    if miles_at_sale is None:
        return 0.75
    if miles_at_sale < 80000:
        return 1.00
    if miles_at_sale < 100000:
        return 0.92
    if miles_at_sale < 120000:
        return 0.80
    if miles_at_sale < 150000:
        return 0.62
    return 0.35          # instant-offer buyers start declining outright


def instant_offer_haircut(miles_at_sale, age_at_sale):
    """
    Discount below private-party value if they exit through CarMax/Carvana
    rather than selling it themselves. Base 15%, widening exactly where the
    reconditioning bill does.
    """
    h = 0.15
    if miles_at_sale is not None:
        if miles_at_sale > 100000:
            h += 0.03
        if miles_at_sale > 120000:
            h += 0.04
        if miles_at_sale > 150000:
            h += 0.10      # likely declined; wholesale auction instead
    if age_at_sale > 9:
        h += 0.03
    if age_at_sale > 12:
        h += 0.04
    return min(h, 0.42)


# ------------------------------------------------------------------- model
ACCIDENT_HAIRCUT = 0.12     # a reported accident on the CARFAX


def project(price, miles, year, make, model, seller_type="dealer",
            hold_months=8, miles_per_month=1000, today=None, accidents=None):
    """
    Project the full cost of owning this car for `hold_months` and selling it.

    Returns a dict with the acquisition cost, the projected resale under both
    exit channels, and the net loss under each.
    """
    if price is None:
        return None

    today = today or datetime.date.today()
    key = (make.lower(), model.lower())

    miles_at_sale = (miles + hold_months * miles_per_month) if miles is not None else None
    age_at_sale = (today.year - year) + hold_months / 12.0

    # --- what it will be worth, privately, at the end of the hold ----------
    annual = ANNUAL_DEPRECIATION.get(key, DEFAULT_ANNUAL_DEPRECIATION)
    time_loss = price * annual * (hold_months / 12.0)
    mile_loss = (hold_months * miles_per_month) * _per_mile(price)

    # A dealer's asking price is above private-party value to begin with;
    # you do not get that markup back when you sell.
    dealer_markup = 0.10 if seller_type == "dealer" else 0.0
    private_value_now = price * (1 - dealer_markup)

    private_resale = max(private_value_now - time_loss - mile_loss, 500)

    # A reported accident follows the VIN. The buyer on the other end will
    # pull the same CARFAX you did, and will price it accordingly.
    if accidents:
        private_resale *= (1 - ACCIDENT_HAIRCUT)

    # Crossing a mileage threshold during the hold costs more than the
    # smooth per-mile figure implies.
    liq_now = mileage_liquidity(miles)
    liq_then = mileage_liquidity(miles_at_sale)
    if liq_then < liq_now:
        private_resale *= (1 - 0.5 * (liq_now - liq_then))

    haircut = instant_offer_haircut(miles_at_sale, age_at_sale)
    instant_resale = max(private_resale * (1 - haircut), 300)

    fees = acquisition_cost(price, seller_type)
    all_in = price + fees

    liquidity = LIQUIDITY.get(key, DEFAULT_LIQUIDITY) * liq_then

    return {
        "all_in": _r(all_in),
        "fees": fees,
        "miles_at_sale": miles_at_sale,
        "private_resale": _r(private_resale),
        "instant_resale": _r(instant_resale),
        "loss_private": _r(all_in - private_resale),
        "loss_instant": _r(all_in - instant_resale),
        # Deliberately unrounded. These feed blended_loss() and the report's
        # JavaScript port, and Python rounds halves to even while JavaScript
        # rounds them up -- rounding here made the two disagree by a dollar
        # or two on cars that land exactly on a .5 boundary. Round at the
        # point of display instead.
        "haircut": haircut,
        "liquidity": liquidity,
        "threshold_warning": (liq_then < liq_now),
        "accident_penalty": bool(accidents),
    }


def blended_loss(proj, private_sale_confidence=0.5):
    """
    They will not certainly manage a private sale from 2,500 miles away, and
    they will not certainly be stuck with the instant offer either. Weight
    the two, leaning on how liquid the car is: an easy car to sell makes the
    private route realistic, a hard one does not.
    """
    if proj is None:
        return None
    p = private_sale_confidence * proj["liquidity"]
    return _r(proj["loss_private"] * p + proj["loss_instant"] * (1 - p))


# ------------------------------------------------------- expected repairs
def expected_repairs(reliability_score, miles, year=None, hold_months=8,
                     today=None):
    """
    A repair bill during the hold is part of the cost of the car, so it
    belongs in the same number as the depreciation rather than in a
    separate hand-wave.

    Three things drive it, and the first two are just physics: an older car
    breaks more, a higher-mileage car breaks more, and a model-year with a
    bad complaint record breaks more than its age and mileage alone predict.

    Leaving age out is how a fourteen-year-old economy car ends up looking
    like the cheapest way to own a car for eight months. It is not -- it is
    the cheapest way to *buy* one, which is a different question, and the
    difference is a tow truck in a city she does not know yet.
    """
    if reliability_score is None:
        reliability_score = 60.0
    today = today or datetime.date.today()

    age = max(0, today.year - year) if year else 8
    miles = miles if miles is not None else 90000

    # Expected annual maintenance-and-repair spend, before the model-year
    # record is taken into account.
    annual = 400.0
    annual += 70.0 * max(0, age - 4)            # things start failing at ~5 yrs
    annual += 0.008 * max(0, miles - 60000)     # and at ~60k miles

    # The model-year's own record scales that up or down.
    factor = 0.6 + 0.8 * ((100.0 - reliability_score) / 100.0)

    return _r(annual * factor * (hold_months / 12.0))


def insurance(make, model, cfg, hold_months=8):
    """
    Cost of insuring it for the hold.

    Left out of the first version of this model, which made every figure it
    produced about a third too low -- and not uniformly, since a midsize
    sedan costs meaningfully more to cover than an economy hatch. The base
    rate is a placeholder until a real quote replaces it in config.py.
    """
    base = getattr(cfg, "INSURANCE_BASE_ANNUAL", 2000)
    klass = getattr(cfg, "INSURANCE_CLASS", {}).get(
        (make.lower(), model.lower()), "compact")
    factor = getattr(cfg, "INSURANCE_FACTOR", {}).get(klass, 1.0)
    return _r(base * factor * (hold_months / 12.0))


def total_cost(proj, reliability_score, miles, year=None,
               private_sale_confidence=0.5, hold_months=8,
               make="", model="", cfg=None):
    """Depreciation loss, plus repairs, plus insurance -- what to minimise."""
    if proj is None:
        return None
    loss = blended_loss(proj, private_sale_confidence)
    repairs = expected_repairs(reliability_score, miles, year, hold_months)
    ins = insurance(make, model, cfg, hold_months) if cfg else 0
    return {"loss": loss, "repairs": repairs, "insurance": ins,
            "total": loss + repairs + ins}


def walk_away_price(target, miles, year, make, model, seller_type,
                    reliability_score, cfg, hold_months=8, miles_per_month=1000,
                    accidents=None, private_sale_confidence=0.5,
                    lo=500, hi=40000):
    """
    The most you can pay for this car and still hit `target` over the hold.

    This is the number you actually want standing on a lot: not a ranking,
    a ceiling. Cost rises monotonically with price -- a dearer car loses
    more to depreciation, tax and the dealer spread -- so a bisection finds
    it in a handful of steps.

    Returns None when even the cheapest plausible price cannot reach the
    target, which is itself the answer: walk away from this one.
    """
    def cost_at(price):
        proj = project(price, miles, year, make, model, seller_type,
                       hold_months=hold_months, miles_per_month=miles_per_month,
                       accidents=accidents)
        c = total_cost(proj, reliability_score, miles, year,
                       private_sale_confidence, hold_months, make, model, cfg)
        return c["total"] if c else float("inf")

    if cost_at(lo) > target:
        return None
    if cost_at(hi) <= target:
        return _r(hi)
    for _ in range(40):
        mid = (lo + hi) / 2.0
        if cost_at(mid) <= target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 5:
            break
    return _r(lo)
