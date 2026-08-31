"""Who the chief executive is, from the company's own certification.

The one piece of v1 carried across whole, because it is the only identity
signal that does not guess. Section 302 of Sarbanes-Oxley requires the
principal executive officer to sign "I, <name>, certify" on every 10-K and
10-Q, under penalty of perjury: the company names its own chief executive,
quarterly, in a structured exhibit.

Everything else failed. Job titles on Form 4 returned Meta's Chief Legal
Officer, Apple's General Counsel, an Nvidia director, and Microsoft's "CEO
Microsoft Commercial" instead of Satya Nadella. Only the certification is
unambiguous, and it costs one request against filings already being read.
"""
from __future__ import annotations

from __future__ import annotations
import re
from dataclasses import dataclass, asdict
from .edgar import EdgarClient, html_to_text


PERIODIC_FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A")

CERT_NAME_RE = re.compile(r"\bI,\s*([^,\n]{2,60}?)\s*,", re.I)

NAME_SHAPE_RE = re.compile(
    # Tokens may include ONE parenthesized alias: "Chih-Hsiang (Thompson)
    # Lin" is the standard English-alias convention for a large class of
    # executives' legal names, and rejecting it recorded AAOI's CEO as
    # having filed no certification. The parenthesized token is part of
    # the name's shape, never required, and never valid alone.
    r"^[A-Z][\w.'\-]*(?:[,]?\s+(?:[A-Za-z][\w.'\-]*|\([A-Za-z][\w.'\-]*\))){1,5}$"
)

NOT_A_NAME = {
    "the undersigned", "the registrant", "the company", "the corporation",
    "on behalf", "in accordance", "pursuant to",
}

EXEC_HINT_RE = re.compile(
    r"principal\s+executive\s+officer|chief\s+executive\s+officer", re.I
)

FIN_HINT_RE = re.compile(
    r"principal\s+financial\s+officer|chief\s+financial\s+officer", re.I
)

TITLE_TAIL_RE = re.compile(
    r"\s*(?:chief|principal|president|chairman|chair|ceo|officer|executive)\b.*$",
    re.I,
)

@dataclass
class CertificationPeo:
    name: str
    form: str
    filing_date: str
    period_end: str | None
    accession: str
    exhibit: str
    exhibit_type: str
    combined_certification: bool = False
    other_names_in_doc: list[str] | None = None
    # How many NEWER periodic filings were tried and yielded nothing. Zero is
    # the normal case. Anything above zero means this answer is older than the
    # company's latest report, which is how EchoStar came back naming a chief
    # executive who had left: three 2026 filings failed silently and the walk
    # settled on a 10-Q from before the change.
    filings_skipped: int = 0

    def as_dict(self) -> dict:
        return asdict(self)

# THE THIRD APOSTROPHE BUG. EDGAR wrote O'Hanley with a space; filers write
# O’Day and O’Grady with a curly quote. Both Gilead and Northern Trust were
# lost here -- the name was extracted correctly and then failed a shape test
# that allowed a straight apostrophe and not a curly one. Both CFOs, with no
# apostrophe in their names, parsed fine on the same documents.
_SMART = str.maketrans({"\u2019": "'", "\u2018": "'", "\u02bc": "'",
                        "\u2010": "-", "\u2011": "-", "\u2012": "-",
                        "\u2013": "-", "\u2014": "-", "\u00a0": " "})


def _clean(raw: str) -> str:
    name = re.sub(r"\s+", " ", (raw or "").translate(_SMART)).strip(" .,;:")
    # "Jane Roe, Chief Executive Officer" occasionally survives the split
    name = TITLE_TAIL_RE.sub("", name).strip(" .,;:")
    return name

def extract_names_from_certification(text: str) -> list[str]:
    """All 'I, <name>, certify' signers in a certification document."""
    out: list[str] = []
    for m in CERT_NAME_RE.finditer(text[:20000]):
        name = _clean(m.group(1))
        if (
            name
            and NAME_SHAPE_RE.match(name)
            and name.lower() not in NOT_A_NAME
            and name.lower() not in (n.lower() for n in out)
        ):
            out.append(name)
    return out

EX31_NAME_RE = re.compile(r"ex(?:h|hibit)?[^a-z0-9]{0,2}31", re.I)

