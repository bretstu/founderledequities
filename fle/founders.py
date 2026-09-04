"""Is the chief executive the person who founded the company?

The site is called Founder Led Equities, and until now nothing in the data
said whether a chief executive founded anything. The flag is decided the way
everything else here is decided: from a document the company itself filed,
with the evidence quoted back.

WHY THE PROXY, NOT THE S-1. Most of the index went public before EDGAR
existed -- there is no S-1 on file for Coca-Cola -- and spin-offs register
on Form 10, foreign issuers on F-1. The proxy statement (DEF 14A) is filed
by every company every year, and the bios in it state founder status as a
matter of convention: "co-founded the Company in 1993" is proxy boilerplate.

WHY NAME PRESENCE PROVES NOTHING. A chief executive's name is ALWAYS in
their own proxy -- compensation tables, bio, signature block -- so searching
for the name answers no question. The discriminating signal is founder
LANGUAGE, so the search runs the other way: find every "found*" stem, then
ask whose name is standing next to it.

THREE VERDICTS, NOT TWO. "No founder language near the name" is a real no.
"The proxy could not be fetched" is not a no, it is an unknown, and writing
it as a no would quietly mislabel every company whose filing failed to
download. The two never share a value.

ONE READER, ALL THE EVIDENCE. The regex finds every stretch of the
document where founder language and the chief executive's surname meet;
it decides nothing. Those windows go, together, in ONE call to a language
model that answers for this person and this company only, in JSON, with
the sentence that decided it quoted back. The quote is checked against
the windows before it is recorded, so the evidence column can never say
something the filing did not.

WHY THE REGEX NO LONGER DECIDES. It once did, for the "obvious" cases,
and the obvious cases were where it was wrong. "Sridhar Ramaswamy, our
CEO, and (ii) Benoit Dageville, our Founder" is one comma-spliced clause;
the surname sat within ninety characters of the word and the rule handed
Dageville's title to Ramaswamy. Arista, Ralph Lauren, Analog Devices,
BlackLine, Wintrust, Element Solutions, FB Financial and Standard Nuclear
were all the same shape: a proxy naming the real founder in the next
breath, and the site crediting the chief executive beside them. A pattern
cannot know which name a title belongs to; a reader can. So the failure
mode moved from a wrong YES with a quote that looked like proof to a
missed window and a visible NO, which is the direction this site prefers
everywhere.

A VERDICT IS CACHED BY WHAT WAS READ. Proxies change once a year, and a
weekly re-run that re-asked the model every time would spend money to
let answers drift. The cache key is the windows themselves (plus the
model, the prompt version, the person and the company), so an unchanged
document is never asked twice and a changed one always is.

"""
from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.request
from dataclasses import dataclass, field

# THE BARE PLURAL WAS MISSING, AND IT IS THE COMMONEST FORM OF ALL.
#
# "founder", "co-founders", "founded" and "founding" all matched; "founders"
# did not, because the alternation demanded a word boundary straight after
# "founder". Tesla's proxy calls Elon Musk "one of our founders" and this
# scan never built a window around it -- so no object test, no model, no
# second look. The verdict was reached without the sentence ever being read.
# "foundation" and "foundry" still fall outside, which is the point.
FOUNDER_STEM = re.compile(r"\b(?:co[-\s]?)?found(?:er|ers|ed|ing)\b",
                          re.IGNORECASE)

SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v", "m.d.", "ph.d."}
WINDOW = 320          # characters of context kept around a founder term
NEAR = 90             # how close the surname must be to count as a candidate

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"


class FoundersApiError(RuntimeError):
    """The classifier could not ASK. Distinct from UNCLEAR (the model read
    the evidence and was unsure) -- the night this shipped, a missing key
    silently classified a third of the universe 'uncertain' at heuristic
    speed and zero cost, and the only tell was an API bill that did not
    move. A classifier that could not ask must not conclude."""
ANTHROPIC_MODEL = "claude-sonnet-4-6"


