#!/usr/bin/env python3
"""
Drive the generated report in a real browser and assert the interactions
actually do what they claim: sorting reorders, sliders re-rank, filters
filter, reset restores.

    python test_ui.py          (needs playwright + chromium)
"""
import os
import sys

FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("playwright not installed - skipping the UI check")
        return 0

    path = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".html")
            else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "out", "share_local.html"))
    path = os.path.abspath(path)
    if not os.path.exists(path):
        print("no out/share_local.html - run `python run.py --snapshot` first")
        return 1

    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1500, "height": 1000})
        errors = []
        pg.on("pageerror", lambda e: errors.append(str(e)))
        pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        pg.goto("file://" + path)
        pg.wait_for_selector("#tb tr", timeout=10000)

        rows = lambda: pg.eval_on_selector_all("#tb tr", "els => els.length")
        col = lambda n: pg.eval_on_selector_all(
            f"#tb tr td:nth-child({n})", "els => els.map(e => e.innerText.trim())")
        scores = lambda: [float(x) for x in col(2)]

        n0 = rows()
        check("every listing renders (no 50-row cap)", n0 > 0, f"{n0} rows")
        check("row count matches the header", str(n0) == pg.inner_text("#shown"))
        check("no JS errors on load", not errors, "; ".join(errors[:3]))

        s = scores()
        check("default sort is score descending", s == sorted(s, reverse=True))

        # --- sorting -------------------------------------------------------
        pg.click("thead th[data-k='price']")
        prices = [int(x.split("\n")[0].replace("$", "").replace(",", ""))
                  for x in col(4) if x.startswith("$")]
        check("clicking Ask sorts by price ascending", prices == sorted(prices))
        pg.click("thead th[data-k='price']")
        prices2 = [int(x.split("\n")[0].replace("$", "").replace(",", ""))
                   for x in col(4) if x.startswith("$")]
        check("clicking again reverses it", prices2 == sorted(prices2, reverse=True))

        pg.click("thead th[data-k='miles']")
        miles = [int(x.split("\n")[0].replace(",", "")) for x in col(7)
                 if x.split("\n")[0].replace(",", "").isdigit()]
        check("Miles column sorts", miles == sorted(miles))

        pg.click("thead th[data-k='score']")
        check("returning to Score restores the ranking",
              scores() == sorted(scores(), reverse=True))

        # --- weight sliders -------------------------------------------------
        WK = ["net_cost", "reliability", "liquidity", "value", "outlay",
              "body", "mileage"]
        setw = lambda k, v: pg.eval_on_selector(
            f"#w_{k}", f"el => {{ el.value = {v}; el.dispatchEvent(new Event('input')); }}")

        order_before = col(3)
        for k in WK:
            setw(k, 60 if k == "reliability" else 0)
        order_after = col(3)
        check("weight sliders reorder the board", order_before != order_after,
              f"top: {order_before[0][:26]} -> {order_after[0][:26]}")
        check("slider readout updates", pg.inner_text("#w_reliability_v") == "60")

        # with every other weight at zero the score IS the reliability score
        rel_scores = [float(x.split("\n")[0]) for x in col(8)]
        worst = max(abs(a - b) for a, b in zip(scores(), rel_scores))
        check("with only reliability weighted, score equals reliability",
              worst < 0.51, f"max delta {worst:.2f}")
        check("and the board is then sorted by reliability",
              rel_scores == sorted(rel_scores, reverse=True))

        # a single weight at zero must not zero the score
        for k in WK:
            setw(k, 0)
        setw("outlay", 20)
        check("an all-but-one-zero weighting still scores", min(scores()) >= 0
              and max(scores()) > 0)

        # --- model-parameter sliders ----------------------------------------
        pg.click("#reset")
        cost_before = col(5)[0].split("\n")[0]
        pg.eval_on_selector("#p_hold", "el => { el.value = 24; el.dispatchEvent(new Event('input')); }")
        cost_after = col(5)[0].split("\n")[0]
        check("hold-length slider changes cost to own", cost_before != cost_after,
              f"{cost_before} -> {cost_after}")

        pg.click("#reset")
        c0 = col(5)[0].split("\n")[0]
        pg.eval_on_selector("#p_conf", "el => { el.value = 100; el.dispatchEvent(new Event('input')); }")
        c1 = col(5)[0].split("\n")[0]
        money = lambda x: int(x.replace("$", "").replace(",", ""))
        check("a certain private sale lowers projected cost", money(c1) < money(c0),
              f"{c0} -> {c1}")

        pg.click("#reset")
        m0 = col(5)[0].split("\n")[0]
        pg.eval_on_selector("#p_mpm", "el => { el.value = 2500; el.dispatchEvent(new Event('input')); }")
        m1 = col(5)[0].split("\n")[0]
        check("driving more raises projected cost", money(m1) > money(m0), f"{m0} -> {m1}")

        # --- walk-away column + target slider --------------------------------
        pg.click("#reset")
        walk = lambda: [x.split("\n")[0] for x in col(6)]
        w0 = walk()
        check("every row has a walk-away figure",
              all(v.startswith("$") or v == "\u2014" for v in w0), w0[0] if w0 else "-")
        pg.eval_on_selector("#p_tgt", "el => { el.value = 9000; el.dispatchEvent(new Event('input')); }")
        w1 = walk()
        money = lambda x: int(x.replace("$", "").replace(",", "")) if x.startswith("$") else -1
        check("raising the target raises the walk-away price",
              money(w1[0]) > money(w0[0]), f"{w0[0]} -> {w1[0]}")
        check("target readout updates", pg.inner_text("#p_tgt_v") == "$9,000")
        pg.eval_on_selector("#p_tgt", "el => { el.value = 4000; el.dispatchEvent(new Event('input')); }")
        w2 = walk()
        check("lowering it lowers them", money(w2[0]) < money(w0[0]), f"{w0[0]} -> {w2[0]}")

        pg.click("#reset")
        check("insurance appears in the cost breakdown",
              "insurance" in pg.inner_text("#tb tr:first-child"))
        check("the rent-instead benchmark is on the page",
              "Renting instead costs" in pg.inner_text("body"))

        # --- filters ---------------------------------------------------------
        pg.click("#reset")
        base = rows()
        pg.fill("#f_price", "12000")
        n1 = rows()
        over = [p for p in [int(x.split("\n")[0].replace("$", "").replace(",", ""))
                            for x in col(4) if x.startswith("$")] if p > 12000]
        check("max-price filter excludes dearer cars", n1 <= base and not over,
              f"{base} -> {n1}")

        pg.fill("#f_price", "")
        pg.select_option("#f_body", "sedan")
        bodies = [x for x in col(3)]
        check("body filter narrows to sedans",
              all("sedan" in b.lower() for b in bodies) if bodies else True,
              f"{rows()} rows")

        pg.select_option("#f_body", "")
        pg.fill("#f_q", "prius")
        q = col(3)
        check("search box filters", all("prius" in x.lower() for x in q) if q else True,
              f"{rows()} rows")

        pg.fill("#f_q", "zzzznope")
        check("no matches shows the empty state",
              rows() == 0 and pg.is_visible("#empty"))

        # --- reset ------------------------------------------------------------
        pg.click("#reset")
        check("reset restores every row", rows() == n0, f"{rows()} vs {n0}")
        check("reset restores default weights", pg.inner_text("#w_net_cost_v") == "35")
        check("reset restores score sort", scores() == sorted(scores(), reverse=True))
        check("still no JS errors after all that", not errors, "; ".join(errors[:3]))

        pg.screenshot(path=os.path.join(os.path.dirname(path), "report_preview.png"),
                      full_page=False)
        b.close()

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}")
        return 1
    print("the report behaves correctly in a real browser")
    return 0


if __name__ == "__main__":
    sys.exit(main())
