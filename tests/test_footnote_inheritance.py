"""RULINGS INHERIT BY VEHICLE (2026-10-01). Zuckerberg's next filing listed the
Biohub again, as 'Biohub, Inc.' with the remarks reworded; the footnote's
content hash differed and the summary asked a person again, twice in an
evening as the watcher deployed. A person's ruling now carries to the same
owner's same vehicle when the reader's fresh label and the disclaimer's
operative phrase match; a new vehicle, a changed label or a changed phrase
still asks. The summary mails only when the set waiting has changed."""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "ops"))
import footnote_review as fr  # noqa: E402


def _line(key, nature, label="disclaimed", quote="has no pecuniary interest in these shares", content="x", owner="1548760", direct="I"):
    return {"key": key, "content": content, "owner_cik": owner, "direct": direct, "nature": nature, "label": label, "quote": quote}


RULED = {"1548760|A|3|h1": {"key": "1548760|A|3|h1", "verdict": "ok", "note": "", "label": "disclaimed"}}
OLD = _line("1548760|A|3|h1", "By Chan Zuckerberg Biohub", content="c-old")


def test_the_vehicle_name_is_a_name():
    assert fr.vehicle_key("By Chan Zuckerberg Biohub, Inc.") == fr.vehicle_key("By Chan Zuckerberg Biohub")
    assert fr.vehicle_key("By Chan Zuckerberg Holdings IV, LLC") != fr.vehicle_key("By Chan Zuckerberg Holdings V, LLC")
    assert fr.vehicle_key("By CZI Holdings, LLC") == "by czi holdings"


def test_the_same_vehicle_with_the_same_disclaimer_inherits():
    new = _line("1548760|B|7|h2", "By Chan Zuckerberg Biohub, Inc.", content="c-new")
    d = fr.decided([OLD, new], RULED)
    assert d[new["key"]][0] == "ok" and "inherited by vehicle" in d[new["key"]][1] and d[new["key"]][2] == OLD["key"]


def test_a_new_vehicle_a_new_label_or_a_new_phrase_still_asks():
    other = _line("1548760|B|8|h3", "By Chan Zuckerberg Holdings VII, LLC", content="c3")
    relabel = _line("1548760|B|9|h4", "By Chan Zuckerberg Biohub, Inc.", label="partial", quote="except to the extent of his pecuniary interest", content="c4")
    rephrase = _line("1548760|B|10|h5", "By Chan Zuckerberg Biohub, Inc.", quote="disclaims beneficial ownership of these shares", content="c5")
    someone_else = _line("1548760|B|11|h6", "By Chan Zuckerberg Biohub, Inc.", owner="999", content="c6")
    direct = _line("1548760|B|12|h7", "By Chan Zuckerberg Biohub, Inc.", direct="D", content="c7")
    d = fr.decided([OLD, other, relabel, rephrase, someone_else, direct], RULED)
    for x in (other, relabel, rephrase, someone_else, direct):
        assert x["key"] not in d, x["nature"]


def test_an_inherited_ruling_does_not_seed_another():
    """only a person's own ruling carries: a chain of inheritances would drift"""
    ruled = dict(RULED)
    ruled["1548760|B|7|h2"] = {"key": "1548760|B|7|h2", "verdict": "ok", "note": "(inherited by vehicle)", "label": "disclaimed"}
    mid = _line("1548760|B|7|h2", "By Chan Zuckerberg Biohub LLC", content="c-mid")
    far = _line("1548760|C|1|h9", "By Chan Zuckerberg Biohub LLC", content="c-far")
    d = fr.decided([mid, far], ruled)
    assert mid["key"] in d and far["key"] not in d


def test_the_summary_mails_on_change_only():
    src = open(os.path.join(ROOT, "ops", "footnote_review.py"), encoding="utf-8").read()
    assert "footnotes-mailed.json" in src and "the same lines as last time" in src
    assert "Copied without asking, by vehicle" in src, "an inheritance is seen in the mail and can be overruled"


def test_the_week_sub_line_names_its_window():
    src = open(os.path.join(ROOT, "ops", "stamp_static.py"), encoding="utf-8").read()
    assert 'of the last {span}' in src and '"seven days"' in src and '"two weeks"' in src and '"month"' in src
