#!/usr/bin/env python3
"""THE PARTNERSHIP STAGE (2026-09-15): the register, generated weekly from
the filings, with the delta printed, written and mailed.

    python3 ops/partnerships_stage.py            # every company on the panel -> universe/partnerships-auto.csv
    python3 ops/partnerships_stage.py --dry-run  # compute and print the delta, write nothing
    python3 ops/partnerships_stage.py OWL SYM    # named tickers only (a check; the file is not rewritten)

THE RULE IS FIXED AND RUNS; A PERSON READS ONLY THE DELTA. For every chief
executive on the panel the four structured facts of ops/upc_census.py are
computed from his own filings (never footnotes):
  1. unit rows in Table II (a partnership or LLC unit title, converting into
     the issuer's stock, with no price and no expiry)
  2. how many classes the cover page tags
  3. his newest Table I holding of a class other than the first
  4. whether any unit title's count equals that holding
A company with no unit rows is not in the register. keep = 1 with 2 (two or
more), 3 and 4: the site's ordinary rule is the founder's as-converted
stake, provably (ops/partnerships.py explains). Anything else with unit
rows = exclude, the safe direction, including the facts that conflict,
which go on the review list. A hand row in universe/partnerships.csv
overrides the generated one for that ticker and is never overwritten
(Carvana: the census misreads the newest partial unit line; a person read
the filings and cited them).

THE DELTA IS THE OUTPUT A PERSON READS: rows added (a new structure, or a
keep that lost its paired class), rows removed (units gone to zero, the
structure collapsed, the company returns), actions changed, and generated
rows a hand row overrides differently. Printed as the stage's log, written
to drafts/partnerships-<date>.md, and mailed to LIVE_TO when not empty.
The panel diff the next morning shows the same companies added or dropped
from the universe, by construction: two views of one event.
"""
import csv
import datetime as dt
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
sys.path.insert(0, HERE)
from fle.partnerships import COLUMNS, read_hand, read_generated   # noqa: E402
import upc_census as census                                        # noqa: E402

HAND = os.path.join(ROOT, "universe", "partnerships.csv")
AUTO = os.path.join(ROOT, "universe", "partnerships-auto.csv")


def members(root):
    """EVERY COMPANY IN THE UNIVERSE, EXCLUDED ONES INCLUDED (2026-09-16). The
    first version read the panel, which no longer holds the companies the
    register had excluded, called their absence "no unit rows now", removed
    their rows, and put them back on the site the next morning. The universe
    file has ticker, CIK, company and the chief executive's owner CIK; the
    panel adds the name and the fewer-lines caution for the companies it has."""
    import glob
    files = sorted(glob.glob(os.path.join(root, "universe", "universe-*.csv")))
    if not files:
        return census.read(os.path.join(root, "panel.csv"))
    panel = {r["ticker"]: r for r in census.read(os.path.join(root, "panel.csv"))}
    # THE OWNER CIK IS REMEMBERED: the universe file has none, the panel has
    # it only for companies still on the panel, so the register keeps it for
    # every company it has ever judged (and a hand row may carry it too)
    known = {}
    for src in (read_generated(os.path.join(root, "universe", "partnerships-auto.csv")), read_hand(os.path.join(root, "universe", "partnerships.csv"))):
        for tk, row in src.items():
            if row.get("owner_cik"):
                known[tk] = row
    out = []
    for r in census.read(files[-1]):
        tk = (r.get("ticker") or "").upper()
        if not tk or not r.get("cik"):
            continue
        p = panel.get(tk, {}); k = known.get(tk, {})
        out.append({"ticker": tk, "cik": r["cik"], "owner_cik": r.get("owner_cik") or p.get("owner_cik") or k.get("owner_cik") or "",
                    "company": r.get("company") or p.get("company") or k.get("company") or "", "ceo": r.get("ceo") or p.get("ceo") or k.get("ceo") or "",
                    "cautions": p.get("cautions") or ""})
    return out


