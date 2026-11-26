"""Build the project page published on GitHub Pages from the reports of the latest deploy.

    python scripts/build_site.py [--out _site]

Reads reports/cost.json, reports/decision.json and the dbt docs in docs/dbt/index.html (which
also give the model and test counts), and writes:

    _site/index.html       the project page: the decision, the cost, how it runs
    _site/dbt/index.html   the dbt docs: lineage and every column, browsable

No network and no cloud access: everything comes from files the deploy committed, so the page
always shows the numbers of the latest run and can be rebuilt anywhere.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
from html import escape
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REPO = "https://github.com/DiegoTDDD/olist-cloud-warehouse"
PAGE = "https://diegotddd.github.io/olist-cloud-warehouse/"
PORTFOLIO = "https://diegoalves.vercel.app/"
MB = 1024**2
TIB = 1024**4
SANDBOX_BYTES = 10 * 1024**3

ADRS = [
    ("0001-bigquery-sandbox.md", "BigQuery in sandbox mode, designed around its limits"),
    ("0002-keyless-ci.md", "CI authenticates without keys, as two least-privilege identities"),
    ("0003-raw-contracts.md", "Explicit schemas for raw, enforced contracts for marts"),
    ("0004-partitioning.md", "Integer-range partitions by month, clustered by state and status"),
    ("0005-terraform-state.md", "Terraform state stays with the one person who applies it"),
    ("0006-daily-replay-and-incremental-models.md", "Daily change feed and incremental marts without DML"),
]

FAVICON = (
    "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
    "%3Crect width='32' height='32' rx='6' fill='%2313233a'/%3E%3Cpath d='M8 22h4v-6H8zm6 0h4V10h-4zm6 0h4v-9h-4z' "
    "fill='%235fd0c4'/%3E%3C/svg%3E"
)


def dbt_counts(docs_html: str) -> dict[str, int]:
    """Models and data tests in the manifest embedded in the static dbt docs."""
    kinds = re.findall(r'"resource_type": "(model|test|source)"', docs_html)
    return {k: kinds.count(k) for k in ("model", "test", "source")}


def flat_from(buckets: list[dict]) -> dict:
    """The first late bucket within 0.15 of the lowest rating: where the decline stops.
    Same rule as scripts/decision_report.py, so the page and the report never disagree."""
    late = [b for b in buckets if b["delay_bucket_days"] > 0]
    floor = min(b["avg_review_score"] for b in late)
    return next(b for b in late if b["avg_review_score"] <= floor + 0.15)


def mb(n: float) -> str:
    return f"{n / MB:,.2f} MB" if n < 10 * MB else f"{n / MB:,.0f} MB"


def pct(x: float) -> str:
    return f"{x:.0%}"


def decision_section(buckets: list[dict], as_of: str | None = None) -> str:
    as_of_note = (
        f", with data as of {as_of}: the history is replayed one day per real day, so the numbers move as "
        "deliveries and reviews arrive"
        if as_of
        else ""
    )
    on_time = sum(b["orders"] for b in buckets if b["delay_bucket_days"] <= 0)
    late = sum(b["orders"] for b in buckets if b["delay_bucket_days"] > 0)
    day0 = next(b for b in buckets if b["delay_bucket_days"] == 0)
    day1 = next(b for b in buckets if b["delay_bucket_days"] == 1)
    flat = flat_from(buckets)
    n = flat["delay_bucket_days"]
    rows = []
    for b in buckets:
        cls = []
        if b["delay_bucket_days"] == n:
            cls.append("turn")
        if b["delay_bucket_days"] > n:
            cls.append("after")
        width = b["avg_review_score"] / 5 * 100
        tip = (f"{b['delay_bucket']}: {b['orders']:,} orders, {b['reviewed_orders']:,} reviewed, "
               f"average {b['avg_review_score']:.2f}, {b['one_star_share']:.1%} gave 1 star")  # fmt: skip
        rows.append(
            f'<tr class="{" ".join(cls)}" title="{escape(tip)}">'
            f'<th scope="row">{escape(b["delay_bucket"])}</th>'
            f'<td class="num hide-sm">{b["orders"]:,}</td>'
            f'<td class="barcell"><div class="bw"><span class="track">'
            f'<span class="bar" style="--w:{width:.1f}%"></span></span>'
            f'<span class="val">{b["avg_review_score"]:.2f}</span></div></td>'
            f'<td class="num">{b["one_star_share"]:.0%}</td></tr>'
        )
    return f"""
