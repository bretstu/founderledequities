"""Render the public-facing analytics page.

Distinct from `dashboard.py`, which is an internal review tool. This one is
for a reader who wants to know which chief executives actually own the
companies they run.

The organising idea comes from the filings themselves. In a proxy statement,
a holder below one percent gets an asterisk instead of a number -- the
document declines to print a figure, because the amount is beneath notice.
Most CEOs are asterisks. So the page is built around that line: a threshold
you can move, and a field that collapses as you raise it.

Everything is embedded, so the output is a single file that opens anywhere.
"""
from __future__ import annotations

import html
import json
from datetime import datetime, timezone


def _rows_from_records(records: list[dict]) -> list[dict]:
    """Keep only rows a reader can act on, ordered by ownership."""
    rows = []
    for r in records:
        pct = r.get("pct_comparable")
        if r.get("error") or not isinstance(pct, (int, float)) or pct <= 0:
            continue
        if not r.get("ceo_name"):
            continue
        rows.append({
            "co": r.get("company") or r.get("ticker") or f"CIK {r.get('cik')}",
            "tk": (r.get("ticker") or "").upper(),
            "ceo": r.get("ceo_name"),
            "sh": r.get("shares_13d3"),
            "pct": round(float(pct), 4),
            "url": r.get("source_url") or "",
            "yr": (r.get("filing_date") or "")[:4],
            # A quiet quality marker. Readers do not need our vocabulary, but
            # they are entitled to know which figures we are least sure of.
            "q": 0 if r.get("confidence") == "HIGH" else 1,
        })
    rows.sort(key=lambda x: -x["pct"])
    return rows


def build_site(records: list[dict], title: str = "Skin in the Game") -> str:
    rows = _rows_from_records(records)
    payload = json.dumps(rows, separators=(",", ":"))
    stamp = datetime.now(timezone.utc).strftime("%d %B %Y")
    return _TEMPLATE.replace("{{DATA}}", payload) \
                    .replace("{{TITLE}}", html.escape(title)) \
                    .replace("{{STAMP}}", stamp)


def write_site(records: list[dict], path: str, title: str = "Skin in the Game") -> None:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(build_site(records, title))


