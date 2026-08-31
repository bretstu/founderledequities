# Running the site

## Nightly

    python -m fle.cli refresh --dir C:\Users\bret1\founderledequitiesv4

One command. It rebuilds the panel, **checks the nine verified holdings**,
walks history for companies that actually filed, refreshes prices, and
re-reads the proxies weekly. Nothing reaches the live folder unless every
stage succeeds; each file is moved into place with a single atomic rename.

Exit codes -- these are what a scheduler should watch:

| code | meaning | what to do |
|------|---------|------------|
| 0 | published | nothing |
| 1 | a stage failed | read `refresh.log`; yesterday's data is still live |
| 2 | a verified holding moved | **look before overriding**; then `--force` |

Code 2 is the important one. It means the pipeline produced a different
answer for a holding that was reconciled against a proxy. That is either a
real corporate event or a regression, and it must be a person who decides
which.

## Scheduling it

**Windows** -- Task Scheduler, daily at 04:00, action:

    python -m fle.cli refresh --dir C:\Users\bret1\founderledequitiesv4

Tick "Run whether user is logged on or not". Point "Start in" at the folder.

**Linux/macOS** -- a systemd timer or cron:

    0 4 * * *  cd /srv/fle && /usr/bin/python3 -m fle.cli refresh --dir /srv/fle >> /srv/fle/cron.log 2>&1

Run it after 04:00 Eastern so the prior close and the day's filings are in.

## Why it is fast enough to run nightly

A full history walk over 500 companies takes hours. Almost none of them
file on a given night, so `refresh` remembers the newest Section 16
accession per company in `history-state.json`; if it has not moved, the
prior rows are carried over and the walk is skipped. One cheap request
replaces the rebuild.

To force a full rebuild -- after a rule change -- delete
`history-state.json` and run again.

## Files it writes

| file | what it is |
|------|-----------|
| `sp500.csv` | the panel: one row per company |
| `history.csv` | a snapshot after every filing |
| `prices.csv` | closing prices |
| `founders.csv` | the founder flag with its evidence |
| `founder-overrides.csv` | hand-settled verdicts, applied last (optional) |
| `history-state.json` | newest accession per company; delete to force a rebuild |
| `panel-diff.csv` | what moved since yesterday |
| `refresh.log` | every run, appended |

## Before going live

- Remove the developer toggle from the HTML (it unlocks Pro for everyone).
- `history.csv` and `founders.csv` are served whole to the browser. Any
  paywall must split these server-side; hiding rows in JavaScript is not a
  paywall.
- Check the price licence before publishing dollar figures commercially.