<section id="decision" aria-labelledby="decision-h">
  <h2 id="decision-h">Every day a delivery is late costs rating, until day {n}</h2>
  <p class="lede">{late / (on_time + late):.1%} of delivered orders arrive late. The rating falls from
  {day0["avg_review_score"]:.2f} on the promised day to {day1["avg_review_score"]:.2f} after one day and
  {flat["avg_review_score"]:.2f} after {n}; after that it barely moves. Logistics money pays off inside the
  first week of a delay: turning a 3-day delay into a 1-day one recovers rating, turning a 20-day delay
  into a 12-day one recovers almost none.</p>
  <div class="scroll">
  <table class="decision">
    <caption>Average review score by days late, {on_time + late:,} delivered orders</caption>
    <thead><tr><th scope="col">Delivery</th><th scope="col" class="num hide-sm">Orders</th>
    <th scope="col">Average rating, 1 to 5</th><th scope="col" class="num">1 star</th></tr></thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
  </div>
  <p class="note">Rebuilt on every deploy from <code>marts.mart_delivery_satisfaction</code>{as_of_note}.
  Correlation in observational data: late orders may differ in other ways.</p>
</section>"""


def cost_section(cost: dict, counts: dict[str, int]) -> str:
    b = cost["build"]
    price = cost["price_usd_per_tib"]
    build_usd = b["bytes_billed"] / TIB * price
    storage_share = cost["storage_bytes"] / SANDBOX_BYTES
    rows = [r for r in cost["benchmark"] if r["unpartitioned_bytes"]]
    top = max(r["unpartitioned_bytes"] for r in rows)
    bench = []
    for r in rows:
        saved = r["bytes_saved"]
        question = r["question"].split(" (")[0]
        bench.append(
            f'<div class="bq"><p class="q">{escape(question)}'
            f'<span class="saved">{"no saving: nothing to prune" if not saved else pct(saved) + " fewer bytes"}'
            f"</span></p>"
            f'<div class="pair" title="{escape(question)}: partitioned {mb(r["partitioned_bytes"])}, '
            f'unpartitioned {mb(r["unpartitioned_bytes"])}">'
            f'<span class="bar a" style="--w:{r["partitioned_bytes"] / top * 100:.1f}%"></span>'
            f'<span class="v">{mb(r["partitioned_bytes"])}</span>'
            f'<span class="bar b" style="--w:{r["unpartitioned_bytes"] / top * 100:.1f}%"></span>'
            f'<span class="v">{mb(r["unpartitioned_bytes"])}</span></div></div>'
        )
    return f"""
<section id="cost" aria-labelledby="cost-h">
  <h2 id="cost-h">What it costs, measured on the latest deploy</h2>
  <dl class="facts">
    <div><dt>US$ {build_usd:.4f}</dt><dd>for the latest daily build: {b["jobs"]} queries reading
    {mb(b["bytes_processed"])}, at the on-demand list price. The sandbox bills nothing.</dd></div>
    <div><dt>{storage_share:.1%}</dt><dd>of the sandbox's 10 GiB lifetime storage: {mb(cost["storage_bytes"])}
    across raw, staging, marts and ops.</dd></div>
    <div><dt>{counts["test"]} tests</dt><dd>on {counts["model"]} dbt models with enforced contracts, run on
    every pull request and every deploy.</dd></div>
  </dl>
  <h3>Bytes read by the same question, partitioned by month vs. unpartitioned</h3>
  <p class="legend"><span><i class="sw a"></i>marts.fct_orders, partitioned and clustered</span>
  <span><i class="sw b"></i>unpartitioned copy</span></p>
  <div class="bench">{"".join(bench)}</div>
  <p class="note">Each question runs on both tables with the query cache off. BigQuery bills at least 10 MB per
  query, so on tables this small the bill is the same; the bytes read are what grow with the data.</p>
