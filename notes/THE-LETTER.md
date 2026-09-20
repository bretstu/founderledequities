# The letter (settled 2026-09-20, after issue 1)

Weekly. One file, written once, that becomes the email, the page and the
Substack post. No day of the week is promised anywhere; the archive's dates
show when issues arrive.

## Who writes what

- **The pipeline** finds and counts: the shortlist of candidates, the
  largest buy and sale, the top five stake moves, the person's history, the
  card. Data, never prose.
- **The session** (from the kit) writes a research BRIEF for the featured
  company: facts with their sources. Not a draft.
- **I write the letter**, in my own words, from the brief and the skeleton.
  The voice is the moat of a letter the way the reconstruction is the moat
  of the site. Substack's detector read issue 1 as 85% AI; from issue 2 the
  prose is mine.

## The six sections

1. **Title.** The feature's claim, in words the filing supports.
   "Medpace's founder sold $15.4M, not on a plan."

2. **This week.** Two sentences: the counts (how many founders bought on
   the open market, how many sold at their own discretion, how many sold on
   plans), and the largest move of any founder's stake, its kind named.
   Plus one sentence when a founder made his first open-market buy on
   record. The week for someone who reads nothing else; everything in it
   has a section below.

3. **The feature**, headed by its claim. One decision, about 300 words, in
   my words: what the company does; what the person has done before with
   the stake; what the filings say that the Form 4 doesn't (plans on file,
   buybacks, the proxy); what this move changed. The top candidate by the
   pipeline's score, at my discretion (the one override: a candidate whose
   kit has no story). The company's card as the image, captioned with the
   window it shows. From issue 2: one line on what the last issue's company
   did since ("Medpace since last week: +2.1%"), printed whatever it is.

4. **Largest open-market buy and discretionary sale**, BY DOLLARS, other
   than the feature. Two labelled paragraphs, *The largest buy* and *The
   largest sale*, each three sentences: what they did and how much of their
   holding it was; one fact from their history (buys and sales in the last
   two years, plan or not); what they own. A week with no buy has one
   paragraph and says so.

5. **Top stake moves.** The five largest changes to any founder's stake
   this week, BY SHARE OF THE HOLDING, whatever the kind, as a five-row
   table: Kind · Company · CEO · Amount · Of holding · Stake. A plan sale,
   a grant or a gift sits beside a discretionary sale, labelled for what it
   was. Under it, one bullet only when a big non-decision missed the five
   (a gift or grant too small a share of the holding: Huang's $93M). Then
   the link: every filing of the week, on the site.

6. **One ranking**, headed by what it ranks. Three bullets from the site's
   data and the link to the screen; a different question each week (who
   added most to their stake this year; who has never sold; the largest
   stakes once the doubtful ones are fixed; the biggest cuts this quarter).

Two measures, each section naming which it uses: dollars in 4, share of
the holding in 5. The score proposes the feature and is never mentioned.
Sections 1, 2, 3, 5, 6 always appear; 4 shrinks on a thin week rather than
being padded. No table longer than five rows; everything else is a link.
No closing sales line; the footer says only where the numbers come from.

## The voice (what issue 1 taught)

- One point per piece: the sentence you'd say across a table. If you can't
  say it, you aren't ready to write.
- Answer the reader's next question in order: what happened; who is this
  and what's the company; what did he do before; how do you know; so what.
- A fact, then what it means, in that order.
- Short sentences, concrete nouns, no word you wouldn't say out loud. No
  editorial rules in the prose. No flourishes ("a better story than the
  number", "not decisions, but not nothing", "worth watching").
- Only what the record shows; an inference stays if it is the plain
  meaning of a document and is attributed.
- Tickers on first mention. Percentages to two decimals. A dash under
  Amount means no money changed hands; a grant raises the holding because
  the company issued the shares.
- Numbers from the site only, from the pipeline's tables, never from a
  screenshot (a screenshot gave Cimpress 0.51% instead of 1.4%).
- Read it aloud before sending; cut what you stumble on.

## Choosing the feature

`ops/moves.py week` writes drafts/moves-week.md with the ranked candidates
(decisions only: log10(dollars) + 2 × share of holding, +1 for a buy, +0.5
for a stake over 5%) and the ≥1% movers. Open the top candidate's kit
first; pass on it only if the filings are dull. In issue 1 a glance at the
dollars picked EquipmentShare (7.3) over Alexandria (8.1) and SoundHound
over Cimpress; the score was right both times.

## The Sunday

1. `ops/moves.py week` → the shortlists.
2. `ops/letter_kit.py <TICKER>` → upload `drafts/kit-<TICKER>-<date>.zip`
   to a new Claude session with `00-PROMPT.md` as the first message; it
   returns the brief. Drop the latest call transcript into
   `transcript.txt` first if you have one.
3. `ops/letter.py draft` writes the skeleton with every number filled.
   Write the feature and the two paragraphs into it. Save as
   `weekly/letter-<date>.md`.
4. `ops/send-tape.sh <date> --test` → read it in your inbox and open
   `weekly/letter-<date>.html`.
5. `ops/send-tape.sh <date> --send --confirm` (mails the list, stamps the
   file `sent:`); `ops/deploy.sh` (publishes /letter/<date>/ and the
   index); `git add weekly/letter-<date>.md && git commit`.
6. Substack: new post; paste the text from the site's page; tables and the
   chart as images (upload `public/og/<TICKER>.png`, caption
   "<Company> on Founder Led Equities →" linked to the company page); H3
   headings; one subscribe button at the end, in your words; tags
   `founder moves` and the ticker; send via email. Fill the "How I make
   this" statement honestly: numbers computed by my pipeline from filings,
   the reading mine, an assistant for research.
7. X: the week's two sentences as a post with the page's link, pinned.

## Where it appears

- `/letter/` — a quiet signup line, then the issues as a list (date · title
  · the week · the featured ticker). Only files stamped `sent:` publish.
- `/letter/<date>/` — the issue in one 720px reading column.
- The nav: Activity · Companies · Letter · Alerts · About · Join.

## The file

`weekly/letter-YYYY-MM-DD.md`, committed. Front matter (`date`, `title`,
`week`, `featured`; `sent:` is stamped by the send), then Markdown: `#`
title, `##` subheads, paragraphs, **bold**, *italic*, [links](url), `- `
bullets, tables, one image per line, and a `---members---` marker for the
paid part when it starts.

## For issue 2 (the pipeline's side)

- The since-2016 stake chart for the featured company, beside the card.
- Table images for Substack (`ops/letter.py substack <date>`).
- The person's history line written into the skeleton's two paragraphs.
- "Since last issue" for the featured stock, from the price store.