VIEWER_FRAGMENT_RE = re.compile(r"^R\d+\.html?$", re.I)

EX31_1_HINT_RE = re.compile(r"31[._\-]?0?1\b|31[._\-]?0?1[^0-9]", re.I)

EX31_2_HINT_RE = re.compile(r"31[._\-]?0?2", re.I)

MAX_CERT_BYTES = 80_000   # a §302 certification is one page

def _small_documents(index: dict, already: set[str]) -> list[tuple[str, str]]:
    """Every small htm/txt document in the filing, smallest first.

    Filenames are not dependable: Rollins and Espey both file certifications
    the search missed because their exhibit names did not contain a
    recognisable "ex31". Rather than keep adding filename patterns, fall back
    to reading the small documents in the filing -- a certification is one
    page, so a size ceiling bounds the search to a handful of candidates and
    the content test decides.
    """
    out = []
    for it in index.get("directory", {}).get("item", []):
        name = it.get("name") or ""
        if name in already:
            continue
        if not name.lower().endswith((".htm", ".html", ".txt")):
            continue
        if VIEWER_FRAGMENT_RE.match(name):
            continue
        # Index pages and the full-submission text file are not exhibits.
        if re.search(r"-index(-headers)?\.html?$|^\d{10}-\d\d-\d{6}\.txt$",
                     name, re.I):
            continue
        try:
            size = int(it.get("size") or 0)
        except (TypeError, ValueError):
            size = 0
        if size > MAX_CERT_BYTES:
            continue
        # An UNKNOWN size must not mean "excluded". The previous test was
        # `0 < size <= MAX`, so any filing whose index omits sizes returned no
        # candidates at all and the fallback never ran. Unknown sizes are kept
        # and sorted last, behind documents known to be small.
        rank = size if size > 0 else MAX_CERT_BYTES + 1
        out.append((rank, name, it.get("type") or ""))
    out.sort()
    return [(n, t) for _, n, t in out]

def _pick_exhibits(index: dict) -> list[tuple[str, str]]:
    """Candidate certification documents, best first.

    NOTE: EDGAR's directory index.json does NOT carry the EDGAR document type
    ("EX-31.1") -- that lives on the filing index page. An earlier version
    assumed it did, matched nothing, and reported every company as having no
    certification. So candidates are ranked on filename and then confirmed by
    reading the document.
    """
    items = index.get("directory", {}).get("item", [])
    cands: list[tuple[int, str, str]] = []
    for it in items:
        name = it.get("name") or ""
        declared = (it.get("type") or "").upper().strip()
        if not name.lower().endswith((".htm", ".html", ".txt")):
            continue
        if declared.startswith("EX-31"):
            rank = 0 if declared in ("EX-31.1", "EX-31.01") else (
                3 if declared.startswith(("EX-31.2", "EX-31.02")) else 1)
            cands.append((rank, name, declared))
            continue
        if EX31_NAME_RE.search(name):
            if EX31_2_HINT_RE.search(name):
                rank = 4          # very likely the CFO certification
            elif EX31_1_HINT_RE.search(name):
                rank = 1
            else:
                rank = 2
            cands.append((rank, name, declared))

    cands.sort(key=lambda c: c[0])
    return [(n, t) for _, n, t in cands]

