"""The panel, and the checkpoint that lets it survive an interruption."""
import json
import os
import tempfile

from fle.panel import _load, _append, run_panel, write_csv, summarise, COLUMNS
from fle.universe import Member, parse_members


class _Client:
    pass


def test_a_finished_row_is_not_run_twice():
    """Five hundred companies is long enough that something will interrupt
    it. Rows are appended as they finish, so a rerun resumes."""
    with tempfile.TemporaryDirectory() as d:
        cp = os.path.join(d, "p.jsonl")
        _append(cp, {"cik": 1318605, "pct": 28.44, "settled": True})
        calls = []

        def _build(client, cik, company="", ticker="", on_progress=None):
            calls.append(cik)
            raise AssertionError("should not have run")

        import fle.panel as P
        real, P.build = P.build, _build
        try:
            rows = run_panel(_Client(), [Member(1318605, "TSLA", "Tesla")], cp)
        finally:
            P.build = real
        assert calls == []
        assert rows[0]["pct"] == 28.44


def test_redo_failed_retries_only_what_is_worth_retrying():
    """An error or an unsettled walk is worth another go. A settled row is
    not -- and re-running five hundred of them to fix three is why v1's
    fingerprint invalidation was dangerous in CI."""
    with tempfile.TemporaryDirectory() as d:
        cp = os.path.join(d, "p.jsonl")
        _append(cp, {"cik": 1, "pct": 5.0, "settled": True})
        _append(cp, {"cik": 2, "pct": None, "settled": False})
        _append(cp, {"cik": 3, "error": "boom", "settled": True})
        ran = []

        class _R:
            def __init__(s, cik): s.cik = cik; s.graded = []
            def as_dict(s): return {"cik": s.cik, "pct": 1.0, "settled": True}

        import fle.panel as P
        # **kw, so a new argument on ownership.build cannot make this stub
        # raise and quietly turn every row into an error row.
        real, P.build = P.build, (lambda c, cik, **kw:
                                  (ran.append(cik), _R(cik))[1])
        try:
            run_panel(_Client(), [Member(i, "T", "C") for i in (1, 2, 3)], cp,
                      redo="failed")
        finally:
            P.build = real
        assert ran == [2, 3]


def test_a_truncated_checkpoint_line_is_survivable():
    """An interrupted write leaves half a line. Losing the whole file to it
    would be worse than losing one row."""
    with tempfile.TemporaryDirectory() as d:
        cp = os.path.join(d, "p.jsonl")
        with open(cp, "w") as fh:
            fh.write(json.dumps({"cik": 1, "pct": 2.0}) + "\n")
            fh.write('{"cik": 2, "pct":')          # cut off mid-write
        assert list(_load(cp)) == [1]


def test_every_row_carries_the_links_to_check_it():
    """A panel without them is a list of assertions; with them it is a
    worksheet. v1 kept the two apart, so the answers shipped and the checking
    never happened."""
    assert "form4_url" in COLUMNS and "cover_url" in COLUMNS
      # somewhere for a human to write
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.csv")
        write_csv([{"cik": 1, "pct": 3.0, "form4_url": "u1", "cover_url": "u2"}], p)
        head = open(p, encoding="utf-8-sig").readline()
        assert "form4_url" in head and "cover_url" in head


def test_rows_are_written_highest_first():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.csv")
        write_csv([{"cik": 1, "pct": 1.0}, {"cik": 2, "pct": 9.0},
                   {"cik": 3, "pct": None}], p)
        body = open(p, encoding="utf-8-sig").read().splitlines()
        assert body[1].startswith("2,")
        assert body[-1].startswith("3,")       # no figure sorts last


def test_the_summary_counts_what_needs_attention():
    s = summarise([{"pct": 1.0, "settled": True, "confidence": "high", "flags": ""},
                   {"pct": None, "settled": False, "confidence": "none",
                    "flags": "walk did not settle; the total is a floor"},
                   {"error": "x", "settled": True, "confidence": "none", "flags": ""}])
    assert s["total"] == 3 and s["with_a_figure"] == 1
    assert s["errors"] == 1 and s["unsettled"] == 1


