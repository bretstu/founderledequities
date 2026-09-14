# Founder Led Equities: the plan

Written 2026-09-13, after the redesign brief and the conversation that
followed it; the two copy corrections of the same day are in. This is the document to read before any product decision.
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

The rule: the free tier is the current S&P 500 picture plus twelve
months of trades, and the whole universe's last seven days; Pro is more
names, the archive, longer windows, the export and a list of watches. The calculation is identical
on both sides of the seal. Pro is more of the same file, never a
different lens.

### Free (no card)

- The current S&P 500 picture: stake, shares, value, founder or hired
  with the proxy's sentence, confidence, the stake-over-time chart (and
  the price-with-trades toggle), and the last twelve months of trades
  with filing links, on every S&P company page; the scoreboard, the
  screener and its filters over the S&P. The archive before that is
  not free, S&P or not.
- The tape for the last seven days, for every company in the universe:
  every purchase, sale and compensation filing by any chief executive,
  with the name, the kind (bought / discretionary / planned /
  compensation), the manner, the date and the amount. The amount is the
  Form 4's own number and shows on every row; the stake after the trade
  is the number only this site computes, and it is sealed outside the
  S&P (blurred on the page, "in Pro" in the email). Decided 2026-09-13
  after two other drafts were considered: blurring both figures made
  the free tape read worse than a Form 4 site without protecting
  anything of ours; opening both gave away the product's own number
  each week.
- The Monday email: the week's tape in those terms.
- One founder watch: an email when that one person buys on the open
  market or makes a discretionary sale.
- The performance chart with its survivorship caveat, the method,
  everything that explains the number.
- Rows for every company everywhere: a sealed company appears in its
  true rank with its name, founder badge and dates; its figures are
  blurred placeholders drawn by CSS (the numbers are not in the free
  files; there is nothing to un-blur).

### Pro: $15 a month or $150 a year, card-backed 14-day trial, cancel in one click (set 2026-09-14; the brief's $19/$190 was the starting point)

- The figures for the ~1,600 companies outside the S&P: stake, shares,
  value, and the size of every trade, current and past.
- The archive: every trade since 2016 on every name, S&P included.
- The tape at 30 days, 90 days and 12 months.
- CSV export of the scoreboard and the tape, kind columns included.
- A watchlist instead of one watch.

Not sold in either tier: recommendations, real-time quotes, speed to
the Form 4, a different formula behind the paywall, a second tier.

Copy rule: never "the full S&P is free," and never "history is Pro"
without saying which history, since twelve months are open. The
accurate line, used verbatim on the hero, the /pro page and the email:

> S&P 500 current stakes and the last twelve months are open. The
> archive, every other $1B+ name, longer tape windows, and export are Pro.

## 3. Why anyone pays (the conversation of 2026-09-13)

The free tier is dynamic on purpose. Because the seven-day tape covers
the whole universe, every Monday there is something true and new to
send, and the email never invents or withholds what happened this week:
who traded, what kind, how much. What it withholds is the one number
this site computes (the stake after the trade) for names outside the
S&P, and everything older than a week. Four moments, all created by
the free tier, turn a reader into a subscriber:

1. The email names someone outside the S&P with the trade: "Mark Lappe
   bought $2.6M at Inhibrx." What does he own now? In Pro. This is the
   most frequent moment and it is the pitch sentence in one line: other
   sites show the Form 4; this site shows whether the stake moved. Most
   interesting buyers are outside the index, which is mostly hired CEOs
   with small stakes.
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
product. A free visitor has used every screen, chart and table on 500
companies with a year of real numbers, and the email every Monday. Pro removes the blur from
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

Nav: Tape · Companies · Method · Pro; right side "Weekly tape, free"
and "Go Pro" (or Account when signed in).

- `/` in this order (revised 2026-09-14: one list, two depths): hero
  (headline "What the person running the company still owns.", subhead,
  three live stats, two buttons, the quiet line from the copy rule
  above, the week in one line), **What they own now** (the screener's
  own table at a depth of twenty rows, by share of the company, the
  dollar column beside it, "All companies" at the foot), **This week's
  tape** (twelve rows, the Monday-email field), footer. No bar board,
  no index chart, no second copy of the list: a block that cannot say
  which of the two jobs it serves does not ship.
- `/companies/`: the same table in full, with search, thresholds,
  founders only, never sold, sort, export, and "N more match in Pro";
  the A-Z index of every company page beneath it.
- Founders against the index is evidence, not a product: a static SVG
  drawn at deploy (ops/perf_svg.py) under "Why founder-led" on the
  Method page, with the survivorship caveat. No /performance page.
- No card grid on the tape, page or letter (decided 2026-09-13, after a
  four-card version was drawn: "largest buy" and "biggest add" were the
  same event split by S&P membership, and the cards existed to give the
  seal a box). The weather line is the summary; the table, grouped by
  kind and ranked by size within each, is the tape; its first rows are
  the largest buy and the largest discretionary sale. The letter may
  carry a two-line kicker (largest open-market buy; largest
  discretionary sale) as a lede. A 10b5-1 sale or a compensation filing
  is never featured anywhere: "the sale of the week was a plan set
  months ago" is the Form 4 site's sentence.
