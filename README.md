# Ashley's car board

Finds used cars near San Diego and ranks them by what each one actually costs
across an eight-month hold — purchase price plus California tax, registration,
insurance and expected repairs, minus what it should resell for — rather than by
sticker price.

It runs itself on GitHub's servers twice a day and publishes the board as a web
page. No computer of yours needs to be on.

---

## Setting it up (about ten minutes, once)

**1. Make the repository.** On github.com, New repository → name it `car-board`
→ **Public** → don't add a README → Create.

> Public is what makes GitHub Pages free. Nothing secret goes in here: your
> auto.dev key lives in the encrypted secret below, never in the code. The page
> itself is only dealer listings that are already public. If you'd rather it not
> be public, a GitHub Pro account ($4/mo) lets Pages serve a private repo.

**2. Upload these files.** On the empty repo page, "uploading an existing file" →
drag in *everything* from this folder, including the hidden `.github` folder →
Commit.

> If the drag-and-drop misses `.github/workflows/refresh.yml` (browsers
> sometimes skip dotted folders), use "Create new file", type
> `.github/workflows/refresh.yml` as the name, and paste that file's contents in.
> Nothing works without it — that file *is* the scheduler.

**3. Add the API key.** Settings → Secrets and variables → Actions → New
repository secret.

- Name: `AUTODEV_API_KEY`
- Value: your auto.dev key

**4. Let it write back.** Settings → Actions → General → Workflow permissions →
**Read and write permissions** → Save.

> It commits the refreshed page and the tracking state after each run. Without
> this it can fetch but not publish.

**5. Turn on the web page.** Settings → Pages → Source: *Deploy from a branch* →
Branch `main`, folder **`/docs`** → Save. A minute later the page is live at
`https://<your-username>.github.io/car-board/`.

**6. Run it once.** Actions tab → "Refresh the car board" → **Run workflow**.
Give it three or four minutes, then open the Pages URL.

On your phone: open that URL, then Share → **Add to Home Screen**. It opens like
an app and the page works with no signal once loaded.

---

## Using it

**Refresh on demand.** github.com → Actions → "Refresh the car board" → **Run
workflow**. This works from a phone browser; it's the refresh button.

**On a schedule.** Twice a day, 6:40am and 4:40pm Pacific, automatically.
Change the `cron:` lines in `.github/workflows/refresh.yml` to move them —
they're in UTC, and GitHub doesn't follow daylight saving.

**What a run tells you.** Open the run in the Actions tab and the summary shows
what passed, what's new, what got cut, the top ten, and how many auto.dev calls
are left this month. The same call budget is shown on the board itself.

**Adding a car the board can't see.** auto.dev doesn't carry every dealer. If
you find a car elsewhere, open `manual.csv` on github.com, tap the pencil, add a
line (year, make, model, trim, price, miles, color, dealer, city, link; numbers
without commas), commit, then Run workflow. It gets scored and ranked with the
rest, and it's never filtered out.

**Shortlist.** Tick the boxes on rows worth seeing, hit **Shortlist**, then
"Print / save as PDF". That's the sheet to hand someone or read in the car — it
carries the asking price, the mileage, the walk-away ceiling and any warnings.

---

## Things worth knowing

**It won't publish a broken board.** If a refresh comes back with fewer than 120
listings — expired key, API outage, a bad query — the run fails, says why in the
summary, and leaves the last good page up. A blank board on the road would be
worse than a stale one.

**Day counts and price history survive.** `out/state.json` is committed after
each run, so "day 19, cut twice" keeps counting. `out/api_usage.json` tracks the
monthly call budget the same way. Don't delete either — you'd lose the history
that makes a sitting car obvious.

**The call budget is real.** auto.dev's free tier is 1,000 calls a month. A full
refresh costs up to 60, so twice a day is comfortable. `MAX_API_CALLS_PER_MONTH`
in `config.py` is the ceiling it won't cross.

**Insurance is an estimate, not a quote.** $2,000/year for California full
coverage, scaled by the kind of car. Published surveys disagree by nearly 2×.
One real quote in `config.py` (`INSURANCE_BASE_ANNUAL`) makes every number on
the board better.

**Hold length.** `HOLD_MONTHS` is 8. If the program really runs nine, change it
in `config.py` — or just drag the slider on the page, which recomputes
everything live without a rerun.

---

## Running it yourself

```
export AUTODEV_API_KEY=...        # setx on Windows
python ci_run.py                  # fetch, score, write docs/index.html
python ci_run.py --dry-run        # score the last capture, change nothing live
python run.py                     # the original local version, writes out/report.html
```

Pure standard library — no pip install. Python 3.9+.

## Tests

```
python test_filters.py     # hard filters, dedupe, API budget guard
python test_tracking.py    # day counts, price history, vanished listings
python test_report.py      # the JS scoring matches the Python, listing by listing
python test_ui.py          # the board in a real headless browser (needs playwright)
python test_ui_extras.py   # shortlist, freshness banner, print layout, offline safety
```

`test_report.py` is the one that matters most: the page recomputes every score
in JavaScript when you move a slider, so that port has to agree with the Python
exactly. It checks every listing under several slider settings.
