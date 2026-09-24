"""Headless checks for the shortlist / freshness / budget additions."""
import os, sys, re
from playwright.sync_api import sync_playwright

FAIL = []
def check(name, cond, detail=""):
    print(f"  {'ok  ' if cond else 'FAIL'} {name}" + (f"   {detail}" if detail else ""))
    if not cond: FAIL.append(name)

def main():
    path = (sys.argv[1] if len(sys.argv) > 1 and sys.argv[1].endswith(".html")
            else os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "out", "share_local.html"))
    path = os.path.abspath(path)
    with sync_playwright() as pw:
        b = pw.chromium.launch()
        pg = b.new_page(viewport={"width": 1400, "height": 950})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)))
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.goto("file://" + path)
        pg.wait_for_selector("#tb tr", timeout=10000)

        print("freshness + budget:")
        check("freshness banner renders", "pulled" in pg.inner_text("#freshage"))
        check("banner is not stale on a fresh build",
              "stale" not in (pg.get_attribute("#fresh", "class") or ""),
              pg.get_attribute("#fresh", "class"))
        bud = pg.inner_text("#budget")
        check("API budget shows calls left", "left this month" in bud, bud)
        check("budget figure is a real number", re.search(r"\b\d{2,4}\b", bud) is not None, bud)

        print("shortlist:")
        check("button starts disabled", pg.is_disabled("#shortbtn"))
        check("button starts at zero", pg.inner_text("#shortbtn") == "Shortlist (0)")
        boxes = pg.query_selector_all("#tb tr td.rk input[type=checkbox]")
        check("every row has a pick box", len(boxes) == pg.eval_on_selector_all("#tb tr", "e=>e.length"),
              f"{len(boxes)} boxes")
        boxes[0].check(); boxes[2].check(); boxes[5].check()
        check("count tracks picks", pg.inner_text("#shortbtn") == "Shortlist (3)",
              pg.inner_text("#shortbtn"))
        check("button enables once something is picked", not pg.is_disabled("#shortbtn"))
        check("picked rows are highlighted",
              pg.eval_on_selector_all("#tb tr.picked", "e=>e.length") == 3)

        # a pick must survive a re-render (sorting)
        pg.click("thead th[data-k='price']")
        check("picks survive a re-sort", pg.inner_text("#shortbtn") == "Shortlist (3)")
        check("checkboxes stay ticked after a re-sort",
              pg.eval_on_selector_all("#tb tr td.rk input:checked", "e=>e.length") == 3)
        pg.click("thead th[data-k='score']")

        pg.click("#shortbtn")
        check("sheet opens", pg.is_visible("#sheet"))
        check("board hides behind the sheet", not pg.is_visible("#board"))
        cards = pg.eval_on_selector_all("#sheet .card", "e=>e.length")
        check("one card per picked car", cards == 3, f"{cards} cards")
        txt = pg.inner_text("#sheet")
        low = txt.lower()   # the dt labels are uppercased by CSS
        for want in ("asking", "walk away above", "miles", "cost to own", "shortlist — 3 cars"):
            check(f"sheet shows {want!r}", want in low)
        check("sheet states the assumptions", "target" in txt and "miles a month" in txt)
        check("every card links to the listing",
              pg.eval_on_selector_all("#sheet .card h3 a[href^='http']", "e=>e.length") == 3)

        pg.click("#sheetback")
        check("back returns to the board", pg.is_visible("#board") and not pg.is_visible("#sheet"))
        check("picks survive the round trip", pg.inner_text("#shortbtn") == "Shortlist (3)")

        print("print layout:")
        pg.click("#shortbtn")
        pg.emulate_media(media="print")
        check("sheet prints", pg.is_visible("#sheet"))
        check("controls do not print", not pg.is_visible(".sheetbar"))
        check("board does not print", not pg.is_visible("#board"))
        pg.emulate_media(media="screen")

        print("offline safety:")
        html = open(path, encoding="utf-8").read()
        ext = re.findall(r'(?:src|href)\s*=\s*["\'](https?://[^"\']+)', html)
        ext = [u for u in ext if "carfax.com" not in u]  # listing links are meant to be external
        ext = [u for u in ext if not re.search(r'autolist|cargurus|\.com/(used|inventory|pre-owned|cars-for-sale|vehicle)', u)]
        check("no external stylesheets or scripts", not ext, "; ".join(ext[:3]))
        check("no external font loads", "fonts.googleapis" not in html and "@import" not in html)
        check("no network calls in script", "fetch(" not in html and "XMLHttpRequest" not in html)

        check("still no JS errors", not errs, "; ".join(errs[:3]))
        b.close()

    print()
    print("shortlist, freshness and budget all behave" if not FAIL
          else f"{len(FAIL)} FAILED: {', '.join(FAIL)}")
    return 1 if FAIL else 0

if __name__ == "__main__":
    sys.exit(main())