def peo_from_certification(
    client: EdgarClient,
    cik: int,
    before: str | None = None,
    max_filings: int = 8,
) -> CertificationPeo | None:
    """Most recent PEO signature on a Section 302 certification.

    Walks back through recent 10-K/10-Q filings until one yields a usable
    signature, so a single malformed exhibit does not lose the company.
    """
    subs = client.submissions(cik)
    filings = [
        f
        for f in subs.get("_filings", [])
        if f.get("form") in PERIODIC_FORMS
        and (before is None or f.get("filingDate", "") <= before)
    ]
    filings.sort(key=lambda f: f.get("filingDate", ""), reverse=True)

    fetch_failures = 0
    docs_read = 0
    for skipped, f in enumerate(filings[:max_filings]):
        acc = f["accessionNumber"]
        try:
            index = client.filing_index(cik, acc)
        except Exception:  # noqa: BLE001
            fetch_failures += 1
            continue

        named = _pick_exhibits(index)[:4]
        tried = {n for n, _ in named}
        # Widen only if the named candidates fail, so the common case stays
        # cheap: most filings resolve on the first document tried. The cap is
        # generous because large filers bury exhibits among many documents.
        candidates = named + _small_documents(index, tried)[:12]

        for doc_name, doc_type in candidates:
            try:
                hit = _read_certification(client, cik, acc, doc_name)
            except Exception:  # noqa: BLE001
                fetch_failures += 1
                continue
            docs_read += 1
            if hit is None:
                continue
            names, _ = hit
            return CertificationPeo(
                name=names[0],
                form=f.get("form", ""),
                filing_date=f.get("filingDate", ""),
                period_end=f.get("reportDate"),
                accession=acc,
                exhibit=doc_name,
                exhibit_type=doc_type or "(untyped)",
                filings_skipped=skipped,
                combined_certification=len(names) > 1,
                other_names_in_doc=names[1:] or None,
            )

        # Last resort: the certification sits inside the report itself, after
        # the signature page, with no separate exhibit at all.
        primary = f.get("primaryDocument") or ""
        if not primary:
            continue
        try:
            raw = client.primary_document(cik, acc, primary)
        except Exception:  # noqa: BLE001
            fetch_failures += 1
            continue
        docs_read += 1
        text = _plain_text(raw)
        idx = text.lower().find("certification")
        while idx != -1:
            window = text[idx: idx + 3000]
            if "certify" in window.lower():
                head = window[:1500]
                if not (FIN_HINT_RE.search(head) and not EXEC_HINT_RE.search(head)):
                    names = extract_names_from_certification(window)
                    if names:
                        return CertificationPeo(
                            name=names[0],
                            form=f.get("form", ""),
                            filing_date=f.get("filingDate", ""),
                            period_end=f.get("reportDate"),
                            accession=acc,
                            exhibit=primary,
                            exhibit_type="(inline, no separate exhibit)",
                            filings_skipped=skipped,
                            combined_certification=len(names) > 1,
                            other_names_in_doc=names[1:] or None,
                        )
            idx = text.lower().find("certification", idx + 1)

    if not fetch_failures and filings and docs_read == 0:
        # A SEARCH THAT READ NOTHING HAS NOT SEARCHED. Every candidate
        # list came back empty -- wrapper-only index listings whose page
        # fallback returned nothing -- so no document was ever opened.
        # That is a broken index, not a company without a certification.
        raise RuntimeError(
            f"certification search opened 0 documents across "
            f"{min(len(filings), max_filings)} periodic filing(s); index "
            f"listings were empty -- refusing to conclude 'no certification'")
    if fetch_failures:
        # EIGHT COMPANIES WERE ONCE RECORDED AS HAVING NO CERTIFICATION
        # because every fetch happened inside SEC's fair-access block and
        # each failure was swallowed as "not found". A search that could
        # not read the documents has not searched; it must error --
        # retryable with --redo failed -- never answer.
        raise RuntimeError(
            f"certification search could not read {fetch_failures} "
            f"document(s) (SEC throttling?); refusing to conclude "
            f"'no certification'")
    return None

def _plain_text(raw: str) -> str:
    """Tags out, entities DECODED, whitespace normalised.

    This replaced three entities by hand and left the rest. SEC filings write
    accented letters as numeric character references, so AES's signer arrived
    as "Andr&#233;s R. Gluski" -- not shaped like a name, and discarded.
    """
    return html_to_text(raw)

def _read_certification(
    client: EdgarClient, cik: int, acc: str, doc_name: str
) -> tuple[list[str], str] | None:
    """Read one document and return its signers if it is a PEO certification.

    Returns None only for a document that was READ and is not a
    certification. A fetch failure raises: the caller counts those, and a
    search that never truly looked must not conclude anything."""
    raw = client.primary_document(cik, acc, doc_name)
    text = _plain_text(raw)
    if "certify" not in text.lower():
        return None
    head = text[:4000]
    # Skip the CFO's certification when the header names only a financial
    # officer.
    if FIN_HINT_RE.search(head) and not EXEC_HINT_RE.search(head):
        return None
    names = extract_names_from_certification(text)
    if not names:
        return None
    return names, text
