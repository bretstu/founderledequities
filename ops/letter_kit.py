#!/usr/bin/env python3
"""THE LETTER KIT (2026-09-19): one folder, zipped, with everything a research
session needs to write the featured section of this week's letter about one
chief executive's move.

    python3 ops/letter_kit.py MEDP                 # this week, the newest move at MEDP
    python3 ops/letter_kit.py MEDP 2026-09-19      # the week ending that Saturday

Writes drafts/kit-<TICKER>-<date>/ and drafts/kit-<TICKER>-<date>.zip:

    00-PROMPT.md            the opening prompt for a new Claude session
    01-the-week.md          the week's moves and numbers (ops/moves.py week)
    02-the-move.md          the filing, its footnotes, and the person's whole
                            history on the site since 2016 (events, the stake
                            over time), with the company's card
    03-company-page.md      what the site states for this company: the number,
                            the grade, the reasons, the exclusions
    04-10-K.txt             the latest annual report, whole, as text
    05-10-Q.txt             the latest quarterly report, whole
    06-8-K-earnings.txt     the latest results release (an 8-K with item 2.02
                            and its exhibit 99.1)
    07-DEF-14A.txt          the latest proxy statement, whole
    08-10b5-1-plans.md      every mention of a Rule 10b5-1 arrangement in the
                            last two years of 10-Qs and 10-Ks, with context:
                            the plans the CEO adopted or ended, and when
    09-previous-letters/    the sent issues, for the voice
    transcript.txt          empty; drop the latest earnings-call transcript in

The kit gathers; the session reasons; you write. The site's numbers are the
letter's numbers and the prompt says so.
"""
from __future__ import annotations

import csv
import datetime as dt
import glob
import html as _html
import os
import re
import shutil
import sys
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from fle.edgar import EdgarClient, html_to_text  # noqa: E402

FORMS_LATEST = {"10-K": "04-10-K.txt", "10-Q": "05-10-Q.txt", "DEF 14A": "07-DEF-14A.txt"}
PLAN_WINDOW_DAYS = 730


def read_csv(name):
    p = os.path.join(ROOT, name)
    if not os.path.exists(p):
        return []
    return list(csv.DictReader(open(p, encoding="utf-8-sig")))


