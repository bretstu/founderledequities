# The letter: how an issue is made (settled 2026-09-20, after issue 1)

One file, written once, that becomes the email, the page and the Substack
post. Weekly; no day of the week is promised anywhere (the archive's dates
show when issues arrive).

## The template

1. **Title**: the feature's claim, in words the filing supports ("Medpace's
   founder sold $15.4M, not on a plan"; not "at a price he chose" when the
   limit-order fact is from an older filing).
2. **The week in a line**: bought / at their own discretion / on plans.
3. **The feature**, ~300 words: the top candidate by the pipeline's score,
   at your discretion (the one override: a candidate whose kit has no story).
   What the company does and how it makes money; what the person has done
   before with the stake; what the filings say (plans on file, buybacks, the
   proxy row); what this move changed. The company's card as the image, with
   a caption saying what window it shows.
4. **Two more decisions**: the largest buy and the largest discretionary
   sale not featured. Three sentences each: what they did and what it was
   as a share of the holding; one fact from their history (from the events
   file: how many buys/sales in two years, on a plan or not); what they own.
   Not two more deep dives.
5. **Moved the stake**: one line saying what the table holds, then the
   pipeline's table of every filing that moved a holding by ≥1%, any kind,
   the kind named in the first column, sorted by "Of holding". Then two
   bullets, person–action–company (ticker): the largest non-decision by
   dollars, and the largest planned sale "by dollars" (say so, or a reader
   asks why it isn't in the table).
6. **The week's decisions**: one line saying it is every buy and
   discretionary sale by a founder-CEO, ranked by what it did to the stake,
   and that plan sales, grants, vests and gifts are not here; then the table.
7. **One ranking**: three bullets from the site's data (e.g. founders who
   added the most to their stakes on the open market this year), one line
   for the largest by dollars, the link to the screen. Not the largest-stake
   list while any number in it is in doubt (Venture Global is the pair's).

No closing sales line. The email footer says only where the numbers come
from and where to unsubscribe.

## The voice (what we cut in issue 1)

- No editorial rules in the prose ("a plan sale that takes 7% is worth
  knowing about"). The section's one-line intro says what the table holds
  and nothing about why.
- No flourishes: "it's a better story than the number", "not decisions, but
  not nothing", "a pattern worth watching", "put their own money in".
- Only what the record shows. A characterisation ("a bad year for real
  estate") is cut unless a filing says it. Inferences stay if they are the
  plain meaning of a document (a limit order: he sets a price, the market
  decides the day) and are attributed.
- Every company gets its ticker on first mention, in prose and tables.
- Percentages to two decimals (0.34%, not 0.343%); "0.84% of his holding",
  not "nearly a percent".
- A dash under Amount means no money changed hands (a grant, a vest, a
  gift); a grant raises the holding because the company issued the shares.
- Numbers from the site only. The pipeline's tables, not screenshots (a
  screenshot gave Cimpress 0.51% instead of 1.4%, and changed the pick).

## Choosing the feature

`ops/moves.py week` writes drafts/moves-week.md with two shortlists at the
end: **Candidates for the feature** (decisions only, scored
log10(dollars) + 2 × share of holding, +1 for a buy, +0.5 for a stake over
5%) and **Moved the stake** (every ≥1% filing, any kind, plus the three
largest plan sales). Open the top candidate's kit first; pass on it only if
the filings are dull. The two shorter moves are the next buy and the next
sale on the list. The score decides, not a glance at the dollars: in issue
1 the glance picked EquipmentShare (7.3) over Alexandria (8.1), and
SoundHound over Cimpress, and both were wrong.

## The Saturday (or Sunday)

1. `ops/moves.py week` → read the two shortlists.
2. `ops/letter_kit.py <TICKER>` for the top candidate → upload
   `drafts/kit-<TICKER>-<date>.zip` to a new Claude session with
   `00-PROMPT.md` as the first message; iterate. Drop the latest earnings
   call transcript into `transcript.txt` first if you have one (the Motley
   Fool transcripts are free to read).
3. For the two shorter moves, the person's history:
   `python3 - <<'EOF'` over events.csv for the two tickers (two years of
   P/S rows, plan or not) — the kit will carry this from issue 2.
4. `ops/letter.py draft` writes the skeleton with the tables filled; paste
   the session's prose into it; save as `weekly/letter-<date>.md`.
5. `ops/send-tape.sh <date> --test` → read it in your inbox (and
   `weekly/letter-<date>.html` in a browser).
6. `ops/send-tape.sh <date> --send --confirm` (mails the list and stamps
   the file `sent:`), then `ops/deploy.sh` (publishes /letter/<date>/ and
   the index), then `git add weekly/letter-<date>.md && git commit`.
7. Substack: new post; paste the text from the site's page; the tables and
   the chart go in as images (Substack has no table support and does not
   fetch remote images): upload `public/og/<TICKER>.png` for the chart with
   the caption "<Company> on Founder Led Equities →" linked to the company
   page; tables as PNGs (the pipeline will render them from issue 2; a
   screenshot until then). Headings as H3. One subscribe button, at the
   end, with your own words in it. Tags: `founder moves` and the featured
   ticker. Social preview: the card (Substack picks the first image).
   Send via email and the app.
8. X: the week's numbers as a short thread with the page's link, pinned.

## What appears where

- `/letter/` — the index: a quiet signup line, then the issues as a list
  with rules (date · title · the week · the featured ticker). Only files
  stamped `sent:` are published; the pipeline's unsent drafts in `weekly/`
  never become pages.
- `/letter/<date>/` — the issue in one 720px reading column: text, image
  and tables the same width. `/tape/<date>/` redirects there.
- The nav: Activity · Companies · Letter · Alerts · About · Join.
- The sitemap carries the index and every sent issue.

## The file

`weekly/letter-YYYY-MM-DD.md`, committed. Front matter, then Markdown:

    ---
    date: 2026-09-19
    title: Medpace's founder sold $15.4M, not on a plan
    week: 14 Sep to 18 Sep
    featured: MEDP
    ---

What renders: `#` title, `##` subheads, paragraphs, **bold**, *italic*,
[links](url), `- ` bullet lists, tables, one image per line
(`![alt](url)`; the company's card is at /og/TICKER.png), and a
`---members---` marker for the paid part when it starts. `title` is the
email subject and the page title; `featured` links the issue to the company
page and picks the card for the link preview.

## For issue 2 (the pipeline's side)

- The since-2016 stake chart for the featured company, drawn beside the
  card, so the feature's image shows the whole story rather than a year.
- The person's history (two years of buys and sales, plan or not) written
  into the kit's `02-the-move.md` and into the skeleton's "Two more
  decisions" lines.
- Table images for Substack (`ops/letter.py substack <date>` → a folder
  with the text, the chart and each table as a PNG).
- The Venture Global shape (a partner's entity is partial) in the reader,
  and the register's `fraction` column.
