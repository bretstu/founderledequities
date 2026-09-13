# Founder Led Equities: the plan

Written 2026-09-13, after the redesign brief and the conversation that
followed it. This is the document to read before any product decision.
It says what the site is, what is free, what is paid, why anyone pays,
what the site looks like, and the order the work ships in.

## 1. What the site is

A research database of economic ownership: what the chief executive of
each US public company worth $1B or more actually owns of the company
they run, computed from the Forms 3, 4 and 5 they signed, never
estimated. For each company it answers:

- What share does this person own, in economic terms (shares whose
  value moves with the stock), not the proxy's legal definition?
- Founder or hired, by the proxy's own words?
- Did a filing move the stake, or was it compensation cashed or a plan
  set months earlier?
- Is the stake growing or shrinking, and what did it?

It is not an insider-trading alert app, a Form 4 firehose, a stock
picker, or a chart product. Nothing on it is investment advice.

The three surfaces are a scoreboard (what they own now), company pages
(one name, its record), and a tape (what moved). The business is a
Monday email that upgrades into Pro.

## 2. Free and paid

The rule: the free tier is the whole product on the S&P 500, plus the
whole universe's last seven days; Pro is more names, the archive, longer
windows, the export and a list of watches. The calculation is identical
on both sides of the seal. Pro is more of the same file, never a
different lens.

### Free (no card)

- Everything on the S&P 500: current stake, shares, value, founder or
  hired with the proxy's sentence, confidence, the stake-over-time chart
  (and the price-with-trades toggle), the last twelve months of trades
  with filing links; the scoreboard, the screener and its filters.
- The tape for the last seven days, for every company in the universe:
  every purchase, sale and compensation filing by any chief executive,
  with the name, the kind (bought / discretionary / planned /
  compensation), the manner and the date. Figures shown for S&P names;
  blurred for the rest.
- The Monday email: the week's tape in those terms.
- One founder watch: an email when that one person buys on the open
  market or makes a discretionary sale.
- The performance chart with its survivorship caveat, the method,
  everything that explains the number.
- Rows for every company everywhere: a sealed company appears in its
  true rank with its name, founder badge and dates; its figures are
  blurred placeholders drawn by CSS (the numbers are not in the free
  files; there is nothing to un-blur).

### Pro: $19 a month or $190 a year, card-backed 14-day trial, cancel in one click

- The figures for the ~1,600 companies outside the S&P: stake, shares,
  value, and the size of every trade, current and past.
- The archive: every trade since 2016 on every name, S&P included.
- The tape at 30 days, 90 days and 12 months.
- CSV export of the scoreboard and the tape, kind columns included.
- A watchlist instead of one watch.

Not sold in either tier: recommendations, real-time quotes, speed to
the Form 4, a different formula behind the paywall, a second tier.

Copy rule: never "the full S&P is free." The accurate line is "S&P 500
current stakes are open. History, every name over $1B, and export are
Pro."

## 3. Why anyone pays (the conversation of 2026-09-13)

The free tier is dynamic on purpose. Because the seven-day tape covers
the whole universe, every Monday there is something true and new to
send, and the email never invents or withholds what happened; it
withholds the sizes of the sealed names' trades and everything older
than a week or a year. Four moments, all created by the free tier,
turn a reader into a subscriber:

1. The email names someone outside the S&P. "Mark Lappe bought at
   Inhibrx." How much, and what does he own now? In Pro. This is the
   most frequent moment: most interesting buyers are outside the index,
   which is mostly hired CEOs with small stakes.
2. They care about one company and want the whole story. The free page
   shows the chart and a year of trades; the chart's shape says the
   stake went from 22% to 28%; the trades that did it are in the
   archive.
3. They use the site as a screener. The filters work identically for
   everyone; a free run of "founders who own more than 10%" returns the
   S&P's ~20 names and a line saying "N more companies match in Pro,"
   computed over the whole panel at build time. The companies that pass
   a concentrated-founder filter are overwhelmingly outside the S&P, so
   the free screen demonstrates the filter and shows how much of the
   answer is sealed.
4. They want a list. One watch is free; the second attempt says
   "You're watching Musk. A list of names is Pro." Likewise the export
   and the longer windows.

