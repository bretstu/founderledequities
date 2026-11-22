# Working in this repository

Read README.md first; it has the layout and the three build gotchas
(`index.html` is the source of `site.css` and of the shared script).

## Check a change

```bash
python -m pytest -q        # about ten seconds; must pass before a commit
node _harness.js           # render paths; needs panel.csv, history.csv, events.csv (not in git)
```

The data files are generated on the owner's machine and are not in git, so
the full build (`ops/deploy.sh`, `ops/preview.sh`) cannot run in a fresh
clone. To check a front-end change without them, load the live pages in a
browser with the repository's CSS and scripts swapped in, at 390px and
1440px, and compare screenshots before and after.

## Rules the project keeps

- No prose parsing and no model calls for anything that must be right for
  every company. The two model readers (founder sentences, Form 4 footnotes)
  are narrow and verified verbatim against the filing.
- A change to the walk's arithmetic (`fle/ledger.py`, `fle/ownership.py`,
  `fle/history.py`) starts with a read-only probe on the affected companies
  and ships with its before/after diff. Do not change those rules as part of
  a cleanup.
- Curated facts live in `universe/exclusions.csv`, each with a quote and a
  source.
- "Never" is not claimed; "since 2016" is. The record starts 2016-01-01.
- A colour or a font size that has no token in `index.html`'s `:root` does
  not exist on the site (`tests/test_design_tokens.py` enforces it, and that
  every class the stylesheet defines is used somewhere).
- Every page must fit a 390px screen without scrolling sideways; a wide
  table scrolls inside its own panel.

## Style

The owner wants plain language, honest odds, and "I don't know, here is the
command to find out" over a guess. Comments in this code explain why a rule
exists and usually carry the date it was decided; keep that habit, and
delete a comment when the thing it describes goes.