@dataclass
class Verdict:
    founder: str = "unknown"      # yes | no | uncertain | unknown
    method: str = ""              # llm | llm-unclear | no-mention | unread | proxy-unavailable | no-name
    evidence: str = ""            # the quoted window that decided it
    source: str = ""              # form, date and accession of the proxy read
    snippets: list = field(default_factory=list)
    other_company: str = ""       # they founded something -- just not this
    early_presence: str = ""      # present | absent | "" (not looked at)
    founders_named: str = ""      # whom the document calls the founders, for the reader
    reason: str = ""              # the reader's one-sentence reason (not published)


def surnames(ceo: str) -> list[str]:
    """The family names to look for, one per person.

    "Ernest C. Garcia III" is Garcia; "Joseph Bae & Scott Nuttall" is two
    people and either one founding would make the seat founder-held.
    """
    out = []
    for person in re.split(r"\s*(?:&|\band\b)\s*", ceo or ""):
        parts = [p for p in person.replace(",", " ").split()
                 if p.lower() not in SUFFIXES]
        if parts:
            out.append(parts[-1])
    return out


def _strip_html(html: str) -> str:
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", html,
                  flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = (text.replace("&nbsp;", " ").replace("&amp;", "&")
                .replace("&#160;", " ").replace("&rsquo;", "'")
                .replace("&#8217;", "'"))
    return re.sub(r"\s+", " ", text)


# In preference order. The proxy states founder status in a bio and every
# company files one -- but a company that registered last year has not held
# an annual meeting yet, so a spin-off or a fresh listing has no proxy at
# all. For those, the registration statement is exactly the document the
# original design reached for, and it is where the founding story lives.
DOC_FORMS = ("DEF 14A", "10-K", "S-1", "S-1/A", "10-12B", "10-12B/A",
             "424B4", "424B3", "S-4", "F-1", "20-F")


EARLY_FORMS = ("S-1", "S-1/A", "10-12B", "10-12B/A", "424B4", "424B1",
               "F-1", "SB-2")


def early_documents(client, cik: int, tries: int = 3) -> list:
    """The company's OLDEST proxy and its registration statement.

    Founding language fades. A founder who has run the place for thirty
    years may have a current bio that says only "has served as Chief
    Executive Officer since 1993" -- the founding edited out years ago as
    the story stopped being news. The early documents still say it.

    These are never read FIRST, because the oldest proxy predates most
    sitting chief executives entirely: Amazon's earliest contains no mention
    of Andrew Jassy, and finding nothing there would be mistaken for finding
    that he founded nothing.
    """
    subs = client.submissions(cik)
    filings = subs.get("_filings", [])
    proxies = sorted((f for f in filings
                      if (f.get("form") or "").upper() == "DEF 14A"),
                     key=lambda f: f.get("filingDate") or "")
    early = sorted((f for f in filings
                    if (f.get("form") or "").upper() in EARLY_FORMS),
                   key=lambda f: f.get("filingDate") or "")
    out = []
    for f in (early[:1] + proxies[:1] + early[1:2]):
        text, src = _fetch(client, cik, f)
        if text:
            out.append((text, src))
        if len(out) >= tries:
            break
    return out


def _fetch(client, cik: int, f: dict) -> tuple[str, str]:
    name = (f.get("primaryDocument") or "").split("/")[-1]
    if not name:
        return "", ""
    url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
           f"{(f.get('accessionNumber') or '').replace('-', '')}/{name}")
    try:
        html = client.get(url)
    except Exception:  # noqa: BLE001
        return "", ""
    text = _strip_html(html)
    if len(text) <= 400:
        return "", ""
    return text, f"{f.get('form')} {f.get('filingDate')} {f.get('accessionNumber')}"