- `/tape`: the full tape with windows 7d/30d/90d/12m (free: 7d;
  longer windows Pro) and toggles (founders only, on by default;
  open-market buys; hide compensation). Columns: Kind · Company · CEO ·
  Amount · New stake · Manner; the amount on every row, the new stake
  blurred outside the S&P. Kind groups in the brief's order, ranked by
  stake change within each. The subhead names the week's dates. For a
  free reader the 30d/90d/12m chips are dimmed and open the Pro box; the
  Pro note sits under the chips, never in their row. The signup box is
  the letter only; watches live on company pages. The archive of past
  tapes (`/tape/2026-09-14/`) is Pro beyond the current week.
- The letter: the weather line, the optional two-line kicker, the same
  six columns with kinds as full words, the largest of each kind (about
  a dozen rows, one compensation row), a small outlined "Pro" tag where
  a stake is sealed, one button to `/tape`, the copy rule verbatim,
  unsubscribe and the postal line.
- `/company/:ticker`: the current shape (name, ticker, market cap; the
  four cards; the chart with Stake default and Price toggle; the trades
  table with its kinds). Free S&P: last twelve months; Pro: the archive.
  Sealed pages as built: the question, one line, blurred cards, the
  price line, a year of blurred trades. Watch box under the chart.
- `/pro`: the one plan card ($15/month or $150/year), the four bullets,
  the trial buttons, the quiet line, the copy rule.
- `/about` (Method): the essay, unchanged, plus the one-person line at
  the top; pricing moved out to /pro.

## 5a. Email: the weekly and the alerts

Two jobs, one provider.

- The Monday tape is a broadcast: one message to a list, with signup,
  unsubscribe and an archive. A watch alert is transactional: one
  message to one person, triggered by a filing, sent by the pipeline.
- Provider: Resend, for both. A transactional API for the alerts and
  Audiences + Broadcasts for the list (unsubscribes handled, sends can
  be scheduled). One domain verification, one key, one place to look.
  Free to 3,000 emails a month. Substack is ruled out (it moves the
  audience onto another domain); Buttondown would be the pick if there
  were no alerts; Beehiiv is the wrong shape.
- The archive lives on this site (`/tape/2026-09-14/`): indexable, and
  what the email links to. Never on another domain.
- The weekly is never automatic. The nightly's Monday run writes a
  draft (an editable file and a rendered preview) and nothing is sent
  until a person runs `ops/send-tape.sh`, or finishes the draft
  broadcast in Resend's dashboard and presses Send there. The pipeline
  prepares; the person sends.
- The alerts are the opposite: one fixed template, sent by the nightly
  when a watched founder buys on the open market or sells at discretion,
  no hand in the loop. Built 2026-09-14: the watch box sits under the
  record on every company page (one free per email, confirmed by a
  click; a signed-in Pro reader is watching at once and can watch a
  list); the watches live in the D1 database on Cloudflare, never on
  the mini PC; the nightly posts the day's decisions to /api/watch/run
  with a shared secret (ALERTS_KEY), the function matches them to the
  watches, sends one email per watcher and records each (watch, filing)
  so nothing is sent twice; every alert carries a one-click stop link.
  A second watch by a free reader answers "You're watching Musk. A list
  of names is Pro."
- The look is ours, not the provider's: an HTML template built once in
  the site's design (paper, a serif headline set in Georgia since mail
  clients do not load web fonts, the counts line, the four cards, the
  tape table reduced to the five columns that fit, sealed names with
  "in Pro" where the figure would be, one link to `/tape`, the plain
  footer), table-based with inline styles, tested in Gmail, Apple Mail
  and Outlook before the first send.
- Legitimacy is not the template: an authenticated sending domain (SPF,
  DKIM, DMARC on founderledequities.com), a consistent from-address
  (tape@founderledequities.com), a working unsubscribe link and the
  List-Unsubscribe header, a physical-address line in the footer
  (CAN-SPAM), and double opt-in so the list is people who asked.
- Setup: DNS records on the Cloudflare zone; an API key in the
  pipeline's environment beside the Polygon key; a signup endpoint (a
  Pages function that adds an address to the audience, double opt-in);
  the digest rewritten to the tape's terms and drafted by the Monday
  run. The watches, later in the order, reuse the key and a D1 table.

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
   design (section 5a: Resend, the drafted-not-sent weekly, our
   template). The digest from weekly.py, rewritten; the leaderboard
   image attached. This is the cadence and the only item that changes
   the visitor count. Both the /tape page and the email are shown as
   rendered mocks in the new design before either is built.
2. `/pro` page, price change to $15 / $150, card-backed Stripe trial.
3. Homepage restructure and the design system across the site.
4. Sealing rule on S&P company pages (archive behind Pro, last twelve
   months free); the screener's "N more match in Pro" counts from the
   build; the copy fix.
5. Watch box with a cap of one; Pro watchlist; the nightly diff and
   sends.
6. Named screens on the companies table: never sold, own more than
   10%, bought this year, hired under 1%, each a chip and a URL on
   /companies/ (?screen=never-sold), each counted over every company at
   build so a free reader's screen says how many more match in Pro.
   Built 2026-09-14.

Out of scope for this pass: coverage below $1B, international issuers,
an API, a second tier, recommendations, YouTube/Discord/podcast.

## 8. Acceptance checks

- A logged-out visitor sees Tesla's and Nvidia's current stake and
  chart, and their last twelve months of trades, not their archive.
- A logged-out visitor cannot see the current stake of a non-S&P name.
- The seven-day tape lists every company's filings for everyone with
  the amount; the stake after the trade is blurred outside the S&P;
  nothing is invented.
- Compensation never counts as "cut a stake."
- `/tape` and `/pro` exist as pages; `/pro` states $15 / $150.
- The watch cap of one is enforced (at the request and at the confirming click).
- The Method page still explains the number in full.
