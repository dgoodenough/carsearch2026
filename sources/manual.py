"""
Cars added by hand, read from manual.csv at the repo root.

auto.dev does not carry every dealer. When a car turns up somewhere the
finder cannot see -- a dealer's own site, Facebook, a friend -- add a row to
manual.csv (github.com lets you edit it from a phone) and run the workflow.
It is scored against the same market data as everything else.

Manual rows skip the hard filters (price cap, colour, mileage): if you
typed it in, you want to see where it ranks. Lines starting with # are
ignored, so the file can carry its own instructions. Numbers must not
contain commas ("9995", not "9,995"); a row that does is skipped with a
warning rather than read with its columns shifted.
"""

import csv
import hashlib
import os

from . import Listing

NAME = "manual"
PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "manual.csv")


def _int(x):
    try:
        return int(float(str(x).replace(",", "").replace("$", "").strip()))
    except (TypeError, ValueError):
        return None


def fetch(cfg, verbose=True):
    try:
        with open(PATH, newline="") as fh:
            lines = [ln for ln in fh if ln.strip() and not ln.lstrip().startswith("#")]
    except OSError:
        return []

    out = []
    for row in csv.DictReader(lines):
        if None in row:
            # more cells than headers -- almost always "$9,995" typed with a comma
            if verbose:
                print(f"  [manual] skipping row with extra columns (a comma inside "
                      f"a number?): {','.join(v for v in row.values() if isinstance(v, str))}")
            continue
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        year = _int(row.get("year"))
        make, model = row.get("make", ""), row.get("model", "")
        if not (year and make and model):
            if verbose:
                print(f"  [manual] skipping row without year/make/model: {row}")
            continue
        vin = row.get("vin") or None
        ident = vin or hashlib.sha1("|".join(
            [str(year), make, model, row.get("miles", ""), row.get("dealer", ""),
             row.get("url", "")]).lower().encode()).hexdigest()[:12]
        out.append(Listing(
            source=NAME,
            listing_id=f"manual-{ident}",
            vin=vin,
            year=year,
            make=make,
            model=model,
            trim=row.get("trim", "")[:60],
            price=_int(row.get("price")),
            miles=_int(row.get("miles")),
            color=row.get("color", ""),
            body=row.get("body", ""),
            seller_type=row.get("seller_type") or "dealer",
            dealer=row.get("dealer", ""),
            city=row.get("city", ""),
            state=row.get("state") or "CA",
            url=row.get("url", ""),
        ))
    if verbose:
        print(f"  [manual] {len(out)} listing(s) from manual.csv")
    return out
