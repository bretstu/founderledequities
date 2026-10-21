#!/usr/bin/env python3
"""WHO CAME. The site's own count of visitors (every page carries the same
beacon; crawlers and unfurlers never fire it), read from the D1 table.

    ops/hits.sh                        # the last 7 days
    ops/hits.sh today
    ops/hits.sh yesterday
    ops/hits.sh 30                     # the last 30 days
    ops/hits.sh 2026-10-10             # that day (Eastern), any day the table has
    ops/hits.sh 2026-10-06..2026-10-10 # those days inclusive
    ops/hits.sh visitors               # today: one row per visitor, then each reader's journey as a table
    ops/hits.sh visitors 2026-10-10    # the same for any window above (a day, a range, a count of days)

THE WINDOW IS READ ONCE (2026-10-20). The report used to ask D1 a dozen
questions per run, each joining the table to itself (a visitor's first
view, the source of that view, whether they were seen on an earlier day),
and a join without a matching index reads rows times rows: two 30-day
visitor reports read a 15,000-row table twenty million times and tripped
the daily cap, with the watch forms and the alert run behind the same cap.
Now two queries: the window's rows, and each visitor's first day on
record; everything below is counted here. However wide the window, the
table is read about once.

FOUR QUESTIONS, IN ORDER (2026-10-14): how many came, how they found the
site, what they looked at, what they did. Every view counts: nothing is
classified or hidden, a scraping night reads as what it was.

Days are Eastern (the table stores UTC timestamps). A private window is a
new visitor every time; the owner's usual browser is switched off with
?nohit=1 once in the address bar.
"""
import datetime as dt
import json
import os
import re
import subprocess
import sys
from collections import Counter, OrderedDict, defaultdict
from zoneinfo import ZoneInfo

EASTERN = ZoneInfo("America/New_York")
DB = os.environ.get("FLE_HITS_DB", "fle-hits")
ACTIONS = {"click", "open", "switch", "sort"}
# THE PATH WITHOUT THE CLICK ID (2026-10-16): an ad click lands with the
# network's own tag appended (X adds twclid=, Google gclid=, Meta fbclid=);
# the path is cut at the first click id, and the site's own ?src= tag,
# which comes first, is kept, so a campaign's landings group on one row.
CLICK_IDS = ("twclid", "gclid", "fbclid", "msclkid", "dclid", "ttclid", "yclid")
_CLICK = re.compile(r"[?&](?:" + "|".join(CLICK_IDS) + r")=")


def clean_path(path):
    m = _CLICK.search(path or "")
    return path[:m.start()] if m else (path or "")


def source_of(ref):
    """the host of the referrer, with the site's own pages (navigation) and
    an empty referrer both reading as direct"""
    if not ref or "founderledequities.com" in ref:
        return "direct"
    host = ref.split("://", 1)[-1].split("/", 1)[0]
    return host[4:] if host.startswith("www.") else host


def eastern(ts):
    """the Eastern wall clock of a stored UTC timestamp"""
    t = ts.replace("Z", "")
    try:
        d = dt.datetime.fromisoformat(t)
    except ValueError:
        d = dt.datetime.strptime(t[:19], "%Y-%m-%dT%H:%M:%S")
    if d.tzinfo is None:
        d = d.replace(tzinfo=dt.timezone.utc)
    return d.astimezone(EASTERN)


def window(arg):
    """(start, end, label, single) in Eastern dates"""
    today = dt.datetime.now(EASTERN).date()
    if arg == "today":
        return today, today, "today", True
    if arg == "yesterday":
        d = today - dt.timedelta(days=1)
        return d, d, "yesterday", True
    m = re.fullmatch(r"(\d{4}-\d{2}-\d{2})\.\.(\d{4}-\d{2}-\d{2})", arg)
    if m:
        a, b = dt.date.fromisoformat(m.group(1)), dt.date.fromisoformat(m.group(2))
        return a, b, f"{a} to {b}", False
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", arg):
        d = dt.date.fromisoformat(arg)
        return d, d, arg, True
    if arg.isdigit() and arg:
        n = int(arg)
        return today - dt.timedelta(days=n), today, f"last {n} days", False
    raise SystemExit("usage: ops/hits.sh [today|yesterday|N|YYYY-MM-DD|YYYY-MM-DD..YYYY-MM-DD]  or  ops/hits.sh visitors [window]")