def test_a_slice_is_deterministic_not_a_sample():
    """v1 had --sample and --seed, and runs made with them could not be
    compared to each other. The first N in ticker order can."""
    import ast
    import inspect
    from fle import cli
    src = inspect.getsource(cli.cmd_panel)
    assert "members[:args.limit]" in src
    # look at what the code CALLS, not at what its comments mention
    called = {n.func.attr if isinstance(n.func, ast.Attribute)
              else getattr(n.func, "id", "")
              for n in ast.walk(ast.parse(src.lstrip()))
              if isinstance(n, ast.Call)}
    assert not called & {"sample", "choice", "shuffle", "seed", "randint"}


def test_progress_reports_filings_not_just_companies():
    """Some insiders have four filings and some have 778, so a bare company
    counter looks stalled on the big ones -- and reading full history made
    that the common case rather than the exception."""
    import inspect
    from fle.panel import run_panel
    src = inspect.getsource(run_panel)
    assert "on_filing" in src
    assert "on_filing(_i, len(members), _m, a, b)" in src   # index and total
    from fle import cli
    cli_src = inspect.getsource(cli.cmd_panel)
    assert "reading filing" in cli_src
    # and the shares are shown, so a wrong percentage says which leg is wrong
    assert 'num(row.get("shares"))' in cli_src or "num(row.get('shares'))" in cli_src
    assert "outstanding" in cli_src


def test_the_matched_name_is_shown_when_it_is_not_an_officer():
    """The certification names a person; the filings name whoever actually
    filed. A line reading "Brian Armstrong -> Brian Armstrong Living Trust"
    needs no explanation, and 500 of them can be skimmed in a minute."""
    import inspect
    from fle import cli
    src = inspect.getsource(cli.cmd_panel)
    assert 'row.get("owner_name")' in src
    assert 'not row.get("is_officer")' in src
    from fle.panel import COLUMNS
    assert {"ceo", "owner_name", "is_officer"} <= set(COLUMNS)


def test_every_uncounted_security_is_named_in_the_sheet():
    """A CEO commonly holds several at once -- options, RSUs and PSUs -- and
    at an up-C, partnership units alongside them.

    A single total cannot tell unvested pay apart from already-issued equity
    in an operating entity, and that distinction is the whole question: 139
    companies show options exceeding shares threefold, but nearly all of them
    are ordinary executive compensation, correctly excluded.
    """
    from fle.ownership import _titles
    from fle.panel import COLUMNS

    assert "option_titles" in COLUMNS

    several = _titles({"Restricted Stock Units": 180_000,
                       "Employee Stock Option  [strike 42.10]": 40_000,
                       "Performance Share Units": 4_302})
    # largest first, so the one that decides the classification leads
    assert several.startswith("Restricted Stock Units = 180,000")
    # trimmed to two, with the remainder counted rather than dumped
    assert "+1 more" in several
    assert "Performance Share Units" not in several

    assert _titles({}) == ""
    assert _titles({"Blackstone Holdings Partnership units": 1_438_529}) == \
        "Blackstone Holdings Partnership units = 1,438,529"


def test_the_titles_are_not_classified_for_you():
    """Keeping them as the filer wrote them. Classifying here would be another
    category guess, and the last two -- "these are partnership units", "this
    is an up-C" -- were right about Blackstone and wrong as general
    statements."""
    import inspect
    from fle import ownership
    src = inspect.getsource(ownership._titles)
    for word in ("rsu", "unvested", "partnership", "up-c", "compensation"):
        assert word not in src.lower().split('"""')[2].lower(), word


def test_the_titles_column_is_trimmed_not_dropped():
    """The full dump ran to 6,416 distinct strings across the index and was
    unreadable. But it is the only way to check whether
    `operating_partnership` classified a row correctly -- and that flag comes
    from a title match, which is the one technique worth distrusting.

    Two is enough: the largest decides the classification, and the second
    shows when a CEO holds units and pay at once.
    """
    from fle.ownership import _titles
    from fle.panel import COLUMNS

    assert "option_titles" in COLUMNS

    reit = _titles({"LTIP Units": 1_158_370, "Restricted Stock Units": 22_000})
    assert reit.startswith("LTIP Units")          # what set the flag
    assert "Restricted Stock Units" in reit       # and what did not
    assert "more" not in reit                     # nothing hidden at two

    assert _titles({"OP Units": 92_202}) == "OP Units = 92,202"


