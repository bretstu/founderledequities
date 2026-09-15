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
<entry><title>424B2 - JPMorgan Chase Financial Co. LLC (0001665650) (Filer)</title><link rel="alternate" href="https://www.sec.gov/Archives/edgar/data/1665650/000191870426027509/0001918704-26-027509-index.htm"/></entry>
</feed>'''


class Client:
    def get(self, url, use_cache=False):
        # one page of filings, then an empty one
        return SAMPLE if "start=0" in url else '<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"></feed>'


def test_the_feed_is_narrowed_to_the_ceo(monkeypatch):
    monkeypatch.setattr(live, "known_accessions", lambda: set())
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
    assert len(seen) == 2, "every Form 4 on the feed is remembered (a prospectus is not a filing here), so the next pass knows its frontier"
    assert "0001918704-26-027509" not in live.feed(Client()), "only Form 4 and 4/A"
    assert live.one_pass(Client(), uni, seen) == ([], []), "nothing is reported twice"


def test_the_published_sentence_is_the_threads_wording():
    u = {"tk": "UPST", "ceo": "Paul Gu"}
    r = {"code": "P", "value": "1300000", "plan": "discretionary", "pct_of_holding": "3.85", "pct_after": "1.38", "price_flag": ""}
    assert live.sentence(u, r) == "Paul Gu bought $1.3M of UPST on the open market, added 3.9% to their stake. Now owns 1.38%.\nhttps://founderledequities.com/company/UPST/"
    r = {"code": "S", "value": "7100000", "plan": "plan", "pct_of_holding": "-23.2", "pct_after": "0.888", "price_flag": ""}
    assert "sold $7.1M of UPST under a pre-set plan, sold 23% of their stake. Now owns 0.888%." in live.sentence(u, r)


def test_what_is_worth_a_post():
    f = {"founder": True}
    h = {"founder": False}
    buy = {"code": "P", "value": "50000", "plan": "discretionary", "label": "open-market purchase", "pct_of_holding": "0.1", "price_flag": ""}
    assert live.worth_a_post(f, buy) == "founder's open-market buy", "any size"
    assert live.worth_a_post(h, buy) == "", "a hired CEO's small buy is not a post"
    assert live.worth_a_post(h, dict(buy, value="2500000")) == "", "hired CEOs are not watched"
    plan_small = {"code": "S", "value": "800000", "plan": "plan", "label": "scheduled sale", "pct_of_holding": "-0.3", "price_flag": ""}
    assert live.worth_a_post(f, plan_small) == ""
    assert live.worth_a_post(f, dict(plan_small, pct_of_holding="-23.2")) == "plan that moved the holding 23.2%"
    assert live.worth_a_post(f, dict(plan_small, value="38400000")) == "plan worth $38.4M", "the name and the amount are the post"
    comp = {"code": "S", "value": "5000000", "plan": "plan", "label": "exercise and sell", "pct_of_holding": "0", "price_flag": ""}
    assert live.worth_a_post(f, comp) == ""
    assert live.worth_a_post(h, {"code": "S", "value": "90000000", "plan": "discretionary", "label": "discretionary sale", "pct_of_holding": "-40", "price_flag": ""}) == "", "a hired CEO's sale is the ordinary state of the world"


def test_a_blank_move_is_judged_by_the_stakes_before_and_after():
    """AMPL, 2026-09-14: a $2.3M planned sale, the per-filing move blank, the
    stake 5.72% before and 4.58% after. A fifth of a founder's stake is a
    post, said with the caveat that the filing alone does not explain it."""
    u = {"tk": "AMPL", "ceo": "Spenser Skates", "founder": True, "pct": "5.72"}
    r = {"code": "S", "value": "2275611", "plan": "plan", "label": "scheduled sale", "pct_of_holding": "", "pct_after": "4.5825", "price_flag": ""}
    assert live.worth_a_post(u, r).startswith("plan that moved the holding 19.")
    t = live.sentence(u, r)
    assert "Now owns 4.58%." in t and "Stake 5.72% before this filing, 4.58% after: more than the sale alone explains; read the record before posting." in t
    small = dict(r, pct_after="5.70")
    assert live.worth_a_post(u, small) == "", "a blank move with the stake barely changed is not a post"


def test_a_relisted_filing_the_site_already_carries_is_not_news(monkeypatch):
    uni = {1647639: {"tk": "UPST", "owner": "1834231", "ceo": "Paul Gu", "co": "Upstart", "pct": "1.38", "asof": "2026-06-01", "founder": True}}
    monkeypatch.setattr(live, "known_accessions", lambda: {"0001647639-26-000123"})
    monkeypatch.setattr(live, "describe", lambda *a: (_ for _ in ()).throw(AssertionError("must not parse a filing the site already carries")))
    lines, decisions = live.one_pass(Client(), uni, set())
    assert lines == [] and decisions == []