def generate(client, panel, covers, only=None, unjudged=None):
    """-> {TICKER: row} for every company with unit rows. A company that
    cannot be judged (no owner CIK, or a read that failed) is added to
    `unjudged`; the caller carries its previous row rather than removing it:
    REMOVAL NEEDS POSITIVE EVIDENCE, the filings read and no unit rows."""
    out = {}
    for r in panel:
        tk = r["ticker"]
        if only and tk not in only:
            continue
        if not r.get("owner_cik"):
            if unjudged is not None:
                unjudged.add(tk)
            continue
        letters = {m.group(1) for m in census.re.finditer(r"Class([A-Z])", covers.get(tk, ""))}
        try:
            c = census.facts(client, r, letters)
        except Exception as exc:  # noqa: BLE001
            print(f"  {tk}: could not read: {exc}", file=sys.stderr)
            if unjudged is not None:
                unjudged.add(tk)
            continue
        if not c:
            continue
        big_title, (big, _w, big_acc) = max(c["units"].items(), key=lambda kv: kv[1][0])
        paired_titles = ", ".join(sorted({k[0] for k in c["paired"]}))
        partial = "names fewer lines" in (r.get("cautions") or "")
        if c["suggest"] == "keep" and partial:
            action, reason = "exclude", (f"Units equal the paired class ({c['match'][0]} = {c['paired_total']:,.0f} {paired_titles}), but the newest "
                                         f"filing names fewer lines than the one before it (the ledger's caution): the match may stand on a partial "
                                         f"statement; excluded until the next complete filing. REVIEW.")
        elif c["suggest"] == "keep":
            action, reason = "keep", (f"Units equal the paired class on the cover ({c['match'][0]} = {c['paired_total']:,.0f} {paired_titles}) in the same filing; "
                                      f"the ordinary rule is the as-converted stake.")
        elif c["suggest"] == "exclude":
            action, reason = "exclude", (f"The chief executive holds {big:,.0f} {big_title} the site does not count"
                                         + (f"; a paired holding of {c['paired_total']:,.0f} does not match" if c["paired_total"] else "; no paired class in Table I")
                                         + ".")
        else:
            action, reason = "exclude", (f"The facts conflict (units {big:,.0f} {big_title}; paired {c['paired_total']:,.0f} {paired_titles}; "
                                         f"cover classes {c['cover']}): excluded until a person reads the filing. REVIEW.")
        out[tk] = {"ticker": tk, "action": action, "structure": "partnership", "company": r.get("company") or "", "ceo": r.get("ceo") or "",
                   "cik": r.get("cik") or "", "owner_cik": r.get("owner_cik") or "", "cover_classes": str(c["cover"]), "paired_class": paired_titles,
                   "units_reported": "; ".join(f"{t} {a:,.0f}" for t, (a, w, acc) in list(c["units"].items())[:3]),
                   "reason": reason, "source": f"https://www.sec.gov/Archives/edgar/data/{int(r['cik'])}/{big_acc.replace('-', '')}/",
                   "as_of": dt.date.today().isoformat(), "by": "census"}
    return out


def delta(old, new, hand):
    lines = []
    for tk in sorted(set(old) | set(new)):
        o, n = old.get(tk), new.get(tk)
        if o and not n:
            lines.append(f"- {tk}: removed from the register ({o['action']}): no unit rows now; the structure may have collapsed and the company returns to the site")
        elif n and not o:
            lines.append(f"- {tk}: added, {n['action']}: {n['reason']}")
        elif o["action"] != n["action"]:
            lines.append(f"- {tk}: {o['action']} -> {n['action']}: {n['reason']}")
        elif "REVIEW" in n["reason"] and "REVIEW" not in (o.get("reason") or ""):
            lines.append(f"- {tk}: now needs a reading: {n['reason']}")
    for tk, h in sorted(hand.items()):
        n = new.get(tk)
        if n and n["action"] != h["action"]:
            lines.append(f"- {tk}: the hand row says {h['action']}, the census says {n['action']} ({n['reason']}); the hand row stands")
        if not n and h["action"] == "exclude" and tk not in old:
            pass   # a hand exclusion the census cannot see (MoonLake's AG shares are not unit-titled): fine
    return lines


def main(argv):
    dry = "--dry-run" in argv
    only = {a.upper() for a in argv if not a.startswith("--")}
    panel = members(ROOT)
    covers = {}
    for h in census.read(os.path.join(ROOT, "history.csv")):
        covers[h["ticker"]] = h.get("classes") or ""
    client = census.EdgarClient()
    old = read_generated(AUTO)
    hand = read_hand(HAND)
    unjudged = set()
    new = generate(client, panel, covers, only or None, unjudged)
    carried = {tk: row for tk, row in old.items() if tk in unjudged}
    new.update(carried)
    if only:
        for tk, r in sorted(new.items()):
            print(f"  {tk:6} {r['action']:8} {r['reason'][:150]}")
        return 0
    lines = delta(old, new, hand)
    kept = sum(1 for r in new.values() if r["action"] == "keep")
    review = sum(1 for r in new.values() if "REVIEW" in r["reason"])
    head = (f"partnerships: {len(new)} companies with unit rows; {kept} kept, {len(new) - kept} excluded "
            f"({review} awaiting a reading); {len(hand)} hand rows on top; {len(carried)} carried unjudged; {len(lines)} change(s) since last run")
    for tk in sorted(carried):
        lines.append(f"- {tk}: carried unchanged: could not be judged this week (no owner CIK on file, or the filings could not be read)")
    print("  " + head)
    for ln in lines:
        print("   " + ln)
    if dry:
        return 0
    with open(AUTO, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for tk in sorted(new):
            w.writerow(new[tk])
    drafts = os.path.join(ROOT, "drafts")
    os.makedirs(drafts, exist_ok=True)
    day = dt.date.today().isoformat()
    text = f"# Partnership register, {day}\n\n{head}\n\n" + ("\n".join(lines) if lines else "(no change)") + "\n"
    with open(os.path.join(drafts, f"partnerships-{day}.md"), "w", encoding="utf-8") as fh:
        fh.write(text)
    if lines:
        try:
            from live import send_mail
            to = os.environ.get("LIVE_TO", "")
            if to and send_mail(to, f"Partnership register: {len(lines)} change(s)", text):
                print(f"  mailed the delta to {to}")
        except Exception as exc:  # noqa: BLE001
            print(f"  (delta not mailed: {exc})")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
