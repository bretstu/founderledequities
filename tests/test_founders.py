"""The founder flag: the regex finds the text, the reader decides.

Every case here is a real proxy sentence that once produced a wrong yes
under the regex tier, or a real one it got right; the reader's answer is
faked so the tests pin THIS code's contract with it, not the model.
"""
import json

import pytest

from fle.founders import (FoundersApiError, VerdictCache, _decide,
                          founder_windows, llm_verdict, parse_reply,
                          quote_is_verbatim, surnames)


# THE SNOW SHAPE. One comma-spliced clause; the founder title belongs to
# the name before it. The regex tier gave it to Ramaswamy.
SNOW = ("The following directors did not receive any additional compensation "
        "for their service as a director: (i) Sridhar Ramaswamy, our CEO, and "
        "(ii) Benoit Dageville, our Founder and Chief Architect. The "
        "compensation of Mr. Ramaswamy as a named executive officer is set "
        "forth below.")
WAYFAIR = ("Our Board is co-chaired by Niraj Shah, our Co-Founder and Chief "
           "Executive Officer, and Steven Conine, our Co-Founder.")


def _reply(obj):
    return {"content": [{"type": "text", "text": json.dumps(obj)}]}


def test_the_regex_still_finds_the_window_it_no_longer_decides():
    """The stem scan is the reader's eyes: the SNOW sentence must still be
    handed over, or the model never sees the case it exists for."""
    ws = founder_windows(SNOW, surnames("Sridhar Ramaswamy"))
    assert len(ws) == 1 and "Dageville, our Founder" in ws[0]


def test_one_call_carries_every_window_and_names_the_person_and_company():
    seen = []

    def post(body):
        seen.append(json.loads(body))
        return _reply({"founder": "no", "evidence": "",
                       "founders_named": "Benoit Dageville",
                       "other_company": "Neeva", "reason": "Dageville is the founder"})

    windows = [SNOW, "Mr. Ramaswamy co-founded Neeva in 2019 with Vivek Raghunathan."]
    got = llm_verdict(windows, "Sridhar Ramaswamy", "Snowflake Inc.", "k", post=post)
    assert len(seen) == 1, "one call per company, not one per window"
    prompt = seen[0]["messages"][0]["content"]
    assert "[1] " + SNOW in prompt and "[2] Mr. Ramaswamy co-founded" in prompt
    assert "Sridhar Ramaswamy" in prompt and "Snowflake Inc." in prompt
    assert seen[0]["temperature"] == 0
    assert got["founder"] == "no" and got["other_company"] == "Neeva"
    assert got["founders_named"] == "Benoit Dageville"


def test_a_no_records_who_the_document_says_founded_it():
    v = _decide(SNOW, "DEF 14A", surnames("Sridhar Ramaswamy"), "Sridhar Ramaswamy",
                "Snowflake Inc.", "k",
                post=lambda b: _reply({"founder": "no", "evidence": "",
                                       "founders_named": "Benoit Dageville",
                                       "other_company": "Neeva", "reason": "r"}),
                cache=None)
    assert v.founder == "no" and v.method == "llm"
    assert v.founders_named == "Benoit Dageville" and v.other_company == "Neeva"
    assert v.evidence == "", "a no carries no quote unless the reader gave one"


def test_a_yes_carries_a_quote_that_is_really_in_the_filing():
    quote = "Our Board is co-chaired by Niraj Shah, our Co-Founder and Chief Executive Officer"
    v = _decide(WAYFAIR, "DEF 14A", surnames("Niraj Shah"), "Niraj Shah", "Wayfair Inc.", "k",
                post=lambda b: _reply({"founder": "yes", "evidence": quote,
                                       "founders_named": "Niraj Shah, Steven Conine",
                                       "other_company": "", "reason": "r"}),
                cache=None)
    assert v.founder == "yes" and v.method == "llm" and v.evidence == quote


def test_a_paraphrased_quote_is_not_a_receipt():
    """The evidence column must never say something the filing did not.
    A quote that is not in the windows is replaced by the window, and the
    method says so."""
    v = _decide(WAYFAIR, "DEF 14A", surnames("Niraj Shah"), "Niraj Shah", "Wayfair Inc.", "k",
                post=lambda b: _reply({"founder": "yes",
                                       "evidence": "Shah founded Wayfair in 2002.",
                                       "founders_named": "", "other_company": "",
                                       "reason": "r"}),
                cache=None)
    assert v.founder == "yes"
    assert "not verbatim" in v.method
    assert v.evidence == WAYFAIR


