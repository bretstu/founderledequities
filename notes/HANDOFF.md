# HANDOFF — Founder Led Equities (written 2026-09-24, for the next session)

Read this first, then look for yourself. Nothing below is to be taken as
true because it is written here; the repo, the tests, and the live site are
the record, and the previous sessions were wrong often enough (see "How we
were wrong") that a fresh look is the point.

## What the project is

A site, founderledequities.com, that answers one question for every US
public company worth $1B or more (2,077 of them): how much of the company
does the chief executive own, computed from every SEC filing they signed
since 2016, never estimated, with the reasons shown when the record is
unsure. A nightly pipeline (Python, Cloudflare Pages, D1, Resend) rebuilds
the numbers, posts founder moves to X within minutes, sends alerts, and
drafts a weekly letter. Founders are marked (the proxy's own words). The
owner writes a weekly letter ("Founder Moves"); issue 1 went out 2026-09-19.

The site's edge is the *position* (ownership over time, an economic
definition, exclusions with quotes), not the transaction feed everyone
else shows.

## How the owner and the assistant work together

The owner runs everything on his own Ubuntu machine; the assistant never
touches it directly. The loop:

1. The assistant works in a sandbox copy of the repo (previous sessions
   kept it at `/home/claude/src`; a replica at `/tmp/verify` was used to
   verify packages install cleanly). Build the sandbox from the zip the
   owner shares.
2. The assistant makes a change, runs the test suite (`python3 -m pytest -q`,
   ~540 tests) and the render harness (`node _harness.js`, must print
   `ALL RENDER PATHS PASS`), and packages ONLY the changed files as
   `<name>-v<N>.zip` with the layout `fix/<path-in-repo>`. Version numbers
   ran to v330 at handoff; continue from there.
3. The owner downloads the zip and runs a one-line install command the
   assistant supplies, of the form:
   `cd ~/projects/founderledequities && unzip -oq ~/Downloads/<zip> -d /tmp/cpN && cp -r /tmp/cpN/fix/. . && .venv/bin/python -m pytest -q 2>&1 | tail -1 && node _harness.js 2>&1 | tail -1 && git add <files> && git commit -q -m "<message>" && git push -q && <deploy or walk>`
   He pastes the terminal output back. The assistant reads it and continues.
   His Python is `.venv/bin/python`; plain `python3` also works for scripts
   that need no deps.
4. Deploy: `ops/deploy.sh` (full: prices, cards, reader, pages, upload;
   10–15 min) or `FLE_QUICK=1 ops/deploy.sh` for code-only changes.
   A targeted rewalk of a few companies: `REWALK=1 FORCE=1 ops/now.sh T1,T2`.
   A full walk of every company with the diff mailed:
   `nohup .venv/bin/python -m fle.cli refresh --dir . --full > weekly-walk.log 2>&1 &`
   (about 40 minutes; also runs automatically every Sunday).
5. Probes before rules: when a change to the walk's arithmetic is proposed,
   write a read-only probe script first (`ops/*_probe.py`), run it on the
   affected companies, read the before/after together, then build. Every
   change to the walk's rules ships with its full diff (the full walk's
   mailed report), never after.

The owner is direct, wants honest odds and plain language, dislikes
flourish and hedging, and will push back hard when something is asserted
without evidence. Say "I don't know" and give a command to find out rather
than guess. He has limited Fable (this model) allowance; be efficient.

## Rules the project adopted (verify they still hold)

- No prose parsing and no model calls for anything that must be right for
  every company. Two model readers exist, narrow and verified: the founder
  reader (proxy sentences) and the footnote reader (Form 4 footnotes, rule
  B). Readers key on filings and never re-run on a walk; a prompt change is
  guarded by a golden set (116 rulings) re-read on Sundays.
- The register (`universe/exclusions.csv`) is where curated facts live,
  each with a quote and a source: whole-class rows (hand) and vehicle rows
  (from footnote decisions, `ops/footnote_register.py`). A changed row is
  rewalked the same night (`universe/rewalk-next.txt`).
- Rule B (ownership): spouse always counts; a child's trust counts unless
  someone outside the household is named trustee; foundations and other
  families' trusts do not; formula language never decides.
- The record starts 2016-01-01; "never" is never claimed, "since 2016" is.
- Partials (a stated fraction) are counted whole and flagged until a
  fraction is known.
