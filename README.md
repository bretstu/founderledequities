# Founder Led Equities

What the chief executive of each US public company worth $200M or more owns
of the company they run, computed from the SEC filings they signed. Live at
<https://founderledequities.com>.

```
ownership  =  common stock the CEO holds  /  shares outstanding
```

Both sides come from structured filings (Forms 3/4/5 and the XBRL cover
page). Nothing is estimated. How the number is computed, and why, is in
[notes/METHOD.md](notes/METHOD.md).

## How it fits together

```
fle/        the pipeline: EDGAR client, the ledger walk, ownership, events, founders
ops/        the nightly and the deploy: site data, page builder, alerts, cards
functions/  Cloudflare Pages functions: /api/watch, /api/subscribe, /api/hit
*.html      page templates          assets/*.js   each page's own script
universe/   tracked inputs: the company list, the exclusions register
tests/      pytest                  _harness.js   render checks (needs the data files)
notes/      product, plan, method, what was tried and abandoned
```

A Linux box runs the pipeline nightly and pushes static files to Cloudflare
Pages. The data files (`panel.csv`, `history.csv`, `events.csv`, ...) are
generated and not in git.

## Setup

```bash
pip install -r requirements.txt -r requirements-dev.txt
cp .env.example .env      # set FLE_USER_AGENT to a real contact address
python -m pytest -q
```

SEC fair access requires a User-Agent naming the caller. Without one EDGAR
returns 403s that look like rate limits.

## Use

```bash
python -m fle.cli ceo         --cik 789019     # who the certification names
python -m fle.cli ledger      --cik 1318605    # every line, with its date
python -m fle.cli outstanding --cik 1318605    # the denominator and its history
python -m fle.cli refresh     --dir .          # the nightly: rebuild, check, publish
python -m fle.cli --help                       # everything else
```

Deploy with `ops/deploy.sh` (`FLE_QUICK=1` for a code-only change);
`ops/preview.sh` builds the same tree and serves it locally. Going live and
staying live: [ops/OPERATIONS.md](ops/OPERATIONS.md). Accounts and recovery:
[ops/ACCOUNTS.md](ops/ACCOUNTS.md).

## Three things the front end does that are easy to miss

1. **`index.html` is the stylesheet.** `ops/build_company_pages.py` lifts its
   `<style>` blocks into `site.css` (comments stripped), and every other page
   links that file. A page's own `<style>` holds only what is its own.
2. **`index.html` is the shared script.** Every declaration that follows a
   `/*@shared*/` marker is lifted into `company.js`, `tape.js`,
   `companies.js`, `alerts.js` and `signin.js`, ahead of that page's file in
   `assets/`. A shared declaration must not touch the DOM or page state.
3. **The built pages are not the templates.** The nav, the numbers and the
   version stamps are written in at build; open `public/` (or the live site)
   to see what a visitor gets.

## Notes

- [notes/THE-PRODUCT.md](notes/THE-PRODUCT.md): what the site is, the
  ownership definition, who would pay
- [notes/THE-PLAN.md](notes/THE-PLAN.md) and
  [notes/DISTRIBUTION.md](notes/DISTRIBUTION.md): the plan and the weekly work
- [notes/HANDOFF.md](notes/HANDOFF.md): the rules the project adopted and
  the open items
- [notes/TRIED-AND-ABANDONED.md](notes/TRIED-AND-ABANDONED.md): paths
  investigated and dropped, so they are not rediscovered