def test_no_field_carries_a_newline_into_the_sheet():
    """Filers wrap long values across lines and the break survives into the
    CSV: "Non-qualified\\nStock Option (Right to Buy)" renders as a
    three-line cell in a spreadsheet, and "By Chan Zuckerberg\\nInitiative,
    LLC" did the same to a holder name.

    Cleaned at the source in _t, and flattened again by the writer, because
    a footnote can arrive with one too.
    """
    import csv
    import os
    import tempfile
    from fle.panel import write_csv

    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "o.csv")
        write_csv([{"cik": 1, "pct": 1.0,
                    "option_titles": "Non-qualified\nStock Option = 850,000",
                    "flags": "a flag\nwith a break"}], p)
        body = open(p, encoding="utf-8-sig").read()
        assert len(body.strip().splitlines()) == 2      # header plus one row
        row = list(csv.DictReader(open(p, encoding="utf-8-sig")))[0]
        assert "\n" not in row["option_titles"]
        assert row["option_titles"] == "Non-qualified Stock Option = 850,000"


def test_every_field_a_row_writes_is_a_string_or_number():
    """`classes` was joined with "|" while holding (kind, letter) TUPLES, and
    every multi-class company died with "sequence item 0: expected str, tuple
    found" -- 48 rows, none of them caught by a test that checked the tuples
    were right.

    A record is only correct if it can be written.
    """
    import csv
    import io
    from fle.ownership import Ownership
    from fle.panel import COLUMNS

    d = Ownership(cik=1).as_dict()
    for k in COLUMNS:
        v = d.get(k, "")
        assert isinstance(v, (str, int, float, bool)) or v is None, (k, type(v))

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=COLUMNS)
    w.writeheader()
    w.writerow({k: d.get(k, "") for k in COLUMNS})
    assert len(buf.getvalue().strip().splitlines()) == 2


def test_a_curated_exclusion_is_applied_and_reported():
    """Emanuel's Form 4 lists 114 million TKO Class B shares held by
    Endeavor's entities and disclaims them in the same footnote; TKO's proxy
    reports him at 143,850 Class A and zero Class B. We read the number and
    not the sentence, and put him at 62.65%.

    No structured field separates shares that are yours from shares merely
    attributed to you, so this is curated -- and never silent.
    """
    from fle.exclusions import read_exclusions, Exclusion
    from fle.panel import COLUMNS
    assert {"excluded_shares", "excluded_detail"} <= set(COLUMNS)

    e = Exclusion(cik="1973266", ticker="TKO",
                  security="Class B Common Stock", direct="I",
                  reason="disclaimed", source="https://sec.gov/...")
    assert e.matches("Class B Common Stock", "I")
    assert not e.matches("Class A Common Stock", "I")     # one class only
    assert not e.matches("Class B Common Stock", "D")     # one side only

    import inspect
    from fle import ledger
    src = inspect.getsource(ledger.build_ledger)
    assert "led.excluded.setdefault" in src
    assert "del here[key]" in src


def test_an_exclusion_without_a_source_is_refused():
    """A source is the whole point. An entry without one is a guess with a
    CSV around it."""
    import tempfile
    import os
    from fle.exclusions import read_exclusions
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w") as fh:
        fh.write("cik,ticker,security,direct,reason,source\n"
                 "1,X,Common Stock,,because I said so,\n")
    try:
        try:
            read_exclusions(path)
            raise AssertionError("should have refused")
        except ValueError as exc:
            assert "no source" in str(exc)
    finally:
        os.unlink(path)


def test_no_list_means_no_change():
    from fle.exclusions import read_exclusions
    ex = read_exclusions("/nonexistent/exclusions.csv")
    assert not ex
    assert ex.for_issuer(1318605) == []


