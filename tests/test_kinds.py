"""ONE TAXONOMY, TWO LANGUAGES (2026-09-15). The page decides what a filing
is in JavaScript (index.html: tapeKind, tapeGroup, tapeDetail, evMove,
evDim); the stamped first paint decides it in Python (ops/kinds.py). These
tests run the page's shared declarations through node over every code,
label, plan and flag the pipeline writes and hold the Python to the same
answers, so the two cannot drift. They also pin the words."""
import csv
import itertools
import json
import os
import shutil
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import kinds  # noqa: E402
import build_company_pages as bcp  # noqa: E402

CODES = ["P", "S", "A", "M", "F", "D", "G", "C", "I", "J", "L", "U", "W", "X", "Z"]
LABELS = ["open-market purchase", "scheduled purchase", "purchase, position unchanged", "sale", "discretionary sale",
          "scheduled sale", "exercise and sell", "exercise, part sold", "vested and sold", "convert and sell",
          "sale, position unchanged", "award granted", "award granted, tax withheld", "options exercised",
          "options exercised, tax withheld", "shares withheld for tax", "forfeited", "gift", "converted",
          "other transaction"]
PLANS = ["plan", "discretionary", "unknown", ""]


def _cases():
    """Every combination, plus the move/after values that exercise the guard."""
    out = []
    moves = [("", "", ""), ("-100", "", "0"), ("-100", "", "0.0"), ("2.5", "", "4.1"), ("0.4", "", "1.2"),
             ("", "0.3", "2.0"), ("-0.9", "", "3.0"), ("", "", "0")]
    for code, label, plan, pre in itertools.product(CODES, LABELS, PLANS, ["", "1"]):
        for i, (pc, pa, po) in enumerate(moves):
            if i and (code not in ("P", "S", "A", "D", "G") or plan not in ("plan", "unknown")):
                continue   # the move cases matter for the guard, not for every code
            out.append({"code": code, "label": label, "plan": plan, "pre_ipo": pre,
                        "pct_of_holding": pc, "pct_approx": pa, "pct_after": po})
    return out


def _js_answers(cases):
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    shared = bcp.extract_shared(open(os.path.join(ROOT, "index.html"), encoding="utf-8").read())
    driver = shared + r"""
const cases=JSON.parse(require("fs").readFileSync(0,"utf8"));
const nv=v=>(v===""||v===null||v===undefined)?null:Number(v);
const out=cases.map(r=>{const e={c:r.code,lb:r.label,pl:r.plan||"unknown",pre:r.pre_ipo==="1",pc:nv(r.pct_of_holding),pa:nv(r.pct_approx),po:nv(r.pct_after),mk:false};
  const m=evMove(e);
  return {kind:tapeKind(e),group:tapeGroup(e),detail:tapeDetail(e),move:m?[m.v,m.approx]:null,dim:evDim(e),moved:evMoved(e)};});
process.stdout.write(JSON.stringify(out));
"""
    # the shared block expects a few globals the page defines outside it
    prelude = "let EVENTS=[],PANEL=[],FOUNDERS={};const state={ev:{win:'7',f:true}};function $(){return null;}\n"
    try:
        p = subprocess.run([node, "-e", prelude + driver], input=json.dumps(cases), capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired) as e:  # pragma: no cover
        pytest.skip(f"node could not run the shared block: {e}")
    assert p.returncode == 0, p.stderr[-2000:]
    return json.loads(p.stdout)


def test_the_python_kinds_are_the_pages_kinds():
    cases = _cases()
    js = _js_answers(cases)
    assert len(js) == len(cases)
    for c, j in zip(cases, js):
        assert kinds.kind_of(c) == j["kind"], (c, j)
        assert kinds.group_of(c) == j["group"], (c, j)
        assert kinds.detail_of(c) == j["detail"], (c, j)
        m = kinds.move_of(c)
        assert (list(m) if m else None) == j["move"], (c, j)
        assert kinds.dim(c) == j["dim"], (c, j)
        assert kinds.moved(c) == j["moved"], (c, j)


def test_the_kinds_by_name():
    k = lambda code, label, plan="unknown", pre="": kinds.kind_of({"code": code, "label": label, "plan": plan, "pre_ipo": pre})  # noqa: E731
    assert k("P", "open-market purchase", "discretionary") == "bought" and k("P", "scheduled purchase", "plan") == "bought"
    assert k("S", "discretionary sale", "discretionary") == "disc" and k("S", "scheduled sale", "plan") == "plan"
    assert k("S", "sale", "unknown") == "sold", "a sale filed before the form had the box"
    assert k("S", "exercise and sell", "discretionary") == "comp", "compensation cashed is compensation, whatever the box says"
    assert k("P", "purchase, position unchanged", "discretionary") == "comp"
    for code in "AMFDX":
        assert k(code, "other transaction") == "comp", code
    for code in "GCIJLUWZ":
        assert k(code, "other transaction") == "xfer", code
    assert k("P", "open-market purchase", "discretionary", "1") == "xfer", "a pre-IPO catch-up"
    assert kinds.group_of({"code": "S", "label": "sale", "plan": ""}) == "sold"
    d = lambda code, label, plan="unknown": kinds.detail_of({"code": code, "label": label, "plan": plan})  # noqa: E731
    assert d("S", "sale") == "not stated" and d("S", "scheduled sale", "plan") == "pre-set plan" and d("P", "open-market purchase", "discretionary") == "open market"
    assert d("S", "exercise, part sold", "plan") == "options cashed, part kept" and d("F", "shares withheld for tax") == "withheld for tax"
    assert d("A", "award granted") == "award granted" and d("G", "gift") == "gift"


