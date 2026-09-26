"""
Car deal finder - search configuration.

Edit this file to change what the finder looks for. Everything else
(scoring, reliability, resale, alerting) reads from here.
"""

# ---------------------------------------------------------------- location
ZIP = "92101"          # downtown San Diego
RADIUS_MILES = 75      # covers SD county + Temecula/Riverside fringe

# ---------------------------------------------------------------- budget
PRICE_MIN = 3000
PRICE_MAX = 20000
PRICE_SWEET_SPOT = 10000   # capital outlay preference (a minor term now)
MAX_MILES = 200000

# ---------------------------------------------------------------- the hold
# This car is being bought to be sold again. That, not the sticker price,
# is what the scoring optimises -- see resale.py.
HOLD_MONTHS = 8
MILES_PER_MONTH = 1000           # ~12k/yr; raise if she'll commute far

# How likely they are to manage a private-party sale rather than taking a
# CarMax/Carvana instant offer. 0 = certainly instant offer, 1 = certainly
# private. Selling from out of state is hard, so 0.5 is the honest default.
PRIVATE_SALE_CONFIDENCE = 0.5

# Acceptable total 8-month cost (depreciation + fees + expected repairs).
# Recalibrated once insurance entered the model: the real spread across the
# board is roughly $4,700 to $10,900, so the old 2500/8500 scale pinned
# almost everything near the bottom.
COST_GOOD = 4500
COST_BAD = 9148          # renting instead. Score zero for failing to beat it.

# Oldest model year worth considering.
MIN_YEAR = 2015

# Mileage the car must stay under at the END of the hold, not just today.
# 150k is where instant-offer buyers start declining cars outright; cars
# between 150k and 200k are kept on the board, and resale.py prices in the
# harder sale, so they surface only when the price makes up for it.
MAX_MILES_AT_SALE = 200000

