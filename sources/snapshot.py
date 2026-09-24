"""
A point-in-time capture of real listings, read from snapshot.json.

CarGurus serves its search pages but blocks automated clients, so its
inventory cannot be polled on a schedule the way auto.dev can. This source
exists so there is a real, clickable shortlist to work from immediately,
and so the scoring can be exercised against actual cars rather than
fixtures. Rebuild it with build_snapshot.py.
"""

import json
import os

from . import Listing

NAME = "snapshot"
PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "snapshot.json")


def fetch(cfg, verbose=True):
    try:
        with open(PATH) as fh:
            data = json.load(fh)
    except (OSError, ValueError):
        if verbose:
            print("  [snapshot] no snapshot.json - skipping")
        return []

    out = [Listing(**row) for row in data.get("listings", [])]
    if verbose:
        print(f"  [snapshot] {len(out)} listings captured {data.get('captured', '?')}")
    return out