def proxy_text(client, cik: int, tries: int = 6) -> tuple[str, str]:
    """The best document available for this company, as plain text.

    Several candidates are attempted rather than one: a single 404 on the
    newest proxy used to condemn the whole company to "unknown", which is
    how Blackstone -- a company that has filed a proxy every year for
    fifteen years -- ended up with no verdict at all.
    """
    subs = client.submissions(cik)
    filings = subs.get("_filings", [])
    ranked = []
    for f in filings:
        form = (f.get("form") or "").upper()
        if form in DOC_FORMS:
            ranked.append((DOC_FORMS.index(form),
                           -_date_key(f.get("filingDate")), f))
    ranked.sort(key=lambda t: (t[0], t[1]))

    for _, _, f in ranked[:tries]:
        name = (f.get("primaryDocument") or "").split("/")[-1]
        if not name:
            continue
        url = (f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/"
               f"{(f.get('accessionNumber') or '').replace('-', '')}/{name}")
        try:
            html = client.get(url)
        except Exception:  # noqa: BLE001 -- try the next candidate
            continue
        text = _strip_html(html)
        if len(text) > 400:
            return text, (f"{f.get('form')} {f.get('filingDate')} "
                          f"{f.get('accessionNumber')}")
    return "", ""


def _date_key(d: str | None) -> int:
    return int((d or "").replace("-", "") or 0)


def founder_windows(text: str, names: list[str]) -> list[str]:
    """Every stretch of proxy where founder language and the name meet."""
    hits = []
    for m in FOUNDER_STEM.finditer(text):
        lo, hi = max(0, m.start() - WINDOW), min(len(text), m.end() + WINDOW)
        # SNAP TO WORDS. A window cut mid-word ("...ounder and has served")
        # made the reader's quote fail the verbatim check fifty times in one
        # run: the sentence it copied began one character before the cut.
        while lo > 0 and not text[lo - 1].isspace():
            lo -= 1
        while hi < len(text) and not text[hi - 1].isspace():
            hi += 1
        window = text[lo:hi]
        if any(re.search(rf"\b{re.escape(n)}\b", window) for n in names):
            hits.append(window.strip())
    # neighbouring stems produce overlapping windows; keep distinct ground
    out: list[str] = []
    for h in hits:
        if not any(h[40:120] and h[40:120] in prev for prev in out):
            out.append(h)
    # Musk's proxy names The Boring Company, Neuralink, SpaceX and a fistful
    # of Foundations before it ever gets near Tesla. Capped at twelve, the
    # scan spent its whole budget on windows about OTHER companies and never
    # reached the sentence that mattered.
    return out[:48]



# ------------------------------------------------------------ the reader

# BUMP WHEN THE PROMPT CHANGES. It is part of the cache key: an old answer
# to a different question is not an answer.
PROMPT_VERSION = "3"

# WHOSE FILING IT IS comes first, because the reader will otherwise infer
# it from the excerpts. SpaceX's S-1 describes xAI's business for pages;
# handed nine excerpts about Grok and "our founder Elon Musk" with no
# filer named, the reader concluded "our" was xAI and answered no, with
# "Musk is our founder, Chief Executive Officer ... and the Chairman of
# our board" among the excerpts. Version 2 never said who "our" was.
PROMPT = """You are reading excerpts from a filing that {company} made with the SEC: its {source}. In these excerpts "we", "our", "us" and "the Company" mean {company}, whatever businesses the excerpts describe; a registrant describes the businesses it owns.

Each excerpt is a stretch of text around the word "founder", "founded" or "founding" that also contains the name {ceo}.

Question: do these excerpts describe {ceo}, the chief executive of {company}, as a founder or co-founder of {company}?

How to read them:
- A founder title belongs to the person it is attached to. "Jane Roe, our Founder" is about Jane Roe and nobody else, even when other names sit in the same sentence or list. A shared surname is not a shared title: "Ms. DeWitte, our co-founder" says nothing about Mr. DeWitte.
- {company} includes its predecessors, subsidiaries and earlier corporate forms. A business the filing calls "our predecessor", "our immediate predecessor" or "our operating company", or one that carries the company's own name (Dell Inc. for Dell Technologies Inc.), is this company; founding it is founding {company}.
- A different business is different: a company that {company} later acquired or merged with, a former employer, an investment firm that manages or sponsors {company}, a foundation. Founding one of those is NO here; record it under other_company.
- "Founding organizer", "founding partner", "founding officer", "member of the founding team" and "founded {company} in <year>" all count as co-founder language.
- "Founders Awards", "Founder Grants" and similar are names of pay programs, not statements about founding. A skills-matrix column headed "Founder" attaches to nobody.
- If no excerpt attaches founder language about {company} to {ceo}, the answer is NO, however prominent the person is elsewhere. UNCLEAR is for a genuine ambiguity about this person and this company, and should be rare.

Record your verdict with the record_verdict tool. The evidence must be one sentence copied exactly from an excerpt; if no sentence supports a YES, leave it empty. founders_named is whom the excerpts call founders or co-founders of {company}; other_company is a business the excerpts say {ceo} founded that is not {company}.

Excerpts:
{excerpts}"""