Why a buyer knows what they are getting: Pro is not a different
product. A free visitor has used every screen, chart, table and the
email on 500 companies with real numbers. Pro removes the blur from
1,600 more names, extends every table to 2016, and lets a watch become
a list. The /pro page says exactly that in four lines and one quiet
one: S&P 500 current stakes stay free.

## 4. Design

Match the art direction of the redesign mockups (2026-09-13),
correcting their factual errors (invented companies, DEF 14A as a
trade, "Line:/Sentence:" labels, rounded percentages, a typo in the
tagline).

- Surface: warm paper, near-black text, hairline warm-gray rules. No
  shadows, no cards stacked as a marketing grid, no gradients.
- Type: a refined serif for headlines and the big figures (Fraunces,
  already subset and served from the site); the grotesque for tables,
  nav and body; the mono for small labels and dates.
- Buttons: rectangular, no pill radius. Primary solid near-black;
  secondary hairline outline.
- Colour: monochrome plus one quiet system for tags: green for bought,
  red for discretionary sales, gray for planned, muted for compensation;
  a small outline badge for founder.
- Layout: max width ~1120-1200px, one column of meaning, tables
  first-class, generous space at the top, dense tables allowed.
- Motion: none beyond a smooth scroll.

The test: if it could be mistaken for a SaaS landing page, it is wrong;
if it could sit beside a footnote in a quarterly letter, it is right.

## 5. Pages and nav

Nav: Scoreboard · Tape · Companies · Performance · Method · Pro; right
side "Weekly tape, free" and "Go Pro" (or Account when signed in).

- `/` in this order: hero (headline "What the person running the
  company still owns.", subhead, three live stats, two buttons, the
  quiet line), the this-week strip, the scoreboard "What they own now",
  the tape excerpt `#tape` with the Monday-email field beside it, the
  performance chart "Founders against the index" with "A portrait, not
  a strategy."
- `/tape`: the full tape with windows 7d/30d/90d/12m (free: 7d) and
  toggles (founders only, open-market buys, hide compensation). Kind
  groups in the brief's order, ranked by stake change within each.
- `/company/:ticker`: the current shape (name, ticker, market cap; the
  four cards; the chart with Stake default and Price toggle; the trades
  table with its kinds). Free S&P: last twelve months; Pro: the archive.
  Sealed pages as built: the question, one line, blurred cards, the
  price line, a year of blurred trades. Watch box under the chart.
- `/pro`: the one plan card, the four bullets, the trial button, the
  quiet line.
- `/about` (Method): the essay, unchanged, plus the one-person line at
  the top; pricing moved out to /pro.

## 6. What already exists (do not rebuild)

Nightly EDGAR refresh and deploy at 02:30; the walk and its rules;
founders from proxy language; planned / discretionary / compensation
classification with the exercise-part-sold and award-granted labels;
the events feed with day nets, first-buy flags and cover-page rows; the
seal mechanics (masked rows with build-time ranks, blurred placeholders,
free per-company shards of a year); the sealed-page teaser; the tape
table with four cards; the harness; `ops/weekly.py`, which already
writes a digest that nobody sends.

## 7. Implementation order

1. Monday email plumbing and the `/tape` page it links to, in the new
   design. Provider: Buttondown or Resend; the digest from weekly.py;
   the leaderboard image attached. This is the cadence and the only
   item that changes the visitor count.
2. `/pro` page, price change to $19 / $190, card-backed Stripe trial.
3. Homepage restructure and the design system across the site.
4. Sealing rule on S&P company pages (archive behind Pro, last twelve
   months free); the screener's "N more match in Pro" counts from the
   build; the copy fix.
5. Watch box with a cap of one; Pro watchlist; the nightly diff and
   sends.
6. Named screens on the companies table.

Out of scope for this pass: coverage below $1B, international issuers,
an API, a second tier, recommendations, YouTube/Discord/podcast.

## 8. Acceptance checks

- A logged-out visitor sees Tesla's and Nvidia's current stake and
  chart, and their last twelve months of trades, not their archive.
- A logged-out visitor cannot see the current stake of a non-S&P name.
- The seven-day tape lists every company's filings for everyone; sealed
  figures are blurred; nothing is invented.
- Compensation never counts as "cut a stake."
- `/tape` and `/pro` exist as pages; `/pro` states $19 / $190.
- The watch cap of one is enforced.
- The Method page still explains the number in full.
