"""The watcher: EDGAR's feed of the latest Form 4s, narrowed to the
universe's chief executives."""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("live", ROOT / "ops" / "live.py")
live = importlib.util.module_from_spec(spec)
sys.modules["live"] = live
spec.loader.exec_module(live)

SAMPLE = '''<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><title>4 - Upstart Holdings, Inc. (0001647639) (Issuer)</title><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1647639/000164763926000123/0001647639-26-000123-index.htm"/></entry>
<entry><title>4 - Gu Paul (0001834231) (Reporting)</title><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1834231/000164763926000123/0001647639-26-000123-index.htm"/></entry>
<entry><title>4 - Upstart Holdings, Inc. (0001647639) (Issuer)</title><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1647639/000164763926000124/0001647639-26-000124-index.htm"/></entry>
<entry><title>4 - Some Director (0009999999) (Reporting)</title><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/9999999/000164763926000124/0001647639-26-000124-index.htm"/></entry>
</feed>'''


class Client:
    def get(self, url, use_cache=False):
        return SAMPLE


def test_the_feed_is_narrowed_to_the_ceo(monkeypatch):
    filings = live.feed(Client())
    assert filings["0001647639-26-000123"]["issuer"] == 1647639 and filings["0001647639-26-000123"]["reporters"] == {"1834231"}
    uni = {1647639: {"tk": "UPST", "owner": "1834231", "ceo": "Paul Gu", "co": "Upstart", "pct": "1.38", "asof": "2026-06-01"}}
    seen = set()
    monkeypatch.setattr(live, "describe", lambda client, u, cik, acc: [("bought", 1300000.0, "open-market purchase", "2026-09-10")])
    monkeypatch.setattr(live, "send_mail", lambda to, s, t: False)
    lines, decisions = live.one_pass(Client(), uni, seen)
    assert decisions == [("0001647639-26-000123", 1647639)], "a purchase is a decision: the run follows"
    assert len(lines) == 1 and "Paul Gu bought $1.3M" in lines[0] and "/company/UPST/" in lines[0]
    assert "Stake as of the 2026-06-01 filing: 1.38%; the new figure lands with ops/now.sh" in lines[0], "no second calculator: the site's own figure, labelled"
    assert "0001647639-26-000124" in seen, "a director's filing is remembered and never reported"
    assert live.one_pass(Client(), uni, seen) == ([], []), "nothing is reported twice"


def test_the_published_sentence_is_the_threads_wording():
    u = {"tk": "UPST", "ceo": "Paul Gu"}
    r = {"code": "P", "value": "1300000", "plan": "discretionary", "pct_of_holding": "3.85", "pct_after": "1.38", "price_flag": ""}
    assert live.sentence(u, r) == "Paul Gu bought $1.3M of UPST on the open market, added 3.9% to their stake. Now owns 1.38%.\nhttps://founderledequities.com/company/UPST/"
    r = {"code": "S", "value": "7100000", "plan": "plan", "pct_of_holding": "-23.2", "pct_after": "0.888", "price_flag": ""}
    assert "sold $7.1M of UPST under a pre-set plan, sold 23% of their stake. Now owns 0.888%." in live.sentence(u, r)
