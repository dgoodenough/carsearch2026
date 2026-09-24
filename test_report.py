#!/usr/bin/env python3
"""
Cross-validate the browser's scoring against Python's.

The report recomputes everything client-side when a slider moves, which is
only trustworthy if the JavaScript port of resale.py and score.py agrees
with the original. This runs both over the same listings, at the default
settings and at several slider positions, and fails on any divergence.

    python test_report.py          (requires node on PATH)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

import config
import report
import resale as rs
import score as scoring
from report_js import SCORING_JS

TOL = 0.001         # after removing intermediate rounding these should match exactly


def build_cases():
    """A spread of listings that exercises every branch of the model."""
    from sources import Listing
    raw = [
        # (year, make, model, price, miles, body, seller, accidents)
        (2018, "Toyota", "Prius", 13999, 78000, "hatchback", "dealer", 0),
        (2013, "Toyota", "Prius", 7900, 138000, "hatchback", "private", 2),
        (2021, "Toyota", "Prius Prime", 12999, 84500, "hatchback", "dealer", 0),
        (2017, "Honda", "Civic", 14500, 62000, "sedan", "dealer", 1),
        (2016, "Mazda", "Mazda3", 11300, 119000, "hatchback", "private", None),
        (2019, "Toyota", "RAV4", 17900, 71000, "small_suv", "dealer", 0),
        (2020, "Kia", "Soul", 15200, 48000, "hatchback", "dealer", None),
        (2015, "Subaru", "Impreza", 9800, 141000, "sedan", "private", 3),
        (2022, "Nissan", "Sentra", 16400, 30000, "sedan", "dealer", 0),
        (2017, "Lexus", "CT 200h", 15900, 99000, "hatchback", "dealer", 0),
        # awkward ones
        (2018, "Toyota", "Corolla", 12000, None, "sedan", "dealer", None),
        (2019, "Honda", "Fit", 13000, 55000, "", "private", 0),
    ]
    out = []
    for y, mk, md, pr, mi, body, seller, acc in raw:
        out.append(Listing(source="test", listing_id=f"t{len(out)}", vin=None,
                           year=y, make=mk, model=md, price=pr, miles=mi,
                           color="Silver", body=body, seller_type=seller,
                           accidents=acc, url="http://x"))
    return out


def python_side(listings, profiles, market, cfg):
    rows = []
    for l in listings:
        s = scoring.score_listing(l, cfg, market, profiles)
        key = (l.make.lower(), l.model.lower())
        payload = report._listing_payload(
            l, s, cfg,
            rs.ANNUAL_DEPRECIATION.get(key, rs.DEFAULT_ANNUAL_DEPRECIATION),
            rs.LIQUIDITY.get(key, rs.DEFAULT_LIQUIDITY))
        rows.append((payload, s))
    return rows


class Cfg:
    """A clone of config with overridable hold parameters."""
    def __init__(self, **over):
        for k in dir(config):
            if k.isupper():
                setattr(self, k, getattr(config, k))
        for k, v in over.items():
            setattr(self, k, v)


def main():
    if not shutil.which("node"):
        print("node not found on PATH - skipping the JS cross-check")
        return 0

    import reliability as rel
    listings = build_cases()
    profiles = {}
    for l in listings:
        key = (l.make.lower(), l.model.lower())
        if key not in profiles:
            profiles[key] = rel.build_profile_offline(l.make, l.model, 2010, 2024)
    market = scoring.build_market(listings)

    # slider positions to check: defaults, plus extremes of every parameter
    scenarios = [
        ("defaults", {}, dict(scoring.WEIGHTS)),
        ("hold 3mo", {"HOLD_MONTHS": 3}, dict(scoring.WEIGHTS)),
        ("hold 24mo", {"HOLD_MONTHS": 24}, dict(scoring.WEIGHTS)),
        ("certain private sale", {"PRIVATE_SALE_CONFIDENCE": 1.0}, dict(scoring.WEIGHTS)),
        ("certain instant offer", {"PRIVATE_SALE_CONFIDENCE": 0.0}, dict(scoring.WEIGHTS)),
        ("2500 mi/mo", {"MILES_PER_MONTH": 2500}, dict(scoring.WEIGHTS)),
        ("300 mi/mo", {"MILES_PER_MONTH": 300}, dict(scoring.WEIGHTS)),
        ("cost only", {}, {"net_cost": 60, "reliability": 0, "liquidity": 0,
                           "value": 0, "outlay": 0, "body": 0, "mileage": 0}),
        ("reliability only", {}, {"net_cost": 0, "reliability": 60, "liquidity": 0,
                                  "value": 0, "outlay": 0, "body": 0, "mileage": 0}),
        ("all weights equal", {}, {k: 10 for k in scoring.WEIGHTS}),
    ]

    fails = []
    for name, over, weights in scenarios:
        cfg = Cfg(**over)
        rows = python_side(listings, profiles, market, cfg)
        payloads = [p for p, _ in rows]
        params = {
            "hold": cfg.HOLD_MONTHS, "mpm": cfg.MILES_PER_MONTH,
            "conf": cfg.PRIVATE_SALE_CONFIDENCE,
            "costGood": cfg.COST_GOOD, "costBad": cfg.COST_BAD,
            "sweetSpot": cfg.PRICE_SWEET_SPOT, "priceMax": cfg.PRICE_MAX,
            "maxMiles": cfg.MAX_MILES, "bodyPref": list(cfg.BODY_PREFERENCE),
            "thisYear": __import__("datetime").date.today().year,
        }
        params["insBase"] = cfg.INSURANCE_BASE_ANNUAL
        params["insFactor"] = dict(cfg.INSURANCE_FACTOR)
        params["target"] = cfg.TARGET_COST
        js = (SCORING_JS + "\nconst DATA=" + json.dumps(payloads) +
              ";\nconst P=" + json.dumps(params) + ";\nconst W=" + json.dumps(weights) +
              ";\nconsole.log(JSON.stringify(DATA.map(c=>{const r=scoreOf(c,P,W);"
              "return {score:r.score,total:r.total,loss:r.loss,repairs:r.repairs,"
              "ins:r.ins,walk:walkAway(c,P,P.target),parts:r.parts};})));")
        with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False) as fh:
            fh.write(js)
            tmp = fh.name
        try:
            out = subprocess.run([shutil.which("node"), tmp], capture_output=True,
                                 text=True, timeout=60)
            if out.returncode != 0:
                fails.append(f"{name}: node error {out.stderr.strip()[:200]}")
                continue
            jsres = json.loads(out.stdout)
        finally:
            os.unlink(tmp)

        worst = 0.0
        for i, ((payload, s), j) in enumerate(zip(rows, jsres)):
            # python's score at these weights, from the unrounded parts
            pnum = sum(s["parts_exact"][k] * weights[k] for k in weights)
            pden = sum(weights.values())
            pscore = pnum / pden if pden else 0.0
            d = abs(pscore - j["score"])
            worst = max(worst, d)
            if d > TOL:
                fails.append(f"{name}: row {i} ({payload['y']} {payload['mk']} "
                             f"{payload['md']}) python={pscore:.3f} js={j['score']:.3f}")
            if s.get("cost") and j.get("ins") is not None:
                di = abs(s["cost"]["insurance"] - j["ins"])
                if di > 0:
                    fails.append(f"{name}: row {i} insurance python="
                                 f"{s['cost']['insurance']} js={j['ins']}")
            if s.get("walk_away") is not None and j.get("walk") is not None:
                dw = abs(s["walk_away"] - j["walk"])
                if dw > 6:      # both bisect to within $5
                    fails.append(f"{name}: row {i} walk-away python="
                                 f"{s['walk_away']} js={j['walk']}")
            elif (s.get("walk_away") is None) != (j.get("walk") is None):
                fails.append(f"{name}: row {i} walk-away None mismatch "
                             f"python={s.get('walk_away')} js={j.get('walk')}")
            if s.get("cost") and j["total"] is not None:
                dc = abs(s["cost"]["total"] - j["total"])
                if dc > 1:
                    fails.append(f"{name}: row {i} cost python={s['cost']['total']} "
                                 f"js={j['total']}")
            for k in s["parts_exact"]:
                dp = abs(s["parts_exact"][k] - j["parts"][k])
                if dp > TOL:
                    fails.append(f"{name}: row {i} part {k} "
                                 f"python={s['parts'][k]} js={j['parts'][k]}")
        print(f"  {'ok  ' if worst <= TOL else 'FAIL'} {name:<24} "
              f"max score delta {worst:.4f} over {len(rows)} listings")

    print()
    if fails:
        print(f"{len(fails)} DIVERGENCE(S):")
        for f in fails[:20]:
            print("   ", f)
        return 1
    print("javascript and python agree on every listing in every scenario")
    return 0


if __name__ == "__main__":
    sys.exit(main())