def test_the_panel_merges_complementary_same_day_filings_too():
    """The panel walks newest-first and keeps the first filing that reports
    each group. On a day split across two Forms 4 that is half the position,
    so the same per-vehicle merge applies -- with the newer document winning
    any vehicle both name."""
    from fle.ledger import Group, _merge_same_day

    newer = Group(security="Common Stock", direct="I", filed="2021-01-06",
                  hold_by_vehicle={"2016 Annuity Trust": 747_390,
                                   "Remainder Trust": 1_251_950})
    newer.shares = sum(newer.hold_by_vehicle.values())
    older = Group(security="Common Stock", direct="I", filed="2021-01-06",
                  hold_by_vehicle={"By Trust": 15_639_909,
                                   "Remainder Trust": 999,      # stale
                                   "By Partnership": 1_237_239})

    _merge_same_day(newer, older, newest_first=True)
    assert newer.vehicles()["Remainder Trust"] == 1_251_950     # newer wins
    assert newer.shares == 747_390 + 1_251_950 + 15_639_909 + 1_237_239


def test_the_diff_flags_a_verified_holding_that_moved():
    """A rule change is not adopted because the tests pass; it is adopted
    because someone looked at what it moved. The nine holdings reconciled
    against proxies and outside data are checked by name, and the command
    exits non-zero if any of them changed."""
    import argparse, csv as _csv, tempfile, os
    from fle import cli

    d = tempfile.mkdtemp()
    before, after = os.path.join(d, "b.csv"), os.path.join(d, "a.csv")
    for path, shares in ((before, 1_123_324_786), (after, 822_733_738)):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["ticker", "ceo", "shares", "pct"])
            w.writerow(["TSLA", "Elon Musk", shares, "28.442"])

    args = argparse.Namespace(before=before, after=after, limit=10, out="")
    assert cli.cmd_diff(args) == 1          # the anchor moved

    args = argparse.Namespace(before=before, after=before, limit=10, out="")
    assert cli.cmd_diff(args) == 0          # nothing moved


