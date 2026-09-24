#!/usr/bin/env python3
"""
Simulates several days of runs to prove the tracking works: a listing that
sticks around accrues days, a price cut is detected and attributed, and a
listing that stops appearing is reported as gone.

    python test_tracking.py
"""
import datetime
import json
import os
import sys

import run as R
from sources import Listing

FAILS = []


def check(name, cond):
    print(("  ok   " if cond else "  FAIL ") + name)
    if not cond:
        FAILS.append(name)


def car(lid, price):
    return Listing(source="auto.dev", listing_id=lid, vin=None, year=2018,
                   make="Toyota", model="Prius", price=price, miles=70000,
                   color="White", body="hatchback", url=f"http://x/{lid}")


def main():
    state = {"listings": {}}
    d = lambda n: (datetime.date(2026, 9, 1) + datetime.timedelta(days=n)).isoformat()

    # --- day 0: two cars appear -------------------------------------------
    a, b = car("A", 13000), car("B", 15000)
    R.track([a, b], state, d(0))
    check("both flagged new on day 0", a.is_new and b.is_new)
    check("day count starts at 0", a.days_listed == 0)

    # --- day 10: A holds, B is cut by $700 --------------------------------
    a, b = car("A", 13000), car("B", 14300)
    R.track([a, b], state, d(10))
    check("neither is new on day 10", not a.is_new and not b.is_new)
    check("A shows 10 days listed", a.days_listed == 10)
    check("B's cut detected", b.prior_price == 15000 and b.price_drop == 700)
    check("A shows no cut", a.price_drop == 0)

    # --- day 30: A cut too, B vanishes, C appears -------------------------
    a, c = car("A", 12250), car("C", 11000)
    vanished = R.track([a, c], state, d(30))
    check("A's cut detected", a.prior_price == 13000 and a.price_drop == 750)
    check("A shows 30 days listed", a.days_listed == 30)
    check("C is new", c.is_new and c.days_listed == 0)
    check("B reported gone", any(sid.endswith(":B") for sid, _ in vanished))
    check("A not reported gone", not any(sid.endswith(":A") for sid, _ in vanished))

    # --- day 31: B comes back (relisted) ----------------------------------
    a, b = car("A", 12250), car("B", 13900)
    vanished = R.track([a, b], state, d(31))
    check("B no longer gone", not any(sid.endswith(":B") for sid, _ in vanished))
    check("B keeps its original first_seen", b.first_seen == d(0))
    check("B's full drop from $15,000", b.price_drop == 1100)

    # --- price history is complete ----------------------------------------
    hist = state["listings"]["auto.dev:B"]["prices"]
    check("B has 3 price points", len(hist) == 3)
    check("B history is chronological",
          [p[1] for p in hist] == [15000, 14300, 13900])

    # --- state survives a save/load round trip ----------------------------
    R.OUT = os.path.dirname(os.path.abspath(__file__))
    R.STATE_PATH = os.path.join(R.OUT, "out", "_test_state.json")
    R.save_state(state)
    reloaded = R.load_state()
    check("state round-trips", reloaded["listings"]["auto.dev:B"]["prices"] == hist)
    os.remove(R.STATE_PATH)

    # --- legacy state migrates -------------------------------------------
    legacy = {"seen": {"auto.dev:Z": "2026-08-01"}}
    with open(R.STATE_PATH, "w") as fh:
        json.dump(legacy, fh)
    migrated = R.load_state()
    check("old state format migrates",
          migrated["listings"]["auto.dev:Z"]["first_seen"] == "2026-08-01")
    os.remove(R.STATE_PATH)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        return 1
    print("all tracking tests passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
