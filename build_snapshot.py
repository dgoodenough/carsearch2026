#!/usr/bin/env python3
"""
Builds snapshot.json from listings read off CarGurus' San Diego search pages
on 2026-09-19.

Why a snapshot instead of a scraper: CarGurus serves its search pages fine
but blocks automated clients, so this is a point-in-time capture rather than
something run on a schedule. The live daily feed is auto.dev. This exists so
there is a real, clickable shortlist before the API key is set up.

Per-listing links use https://www.cargurus.com/Cars/link/<listingId>, which
is the form that actually resolves -- vdp.action?listingId=... redirects to
the homepage.

Scope: San Diego County plus Temecula/Murrieta. Nationwide-shipping listings
from Florida, Illinois, Arizona and so on are dropped -- they are no use for
a car you need to look at in person on the 25th.
"""

import json

CAPTURED = "2026-09-19"
LINK = "https://www.cargurus.com/Cars/link/{}"

# (year, model, trim, price, miles, color, body, city, listingId)
ROWS = [
    # ---- Toyota Prius ------------------------------------------------
    (2018, "Prius", "One FWD",        16138, 119578, "Blizzard Pearl White", "hatchback", "Vista",       419308740),
    (2016, "Prius", "Three Touring",  16195, 115960, "Blizzard Pearl White", "hatchback", "Temecula",    457647176),
    (2015, "Prius", "Two",            15488,  56900, "White",                "hatchback", "Escondido",   457748364),
    (2015, "Prius", "Two",            18147,  80514, "White",                "hatchback", "San Diego",   458883639),
    (2015, "Prius", "Two",            15998,  99710, "Silver",               "hatchback", "San Diego",   458709912),
    (2015, "Prius", "Four",           16147, 105842, "Gray",                 "hatchback", "San Diego",   456806919),
    (2015, "Prius", "Four",           13335, 121877, "White",                "hatchback", "Escondido",   455027377),
    (2013, "Prius", "Two",            10020, 143322, "Black",                "hatchback", "Oceanside",   457371002),
    (2012, "Prius", "Three",           7888, 133000, "Black",                "hatchback", "Escondido",   457748361),
    (2011, "Prius", "Two",             8079, 134033, "Silver",               "hatchback", "San Diego",   455132295),
    (2010, "Prius", "Two",             7566, 142716, "Blue Ribbon Metallic", "hatchback", "Temecula",    455776088),
    (2006, "Prius", "FWD",            10990,  75196, "Red",                  "hatchback", "Carlsbad",    453030090),

    # ---- Toyota Prius Prime ------------------------------------------
    (2021, "Prius Prime", "LE FWD",   12999,  84500, "Gray",                 "hatchback", "San Diego",   459117055),
    (2020, "Prius Prime", "XLE FWD",  18998, 125239, "Gray",                 "hatchback", "San Diego",   459243676),
    (2017, "Prius Prime", "Premium",  18998, 100679, "White",                "hatchback", "San Diego",   455851240),
    (2020, "Prius Prime", "LE FWD",   18428,  94500, "Red",                  "hatchback", "Escondido",   447090522),

    # ---- Toyota Yaris -------------------------------------------------
    (2020, "Yaris", "LE Hatchback",   16071,  82898, "Gray",                 "hatchback", "Vista",       449248236),
    (2016, "Yaris", "SE",             16998,  53085, "White",                "hatchback", "San Diego",   457919134),
    (2015, "Yaris", "L 2dr",          17997,  71444, "Silver",               "hatchback", "San Diego",   457051095),
    (2019, "Yaris", "L Sedan FWD",    15998,  67423, "Gray",                 "sedan",     "Murrieta",    457013277),
    (2019, "Yaris", "LE Sedan FWD",   16497, 124220, "Gray",                 "sedan",     "San Diego",   457337691),
    (2019, "Yaris", "L Sedan FWD",    19597,  54802, "Silver",               "sedan",     "San Diego",   459161777),
    (2020, "Yaris", "FWD",            20497,  73072, "Burgundy",             "sedan",     "San Diego",   458299288),

    # ---- Toyota Yaris iA (uncle's lead is 457647353) -------------------
    (2017, "Yaris iA", "Base",        10749, 140474, "Stealth Gray",         "sedan",     "Poway",       457647353),
    (2017, "Yaris iA", "Base",        10979, 105918, "White",                "sedan",     "Temecula",    454664700),
    (2017, "Yaris iA", "Base",        10964, 123673, "Gray",                 "sedan",     "San Diego",   457287338),
    (2018, "Yaris iA", "Base",        15477,  64223, "Silver",               "sedan",     "Poway",       451632991),

    # ---- Mazda3 --------------------------------------------------------
    (2018, "Mazda3", "Touring Hatch", 15998,  91987, "Gray",                 "hatchback", "San Diego",   459361021),
    (2018, "Mazda3", "Grand Touring", 15985,  75182, "White",                "sedan",     "San Diego",   443112969),
    (2020, "Mazda3", "Premium AWD",   16599,  96957, "Snowflake White Pearl","sedan",     "San Diego",   455601153),
    (2017, "Mazda3", "Sport Sedan",   10373, 134772, "Snowflake White Pearl","sedan",     "El Cajon",    456411084),
    (2016, "Mazda3", "i Grand Touring",17171, 71948, "Soul Red Metallic",    "hatchback", "San Diego",   452922678),
    (2015, "Mazda3", "i Touring",     13592,  86751, "Red Metallic",         "hatchback", "Chula Vista", 458685678),
    (2015, "Mazda3", "i Touring",     11529, 114376, "Red Metallic",         "sedan",     "Lemon Grove", 457894478),
    (2014, "Mazda3", "i Touring",      9085, 127067, "Silver",               "sedan",     "Escondido",   448072837),
    (2015, "Mazda3", "i Sport",        7169, 135042, "Deep Crystal Blue",    "sedan",     "Oceanside",   456006426),
    (2011, "Mazda3", "i Touring",      7040, 117468, "Crystal White Pearl",  "sedan",     "San Diego",   459048637),
    (2010, "Mazda3", "s Sport",        7583, 124780, "Silver",               "hatchback", "San Diego",   456694561),
    (2013, "Mazda3", "i SV",           6999, 113785, "Unlisted",             "sedan",     "Temecula",    458814547),
    (2012, "Mazda3", "i Sport",        5960, 116880, "Unlisted",             "sedan",     "San Diego",   456960220),

    # ---- Toyota RAV4 ----------------------------------------------------
    (2017, "RAV4", "LE",              16999,  83419, "Blue",                 "small_suv", "San Diego",   449548294),
    (2016, "RAV4", "LE",              18060,  73221, "Black",                "small_suv", "Spring Valley",456990326),
    (2018, "RAV4", "LE",              17076, 104938, "Black",                "small_suv", "Temecula",    458299683),
    (2017, "RAV4", "LE",              17291, 113505, "Super White",          "small_suv", "Chula Vista", 457845922),
    (2017, "RAV4", "Limited",         18622, 121100, "Magnetic Gray",        "small_suv", "Temecula",    454767873),
    (2017, "RAV4", "XLE AWD",         15129, 129423, "White",                "small_suv", "San Diego",   438766343),
    (2015, "RAV4", "Limited",         17422,  91230, "Magnetic Gray",        "small_suv", "El Cajon",    448119606),
    (2015, "RAV4", "Limited",         17444,  97917, "Blizzard Pearl White", "small_suv", "Carlsbad",    457433711),
    (2014, "RAV4", "XLE",             14622,  94399, "Magnetic Gray",        "small_suv", "El Cajon",    448507044),
    (2015, "RAV4", "XLE",             13695, 131336, "Super White",          "small_suv", "Oceanside",   459312059),
    (2017, "RAV4", "SE",              15421, 144642, "Black",                "small_suv", "Chula Vista", 457845940),
    (2016, "RAV4", "LE AWD",          14985, 137862, "White",                "small_suv", "San Diego",   445472768),
    (2019, "RAV4", "Limited FWD",     18995, 141568, "Gray",                 "small_suv", "San Diego",   454189846),
    (2021, "RAV4", "LE FWD",          17413, 149097, "White",                "small_suv", "Chula Vista", 459376096),
]

MAKE = {"Mazda3": "Mazda"}


def build():
    out = []
    for year, model, trim, price, miles, color, body, city, lid in ROWS:
        out.append({
            "source": "cargurus-snapshot",
            "listing_id": str(lid),
            "vin": None,
            "year": year,
            "make": MAKE.get(model, "Toyota"),
            "model": model,
            "trim": trim,
            "price": price,
            "miles": miles,
            "color": color,
            "body": body,
            "title_status": "clean",
            "seller_type": "dealer",
            "dealer": "",
            "city": city,
            "state": "CA",
            "url": LINK.format(lid),
        })
    return {"captured": CAPTURED, "listings": out}


if __name__ == "__main__":
    data = build()
    with open("snapshot.json", "w") as fh:
        json.dump(data, fh, indent=1)
    print(f"{len(data['listings'])} real listings written to snapshot.json")