def test_the_guard_and_the_dimming():
    zero = {"code": "D", "label": "forfeited", "plan": "", "pct_of_holding": "-100", "pct_after": "0"}
    assert kinds.move_of(zero) is None, "a filing with no purchase or sale that takes the position to zero is not ranked"
    assert not kinds.dim(zero) and not kinds.moved(zero), "and it is neither dimmed nor a move: the site does not know"
    sold_out = dict(zero, code="S", label="discretionary sale", plan="discretionary")
    assert kinds.move_of(sold_out) == (-100.0, False), "a sale of the whole holding is ranked"
    small = {"code": "F", "label": "shares withheld for tax", "plan": "", "pct_of_holding": "-0.4", "pct_after": "2"}
    big = {"code": "A", "label": "award granted", "plan": "", "pct_of_holding": "40", "pct_after": "2.8"}
    assert kinds.dim(small) and not kinds.dim(big), "a grant or a withholding dims by its move"
    trade = {"code": "S", "label": "scheduled sale", "plan": "plan", "pct_of_holding": "-0.3", "pct_after": "9.5"}
    assert not kinds.dim(trade), "a purchase or a sale never dims"
    unch = {"code": "S", "label": "exercise and sell", "plan": "discretionary", "pct_of_holding": "", "pct_after": "2"}
    assert kinds.dim(unch), "a sale the site says did not move the position is dimmed"
    assert kinds.stake_change(-23.4) == "−23%" and kinds.stake_change(7.6) == "+7.6%" and kinds.stake_change(0.45) == "+0.45%" and kinds.stake_change(-0.4) == "−0.40%"
    assert kinds.stake_change(250) == "×3.5" and kinds.stake_change(-100) == "sold out"