# THE VERDICT IS A TOOL CALL, NOT PROSE. Asked for JSON in text, the model
# answered Oklo twice with something the parser could not read (a quote
# inside the quoted evidence, most likely) and the code recorded
# "uncertain" for a reader that had never been understood. A forced tool
# call returns a structure the API has already validated against the
# schema; there is nothing to parse.
VERDICT_TOOL = {
    "name": "record_verdict",
    "description": "Record whether the chief executive is described as a "
                   "founder of this company, with the evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "founder": {"type": "string", "enum": ["yes", "no", "unclear"]},
            "evidence": {"type": "string",
                         "description": "One sentence copied exactly from an excerpt; empty if none."},
            "founders_named": {"type": "string",
                               "description": "People the excerpts call founders or co-founders of this company, comma separated; empty if none."},
            "other_company": {"type": "string",
                              "description": "A business the excerpts say the chief executive founded that is not this company; empty if none."},
            "reason": {"type": "string", "description": "One sentence."},
        },
        "required": ["founder", "evidence", "founders_named", "other_company", "reason"],
    },
}

MAX_TOKENS = 600


class VerdictCache:
    """Answers already given, keyed by exactly what was asked.

    A JSON file in the document cache, written atomically after each new
    answer so an interrupted run keeps what it paid for."""

    def __init__(self, path: str | None):
        self.path = path
        self.data: dict = {}
        self.hits = 0
        self.misses = 0
        if path and os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as fh:
                    self.data = json.load(fh)
            except (OSError, ValueError):
                self.data = {}

    @staticmethod
    def key(ceo: str, company: str, windows: list, model: str,
            source: str = "") -> str:
        raw = "\x1f".join([PROMPT_VERSION, model, ceo, company, source]
                           + list(windows))
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def get(self, k: str):
        got = self.data.get(k)
        if got is not None:
            self.hits += 1
        else:
            self.misses += 1
        return got

    def put(self, k: str, value: dict) -> None:
        self.data[k] = value
        if not self.path:
            return
        tmp = f"{self.path}.{os.getpid()}.tmp"
        try:
            os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.data, fh)
            os.replace(tmp, self.path)
        except OSError:
            pass


