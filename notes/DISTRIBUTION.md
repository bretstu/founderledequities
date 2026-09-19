# Distribution: the plan and the weekly work

*Written 2026-09-18. The site is built; the pipeline drafts nearly every word.
What grows the audience is consistency, and this file is the reminder of what
that means in hours and in order.*

## The goal

**Two thousand letter readers.** That is the number that makes the rest
possible: a sponsor slot in the letter, a member tier that yields something,
and the audience a dataset buyer wants to see. Two hundred paying members was
the wrong intermediate goal for this product; members follow readers at one to
three percent, so the readers are the work.

## What the site is (settled 2026-09-18)

A reference with a live feed. The reference: every company page answers "how
much of X does Y own", with the history and the reasons, free, for search to
find and people to cite. The feed: the tape, the X posts and the Saturday
letter, which is how the reference gets known. Not a tool: nobody pays for
filters, and the seal that protected the numbers was blocking the funnel.

**Free:** the whole site. Every company page, every stake, every trade since
2016, the history, the Companies list with every chief executive's number, the
screens and the 12-month column, the tape at every window, the X feed, the
letter.

**Members ($69 a year, or $8 a month; 14-day trial):** live founder alerts by
email, watches on any chief executive at any company, exports as CSV, and a
free site that stays free. Members keep it that way. Why someone joins, in
order: they read the letter every Saturday and want it Thursday; they hold a
few companies and want an email rather than a timeline; they want the CSV;
they use the site and want it to exist. Expect one to three percent of
readers. Add paid things later; never re-gate free ones.

## Where the money is, in order, as the list grows

1. Sponsorship of the letter, once it has a few thousand engaged readers.
2. The member tier, small and steady.
3. The dataset licence (notes/THE-PRODUCT.md), the large one.

## The hook, in one sentence

When the person running the company changes what they own, you know within
minutes, and you know whether they meant it. Speed is table stakes; the
classification (planned / discretionary / vest / gift) and the stake number
are the product. Nobody else separates them or states the stake before and
after.

## The standing work

**Every weekday evening, ~10 minutes.** The watcher's emails arrive from about
4 p.m. Eastern (most founder Form 4s are accepted between 4 and 8 p.m.; a few
at 7 a.m.; never overnight or weekends). Each email carries the post text
ready to paste and the page link. Paste the four lines, post, reply with the
link. Discretionary buys and sales always; planned sales when the size or the
name makes them notable; nothing else. The link renders the company's card.

**Saturday morning, 30–45 minutes.** The letter. `ops/moves.py week` writes
the week's numbers and the ranked moves; read it, cut what is dull, add one
line of your own if something deserves it, send. Then the same numbers as a
short thread on X, pinned. That is the week's article, mostly written for you.

**Once a month, about an hour.** One ranked post from the stakes file
(`ops/moves.py stakes`): "the 25 founders who own the most of their company",
"who bought the most this quarter", "founders who never sold". A list people
screenshot and cite. Post it on X and, as a data-first post (not a link-first
one), on r/stocks or r/ValueInvesting.

**Once, ever, a weekend.** The methodology post: *what every Form 4 a founder
signed actually says.* About 3,000 words, eight findings, each with a filing
anyone can open: most insider sales are not decisions; a Form 4 states what
is on that filing, not what you own (Amplitude); the same shares counted twice
by reading the form correctly (Under Armour); control is not ownership (the
Biohub, the foundations); three vendors, three defensible numbers (Dudum at
16.6M / 22.6M / 23.8M); classes retire without announcement (Archer); the
record disagreeing with itself as information; how the site grades its own
numbers. For Hacker News and finance X, then a page on the site that keeps
working. The single highest-return hour of the plan.

## The multipliers (do early; they compound while you post)

- **Static screen pages** for search: `/screens/never-sold/`, `/screens/own-10-plus/`,
  `/screens/bought-this-year/` as real addresses with their own titles, instead
  of query strings Google sees as one page. Half a day.
- **The methodology post** (above).
- **The monthly ranking** (above), which gives other accounts a reason to quote.

## The format (settled)

Post: the kind in capitals, the six-word sentence, the stake line, the timing,
the link. No pronouns anywhere.

    DISCRETIONARY SALE
    Founder Keyvan Mohajer sold $869K of $SOUN.
    0.76% of the stake. Now owns 4.01%.
    Filed 9 minutes ago.
    https://founderledequities.com/company/SOUN/

Kinds: OPEN-MARKET BUY / DISCRETIONARY SALE / PLANNED SALE. The link's card is
the company's OG image (1200×630): company, person, the year's chart, the
trade line in its colour, the stake before and after.

## What not to do

- Replies on X to other accounts: tried, does not work for a data account.
- Posting the link card vs an image: the link is the card; no attachments.
- Articles every week: the letter is the week's piece; the data writes it.
- Waiting for the numbers before posting consistently: the numbers follow the
  posting by months, not the other way round.

## What to measure (weekly, Sunday, `ops/hits.sh 7` and `ops/subscribers.sh`)

- Letter subscribers added this week: the leading number. 30–50 a week after
  three months of daily posting means 200 payers arrives on schedule; 5 a week
  means the format needs changing, not the effort.
- Google referrals per week (the reference working), trial starts, members.
- t.co and google referrers; which company pages people land on.
- Churn once there are payers (5–8% a month is normal at $15).

## The longer game

The site and the audience are the proof; the alerts are a small revenue line;
the product with a real price is the dataset: a point-in-time, documented,
graded series of what founder-CEOs own, licensed to systematic investors and
"founder-led" index providers ($20k–$100k a year per licence is the normal
range for a niche alternative dataset). What that needs beyond today: a
point-in-time export (the history is most of it), a short method paper (the
About page, longer, with the grade explained and the model's role stated
plainly), one piece of evidence that founder discretionary moves or ownership
levels predict anything, and a listing on one alt-data marketplace. Keep two
columns available: beneficial ownership as reported (no model anywhere in its
lineage) and economic ownership (the register applied), so a buyer can choose
what they can defend.