def d1(sql, again=True):
    """one query, its rows; a wrangler error is printed and ends the run"""
    out = subprocess.run(["wrangler", "d1", "execute", DB, "--remote", "--json", "--command", sql],
                         capture_output=True, text=True)
    try:
        res = json.loads(out.stdout)
    except ValueError:
        raise SystemExit(f"  (query failed: {(out.stderr or out.stdout)[:300]})")
    if not isinstance(res, list):   # wrangler reports an error as an object, not a result list (2026-09-29)
        text = str(res.get("error") or res.get("errors") or res)
        # THE STALE LOGIN (2026-10-21): the first run after a while sends an
        # expired token, Cloudflare refuses it (code 10000), and wrangler
        # refreshes the token on the way out; the same query once more works
        if again and "10000" in text:
            return d1(sql, again=False)
        raise SystemExit("  (query failed: " + text[:300] + ")")
    return res[0]["results"]


def load(start, end):
    """the window's rows (bounded by the indexed UTC day, a day wide on each
    side, then cut to the Eastern window here) and each visitor's first day"""
    lo, hi = (start - dt.timedelta(days=1)).isoformat(), (end + dt.timedelta(days=1)).isoformat()
    rows = d1(f"SELECT ts, vid, kind, name, detail, path, ref, country FROM hits "
              f"WHERE day BETWEEN '{lo}' AND '{hi}' ORDER BY ts")
    for r in rows:
        r["at"] = eastern(r["ts"])
        r["eday"] = r["at"].date()
        r["path"] = clean_path(r.get("path") or "")
    rows = [r for r in rows if start <= r["eday"] <= end]
    firsts = {r["vid"]: r["day"] for r in d1("SELECT vid, MIN(day) AS day FROM hits WHERE kind='view' GROUP BY vid")}
    return rows, firsts


def table(cols, rows):
    """a table the way the report has always printed one: two spaces in,
    numbers right-aligned, a cell cut at 72"""
    if not rows:
        print("  (none)")
        return
    rows = [[c for c in r] for r in rows]
    num = [all(isinstance(r[i], (int, float)) for r in rows) for i in range(len(cols))]
    w = [min(72, max(len(cols[i]), *(len(str(r[i])) for r in rows))) for i in range(len(cols))]

    def cell(i, v):
        t = str(v)[:72]
        return t.rjust(w[i]) if num[i] else t.ljust(w[i])
    print("  " + "  ".join(cols[i].rjust(w[i]) if num[i] else cols[i].ljust(w[i]) for i in range(len(cols))))
    for r in rows:
        print("  " + "  ".join(cell(i, r[i]) for i in range(len(cols))))


def did_of(r):
    """what a row says a visitor DID: a control, or a filter on the companies page"""
    if r["kind"] in ACTIONS:
        return (r.get("name") or "") + ((" " + r["detail"]) if r.get("detail") else "")
    if r["kind"] == "view" and r["path"].startswith("/companies/?"):
        return "filter " + r["path"].split("?", 1)[1].replace("&", ", ")
    return ""


def digest(rows):
    """per visitor: views in order, actions in order, first view, country"""
    V = OrderedDict()
    for r in rows:
        v = V.setdefault(r["vid"], {"views": [], "acts": [], "country": r.get("country") or ""})
        if r["kind"] == "view":
            v["views"].append(r)
        did = did_of(r)
        if did:
            v["acts"].append((r, did))
    return OrderedDict((k, v) for k, v in V.items() if v["views"])


def clock(at, single):
    return at.strftime("%H:%M") if single else at.strftime("%Y-%m-%d %H:%M")


def visitors_report(V, label, single):
    print(f"== visitors ({label}), one row each: when they arrived, where from, the page they landed on, pages seen, actions taken ==")
    out = []
    for vid, v in V.items():
        f = v["views"][0]
        out.append([clock(f["at"], single), vid[:6], v["country"], source_of(f.get("ref")), f["path"], len(v["views"]), len(v["acts"])])
    table(["first", "who", "country", "came_from", "landed_on", "pages", "actions"], out)
    shown = 0
    for vid, v in V.items():
        if len(v["views"]) < 2 and not v["acts"]:
            continue
        shown += 1
        if shown > 40:
            break
        f = v["views"][0]
        print()
        print(f"== {vid[:6]}, {v['country']}, from {source_of(f.get('ref'))}: {len(v['views'])} pages, {len(v['acts'])} actions ==")
        journey = [(r["at"], r["path"], did_of(r) if r["path"].startswith("/companies/?") else "") for r in v["views"]]
        journey += [(r["at"], r["path"], did) for r, did in v["acts"] if r["kind"] in ACTIONS]
        journey.sort(key=lambda x: x[0])
        table(["at", "path", "action"], [[clock(a, single), p, d] for a, p, d in journey])