def money(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    if v >= 1e9:
        return f"${v / 1e9:.1f}B"
    if v >= 1e6:
        return f"${v / 1e6:.1f}M"
    if v >= 1e3:
        return f"${v / 1e3:.0f}K"
    return f"${v:,.0f}"


def pct(v):
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ""
    return f"{v:.3f}%" if v < 1 else f"{v:.2f}%"


def filings_of(client, cik):
    subs = client.submissions(cik)
    return subs.get("_filings", []) or []


def doc_url(cik, f):
    name = (f.get("primaryDocument") or "").split("/")[-1]
    if not name:
        return ""
    return (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
            f"{(f.get('accessionNumber') or '').replace('-', '')}/{name}")


def fetch_text(client, url):
    try:
        raw = client.get(url)
    except Exception as e:  # noqa: BLE001
        return f"(could not fetch {url}: {e})"
    return html_to_text(raw)


def latest(filings, form):
    for f in filings:  # newest first
        if (f.get("form") or "").upper() == form:
            return f
    return None


def earnings_8k(client, cik, filings):
    """The latest 8-K with item 2.02 (results of operations); its exhibit 99.1
    is the release. Returns (header, text)."""
    for f in filings:
        if (f.get("form") or "").upper() != "8-K":
            continue
        items = (f.get("items") or "")
        if "2.02" not in items:
            continue
        acc = f.get("accessionNumber") or ""
        try:
            idx = client.filing_index_page(cik, acc)
        except Exception:  # noqa: BLE001
            idx = []
        ex = None
        for row in idx:
            nm = (row.get("name") or row.get("file") or "").lower()
            typ = (row.get("type") or "").upper()
            if "99" in typ or re.search(r"ex[-_]?99", nm):
                ex = row.get("name") or row.get("file")
                break
        base = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{acc.replace('-', '')}/"
        text = fetch_text(client, base + ex) if ex else fetch_text(client, doc_url(cik, f))
        head = f"8-K filed {f.get('filingDate')} ({acc}), items {items}; {'exhibit ' + ex if ex else 'the primary document'}\n{base}\n\n"
        return head, text
    return "(no 8-K with item 2.02 found)\n", ""


def plan_mentions(client, cik, filings, ceo, since):
    """Every passage mentioning a Rule 10b5-1 arrangement in the 10-Qs and 10-Ks
    filed since `since`, with context, so the CEO's plans and their dates are
    on one page."""
    out = []
    surname = (ceo or "").split()[-1] if ceo else ""
    for f in filings:
        form = (f.get("form") or "").upper()
        if form not in ("10-Q", "10-K"):
            continue
        if (f.get("filingDate") or "") < since:
            continue
        text = fetch_text(client, doc_url(cik, f))
        found = []
        for m in re.finditer(r"10b5-1", text):
            a, b = max(0, m.start() - 900), min(len(text), m.end() + 900)
            seg = text[a:b]
            if found and a < found[-1][1]:
                found[-1] = (found[-1][0], b)
            else:
                found.append((a, b))
        for a, b in found:
            seg = re.sub(r"\s+", " ", text[a:b]).strip()
            mark = " ← names the CEO" if surname and surname in seg else ""
            out.append(f"### {form} filed {f.get('filingDate')} ({f.get('accessionNumber')}){mark}\n\n…{seg}…\n")
    if not out:
        return "No mention of a Rule 10b5-1 arrangement in the 10-Qs and 10-Ks of the last two years.\n"
    return "\n".join(out)


def founder_history(tk, ceo):
    ev = sorted([e for e in read_csv("events.csv") if e.get("ticker") == tk], key=lambda x: (x.get("filed") or "", x.get("traded") or ""))
    hist = sorted([h for h in read_csv("history.csv") if h.get("ticker") == tk and (h.get("form") or "").startswith("4")], key=lambda x: x.get("date") or "")
    lines = [f"## Every move on the site for {ceo} at {tk} since 2016\n",
             "| Filed | Traded | Code | Kind | Amount | Shares | Stake after | Filing |", "|---|---|---|---|---|---|---|---|"]
    for e in ev:
        lines.append(f"| {e.get('filed','')} | {e.get('traded','')} | {e.get('code','')} | {e.get('label','')} | {money(e.get('value'))} | {e.get('shares','')} | {pct(e.get('pct_after'))} | {e.get('url','')} |")
    lines.append("\n## The stake over time (one row per Form 4 filing)\n")
    lines.append("| Date | Shares held | Groups | Unexplained |")
    lines.append("|---|---|---|---|")
    for h in hist:
        lines.append(f"| {h.get('date','')} | {float(h.get('shares') or 0):,.0f} | {h.get('groups','')} | {h.get('unexplained') or '0'} |")
    return "\n".join(lines) + "\n"


def the_move(tk, ceo, date):
    ev = [e for e in read_csv("events.csv") if e.get("ticker") == tk and (e.get("filed") or "") <= date]
    ev = [e for e in ev if e.get("code") in ("P", "S")] or ev
    if not ev:
        return f"(no move on file for {tk})\n"
    e = max(ev, key=lambda x: (x.get("filed") or "", x.get("traded") or ""))   # the newest, whatever order the file is in
    return (f"## The move\n\n- **Company:** {tk}\n- **Person:** {ceo}\n- **Kind:** {e.get('label','')} (code {e.get('code','')}, {e.get('plan','')})\n"
            f"- **Amount:** {money(e.get('value'))}\n- **Shares:** {e.get('shares','')}\n- **Traded:** {e.get('traded','')}\n- **Filed:** {e.get('filed','')}\n"
            f"- **Stake after:** {pct(e.get('pct_after'))} of the company (holding {float(e.get('holding_after') or 0):,.0f} shares of {float(e.get('outstanding') or 0):,.0f} outstanding)\n"
            f"- **Filing:** {e.get('url','')}\n- **Also filed that day:** {e.get('also_detail') or '-'}\n\n")


def company_page(tk):
    uni = {r["ticker"]: r for r in read_csv(os.path.join("public", "universe.csv"))}
    pan = {r["ticker"]: r for r in read_csv("panel.csv")}
    r = uni.get(tk) or pan.get(tk) or {}
    fd = {r["ticker"].upper(): r for r in read_csv("founders.csv")}.get(tk, {})
    out = [f"# {r.get('company', tk)} ({tk}), as the site states it\n",
           f"- CEO: {r.get('ceo','')} · founder: {fd.get('founder','?')} ({(fd.get('evidence') or '')[:300]})",
           f"- Stake: {pct(r.get('pct'))} · shares held: {float(r.get('shares') or 0):,.0f} · outstanding: {float(r.get('shares_outstanding') or r.get('outstanding') or 0):,.0f} (as of {r.get('shares_as_of','')})",
           f"- Confidence: {r.get('confidence','')} · grade checks: chain {r.get('chain','')} | statement {r.get('statement','')} | classes {r.get('classes','')}",
           f"- Problems: {r.get('problems') or '-'}", f"- Cautions: {r.get('cautions') or '-'}",
           f"- Never sold on the market: {r.get('never_sold','')} · last trade: {r.get('lt_code','')} {r.get('lt_traded','')}",
           f"- Page: https://founderledequities.com/company/{tk}/\n",
           "These are the letter's numbers. Do not restate the stake from the proxy or any other source; the proxy counts options and the site does not."]
    return "\n".join(out) + "\n"


PROMPT = """# This week's letter: the featured move

You are helping me write the featured section of this week's issue of Founder Led Equities, a weekly letter about what chief executives do with their own stakes in the companies they run. The site (https://founderledequities.com) computes every number from SEC filings and never estimates; the letter explains the two or three moves that mattered this week, one of them in depth.

**This week's featured move:** {ceo} at {company} ({tk}). The files in this folder are everything you need.

## Read in this order
1. `09-previous-letters/`: the issues already sent. Match their voice and format exactly; that is the voice the letter is written in. The format is fixed: one line on the week, ONE move in about 300 words, two shorter moves, one chart or ranking, the link to the full list.
2. `03-company-page.md`: what the site states for this company. **These are the letter's numbers.** Never restate the stake from the proxy or elsewhere.
3. `02-the-move.md`: the move itself and the person's whole history on the site since 2016.
4. `01-the-week.md`: the rest of the week, for the two shorter moves.
5. `08-10b5-1-plans.md`: every trading-plan arrangement the company disclosed in two years. Whether this move was inside a plan, and when any plan was adopted or ended, is the single most useful fact for the letter.
6. `04-10-K.txt`, `05-10-Q.txt`, `06-8-K-earnings.txt`, `07-DEF-14A.txt`: the company's own documents, whole. `transcript.txt` if I added the latest call.

## Then, before drafting, tell me
- In five sentences, what the company does and how it makes money (from the 10-K), in plain words a reader who has never heard of it will follow.
- What management said last quarter (the 8-K release; the transcript if present) and what the guidance is.
- What trading plans this CEO has on file, with dates, and whether this move was inside one.
- What this person has done before with their stake, from `02-the-move.md`: buys, discretionary sales, the stake's peak and trough since 2016.
- Anything in the proxy about the person's ownership or pay that a reader should know.
- The three things you could not find or would want verified.

## Then draft the featured section: about 300 words
Every claim points at the document it came from (name the file and quote at most a phrase). Numbers only from `03-company-page.md` and `02-the-move.md`. No prediction, no recommendation, no adjectives about the stock; what the person did, what it changed, what they have done before, and what the company is, so the reader learns something they could not get from a headline. I will edit it; you are the research partner, not the author.

Then we work on it together.
"""


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    tk = argv[0].upper()
    date = argv[1] if len(argv) > 1 else dt.date.today().isoformat()
    pan = {r["ticker"]: r for r in read_csv("panel.csv")}
    row = pan.get(tk)
    if not row:
        print(f"  {tk} is not on the panel")
        return 1
    cik, ceo, company = int(row["cik"]), row.get("ceo") or "", row.get("company") or tk
    out = os.path.join(ROOT, "drafts", f"kit-{tk}-{date}")
    shutil.rmtree(out, ignore_errors=True)
    os.makedirs(os.path.join(out, "09-previous-letters"), exist_ok=True)
    client = EdgarClient()

    # 00, 01, 02, 03: the prompt, the week, the move, the page
    open(os.path.join(out, "00-PROMPT.md"), "w", encoding="utf-8").write(PROMPT.format(ceo=ceo, company=company, tk=tk))
    import subprocess
    subprocess.run([sys.executable, os.path.join(ROOT, "ops", "moves.py"), "week", date], check=False, capture_output=True)
    wk = os.path.join(ROOT, "drafts", "moves-week.md")
    shutil.copy(wk, os.path.join(out, "01-the-week.md")) if os.path.exists(wk) else None
    open(os.path.join(out, "02-the-move.md"), "w", encoding="utf-8").write(the_move(tk, ceo, date) + founder_history(tk, ceo))
    open(os.path.join(out, "03-company-page.md"), "w", encoding="utf-8").write(company_page(tk))
    card = os.path.join(ROOT, "public", "og", f"{tk}.png")
    if os.path.exists(card):
        shutil.copy(card, os.path.join(out, "02-the-card.png"))

    # 04-07: the documents, whole
    filings = filings_of(client, cik)
    for form, name in FORMS_LATEST.items():
        f = latest(filings, form)
        if not f:
            open(os.path.join(out, name), "w", encoding="utf-8").write(f"(no {form} on file)\n")
            continue
        head = f"{form} filed {f.get('filingDate')} for the period {f.get('reportDate')} ({f.get('accessionNumber')})\n{doc_url(cik, f)}\n\n"
        open(os.path.join(out, name), "w", encoding="utf-8").write(head + fetch_text(client, doc_url(cik, f)))
        print(f"  {name}: {form} {f.get('filingDate')}")
    head, text = earnings_8k(client, cik, filings)
    open(os.path.join(out, "06-8-K-earnings.txt"), "w", encoding="utf-8").write(head + text)
    print(f"  06-8-K-earnings.txt: {head.splitlines()[0][:80]}")

    # 08: the plans
    since = (dt.date.fromisoformat(date) - dt.timedelta(days=PLAN_WINDOW_DAYS)).isoformat()
    open(os.path.join(out, "08-10b5-1-plans.md"), "w", encoding="utf-8").write(
        f"# Rule 10b5-1 arrangements disclosed by {company} since {since}\n\nFrom every 10-Q and 10-K filed in the window; each passage is the filing's own words with context. "
        f"Passages naming the CEO are marked.\n\n" + plan_mentions(client, cik, filings, ceo, since))

    # 09: the previous letters (the sent ones: weekly/letter-*.md), newest last
    for p in sorted(glob.glob(os.path.join(ROOT, "weekly", "letter-*.md")))[-6:]:
        shutil.copy(p, os.path.join(out, "09-previous-letters", os.path.basename(p)))
    open(os.path.join(out, "transcript.txt"), "w", encoding="utf-8").write("(paste the latest earnings-call transcript here, if you have it)\n")

    z = out + ".zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for base, _d, files in os.walk(out):
            for fn in files:
                full = os.path.join(base, fn)
                zf.write(full, os.path.relpath(full, os.path.dirname(out)))
    sizes = {fn: os.path.getsize(os.path.join(out, fn)) for fn in os.listdir(out) if os.path.isfile(os.path.join(out, fn))}
    print(f"  kit: {out}  ({sum(sizes.values()) / 1e6:.1f} MB of text)  zip: {z}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
