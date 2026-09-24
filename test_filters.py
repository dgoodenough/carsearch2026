#!/usr/bin/env python3
"""Smoke tests for the filters, market fit and reliability overlay.

    python test_filters.py
"""
import sys
import config
import score as sc
import reliability as rl
from sources import Listing

FAILS = []


def L(**kw):
    kw.setdefault("source", "auto.dev")
    kw.setdefault("listing_id", "x")
    kw.setdefault("vin", None)
    kw.setdefault("year", 2018)
    kw.setdefault("make", "Toyota")
    kw.setdefault("model", "Prius")
    return Listing(**kw)


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def main():
    hf = lambda **kw: sc.hard_filter(L(**kw), config)
    print("hard filters:")
    check("rejects red", hf(color="Hypersonic Red", price=9000, miles=50000, body="hatchback"))
    check("rejects Barcelona Red", hf(color="Barcelona Red Metallic", price=9000, miles=50000, body="hatchback"))
    check("accepts Sea Glass Pearl", hf(color="Sea Glass Pearl", price=9000, miles=50000, body="hatchback") is None)
    check("rejects van", hf(color="White", price=9000, miles=50000, body="van"))
    check("rejects truck", hf(color="White", price=9000, miles=50000, body="truck"))
    check("rejects 151k miles", hf(color="White", price=9000, miles=151000, body="sedan"))
    # 149k passes the raw cap but crosses 150k during the hold, so it is out
    check("rejects 149k (crosses 150k during the hold)",
          hf(color="White", price=9000, miles=149000, body="sedan"))
    check("accepts 141k miles", hf(color="White", price=9000, miles=141000, body="sedan") is None)
    check("rejects over budget", hf(color="White", price=20001, miles=50000, body="sedan"))
    check("rejects salvage", hf(color="White", price=9000, miles=50000, body="sedan", title_status="Salvage"))
    check("rejects rebuilt", hf(color="White", price=9000, miles=50000, body="sedan", title_status="rebuilt title"))
    check("craigslist w/o price survives",
          hf(source="craigslist", color="White", price=None, miles=None, body="hatchback") is None)
    check("dealer w/o price rejected", hf(color="White", price=None, miles=50000, body="hatchback"))
    check("unknown mileage survives", hf(color="White", price=9000, miles=None, body="hatchback") is None)

    print("market fit:")
    check("empty input", sc.build_market([]) == {})
    check("priceless input", sc.build_market([L(price=None, miles=5)]) == {})
    m = sc.build_market([L(price=10000 + i * 100, miles=60000 + i * 1000, year=2017 + i % 4)
                         for i in range(12)])
    check("12 comps produce a predictor",
          ("toyota", "prius") in m and callable(m[("toyota", "prius")][0]))
    check("cohort size recorded", m[("toyota", "prius")][1] == 12)

    print("scoring:")
    s = sc.score_listing(L(price=9000, miles=50000, color="White", body="hatchback"), config, {}, {})
    check("score in range", 0 <= s["total"] <= 100)
    check("neutral value with no comps", s["parts"]["value"] == 50.0)
    check("outlay 100 at the target", s["parts"]["outlay"] == 100.0)
    s2 = sc.score_listing(L(price=20000, miles=50000, color="White", body="hatchback"), config, {}, {})
    check("outlay 0 at the ceiling", s2["parts"]["outlay"] == 0.0)
    check("hatchback outranks small SUV",
          sc.score_listing(L(price=9000, miles=5, color="W", body="hatchback"), config, {}, {})["parts"]["body"]
          > sc.score_listing(L(price=9000, miles=5, color="W", body="small_suv"), config, {}, {})["parts"]["body"])

    print("resale / net cost:")
    import resale as rs
    check("rejects a car that crosses 150k during the hold",
          hf(color="White", price=9000, miles=145000, body="sedan"))
    check("accepts one that stays under",
          hf(color="White", price=9000, miles=140000, body="sedan") is None)
    priv = sc.score_listing(L(price=11000, miles=80000, color="W", body="hatchback",
                              seller_type="private"), config, {}, {})
    deal = sc.score_listing(L(price=11000, miles=80000, color="W", body="hatchback",
                              seller_type="dealer"), config, {}, {})
    check("private party beats the identical dealer car",
          priv["cost"]["total"] < deal["cost"]["total"])
    lo = sc.score_listing(L(price=11000, miles=60000, color="W", body="hatchback"), config, {}, {})
    hi = sc.score_listing(L(price=11000, miles=135000, color="W", body="hatchback"), config, {}, {})
    check("high mileage costs more to own at the same price",
          hi["cost"]["total"] > lo["cost"]["total"])
    check("liquidity drops with mileage",
          hi["parts"]["liquidity"] < lo["parts"]["liquidity"])
    bad = sc.score_listing(L(price=8000, miles=100000, color="W", body="hatchback"),
                           config, {}, {("toyota", "prius"): {2018: {"score": 20, "why": ""}}})
    good = sc.score_listing(L(price=8000, miles=100000, color="W", body="hatchback"),
                            config, {}, {("toyota", "prius"): {2018: {"score": 90, "why": ""}}})
    check("unreliable model-year carries a higher expected repair bill",
          bad["cost"]["repairs"] > good["cost"]["repairs"])
    p8 = rs.project(12000, 80000, 2018, "Toyota", "Prius", "private")
    check("fees land in a sane California range", 1000 < p8["fees"] < 1800)
    check("instant offer is below private party",
          p8["instant_resale"] < p8["private_resale"])

    print("reliability overlay:")
    p = rl.build_profile_offline("Toyota", "RAV4", 2016, 2021, extra_years=[2019])
    check("2019 RAV4 penalised", p[2019]["score"] < p[2017]["score"])
    check("2019 RAV4 carries a reason", "XA50" in p[2019]["why"])
    pp = rl.build_profile_offline("Toyota", "Prius", 2012, 2020)
    check("Gen 3 Prius penalised", pp[2013]["score"] < pp[2018]["score"])

    print("dedupe across sources:")
    import run as R
    a = L(source="auto.dev", listing_id="1", vin="VIN123", price=12999, miles=84500,
          color="Magnetic Gray", accidents=0, one_owner=True,
          carfax_url="http://cf", url="http://ad")
    b = L(source="cargurus-snapshot", listing_id="9", price=12999, miles=84500,
          color="Gray", url="http://cg")
    c = L(source="cargurus-snapshot", listing_id="7", price=7169, miles=135042,
          year=2015, url="http://cg2")
    d = L(source="auto.dev", listing_id="8", vin="VIN999", price=6995, miles=135042,
          year=2015, accidents=1, url="http://ad2")
    e = L(listing_id="solo", price=15477, miles=64223)
    out = R.dedupe([a, b, c, d, e])
    check("5 listings collapse to 3", len(out) == 3)
    check("the VIN-bearing record survives a cross-source pair",
          any(l.vin == "VIN123" and l.accidents == 0 for l in out))
    check("the merged record keeps the CARFAX", any(l.carfax_url == "http://cf" for l in out))
    check("same car at two prices collapses to the cheaper",
          any(l.miles == 135042 and l.price == 6995 for l in out))
    check("an unmatched listing is left alone", any(l.listing_id == "solo" for l in out))
    check("dedupe of an empty list is empty", R.dedupe([]) == [])
    check("no Listing still exposes the removed .key()",
          not hasattr(a, "key"))

    print("api budget guard:")
    import datetime, json, os
    from sources import autodev as ad
    month = datetime.date.today().strftime("%Y-%m")
    os.makedirs(os.path.dirname(ad.USAGE_PATH), exist_ok=True)
    saved = None
    if os.path.exists(ad.USAGE_PATH):
        saved = open(ad.USAGE_PATH).read()

    class _cfg:
        TARGETS = [{"make": m, "model": "Prius", "body": "hatchback",
                    "good_years": (2017, 2022), "hard_avoid": None}
                   for m in ("Toyota", "Honda", "Mazda", "Kia", "Subaru", "Nissan")]
        QUERY_GROUPS = [[m] for m in ("Toyota", "Honda", "Mazda", "Kia",
                                      "Subaru", "Nissan")]
        ZIP, RADIUS_MILES, PRICE_MIN, PRICE_MAX = "92101", 75, 3000, 20000
        MAX_MILES = 150000
        MAX_API_CALLS_PER_MONTH = 800
        API_MIN_CALLS_PER_RUN, API_MAX_CALLS_PER_RUN = 6, 60
        API_MAX_PAGES_PER_GROUP = 1

    calls = {"n": 0}
    real_get, real_key = ad._get, os.environ.get("AUTODEV_API_KEY")
    ad._get = lambda *a, **k: (calls.__setitem__("n", calls["n"] + 1), {"records": []})[1]
    os.environ["AUTODEV_API_KEY"] = "test"
    try:
        json.dump({month: 800}, open(ad.USAGE_PATH, "w"))
        ad.fetch(_cfg, verbose=False)
        check("at the cap, no calls are made", calls["n"] == 0)

        json.dump({month: 797}, open(ad.USAGE_PATH, "w"))
        calls["n"] = 0
        ad.fetch(_cfg, verbose=False)
        check("near the cap, it stops at the boundary", calls["n"] == 3)
        # the invariant that matters: never promise more than is left
        ok = True
        for u in (0, 400, 780, 797, 800, 900):
            json.dump({month: u}, open(ad.USAGE_PATH, "w"))
            allow, used_, cap_ = ad._calls_allowed(_cfg)
            if allow > max(cap_ - u, 0):
                ok = False
        check("the run allowance never exceeds what is left", ok)
        json.dump({month: 797}, open(ad.USAGE_PATH, "w"))

        json.dump({month: 0}, open(ad.USAGE_PATH, "w"))
        calls["n"] = 0
        ad.fetch(_cfg, verbose=False)
        check("with budget, one call per target", calls["n"] == 6)
    finally:
        ad._get = real_get
        if real_key is None:
            os.environ.pop("AUTODEV_API_KEY", None)
        else:
            os.environ["AUTODEV_API_KEY"] = real_key
        if saved is not None:
            open(ad.USAGE_PATH, "w").write(saved)
        elif os.path.exists(ad.USAGE_PATH):
            os.remove(ad.USAGE_PATH)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        return 1
    print("all tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
