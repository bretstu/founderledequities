# The letter: how an issue is made (2026-09-20)

One file, written once, that becomes the email, the page and the Substack post.

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

    ## Two more that mattered
    ## The week's numbers

    | Kind | Company | CEO | Amount | Stake |
    |---|---|---|---|---|
    | Bought | EQPT | Jabbok Schlacks | $445K | 13.11% |

    ---members---            (later: everything below is for members)

What renders: `#` title, `##` subheads, paragraphs, **bold**, *italic*,
[links](url), tables, one image per line (`![alt](url)`; the company's card
is at /og/TICKER.png). `title` is the email subject and the page title;
`featured` links the issue to the company page and picks the card for the
link preview.

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

## Where it appears

- `/letter/` — the index: date, title, the week; the signup box on top.
- `/letter/<date>/` — the issue; `/tape/<date>/` redirects there.
- The nav: Activity · Letter · Companies · Alerts · About · Join.
- The sitemap carries the index and every issue.

## The paid part, when it starts

A `---members---` line in the file. The page shows everything above it to
everyone and the rest to a signed-in member (the page asks /api/me); the free
email stops at the marker; the member email carries the whole issue.
