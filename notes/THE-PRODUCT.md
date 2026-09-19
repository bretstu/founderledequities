# The product: what the site is, and who would pay for it

*Written 2026-09-18, after a day of reconciling the site's numbers against
two outside sources and the companies' own proxies. Keep beside
DISTRIBUTION.md; that one is how to reach people, this one is what they are
reached with.*

## What the site is, in one line

Every founder's stake, from the filings, by one stated rule, with the
reasons shown.

## The value, precisely

Not "more accurate" (nobody can check that from outside) but **a stated
definition applied the same way to every company, with the record of how**:

- one rule for Musk and for a $1B founder nobody covers;
- a grade per number that says when the rules could not settle it, and why;
- the footnote on the page when a line is left out of the count;
- the history: the number over time, not a snapshot;
- the tape's classification: planned, discretionary, vest, gift -- whether
  a move was a decision;
- within minutes of the filing.

Anyone can open the filing the site links to and see why the number is what
it is. That is the product. Transparent consistency is the mechanism; a
number you can check is what is sold.

## What the alternatives are, as found

- **S&P Global Market Intelligence** supplies Simply Wall St (their support
  page says all their data is S&P's; the ownership package is built from
  Form 4 and 13D). S&P's own listing describes the dataset as point-in-time
  by filing date and holding date, from regulatory filings and news
  vendors, updated daily; the data dictionary is behind a client login. No
  public definition of "shares owned".
- **What that produces in practice:** Hims (Dudum) on Simply Wall St matched
  the newest Form 4 total to the share (16,610,815); Coinbase (Armstrong)
  matched a proxy-with-options figure (~32.5M against 25.6M held). Same
  vendor, two upstream paths, no definition on the page. Simply Wall St is
  therefore a *lead*, not a definition: each mismatch must be reconciled on
  its own.
- **Fiscal.ai** does not publish a source; its numbers have behaved like the
  proxy's beneficial ownership (shares plus options exercisable within 60
  days) rolled forward with Form 4 deltas. Consistently high by the options
  figure for founders with large option books.
- **The proxy (DEF 14A)** is the one source that has explained every
  mismatch so far, by hand: Coinbase's footnote 4 gave our number to the
  share (526 + 22,681,225 + 2,958,393 = 25,640,144) plus 8,167,446 options,
  and put Armstrong's completed gifts to independent-trustee trusts on a
  separate row -- the company applying the same rule the site adopted.
- **Free sites** (OpenInsider, SecForm4, the Quiver / Unusual Whales feeds)
  show transactions, not positions, and monetise by volume.
- **Nobody** reconstructs the position over time, states a definition,
  grades the number, or shows the footnote. That is why it is a gap: the
  vendor will not judge, the ad site will not bother, the fund will not
  share.

## Who would pay

1. **Retail (the Pro plan).** Real, small: hundreds, not thousands. The
   public proof, not the business.
2. **Journalists and researchers.** Will not pay; give credibility. Make the
   method page easy to cite.
3. **Systematic investors and founder-led index / ETF providers.** The
   dataset: a point-in-time, documented, graded series. $20k-$100k a year
   per licence is the normal range for a niche alternative dataset. They
   need: a point-in-time export (the history is most of it), a method paper
   (the About page, longer, with the grade and the model's role stated
   plainly), evidence the signal means something, a marketplace listing
   (Neudata, Eagle Alpha, BattleFin).
4. **The display sites one tier below S&P** (Simply Wall St, Fiscal.ai and
   their kind). They show a number they cannot explain, from a vendor that
   charges for breadth they do not use, and their users notice when two
   sites disagree by 36%. A feed of "shares held by the chief executive,
   economic definition stated, graded, footnoted, within minutes of the
   filing" is a product they do not have and could describe to their users.
   S&P itself would build before buying; the tier below would not.

One dataset, two doors (3 and 4). Both need the method page first and a few
months of the footnote reader running clean.

## What a buyer will ask about the model

Index providers need reproducibility: same inputs and rules, same
constituents. The answer is structural, and it must be in the method paper:

- the model never changes a number; it proposes rows for the register
  (universe/exclusions.csv), a plain versioned file, and the number is
  deterministic given the filings and the register;
- every model reading is verified verbatim against the filing's text before
  it is recorded, and carries its prompt version and date;
- the golden set re-reads every ruled line after any prompt change;
- the founder badge rests on a quoted span from the proxy, checked verbatim.

Offer two columns: beneficial ownership as reported (no model anywhere in
its lineage) and economic ownership (the register applied). A buyer chooses
what they can defend.

## The definition the site keeps (settled 2026-09-19, rule B: a name or a statement, never a phrase)

**What counts as the person's.** Every share the person's own Form 4 reports,
in every class, counted one for one: held directly, or through an entity they
own or control (a holding company, an LLC, a family partnership, whatever its
purpose), a trust they or their spouse can direct or serve as trustee of, a
spouse's holdings whatever the disclaimer says, and a child's holdings still
in their hands (a custodial account, a trust with no trustee named, a trust
with any disclaimer but no one else named). Voting shares paired with
partnership units are the units. Options and unvested awards are not shares
and are not counted.

**What doesn't.** A line the filing itself shows is not theirs, by naming
who holds it or stating the person has no interest:
- shares held by a charitable foundation the person serves as trustee,
  officer, member or director, where nothing says the family benefits;
- a trust the person administers for another family;
- a line where the footnote states the person has no pecuniary or financial
  interest, or that the beneficiaries are not family;
- a trust for the person's children or descendants where the filing names an
  independent trustee (a trust company, a third party, their counsel),
  including the remainder of a GRAT held that way: a gift completed, even if
  the person may replace the trustee.

The wording of a disclaimer never decides: the hedge ("except to the extent
of pecuniary interest") and the unhedged form ("not an admission") change
nothing on their own. A trust with a trustee named but no beneficiary
stated, a trust "under" a GRAT with no trustee named, and a trust for
"immediate family" are not shown to be gifts and stay counted.

**Where it's unsure.** A vehicle the filing describes as a fraction (a
partnership interest, a membership) is counted whole and marked until the
fraction is known. Each exclusion appears on the company page with the
footnote's own words and a link to the filing.

**Why a name and not a phrase.** The reader makes rule calls, not judgement
calls: it finds a foundation, a trustee outside the family, a statement of
no interest, a fraction, and quotes it. The one criterion the issuer itself
applies (Coinbase's proxy puts Armstrong's independent-trustee trusts on a
row of their own) is the named trustee. No outside source measures economic
ownership; the vendors carry beneficial ownership as filed, which the
dataset's other column matches to the share.
