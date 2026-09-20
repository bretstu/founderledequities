# The letter: how an issue is made (2026-09-20)

One file, written once, that becomes the email, the page and the Substack post.

## The template (settled 2026-09-20)

1. **Title**: the feature's claim ("Medpace's founder sold $15.4M, at a price he chose").
2. **The week in a line**: bought / discretionary / on plans.
3. **The feature**, ~300 words: the top candidate by the pipeline's score, at
   your discretion (the one override: a candidate whose kit has no story).
4. **Two more decisions**: the largest buy and the largest discretionary sale
   not featured, one paragraph each, person–action–company (ticker).
5. **Moved the stake**: the pipeline's table of every filing that moved a
   holding by ≥1%, any kind, the kind named; then one bullet for the largest
   non-decision by dollars and one for the largest planned sale.
6. **The week's decisions**: the pipeline's table of every buy and
   discretionary sale, with a line saying that is what it holds.
7. **One ranking**: three names and the link to a screen.

Editorial rules stay out of the prose; every company gets its ticker on
first mention; numbers come from the site only.

`ops/letter.py draft` writes this skeleton with the tables filled and the
writing in brackets; `ops/moves.py week` prints the ranked candidates.

## The file

`weekly/letter-YYYY-MM-DD.md`, committed. Front matter, then Markdown:

    ---
    date: 2026-09-19
    title: Medpace's founder sold $15.4M, at a price he chose
    week: 12 Sep to 19 Sep
    featured: MEDP
    ---

    # Medpace's founder sold $15.4M, at a price he chose

    *Founder Moves · the week of 12–19 September 2026*

    Two founders put their own money in this week ...

    ## Troendle sells $15.4M of Medpace, at a price he chose

    ...

    ![Troendle's stake since 2016](https://founderledequities.com/og/MEDP.png)

    ## Two more decisions
    ## Moved the stake          (a table: every filing that moved a holding by ≥1%, any kind, the kind in the first column; then one sentence each for the largest non-decision by dollars and the largest planned sale)
    ## The week's decisions   (buys and discretionary sales only; a line says so, and links the full list)

    | Kind | Company | CEO | Amount | Stake |
    |---|---|---|---|---|
    | Bought | EQPT | Jabbok Schlacks | $445K | 13.11% |

    ---members---            (later: everything below is for members)

What renders: `#` title, `##` subheads, paragraphs, **bold**, *italic*,
[links](url), tables, one image per line (`![alt](url)`; the company's card
is at /og/TICKER.png). `title` is the email subject and the page title;
`featured` links the issue to the company page and picks the card for the
link preview.

## Choosing the feature

`ops/moves.py week` writes drafts/moves-week.md with two shortlists at the
end: **Candidates for the feature** (decisions only, ranked by
log10(dollars) + 2 × share of holding, a premium for a buy and for a stake
over 5%) and **Moved the stake** (every filing that moved a holding by a
percent or more, whatever its kind, plus the three largest planned sales;
the letter's "Moved the stake" table is every ≥1% line with its kind named,
followed by a sentence each for the largest non-decision by dollars and the
largest planned sale, which the threshold can miss).
The feature is the top candidate unless its kit has no story; the two
shorter moves are the next two decisions, one a buy if there was one; the
Moved-the-stake section is the second list, each line naming its kind (a
gift, a grant, a plan sale), so no reader mistakes a plan for a decision.

## The Saturday

1. `ops/letter_kit.py MEDP` → upload `drafts/kit-MEDP-<date>.zip` to a new
   Claude session with `00-PROMPT.md` as the first message; iterate.
2. "Give me the final issue as Markdown in the template" → save it as
   `weekly/letter-<date>.md`.
3. `ops/send-tape.sh <date> --test` (to yourself) then `--send --confirm`
   (the list); `ops/deploy.sh` publishes `/letter/<date>/` and the index.
4. Substack: open `/letter/<date>/` on the site, select the issue, copy,
   paste into Substack's editor (rich text: headings, table, image, links
   come through), set the title, publish.
5. `git add weekly/letter-<date>.md && git commit` — the archive is
   versioned, and the next kit reads it for the voice.

An issue is an issue once it is sent: `--send --confirm` stamps
`sent: <date>` into the file's front matter, and only stamped files are
published, listed in the sitemap, or used for the voice. The pipeline's
Saturday drafts sit in the same folder unstamped and never become pages.

## Where it appears

- `/letter/` — the index: date, title, the week; the signup box on top.
- `/letter/<date>/` — the issue; `/tape/<date>/` redirects there.
- The nav: Activity · Letter · Companies · Alerts · About · Join.
- The sitemap carries the index and every issue.

## The paid part, when it starts

A `---members---` line in the file. The page shows everything above it to
everyone and the rest to a signed-in member (the page asks /api/me); the free
email stops at the marker; the member email carries the whole issue.
