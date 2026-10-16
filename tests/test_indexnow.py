"""INDEXNOW (2026-10-16): the deploy tells the engines what changed, once,
and the description under a search result is one sentence."""
import json
import os
import sys

import pytest

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "ops"))

import indexnow  # noqa: E402

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://founderledequities.com/</loc><lastmod>2026-10-16</lastmod></url>
  <url><loc>https://founderledequities.com/tape/</loc><lastmod>2026-10-16</lastmod></url>
  <url><loc>https://founderledequities.com/company/TSLA/</loc><lastmod>2026-06-16</lastmod></url>
  <url><loc>https://founderledequities.com/company/BRVE/</loc><lastmod>2026-10-09</lastmod></url>
</urlset>
"""


def _sitemap(tmp_path, text=SITEMAP):
    p = tmp_path / "sitemap.xml"
    p.write_text(text, encoding="utf-8")
    return str(p)


def test_the_sitemap_is_read_with_its_dates(tmp_path):
    urls = indexnow.sitemap_urls(_sitemap(tmp_path))
    assert urls[0] == ("https://founderledequities.com/", "2026-10-16")
    assert ("https://founderledequities.com/company/TSLA/", "2026-06-16") in urls
    assert len(urls) == 4


def test_only_what_changed_is_told_and_a_gone_page_once(tmp_path):
    urls = indexnow.sitemap_urls(_sitemap(tmp_path))
    # the first time: everything
    assert indexnow.changed(urls, {}) == [u for u, _ in urls]
    # the next night: the pages whose lastmod moved (home and the tape move
    # daily; TSLA's figure rests on the same June filing), a new page, and
    # a page that left the sitemap, told once so the engine drops it
    sent = {"https://founderledequities.com/": "2026-10-15", "https://founderledequities.com/tape/": "2026-10-15",
            "https://founderledequities.com/company/TSLA/": "2026-06-16",
            "https://founderledequities.com/company/GONE/": "2026-01-01"}
    told = indexnow.changed(urls, sent)
    assert "https://founderledequities.com/company/TSLA/" not in told
    assert "https://founderledequities.com/company/BRVE/" in told, "a new page"
    assert "https://founderledequities.com/company/GONE/" in told, "a page that left, once"
    assert "https://founderledequities.com/tape/" in told and "https://founderledequities.com/" in told
    # nothing moved: nothing told
    assert indexnow.changed(urls, dict(urls)) == []


def test_the_key_is_checked_and_the_key_file_is_the_key(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv("INDEXNOW_KEY", raising=False)
    assert indexnow.key() == "" and "not set" in capsys.readouterr().out
    monkeypatch.setenv("INDEXNOW_KEY", "not hex!")
    assert indexnow.key() == "" and "hex" in capsys.readouterr().out
    monkeypatch.setenv("INDEXNOW_KEY", "a3f9c2e1b7d4a3f9c2e1b7d4")
    assert indexnow.key() == "a3f9c2e1b7d4a3f9c2e1b7d4"
    path = indexnow.keyfile(str(tmp_path), "a3f9c2e1b7d4a3f9c2e1b7d4")
    assert os.path.basename(path) == "a3f9c2e1b7d4a3f9c2e1b7d4.txt"
    assert open(path, encoding="utf-8").read() == "a3f9c2e1b7d4a3f9c2e1b7d4"


def test_a_submit_posts_the_list_once_and_remembers_only_on_success(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INDEXNOW_KEY", "a3f9c2e1b7d4a3f9c2e1b7d4")
    monkeypatch.setattr(indexnow, "SENT", str(tmp_path / "weekly" / "indexnow-sent.json"))
    posts = []

    def fake_post(k, batch):
        posts.append((k, list(batch)))
        return (True, 202) if len(posts) > 2 else (False, 403)

    monkeypatch.setattr(indexnow, "post", fake_post)
    monkeypatch.setattr(indexnow, "key_served", lambda k: True)
    monkeypatch.setattr(indexnow, "RETRY_PAUSE", 0)
    sm = _sitemap(tmp_path)
    # the endpoint refuses twice (the key file did not check out): nothing remembered
    assert indexnow.submit(sm) == 1
    assert "403" in capsys.readouterr().out and not os.path.exists(indexnow.SENT)
    # it accepts: everything told the first time, the record written
    assert indexnow.submit(sm) == 0
    assert "the first time" in capsys.readouterr().out
    assert posts[-1][0] == "a3f9c2e1b7d4a3f9c2e1b7d4" and len(posts[-1][1]) == 4
    assert json.load(open(indexnow.SENT))["https://founderledequities.com/company/TSLA/"] == "2026-06-16"
    # the same sitemap again: nothing to say, no request
    n = len(posts)
    assert indexnow.submit(sm) == 0 and len(posts) == n
    assert "nothing changed" in capsys.readouterr().out
    # the next night the tape moved: one address, not two thousand
    assert indexnow.submit(_sitemap(tmp_path, SITEMAP.replace("tape/</loc><lastmod>2026-10-16", "tape/</loc><lastmod>2026-10-17"))) == 0
    assert posts[-1][1] == ["https://founderledequities.com/tape/"]


def test_a_dry_run_sends_nothing(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INDEXNOW_KEY", "a3f9c2e1b7d4a3f9c2e1b7d4")
    monkeypatch.setattr(indexnow, "SENT", str(tmp_path / "indexnow-sent.json"))
    monkeypatch.setattr(indexnow, "post", lambda k, b: pytest.fail("a dry run must not post"))
    monkeypatch.setattr(indexnow, "key_served", lambda k: pytest.fail("a dry run fetches nothing"))
    assert indexnow.submit(_sitemap(tmp_path), dry=True) == 0
    assert "would tell" in capsys.readouterr().out and not os.path.exists(indexnow.SENT)


def test_the_post_carries_the_host_the_key_and_its_location(monkeypatch):
    seen = {}

    class R:
        status = 202

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=0):
        seen["url"] = req.full_url
        seen["body"] = json.loads(req.data.decode())
        return R()

    monkeypatch.setattr(indexnow.urllib.request, "urlopen", fake_urlopen)
    ok, status = indexnow.post("a3f9c2e1b7d4a3f9c2e1b7d4", ["https://founderledequities.com/tape/"])
    assert ok and status == 202
    assert seen["url"] == indexnow.ENDPOINT
    assert seen["body"]["host"] == "founderledequities.com"
    assert seen["body"]["key"] == "a3f9c2e1b7d4a3f9c2e1b7d4"
    assert seen["body"]["keyLocation"] == "https://founderledequities.com/a3f9c2e1b7d4a3f9c2e1b7d4.txt"
    assert seen["body"]["urlList"] == ["https://founderledequities.com/tape/"]


def test_the_deploy_writes_the_key_file_before_publishing_and_tells_after():
    sh = open(os.path.join(ROOT, "ops", "deploy.sh"), encoding="utf-8").read()
    key_at = sh.index("ops/indexnow.py keyfile public/")
    deploy_at = sh.index("wrangler pages deploy public")
    tell_at = sh.index("ops/indexnow.py submit public/sitemap.xml")
    alerts_at = sh.index("python3 ops/alerts.py")
    assert key_at < deploy_at < alerts_at < tell_at, "the key file rides in the tree; the alerts go first; the engines are told last"
    assert '[ "$BRANCH" = "production" ]' in sh[deploy_at:tell_at], "a preview is not the site"
    assert "INDEXNOW_KEY" in open(os.path.join(ROOT, ".env.example"), encoding="utf-8").read()


def test_the_description_under_a_search_result_is_one_sentence():
    sys.path.insert(0, os.path.join(ROOT, "ops"))
    import build_company_pages as bcp
    settled = {"ceo": "Elon Musk", "company": "Space Exploration Technologies Corp.", "ticker": "SPCX",
               "pct": "46.04", "shares": "6068547515", "shares_as_of": "2026-06-15"}
    title, desc = bcp.page_text(settled, 154.8)
    assert title == "Elon Musk owns 46.04% of Space Exploration Technologies (SPCX) · Founder Led Equities", "the title is the fact, unchanged"
    assert desc.startswith("Elon Musk, CEO of Space Exploration Technologies, owns 46.04% of the company, worth $939")
    assert desc.endswith("From SEC filings, never estimated.")
    assert "6,068,547,515" not in desc and "as of" not in desc, "the share count and the filing date are on the page"
    assert len(desc) <= 160, (len(desc), desc)
    unsettled = {"ceo": "Jane Doe", "company": "Sealed Holdings Corp", "ticker": "SEALD", "pct": "", "shares": ""}
    title, desc = bcp.page_text(unsettled, 10.0)
    assert title.startswith("How much of Sealed Holdings does Jane Doe own?")
    assert len(desc) <= 160, (len(desc), desc)


def test_nothing_is_sent_until_the_site_serves_the_key_file(tmp_path, monkeypatch, capsys):
    """THE EDGE LAGS THE DEPLOY (2026-10-16): the first live submit got a 403
    because the endpoint fetched the key file before the edge had it."""
    monkeypatch.setenv("INDEXNOW_KEY", "a3f9c2e1b7d4a3f9c2e1b7d4")
    monkeypatch.setattr(indexnow, "SENT", str(tmp_path / "indexnow-sent.json"))
    monkeypatch.setattr(indexnow, "post", lambda k, b: pytest.fail("not before the key file is served"))
    monkeypatch.setattr(indexnow, "key_served", lambda k: False)
    assert indexnow.submit(_sitemap(tmp_path)) == 1
    assert "not serving" in capsys.readouterr().out and not os.path.exists(indexnow.SENT)


def test_the_key_file_is_polled_until_it_answers_with_the_key(monkeypatch):
    answers = iter([None, "", "a3f9c2e1b7d4a3f9c2e1b7d4\n"])

    class R:
        def __init__(self, body):
            self.body = body

        def read(self, n):
            return self.body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(url, timeout=0):
        assert url == "https://founderledequities.com/a3f9c2e1b7d4a3f9c2e1b7d4.txt"
        a = next(answers)
        if a is None:
            raise indexnow.urllib.error.URLError("not yet")
        return R(a)

    monkeypatch.setattr(indexnow.urllib.request, "urlopen", fake_urlopen)
    assert indexnow.key_served("a3f9c2e1b7d4a3f9c2e1b7d4", tries=3, pause=0)
    monkeypatch.setattr(indexnow.urllib.request, "urlopen", lambda url, timeout=0: R("something else"))
    assert not indexnow.key_served("a3f9c2e1b7d4a3f9c2e1b7d4", tries=2, pause=0)


def test_a_403_is_tried_once_more_after_a_pause(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("INDEXNOW_KEY", "a3f9c2e1b7d4a3f9c2e1b7d4")
    monkeypatch.setattr(indexnow, "SENT", str(tmp_path / "indexnow-sent.json"))
    monkeypatch.setattr(indexnow, "key_served", lambda k: True)
    monkeypatch.setattr(indexnow, "RETRY_PAUSE", 0)
    calls = []
    monkeypatch.setattr(indexnow, "post", lambda k, b: (calls.append(1), (False, 403) if len(calls) == 1 else (True, 200))[1])
    assert indexnow.submit(_sitemap(tmp_path)) == 0
    assert len(calls) == 2 and "told the engines" in capsys.readouterr().out
    # any other refusal is not retried
    calls.clear()
    monkeypatch.setattr(indexnow, "post", lambda k, b: (calls.append(1), (False, 422))[1])
    assert indexnow.submit(_sitemap(tmp_path, SITEMAP.replace("2026-10-16", "2026-10-17"))) == 1
    assert len(calls) == 1
