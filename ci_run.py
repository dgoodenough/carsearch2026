#!/usr/bin/env python3
"""
The entry point GitHub Actions runs. Same pipeline as run.py, but it writes
the board to docs/index.html (which GitHub Pages serves) and it refuses to
publish a broken board over a good one.

That last part is the whole reason this file exists rather than reusing
run.py. On the road the published page is the only copy anyone looks at, so
a run that fetched nothing -- an expired key, an API outage, a bad query --
must fail loudly and leave yesterday's page standing, not quietly replace it
with an empty table that looks like "no cars matched".

    python ci_run.py            fetch, score, write docs/index.html
    python ci_run.py --dry-run  do it from snapshot.json, touch nothing live
"""
import datetime
import json
import os
import sys

import config
import report
import score as scoring
import run as R

HERE = os.path.dirname(os.path.abspath(__file__))
DOCS = os.path.join(HERE, "docs")

# If a run returns fewer than this, something is wrong upstream -- publishing
# it would throw away a working board. Tuned well under a normal run (~1,100)
# but above any plausible quiet day.
MIN_LISTINGS = 120

INTRO = """
  <div class="intro">
    <h2>What you're looking at</h2>
    <p>Every used car within {radius} miles of San Diego under ${pmax:,}
       &mdash; {models} &mdash; refreshed automatically. Ashley needs one for
       about {hold} months during the whale-watching program, and then we sell it.</p>
    <p>It is <b>not sorted by price</b>. It is sorted by what each car costs across the
       whole round trip: purchase price, plus California tax and registration, plus
       insurance and a realistic repair allowance, minus what it should resell for at the
       end. That is the <b>Cost to own</b> column. A $7k car that is hard to resell can
       easily cost more than an $11k one that isn't.</p>
    <p><b>Walk away above</b> is the most you can pay for that specific car and still hit
       the target. That is the number to have in your pocket on a lot.</p>
    <p><b>Tick the boxes</b> on the rows worth seeing, then hit <b>Shortlist</b> for a
       clean one-page list you can print, save as a PDF or read off in the car.</p>
    <p><b>Click any column to sort.</b> The sliders re-rank the whole board live &mdash;
       they recompute the real arithmetic, they don't just reorder a fixed number.</p>
  </div>
"""


def summary(text):
    """Write to the Actions run summary when there is one, else stdout."""
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(text + "\n")


def main():
    dry = "--dry-run" in sys.argv
    started = datetime.datetime.now()
    print(f"Car deal finder (CI) - {started:%Y-%m-%d %H:%M}")

    raw = R.dedupe(R.gather(snapshot=dry))
    print(f"  {len(raw)} unique listings")

    if not dry and len(raw) < MIN_LISTINGS:
        summary(f"### Refresh aborted\n\nOnly **{len(raw)}** listings came back "
                f"(expected at least {MIN_LISTINGS}). The published board was left "
                f"untouched rather than overwritten with a broken one.\n\n"
                f"Usual causes: the auto.dev key expired or hit its monthly cap, "
                f"or the API is down. Check the step log above.")
        return 2

    profiles = R.load_reliability(mode="live")

    kept, rejected = [], {}
    for l in raw:
        why = scoring.hard_filter(l, config)
        if why:
            b = why.split(" (")[0]
            rejected[b] = rejected.get(b, 0) + 1
        else:
            kept.append(l)

    if not kept:
        summary("### Refresh aborted\n\nEvery listing was filtered out, which means a "
                "filter is misconfigured. Board left untouched.")
        return 2

    market = scoring.build_market(kept)
    state = R.load_state()
    today = datetime.date.today().isoformat()
    vanished = R.track(kept, state, today)

    rows, drops = [], []
    for l in kept:
        l.color_unverified = not (l.color or "").strip()
        sc = scoring.score_listing(l, config, market, profiles)
        rows.append((l, sc))
        if l.prior_price is not None and l.price < l.prior_price:
            drops.append((l, sc))
    rows.sort(key=lambda r: -r[1]["total"])

    stats = {
        "fetched": len(raw), "passed": len(kept),
        "new": sum(1 for l in kept if l.is_new),
        "alerts": 0, "drops": len(drops), "vanished": len(vanished),
        "held": sum(1 for l in kept if l.days_listed >= 21),
        "rejected_summary": ", ".join(f"{v} {k}" for k, v in
                                      sorted(rejected.items(), key=lambda kv: -kv[1]))
                            or "nothing",
    }

    from sources import autodev
    used = autodev.used_this_month()
    usage = {"used": used, "cap": config.MAX_API_CALLS_PER_MONTH,
             "left": max(config.MAX_API_CALLS_PER_MONTH - used, 0),
             "perRun": config.API_MAX_CALLS_PER_RUN}

    intro = INTRO.format(
        models=f"{len(rows)} listings across "
               f"{len({(l.make, l.model) for l, _ in rows})} models and "
               f"{len({l.make for l, _ in rows})} makes",
        radius=config.RADIUS_MILES, pmax=config.PRICE_MAX, hold=config.HOLD_MONTHS)

    os.makedirs(DOCS, exist_ok=True)
    out = os.path.join(DOCS, "index.html")
    n = report.build(rows, config, stats, drops, vanished,
                     dict(scoring.WEIGHTS), out, mode="local", intro=intro,
                     title="Ashley's Car Search", usage=usage)

    # Pages serves this directory verbatim; without this, Jekyll eats it.
    open(os.path.join(DOCS, ".nojekyll"), "w").close()
    R.write_csv(rows, os.path.join(DOCS, "listings.csv"))

    if not dry:
        state["last_run"] = datetime.datetime.now().isoformat(timespec="seconds")
        R.save_state(state)

    top = "\n".join(
        f"| {s['total']:.0f} | {l.year} {l.make} {l.model} | ${l.price:,} | "
        f"{(l.miles or 0):,} | ${s['cost']['total']:,} | ${s['walk_away']:,} |"
        for l, s in rows[:10])
    summary(
        f"### Board refreshed\n\n"
        f"**{stats['passed']}** of {stats['fetched']} listings passed · "
        f"**{stats['new']}** new · **{stats['drops']}** price cuts · "
        f"**{stats['vanished']}** gone · {usage['left']} auto.dev calls left "
        f"this month · page is {n:,} bytes\n\n"
        f"| Score | Car | Ask | Miles | 8-mo cost | Walk away |\n"
        f"|--:|---|--:|--:|--:|--:|\n{top}\n\n"
        f"Rejected: {stats['rejected_summary']}")
    return 0


if __name__ == "__main__":
    # main()'s own return value carries the exit code; wrapping sys.exit in
    # the try would make SystemExit(0) look like a crash to the handler.
    try:
        code = main()
    except BaseException as exc:
        R._log_failure(exc)
        summary(f"### Refresh failed\n\n`{type(exc).__name__}: {exc}`\n\n"
                f"The published board was left untouched.")
        raise
    sys.exit(code)