def _week(tmp_path):
    (tmp_path / "universe").mkdir()
    (tmp_path / "universe" / "sp500-2026-09-10.csv").write_text("cik,ticker\n1,OPEN\n")
    (tmp_path / "founders.csv").write_text("ticker,founder\nOPEN,yes\nSEAL,yes\nHIRE,no\n")
    cols = ["ticker", "ceo", "filed", "traded", "code", "label", "plan", "value", "price_flag", "pct_of_holding", "pct_approx",
            "pct_after", "pre_ipo", "first_buy", "url"]
    rows = [
        ["OPEN", "Ann Founder", "2026-09-10", "2026-09-09", "P", "open-market purchase", "discretionary", "2600000", "", "2.7", "", "6.46", "", "1", "https://www.sec.gov/a"],
        ["OPEN", "Ann Founder", "2026-09-11", "2026-09-10", "A", "award granted", "", "", "", "40.3", "", "9.06", "", "", "https://www.sec.gov/b"],
        ["OPEN", "Ann Founder", "2026-09-12", "2026-09-11", "F", "shares withheld for tax", "", "", "", "-0.4", "", "9.02", "", "", "https://www.sec.gov/c"],
        ["SEAL", "Bob Founder", "2026-09-12", "2026-09-11", "G", "gift", "", "", "", "-58.5", "", "0.91", "", "", "https://www.sec.gov/d"],
        ["SEAL", "Bob Founder", "2026-09-13", "2026-09-12", "S", "exercise, part sold", "plan", "61500000", "", "166", "", "3.02", "", "", "https://www.sec.gov/e"],
        ["SEAL", "Bob Founder", "2026-09-13", "2026-09-12", "S", "scheduled sale", "plan", "7100000", "", "-23", "", "0.888", "", "", "https://www.sec.gov/f"],
        ["OPEN", "Ann Founder", "2026-09-13", "2026-09-12", "D", "forfeited", "", "", "", "-100", "", "0", "", "", "https://www.sec.gov/g"],
        ["OPEN", "Ann Founder", "2026-09-08", "2026-09-07", "P", "open-market purchase", "discretionary", "1000", "", "0.1", "", "1", "1", "", "https://www.sec.gov/h"],
        ["HIRE", "Cy Hired", "2026-09-12", "2026-09-11", "A", "award granted", "", "", "", "67.5", "", "1.34", "", "", "https://www.sec.gov/i"],
    ]
    with open(tmp_path / "events.csv", "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(cols); w.writerows(rows)
    return str(tmp_path)


def test_the_window_is_every_filing_founders_only_pre_ipo_out(tmp_path):
    root = _week(tmp_path)
    rows, since = kinds.window_rows(root, "2026-09-14")
    assert since == "2026-09-07"
    tks = [(r["tk"], r["code"]) for r in kinds.sorted_rows(rows)]
    assert ("HIRE", "A") not in tks, "founders only"
    assert ("OPEN", "P") in tks and ("OPEN", "A") in tks and ("SEAL", "G") in tks and ("OPEN", "D") in tks, "every code is a row"
    assert not any(r["filed"] == "2026-09-08" for r in rows), "a pre-IPO catch-up stays off the tape"
    # the order: bought, then plan (the sale group), then compensation ranked by |move| among the open rows
    # (award 40.3 before withholding 0.4), then the unranked ones by filing day then ticker (the guarded
    # forfeiture and the sealed exercise, both filed Sep 13: a sealed row has no move for the free first
    # paint, as on the page), then the transfer
    assert tks == [("OPEN", "P"), ("SEAL", "S"), ("OPEN", "A"), ("OPEN", "F"), ("OPEN", "D"), ("SEAL", "S"), ("SEAL", "G")], tks
    kinds_ = [kinds.kind_of(r) for r in kinds.sorted_rows(rows)]
    assert kinds_ == ["bought", "plan", "comp", "comp", "comp", "comp", "xfer"]


def test_the_weather_line_and_the_stamped_table(tmp_path):
    root = _week(tmp_path)
    rows, _ = kinds.window_rows(root, "2026-09-14")
    c = kinds.counts(rows)
    assert c == {"bought": 1, "first": 1, "disc": 0, "plan": 1, "paid": 2, "gave": 1, "n": 7}, c
    w = kinds.weather(rows)
    assert w == ("<b>1</b> CEO bought · <b>1</b> for the first time ever · <b>0</b> cut a stake · <b>1</b> sold on a plan · <b>2</b> paid in shares · "
                 "<b>1</b> gave shares away"), w
    assert "did not move a stake" not in w and "moved nothing" not in w, "no count that a sealed figure could change"
    sealed = [dict(r, sealed=True) for r in rows]
    assert kinds.counts(sealed) == c, "the line is the same on both sides of the seal"
    assert all(kinds.move_of(r) is None and not kinds.dim(r) for r in sealed), "a sealed row has no move to rank or dim by, as on the page"
    t = kinds.table_html(kinds.sorted_rows(rows), {"OPEN": "Open Co", "SEAL": "Sealed Co"})
    assert t.startswith(kinds.TAPE_HEAD) and '<th class="n">Change</th>' in t and t.count("<tr ") == 7
    assert '<span class="kind comp">Compensation</span><span class="detail">award granted</span>' in t
    assert '<span class="kind xfer">Transfer</span><span class="detail">gift</span>' in t
    assert '<td class="n v">$61.5M</td>' in t, "the sale inside an exercise shows the Form 4's number"
    assert '<span class="plus">+40%</span>' in t and '<span class="minus">−0.40%</span>' in t and 'class="dayrow dim"' in t, "the change, in the page's format; the withholding dimmed"
    assert "−23%" not in t, "a sealed company's change is blurred, never printed"
    forf = t[t.index("forfeited"):t.index("forfeited") + 400]
    assert '<td class="n ch"></td>' in forf and "sold out" not in forf, "the guarded change is blank in the stamp"
    seal = t[t.index('href="/company/SEAL/"') - 300:]
    assert seal.count('class="sealed"') >= 2 and "$61.5M" in seal, "sealed: the change and the stake blurred, the amount shown"
    assert "9.06%" in t and "0.91" not in seal.split("</tr>")[0]


def test_no_script_keeps_its_own_copy_of_the_kinds():
    """ONE COPY (2026-09-15). Every ops script that decides what a filing is
    reads ops/kinds.py; a private set of the compensation labels is how the
    tape, the letter, the drafts and the watcher drifted apart the first
    time. fle/events.py writes the labels and is the source; two scripts
    keep a narrower set on purpose and are named here so a third cannot
    appear unnoticed."""
    import re
    literal = re.compile(r'"exercise and sell",\s*"exercise, part sold",\s*"vested and sold"')
    allowed = {"kinds.py"}
    narrower = {"build_company_pages.py": "UNCHANGED", "company_cards.py": "startswith"}
    for name in sorted(os.listdir(os.path.join(ROOT, "ops"))):
        if not name.endswith(".py"):
            continue
        src = open(os.path.join(ROOT, "ops", name), encoding="utf-8").read()
        if name in allowed:
            continue
        assert not literal.search(src), f"ops/{name} keeps its own copy of the compensation labels; import kinds"
        if name in narrower:
            assert narrower[name] in src, f"ops/{name} changed its narrower rule; decide whether it is still deliberate"
    assert not os.path.exists(os.path.join(ROOT, "ops", "weekly.py")), "weekly.py is retired; its week-over-week section is ops/moves.py stakes"
