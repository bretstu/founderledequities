# CEO Ownership Pipeline

Builds a validated dataset of **what percent of a company its CEO actually owns**, from SEC filings.

```
pct_comparable = common shares beneficially owned by the CEO
                 (direct + indirect, disclaimed excluded, derivatives excluded)
                 ÷ total shares outstanding, all classes
```

## Quick start

```bash
pip install -r requirements.txt

# See the whole thing work with no credentials and no network:
python3 demo.py
python3 -m unittest discover -s tests

# Then, for real data:
export OWNERSHIP_UA="Your Name your@email.com"   # SEC requires this
export ANTHROPIC_API_KEY="sk-ant-..."

python3 -m ceo_ownership.cli run --tickers AAPL,META,TSLA,BRK-B --out results.csv
python3 -m ceo_ownership.cli run --tickers META --as-of 2019-06-30   # point-in-time
python3 -m ceo_ownership.cli universe --year 2019 --out universe_2019.csv
```

Start with 10–20 tickers, read the `flags` and `validation` columns, then scale.

## The two percentages

The pipeline emits both, and they are **not** interchangeable.

| Column | What it is | Use it for |
|---|---|---|
| `pct_reported` | Exactly as printed by the filer | Auditing against the source document |
| `pct_comparable` | Our number, one denominator for everyone | **Sorting, ranking, backtesting** |

They differ because Rule 13d-3(d)(1)(i) deems a person's own exercisable options outstanding *for their percentage only*. Every row in a proxy table has a different denominator, so reported percentages are not comparable across companies. Ranking on `pct_reported` is a silent correctness bug. `demo.py` shows the gap concretely.

## Why derivatives are excluded

An unexercised option is a right to buy, not ownership — and an underwater one is worth nothing at all. A CEO holding 5M options struck at $80 on a $25 stock would otherwise appear as a major owner.

Nothing real is lost by excluding them. A Form 4 option exercise is a *paired* transaction: code M disposes of the derivative in Table II and simultaneously acquires the underlying common in Table I. Anything exercised, vested, settled, or converted is already in the common count.

**The one genuine gap is Up-C structures** — LLC/LP units exchangeable 1:1 for Class A shares are real economic ownership held in derivative form. These are flagged (`upc_exchangeable_units_excluded`), never silently included. Review that list by hand.

## Survivorship bias

`universe.py` builds the company list from EDGAR's quarterly `master.idx` — the record of what was actually filed at the time. Companies that later went bankrupt or were acquired are present because they filed while alive. Survivorship becomes structurally impossible rather than something you patch later.

This matters more than extraction accuracy. Founder-controlled firms fail and go private at elevated rates, so building the universe from companies that exist today would delete disproportionately from the high-ownership group and manufacture fake outperformance.

Three related guards, all enforced in code:

- **Look-ahead** — every date cutoff keys on `filing_date`, never the as-of date printed inside a document. A proxy stating March holdings isn't public until April.
- **Restatement overwrite** — `outstanding.snapshot()` freezes denominators at ingest, because companyfacts keeps only the latest value and a restatement rewrites history.
- **Exit classification** — `find_exits()` returns `exit_reason=None` deliberately. Merger exits and failure exits need opposite return assumptions, and guessing is how backtests break.

Delisting returns are not included; `yfinance` drops delisted tickers entirely. Read Shumway on delisting bias before choosing a convention, or use CRSP.

## Validation

Three checks, each proving something different:

| Check | Proves | Blind spot |
|---|---|---|
| `pct_reconciliation` | Shares, percentage, denominator, and option split are all correct at once | **Passes on the wrong person's row** |
| `group_bound` | CEO ≤ "all directors and officers as a group" | Coarse |
| `identity_match` + `form4_divergence` | Right human, right number, from an independent document | Needs a locatable Form 3/4/5 |

`assign_confidence` requires `identity_match` to pass before awarding HIGH. Reconciliation can never substitute for confirming the human, because every row in a table reconciles internally — including the CFO's.

Most large-cap CEOs show an asterisk rather than a percentage (sub-1%), which silently removes them from check 1. That's why the group row exists as a fallback anchor.

## Known limitations

- **Coverage** ~10–15% of small caps incorporate Item 403 by reference; the pipeline falls back to 10-K/A and flags it.
- **Foreign private issuers** were historically exempt from Section 16. The 2026 NDAA removed that exemption but implementation is still settling — verify current state before scoping them in.
- **Extraction is not free.** See Cost below.
- **`--as-of` is honest but slow** — it re-derives everything from filing history rather than reading a prebuilt panel.

## Cost

One model call per company, per proxy year. Everything else is free SEC data.

Three levers, all already implemented:

1. **Tables are sent as text, not HTML.** `table_to_text()` strips inline styles, span wrappers and XBRL attributes before the call -- typically 8-15x fewer input tokens on real EDGAR filings.
2. **Responses are cached on content hash** under `.cache/extractions/`. Re-runs and iteration cost nothing; only genuinely new filings are billed. Delete that folder to force re-extraction.
3. **The model is configurable** via `--model` or `OWNERSHIP_MODEL`. Haiku is roughly an order of magnitude cheaper than Sonnet and this is a well-specified schema-filling task -- benchmark it on your golden set before assuming you need the larger model.

There is also a fourth lever: skip the LLM entirely. `form4.py` computes the same metric from Table I with no API call, giving up the proxy cross-check and the clean annual as-of date. Running Form-4-primary across thousands of companies is free.

Check current token prices at https://www.anthropic.com/pricing -- do not trust a hardcoded estimate here.

## Calibration

Automated validators tell you a row passed; they don't tell you what "passed" is worth. Hand-label ~150 companies stratified across market-cap deciles once, measure the false-pass rate, and you can then quote a defensible accuracy figure. Re-calibrate annually, not per run.

Expected: **~99% accuracy on the ~85–92% of rows that pass both validators.** The residual is definitional (disclaimed shares, indirect holdings, Up-C units), not fixable by better parsing.

## Layout

```
ceo_ownership/
  config.py       metric definition + security-title allowlists  <- start here
  edgar.py        rate-limited SEC client (8 req/s) with disk cache
  universe.py     point-in-time universe from master.idx
  proxy.py        proxy discovery + table locator (scoring heuristic)
  extract.py      LLM extraction with footnote decomposition
  form4.py        Form 4 Table I parser (independent validator)
  outstanding.py  denominator from XBRL companyfacts
  validate.py     the three checks + confidence assignment
  pipeline.py     orchestration -> OwnershipRecord
  cli.py          run / universe / exits
demo.py           offline end-to-end walkthrough
tests/            26 offline tests
```

Every number carries `source_url`, `filing_date`, `as_of_date`, `confidence`, and `flags`. On a public dashboard, publish the confidence state — 4,500 verified rows plus 500 marked "unverified, see filing" is more credible than 5,000 rows at unstated quality.
