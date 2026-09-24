"""Listing sources. Each source exposes fetch(cfg) -> list[Listing]."""

from dataclasses import dataclass, field, asdict
from typing import Optional


@dataclass
class Listing:
    """One car, normalised across every source."""
    source: str
    listing_id: str
    vin: Optional[str]
    year: int
    make: str
    model: str
    trim: str = ""
    price: Optional[int] = None
    miles: Optional[int] = None
    color: str = ""
    body: str = ""
    title_status: str = "clean"
    seller_type: str = ""          # dealer | private | online
    dealer: str = ""
    city: str = ""
    state: str = ""
    url: str = ""
    # --- filled in by run.py from out/state.json, not by the sources ---
    first_seen: str = ""        # ISO date this listing was first seen
    days_listed: int = 0        # days on your list (a negotiation lever)
    is_new: bool = False
    price_drop: int = 0         # total $ dropped since first seen
    prior_price: int = None     # the price at the previous run
    color_unverified: bool = False   # source gave us no colour to check
    accidents: int = None            # reported accident count, if known
    one_owner: bool = False
    carfax_url: str = ""
    raw: dict = field(default_factory=dict, repr=False)

    def vin_key(self):
        return ("vin", self.vin.upper()) if self.vin else None

    def fuzzy_key(self):
        """Identity for the same car seen through two sources.

        Deliberately excludes price: the whole point of tracking is that
        prices move, and the same car at $6,995 today and $7,169 last week
        is one car with a price cut, not two listings. Exact mileage plus
        year/make/model is a strong enough fingerprint.
        """
        return ("fuzzy", self.year, self.make.lower(), self.model.lower(),
                self.miles if self.miles is not None else -1)

    def richness(self):
        """How much this record tells us -- used to pick a survivor."""
        return (1 if self.vin else 0) + (1 if self.accidents is not None else 0) \
             + (1 if self.carfax_url else 0) + (1 if self.color else 0) \
             + (1 if self.url else 0)

    def to_dict(self):
        d = asdict(self)
        d.pop("raw", None)
        return d
