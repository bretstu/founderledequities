"""Render pipeline results as a single self-contained HTML page.

The page has one job: let you see, in a few seconds, which rows to distrust.
So confidence, provenance and flags are foreground -- not decoration around a
league table -- and every figure links back to the filing it came from. A
dashboard for a dataset this young is a review tool first and a chart second.

No network, no API calls, no dependencies. Just a file you can open.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone

CONF_ORDER = {"HIGH": 0, "MEDIUM": 1, "LOW": 2, "UNKNOWN": 3}

# Flags that describe the FILER, not a problem with our reading.
BENIGN_FLAGS = {
    "ceo_transition_in_period",
    "combined_certification_multiple_signers",
    "multi_class",
    "shares_pledged",
}


def _esc(v) -> str:
    return html.escape(str(v)) if v is not None else ""


def _fmt_int(v) -> str:
    return f"{v:,.0f}" if isinstance(v, (int, float)) else "—"


def _fmt_pct(v) -> str:
    if not isinstance(v, (int, float)):
        return "—"
    return f"{v:.3f}%" if v >= 0.001 else "<0.001%"


def _bar(pct: float | None, max_pct: float) -> str:
    if not isinstance(pct, (int, float)) or max_pct <= 0:
        return ""
    # Square root keeps sub-1% holders visible next to a 20% founder; a linear
    # scale renders most of the dataset as an invisible sliver.
    width = 100.0 * (pct / max_pct) ** 0.5
    return f'<span class="bar" style="width:{width:.1f}%"></span>'


def build_dashboard(records: list[dict], title: str = "CEO ownership") -> str:
    rows = [r for r in records if not r.get("error")]
    errs = [r for r in records if r.get("error")]
    rows.sort(
        key=lambda r: (
            -(r.get("pct_comparable") or 0),
            CONF_ORDER.get(r.get("confidence"), 9),
        )
    )
    max_pct = max((r.get("pct_comparable") or 0) for r in rows) if rows else 1.0

    n = len(records)
    high = sum(1 for r in rows if r.get("confidence") == "HIGH")
    med = sum(1 for r in rows if r.get("confidence") == "MEDIUM")
    low = sum(1 for r in rows if r.get("confidence") == "LOW")
    free = sum(1 for r in records if r.get("resolution") == "free_path")
    funds = sum(1 for r in records
                if "likely_investment_company" in (r.get("flags") or []))

    body = [_HEAD.replace("{{TITLE}}", _esc(title))]
    body.append(f'''
<header>
  <p class="eyebrow">Rule 13d-3 beneficial ownership &middot; SEC proxy statements</p>
  <h1>{_esc(title)}</h1>
  <p class="sub">What share of each company its chief executive beneficially owns.
     Every figure links to the filing it came from.</p>
  <dl class="stats">
    <div><dt>Companies</dt><dd>{n}</dd></div>
    <div><dt>High confidence</dt><dd class="c-high">{high}</dd></div>
    <div><dt>Medium</dt><dd class="c-med">{med}</dd></div>
    <div><dt>Low</dt><dd class="c-low">{low}</dd></div>
    <div><dt>Could not read</dt><dd class="c-err">{len(errs)}</dd></div>
    <div><dt>No API call needed</dt><dd>{free}</dd></div>
  </dl>
  {'<p class="note">' + str(funds) + ' filers look like funds or trusts rather than operating companies. They are shown but should be excluded from analysis.</p>' if funds else ''}
</header>

<nav class="filters">
  <button data-filter="all" class="on">All</button>
  <button data-filter="HIGH">High confidence</button>
  <button data-filter="review">Needs review</button>
  <button data-filter="flagged">Flagged</button>
</nav>

<table>
  <thead>
    <tr>
      <th class="num">%</th>
      <th>Company</th>
      <th>Chief executive</th>
      <th class="num">Shares</th>
      <th>Read from</th>
      <th>Confidence</th>
      <th>Notes</th>
    </tr>
  </thead>
  <tbody>''')

    for r in rows:
        conf = r.get("confidence") or "UNKNOWN"
        flags = r.get("flags") or []
        concerning = [f for f in flags if f.split(":")[0] not in BENIGN_FLAGS]
        classes = [f"conf-{conf}"]
        if conf != "HIGH":
            classes.append("review")
        if flags:
            classes.append("flagged")

        src = r.get("shares_source") or ""
        src_label = {
            "proxy_item403": "proxy",
            "form4_all_classes": "Form 4",
        }.get(src, src or "—")
        col = (r.get("column_used") or "").replace("column=", "")

        yoy = r.get("yoy_change_pct")
        yoy_txt = f"{yoy:+.1f}% y/y" if isinstance(yoy, (int, float)) else ""

        notes = []
        for f in flags:
            cls = "chip warn" if f.split(":")[0] not in BENIGN_FLAGS else "chip"
            notes.append(f'<span class="{cls}">{_esc(f.split(":")[0])}</span>')
        if yoy_txt:
            notes.append(f'<span class="chip quiet">{_esc(yoy_txt)}</span>')

        url = r.get("source_url") or ""
        name = r.get("company") or r.get("ticker") or f"CIK {r.get('cik')}"
        ident = r.get("ceo_identity_source") or ""

        body.append(f'''
    <tr class="{' '.join(classes)}">
      <td class="num pct">{_fmt_pct(r.get('pct_comparable'))}{_bar(r.get('pct_comparable'), max_pct)}</td>
      <td class="co">{'<a href="' + _esc(url) + '" target="_blank" rel="noopener">' if url else ''}{_esc(name)}{'</a>' if url else ''}
          <span class="tick">{_esc(r.get('ticker') or '')}</span></td>
      <td>{_esc(r.get('ceo_name') or '—')}<span class="tick">{_esc(ident.replace('sox302_ex31','§302 cert').replace('ixbrl_peoname','PvP tag').replace('form4_title','title guess'))}</span></td>
      <td class="num">{_fmt_int(r.get('shares_13d3'))}</td>
      <td class="src">{_esc(src_label)}<span class="tick">{_esc(col)}</span></td>
      <td><span class="conf c-{conf.lower()}">{_esc(conf)}</span></td>
      <td class="notes">{''.join(notes)}</td>
    </tr>''')

    body.append("  </tbody>\n</table>")

    if errs:
        body.append('<h2>Could not read</h2><table class="errs"><tbody>')
        for r in errs:
            name = r.get("company") or r.get("ticker") or f"CIK {r.get('cik')}"
            url = r.get("source_url") or ""
            body.append(f'''
    <tr>
      <td class="co">{'<a href="' + _esc(url) + '" target="_blank" rel="noopener">' if url else ''}{_esc(name)}{'</a>' if url else ''}</td>
      <td class="why">{_esc((r.get('error') or '')[:220])}</td>
    </tr>''')
        body.append("</tbody></table>")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    body.append(f'''
<footer>
  <p>Ownership is measured under Rule 13d-3: securities over which the person
     holds voting or investment power, plus anything they may acquire within
     60&nbsp;days. That includes options exercisable now, shares held through
     trusts and controlled entities, and pledged shares. It excludes unvested
     awards.</p>
  <p>Percentages are computed against total shares outstanding across all
     classes, so they are comparable between companies. A filer's own printed
     percentage is not: Rule&nbsp;13d-3(d)(1)(i) puts each holder's options
     into their own denominator alone.</p>
  <p class="stamp">Generated {stamp}</p>
</footer>
<script>
const btns = document.querySelectorAll('.filters button');
btns.forEach(b => b.addEventListener('click', () => {{
  btns.forEach(x => x.classList.remove('on'));
  b.classList.add('on');
  const f = b.dataset.filter;
  document.querySelectorAll('tbody tr').forEach(tr => {{
    tr.style.display = (f === 'all' || tr.classList.contains(f)) ? '' : 'none';
  }});
}}));
</script>
</body></html>''')
    return "\n".join(body)


_HEAD = """<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}}</title>
<style>
:root{
  --ink:#12161c; --paper:#fbfaf7; --rule:#e2ded5; --dim:#6c7076;
  --high:#1f6f4a; --med:#8a6d18; --low:#9c3024; --accent:#2b4a7d;
}
*{box-sizing:border-box}
body{
  margin:0; padding:2.5rem 1.5rem 4rem; background:var(--paper); color:var(--ink);
  font:15px/1.55 ui-sans-serif,-apple-system,"Segoe UI",Roboto,sans-serif;
  max-width:1180px; margin-inline:auto;
}
.eyebrow{
  font-size:11px; letter-spacing:.14em; text-transform:uppercase;
  color:var(--dim); margin:0 0 .5rem;
}
h1{font-size:2rem; margin:0 0 .35rem; letter-spacing:-.02em; font-weight:650}
.sub{margin:0 0 1.5rem; color:var(--dim); max-width:56ch}
.note{
  margin:1rem 0 0; padding:.6rem .8rem; background:#fff6e5;
  border-left:3px solid var(--med); font-size:13.5px;
}
.stats{display:flex; flex-wrap:wrap; gap:0; margin:0; border-top:1px solid var(--rule)}
.stats div{padding:.7rem 1.6rem .7rem 0; margin-right:1.6rem; border-right:1px solid var(--rule)}
.stats div:last-child{border-right:0}
dt{font-size:11px; letter-spacing:.08em; text-transform:uppercase; color:var(--dim)}
dd{margin:.15rem 0 0; font-size:1.5rem; font-weight:600;
   font-variant-numeric:tabular-nums}