</section>"""


ARCH = """
<section id="how" aria-labelledby="how-h">
  <h2 id="how-h">How it runs</h2>
  <ol class="flow">
    <li><strong>GitHub Actions</strong><span>a push, a pull request, or the daily schedule</span></li>
    <li><strong>Workload Identity Federation</strong><span>GitHub's signed token is exchanged for a Google
    token that lasts one hour. No key is stored anywhere, and only this repository, by its numeric id,
    is accepted.</span></li>
    <li><strong>Two service accounts</strong><span><em>deployer</em> writes production; <em>pr-builder</em>
    reads raw and builds in throwaway datasets.</span></li>
    <li><strong>BigQuery, São Paulo</strong><span>customer data stays in Brazil</span>
      <span class="layers"><b>raw</b><b>staging</b><b>marts</b><b>ops</b></span></li>
  </ol>
  <dl class="layer-list">
    <div><dt>raw</dt><dd>A daily change feed: the Olist history replayed one day per real day, so orders
    arrive, get delivered and get reviewed on different days. One partition per batch, replaced by a load
    job, so reruns and catch-ups are idempotent. Every source file's SHA-256 is checked.</dd></div>
    <div><dt>staging</dt><dd>dbt views: the latest version of each record, renames, casts, category
    translation.</dd></div>
    <div><dt>marts</dt><dd>Star schema and decision marts. The fact tables are incremental: each day only the
    purchase months with a changed order are rebuilt and swapped in with copy jobs (the sandbox has no
    MERGE).</dd></div>
    <div><dt>ops</dt><dd>Load audit and cost ledger, one row per run.</dd></div>
  </dl>
  <h3>How a change ships</h3>
  <ol class="steps">
    <li><strong>Every push and pull request.</strong> Lint, unit tests, <code>dbt parse</code>,
    <code>terraform validate</code> and a checkov security scan, with no cloud access.</li>
    <li><strong>Every pull request.</strong> In BigQuery, in datasets of its own: replay 31 days of data,
    build, build again incrementally, rebuild from scratch, and fail unless both builds hold the same rows.</li>
    <li><strong>Every day at 06:17, and on merge to main.</strong> Load every batch due (catching up after an
    outage), build and test incrementally, check freshness, publish the dbt docs, measure cost and rewrite the
    decision report. This page is rebuilt from those reports.</li>
    <li><strong>Every six hours.</strong> A freshness check apart from the deploy. A failed deploy or data more
    than 50 hours old opens a GitHub issue; the next good run closes it.</li>
  </ol>
  <p class="note">All infrastructure (datasets, service accounts, IAM per layer, the identity pool) is
  Terraform in <a href="{repo}/tree/main/infra">infra/</a>.</p>
