"""
The interactive report.

Every listing carries its own scoring inputs, and the whole resale model is
ported to JavaScript (report_js.py), so moving a slider re-runs the real
arithmetic in the browser rather than re-weighting a precomputed number.
That matters for the hold-length and sale-channel sliders in particular:
changing how long she keeps the car changes the projected mileage at sale,
which can push a listing across a liquidity threshold and reorder the board.
"""

import datetime
import html as H
import json
import os

from report_js import SCORING_JS

WEIGHT_META = [
    ("net_cost",    "8-month cost",  "What the car actually costs to own and sell"),
    ("reliability", "Reliability",   "NHTSA complaint record for that exact model-year"),
    ("liquidity",   "Resale ease",   "How readily it sells again in San Diego"),
    ("value",       "Vs. market",    "Asking price against comparable live listings"),
    ("outlay",      "Cash up front", "Prefers a smaller cheque today"),
    ("body",        "Body style",    "Hatchback > sedan > small SUV"),
    ("mileage",     "Mileage",       "Headroom under the cap"),
]


def _listing_payload(l, s, cfg, dep, liq0):
    return {
        "id": f"{l.source}:{l.listing_id}",
        "y": l.year, "mk": l.make, "md": l.model, "tr": l.trim or "",
        "price": l.price, "miles": l.miles,
        "color": l.color or "", "body": l.body or "",
        "city": l.city or "", "dealer": l.dealer or "",
        "src": l.source, "url": l.url or "", "carfax": l.carfax_url or "",
        "seller": l.seller_type or "dealer",
        "acc": l.accidents, "own": bool(l.one_owner),
        "days": l.days_listed, "isNew": bool(l.is_new),
        "drop": l.price_drop or 0, "prior": l.prior_price,
        "rel": s["parts"]["reliability"],
        "relNote": s.get("reliability_note") or "",
        "complaints": s.get("complaints"), "recalls": s.get("recalls"),
        "relChecked": bool(s.get("rel_checked")),
        "expected": s.get("expected_price"), "cohortN": s.get("cohort_n") or 0,
        "tooGood": bool(s.get("too_good")),
        "colorUnknown": bool(l.color_unverified),
        "dep": dep, "liq0": liq0,
        "insClass": cfg.INSURANCE_CLASS.get((l.make.lower(), l.model.lower()),
                                            "compact"),
    }


def build(rows, cfg, stats, drops, vanished, weights, path,
          mode="local", intro="", title="San Diego car deals", usage=None):
    import resale as rs

    data = []
    for l, s in rows:
        key = (l.make.lower(), l.model.lower())
        dep = rs.ANNUAL_DEPRECIATION.get(key, rs.DEFAULT_ANNUAL_DEPRECIATION)
        liq0 = rs.LIQUIDITY.get(key, rs.DEFAULT_LIQUIDITY)
        data.append(_listing_payload(l, s, cfg, dep, liq0))

    params = {
        "hold": cfg.HOLD_MONTHS, "mpm": cfg.MILES_PER_MONTH,
        "conf": cfg.PRIVATE_SALE_CONFIDENCE,
        "costGood": cfg.COST_GOOD, "costBad": cfg.COST_BAD,
        "sweetSpot": cfg.PRICE_SWEET_SPOT, "priceMax": cfg.PRICE_MAX,
        "maxMiles": cfg.MAX_MILES, "bodyPref": list(cfg.BODY_PREFERENCE),
        "thisYear": datetime.date.today().year,
        "insBase": cfg.INSURANCE_BASE_ANNUAL,
        "insFactor": dict(cfg.INSURANCE_FACTOR),
        "target": cfg.TARGET_COST,
        "rentInstead": min(cfg.RENT_INSTEAD.values()),
        "rentLabel": min(cfg.RENT_INSTEAD, key=cfg.RENT_INSTEAD.get),
        "builtAt": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "usage": dict(usage or {}),
    }

    gone = [{"label": r.get("label", sid), "since": r.get("gone_since", "?"),
             "url": r.get("url", "")} for sid, r in list(vanished)[:20]]

    fmt = "%a %b %d, %Y at %I:%M %p" if os.name == "nt" else "%a %b %d, %Y at %-I:%M %p"
    now = datetime.datetime.now().strftime(fmt)

    sliders = "".join(f'''
      <label class="ctl" data-w="{k}">
        <span class="ctl-h"><b>{H.escape(label)}</b><i id="w_{k}_v">{weights[k]}</i></span>
        <input type="range" min="0" max="60" value="{weights[k]}" id="w_{k}">
        <span class="ctl-d">{H.escape(desc)}</span>
      </label>''' for k, label, desc in WEIGHT_META)

    doc = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title>
