"""Synthetic listings for --demo runs and for the test suite.

These cars are NOT real -- they exist to exercise the filters. Every one
deliberately hits a case that must be handled: red paint, a van, a salvage
title, 180k miles, a $24k ask, a cross-source duplicate. Their links point
at the relevant CarGurus search page rather than a specific car, because
there is no specific car.

For real listings with real per-car links, use `run.py --snapshot`.
"""

from sources import Listing


_SEQ = iter(range(1, 999))


def _l(**kw):
    kw.setdefault("source", "auto.dev")
    kw.setdefault("listing_id", f"demo-{next(_SEQ):03d}")
    kw.setdefault("vin", None)
    kw.setdefault("seller_type", "dealer")
    kw.setdefault("state", "CA")
    # no fake per-car links: point at the real search page for that model
    mk = kw.get("make", "Toyota")
    md = kw.get("model", "Prius")
    slug = f"{mk}-{md}".replace(" ", "-")
    cg = {"Toyota-Prius": "d15", "Toyota-Prius-Prime": "d2418",
          "Toyota-Yaris": "d827", "Toyota-Yaris-iA": "d2566",
          "Mazda-Mazda3": "d214", "Toyota-RAV4": "d306"}.get(slug)
    kw.setdefault("url", (f"https://www.cargurus.com/Cars/l-Used-{slug}"
                          f"-San-Diego-{cg}_L2362" if cg
                          else "https://www.cargurus.com/"))
    return Listing(**kw)


def load():
    return [
        # --- should rank well -------------------------------------------
        _l(year=2018, make="Toyota", model="Prius", trim="Two Eco", price=12450,
           miles=71000, color="Sea Glass Pearl", body="hatchback",
           dealer="Toyota of El Cajon", city="El Cajon", vin="JTDKARFU0J3060001"),
        _l(year=2019, make="Toyota", model="Prius", trim="LE", price=13900,
           miles=64000, color="Classic Silver", body="hatchback",
           dealer="Kearny Mesa Toyota", city="San Diego"),
        _l(year=2020, make="Toyota", model="Prius", trim="L Eco", price=15200,
           miles=48000, color="Blizzard Pearl", body="hatchback",
           dealer="Toyota Chula Vista", city="Chula Vista"),
        _l(year=2018, make="Toyota", model="Prius Prime", trim="Plus", price=14100,
           miles=59000, color="Blue Magnetism", body="hatchback",
           dealer="Escondido Toyota", city="Escondido"),
        _l(year=2017, make="Toyota", model="Prius", trim="Three", price=9800,
           miles=112000, color="White", body="hatchback",
           seller_type="private", source="craigslist", city="sandiego"),
        _l(year=2017, make="Mazda", model="Mazda3", trim="Sport", price=11300,
           miles=78000, color="Machine Gray", body="hatchback",
           dealer="Mazda of Escondido", city="Escondido"),
        _l(year=2018, make="Mazda", model="Mazda3", trim="Touring", price=12900,
           miles=69000, color="Snowflake White", body="sedan",
           dealer="Bob Baker Mazda", city="Carlsbad"),
        _l(year=2019, make="Toyota", model="Yaris", trim="LE", price=10600,
           miles=58000, color="Icy Silver", body="hatchback",
           dealer="Toyota Carlsbad", city="Carlsbad"),
        _l(year=2017, make="Toyota", model="RAV4", trim="LE", price=14800,
           miles=94000, color="Super White", body="small_suv",
           dealer="Toyota Poway", city="Poway"),
        _l(year=2016, make="Toyota", model="RAV4", trim="XLE", price=13200,
           miles=108000, color="Silver Sky", body="small_suv",
           dealer="Frank Toyota", city="National City"),
        # a genuinely underpriced one, to prove the value model finds it
        _l(year=2019, make="Toyota", model="Prius", trim="LE", price=10200,
           miles=68000, color="Magnetic Gray", body="hatchback",
           seller_type="private", source="craigslist", city="sandiego"),

        # --- should rank badly (bad model-year, not rejected) -----------
        _l(year=2019, make="Toyota", model="RAV4", trim="LE", price=17900,
           miles=71000, color="Silver", body="small_suv",
           dealer="Mossy Toyota", city="San Diego"),
        _l(year=2013, make="Toyota", model="Prius", trim="Two", price=7900,
           miles=138000, color="Winter Gray", body="hatchback",
           seller_type="private", source="craigslist", city="sandiego"),

        # --- must be rejected outright ----------------------------------
        _l(year=2018, make="Toyota", model="Prius", trim="Two", price=12900,
           miles=66000, color="Hypersonic Red", body="hatchback",
           dealer="Red Herring Motors", city="San Diego"),
        _l(year=2017, make="Toyota", model="Sienna", trim="LE", price=16500,
           miles=99000, color="White", body="van",
           dealer="Van City", city="San Diego"),
        _l(year=2016, make="Toyota", model="Prius", trim="Two", price=8200,
           miles=181000, color="Black", body="hatchback",
           seller_type="private", source="craigslist", city="sandiego"),
        _l(year=2018, make="Toyota", model="RAV4", trim="XLE", price=24500,
           miles=52000, color="Blue", body="small_suv",
           dealer="Overpriced Auto", city="La Mesa"),
        _l(year=2018, make="Mazda", model="Mazda3", trim="Touring", price=8900,
           miles=71000, color="Gray", body="sedan", title_status="salvage",
           seller_type="private", source="craigslist", city="sandiego"),

        # --- duplicate of the first car, same VIN, different source ------
        _l(year=2018, make="Toyota", model="Prius", trim="Two Eco", price=12995,
           miles=71000, color="Sea Glass Pearl", body="hatchback",
           source="craigslist", seller_type="private", city="sandiego",
           vin="JTDKARFU0J3060001"),
    ]


