

def test_an_api_failure_raises_not_uncertain():
    """A missing or dead key once classified a third of the universe
    'uncertain' at heuristic speed and zero cost. The classifier that
    could not ask raises; UNCLEAR remains reserved for a model that read
    the evidence and said so."""
    import pytest
    from fle.founders import FoundersApiError, llm_verdict

    calls = []
    def broken_post(body):
        calls.append(1)
        raise ConnectionError("boom")
    with pytest.raises(FoundersApiError, match="failed twice"):
        llm_verdict("Some window about the founder", "Jane Doe",
                    api_key="k", post=broken_post)
    assert len(calls) == 2   # the one retry happened

    def unclear_post(body):
        return {"content": [{"type": "text", "text": "UNCLEAR"}]}
    assert llm_verdict("w", "Jane Doe", api_key="k", post=unclear_post) is None