- The Up-C rule (v326–v328): a person's LLC units count as economic
  ownership when a share class on his own filing equals them (the paired
  voting class, excluded); no match → units set aside as before; no units →
  untouched. Companies whose founders hold units with no paired class are
  hidden by the partnership census (46 of them, incl. UWM, Pershing Square,
  Blackstone, Ares, most UPREITs) because the denominator (units
  outstanding) is not in XBRL for most (probe: 4 of 46). Tabled; the path
  back is a hand `units_outstanding` column.
- A percentage over 100 is withheld with the reason (Boxabl).
- SEO: the company page's <title> is the answer ("Elon Musk owns 28.44% of
  Tesla (TSLA)"), and since v330 so is the H1 and a static first sentence.

## The current path (what the owner decided on 2026-09-24)

The pipeline is done enough. The bottleneck is audience, and the decided
strategy is:

1. SEO on the site as the main audience source (Search Console showed 7K
   impressions, 23 clicks, position 16.4 with no SEO work; page two of
   results). Weekly: the Queries tab, pages at positions 8–20, match titles
   and first sentences to the query; check indexing coverage; one backlink
   attempt a month.
2. Capture on every company page: a one-field, no-account watch ("Email me
   when Elon Musk's stake moves"; one click to confirm; free) — the API
   existed, v330 put the field in view. Measure watch signups per week; that
   is the one number that matters.
3. X daily: the pipeline's cards for founder moves at the ~30 companies
   retail investors care about, within minutes, plus one sentence of the
   owner's own view. Fridays: the week's open-market buyers as one chart
   (a card renderer for this is not yet built).
4. (The weekly letter left the site and the pipeline on 2026-09-29; any
   future letter is Substack's, with no code here.)
5. Nothing else built for ~12 weeks. Monetization later: a paid watchlist
   alert, opportunistic data licensing; affiliates and ads judged small.
   Honest odds discussed: $1K/month within 24 months maybe 30–40%.

## Open items, none urgent (verify before touching)

- Apollo (APO) was removed as "delisted" by a Form 15-12G that is almost
  certainly a reorganization; Blackstone (BX) is absent from the panel for
  an unknown reason. Both are big founder stakes missing from the list.
- Krystal Biotech (KRYS): the CEO's wife is an officer and now files her
  own Form 4s; the site shows his stake alone (5.29%) with a wrong-sounding
  flag ("fell 47% with no transaction"). Decided: leave, but fix the flag's
  wording.
- Four anonymous foundation lines the register cannot key by text (Trade
  Desk's Green 920,901 shares matters most); Venture Global counts the two
  founders' shared entity as Sabel's; Musk's unearned 2025 award is counted.
- The trading-arrangement (10b5-1) disclosures in 10-Q Item 5 / 10-K Item
  9B: a detect-and-quote step was proposed (no parsing), not built.
- Deploy is slower since the footnote reader's nightly step was added to
  deploy.sh; proposed: move it to the nightly only, add stage timings.
- The Friday buyers-list card renderer.

## How we were wrong (so the next session stays skeptical)

- Assumed the walk summed multi-line Form 4s (it doesn't; the parser was
  right; the Krystal drop was a spouse's shares moving to her own filing).
- Assumed the Companies page's data was current (it fetched
  `?v=dev` for two weeks; a cache bug; fixed v320).
- Expected the Up-C rule to move many numbers (it moved none; the site had
  been counting the paired class, right number wrong reason).
- Expected XBRL to carry units outstanding (4 of 46 do).
- Told the owner a hand register row was needed for Hagerty, then removed
  it: his filings report the Class V and never the units, so counting the
  Class V was right all along.

## Key files

- `fle/ledger.py` (the walk), `fle/ownership.py` (the record and flags),
  `fle/cli.py` (refresh, the weekly walk, anchors), `fle/footnotes.py`
  (the reader, prompt v297), `fle/exclusions.py` (the register).
- `ops/deploy.sh`, `ops/now.sh`, `ops/rewalk.sh`, `ops/build_site_data.py`,
  `ops/build_company_pages.py`, `ops/moves.py`,
  `ops/footnote_reads.py|review.py|register.py`, `ops/upc_census.py`,
  `ops/partnerships_stage.py`, `ops/brand.py`.
- `index.html` (the home page and the shared JS the other pages are built
  from; `/*@shared*/` marks what is lifted), `company.html`, `tape.html`,
  `assets/*.js`, `_harness.js`.
- Data: `panel.csv` (the current row per company), `history.csv`,
  `events.csv`, `founders.csv`, `universe/*.csv`.
- Notes: `notes/THE-PRODUCT.md`, `notes/THE-PLAN.md`,
  `notes/DISTRIBUTION.md`, and this file.
- Secrets live in `.env` on the owner's machine (never in a zip).