def _post(body: bytes, api_key: str) -> dict:
    req = urllib.request.Request(
        ANTHROPIC_URL, data=body,
        headers={"content-type": "application/json", "x-api-key": api_key,
                 "anthropic-version": "2023-06-01"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def quote_is_verbatim(quote: str, windows: list) -> bool:
    """Is the model's evidence really in the text it was given? Compared
    with punctuation, case and whitespace removed, so a smart quote or a
    decoded entity does not fail a real quote; anything else does."""
    q = _norm(quote)
    if len(q) < 12:
        return False
    return any(q in _norm(w) for w in windows)


def parse_reply(data: dict) -> dict | None:
    """The verdict in the model's reply, or None.

    A forced tool call arrives as a tool_use block whose input is already a
    dict; a JSON object in text is accepted too, so a reply from a client
    that ignores tools still reads."""
    got = None
    for b in data.get("content", []):
        if b.get("type") == "tool_use" and isinstance(b.get("input"), dict):
            got = b["input"]
            break
    if got is None:
        text = "".join(b.get("text", "") for b in data.get("content", [])
                       if b.get("type") == "text").strip()
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text)
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            got = json.loads(m.group(0))
        except ValueError:
            return None
    if not isinstance(got, dict):
        return None
    f = str(got.get("founder") or "").strip().lower()
    if f not in ("yes", "no", "unclear"):
        return None
    return {"founder": f,
            "evidence": str(got.get("evidence") or "").strip(),
            "founders_named": str(got.get("founders_named") or "").strip(),
            "other_company": str(got.get("other_company") or "").strip(),
            "reason": str(got.get("reason") or "").strip()}


def _describe(source: str) -> str:
    """'DEF 14A 2026-05-18 0001640147-26-000019' -> 'DEF 14A (proxy
    statement) filed 2026-05-18'."""
    kinds = {"DEF 14A": "proxy statement", "10-K": "annual report",
             "S-1": "registration statement", "F-1": "registration statement",
             "10-12B": "registration statement", "424B4": "prospectus",
             "S-4": "registration statement", "20-F": "annual report"}
    parts = (source or "").split()
    if not parts:
        return "filing"
    date = next((p for p in parts if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p)), "")
    form = " ".join(p for p in parts if p != date and not re.fullmatch(r"\d{10}-\d{2}-\d{6}", p))
    kind = kinds.get(form)
    out = f"{form} ({kind})" if kind else form
    return f"{out} filed {date}" if date else out


def llm_verdict(windows: list, ceo: str, company: str, api_key: str,
                post=None, cache: VerdictCache | None = None,
                source: str = "") -> dict:
    """One call, every window, a JSON verdict for THIS person at THIS
    company. Returns {founder, evidence, founders_named, other_company,
    reason, verbatim}; founder is yes / no / unclear.

    The model never decides alone: its input is quoted spans of the
    filing, its evidence is checked against those spans, and both are
    written to the CSV beside the answer."""
    model = ANTHROPIC_MODEL
    k = VerdictCache.key(ceo, company, windows, model, source)
    if cache is not None:
        got = cache.get(k)
        if got is not None:
            return dict(got)

    excerpts = "\n\n".join(f"[{i}] {w}" for i, w in enumerate(windows, 1))
    body = json.dumps({
        "model": model, "max_tokens": MAX_TOKENS, "temperature": 0,
        "tools": [VERDICT_TOOL],
        "tool_choice": {"type": "tool", "name": "record_verdict"},
        "messages": [{"role": "user", "content": PROMPT.format(
            ceo=ceo, company=company or "this company",
            source=_describe(source), excerpts=excerpts)}],
    }).encode()
    send = post if post is not None else (lambda b: _post(b, api_key))

    parsed = None
    last_exc = None
    for attempt in range(2):
        try:
            if attempt:
                time.sleep(2)
            parsed = parse_reply(send(body))
        except Exception as exc:  # noqa: BLE001 -- transport; one retry
            last_exc = exc
            continue
        if parsed is not None:
            break
    if last_exc is not None and parsed is None:
        # the failure is the answer, and it must not be recorded as one
        raise FoundersApiError(
            f"API call failed twice ({type(last_exc).__name__}: "
            f"{str(last_exc)[:120]})") from last_exc
    if parsed is None:
        # Read twice, never a JSON object: the model was asked and did
        # not answer the question. Not cached, so the next run asks again.
        return {"founder": "unclear", "evidence": "", "founders_named": "",
                "other_company": "", "reason": "reply was not a JSON verdict",
                "verbatim": False}
    parsed["verbatim"] = quote_is_verbatim(parsed["evidence"], windows)
    if cache is not None:
        cache.put(k, parsed)
    return dict(parsed)


# ------------------------------------------------------------ the verdict