_TEMPLATE = r"""<!doctype html>
<html lang="en"><head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{{TITLE}} — CEO ownership of US public companies</title>
<meta name="description" content="What share of each US public company its chief executive actually owns, from SEC proxy statements.">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Instrument+Serif:ital@0;1&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
:root{
  --paper:#eef0f3;
  --card:#f8f9fa;
  --ink:#14181f;
  --slate:#5a6472;
  --rule:#d3d8de;
  --brass:#a8741a;
  --brass-lt:#d9ac54;
  --teal:#1d5b63;
  --below:#9aa4b1;
}
*{box-sizing:border-box}
html{-webkit-text-size-adjust:100%}
body{
  margin:0;background:var(--paper);color:var(--ink);
  font-family:"IBM Plex Sans",ui-sans-serif,-apple-system,"Segoe UI",sans-serif;
  font-size:16px;line-height:1.5;
  padding:0 1.25rem 5rem;
}
.wrap{max-width:1060px;margin:0 auto}

/* ---------- masthead ---------- */
header{padding:3.5rem 0 0}
.eyebrow{
  font-family:"IBM Plex Mono",ui-monospace,monospace;
  font-size:11px;letter-spacing:.16em;text-transform:uppercase;
  color:var(--slate);margin:0 0 1.25rem;
}
h1{
  font-family:"Instrument Serif",Georgia,serif;
  font-size:clamp(3rem,9vw,5.5rem);line-height:.92;
  font-weight:400;margin:0;letter-spacing:-.015em;
}
h1 em{font-style:italic;color:var(--brass)}
.lede{
  font-family:"Instrument Serif",Georgia,serif;
  font-size:clamp(1.3rem,3.2vw,1.95rem);line-height:1.3;
  margin:1.75rem 0 0;max-width:24ch;color:var(--ink);
}
.lede b{font-style:normal;font-weight:400;color:var(--brass);
        font-variant-numeric:tabular-nums}
.lede .of{color:var(--slate)}

/* ---------- threshold control ---------- */
.control{
  margin:2.75rem 0 0;padding:1.5rem 1.5rem 1.25rem;
  background:var(--card);border:1px solid var(--rule);border-radius:2px;
}
.control-head{
  display:flex;justify-content:space-between;align-items:baseline;
  gap:1rem;margin-bottom:.9rem;flex-wrap:wrap;
}
.control-label{
  font-family:"IBM Plex Mono",monospace;font-size:11px;
  letter-spacing:.14em;text-transform:uppercase;color:var(--slate);
}
.readout{font-family:"IBM Plex Mono",monospace;font-size:13px;color:var(--slate)}
.readout b{color:var(--ink);font-weight:500}

/* distribution: every company as a tick, so the skew is visible */
.dist{
  position:relative;height:54px;margin-bottom:-2px;
  display:flex;align-items:flex-end;gap:1px;
}
.dist span{
  flex:1;background:var(--below);min-height:2px;border-radius:1px 1px 0 0;
  transition:background .18s ease;
}
.dist span.on{background:var(--brass-lt)}
.dist-axis{
  position:absolute;left:0;right:0;bottom:0;height:1px;background:var(--rule);
}

input[type=range]{
  -webkit-appearance:none;appearance:none;width:100%;
  background:transparent;margin:.5rem 0 0;cursor:pointer;
}
input[type=range]::-webkit-slider-runnable-track{
  height:2px;background:var(--rule);
}
input[type=range]::-moz-range-track{height:2px;background:var(--rule)}
input[type=range]::-webkit-slider-thumb{
  -webkit-appearance:none;width:20px;height:20px;border-radius:50%;
  background:var(--brass);border:3px solid var(--card);margin-top:-9px;
  box-shadow:0 0 0 1px var(--brass);
}
input[type=range]::-moz-range-thumb{
  width:20px;height:20px;border-radius:50%;background:var(--brass);
  border:3px solid var(--card);box-shadow:0 0 0 1px var(--brass);
}
input[type=range]:focus-visible{outline:2px solid var(--teal);outline-offset:6px}

.scale{
  display:flex;justify-content:space-between;
  font-family:"IBM Plex Mono",monospace;font-size:10.5px;color:var(--slate);
  margin-top:.4rem;
}
.presets{display:flex;gap:.4rem;flex-wrap:wrap;margin-top:1rem}
.presets button{
  font:inherit;font-size:12.5px;font-family:"IBM Plex Mono",monospace;
  padding:.3rem .75rem;background:transparent;color:var(--slate);
  border:1px solid var(--rule);border-radius:2px;cursor:pointer;
  transition:all .15s ease;
}
.presets button:hover{border-color:var(--brass);color:var(--brass)}
.presets button[aria-pressed=true]{
  background:var(--ink);border-color:var(--ink);color:var(--paper);
}

/* ---------- toolbar ---------- */
.toolbar{
  display:flex;gap:.75rem;align-items:center;
  margin:2rem 0 .5rem;flex-wrap:wrap;
}
.search{
  flex:1;min-width:190px;font:inherit;font-size:14px;
  padding:.5rem .75rem;background:var(--card);
  border:1px solid var(--rule);border-radius:2px;color:var(--ink);
}
.search:focus{outline:none;border-color:var(--teal)}
.sortsel{
  font:inherit;font-size:13px;padding:.5rem .6rem;background:var(--card);
  border:1px solid var(--rule);border-radius:2px;color:var(--ink);cursor:pointer;
}

/* ---------- table ---------- */
table{width:100%;border-collapse:collapse;margin-top:.5rem}
thead th{
  font-family:"IBM Plex Mono",monospace;font-size:10.5px;font-weight:500;
  letter-spacing:.12em;text-transform:uppercase;color:var(--slate);
  text-align:left;padding:.6rem .7rem;border-bottom:1px solid var(--ink);
  white-space:nowrap;
}
th.r,td.r{text-align:right}
tbody tr{border-bottom:1px solid var(--rule)}
tbody tr.hidden{display:none}
td{padding:.85rem .7rem;vertical-align:middle}
.rank{
  font-family:"IBM Plex Mono",monospace;font-size:12px;color:var(--slate);
  width:2.5rem;
}
.co{font-weight:500;line-height:1.25}
.co a{color:var(--ink);text-decoration:none;border-bottom:1px solid transparent}
.co a:hover{border-bottom-color:var(--brass);color:var(--brass)}
.tkr{
  display:inline-block;font-family:"IBM Plex Mono",monospace;font-size:11px;
  color:var(--slate);margin-left:.45rem;
}
.ceo{color:var(--slate);font-size:14.5px}
.num{font-family:"IBM Plex Mono",monospace;font-size:13.5px;
     font-variant-numeric:tabular-nums;white-space:nowrap}
.pctcell{width:32%;min-width:150px}
.pctval{
  font-family:"IBM Plex Mono",monospace;font-size:14px;font-weight:500;
  font-variant-numeric:tabular-nums;display:block;margin-bottom:.3rem;
}
.track{height:4px;background:var(--rule);border-radius:2px;overflow:hidden}
.fill{height:100%;background:var(--brass);border-radius:2px;
      transition:width .3s cubic-bezier(.2,.8,.3,1)}
.fill.low{background:var(--below)}
.est{color:var(--slate);cursor:help}

/* ---------- empty + footer ---------- */
.empty{
  padding:3.5rem 1rem;text-align:center;color:var(--slate);
  font-family:"Instrument Serif",Georgia,serif;font-size:1.35rem;
}
.empty span{display:block;font-family:"IBM Plex Sans",sans-serif;
            font-size:.85rem;margin-top:.6rem}
footer{
  margin-top:3.5rem;padding-top:1.5rem;border-top:1px solid var(--rule);
  color:var(--slate);font-size:13.5px;max-width:68ch;
}
footer p{margin:0 0 .8rem}
footer b{color:var(--ink);font-weight:500}
.stamp{font-family:"IBM Plex Mono",monospace;font-size:11px;margin-top:1.25rem}

@media (max-width:720px){
  header{padding-top:2.25rem}
  .hide-s{display:none}
  .pctcell{width:38%;min-width:110px}
  td{padding:.7rem .4rem}
  .control{padding:1.1rem}
}
@media (prefers-reduced-motion:reduce){
  *{transition:none !important;animation:none !important}
}
</style></head>
<body><div class="wrap">

<header>
  <p class="eyebrow">SEC proxy statements · Rule 13d-3</p>
  <h1>Skin in<br>the <em>game</em></h1>
  <p class="lede">
    Of <b id="total">0</b> <span class="of">chief executives,</span>
    <b id="count">0</b> <span class="of">own more than</span>
    <b id="thr">1.0%</b> <span class="of">of the company they run.</span>
  </p>
</header>

<section class="control">
  <div class="control-head">
    <span class="control-label">Owns more than</span>
    <span class="readout">each mark is one company · <b id="shown">0</b> shown</span>
  </div>
  <div class="dist" id="dist" aria-hidden="true"><div class="dist-axis"></div></div>
  <input type="range" id="slider" min="0" max="1000" value="200" step="1"
         aria-label="Minimum ownership percentage">
  <div class="scale"><span>0%</span><span>1%</span><span>5%</span><span>12%</span><span>25%</span></div>
  <div class="presets" id="presets">
    <button data-v="0" aria-pressed="false">Any</button>
    <button data-v="0.5" aria-pressed="false">0.5%</button>
    <button data-v="1" aria-pressed="true">1%</button>
    <button data-v="5" aria-pressed="false">5%</button>
    <button data-v="10" aria-pressed="false">10%</button>
  </div>
</section>

<div class="toolbar">
  <input class="search" id="search" type="search"
         placeholder="Search company or chief executive" aria-label="Search">
  <select class="sortsel" id="sort" aria-label="Sort by">
    <option value="pct">Ownership, highest first</option>
    <option value="sh">Shares, most first</option>
    <option value="co">Company, A–Z</option>
  </select>
</div>

<table>
  <thead><tr>
    <th class="rank"></th>
    <th>Company</th>
    <th class="hide-s">Chief executive</th>
    <th class="r hide-s">Shares owned</th>
    <th>Share of company</th>
  </tr></thead>
  <tbody id="body"></tbody>
</table>
<div class="empty" id="empty" style="display:none">
  No chief executive owns that much.
  <span>Lower the threshold to see more.</span>
</div>

<footer>
  <p><b>What this measures.</b> Beneficial ownership under Rule 13d-3: shares
  the chief executive can vote or sell, including those held through trusts
  and family entities, plus options they could exercise within 60 days. It
  excludes unvested grants. Figures come from each company's annual proxy
  statement — click a company to read the filing it was taken from.</p>

  <p><b>Why our percentages differ from the filing.</b> A company calculates
  each person's percentage against a share count that includes that person's
  own options and nobody else's, which makes the printed figures
  incomparable between companies. We divide by total shares outstanding
  instead, so these numbers can be ranked against one another.</p>

  <p><b>A caution.</b> Ownership is not the same as commitment, and a large
  stake can reflect inheritance or a founding position as easily as
  conviction. Figures marked <span class="est">*</span> passed fewer of our
  automated checks and are worth reading against the filing.</p>

  <p class="stamp">Data as of {{STAMP}} · Not investment advice</p>
</footer>

</div>
<script>
const DATA = {{DATA}};
const MAX = 25;                       // slider ceiling, in percent
const body = document.getElementById('body');
const dist = document.getElementById('dist');
const slider = document.getElementById('slider');
const search = document.getElementById('search');
const sortSel = document.getElementById('sort');

// The slider is squared rather than linear. Ownership clusters hard below 2%,
// so a linear track would spend most of its travel in empty space and make
// the interesting range impossible to hit.
const posToPct = p => Math.pow(p / 1000, 2) * MAX;
const pctToPos = v => Math.round(Math.sqrt(Math.min(v, MAX) / MAX) * 1000);

const fmtInt = n => n == null ? '—' : Math.round(n).toLocaleString('en-US');
const fmtPct = v => v >= 10 ? v.toFixed(1) + '%'
                  : v >= 1  ? v.toFixed(2) + '%'
                            : v.toFixed(3) + '%';

// One tick per company, ordered by ownership: the shape of the distribution
// is the finding, so it is shown rather than described.
const ticks = [];
DATA.forEach(d => {
  const s = document.createElement('span');
  const h = Math.pow(d.pct / (DATA[0]?.pct || 1), 0.4) * 100;
  s.style.height = Math.max(3, h) + '%';
  s.title = d.co + ' · ' + fmtPct(d.pct);
  dist.appendChild(s);
  ticks.push({el: s, pct: d.pct});
});

DATA.forEach((d, i) => {
  const tr = document.createElement('tr');
  tr.dataset.i = i;
  const name = d.url
    ? `<a href="${d.url}" target="_blank" rel="noopener">${d.co}</a>`
    : d.co;
  const low = d.pct < 1 ? ' low' : '';
  const w = Math.min(100, Math.pow(d.pct / MAX, 0.45) * 100);
  tr.innerHTML =
    `<td class="rank"></td>
     <td class="co">${name}${d.tk ? `<span class="tkr">${d.tk}</span>` : ''}</td>
     <td class="ceo hide-s">${d.ceo}${d.q ? ' <span class="est" title="Passed fewer automated checks">*</span>' : ''}</td>
     <td class="num r hide-s">${fmtInt(d.sh)}</td>
     <td class="pctcell">
       <span class="pctval">${fmtPct(d.pct)}</span>
       <span class="track"><span class="fill${low}" style="width:${w}%"></span></span>
     </td>`;
  body.appendChild(tr);
});
const trs = Array.from(body.children);

document.getElementById('total').textContent = DATA.length;

function apply() {
  const thr = posToPct(+slider.value);
  const q = search.value.trim().toLowerCase();
  let shown = 0;

  trs.forEach(tr => {
    const d = DATA[+tr.dataset.i];
    const hit = !q || d.co.toLowerCase().includes(q) || d.ceo.toLowerCase().includes(q);
    const ok = d.pct > thr && hit;
    tr.classList.toggle('hidden', !ok);
    if (ok) tr.firstElementChild.textContent = ++shown;
  });

  ticks.forEach(t => t.el.classList.toggle('on', t.pct > thr));

  document.getElementById('thr').textContent = fmtPct(thr);
  document.getElementById('count').textContent = DATA.filter(d => d.pct > thr).length;
  document.getElementById('shown').textContent = shown;
  document.getElementById('empty').style.display = shown ? 'none' : 'block';

  document.querySelectorAll('#presets button').forEach(b => {
    b.setAttribute('aria-pressed', String(Math.abs(+b.dataset.v - thr) < 0.02));
  });
}

function sortRows() {
  const key = sortSel.value;
  const order = [...trs].sort((a, b) => {
    const x = DATA[+a.dataset.i], y = DATA[+b.dataset.i];
    if (key === 'co') return x.co.localeCompare(y.co);
    if (key === 'sh') return (y.sh || 0) - (x.sh || 0);
    return y.pct - x.pct;
  });
  order.forEach(tr => body.appendChild(tr));
  apply();
}

slider.addEventListener('input', apply);
search.addEventListener('input', apply);
sortSel.addEventListener('change', sortRows);
document.querySelectorAll('#presets button').forEach(b => {
  b.addEventListener('click', () => {
    slider.value = pctToPos(+b.dataset.v);
    apply();
  });
});

slider.value = pctToPos(1);
apply();
</script>
</body></html>
"""
