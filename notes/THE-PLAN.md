# The plan (settled 2026-09-19)

*What the site is, what is sold, how a week goes, and the 90 days that test it.
Keep beside DISTRIBUTION.md (the posting work) and THE-PRODUCT.md (the value
and the ownership definition). Where those disagree with this file, this file
wins; it is the later decision.*

## The decision, in one sentence

A weekly research letter on what chief executives do with their own stakes,
written under a byline, powered by a free reference site that makes every
claim in it checkable.

The site is the reference and the proof (free, correct, cited). The letter is
the product. The pipeline is what makes the letter cheap and credible to
write. Memberships buy the letter; the site's alerts, watches and exports come
with it.

## What's free and what's paid

**Free, always:** every company page, every stake and trade since 2016, the
screens, the Activity page, the X feed of founder decisions, and the letter's
free part (the week's numbers, the list of moves, a paragraph on the two or
three that matter).

**Paid (membership, one product, sold on the site):** the letter's analysis
(the featured move, ~300 words, the person's history and the pooled base
rate), plus live alerts by email, watches on any chief executive, and exports.

**Price:** $15 a month or $149 a year once the paid part starts, with a $99 a
year founding rate for the first cohort, permanent for them. Until then the
site's Member tier stays live at $8 / $69 for anyone who wants alerts and
exports today; not promoted; whoever joins is grandfathered at what they paid.

**Not for sale:** delivery speed. The feed is advertising.

## Platform choices

- **Site:** the store (the Stripe already wired), the member sign-in, the
  gated alerts and watches, the letter archive, the reference pages.
- **Letter delivery:** the pipeline's own draft and send (Resend), from the
  site. Every issue also has a page at /letter/<date>/ and an index at
  /letter/, in the sitemap, with "Letter" in the nav.
- **Substack:** a syndication channel, not the store. The free letter is
  posted there every Saturday too, for its recommendation network and search,
  with a link to the site for membership. If the Substack list ever outgrows
  the site's, the move onto Substack is a day's work (the list exports).
- **X:** the brand account, kept. Founder decisions posted daily as cards
  with one line of context (X suppresses links; the link goes in a reply).
  A named personal account was considered and set aside: a small edge, not
  necessary. The letter is signed with your name.
- **Data licensing:** one line on the About page, inbound only. One such
  customer equals forty members.

## The letter's format (fixed, so issue 31 is possible)

1. One line on the week: the five numbers.
2. One move, about 300 words: who the person is, what the company does, what
   the stake has done since 2016 (the chart), how this move compares with
   their past ones, and the pooled base rate once the backtest exists. This
   is the research: the company nobody's heard of whose founder just acted.
3. Two shorter moves, a paragraph each.
4. One chart or ranking (the site makes them).
5. The link to the full list on the site.

One deep dive, always. When two moves are significant, the second is the
first short (150 words) and next week's candidate. A rare event (a famous
founder's first discretionary sale in a decade) gets a special issue, once or
twice a year. Hired CEOs' conviction buys are in scope: founder buys alone
cannot fill 52 issues, and the pipeline has them.

## A typical week (eight to ten hours, a pace that holds for a year)

- **Monday to Friday, ~30 minutes each evening.** The watcher's emails
  arrive; post the day's founder decisions as cards with a line of context;
  reply with a card where a larger account is discussing a company whose CEO
  just traded.
- **Saturday morning, two to three hours.** The letter, from the pipeline's
  draft and the featured-move brief; the company context is your reading.
  Send from the site; paste to Substack; the same numbers as a short thread on
  X, pinned.
- **Sunday, fifteen minutes.** Readers added, open rate, replies, whether a
  card was shared. The trend, not the count.

## The 90 days (the test of the whole plan)

1. Fix Musk's row (the 2025 award's unearned restricted shares are counted;
   the method says unvested awards are not) and Tesla's two worths (home page
   vs company page). Correctness is in scope; features are not.
2. The letter archive on the site (/letter/), the licensing line on About,
   the letter box offering both email and Substack. One zip.
3. Letter #1 this Saturday, in the format above, free in full, even with the
   backtest unstarted. Then twelve consecutive Saturdays.
4. Daily posts, cards with context, every weekday.
5. The backtest, timeboxed to four weeks, in the background: every CEO
   open-market buy above a threshold since 2016, defined by the event (not by
   what the company is worth today, which is survivorship bias), benchmarked
   by sector and size, prices from a source that keeps delisted tickers,
   written as "what happened after these buys", not as a strategy's returns.
   It is the launch piece (X, Reddit's investing subs, Hacker News) and the
   base rates the letter uses. Per-founder track records are NOT a feature:
   five buys is noise.
6. The pipeline's featured-move brief (moves.py): the founder's history from
   events.csv and history.csv, the chart, the filing links. The one build
   that serves the letter directly.
7. Nothing else built. The footnote reader finishes its hired pass
   unattended; phase two waits. Keep a list of feature ideas and do not touch
   it until after the offer.

## The founding-member offer (around week 12)

One message to the list: the letter stays free; from next month the deep
dive and the site's alerts, watches and exports are for members; the first
hundred pay $99 a year, permanently, instead of $149. Run it at ~300 readers
even if the 500 target is not reached; weigh the trend, an open rate above
~45%, replies, and whether a larger account has shared a card, over the raw
count. If 3–5% of readers buy, the letter is a business at the size the list
reaches and the tools get built for members. If under 1%, the letter is
content and the money is elsewhere (licensing, contract work), learned in 90
days instead of a year.

## Honest odds, so the goal is held loosely

Memberships alone reaching $1,000 a month: 10–20% in 12 months, 30–40% in
24, if the posting is daily and the backtest is favourable. The biggest
variable is whether the letter becomes a voice people follow; that is
writing work, not building work. Two Claude sessions agreeing is one
opinion; strangers subscribing is the only evidence.

## Why this and not the alternatives

- A tool (dashboards, screeners) needs tens of thousands of visitors;
  a letter needs a few thousand readers. Same buyer, lower requirement.
- Nobody pays for delivery of what is free on X; the feed is advertising.
- The reference pages rank slowly and are visited out of curiosity more than
  intent; keep them, do not count on them.
- Funds and index shops are the largest cheque and the slowest sale; take
  inbound, do not pitch.
- Free first, paid later, is how every comparable started (Unusual Whales,
  Quiver, Stratechery, the Substack finance letters); the exceptions had an
  audience from elsewhere.