</section>"""


CSS = """
:root{--paper:#f3f5f7;--ink:#13233a;--muted:#566476;--rule:#d5dbe2;--link:#0b625b;--panel:#e8ecf0;
--a:#008a7c;--b:#a35a00;--display:"Schibsted Grotesk","Helvetica Neue",Arial,sans-serif;
--text:"Source Serif 4",Georgia,"Times New Roman",serif;color-scheme:light}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#0f1a28;--ink:#e4e9ef;
--muted:#9aa8b8;--rule:#263548;--link:#5fd0c4;--panel:#172536;--a:#2aa89b;--b:#cf8526;color-scheme:dark}}
:root[data-theme="dark"]{--paper:#0f1a28;--ink:#e4e9ef;--muted:#9aa8b8;--rule:#263548;--link:#5fd0c4;
--panel:#172536;--a:#2aa89b;--b:#cf8526;color-scheme:dark}
*,*::before,*::after{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{margin:0;background:var(--paper);color:var(--ink);font:400 1.0625rem/1.65 var(--text)}
h1,h2,h3,header,footer,.facts dt,table,.legend,.bench,.flow,.layer-list dt,.btn,caption{font-family:var(--display)}
a{color:var(--link);text-underline-offset:.18em;text-decoration-thickness:1px}
a:hover{text-decoration-thickness:2px}
:focus-visible{outline:3px solid var(--link);outline-offset:3px;border-radius:2px}
code{font-size:.9em;background:var(--panel);padding:.05em .3em;border-radius:3px;overflow-wrap:anywhere}
.wrap{max-width:60rem;margin:0 auto;padding-inline:1rem}
@media (min-width:40rem){.wrap{padding-inline:1.5rem}}
header{display:flex;justify-content:space-between;align-items:center;gap:1rem;flex-wrap:wrap;
padding-block:1rem;border-bottom:1px solid var(--rule)}
header a{font-weight:700;text-decoration:none;color:var(--ink);display:inline-block;padding:.35rem 0}
header nav{display:flex;gap:1.25rem;flex-wrap:wrap}
header nav a{font-weight:500;color:var(--link)}
.intro{padding-block:2.5rem 1rem}
h1{font-size:clamp(2.1rem,6vw,3.4rem);line-height:1.05;letter-spacing:-.02em;margin:0 0 1rem;font-weight:800}
.intro p{max-width:40rem;margin:0 0 1.25rem;font-size:1.15rem}
.btns{display:flex;flex-wrap:wrap;gap:.75rem}
.btn{display:inline-block;padding:.65rem 1.1rem;border-radius:6px;font-weight:600;text-decoration:none;
border:2px solid var(--ink);color:var(--ink)}
.btn.primary{background:var(--ink);color:var(--paper)}
.stack{font-family:var(--display);color:var(--muted);font-size:.95rem;margin-top:1.25rem!important}
section{padding-block:2.5rem;border-top:1px solid var(--rule)}
h2{font-size:clamp(1.45rem,3.6vw,2rem);line-height:1.15;margin:0 0 1rem;letter-spacing:-.01em}
h3{font-size:1.1rem;margin:2rem 0 .5rem}
.lede{max-width:42rem;margin:0 0 1.5rem}
.note{color:var(--muted);font-size:.95rem;max-width:42rem}
.scroll{overflow-x:auto}
table{border-collapse:collapse;width:100%;font-size:.95rem}
caption{text-align:left;color:var(--muted);font-size:.9rem;padding-bottom:.5rem}
th,td{padding:.45rem .5rem;border-bottom:1px solid var(--rule);text-align:left;vertical-align:middle}
thead th{font-weight:600;color:var(--muted);font-size:.85rem}
tbody th{font-weight:500;white-space:nowrap}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.barcell{width:50%;min-width:9rem}
.bw{display:flex;align-items:center;gap:.5rem}
.track{flex:1 1 auto;min-width:0}
.decision .bar{display:block;height:12px;width:var(--w);background:var(--a);border-radius:0 4px 4px 0}
.decision .val{font-variant-numeric:tabular-nums;font-weight:600;min-width:2.3rem;text-align:right}
.decision tr.after .bar{opacity:.45}
.decision tr.turn th,.decision tr.turn .val{font-weight:800}
.decision tr.turn th::after{content:" \\2190 the decline stops";font-weight:500;color:var(--muted);font-size:.8rem}
@media (max-width:30rem){.hide-sm{display:none}.decision tr.turn th::after{content:""}
th,td{padding-inline:.3rem}.barcell{min-width:7rem}}
.facts{display:grid;gap:1.25rem;margin:0 0 1rem;grid-template-columns:1fr}
@media (min-width:44rem){.facts{grid-template-columns:repeat(3,1fr)}}
.facts div{border-top:3px solid var(--ink);padding-top:.6rem}
.facts dt{font-size:1.9rem;font-weight:800;line-height:1.1}
.facts dd{margin:.35rem 0 0;color:var(--muted);font-size:.95rem}
.legend{display:flex;flex-wrap:wrap;gap:.4rem 1.25rem;font-size:.9rem;color:var(--muted);margin:.25rem 0 1rem}
.legend span{display:inline-flex;align-items:center;gap:.4rem}
.sw{display:inline-block;width:12px;height:12px;border-radius:2px}
.sw.a{background:var(--a)}.sw.b{background:var(--b)}
.bq{margin-bottom:1.1rem}
.q{margin:0 0 .35rem;font-weight:600;font-size:.95rem;display:flex;flex-wrap:wrap;justify-content:space-between;
gap:.25rem 1rem}
.saved{font-weight:700;color:var(--ink)}
.pair{display:grid;grid-template-columns:1fr auto;align-items:center;gap:2px .6rem}
.pair .bar{display:block;height:10px;width:var(--w);min-width:3px;border-radius:0 4px 4px 0}
.pair .a{background:var(--a)}.pair .b{background:var(--b)}
.pair .v{font-size:.85rem;color:var(--muted);font-variant-numeric:tabular-nums;white-space:nowrap}
.flow{list-style:none;padding:0;margin:0 0 1.5rem;display:grid;gap:1.5rem;grid-template-columns:1fr}
.flow li{background:var(--panel);border-radius:8px;padding:.9rem 1rem;position:relative}
.flow li strong{display:block;font-size:1.02rem}
.flow li span{display:block;color:var(--muted);font-size:.92rem;line-height:1.45;margin-top:.25rem}
.flow li+li::before{content:"\\2193";position:absolute;top:-1.45rem;left:1.1rem;color:var(--muted);font-size:1.1rem}
@media (min-width:56rem){.flow{grid-template-columns:repeat(4,1fr);gap:1.6rem}
.flow li+li::before{content:"\\2192";top:42%;left:-1.3rem}}
.layers{display:flex!important;flex-wrap:wrap;gap:.3rem;margin-top:.6rem!important}
.layers b{font-size:.8rem;padding:.1rem .45rem;border:1px solid var(--muted);border-radius:4px;color:var(--ink);
font-weight:600}
.layer-list{display:grid;gap:.75rem;margin:0}
.layer-list div{display:grid;grid-template-columns:5.5rem 1fr;gap:.75rem}
.layer-list dt{font-weight:700}
.layer-list dd{margin:0}
.steps{padding-left:1.4rem;max-width:44rem}
.steps li{margin-bottom:.6rem}
.adrs{padding-left:1.2rem}
.adrs li{margin-bottom:.4rem}
.adrs a{display:inline-block;padding:.15rem 0}
footer{border-top:1px solid var(--rule);padding-block:1.5rem 2.5rem;color:var(--muted);font-size:.9rem}
footer p{margin:.3rem 0}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
@media print{header nav,.btns{display:none}}
"""


def render(cost: dict, decision: dict, counts: dict[str, int]) -> str:
    run_at = dt.datetime.fromisoformat(cost["run_at"])
    date = f"{run_at:%B} {run_at.day}, {run_at.year}"
    description = (
        "A data warehouse for the Olist marketplace on Google BigQuery: daily change feed, incremental dbt "
        "models, freshness alerts, Terraform, keyless CI and measured cost."
    )
    adrs = "".join(f'<li><a href="{REPO}/blob/main/docs/adr/{f}">{escape(t)}</a></li>' for f, t in ADRS)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Olist cloud warehouse</title>
<meta name="description" content="{escape(description)}">
<link rel="canonical" href="{PAGE}">
<meta property="og:title" content="Olist cloud warehouse">
<meta property="og:description" content="{escape(description)}">
<meta property="og:url" content="{PAGE}">
<meta property="og:type" content="website">
<meta name="theme-color" content="#f3f5f7" media="(prefers-color-scheme: light)">
<meta name="theme-color" content="#0f1a28" media="(prefers-color-scheme: dark)">
<link rel="icon" href="{FAVICON}">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Schibsted+Grotesk:wght@400;500;600;700;800&family=Source+Serif+4:opsz,wght@8..60,400;8..60,600&display=swap">
<style>{CSS}</style>
</head>
<body>
<div class="wrap">
<header>
  <a href="{PORTFOLIO}">Diego Alves</a>
  <nav aria-label="Project"><a href="#decision">Decision</a><a href="#cost">Cost</a><a href="#how">How it runs</a>
  <a href="{REPO}">Code</a></nav>
</header>
<main>
<div class="intro">
  <h1>Olist cloud warehouse</h1>
  <p>99,441 orders from a Brazilian marketplace, modelled in Google BigQuery so that it costs nothing and could
  still be handed to a production team. New data lands every day as a change feed, the marts update
  incrementally, a pull request must prove the incremental build equals a full rebuild, and a late or failed
  run opens an alert. Infrastructure as code, CI without keys, contracts on every table, cost measured on
  every deploy.</p>
  <div class="btns"><a class="btn primary" href="dbt/">Browse the models and lineage</a>
  <a class="btn" href="{REPO}">Read the code</a></div>
  <p class="stack">Google Cloud · BigQuery · Terraform · Workload Identity Federation · dbt · GitHub Actions</p>
</div>
{decision_section(decision["buckets"], decision.get("as_of"))}
{cost_section(cost, counts)}
{ARCH.replace("{repo}", REPO)}
<section aria-labelledby="adr-h">
  <h2 id="adr-h">Decisions, and why</h2>
  <ol class="adrs">{adrs}</ol>
</section>
</main>
<footer>
  <p>Numbers from the deploy of {date}. This page is rebuilt from that deploy's reports.</p>
  <p>Data: <a href="https://www.kaggle.com/datasets/olistbr/brazilian-ecommerce">Brazilian E-Commerce Public
  Dataset by Olist</a>, CC BY-NC-SA 4.0. Built by <a href="{PORTFOLIO}">Diego Alves</a>.</p>
</footer>
</div>
</body>
</html>
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--out", type=Path, default=ROOT / "_site")
    args = parser.parse_args()

    docs = ROOT / "docs" / "dbt" / "index.html"
    cost = json.loads((ROOT / "reports" / "cost.json").read_text())
    decision = json.loads((ROOT / "reports" / "decision.json").read_text())
    counts = dbt_counts(docs.read_text())
    if not counts["model"] or not counts["test"]:
        raise SystemExit(f"{docs}: no models or tests found in the embedded manifest")
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "index.html").write_text(render(cost, decision, counts))
    (args.out / "dbt").mkdir(exist_ok=True)
    shutil.copyfile(docs, args.out / "dbt" / "index.html")
    print(f"wrote {args.out}/index.html and dbt/index.html ({counts['model']} models, {counts['test']} tests)")


if __name__ == "__main__":
    main()