<style>
  :root {{
    --bg:#faf9f7; --fg:#1d1b18; --mut:#6b6762; --line:#e5e1db; --card:#fff;
    --good:#2f7d5a; --mid:#b07d28; --bad:#a8453a; --accent:#1f5fa8;
    --hdr:#f2efe9;
  }}
  @media (prefers-color-scheme: dark) {{
    :root:not([data-theme="light"]) {{
      --bg:#16150f; --fg:#eceae4; --mut:#9a958c; --line:#2e2c26; --card:#1f1e17;
      --good:#68c39a; --mid:#e0b45f; --bad:#e08579; --accent:#7db3f0; --hdr:#23221b;
    }}
  }}
  :root[data-theme="dark"] {{
    --bg:#16150f; --fg:#eceae4; --mut:#9a958c; --line:#2e2c26; --card:#1f1e17;
    --good:#68c39a; --mid:#e0b45f; --bad:#e08579; --accent:#7db3f0; --hdr:#23221b;
  }}
  * {{ box-sizing:border-box; }}
  body {{ margin:0; background:var(--bg); color:var(--fg);
    font:14px/1.45 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif; }}
  .wrap {{ max-width:1500px; margin:0 auto; padding-inline:16px;
    padding-block:26px 70px; }}
  h1 {{ font-size:24px; margin:0 0 3px; letter-spacing:-.02em; }}
  .sub {{ color:var(--mut); margin:0 0 18px; font-size:13px; }}
  .stats {{ display:flex; flex-wrap:wrap; gap:8px; margin-bottom:18px; }}
  .stat {{ background:var(--card); border:1px solid var(--line); border-radius:9px;
    padding:8px 13px; }}
  .stat b {{ display:block; font-size:18px; font-variant-numeric:tabular-nums; }}
  .stat span {{ color:var(--mut); font-size:11.5px; }}

  .panel {{ background:var(--card); border:1px solid var(--line); border-radius:12px;
    padding:16px 18px; margin-bottom:16px; }}
  .panel h2 {{ font-size:13px; margin:0 0 3px; text-transform:uppercase;
    letter-spacing:.06em; color:var(--mut); }}
  .panel .hint {{ color:var(--mut); font-size:12px; margin:0 0 14px; }}
  .ctls {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(215px,1fr)); gap:14px 20px; }}
  .ctl {{ display:block; }}
  .ctl-h {{ display:flex; justify-content:space-between; align-items:baseline;
    font-size:12.5px; margin-bottom:3px; }}
  .ctl-h i {{ font-style:normal; color:var(--accent); font-variant-numeric:tabular-nums;
    font-weight:650; }}
  .ctl-d {{ display:block; color:var(--mut); font-size:11px; margin-top:2px; }}
  input[type=range] {{ width:100%; accent-color:var(--accent); margin:0; }}
  .row2 {{ display:flex; flex-wrap:wrap; gap:14px 22px; align-items:flex-end;
    margin-top:16px; padding-top:14px; border-top:1px solid var(--line); }}
  .fld {{ display:flex; flex-direction:column; gap:3px; font-size:12.5px; }}
  .fld span {{ color:var(--mut); font-size:11px; }}
  select, input[type=number], input[type=search] {{ background:var(--bg); color:var(--fg);
    border:1px solid var(--line); border-radius:7px; padding:5px 8px; font:inherit;
    font-size:12.5px; }}
  input[type=search] {{ min-width:190px; }}
  button {{ background:var(--accent); color:#fff; border:0; border-radius:7px;
    padding:7px 13px; font:inherit; font-size:12.5px; cursor:pointer; }}
  button.ghost {{ background:transparent; color:var(--accent);
    border:1px solid var(--line); }}
  label.chk {{ display:flex; align-items:center; gap:6px; font-size:12.5px; cursor:pointer; }}

  .tablewrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:11px;
    background:var(--card); }}
  table {{ width:100%; border-collapse:collapse; min-width:0; }}
  thead th {{ background:var(--hdr); text-align:left; padding:9px 10px; font-size:11.5px;
    text-transform:uppercase; letter-spacing:.05em; color:var(--mut);
    cursor:pointer; user-select:none; white-space:nowrap;
    position:sticky; top:0; z-index:2; }}
  thead th:hover {{ color:var(--fg); }}
  thead th.num {{ text-align:right; }}
  thead th .ar {{ opacity:.45; font-size:9px; }}
  tbody td {{ padding:9px 10px; border-top:1px solid var(--line); vertical-align:top; }}
  tbody tr:hover {{ background:color-mix(in srgb,var(--accent) 5%,transparent); }}
  td.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
  .rk {{ color:var(--mut); font-variant-numeric:tabular-nums; width:38px; }}
  .sc {{ font-size:17px; font-weight:650; font-variant-numeric:tabular-nums; width:52px; }}
  .sc.good {{ color:var(--good); }} .sc.mid {{ color:var(--mid); }} .sc.bad {{ color:var(--bad); }}
  .veh a {{ color:var(--fg); text-decoration:none; font-weight:600; }}
  .veh a:hover {{ color:var(--accent); text-decoration:underline; }}
  .meta {{ color:var(--mut); font-size:11.5px; margin-top:2px; }}
  .note {{ color:var(--mid); font-size:11px; margin-top:3px; max-width:430px; }}
  .tags {{ margin-top:4px; display:flex; flex-wrap:wrap; gap:4px; }}
  .tag {{ font-size:10.5px; padding:1px 6px; border-radius:20px; white-space:nowrap; }}
  .tag.win,.tag.priv {{ background:color-mix(in srgb,var(--good) 18%,transparent); color:var(--good); }}
  .tag.over,.tag.stale {{ background:color-mix(in srgb,var(--bad) 15%,transparent); color:var(--bad); }}
  .tag.new {{ background:color-mix(in srgb,var(--accent) 18%,transparent); color:var(--accent); }}
  .tag.drop,.tag.warm {{ background:color-mix(in srgb,var(--mid) 20%,transparent); color:var(--mid); }}
  .tag.age {{ background:color-mix(in srgb,var(--mut) 15%,transparent); color:var(--mut); }}
  .tag.verify {{ background:color-mix(in srgb,var(--bad) 18%,transparent); color:var(--bad); font-weight:600; }}
  .cost.good {{ color:var(--good); }} .cost.mid {{ color:var(--mid); }} .cost.bad {{ color:var(--bad); }}
  .sub2 {{ color:var(--mut); font-size:10.5px; }}
  .bars {{ display:flex; gap:2px; align-items:flex-end; height:22px; }}
  .bars i {{ width:6px; background:var(--accent); opacity:.6; border-radius:1px; display:block; }}
  h2.sec {{ font-size:15px; margin:30px 0 9px; }}
  .intro {{ background:var(--card); border:1px solid var(--line);
    border-left:3px solid var(--accent); border-radius:11px;
    padding:16px 18px; margin-bottom:16px; max-width:70ch; }}
  .intro h2 {{ font-size:15px; margin:0 0 7px; letter-spacing:-.01em;
    text-transform:none; color:var(--fg); }}
  .intro p {{ margin:0 0 9px; font-size:13.5px; }}
  .intro p:last-child {{ margin-bottom:0; }}
  .intro b {{ color:var(--accent); }}
  .bench {{ background:color-mix(in srgb,var(--mid) 12%,var(--card));
    border:1px solid color-mix(in srgb,var(--mid) 35%,var(--line));
    border-radius:11px; padding:13px 16px; margin-bottom:16px; font-size:13.5px;
    max-width:74ch; }}
  .bench b {{ color:var(--mid); }}
  .walk {{ font-size:15px; font-weight:650; font-variant-numeric:tabular-nums; }}
  .walk.over {{ color:var(--bad); }}
  .walk.under {{ color:var(--good); }}
  tr.loses td {{ background:color-mix(in srgb,var(--bad) 6%,transparent); }}
  ul.plain {{ list-style:none; padding:0; margin:0; }}
  ul.plain li {{ padding:7px 11px; border:1px solid var(--line); border-radius:8px;
    margin-bottom:5px; background:var(--card); font-size:12.5px; }}
  ul.plain a {{ color:var(--fg); font-weight:600; text-decoration:none; }}
  footer {{ color:var(--mut); font-size:12px; margin-top:26px; line-height:1.65; }}
  .empty {{ padding:38px; text-align:center; color:var(--mut); }}
  @media (max-width:900px) {{ .hide-sm {{ display:none; }} }}

  /* --- freshness + API budget banner --- */
  .fresh {{ display:flex; flex-wrap:wrap; align-items:center; gap:6px 14px;
    background:var(--card); border:1px solid var(--line);
    border-left:3px solid var(--good); border-radius:10px;
    padding:10px 14px; margin-bottom:16px; font-size:13px; }}
  .fresh.warn {{ border-left-color:var(--mid);
    background:color-mix(in srgb,var(--mid) 9%,var(--card)); }}
  .fresh.stale {{ border-left-color:var(--bad);
    background:color-mix(in srgb,var(--bad) 9%,var(--card)); }}
  .fresh .age {{ font-weight:650; }}
  .fresh .budget {{ margin-left:auto; color:var(--mut); font-size:12px; }}
  .fresh .budget b {{ color:var(--fg); font-variant-numeric:tabular-nums; }}

  /* --- shortlist picking --- */
  td.rk input {{ width:17px; height:17px; accent-color:var(--accent);
    cursor:pointer; display:block; margin:0 auto 4px; }}
  tr.picked td {{ background:color-mix(in srgb,var(--accent) 10%,transparent); }}
  #shortbtn[disabled] {{ opacity:.45; cursor:default; }}

  /* --- the printable shortlist --- */
  #sheet {{ display:none; }}
  body.sheeton #board, body.sheeton .panel, body.sheeton .stats,
  body.sheeton .bench, body.sheeton .intro, body.sheeton .empty,
  body.sheeton .sec, body.sheeton ul.plain, body.sheeton footer,
  body.sheeton .fresh {{ display:none !important; }}
  body.sheeton #sheet {{ display:block; }}
  #sheet h2 {{ font-size:18px; margin:0 0 4px; }}
  #sheet .when {{ color:var(--mut); font-size:12.5px; margin:0 0 16px; }}
  .card {{ border:1px solid var(--line); border-radius:10px; background:var(--card);
    padding:13px 15px; margin-bottom:10px; break-inside:avoid; }}
  .card h3 {{ font-size:16px; margin:0 0 3px; }}
  .card h3 a {{ color:var(--fg); text-decoration:none; }}
  .card .sub2 {{ font-size:12px; }}
  .card dl {{ display:grid; grid-template-columns:repeat(auto-fit,minmax(118px,1fr));
    gap:8px 14px; margin:10px 0 0; }}
  .card dt {{ color:var(--mut); font-size:10.5px; text-transform:uppercase;
    letter-spacing:.05em; margin:0; }}
  .card dd {{ margin:1px 0 0; font-size:15px; font-weight:650;
    font-variant-numeric:tabular-nums; }}
  .card dd.ceiling {{ color:var(--good); }}
  .card .why {{ color:var(--mid); font-size:11.5px; margin-top:8px; }}
  .sheetbar {{ display:flex; gap:8px; margin-bottom:16px; }}
  .hint-save {{ color:var(--mut); font-size:11.5px; margin-top:22px; }}

  @media print {{
    @page {{ margin:14mm; }}
    body {{ background:#fff; color:#000; }}
    .sheetbar, .hint-save {{ display:none !important; }}
    .card {{ border:1px solid #bbb; background:#fff; }}
    .card h3 a {{ color:#000; }}
    .card dd.ceiling {{ color:#000; }}
    a[href]:after {{ content:""; }}
  }}
</style></head><body><div class="wrap">

  <h1>{title}</h1>
  <p class="sub">{now} &middot; {cfg.RADIUS_MILES} mi of {cfg.ZIP}
     &middot; <span id="shown">0</span> of {len(data)} listings
     &middot; ranked by projected cost to own, not sticker price</p>

  <div class="fresh" id="fresh">
    <span>Data <span class="age" id="freshage">just now</span></span>
    <span id="freshwhy" style="color:var(--mut)"></span>
    <span class="budget" id="budget"></span>
  </div>

  <div class="stats">
    <div class="stat"><b>{stats['fetched']}</b><span>pulled</span></div>
    <div class="stat"><b>{stats['passed']}</b><span>passed filters</span></div>
    <div class="stat"><b>{stats['new']}</b><span>new today</span></div>
    <div class="stat"><b>{stats.get('held',0)}</b><span>sitting 3+ weeks</span></div>
    <div class="stat"><b>{stats.get('drops',0)}</b><span>price cuts</span></div>
    <div class="stat"><b>{stats.get('vanished',0)}</b><span>gone</span></div>
  </div>

  {intro}

  <div class="bench">
    <b>Renting instead costs ${min(cfg.RENT_INSTEAD.values()):,}</b> for the same
    {cfg.HOLD_MONTHS} months &mdash; a live San Diego quote for 26 Sep to 26 May,
    242 days, {H.escape(min(cfg.RENT_INSTEAD, key=cfg.RENT_INSTEAD.get))}, before any
    collision waiver. That is the real break-even, not the $6&ndash;7k that got
    assumed back in August. Any car whose cost to own lands above that line is
    worse than not buying at all.
  </div>

  <div class="panel">
    <h2>What matters to you</h2>
    <p class="hint">Drag to re-rank. These are real weights &mdash; the whole
       board recomputes, it is not just re-sorting a fixed number.</p>
    <div class="ctls">{sliders}</div>

    <div class="row2">
      <label class="ctl" style="min-width:210px">
        <span class="ctl-h"><b>Months she keeps it</b><i id="p_hold_v">{cfg.HOLD_MONTHS}</i></span>
        <input type="range" min="3" max="24" value="{cfg.HOLD_MONTHS}" id="p_hold">
        <span class="ctl-d">Longer hold = more miles at resale</span>
      </label>
      <label class="ctl" style="min-width:210px">
        <span class="ctl-h"><b>Chance of a private sale</b><i id="p_conf_v">{int(cfg.PRIVATE_SALE_CONFIDENCE*100)}%</i></span>
        <input type="range" min="0" max="100" value="{int(cfg.PRIVATE_SALE_CONFIDENCE*100)}" id="p_conf">
        <span class="ctl-d">0% = you take the CarMax offer</span>
      </label>
      <label class="ctl" style="min-width:210px">
        <span class="ctl-h"><b>Miles per month</b><i id="p_mpm_v">{cfg.MILES_PER_MONTH}</i></span>
        <input type="range" min="300" max="2500" step="100" value="{cfg.MILES_PER_MONTH}" id="p_mpm">
        <span class="ctl-d">How much she'll actually drive</span>
      </label>
      <label class="ctl" style="min-width:210px">
        <span class="ctl-h"><b>Target cost for the 8 months</b><i id="p_tgt_v">${cfg.TARGET_COST:,}</i></span>
        <input type="range" min="4000" max="9500" step="250" value="{cfg.TARGET_COST}" id="p_tgt">
        <span class="ctl-d">Sets the walk-away price on every row</span>
      </label>
    </div>

    <div class="row2">
      <div class="fld"><span>Search</span>
        <input type="search" id="f_q" placeholder="model, colour, dealer, city"></div>
      <div class="fld"><span>Max price</span>
        <input type="number" id="f_price" step="500" placeholder="{cfg.PRICE_MAX}"></div>
      <div class="fld"><span>Max miles</span>
        <input type="number" id="f_miles" step="5000" placeholder="{cfg.MAX_MILES}"></div>
      <div class="fld"><span>Min year</span>
        <input type="number" id="f_year" step="1" placeholder="{cfg.MIN_YEAR}"></div>
      <div class="fld"><span>Body</span>
        <select id="f_body"><option value="">any</option>
          <option value="hatchback">hatchback</option>
          <option value="sedan">sedan</option>
          <option value="small_suv">small SUV</option></select></div>
      <div class="fld"><span>Make</span>
        <select id="f_make"><option value="">any</option></select></div>
      <label class="chk"><input type="checkbox" id="f_noacc"> no reported accidents</label>
      <label class="chk"><input type="checkbox" id="f_nostale"> hide day-0 only</label>
      <button id="shortbtn" disabled>Shortlist (0)</button>
      <button class="ghost" id="reset">Reset everything</button>
    </div>
  </div>

  <div id="board">
  <div class="tablewrap">
  <table>
    <thead><tr>
      <th style="width:38px">#</th>
      <th class="num sortable" data-k="score">Score <span class="ar">&#9660;</span></th>
      <th class="sortable" data-k="veh">Vehicle</th>
      <th class="num sortable" data-k="price">Ask</th>
      <th class="num sortable" data-k="total">Cost to own</th>
      <th class="num sortable" data-k="walk">Walk away above</th>
      <th class="num sortable" data-k="miles">Miles</th>
      <th class="num sortable hide-sm" data-k="rel">Reliab.</th>
      <th class="num sortable hide-sm" data-k="days">Days</th>
      <th class="hide-sm">Breakdown</th>
    </tr></thead>
    <tbody id="tb"></tbody>
  </table>
  </div>
  </div>
  <div class="empty" id="empty" style="display:none">Nothing matches those filters.</div>

  <section id="sheet"></section>

  {_drops_html(drops)}
  {_gone_html(gone)}

  <footer>
    <b>Walk away above</b> is the most you can pay for that specific car and still hit the
    target cost &mdash; drag the target slider and every ceiling moves with it. Rows shaded
    red cost more over the hold than simply renting.<br>
    <b>Insurance</b> is an estimate, not a quote: ${cfg.INSURANCE_BASE_ANNUAL:,}/year
    for full coverage in California, scaled by the kind of car. Published surveys disagree
    by nearly 2&times; on this, so get one real quote and put it in config.py.<br>
    <b>Cost to own</b> is the whole round trip: purchase price plus California tax and
    registration, minus projected resale after the hold, plus expected repairs and insurance. The two
    resale figures behind it are a private-party sale and a CarMax/Carvana instant offer,
    blended by the slider above and weighted by how liquid the car is.<br>
    <b>Reliability</b> is NHTSA complaint volume for that exact model-year, weighted by how
    expensive the failing component is, normalised for the car's age, then penalised for
    known big-ticket defects.<br>
    <b>Verify before trusting</b> means the price is more than 30% under its own comparables
    &mdash; usually a branded title, odometer discrepancy or listing error rather than a find.<br>
    <b>Day counts are negotiating leverage.</b> A car at day 45 with two price cuts has a
    seller who wants out.<br>
    Rejected this run: {H.escape(stats['rejected_summary'])}
  </footer>
</div>

<script>
const DATA = {json.dumps(data, separators=(",", ":"))};
const P0 = {json.dumps(params)};
const W0 = {json.dumps(weights)};
{SCORING_JS}
{_UI_JS}
</script>
</body></html>"""

    if mode == "artifact":
        # The Artifact platform supplies the document skeleton, so ship the
        # <title>, the <style> and the content -- no doctype/html/head/body.
        head = doc[doc.index("<title>"):doc.index("</head>")]
        body = doc[doc.index("<body>") + len("<body>"):doc.rindex("</body>")]
        doc = head + body

    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return len(doc)


def _drops_html(drops):
    if not drops:
        return ""
    items = "".join(
        f'<li><a href="{H.escape(l.url)}" target="_blank" rel="noopener">'
        f'{l.year} {H.escape(l.make)} {H.escape(l.model)}</a> '
        f'<b>&darr; ${l.prior_price - l.price:,}</b> '
        f'&nbsp;${l.prior_price:,} &rarr; ${l.price:,} &middot; day {l.days_listed}</li>'
        for l, _ in sorted(drops, key=lambda r: r[0].price - r[0].prior_price))
    return f'<h2 class="sec">Price cuts since the last run</h2><ul class="plain">{items}</ul>'


def _gone_html(gone):
    if not gone:
        return ""
    items = "".join(
        f'<li>{H.escape(g["label"])} <span style="color:var(--mut)">'
        f'&mdash; gone since {H.escape(str(g["since"]))}</span></li>' for g in gone)
    return f'<h2 class="sec">Disappeared &mdash; sold, or pulled</h2><ul class="plain">{items}</ul>'


_UI_JS = r"""
const WKEYS = Object.keys(W0);
let W = Object.assign({}, W0);
let P = Object.assign({}, P0);
let sortKey = "score", sortDir = -1;
const PICK = new Set();

const $ = id => document.getElementById(id);
const money = n => n == null ? "—" : "$" + Math.round(n).toLocaleString();
const esc = s => String(s == null ? "" : s).replace(/[&<>"]/g,
  c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));

// make filter options
{
  const makes = [...new Set(DATA.map(c => c.mk))].sort();
  $("f_make").insertAdjacentHTML("beforeend",
    makes.map(m => `<option value="${esc(m)}">${esc(m)}</option>`).join(""));
}

function band(v) { return v >= 70 ? "good" : (v >= 45 ? "mid" : "bad"); }
function costBand(c) { return c == null ? "mid" : (c <= 4000 ? "good" : (c <= 6000 ? "mid" : "bad")); }

function passes(c) {
  const q = $("f_q").value.trim().toLowerCase();
  if (q) {
    const hay = [c.mk, c.md, c.tr, c.color, c.dealer, c.city, c.body].join(" ").toLowerCase();
    if (!hay.includes(q)) return false;
  }
  const mp = parseFloat($("f_price").value); if (mp && c.price > mp) return false;
  const mm = parseFloat($("f_miles").value); if (mm && c.miles != null && c.miles > mm) return false;
  const my = parseFloat($("f_year").value);  if (my && c.y < my) return false;
  const b = $("f_body").value; if (b && c.body !== b) return false;
  const mk = $("f_make").value; if (mk && c.mk !== mk) return false;
  if ($("f_noacc").checked && c.acc) return false;
  if ($("f_nostale").checked && c.days === 0 && !c.isNew) return false;
  return true;
}

function tagsFor(c, r) {
  const t = [];
  if (c.isNew) t.push('<span class="tag new">NEW</span>');
  else if (c.days >= 35) t.push(`<span class="tag stale">day ${c.days} &middot; sitting</span>`);
  else if (c.days >= 21) t.push(`<span class="tag warm">day ${c.days}</span>`);
  else if (c.days > 0) t.push(`<span class="tag age">day ${c.days}</span>`);
  if (c.drop) t.push(`<span class="tag drop">&darr; ${money(c.drop)} since listed</span>`);
  if (c.seller === "private") t.push('<span class="tag priv">private party</span>');
  if (c.acc) t.push(`<span class="tag over">${c.acc} accident${c.acc > 1 ? "s" : ""}</span>`);
  else if (c.acc === 0) t.push('<span class="tag win">no accidents</span>');
  if (c.own) t.push('<span class="tag priv">1 owner</span>');
  if (c.colorUnknown) t.push('<span class="tag verify">colour unknown</span>');
  if (c.tooGood && c.expected) {
    t.push(`<span class="tag verify">${money(c.expected - c.price)} under comps &mdash; verify</span>`);
  } else if (c.expected && c.expected - c.price > 500) {
    t.push(`<span class="tag win">${money(c.expected - c.price)} under market</span>`);
  } else if (c.expected && c.price - c.expected > 500) {
    t.push(`<span class="tag over">${money(c.price - c.expected)} over market</span>`);
  }
  if (r.proj && r.proj.milesAtSale > 140000) {
    t.push(`<span class="tag over">${r.proj.milesAtSale.toLocaleString()} mi at resale</span>`);
  }
  return t.join("");
}

function render() {
  const scored = [];
  for (const c of DATA) {
    if (!passes(c)) continue;
    scored.push({ c, r: scoreOf(c, P, W) });
  }
  const get = o => {
    switch (sortKey) {
      case "score": return o.r.score;
      case "price": return o.c.price == null ? Infinity : o.c.price;
      case "total": return o.r.total == null ? Infinity : o.r.total;
      case "miles": return o.c.miles == null ? Infinity : o.c.miles;
      case "walk": {
        const ww = walkAway(o.c, P, P.target);
        if (ww == null) return Infinity;
        return o.c.price == null ? Infinity : o.c.price - ww;
      }
      case "rel":   return o.c.rel;
      case "days":  return o.c.days;
      case "veh":   return (o.c.mk + " " + o.c.md + " " + o.c.y);
      default:      return o.r.score;
    }
  };
  scored.sort((a, b) => {
    const x = get(a), y = get(b);
    if (typeof x === "string") return sortDir * x.localeCompare(y);
    return sortDir * (x - y);
  });

  const maxW = Math.max(...WKEYS.map(k => W[k]), 1);
  const rows = scored.map((o, i) => {
    const c = o.c, r = o.r;
    const bars = WKEYS.map(k =>
      `<i style="height:${Math.max(2, (r.parts[k] || 0) * 0.22)}px;opacity:${0.25 + 0.6 * W[k] / maxW}" title="${k}: ${Math.round(r.parts[k])}"></i>`).join("");
    const resale = r.proj
      ? `<div class="sub2">${money(r.proj.allIn)} in &rarr; ${money(r.proj.privateResale)} priv / ${money(r.proj.instantResale)} inst</div>`
      : "";
    const w = walkAway(c, P, P.target);
    const over = w != null && c.price != null && c.price > w;
    const gap = w != null && c.price != null ? c.price - w : null;
    const loses = r.total != null && r.total > P.rentInstead;
    return `<tr class="${loses ? "loses" : ""}${PICK.has(c.id) ? " picked" : ""}">
      <td class="rk"><input type="checkbox" data-pick="${esc(c.id)}"${PICK.has(c.id) ? " checked" : ""} aria-label="add to shortlist">${i + 1}</td>
      <td class="num sc ${band(r.score)}">${r.score.toFixed(0)}</td>
      <td class="veh">
        <div><a href="${esc(c.url)}" target="_blank" rel="noopener">${c.y} ${esc(c.mk)} ${esc(c.md)}</a>
          ${c.tr ? `<span class="sub2">${esc(c.tr)}</span>` : ""}</div>
        <div class="meta">${esc(c.color || "colour n/a")} &middot; ${esc((c.body || "?").replace("_", " "))}
          &middot; ${esc(c.dealer || c.seller)} &middot; ${esc(c.city)} &middot; ${esc(c.src)}
          ${c.carfax ? ` &middot; <a href="${esc(c.carfax)}" target="_blank" rel="noopener">CARFAX</a>` : ""}</div>
        <div class="tags">${tagsFor(c, r)}</div>
        ${c.relNote ? `<div class="note">${esc(c.relNote)}</div>` : ""}
      </td>
      <td class="num">${money(c.price)}${c.drop ? `<div class="sub2" style="text-decoration:line-through">${money(c.price + c.drop)}</div>` : ""}</td>
      <td class="num cost ${costBand(r.total)}"><b>${money(r.total)}</b>${resale}
        <div class="sub2">${money(r.repairs)} repairs &middot; ${money(r.ins)} insurance</div>
        ${loses ? '<div class="sub2" style="color:var(--bad)">worse than renting</div>' : ""}</td>
      <td class="num">
        <span class="walk ${w == null ? "over" : (over ? "over" : "under")}">${w == null ? "&mdash;" : money(w)}</span>
        <div class="sub2">${w == null ? "can't hit target at any price"
          : (over ? `${money(gap)} too dear` : `${money(-gap)} of room`)}</div></td>
      <td class="num">${c.miles == null ? "—" : c.miles.toLocaleString()}
        ${r.proj && r.proj.milesAtSale != null ? `<div class="sub2">&rarr; ${r.proj.milesAtSale.toLocaleString()}</div>` : ""}</td>
      <td class="num hide-sm">${Math.round(c.rel)}
        ${c.complaints != null ? `<div class="sub2">${c.complaints} compl.</div>`
          : '<div class="sub2" title="NHTSA was unreachable on this run">not checked</div>'}</td>
      <td class="num hide-sm">${c.days}</td>
      <td class="hide-sm"><div class="bars">${bars}</div></td>
    </tr>`;
  }).join("");

  $("tb").innerHTML = rows;
  $("shown").textContent = scored.length;
  $("empty").style.display = scored.length ? "none" : "block";
  document.querySelectorAll("thead th.sortable").forEach(th => {
    const on = th.dataset.k === sortKey;
    th.querySelector(".ar")?.remove();
    if (on) th.insertAdjacentHTML("beforeend",
      ` <span class="ar">${sortDir < 0 ? "&#9660;" : "&#9650;"}</span>`);
  });
}

// --- wiring ------------------------------------------------------------
WKEYS.forEach(k => {
  const el = $("w_" + k);
  el.addEventListener("input", () => {
    W[k] = +el.value; $("w_" + k + "_v").textContent = el.value; render();
  });
});
const PMAP = { p_tgt:  ["target", v => v, v => "$" + (+v).toLocaleString()],
               p_hold: ["hold", v => v, v => v],
               p_conf: ["conf", v => v / 100, v => v + "%"],
               p_mpm:  ["mpm",  v => v, v => (+v).toLocaleString()] };
Object.entries(PMAP).forEach(([id, [key, conv, fmt]]) => {
  const el = $(id);
  el.addEventListener("input", () => {
    P[key] = conv(+el.value); $(id + "_v").textContent = fmt(el.value); render();
  });
});
["f_q","f_price","f_miles","f_year","f_body","f_make","f_noacc","f_nostale"]
  .forEach(id => $(id).addEventListener("input", render));
document.querySelectorAll("thead th.sortable").forEach(th => {
  th.addEventListener("click", () => {
    const k = th.dataset.k;
    if (k === sortKey) sortDir = -sortDir;
    else { sortKey = k; sortDir = (k === "price" || k === "total" || k === "miles") ? 1 : -1; }
    render();
  });
});
$("reset").addEventListener("click", () => {
  W = Object.assign({}, W0); P = Object.assign({}, P0);
  WKEYS.forEach(k => { $("w_" + k).value = W0[k]; $("w_" + k + "_v").textContent = W0[k]; });
  $("p_hold").value = P0.hold; $("p_hold_v").textContent = P0.hold;
  $("p_conf").value = Math.round(P0.conf * 100); $("p_conf_v").textContent = Math.round(P0.conf * 100) + "%";
  $("p_mpm").value = P0.mpm; $("p_mpm_v").textContent = P0.mpm.toLocaleString();
  $("p_tgt").value = P0.target; $("p_tgt_v").textContent = "$" + P0.target.toLocaleString();
  ["f_q","f_price","f_miles","f_year"].forEach(id => $(id).value = "");
  ["f_body","f_make"].forEach(id => $(id).value = "");
  ["f_noacc","f_nostale"].forEach(id => $(id).checked = false);
  sortKey = "score"; sortDir = -1;
  PICK.clear(); syncPickUI(); render();
});

// --- freshness -----------------------------------------------------------
(function freshness() {
  const built = new Date(P0.builtAt);
  const el = $("fresh"), age = $("freshage"), why = $("freshwhy");
  if (!el || isNaN(built)) return;
  const stamp = built.toLocaleString(undefined,
    { weekday: "short", month: "short", day: "numeric",
      hour: "numeric", minute: "2-digit" });
  function tick() {
    const mins = Math.max(0, Math.round((Date.now() - built) / 60000));
    let s;
    if (mins < 2)        s = "pulled just now";
    else if (mins < 60)  s = `pulled ${mins} minutes ago`;
    else if (mins < 2880) s = `pulled ${Math.round(mins / 60)} hours ago`;
    else                 s = `pulled ${Math.round(mins / 1440)} days ago`;
    age.textContent = s;
    el.classList.toggle("warn", mins >= 1440 && mins < 4320);
    el.classList.toggle("stale", mins >= 4320);
    why.textContent = mins >= 4320
      ? `— ${stamp}. This is old; prices and availability have moved. Refresh before you drive anywhere.`
      : (mins >= 1440
          ? `— ${stamp}. More than a day old; check anything before you drive to it.`
          : `— ${stamp}`);
  }
  tick();
  setInterval(tick, 60000);
})();

// --- API budget ----------------------------------------------------------
(function budget() {
  const u = P0.usage || {}, el = $("budget");
  if (!el) return;
  if (u.left == null && u.used == null) { el.textContent = ""; return; }
  const cap = u.cap != null ? u.cap : 1000;
  const used = u.used != null ? u.used : (cap - u.left);
  const left = u.left != null ? u.left : (cap - used);
  const per = u.perRun ? ` · a refresh costs about ${u.perRun}` : "";
  el.innerHTML = `auto.dev calls: <b>${left.toLocaleString()}</b> of `
    + `${cap.toLocaleString()} left this month${per}`;
})();

// --- shortlist -----------------------------------------------------------
function pickCount() { return PICK.size; }

function syncPickUI() {
  const b = $("shortbtn");
  b.textContent = `Shortlist (${pickCount()})`;
  b.disabled = pickCount() === 0;
}

document.getElementById("tb").addEventListener("change", ev => {
  const cb = ev.target.closest("input[data-pick]");
  if (!cb) return;
  const id = cb.getAttribute("data-pick");
  if (cb.checked) PICK.add(id); else PICK.delete(id);
  cb.closest("tr").classList.toggle("picked", cb.checked);
  syncPickUI();
});

function buildSheet() {
  const chosen = DATA.filter(c => PICK.has(c.id))
    .map(c => ({ c, r: scoreOf(c, P, W) }))
    .sort((a, b) => b.r.score - a.r.score);

  const when = new Date(P0.builtAt).toLocaleString(undefined,
    { weekday: "long", month: "long", day: "numeric", hour: "numeric", minute: "2-digit" });

  const cards = chosen.map(({ c, r }) => {
    const w = walkAway(c, P, P.target);
    const over = w != null && c.price != null && c.price > w;
    const phoneBits = [c.dealer, c.city].filter(Boolean).map(esc).join(" · ");
    const flags = [];
    if (c.acc) flags.push(`${c.acc} reported accident${c.acc > 1 ? "s" : ""}`);
    if (c.days >= 21) flags.push(`on the lot ${c.days} days — ask why`);
    if (c.drop) flags.push(`already cut ${money(c.drop)}`);
    if (c.tooGood) flags.push("priced well under comparable cars — check the title");
    if (c.relNote) flags.push(c.relNote);
    if (r.proj && r.proj.milesAtSale > 140000) {
      flags.push(`about ${r.proj.milesAtSale.toLocaleString()} miles by resale`);
    }
    return `<div class="card">
      <h3><a href="${esc(c.url)}" target="_blank" rel="noopener">${c.y} ${esc(c.mk)} ${esc(c.md)}</a></h3>
      <div class="sub2">${esc(c.tr || "")}</div>
      <div class="sub2">${phoneBits}${c.color ? " · " + esc(c.color) : ""}</div>
      <dl>
        <div><dt>Asking</dt><dd>${money(c.price)}</dd></div>
        <div><dt>Walk away above</dt>
             <dd class="${over ? "" : "ceiling"}">${w == null ? "—" : money(w)}</dd></div>
        <div><dt>Miles</dt><dd>${c.miles == null ? "—" : c.miles.toLocaleString()}</dd></div>
        <div><dt>Cost to own</dt><dd>${money(r.total)}</dd></div>
        <div><dt>Score</dt><dd>${r.score.toFixed(0)}</dd></div>
      </dl>
      ${flags.length ? `<div class="why">${flags.map(esc).join(" · ")}</div>` : ""}
    </div>`;
  }).join("");

  $("sheet").innerHTML = `
    <div class="sheetbar">
      <button id="sheetprint">Print / save as PDF</button>
      <button class="ghost" id="sheetback">Back to the board</button>
    </div>
    <h2>Shortlist — ${chosen.length} car${chosen.length === 1 ? "" : "s"}</h2>
    <p class="when">Prices as of ${esc(when)}. Walk-away ceilings assume
       ${P.hold} months, ${(+P.mpm).toLocaleString()} miles a month and a
       $${(+P.target).toLocaleString()} target.</p>
    ${cards}
    <p class="hint-save">Tip: "Print / save as PDF" also works on a phone —
       choose Save to Files, or share it straight from the print sheet.</p>`;

  $("sheetprint").addEventListener("click", () => window.print());
  $("sheetback").addEventListener("click", () => {
    document.body.classList.remove("sheeton");
    window.scrollTo(0, 0);
  });
}

$("shortbtn").addEventListener("click", () => {
  if (!pickCount()) return;
  buildSheet();
  document.body.classList.add("sheeton");
  window.scrollTo(0, 0);
});

syncPickUI();
render();
"""
