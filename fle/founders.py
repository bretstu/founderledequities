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

THE TIERS. A sentence like "Mr. Huang co-founded NVIDIA" is decidable by
pattern and costs nothing. A sentence like "Mr. Cook succeeded our
co-founder, Steve Jobs" puts the term and the name in one window while
meaning the opposite -- those windows go to a language model when a key is
configured, and stay honestly UNCERTAIN when one is not. Every verdict,
from either tier, carries its quoted evidence into the CSV.
"""
from __future__ import annotations

import json
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

# "one of OUR founders", "the Company's co-founder" -- the claim on this
# company is staked BEFORE the word, by a possessive, rather than after it
# by an object. Both readings have to be looked for.
POSSESSIVE_FOUNDER = re.compile(
    r"\b(our|its|the\s+(?:Company|Firm|Issuer)'?s?)\s+"
    r"(?:[a-z]+\s+){0,2}(?:co[-\s]?)?founders?\b", re.IGNORECASE)
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v", "m.d.", "ph.d."}
WINDOW = 240          # characters of context kept around a founder term
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
    method: str = ""              # sentence-match | llm | no-mention | proxy-unavailable
    evidence: str = ""            # the quoted window that decided it
    source: str = ""              # form, date and accession of the proxy read
    snippets: list = field(default_factory=list)
    other_company: str = ""       # they founded something -- just not this
    early_presence: str = ""      # present | absent | "" (not looked at)


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
        lo, hi = max(0, m.start() - WINDOW), m.end() + WINDOW
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


GENERIC = {"inc", "inc.", "corp", "corp.", "corporation", "co", "co.",
           "company", "companies", "holdings", "holding", "group", "groups",
           "plc", "ltd", "ltd.", "llc", "l.l.c.", "lp", "l.p.", "nv", "n.v.",
           "sa", "s.a.", "the", "and", "of", "&", "class", "common"}
SELF_REF = re.compile(r"\b(?:the\s+)?(?:compan(?:y|ies)|firm|partnership|bank|"
                      r"issuer|business|predecessor|organization|our\s+\w+|us|it)\b",
                      re.IGNORECASE)
FOUNDED_OBJ = re.compile(
    r"(?:co[-\s]?founded|founded|co[-\s]?founder|founder)"
    r"(?:\s+(?:and|,)\s*\w+)*"          # "founded and led", "Founder and CEO,"
    r"\s*(?:of|,)?\s*"
    r"([A-Z][\w&.'\-]*(?:\s+[A-Z][\w&.'\-]*){0,4}|the\s+\w+|our\s+\w+|us\b)")


def _key(text: str) -> str:
    """Company names compared without punctuation, spacing or suffixes."""
    words = [w for w in re.split(r"[^A-Za-z0-9]+", text or "") if w]
    return "".join(w.lower() for w in words if w.lower() not in GENERIC)


def founded_objects(window: str) -> list[str]:
    """EVERY candidate the founder terms name, not just the first.

    "Our founder, David Ellison, founded Skydance in 2010" names the man
    before it names the company. Reading only the first would conclude he
    founded himself.
    """
    out = [m.group(1).strip() for m in FOUNDED_OBJ.finditer(window)]
    # a possessive stakes the same claim from in front of the word
    out += [m.group(0).strip() for m in POSSESSIVE_FOUNDER.finditer(window)]
    return out


def founded_object(window: str) -> str:
    """What the founder verb actually names.

    This is the whole discriminator. Sanjay Mehrotra "co-founded and led
    SanDisk Corporation" -- a true sentence about a man who did not found
    Micron. Apple's proxy lists directors in a table where "Founder and CEO,
    Calico" (Art Levinson) sits thirty characters from "Tim Cook". Proximity
    called both of them founders of the company they run. Naming the object
    of the verb is what separates them.
    """
    m = FOUNDED_OBJ.search(window)
    return m.group(1).strip() if m else ""


def _about_this_company(obj: str, company: str) -> bool:
    """Did they found THIS company, or merely a company?"""
    if not obj:
        return False
    if SELF_REF.fullmatch(obj.strip()) or SELF_REF.match(obj.strip()):
        return True                       # "the Company", "our predecessor"
    a, b = _key(obj), _key(company)
    if not a or not b:
        return False
    # Supermicro vs Super Micro Computer; NVIDIA vs NVIDIA Corporation
    return a.startswith(b[:8]) or b.startswith(a[:8]) or a in b or b in a


# AN HONORIFIC IS NOT THE END OF A SENTENCE.
#
# The proximity test refuses to cross a full stop, so that "founded
# Foundstone. Mr. Kurtz" cannot be read as one clause. But "Mr." is itself a
# full stop, and it stands directly in front of almost every name a proxy
# prints: "one of our founders and our largest shareholder, Mr. Musk" was
# unreachable for exactly that reason. The abbreviations lose their dots
# before the test runs; real sentence ends keep theirs.
_TITLE_DOT = re.compile(
    r"\b(Mr|Mrs|Ms|Dr|Prof|Messrs|Jr|Sr|St|Inc|Corp|Co|Ltd|No|Nos)\.",
    re.IGNORECASE)


def _flat(window: str) -> str:
    return _TITLE_DOT.sub(lambda m: m.group(1), window)


def _tight_match(window: str, names: list[str]) -> bool:
    """A pattern so close it needs no model: the name and the founder term
    inside one short span with nothing but connective tissue between --
    "Mr. Huang co-founded", "founder and CEO, Jensen Huang".
    """
    window = _flat(window)
    for n in names:
        n = re.escape(n)
        if re.search(rf"\b{n}\b[^.;]{{0,{NEAR}}}?"
                     rf"(?:co[-\s]?)?found(?:er|ers|ed|ing)\b",
                     window, re.IGNORECASE):
            return True
        if re.search(rf"\b(?:co[-\s]?)?founders?\b[^.;]{{0,{NEAR}}}?\b{n}\b",
                     window, re.IGNORECASE):
            return True
    return False


def _other_person_claims_it(window: str, names: list[str]) -> bool:
    """Founder language attached to a DIFFERENT capitalized name --
    "our co-founder, Steve Jobs" in Tim Cook's proxy."""
    m = re.search(r"\b(?:co[-\s]?founder|founder)s?[,\s]+(?:and\s+)?"
                  r"((?:[A-Z][a-z]+\s+){1,2}[A-Z][a-z]+)", window)
    if not m:
        return False
    named = m.group(1)
    return not any(n.lower() in named.lower() for n in names)