def seed_state(today):
    """
    Backdate a plausible history for the demo listings so a --demo run shows
    the tracking features off: some cars new today, some sitting for weeks,
    two with price cuts, one that has vanished.
    """
    import datetime
    d = datetime.date.fromisoformat(today)
    ago = lambda n: (d - datetime.timedelta(days=n)).isoformat()

    return {"listings": {
        # sitting 41 days with two cuts -- the negotiable one
        "auto.dev:demo-001": {"first_seen": ago(41), "last_seen": ago(1),
                              "prices": [[ago(41), 13795], [ago(22), 12995]],
                              "label": "2018 Toyota Prius", "url": ""},
        # steady, three weeks in
        "auto.dev:demo-002": {"first_seen": ago(23), "last_seen": ago(1),
                              "prices": [[ago(23), 13900]],
                              "label": "2019 Toyota Prius", "url": ""},
        # a week old, just cut
        "auto.dev:demo-004": {"first_seen": ago(8), "last_seen": ago(1),
                              "prices": [[ago(8), 14900]],
                              "label": "2018 Toyota Prius Prime", "url": ""},
        "craigslist:demo-005": {"first_seen": ago(4), "last_seen": ago(1),
                                "prices": [[ago(4), 9800]],
                                "label": "2017 Toyota Prius", "url": ""},
        "auto.dev:demo-009": {"first_seen": ago(31), "last_seen": ago(1),
                              "prices": [[ago(31), 14800]],
                              "label": "2017 Toyota RAV4", "url": ""},
        # seen before, gone now
        "auto.dev:demo-gone1": {"first_seen": ago(26), "last_seen": ago(2),
                                "prices": [[ago(26), 11750]],
                                "label": "2018 Toyota Prius Two Eco", "url": ""},
        "craigslist:demo-gone2": {"first_seen": ago(14), "last_seen": ago(2),
                                  "prices": [[ago(14), 10400]],
                                  "label": "2017 Mazda Mazda3 Sport", "url": ""},
    }}
