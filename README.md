# Founder Led Equities — v2

What a chief executive owns of the company they run.

```
ownership  =  common stock the CEO holds  /  shares outstanding
```

Both sides come from structured filings. No model runs, no HTML is parsed,
nothing is typed in by hand.

| | source | format | current to |
|---|---|---|---|
| numerator | Form 3/4/5, Table I + convertible classes | XML, fixed schema | 2 business days |
| denominator | `dei:EntityCommonStockSharesOutstanding` | XBRL cover page | last quarter |
| identity | Section 302 certification | exhibit to 10-K/10-Q | last quarter |

## Why v2 exists

v1 read the proxy statement. Item 403 mandates *content* but not *format*, so
that needed a model, table-location heuristics, denominator corroboration and
a verification worksheet — and the metric it produced was directionally wrong.

v1 counted options exercisable within 60 days in the numerator, over a
denominator that excludes them. Exercising an option issues shares, so the
denominator grows while the numerator does not:

| | on exercise | comparable across companies |
|---|---|---|
| `common / outstanding` | **rises** — correct | yes |
| `13d-3 / (outstanding + their options)` | unchanged | no |
| `13d-3 / outstanding` — **v1** | falls | yes |

Musk exercised 303,960,630 options and v1 moved him from 21.6% to 19.8%.

## What survives from v1

**The Section 302 identity path**, because it is the only signal that does not
guess. Job titles returned Meta's Chief Legal Officer, Apple's General
Counsel, an Nvidia director, and Microsoft's "CEO Microsoft Commercial"
instead of Satya Nadella.

**The name matching**, because it correctly refuses those, and handles
`Musk Elon` against `Elon Musk` and `BANCEL STEPHANE` against `Stéphane Bancel`.

**The EDGAR client** — rate limiter, cache, retries.

Everything else is new.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env      # set FLE_USER_AGENT to a real contact address
python -m pytest tests/ -q
```

SEC fair access requires a User-Agent naming the caller. Without one you get
403s that look like rate limits.

## Use

```bash
# one company, showing its working
python -m fle.cli ceo         --cik 789019     # who the certification names
python -m fle.cli ledger      --cik 1318605    # every line, with its date
python -m fle.cli outstanding --cik 1318605    # the denominator and its history

# the whole index
python -m fle.cli index                                   # dated membership snapshot
python -m fle.cli panel --universe universe/sp500-2026-08-25.csv \
                        --checkpoint panel.jsonl --out panel.csv

python -m fle.cli panel --universe universe/sp500-2026-08-25.csv --redo failed
```

The panel resumes: rows are appended to the checkpoint as they finish, so an
interrupted run loses at most one company. `--redo failed` retries errors and
walks that did not settle, and leaves settled rows alone.

`ledger` prints the working, not just the answer — every v1 failure was
silent, and each was caught by a human noticing a number looked wrong.

## Reading a Form 4

A line is **three fields**: security title × direct/indirect × nature of the
indirect holding. Not a row position.

```
1  Common Stock  06/16  M  303,960,630  A  $23.34   727,704,534  D
2  Common Stock  06/16  F   17,531,857  D  $404.66  710,172,677  D
3  Common Stock    —    —        —      —     —     413,152,109  I  By Trust
```

Rows 1 and 2 are the same line; row 2 supersedes. Row 3 is a different line
and carries no transaction at all — it exists to restate the balance.

```
710,172,677 + 413,152,109 = 1,123,324,786
```

Four rules the code follows, each a bug v1 shipped:

1. **Group by line, not by row.** "The last row" and "the biggest number" are
   both wrong almost always.
2. **Within a filing the last row wins; across filings the newest does.**
   Getting the second backwards keeps `727,704,534` — the balance after Musk's
   exercise and before the shares withheld to pay for it.
3. **Carry lines a filing omits.** Holding rows are customary, not mandatory.
4. **Table II is not only options.** A class convertible into another is a
   derivative by definition. Zuckerberg's Class B is 341,232,288 of his
   342,463,325.

## What is counted

Issued common stock, including unvested restricted stock — issued, votable,
and in the denominator, so excluding it would make this the outlier. It is
flagged, because it matters far more to what a stake is *worth* than to what
fraction it represents. Options and RSUs are reported separately and never
added.

## The known gap

Losing the proxy loses the one **independent** statement of the same number,
and every ledger bug in v1 was caught by an outside reference rather than by
internal logic — a ledger adds up whether or not it has missed a line.

So the checks here ask whether the ledger is *complete*, not whether it is
self-consistent: did the walk settle, was a direct line ever seen, did the
denominator jump, are the two dates far apart. Re-adding the proxy as an
annual cross-check — not as a source — is the first thing on the list.

## The panel is the verification sheet

v1 kept them apart — a panel of answers, and a worksheet built from it later —
which meant the answers shipped first and the checking came second, if at all.

Every row here carries `form4_url` and `cover_url`. Checking one means opening
two filings and comparing two numbers, and there are `checked_shares`,
`checked_by` and `note` columns to write the result into. Rows sort by
ownership, so the ones worth checking first are at the top.

## Not yet built

Prices · the conversion ratio for classes that are not 1:1 (Berkshire's Class A is 1,500
Class B) · the annual proxy cross-check · the site.