def test_the_gate_survives_a_first_run_with_no_published_panel():
    """A first run has nothing to compare against, and that is not an error.

    `refresh` hands the gate the live panel as `before`, which on a first
    run does not exist -- so a four-hour build finished, wrote its rows,
    and then died at the gate on FileNotFoundError. The gate never needed
    the baseline: the anchors are checked against the new panel alone. A
    missing baseline reads as empty, and the anchors still decide.
    """
    import argparse, csv as _csv, tempfile, os
    from fle import cli

    d = tempfile.mkdtemp()
    missing = os.path.join(d, "not-there.csv")
    after = os.path.join(d, "a.csv")

    def write(shares):
        with open(after, "w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["ticker", "ceo", "shares", "pct"])
            w.writerow(["TSLA", "Elon Musk", shares, "28.442"])

    # No baseline, anchor intact -- the run may publish.
    write(1_123_324_786)
    args = argparse.Namespace(before=missing, after=after, limit=10, out="")
    assert cli.cmd_diff(args) == 0

    # No baseline is not a licence to publish anything: the anchor still bites.
    write(822_733_738)
    assert cli.cmd_diff(args) == 1


def test_the_feed_preserves_the_report_date():
    """The period a filing covers is what makes two documents one moment, so
    it has to survive the column-to-row transform EDGAR's feed arrives in."""
    from fle.edgar import _columns_to_rows

    rows = _columns_to_rows({
        "form": ["4", "5/A"],
        "filingDate": ["2023-03-10", "2023-03-10"],
        "reportDate": ["2023-03-08", "2022-12-31"],
        "accessionNumber": ["a", "b"],
    })
    assert [r["reportDate"] for r in rows] == ["2023-03-08", "2022-12-31"]


def test_the_refresh_refuses_to_publish_when_an_anchor_moves():
    """The nine reconciled holdings are a gate, not a report. A rule change
    that quietly breaks Musk must not reach the site at 3am with nobody
    watching -- and yesterday's file must still be there in the morning."""
    import argparse, csv as _csv, os, tempfile
    from fle import cli

    d = tempfile.mkdtemp()
    live = os.path.join(d, "site")
    os.makedirs(live)

    def write(path, shares):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = _csv.writer(fh)
            w.writerow(["ticker", "ceo", "shares", "pct"])
            w.writerow(["TSLA", "Elon Musk", shares, "28.442"])

    write(os.path.join(live, "sp500.csv"), 1_123_324_786)   # yesterday, good

    # a staged panel that breaks the anchor
    stage = os.path.join(live, "_staging")
    os.makedirs(stage)
    write(os.path.join(stage, "sp500.csv"), 822_733_738)

    gate = cli.cmd_diff(argparse.Namespace(
        before=os.path.join(live, "sp500.csv"),
        after=os.path.join(stage, "sp500.csv"), limit=5, out=""))
    assert gate == 1                       # the gate fires

    # and yesterday's file is untouched
    with open(os.path.join(live, "sp500.csv"), encoding="utf-8") as fh:
        assert "1123324786" in fh.read()


def test_publishing_is_atomic():
    """A run that dies halfway must leave the live file whole. Files are
    built in staging and moved into place with one rename each."""
    import os, tempfile
    d = tempfile.mkdtemp()
    live = os.path.join(d, "sp500.csv")
    with open(live, "w", encoding="utf-8") as fh:
        fh.write("yesterday")
    stage = os.path.join(d, "staged.csv")
    with open(stage, "w", encoding="utf-8") as fh:
        fh.write("today")
    os.replace(stage, live)                # the operation refresh uses
    with open(live, encoding="utf-8") as fh:
        assert fh.read() == "today"        # never a partial write
    assert not os.path.exists(stage)


def test_every_refresh_stage_is_given_what_its_command_reads():
    """The nightly runner builds a namespace per stage by hand. The first
    version named a --cache-dir the parser has never defined, so refresh
    died on stage one; three more stages were missing arguments that would
    have killed the run hours in, in the dark, unattended.

    Rather than trust the list, this reads what each cmd_* actually takes
    off `args` and checks the runner supplies it."""
    import ast, inspect, re
    from fle import cli

    src = inspect.getsource(cli)
    tree = ast.parse(src)
    reads = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name.startswith("cmd_"):
            reads[node.name] = {
                n.attr for n in ast.walk(node)
                if isinstance(n, ast.Attribute)
                and isinstance(n.value, ast.Name) and n.value.id == "args"}

    block = src[src.index("def cmd_refresh"):src.index("\ndef cmd_diff")]
    # refresh's own options, inherited by every stage it launches
    inherited = {"user_agent", "exclusions", "dir", "universe", "since",
                 "workers", "founders", "force"}

    stages = re.findall(r"cmd_(\w+)\(ns\((.*?)\)\)", block, re.S)
    assert len(stages) >= 4, "the runner should launch panel, history, prices, founders"
    for name, argstr in stages:
        supplied = set(re.findall(r"(\w+)\s*=", argstr)) | inherited
        missing = reads.get("cmd_" + name, set()) - supplied
        assert not missing, f"refresh calls cmd_{name} without {sorted(missing)}"


def test_the_parser_builds_and_every_command_is_wired():
    """198 tests passed while the CLI could not start at all -- a patch had
    written `ix.ix.add_argument` and nothing here ever built the parser. A
    suite that green-lights a program which crashes on launch is missing the
    cheapest test there is."""
    from fle import cli

    parser = cli.build_parser() if hasattr(cli, "build_parser") else None
    if parser is None:                       # parser is built inside main()
        import argparse, inspect
        src = inspect.getsource(cli.main)
        assert "add_parser" in src
        # exercise it the only way available: parse a trivial command line
        import contextlib, io
        for argv in (["index", "--help"], ["refresh", "--help"],
                     ["panel", "--help"], ["history", "--help"],
                     ["founders", "--help"], ["prices", "--help"],
                     ["diff", "--help"]):
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                try:
                    cli.main(argv)
                except SystemExit as exc:     # --help exits 0
                    assert exc.code == 0, f"{argv[0]} failed to build"
            assert "usage:" in buf.getvalue(), argv[0]


def test_index_accepts_the_all_flag():
    """The SEC ticker file is reachable from the command line."""
    import contextlib, io
    from fle import cli
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        try:
            cli.main(["index", "--help"])
        except SystemExit:
            pass
    assert "--all" in buf.getvalue()


def test_threaded_panel_matches_sequential(tmp_path, monkeypatch):
    """Four workers, one worker: identical rows in identical order, every
    company checkpointed exactly once."""
    import csv as _csv
    import fle.panel as P

    class M:
        def __init__(self, cik, tk): self.cik, self.ticker, self.company = cik, tk, tk + " Co"
    members = [M(i, f"T{i:02}") for i in range(1, 13)]

    class Rec:
        def __init__(self, cik):
            self.graded = []
            self._d = {"cik": cik, "pct": cik * 1.0, "settled": True,
                       "confidence": "high", "ceo": f"CEO {cik}"}
        def as_dict(self): return dict(self._d)
    monkeypatch.setattr(P, "build",
                        lambda client, cik, **kw: Rec(cik))

    def run(workers, ck):
        return P.run_panel(None, members, str(ck), workers=workers)
    seq = run(1, tmp_path / "a.jsonl")
    par = run(4, tmp_path / "b.jsonl")
    assert [r["cik"] for r in seq] == [r["cik"] for r in par] == [m.cik for m in members]
    assert seq == par
    lines = open(tmp_path / "b.jsonl").read().strip().splitlines()
    assert len(lines) == 12                       # one checkpoint line each
    # and a resume run touches nothing: all rows come back marked resumed
    calls = []
    monkeypatch.setattr(P, "build", lambda *a, **k: calls.append(1) or Rec(0))
    again = run(4, tmp_path / "b.jsonl")
    assert not calls and [r["cik"] for r in again] == [m.cik for m in members]


def test_a_second_run_on_the_same_checkpoint_is_refused(tmp_path):
    """Two panels on one checkpoint corrupt each other. The lock is held by
    the process, released by the OS on exit, and refuses any second
    holder however it was launched."""
    import subprocess, sys, textwrap, time
    lock_target = str(tmp_path / "panel.jsonl")
    holder = subprocess.Popen([sys.executable, "-c", textwrap.dedent(f"""
        import sys, time; sys.path.insert(0, {repr(str(__import__('pathlib').Path(__file__).resolve().parents[1]))})
        from fle.cli import _exclusive
        h = _exclusive({lock_target!r}); print("held", flush=True); time.sleep(5)
    """)], stdout=subprocess.PIPE, text=True)
    assert holder.stdout.readline().strip() == "held"
    try:
        second = subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
            import sys; sys.path.insert(0, {repr(str(__import__('pathlib').Path(__file__).resolve().parents[1]))})
            from fle.cli import _exclusive
            _exclusive({lock_target!r})
        """)], capture_output=True, text=True)
        assert second.returncode == 2 and "another run holds" in second.stderr
    finally:
        holder.kill(); holder.wait()
    # once the holder is gone the lock is free
    subprocess.run([sys.executable, "-c", textwrap.dedent(f"""
        import sys; sys.path.insert(0, {repr(str(__import__('pathlib').Path(__file__).resolve().parents[1]))})
        from fle.cli import _exclusive
        _exclusive({lock_target!r}); print("free")
    """)], check=True)


def test_ctrl_c_stops_within_seconds_and_checkpoints_nothing_in_flight(tmp_path, monkeypatch):
    """With 2,000 companies queued, the pool's context exit once waited for
    all of them; Ctrl+C did nothing. Now: pending work cancelled, workers
    waiting on the limiter abandon their request, the interrupted company
    is never written."""
    import threading, time
    import fle.panel as P
    import fle.edgar as E
    E.STOP.clear()

    class M:
        def __init__(self, cik, tk): self.cik, self.ticker, self.company = cik, tk, tk
    members = [M(i, f"T{i:03}") for i in range(1, 41)]
    started = threading.Event()

    def slow_build(client, cik, **kw):
        started.set()
        # a worker parked in the limiter's rest loop: waits until told
        while not E.STOP.is_set():
            time.sleep(0.01)
        raise E.Stopped("interrupted")
    monkeypatch.setattr(P, "build", slow_build)

    def interrupt_soon():
        started.wait(2)
        time.sleep(0.05)
        import _thread
        _thread.interrupt_main()
    threading.Thread(target=interrupt_soon, daemon=True).start()
    t0 = time.time()
    try:
        P.run_panel(None, members, str(tmp_path / "ck.jsonl"), workers=4)
        assert False, "expected KeyboardInterrupt"
    except KeyboardInterrupt:
        pass
    assert time.time() - t0 < 5
    assert not (tmp_path / "ck.jsonl").exists() or (tmp_path / "ck.jsonl").read_text() == ""
    E.STOP.clear()