def llm_verdict(window: str, ceo: str, api_key: str, company: str = "",
                post=None) -> str | None:
    """Ask a model about ONE ambiguous window. Returns yes / no / None.

    The model never decides alone: its input is a quoted span of the proxy,
    and the span itself is written into the CSV beside the answer.
    """
    body = json.dumps({
        "model": ANTHROPIC_MODEL,
        "max_tokens": 10,
        "messages": [{"role": "user", "content":
            "Text from a proxy statement:\n\n\"" + window + "\"\n\n"
            f"Is {ceo} described as a founder or co-founder of "
            f"{company or 'this company'} SPECIFICALLY? Founding a different "
            "company, or another person being the founder, is NO. "
            "Answer with exactly one word: YES, NO, or UNCLEAR."}],
    }).encode()
    try:
        if post is None:
            req = urllib.request.Request(
                ANTHROPIC_URL, data=body,
                headers={"content-type": "application/json",
                         "x-api-key": api_key,
                         "anthropic-version": "2023-06-01"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read())
        else:
            data = post(body)
        answer = "".join(b.get("text", "") for b in data.get("content", [])
                         if b.get("type") == "text").strip().upper()
    except Exception as exc:  # noqa: BLE001
        # one retry for a transient blip; then the failure is the answer
        try:
            time.sleep(2)
            if post is None:
                req = urllib.request.Request(
                    ANTHROPIC_URL, data=body,
                    headers={"content-type": "application/json",
                             "x-api-key": api_key,
                             "anthropic-version": "2023-06-01"})
                with urllib.request.urlopen(req, timeout=30) as r:
                    data = json.loads(r.read())
            else:
                data = post(body)
            answer = "".join(b.get("text", "") for b in data.get("content", [])
                             if b.get("type") == "text").strip().upper()
        except Exception:  # noqa: BLE001
            raise FoundersApiError(
                f"API call failed twice ({type(exc).__name__}: "
                f"{str(exc)[:120]})") from exc
    if answer.startswith("YES"):
        return "yes"
    if answer.startswith("NO"):
        return "no"
    return None


def find_founder(client, cik: int, ceo: str, company: str = "",
                 api_key: str | None = None, post=None,
                 escalate: bool = True) -> Verdict:
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

    v = _decide(text, src, names, ceo, company, api_key, post)

    # THE SECOND LOOK.
    #
    # "No founder language anywhere near the name" is only as good as the
    # document it was read in. When the newest proxy says nothing, the
    # earliest one and the registration statement are consulted before the
    # answer is allowed to be no.
    # THE SECOND LOOK IS FOR EVERY NO.
    #
    # It used to fire only when the proxy said nothing at all. But a bio
    # that credits founding OTHER companies -- "founder of The Boring
    # Company" in Musk's -- is the same faded-founding shape: the language
    # about THIS company, if it exists, lives in the S-1 and the earliest
    # proxy, not the newest one.
    if escalate and v.founder == "no":
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
            # return in 1997. Founders who leave and come back, and founders
            # who were too junior to be named, are both invisible here.
            if not v.early_presence:
                v.early_presence = ("present"
                                    if any(re.search(rf"\b{re.escape(n)}\b",
                                                     text2) for n in names)
                                    else "absent")
            v2 = _decide(text2, src2, names, ceo, company, api_key, post)
            if v2.founder == "yes":
                v2.method += " (early document)"
                return v2
            if v2.method != "no-mention":
                v.other_company = v.other_company or v2.other_company
        # the label keeps HOW the no was reached, and adds where we looked
        v.method = (f"{v.method or 'no-mention'} (early documents checked; "
                    f"name {v.early_presence or 'not found'} in them)")
    return v


def _decide(text: str, src: str, names: list, ceo: str, company: str,
            api_key, post) -> Verdict:
    windows = founder_windows(text, names)
    v = Verdict(source=src, snippets=windows)
    if not windows:
        v.founder, v.method = "no", "no-mention"
        return v

    for w in windows:
        if not _tight_match(w, names) or _other_person_claims_it(w, names):
            continue
        objs = founded_objects(w)
        if not any(_about_this_company(o, company) for o in objs):
            # what they DID found, for the record -- skipping their own name
            obj = next((o for o in objs
                        if not any(n.lower() in o.lower() for n in names)), "")
            # Founder language about a DIFFERENT company. Keep looking: the
            # real sentence may be further down the same proxy, as it is for
            # George Kurtz, whose bio names Foundstone before CrowdStrike.
            v.other_company = v.other_company or obj
            continue
        v.founder, v.method, v.evidence = "yes", "sentence-match", w
        return v

    if api_key:
        for w in windows:
            got = llm_verdict(w, ceo, api_key, company=company, post=post)
            if got == "yes":
                v.founder, v.method, v.evidence = "yes", "llm", w
                return v
            if got == "no":
                v.founder, v.method, v.evidence = "no", "llm", w
        if v.founder == "no":
            return v

    v.founder = "uncertain" if v.founder == "unknown" else v.founder
    v.method = v.method or "ambiguous"
    v.evidence = v.evidence or (windows[0] if windows else "")
    return v
