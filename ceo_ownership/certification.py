"""Who is the CEO? Read the signature on the Section 302 certification.

Sarbanes-Oxley section 302 (15 U.S.C. 7241) requires the principal executive
officer to personally certify every periodic report. The certification is
filed as Exhibit 31.1 to every 10-K and every 10-Q, and the SEC's rules
require the PEO to sign it themselves -- it cannot be signed by an
attorney-in-fact under a power of attorney.

That makes the signer the principal executive officer by operation of law,
which is why this beats every alternative:

  * Quarterly, not annual. Four observations a year.
  * 2002 onward, so a ten-year backtest is covered end to end. The tagged
    ecd:PeoName alternative only exists from the 2023 proxy season.
  * No exemptions. Emerging growth companies, smaller reporting companies and
    foreign private issuers all certify; pay-versus-performance exempts the
    first and third outright.
  * Durable. Section 302 is core statutory plumbing, well away from the
    executive-compensation disclosure simplification now on the SEC agenda.
  * Definitional. A divisional "CEO of Commercial Business" cannot sign it,
    so the failure that picked Microsoft's divisional CEO over Satya Nadella
    is impossible here rather than merely guarded against.

The document is one formulaic page: "I, [Name], certify that: 1. I have
reviewed this annual report on Form 10-K of [Company]..."
"""
from __future__ import annotations

import re
from dataclasses import dataclass, asdict

from .edgar import EdgarClient

PERIODIC_FORMS = ("10-K", "10-Q", "10-K/A", "10-Q/A")

# "I, Timothy D. Cook, certify that:" and
# "I, Jane Roe, Chief Executive Officer of Acme Inc., certify that:"
# The name is always the first comma-delimited chunk after "I,".
CERT_NAME_RE = re.compile(r"\bI,\s*([^,\n]{2,60}?)\s*,", re.I)

# A plausible personal name: two to five words, EVERY one starting with a
# capital. The capital rule matters -- without it "I, the undersigned, hereby
# state" parses as a person named "the undersigned".
NAME_SHAPE_RE = re.compile(
    r"^[A-Z][\w.'\-]*(?:[,]?\s+[A-Za-z][\w.'\-]*){1,5}$"
)
# Phrases that are shaped like names but are not people.
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

    def as_dict(self) -> dict:
        return asdict(self)


def _clean(raw: str) -> str:
    name = re.sub(r"\s+", " ", raw or "").strip(" .,;:")
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


# Exhibit filenames vary wildly: "ex311.htm", "ex-31_1.htm",
# "a10-kexhibit311.htm", "d908201dex311.htm", "citi-exh3101x6302026.htm".
# Search anywhere in the name rather than anchoring at the start.
#
# The abbreviation is the part that varies: "ex", "exh", "exhibit". An
# earlier pattern accepted only "ex" and "exhibit", so Citigroup's "exh3101"
# never matched -- the certification was sitting in the filing directory
# unrecognised, and the company was reported as having none.
EX31_NAME_RE = re.compile(r"ex(?:h|hibit)?[^a-z0-9]{0,2}31", re.I)

# XBRL viewer fragments. Large filers emit dozens of these -- Citigroup's
# 10-Q has 177 documents -- and being tiny they sort to the front of a
# size-ordered list and crowd out the real exhibits.
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

    for f in filings[:max_filings]:
        acc = f["accessionNumber"]
        try:
            index = client.filing_index(cik, acc)
        except Exception:  # noqa: BLE001
            continue

        named = _pick_exhibits(index)[:4]
        tried = {n for n, _ in named}
        # Widen only if the named candidates fail, so the common case stays
        # cheap: most filings resolve on the first document tried. The cap is
        # generous because large filers bury exhibits among many documents.
        candidates = named + _small_documents(index, tried)[:12]

        for doc_name, doc_type in candidates:
            hit = _read_certification(client, cik, acc, doc_name)
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
            continue
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
                            combined_certification=len(names) > 1,
                            other_names_in_doc=names[1:] or None,
                        )
            idx = text.lower().find("certification", idx + 1)

    return None


def _plain_text(raw: str) -> str:
    text = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"&nbsp;?|&#160;|&amp;", " ", text)


def _read_certification(
    client: EdgarClient, cik: int, acc: str, doc_name: str
) -> tuple[list[str], str] | None:
    """Read one document and return its signers if it is a PEO certification."""
    try:
        raw = client.primary_document(cik, acc, doc_name)
    except Exception:  # noqa: BLE001
        return None
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