# ---------------------------------------------------------------- vehicles
#
# Deliberately broad. An earlier version of this file listed six models,
# which quietly pre-decided the answer -- if a well-kept Corolla or Civic or
# Impreza is the cheapest way to own a car for eight months, the finder
# should be able to say so. The rule for inclusion is: economy or compact
# car, hatchback / sedan / small crossover, with a resale market in Southern
# California and no catastrophic known defect across its whole production run.
#
#   good_years  the window worth buying. Outside it a car is not excluded,
#               it just scores badly -- so a screaming deal still surfaces.
#   hard_avoid  (lo, hi) inclusive, for years with a known expensive defect.
#
# Deliberately NOT included: Hyundai Sonata, Santa Fe, Tucson and Kia Optima,
# Sorento, Sportage from 2011-2019. Those carry the Theta II 2.0T/2.4L GDI
# engine, whose rod-bearing failures drove a multi-billion-dollar recall and
# settlement. The compact Hyundai/Kia models below use different engines and
# are not affected.
TARGETS = [
    # ---- Toyota ---------------------------------------------------------
    {"make": "Toyota", "model": "Prius", "body": "hatchback",
     "good_years": (2016, 2022), "hard_avoid": (2010, 2015),
     "note": "Gen 4. 2016 is a shaky first year; 2019+ is the sweet spot."},
    {"make": "Toyota", "model": "Prius Prime", "body": "hatchback",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Cleanest complaint record of anything on this list."},
    {"make": "Toyota", "model": "Prius c", "body": "hatchback",
     "good_years": (2015, 2019), "hard_avoid": None,
     "note": "Smaller 1.5L hybrid, not the Gen 3 drivetrain. Cheap to run, tight inside."},
    {"make": "Toyota", "model": "Prius v", "body": "hatchback",
     "good_years": (2015, 2017), "hard_avoid": None,
     "note": "Wagon-shaped Prius. Same Gen 3 engine family -- ask about EGR service."},
    {"make": "Toyota", "model": "Corolla", "body": "sedan",
     "good_years": (2015, 2022), "hard_avoid": None,
     "note": "About as boring and dependable as used cars get."},
    {"make": "Toyota", "model": "Corolla Hatchback", "body": "hatchback",
     "good_years": (2019, 2022), "hard_avoid": None,
     "note": "2019+ TNGA platform, genuinely good to drive."},
    {"make": "Toyota", "model": "Corolla Hybrid", "body": "sedan",
     "good_years": (2020, 2022), "hard_avoid": None,
     "note": "Prius drivetrain in a Corolla body. Excellent resale."},
    {"make": "Toyota", "model": "Camry", "body": "sedan",
     "good_years": (2015, 2022), "hard_avoid": None,
     "note": "Bigger than she needs, but the resale market is deep."},
    {"make": "Toyota", "model": "Camry Hybrid", "body": "sedan",
     "good_years": (2015, 2022), "hard_avoid": None, "note": ""},
    {"make": "Toyota", "model": "Yaris", "body": "hatchback",
     "good_years": (2016, 2020), "hard_avoid": None,
     "note": "2019-20 is a rebadged Mazda2. Watch the Denso fuel-pump recall."},
    {"make": "Toyota", "model": "Yaris iA", "body": "sedan",
     "good_years": (2017, 2018), "hard_avoid": None,
     "note": "Rebadged Mazda2 sedan. Solid mechanically, thin resale market."},
    {"make": "Toyota", "model": "C-HR", "body": "small_suv",
     "good_years": (2018, 2022), "hard_avoid": None,
     "note": "Corolla underneath. Slow, but cheap and dependable."},
    {"make": "Toyota", "model": "RAV4", "body": "small_suv",
     "good_years": (2016, 2018), "hard_avoid": (2019, 2019),
     "note": "XA40 only. 2019 is the single worst year on this whole list."},

    # ---- Honda ----------------------------------------------------------
    {"make": "Honda", "model": "Civic", "body": "sedan",
     "good_years": (2015, 2022), "hard_avoid": None,
     "note": "Check whether it is the 1.5T or the naturally aspirated 2.0."},
    {"make": "Honda", "model": "Civic Hatchback", "body": "hatchback",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Hatchback trims are all 1.5T -- see the oil-dilution note."},
    {"make": "Honda", "model": "Fit", "body": "hatchback",
     "good_years": (2016, 2020), "hard_avoid": None,
     "note": "Astonishing interior space for the footprint. Very reliable."},
    {"make": "Honda", "model": "Accord", "body": "sedan",
     "good_years": (2015, 2022), "hard_avoid": None, "note": ""},
    {"make": "Honda", "model": "HR-V", "body": "small_suv",
     "good_years": (2016, 2022), "hard_avoid": None,
     "note": "Fit mechanicals, higher seating. No turbo, so no dilution issue."},
    {"make": "Honda", "model": "CR-V", "body": "small_suv",
     "good_years": (2015, 2018), "hard_avoid": None,
     "note": "2015-16 uses the 2.4 NA engine; 2017+ is the 1.5T."},
    {"make": "Honda", "model": "Insight", "body": "sedan",
     "good_years": (2019, 2022), "hard_avoid": None,
     "note": "Civic-based hybrid, quietly one of the best buys here."},

    # ---- Mazda ----------------------------------------------------------
    {"make": "Mazda", "model": "Mazda3", "body": "hatchback",
     "good_years": (2015, 2018), "hard_avoid": None,
     "note": "BM/BN gen. 2019+ (BP) has 2.5L oil-consumption reports."},
    {"make": "Mazda", "model": "Mazda6", "body": "sedan",
     "good_years": (2015, 2021), "hard_avoid": None, "note": ""},
    {"make": "Mazda", "model": "CX-3", "body": "small_suv",
     "good_years": (2016, 2021), "hard_avoid": None,
     "note": "Mazda2 underneath. Small, but cheap and trouble-free."},
    {"make": "Mazda", "model": "CX-30", "body": "small_suv",
     "good_years": (2020, 2022), "hard_avoid": None, "note": ""},
    {"make": "Mazda", "model": "CX-5", "body": "small_suv",
     "good_years": (2016, 2022), "hard_avoid": None,
     "note": "Consistently one of the best-rated compact crossovers."},

    # ---- Hyundai --------------------------------------------------------
    {"make": "Hyundai", "model": "Elantra", "body": "sedan",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Nu engine, not the Theta II that plagued the bigger Hyundais."},
    {"make": "Hyundai", "model": "Ioniq", "body": "hatchback",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Hybrid; beats the Prius on economy, loses to it on resale."},
    {"make": "Hyundai", "model": "Kona", "body": "small_suv",
     "good_years": (2018, 2022), "hard_avoid": None, "note": ""},
    {"make": "Hyundai", "model": "Accent", "body": "sedan",
     "good_years": (2018, 2022), "hard_avoid": None, "note": ""},
    {"make": "Hyundai", "model": "Veloster", "body": "hatchback",
     "good_years": (2019, 2021), "hard_avoid": None, "note": ""},

    # ---- Kia ------------------------------------------------------------
    {"make": "Kia", "model": "Soul", "body": "hatchback",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Boxy, cheap, surprisingly practical. Gamma/Nu engines, not Theta."},
    {"make": "Kia", "model": "Forte", "body": "sedan",
     "good_years": (2019, 2022), "hard_avoid": None, "note": ""},
    {"make": "Kia", "model": "Niro", "body": "small_suv",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "Hybrid crossover. Good economy, decent resale."},
    {"make": "Kia", "model": "Rio", "body": "sedan",
     "good_years": (2018, 2022), "hard_avoid": None, "note": ""},
    {"make": "Kia", "model": "Seltos", "body": "small_suv",
     "good_years": (2021, 2022), "hard_avoid": None, "note": ""},

    # ---- Subaru ---------------------------------------------------------
    {"make": "Subaru", "model": "Impreza", "body": "hatchback",
     "good_years": (2017, 2022), "hard_avoid": None,
     "note": "2017+ is the new platform; earlier FB engines burn oil."},
    {"make": "Subaru", "model": "Crosstrek", "body": "small_suv",
     "good_years": (2018, 2022), "hard_avoid": None,
     "note": "AWD if she ends up driving to the mountains."},
    {"make": "Subaru", "model": "Legacy", "body": "sedan",
     "good_years": (2018, 2022), "hard_avoid": None, "note": ""},

    # ---- Nissan / Lexus / VW --------------------------------------------
    {"make": "Nissan", "model": "Versa", "body": "sedan",
     "good_years": (2020, 2022), "hard_avoid": None,
     "note": "2020+ only -- the earlier CVT is a known money pit."},
    {"make": "Nissan", "model": "Sentra", "body": "sedan",
     "good_years": (2020, 2022), "hard_avoid": None,
     "note": "2020 redesign. Avoid anything older on CVT grounds."},
    {"make": "Nissan", "model": "Kicks", "body": "small_suv",
     "good_years": (2018, 2022), "hard_avoid": None, "note": ""},
    {"make": "Lexus", "model": "CT 200h", "body": "hatchback",
     "good_years": (2014, 2017), "hard_avoid": None,
     "note": "Prius Gen 3 drivetrain in a nicer shell -- same EGR caution."},
    {"make": "Volkswagen", "model": "Golf", "body": "hatchback",
     "good_years": (2015, 2021), "hard_avoid": None,
     "note": "Great to drive, thinner resale and pricier parts than the Japanese."},
    {"make": "Volkswagen", "model": "Jetta", "body": "sedan",
     "good_years": (2019, 2022), "hard_avoid": None,
     "note": "2019+ MQB. Earlier cars have timing-chain tensioner history."},
]

# API queries are grouped so several models ride in one call -- auto.dev
# accepts comma-separated makes and models. Keep groups to one or two makes
# so a single group's result set stays paginatable.
#
# Order matters: smallest result sets first. A group that finishes early
# hands its unused pages to the groups after it, so the big makes (Toyota,
# Honda: ~300 listings each) go last and pick up the leftovers. With them
# first they were cut off at 200 and a third of their listings never seen.
QUERY_GROUPS = [
    ["Subaru"],
    ["Mazda"],
    ["Nissan", "Lexus", "Volkswagen"],
    ["Hyundai", "Kia"],
    ["Toyota"],
    ["Honda"],
]

# ---------------------------------------------------------------- filters
EXCLUDE_COLORS = ["red", "burgundy", "maroon", "crimson", "ruby", "barcelona",
                  "scarlet", "cardinal"]

# Body styles, most preferred first. Anything not listed is rejected.
BODY_PREFERENCE = ["hatchback", "sedan", "small_suv"]

REQUIRE_CLEAN_TITLE = True

# ------------------------------------------------------------- insurance
# Insurance was missing from this model entirely, which made every "cost to
# own" figure roughly a third too low. It is also not flat across the board:
# a midsize sedan costs meaningfully more to insure than an economy hatch.
#
# GET A REAL QUOTE AND PUT IT HERE. Published averages disagree wildly --
# one 2026 survey puts a CR-V at $1,249/yr and another at $2,316, because
# they assume different coverage and different drivers. California runs high,
# and a new in-state policyholder with no local history runs higher still.
# This default is a placeholder that is honest about being one.
INSURANCE_BASE_ANNUAL = 2000      # full coverage, clean record, California
INSURANCE_IS_ESTIMATE = True      # flips off once you've entered a real quote

# Relative cost to insure, by the kind of car. Anchored on published 2026
# rate surveys where a Crosstrek/CR-V sit at the baseline, a RAV4 a little
# above, and a Camry ~25% above that.
INSURANCE_FACTOR = {
    "economy":      0.92,   # Yaris, Rio, Accent, Versa, Fit, Mirage
    "compact":      1.00,   # Corolla, Civic, Elantra, Mazda3, Forte, Impreza
    "hybrid":       1.06,   # pricier to repair than the shell suggests
    "midsize":      1.15,   # Camry, Accord, Mazda6, Legacy, Jetta
    "small_suv":    1.02,   # HR-V, CX-3, CX-30, Kona, Kicks, C-HR, Crosstrek
    "compact_suv":  1.06,   # RAV4, CR-V, CX-5
    "sporty":       1.18,   # Veloster, Golf, CT 200h
}

# Which bucket each model falls in. Anything unlisted lands in "compact".
INSURANCE_CLASS = {
    ("toyota", "yaris"): "economy", ("toyota", "yaris ia"): "economy",
    ("kia", "rio"): "economy", ("hyundai", "accent"): "economy",
    ("nissan", "versa"): "economy", ("honda", "fit"): "economy",
    ("toyota", "prius"): "hybrid", ("toyota", "prius prime"): "hybrid",
    ("toyota", "prius c"): "hybrid", ("toyota", "prius v"): "hybrid",
    ("toyota", "corolla hybrid"): "hybrid", ("toyota", "camry hybrid"): "hybrid",
    ("honda", "insight"): "hybrid", ("hyundai", "ioniq"): "hybrid",
    ("kia", "niro"): "hybrid",
    ("toyota", "camry"): "midsize", ("honda", "accord"): "midsize",
    ("mazda", "mazda6"): "midsize", ("subaru", "legacy"): "midsize",
    ("volkswagen", "jetta"): "midsize",
    ("toyota", "rav4"): "compact_suv", ("honda", "cr-v"): "compact_suv",
    ("mazda", "cx-5"): "compact_suv",
    ("hyundai", "veloster"): "sporty", ("volkswagen", "golf"): "sporty",
    ("lexus", "ct 200h"): "sporty",
}

# ---------------------------------------------------- the walk-away number
# The price at which a car's 8-month cost hits this figure. Anything above
# it and you are paying more than you decided the trip is worth.
#
# Note the history here. The original tolerance was "$3-4k is fine, $6-7k is
# a wash against renting." Both halves turned out to be wrong. Once insurance
# is counted, nothing in 334 San Diego listings comes in under $4,000 and the
# cheapest is $4,702 -- so a $4k target says "walk away from everything."
# And the wash point is not $6-7k: a real quote for the same eight months of
# rental is $9,148, so the true break-even is far higher than assumed.
# $6,000 is ambitious but reachable -- better than about 85% of the board.
TARGET_COST = 6000

# What the same eight months cost if you simply rent instead. Quoted from a
# live San Diego search on 2026-09-19 for 26 Sep 2026 - 26 May 2027 (242
# days), downtown pickup, before any collision waiver. Any car that cannot
# beat this has no business being bought.
RENT_INSTEAD = {
    "Economy (Mitsubishi Mirage or similar)": 9148,
    "Compact (Nissan Versa or similar)": 9170,
    "Intermediate (Toyota Corolla or similar)": 9257,
    "Standard (VW Jetta or similar)": 9743,
    "Full-size (Nissan Altima or similar)": 9932,
}

# --------------------------------------------------------- time budgets
# Craigslist is a bonus source, not a required one, and it must never be
# able to stop the run from writing a report. A scheduled run was killed by
# its own 20-minute limit doing exactly that.
CRAIGSLIST_TIME_BUDGET = 150      # seconds

# ------------------------------------------------------------- API budget
# auto.dev's free tier is 1,000 calls/month. Rather than a fixed per-run
# cost, the run takes a share of what is left divided by the days remaining
# in the month, so an early-month run can be generous and a late-month one
# throttles itself. out/api_usage.json is the enforced counter.
MAX_API_CALLS_PER_MONTH = 1000     # auto.dev free tier
API_MIN_CALLS_PER_RUN = 6         # always enough for one page per group
# None = no per-run throttle: every run fetches every page, spending as much
# of the monthly allowance as that takes (~60 calls for a full sweep). Set
# back to a number (e.g. 60) to spread the allowance across the month again.
API_MAX_CALLS_PER_RUN = None
API_MAX_PAGES_PER_GROUP = 50      # 20 listings/page; far above any group's size

# ---------------------------------------------------------------- output
TOP_N = None                    # None = show every listing that passes
ALERT_ON_SCORE_ABOVE = 70