def test_quote_matching_ignores_punctuation_case_and_whitespace():
    assert quote_is_verbatim("niraj shah, our co-founder AND chief executive officer",
                             [WAYFAIR])
    assert quote_is_verbatim("Niraj Shah, our Co\u2011Founder", [WAYFAIR])   # non-breaking hyphen
    assert not quote_is_verbatim("Shah founded Wayfair", [WAYFAIR])
    assert not quote_is_verbatim("Shah", [WAYFAIR]), "too short to be evidence"


def test_no_windows_means_no_without_asking():
    calls = []
    v = _decide("Nothing here about how the company began, only Mr. Cook and the auditors.",
                "DEF 14A", surnames("Tim Cook"), "Tim Cook", "Apple", "k",
                post=lambda b: calls.append(1), cache=None)
    assert v.founder == "no" and v.method == "no-mention" and not calls


def test_without_the_reader_the_question_stays_open():
    """--no-llm: windows are recorded, nothing is decided. UNCERTAIN, not
    no: a rule that cannot read must not answer."""
    v = _decide(SNOW, "DEF 14A", surnames("Sridhar Ramaswamy"), "Sridhar Ramaswamy",
                "Snowflake Inc.", api_key=None, post=None, cache=None)
    assert v.founder == "uncertain" and v.method == "unread"
    assert v.evidence == v.snippets[0]


def test_unclear_is_the_readers_word_and_is_kept_apart_from_no():
    v = _decide(SNOW, "DEF 14A", surnames("Sridhar Ramaswamy"), "Sridhar Ramaswamy",
                "Snowflake Inc.", "k",
                post=lambda b: _reply({"founder": "unclear", "evidence": "",
                                       "founders_named": "", "other_company": "",
                                       "reason": "the predecessor is unnamed"}),
                cache=None)
    assert v.founder == "uncertain" and v.method == "llm-unclear"


def test_the_cache_answers_an_unchanged_document_and_asks_a_changed_one(tmp_path):
    calls = []

    def post(body):
        calls.append(1)
        return _reply({"founder": "no", "evidence": "", "founders_named": "",
                       "other_company": "", "reason": "r"})

    cache = VerdictCache(str(tmp_path / "v.json"))
    llm_verdict([SNOW], "Sridhar Ramaswamy", "Snowflake Inc.", "k", post=post, cache=cache)
    llm_verdict([SNOW], "Sridhar Ramaswamy", "Snowflake Inc.", "k", post=post, cache=cache)
    assert len(calls) == 1, "same windows, same person: not asked twice"
    assert cache.hits == 1 and cache.misses == 1

    # a new proxy year rewrites the window: asked again
    llm_verdict([SNOW + " (2027)"], "Sridhar Ramaswamy", "Snowflake Inc.", "k",
                post=post, cache=cache)
    assert len(calls) == 2
    # and the file survives a fresh process
    again = VerdictCache(str(tmp_path / "v.json"))
    llm_verdict([SNOW], "Sridhar Ramaswamy", "Snowflake Inc.", "k", post=post, cache=again)
    assert len(calls) == 2


def test_the_cache_key_changes_with_the_prompt_version(monkeypatch):
    import fle.founders as F
    k1 = VerdictCache.key("a", "b", ["w"], "m")
    monkeypatch.setattr(F, "PROMPT_VERSION", "999")
    assert VerdictCache.key("a", "b", ["w"], "m") != k1


def test_parse_reply_tolerates_fences_and_rejects_nonsense():
    assert parse_reply({"content": [{"type": "text", "text":
        '```json\n{"founder": "YES", "evidence": "x"}\n```'}]})["founder"] == "yes"
    assert parse_reply({"content": [{"type": "text", "text": "I think yes."}]}) is None
    assert parse_reply({"content": [{"type": "text", "text": '{"founder": "maybe"}'}]}) is None


def test_a_reply_that_is_not_a_verdict_is_unclear_and_not_cached(tmp_path):
    cache = VerdictCache(str(tmp_path / "v.json"))
    got = llm_verdict([SNOW], "x", "y", "k",
                      post=lambda b: {"content": [{"type": "text", "text": "Yes"}]},
                      cache=cache)
    assert got["founder"] == "unclear" and not cache.data


def test_an_api_failure_raises_not_uncertain():
    """A missing or dead key once classified a third of the universe
    'uncertain' at heuristic speed and zero cost. The classifier that
    could not ask raises; UNCLEAR remains reserved for a model that read
    the evidence and said so."""
    calls = []

    def broken_post(body):
        calls.append(1)
        raise ConnectionError("boom")

    with pytest.raises(FoundersApiError, match="failed twice"):
        llm_verdict([SNOW], "Jane Doe", "Co", api_key="k", post=broken_post)
    assert len(calls) == 2   # the one retry happened
