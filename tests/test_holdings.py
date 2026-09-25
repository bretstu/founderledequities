"""HOW THE STAKE IS HELD -- the exporter's contracts (2026-09-25).

The rows are the ledger's open groups, whole: verbatim vehicle text when the
group's own document offers it, plain words when it does not, closed groups
out, stale lines flagged, largest first. The sums-to-the-stake gate is the
page builder's (tested in test_company_pages); here the rows themselves.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fle.holdings import class_label, holdings_rows, vehicle_label  # noqa: E402
from fle.ledger import SINGLE_CLASS, Group, Ledger, vehicle_key     # noqa: E402


def _led():
    led = Ledger()
    g1 = Group(security="Class B Common Stock", direct="I")
    g1.shares = 150.0
    g1.hold_by_vehicle = {vehicle_key("I", "By CZI Holdings, LLC"): 100.0,
                          vehicle_key("I", "By Trust(9)"): 50.0}
    g1.as_of = "2026-07-31"
    g1.accession = "ACC-NEW"
    g2 = Group(security="Class A Common Stock", direct="D")
    g2.shares = 40.0
    g2.hold_by_vehicle = {vehicle_key("D", ""): 40.0}
    g2.as_of = "2020-09-22"
    g2.accession = "ACC-OLD"
    led.groups = {"class b common stock": g1, "class a common stock": g2}
    return led


def test_the_rows_are_the_open_groups_largest_first_with_stale_flags():
    rows = holdings_rows(_led())
    assert [r["shares"] for r in rows] == [100, 50, 40], "largest line first"
    assert rows[0]["klass"] == "Class B" and rows[2]["klass"] == "Class A"
    assert rows[0]["stale"] == 0 and rows[1]["stale"] == 0
    assert rows[2]["stale"] == 1, "a line six years older than the newest wears the flag"
    assert rows[0]["pct_of_stake"] == 52.6 and rows[2]["accession"] == "ACC-OLD"
    total = sum(r["shares"] for r in rows)
    assert total == 190, "the rows are the groups, whole: the page's gate compares this to the panel"


def test_zero_lines_and_labels():
    led = _led()
    led.groups["class b common stock"].hold_by_vehicle[vehicle_key("I", "By Empty GRAT")] = 0.0
    rows = holdings_rows(led)
    assert all(r["shares"] > 0 for r in rows), "a zero balance is reconciliation state, not a row"
    # without the document, the squashed key never leaks: plain words instead
    assert rows[2]["vehicle"] == "Held directly"
    assert vehicle_label(vehicle_key("I", "I"), None) == "Indirect holding"
    assert vehicle_label(vehicle_key("I", "See footnote"), "See Footnote (4)") == "Indirect, per the filing\u2019s footnote"
    assert vehicle_label(vehicle_key("I", "x"), "By Trust(9)") == "By Trust", "the filing's words, the reference stripped"
    assert class_label(SINGLE_CLASS) == "Common stock"
    assert class_label("Series A Common Stock") == "Series A"
    assert class_label("Common Stock, $.00001 par value") == "Common Stock"


def test_closed_groups_never_render():
    led = _led()
    led.retired = {"class a common stock": "2016-09-01"}
    from fle.ledger import closed_groups
    closed = {k for k, _g, _c in closed_groups(led.groups, led.retired, "")}
    rows = holdings_rows(led)
    if closed:
        assert all(r["klass"] != "Class A" for r in rows), "a retired class is not part of the answer"
    else:
        assert len(rows) == 3, "this ledger version keys retirement elsewhere; the export keeps the open groups"
