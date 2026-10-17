#!/usr/bin/env python3
"""INDEXNOW (2026-10-16): tell Bing which pages changed tonight.

A site with almost no inbound links gets a crawl budget to match: Bing had
the TSLA page from September 22 and had not fetched it by October 16.
IndexNow is the search engines' own channel for "these addresses changed,
fetch them": one POST per deploy to api.indexnow.org, which forwards to
Bing, DuckDuckGo, Yandex and the others that share it. Bing's index is also
what ChatGPT search reads. Google does not take IndexNow; for Google the
sitemap's lastmod stands.

What is sent is what changed. The sitemap's lastmod is the newest filing a
company's figure rests on, so a page is submitted when its figure moved, a
new page when it appears, a gone page once (the engine refetches, finds the
404 and drops it), and the three pages that change nightly (home, the tape,
the companies index) every day. weekly/indexnow-sent.json remembers what
was told; a failed POST leaves it untouched, so the next deploy tells again.

The key is INDEXNOW_KEY in .env, 8 to 128 hex characters or dashes; the
engines verify it by fetching https://founderledequities.com/<key>.txt,
which the deploy writes into public/ before publishing. No key, nothing
sent, the deploy unaffected.

    python3 ops/indexnow.py keyfile public/            write <key>.txt into the tree
    python3 ops/indexnow.py submit public/sitemap.xml  tell the engines what changed
    python3 ops/indexnow.py submit public/sitemap.xml --dry-run
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
from fle import config as _config  # noqa: E402  (loads .env; the user agent)

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
SENT = os.path.join(ROOT, "weekly", "indexnow-sent.json")
ENDPOINT = os.environ.get("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow")
HOST = "founderledequities.com"
PER_POST = 10000        # the protocol's ceiling per request
RETRY_PAUSE = 20.0      # seconds before the one retry of a 403
KEY_SHAPE = re.compile(r"^[A-Fa-f0-9-]{8,128}$")


def key():
    """the key from .env, or '' with the reason printed"""
    k = os.environ.get("INDEXNOW_KEY", "").strip()
    if not k:
        print("  indexnow: INDEXNOW_KEY is not set (.env); the engines are not told")
        return ""
    if not KEY_SHAPE.match(k):
        print("  indexnow: INDEXNOW_KEY must be 8 to 128 hex characters or dashes; the engines are not told")
        return ""
    return k


def keyfile(out_dir, k):
    """<key>.txt at the root of the tree: the engines fetch it to check the key is ours"""
    path = os.path.join(out_dir, f"{k}.txt")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(k)
    return path


def sitemap_urls(path):
    """[(loc, lastmod)] in sitemap order"""
    text = open(path, encoding="utf-8").read()
    out = []
    for m in re.finditer(r"<url>\s*<loc>([^<]+)</loc>\s*(?:<lastmod>([^<]*)</lastmod>)?", text):
        out.append((m.group(1).strip(), (m.group(2) or "").strip()))
    return out


def changed(urls, sent):
    """what the engines have not been told: a new address, a moved lastmod,
    and an address that left the sitemap (told once, then forgotten)"""
    now = dict(urls)
    fresh = [u for u, lm in urls if sent.get(u) != lm]
    gone = [u for u in sent if u not in now]
    return fresh + gone


def load_sent():
    try:
        return json.load(open(SENT, encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_sent(urls):
    os.makedirs(os.path.dirname(SENT), exist_ok=True)
    with open(SENT, "w", encoding="utf-8") as fh:
        json.dump(dict(urls), fh, indent=0, sort_keys=True)


def key_served(k, tries=12, pause=5.0):
    """THE EDGE LAGS THE DEPLOY (2026-10-16): the first submit ran seconds
    after "Deployment complete" and the endpoint answered 403, its fetch of
    the key file having beaten the file to the edge. Wait until the site
    serves the key back (a minute at most) before asking anyone to fetch it."""
    # THE POLL SAYS WHO IT IS (2026-10-17): a bare urllib fetch announces
    # itself as Python-urllib, which the edge's bot protection challenges, so
    # the poll read a challenge page for a minute and gave up while the file
    # was serving all along; the fetch carries the pipeline's own user agent
    url = f"https://{HOST}/{k}.txt"
    req = urllib.request.Request(url, headers={"User-Agent": _config.DEFAULT_USER_AGENT})
    for i in range(tries):
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.read(256).decode("utf-8", "replace").strip() == k:
                    return True
        except (urllib.error.URLError, OSError):
            pass
        if i + 1 < tries:
            time.sleep(pause)
    return False


def post(k, batch):
    """one request; True when the endpoint accepted it (200 or 202)"""
    body = json.dumps({"host": HOST, "key": k, "keyLocation": f"https://{HOST}/{k}.txt", "urlList": batch}).encode()
    req = urllib.request.Request(ENDPOINT, data=body, method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.status in (200, 202), r.status
    except urllib.error.HTTPError as e:
        # 400 bad request, 403 the key file did not check out, 422 an address
        # not on this host, 429 too many; all of them leave the record alone
        return False, e.code
    except (urllib.error.URLError, OSError) as e:
        return False, str(e)


def submit(sitemap, dry=False):
    k = key()
    if not k:
        return 0
    urls = sitemap_urls(sitemap)
    if not urls:
        print(f"  indexnow: {sitemap} lists no addresses; nothing sent")
        return 1
    sent = load_sent()
    todo = changed(urls, sent)
    if not todo:
        print(f"  indexnow: nothing changed since the last deploy ({len(urls):,} addresses on record)")
        return 0
    first = not sent
    if dry:
        print(f"  indexnow: would tell the engines about {len(todo):,} of {len(urls):,} addresses"
              + (" (the first time: everything)" if first else ""))
        for u in todo[:10]:
            print(f"    {u}")
        return 0
    if not key_served(k):
        # the poll could not confirm the file, but the engines fetch it with
        # their own crawlers; say so and send anyway, the 403 retry below
        # covers a key file that truly is not there yet
        print(f"  indexnow: could not confirm /{k}.txt from here; sending anyway")
    for i in range(0, len(todo), PER_POST):
        batch = todo[i:i + PER_POST]
        ok, status = post(k, batch)
        if not ok and status == 403:
            # the endpoint's own fetch of the key file can still be a beat
            # behind ours; one more try after a pause
            time.sleep(RETRY_PAUSE)
            ok, status = post(k, batch)
        if not ok:
            print(f"  indexnow: the endpoint answered {status}; {len(batch):,} addresses not told, will retry next deploy")
            return 1
    save_sent(urls)
    print(f"  indexnow: told the engines about {len(todo):,} of {len(urls):,} addresses"
          + (" (the first time: everything)" if first else ""))
    return 0


def main(argv):
    if len(argv) >= 2 and argv[0] == "keyfile":
        k = key()
        if not k:
            return 0
        path = keyfile(argv[1], k)
        print(f"  indexnow: key file at {os.path.relpath(path, ROOT)}")
        return 0
    if len(argv) >= 2 and argv[0] == "submit":
        return submit(argv[1], dry="--dry-run" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