.c-high{color:var(--high)} .c-med{color:var(--med)}
.c-low,.c-err{color:var(--low)}
.filters{display:flex; gap:.4rem; margin:1.75rem 0 .75rem; flex-wrap:wrap}
.filters button{
  font:inherit; font-size:13px; padding:.35rem .8rem; cursor:pointer;
  background:transparent; border:1px solid var(--rule); border-radius:99px;
  color:var(--dim);
}
.filters button.on{background:var(--ink); color:var(--paper); border-color:var(--ink)}
table{width:100%; border-collapse:collapse; font-size:14px}
th{
  text-align:left; font-size:11px; letter-spacing:.08em; text-transform:uppercase;
  color:var(--dim); font-weight:600; padding:.5rem .6rem; border-bottom:1px solid var(--ink);
  white-space:nowrap;
}
td{padding:.6rem; border-bottom:1px solid var(--rule); vertical-align:top}
.num{text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap}
.pct{position:relative; font-weight:600; min-width:8.5rem; padding-right:.6rem}
.bar{
  display:block; height:3px; background:var(--accent); opacity:.28;
  margin-top:.3rem; margin-left:auto; border-radius:2px;
}
.co a{color:var(--ink); text-decoration:none; border-bottom:1px solid var(--rule)}
.co a:hover{border-bottom-color:var(--accent); color:var(--accent)}
.tick{display:block; font-size:11.5px; color:var(--dim); margin-top:.15rem}
.src{font-size:13px; color:var(--dim)}
.conf{font-size:11px; letter-spacing:.06em; font-weight:700}
.c-high{color:var(--high)} .c-medium{color:var(--med)} .c-low{color:var(--low)}
.notes{max-width:22rem}
.chip{
  display:inline-block; font-size:11px; padding:.1rem .45rem; margin:0 .25rem .25rem 0;
  border:1px solid var(--rule); border-radius:3px; color:var(--dim);
}
.chip.warn{border-color:#e5c9a2; background:#fdf4e5; color:#7a5a12}
.chip.quiet{border-style:dashed}
h2{font-size:1.05rem; margin:2.5rem 0 .5rem; font-weight:650}
.errs td{font-size:13px}
.errs .why{color:var(--low)}
footer{margin-top:3rem; padding-top:1.25rem; border-top:1px solid var(--rule);
       color:var(--dim); font-size:13px; max-width:70ch}
footer p{margin:0 0 .7rem}
.stamp{font-size:11.5px}
a:focus-visible,button:focus-visible{outline:2px solid var(--accent); outline-offset:2px}
@media (max-width:760px){
  body{padding:1.5rem 1rem 3rem}
  .src,.notes{display:none}
  .stats div{padding-right:1rem; margin-right:1rem}
}
</style></head><body>"""


def write_dashboard(records: list[dict], path: str, title: str) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_dashboard(records, title))


def load_records(path: str) -> list[dict]:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