def summary(V, firsts, start, end, label, single):
    acted = {vid for vid, v in V.items() if v["acts"]}
    views = sum(len(v["views"]) for v in V.values())
    if single:
        print(f"== {label}: how many came ==")
        earlier = sum(1 for vid in V if (firsts.get(vid) or "9999") < start.isoformat())
        table(["visitors", "views", "seen_on_an_earlier_day", "took_an_action"], [[len(V), views, earlier, len(acted)]])
    else:
        print(f"== {label}: how many came, by day ==")
        byday = defaultdict(lambda: [set(), 0])
        for vid, v in V.items():
            for r in v["views"]:
                byday[r["eday"]][0].add(vid)
                byday[r["eday"]][1] += 1
        table(["day", "visitors", "views"], [[d.isoformat(), len(s), n] for d, (s, n) in sorted(byday.items())])
        print("== and over the whole window: a visitor seen on 2+ days is a person who came back ==")
        back = sum(1 for v in V.values() if len({r["eday"] for r in v["views"]}) >= 2)
        table(["visitors", "views", "came_back", "took_an_action"], [[len(V), views, back, len(acted)]])
    print(f"== by country ({label}) ==")
    c = Counter(v["country"] for v in V.values())
    table(["country", "visitors"], [[k, n] for k, n in c.most_common(8)])

    print(f"== how they found it ({label}): each visitor's source, and the page they landed on ==")
    src = OrderedDict()
    for v in V.values():
        f = v["views"][0]
        s = src.setdefault(source_of(f.get("ref")), [0, []])
        s[0] += 1
        if f["path"] not in s[1]:
            s[1].append(f["path"])
    rows = [[k, n, f"{len(p)} different pages" if len(p) > 3 else ",".join(p)] for k, (n, p) in src.items()]
    table(["came_from", "visitors", "landed_on"], sorted(rows, key=lambda r: -r[1]))

    print(f"== what they looked at ({label}) ==")
    seen = defaultdict(lambda: [set(), 0])
    for vid, v in V.items():
        for r in v["views"]:
            seen[r["path"]][0].add(vid)
            seen[r["path"]][1] += 1
    table(["path", "visitors", "views"], [[p, len(s), n] for p, (s, n) in sorted(seen.items(), key=lambda x: -x[1][1])[:20]])

    print(f"== how deep ({label}): pages viewed per visitor, and how many took an action ==")
    depth = OrderedDict((k, [0, 0]) for k in ("1 page", "2-3 pages", "4+ pages"))
    for vid, v in V.items():
        n = len(v["views"])
        k = "1 page" if n == 1 else "2-3 pages" if n <= 3 else "4+ pages"
        depth[k][0] += 1
        depth[k][1] += 1 if vid in acted else 0
    table(["depth", "visitors", "took_an_action"], [[k, a, b] for k, (a, b) in depth.items() if a])
    print(f"== actions ({label}): the page's controls, the watch form, a filter on the companies page ==")
    acts = defaultdict(lambda: [0, set()])
    for vid, v in V.items():
        for r, did in v["acts"]:
            acts[did][0] += 1
            acts[did][1].add(vid)
    table(["action", "n", "visitors"], [[d, n, len(s)] for d, (n, s) in sorted(acts.items(), key=lambda x: -x[1][0])[:15]])


def main(argv):
    vis = bool(argv) and argv[0] == "visitors"
    arg = (argv[1] if vis and len(argv) > 1 else argv[0] if not vis and argv else ("today" if vis else "7"))
    start, end, label, single = window(arg)
    rows, firsts = load(start, end)
    V = digest(rows)
    if vis:
        visitors_report(V, label, single)
    else:
        summary(V, firsts, start, end, label, single)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
