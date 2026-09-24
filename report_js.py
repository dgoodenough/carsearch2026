"""
The client-side half of the report: a faithful port of resale.py and
score.py into JavaScript.

Keeping this in one place, as a single string, makes the contract explicit:
the numbers the browser computes when a slider moves must match what Python
computed when the report was written. test_report.py runs both against the
same listings under node and fails if they ever diverge.
"""

SCORING_JS = r"""
// ---- ported from resale.py -------------------------------------------
const CA_SALES_TAX = 0.0775, CA_DOC_FEE = 85, CA_SMOG = 37;
const ACCIDENT_HAIRCUT = 0.12;

function caReg(price) { return 180 + 0.0065 * price; }

function acquisitionCost(price, sellerType) {
  let fees = price * CA_SALES_TAX + caReg(price);
  if (sellerType !== "private") fees += CA_DOC_FEE + CA_SMOG;
  return Math.round(fees);
}

function perMile(price) {
  if (price == null) return 0.055;
  if (price < 9000) return 0.035;
  if (price < 14000) return 0.050;
  return 0.070;
}

function mileageLiquidity(m) {
  if (m == null) return 0.75;
  if (m < 80000) return 1.00;
  if (m < 100000) return 0.92;
  if (m < 120000) return 0.80;
  if (m < 150000) return 0.62;
  return 0.35;
}

function instantHaircut(milesAtSale, ageAtSale) {
  let h = 0.15;
  if (milesAtSale != null) {
    if (milesAtSale > 100000) h += 0.03;
    if (milesAtSale > 120000) h += 0.04;
    if (milesAtSale > 150000) h += 0.10;
  }
  if (ageAtSale > 9) h += 0.03;
  if (ageAtSale > 12) h += 0.04;
  return Math.min(h, 0.42);
}

function project(c, P) {
  if (c.price == null) return null;
  const holdMonths = P.hold, mpm = P.mpm;
  const milesAtSale = c.miles == null ? null : c.miles + holdMonths * mpm;
  const ageAtSale = (P.thisYear - c.y) + holdMonths / 12.0;

  const timeLoss = c.price * c.dep * (holdMonths / 12.0);
  const mileLoss = (holdMonths * mpm) * perMile(c.price);
  const dealerMarkup = c.seller === "dealer" ? 0.10 : 0.0;
  const privateValueNow = c.price * (1 - dealerMarkup);

  let privateResale = Math.max(privateValueNow - timeLoss - mileLoss, 500);
  if (c.acc) privateResale *= (1 - ACCIDENT_HAIRCUT);

  const liqNow = mileageLiquidity(c.miles);
  const liqThen = mileageLiquidity(milesAtSale);
  if (liqThen < liqNow) privateResale *= (1 - 0.5 * (liqNow - liqThen));

  const haircut = instantHaircut(milesAtSale, ageAtSale);
  const instantResale = Math.max(privateResale * (1 - haircut), 300);

  const fees = acquisitionCost(c.price, c.seller);
  const allIn = c.price + fees;
  const liquidity = c.liq0 * liqThen;

  return {
    allIn: Math.round(allIn), fees, milesAtSale,
    privateResale: Math.round(privateResale),
    instantResale: Math.round(instantResale),
    lossPrivate: Math.round(allIn - privateResale),
    lossInstant: Math.round(allIn - instantResale),
    // unrounded on purpose -- see the note in resale.py project()
    haircut: haircut,
    liquidity: liquidity
  };
}

function blendedLoss(proj, conf) {
  if (!proj) return null;
  const p = conf * proj.liquidity;
  return Math.round(proj.lossPrivate * p + proj.lossInstant * (1 - p));
}

function expectedRepairs(rel, miles, year, holdMonths, thisYear) {
  if (rel == null) rel = 60.0;
  const age = Math.max(0, thisYear - year);
  const m = miles == null ? 90000 : miles;
  let annual = 400.0;
  annual += 70.0 * Math.max(0, age - 4);
  annual += 0.008 * Math.max(0, m - 60000);
  const factor = 0.6 + 0.8 * ((100.0 - rel) / 100.0);
  return Math.round(annual * factor * (holdMonths / 12.0));
}

function insuranceCost(c, P) {
  const factor = P.insFactor[c.insClass] ?? 1.0;
  return Math.floor(P.insBase * factor * (P.hold / 12.0) + 0.5);
}

// ---- ported from score.py --------------------------------------------
function ramp(x, good, bad) {
  if (x == null) return 50.0;
  if (x <= good) return 100.0;
  if (x >= bad) return 0.0;
  return 100.0 * (bad - x) / (bad - good);
}

function computeParts(c, P) {
  const proj = project(c, P);
  const loss = blendedLoss(proj, P.conf);
  const repairs = expectedRepairs(c.rel, c.miles, c.y, P.hold, P.thisYear);
  const ins = insuranceCost(c, P);
  const total = loss == null ? null : loss + repairs + ins;

  const parts = {};
  parts.reliability = c.rel == null ? 50.0 : c.rel;
  parts.net_cost = ramp(total, P.costGood, P.costBad);
  parts.liquidity = proj ? proj.liquidity * 100.0 : 50.0;

  if (c.expected && c.expected > 0 && c.price != null) {
    let delta = (c.expected - c.price) / c.expected;
    const confidence = Math.min(1.0, c.cohortN / 20.0);
    if (c.tooGood) delta = Math.min(delta, 0.15);
    parts.value = Math.max(0.0, Math.min(100.0, 50.0 + delta * 250.0 * confidence));
  } else {
    parts.value = 50.0;
  }

  parts.outlay = ramp(c.price, P.sweetSpot, P.priceMax);
  parts.mileage = c.miles == null ? 50.0
    : Math.max(0.0, 100.0 * (1.0 - c.miles / P.maxMiles));

  const rank = P.bodyPref.indexOf(c.body);
  parts.body = rank < 0 ? 50.0 : 100.0 - rank * (100.0 / P.bodyPref.length);

  return { parts, proj, loss, repairs, ins, total };
}

function scoreOf(c, P, W) {
  const r = computeParts(c, P);
  let num = 0, den = 0;
  for (const k in W) { num += (r.parts[k] || 0) * W[k]; den += W[k]; }
  r.score = den > 0 ? num / den : 0;
  return r;
}

// The most you can pay and still hit the target. Cost rises monotonically
// with price, so bisect -- same routine as resale.walk_away_price().
function walkAway(c, P, target) {
  const costAt = price => {
    const t = computeParts(Object.assign({}, c, { price }), P);
    return t.total == null ? Infinity : t.total;
  };
  let lo = 500, hi = 40000;
  if (costAt(lo) > target) return null;
  if (costAt(hi) <= target) return hi;
  for (let i = 0; i < 40 && hi - lo >= 5; i++) {
    const mid = (lo + hi) / 2;
    if (costAt(mid) <= target) lo = mid; else hi = mid;
  }
  return Math.floor(lo + 0.5);
}
"""
