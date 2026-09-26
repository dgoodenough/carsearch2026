#!/usr/bin/env python3
"""
Car deal finder -- main entry point.

    python run.py                 normal run
    python run.py --demo          run against bundled fixtures (no API keys)
    python run.py --no-reliability   skip NHTSA lookups (faster, offline)
    python run.py --open          open the report when it finishes

Writes out/report.html, out/listings.csv and out/state.json. Anything new
above config.ALERT_ON_SCORE_ABOVE is printed to stdout and appended to
out/alerts.log, which is what the scheduled task surfaces.
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
import traceback
import webbrowser

import config
import score as scoring
import reliability as rel

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "out")
STATE_PATH = os.path.join(OUT, "state.json")


# ------------------------------------------------------------------ gather
def gather(demo=False, snapshot=False):
    listings = []
    if demo:
        import fixtures
        print("  [demo] using bundled fixtures")
        return fixtures.load()

    if snapshot:
        from sources import snapshot as snap
        return snap.fetch(config)

    from sources import autodev, craigslist, manual, snapshot as snap
    for mod in (autodev, craigslist, snap, manual):
        try:
            listings.extend(mod.fetch(config))
        except Exception as exc:
            print(f"  [{mod.NAME}] failed: {type(exc).__name__}: {exc}")
    return listings


def dedupe(listings):
    """
    Collapse the same car seen through more than one source.

    Two passes, because the sources do not agree on what they publish:
    auto.dev gives VINs, the CarGurus snapshot does not, so a VIN-only
    match leaves every cross-source pair sitting in the report twice. The
    second pass catches those on year/make/model/mileage.

    The survivor is the richest record, not the first one seen -- given the
    same car from both sources we want the one carrying the VIN, the CARFAX
    and the accident count. Price is taken from the cheapest listing, since
    that is the number you would actually pay.
    """
    def merge(keep, drop):
        if drop.price is not None and (keep.price is None or drop.price < keep.price):
            keep.price = drop.price
            keep.url = drop.url or keep.url
        for attr in ("vin", "color", "carfax_url", "dealer", "trim", "url"):
            if not getattr(keep, attr) and getattr(drop, attr):
                setattr(keep, attr, getattr(drop, attr))
        if keep.accidents is None and drop.accidents is not None:
            keep.accidents = drop.accidents
        keep.one_owner = keep.one_owner or drop.one_owner
        return keep

    def collapse(items, keyfn):
        best = {}
        order = []
        for l in items:
            k = keyfn(l)
            if k is None:
                order.append(l)
                continue
            if k not in best:
                best[k] = l
                order.append(l)
            else:
                cur = best[k]
                if l.richness() > cur.richness():
                    order[order.index(cur)] = l
                    best[k] = merge(l, cur)
                else:
                    best[k] = merge(cur, l)
        seen = set()
        out = []
        for l in order:
            k = keyfn(l)
            winner = best.get(k, l) if k is not None else l
            if id(winner) not in seen:
                seen.add(id(winner))
                out.append(winner)
        return out

    return collapse(collapse(listings, lambda l: l.vin_key()),
                    lambda l: l.fuzzy_key())


# -------------------------------------------------------------- reliability
def _year_span(t):
    lo, hi = t["good_years"]
    years = set(range(lo - 4, hi + 3))
    if t["hard_avoid"]:
        years |= set(range(t["hard_avoid"][0], t["hard_avoid"][1] + 1))
    return sorted(years)


def load_reliability(mode="live"):
    """mode: live (NHTSA) | offline (curated overlay only) | off (neutral)"""
    profiles = {}
    if mode == "off":
        return {(t["make"].lower(), t["model"].lower()): {} for t in config.TARGETS}

    if mode == "offline":
        for t in config.TARGETS:
            ys = _year_span(t)
            profiles[(t["make"].lower(), t["model"].lower())] = \
                rel.build_profile_offline(t["make"], t["model"], ys[0], ys[-1])
        return profiles

    # A 44-model list is several hundred model-years. Warm them all in
    # parallel first -- sequentially this is minutes of HTTP for nothing.
    jobs = [(t["make"], t["model"], y) for t in config.TARGETS for y in _year_span(t)]

    def progress(done, total):
        print(f"\r  [nhtsa] {done}/{total} model-years fetched", end="", flush=True)

    try:
        cache = rel.prefetch(jobs, progress=progress)
        print(f"\r  [nhtsa] {len(jobs)} model-years ready          ")
    except Exception as exc:
        print(f"\n  [nhtsa] prefetch failed ({exc}); using the curated defect list")
        return load_reliability(mode="offline")

    unchecked = sum(1 for k, v in cache.items() if v.get("error"))
    if unchecked:
        print(f"  [nhtsa] {unchecked} model-year lookup(s) failed - those rows "
              f"are marked 'not checked' rather than scored as clean")

    errs = 0
    for t in config.TARGETS:
        ys = _year_span(t)
        key = (t["make"].lower(), t["model"].lower())
        try:
            profiles[key] = rel.build_profile(t["make"], t["model"], ys[0], ys[-1],
                                              cache=cache)
        except Exception:
            errs += 1
            profiles[key] = rel.build_profile_offline(t["make"], t["model"],
                                                      ys[0], ys[-1])
    if errs:
        print(f"  [nhtsa] {errs} model(s) fell back to the curated list")
    return profiles


# ------------------------------------------------------------------- state
def track(listings, state, today):
    """
    Fold each listing into the price/appearance history and stamp the
    per-listing fields the report reads back out.

    This is the part that answers "has this been sitting?" -- a car that has
    been on the lot 40 days with two price cuts is a car with a motivated
    seller, and that is worth more at the negotiating table than any
    scoring weight.
    """
    hist = state["listings"]
    seen_now = set()

    for l in listings:
        sid = f"{l.source}:{l.listing_id or l.url}"
        seen_now.add(sid)
        rec = hist.get(sid)

        if rec is None:
            rec = {"first_seen": today, "last_seen": today, "prices": []}
            hist[sid] = rec
            l.is_new = True

        prices = rec["prices"]
        if l.price is not None and (not prices or prices[-1][1] != l.price):
            if prices:
                l.prior_price = prices[-1][1]
            prices.append([today, l.price])
        rec["last_seen"] = today
        rec.pop("gone_since", None)

        # keep a light description of the car so vanished listings stay
        # readable in the report after the source stops returning them
        rec["label"] = f"{l.year} {l.make} {l.model}".strip()
        rec["url"] = l.url

        l.first_seen = rec["first_seen"]
        l.days_listed = _days_between(rec["first_seen"], today)
        if prices and l.price is not None:
            l.price_drop = max(0, prices[0][1] - l.price)

    # anything we have seen before and did not see now has gone away
    vanished = []
    for sid, rec in hist.items():
        if sid in seen_now:
            continue
        if rec.get("last_seen") == today:
            continue
        rec.setdefault("gone_since", today)
        if _days_between(rec["gone_since"], today) <= 14:
            vanished.append((sid, rec))
    vanished.sort(key=lambda kv: kv[1].get("gone_since", ""), reverse=True)
    return vanished


def _days_between(a, b):
    try:
        da = datetime.date.fromisoformat(a)
        db = datetime.date.fromisoformat(b)
        return (db - da).days
    except (TypeError, ValueError):
        return 0


def load_state():
    try:
        with open(STATE_PATH) as fh:
            st = json.load(fh)
    except (OSError, ValueError):
        st = {}
    st.setdefault("listings", {})
    # migrate the older flat {"seen": {id: date}} format
    for sid, first in (st.pop("seen", {}) or {}).items():
        st["listings"].setdefault(sid, {"first_seen": first, "last_seen": first,
                                        "prices": []})
    return st


def save_state(state):
    os.makedirs(OUT, exist_ok=True)
    with open(STATE_PATH, "w") as fh:
        json.dump(state, fh, indent=1)


# ------------------------------------------------------------------ output
def write_csv(rows, path):
    if not rows:
        return
    fields = ["score", "year", "make", "model", "trim", "price", "net_cost_8mo",
              "accidents", "one_owner", "carfax_url",
              "loss_private", "loss_instant", "expected_repairs", "fees",
              "miles", "miles_at_sale", "liquidity", "expected_price",
              "under_market", "color", "body", "seller_type", "dealer",
              "city", "source", "reliability", "complaints", "recalls",
              "first_seen", "days_listed", "price_drop", "is_new", "url",
              "reliability_note"]
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for l, s in rows:
            d = l.to_dict()
            proj, cost = s.get("projection"), s.get("cost")
            d.update({
                "score": s["total"],
                "net_cost_8mo": (cost or {}).get("total"),
                "loss_private": (proj or {}).get("loss_private"),
                "loss_instant": (proj or {}).get("loss_instant"),
                "expected_repairs": (cost or {}).get("repairs"),
                "fees": (proj or {}).get("fees"),
                "miles_at_sale": (proj or {}).get("miles_at_sale"),
                "liquidity": (proj or {}).get("liquidity"),
                "expected_price": s["expected_price"],
                "under_market": s["under_market"],
                "reliability": s["parts"]["reliability"],
                "complaints": s["complaints"],
                "recalls": s["recalls"],
                "reliability_note": s["reliability_note"],
            })
            w.writerow(d)


# -------------------------------------------------------------------- main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--snapshot", action="store_true",
                    help="score only the captured real listings in snapshot.json")
    ap.add_argument("--no-reliability", action="store_true")
    ap.add_argument("--open", action="store_true")
    args = ap.parse_args()

    os.makedirs(OUT, exist_ok=True)
    print(f"Car deal finder - {datetime.datetime.now():%Y-%m-%d %H:%M}")
    t0 = time.monotonic()
    lap = lambda what: print(f"  [{time.monotonic() - t0:5.0f}s] {what}")

    print("Fetching listings...")
    raw = gather(demo=args.demo, snapshot=args.snapshot)
    lap("sources done")
    raw = dedupe(raw)
    print(f"  {len(raw)} unique listings")

    lap("deduped")
    print("Scoring model-year reliability...")
    profiles = load_reliability(
        mode="off" if args.no_reliability else ("offline" if args.demo else "live"))

    # hard filters
    kept, rejected = [], {}
    for l in raw:
        why = scoring.hard_filter(l, config)
        if why:
            bucket = why.split(" (")[0]
            rejected[bucket] = rejected.get(bucket, 0) + 1
        else:
            kept.append(l)

    market = scoring.build_market(kept)

    state = load_state()
    today = datetime.date.today().isoformat()
    if args.demo and not state["listings"]:
        import fixtures
        state = fixtures.seed_state(today)
    vanished = track(kept, state, today)

    rows = []
    alerts = []
    drops = []
    for l in kept:
        l.color_unverified = not (l.color or "").strip()
        sc = scoring.score_listing(l, config, market, profiles)
        rows.append((l, sc))
        if l.is_new and sc["total"] >= config.ALERT_ON_SCORE_ABOVE:
            alerts.append((l, sc))
        if l.prior_price is not None and l.price < l.prior_price:
            drops.append((l, sc))

    new_count = sum(1 for l in kept if l.is_new)
    rows.sort(key=lambda r: -r[1]["total"])
    top = rows if config.TOP_N is None else rows[:config.TOP_N]

    stats = {
        "fetched": len(raw), "passed": len(kept), "new": new_count,
        "alerts": len(alerts), "drops": len(drops), "vanished": len(vanished),
        "held": sum(1 for l in kept if l.days_listed >= 21),
        "rejected_summary": (", ".join(f"{v} {k}" for k, v in
                                       sorted(rejected.items(), key=lambda kv: -kv[1]))
                             or "nothing"),
    }

    write_csv(rows, os.path.join(OUT, "listings.csv"))
    import report
    report.build(top, config, stats, drops, vanished,
                 dict(scoring.WEIGHTS), os.path.join(OUT, "report.html"))
    state["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
    save_state(state)

    print(f"\n{stats['passed']} passed filters, {new_count} new, "
          f"{len(drops)} price drops, {stats['held']} sitting 3+ weeks, "
          f"{len(vanished)} gone.")
    print(f"Rejected: {stats['rejected_summary']}")

    unknown = [l for l in kept if l.color_unverified]
    if unknown:
        print(f"\n{len(unknown)} listing(s) had no colour reported - the red filter "
              f"could not be applied to them. They are tagged in the report.")

    if drops:
        print("\nPrice drops since the last run:")
        for l, _ in sorted(drops, key=lambda r: r[0].price - r[0].prior_price):
            print(f"  -${l.prior_price - l.price:,}  {l.year} {l.make} {l.model} "
                  f"${l.prior_price:,} -> ${l.price:,}  (day {l.days_listed})  {l.url}")

    if alerts:
        line = f"\n=== {datetime.datetime.now():%Y-%m-%d %H:%M} - {len(alerts)} new ===\n"
        for l, s in sorted(alerts, key=lambda r: -r[1]["total"]):
            line += (f"  {s['total']:.0f}  {l.year} {l.make} {l.model} "
                     f"${l.price:,} / {l.miles or 0:,}mi / {l.color or '?'} "
                     f"[{l.city}] {l.url}\n")
        print(line)
        with open(os.path.join(OUT, "alerts.log"), "a", encoding="utf-8") as fh:
            fh.write(line)

    lap("report written")
    print(f"\nReport: {os.path.join(OUT, 'report.html')}")
    if args.open:
        webbrowser.open("file://" + os.path.join(OUT, "report.html"))
    return 0


def _log_failure(exc):
    """
    Leave a readable trail. A scheduled task reports success when the process
    exits, whatever happened inside it, so a run that dies silently looks
    exactly like a run that worked -- which is how a crash went unnoticed for
    a day. Write the traceback where it can be found.
    """
    try:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, "last_error.log"), "w", encoding="utf-8") as fh:
            fh.write(f"{datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
            fh.write("".join(traceback.format_exception(
                type(exc), exc, exc.__traceback__)))
    except Exception:
        pass


if __name__ == "__main__":
    try:
        code = main()
    except BaseException as exc:          # including a scheduler kill
        _log_failure(exc)
        print(f"\nFAILED: {type(exc).__name__}: {exc}")
        print(f"Traceback written to {os.path.join(OUT, 'last_error.log')}")
        raise
    sys.exit(code)