def _decide(text: str, src: str, names: list, ceo: str, company: str,
            api_key, post, cache) -> Verdict:
    windows = founder_windows(text, names)
    v = Verdict(source=src, snippets=windows)
    if not windows:
        v.founder, v.method = "no", "no-mention"
        return v
    if not api_key and post is None:
        # deliberately running without the reader (--no-llm): the windows
        # are recorded, the question is left open
        v.founder, v.method = "uncertain", "unread"
        v.evidence = windows[0]
        return v
    got = llm_verdict(windows, ceo, company, api_key, post=post, cache=cache,
                      source=src)
    v.founder = {"yes": "yes", "no": "no"}.get(got["founder"], "uncertain")
    v.method = "llm"
    v.founders_named = got.get("founders_named", "")
    v.other_company = got.get("other_company", "")
    v.reason = got.get("reason", "")
    if got["founder"] == "unclear" and got.get("reason"):
        v.method = "llm-unclear"
    if got["evidence"] and got.get("verbatim"):
        v.evidence = got["evidence"]
    elif got["evidence"]:
        # THE QUOTE MUST BE IN THE FILING. A paraphrase is not a receipt:
        # the window it was drawn from is recorded instead, and the method
        # says the quote was not verbatim so a reader knows to look.
        v.method += " (quote not verbatim; window shown)"
        v.evidence = next((w for w in windows
                           if any(n.lower() in w.lower() for n in names)),
                          windows[0])
    else:
        v.evidence = windows[0] if v.founder != "no" else ""
    return v


def find_founder(client, cik: int, ceo: str, company: str = "",
                 api_key: str | None = None, post=None,
                 escalate: bool = True, cache: VerdictCache | None = None) -> Verdict:
    names = surnames(ceo)
    if not names:
        return Verdict(founder="unknown", method="no-name")
    try:
        text, src = proxy_text(client, cik)
    except Exception:  # noqa: BLE001
        text, src = "", ""
    if not text:
        # The distinction the whole design protects: a fetch that failed is
        # not evidence of anything.
        return Verdict(founder="unknown", method="proxy-unavailable")

    v = _decide(text, src, names, ceo, company, api_key, post, cache)

    # THE SECOND LOOK, FOR EVERY ANSWER THAT IS NOT YES.
    #
    # "No founder language near the name" is only as good as the document
    # it was read in, and founding language fades: a bio that credits
    # founding OTHER companies ("founder of The Boring Company" in Musk's)
    # is the same faded shape. The language about THIS company, if it
    # exists, lives in the S-1 and the earliest proxy, not the newest one.
    if escalate and v.founder in ("no", "uncertain"):
        try:
            docs = early_documents(client, cik)
        except Exception:  # noqa: BLE001
            docs = []
        for text2, src2 in docs:
            if src2 == src:
                continue
            # WAS THIS PERSON EVEN THERE?
            #
            # A chief executive absent from the company's earliest filing is
            # very unlikely to have founded it -- strong corroboration for a
            # no, and recorded as such. It is not proof, and never decides
            # anything on its own: a proxy names directors and a few senior
            # officers, not everyone who founded the place. Steve Jobs appears
            # in no Apple proxy of 1994; he had been gone nine years and would
            # return in 1997.
            if not v.early_presence:
                v.early_presence = ("present"
                                    if any(re.search(rf"\b{re.escape(n)}\b",
                                                     text2) for n in names)
                                    else "absent")
            v2 = _decide(text2, src2, names, ceo, company, api_key, post, cache)
            if v2.founder == "yes":
                v2.method += " (early document)"
                v2.early_presence = v.early_presence
                return v2
            if v2.method != "no-mention":
                v.other_company = v.other_company or v2.other_company
                v.founders_named = v.founders_named or v2.founders_named
        # the label keeps HOW the answer was reached, and adds where we looked
        v.method = (f"{v.method or 'no-mention'} (early documents checked; "
                    f"name {v.early_presence or 'not found'} in them)")
    return v
