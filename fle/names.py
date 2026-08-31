"""Matching a person named two ways.

EDGAR writes "Musk Elon"; a Section 302 certification says "Elon Musk"; a
proxy might say "Elon R. Musk". Surname order differs, initials abbreviate,
suffixes come and go, and accents survive in one place and not the other --
"Stephane Bancel" against "BANCEL STEPHANE" cost five companies in v1 until
the Unicode decomposition was fixed.

Carried over from v1 unchanged because it earned its place: it correctly
refuses "Satya Nadella" against "Althoff Judson", which is the failure that
cost the most time.
"""
from __future__ import annotations

import re
import unicodedata


NICKNAMES = {
    "robert": {"bob", "rob", "bobby"}, "william": {"bill", "will", "billy"},
    "richard": {"rick", "dick", "rich"}, "james": {"jim", "jimmy"},
    "john": {"jack", "johnny"}, "michael": {"mike"}, "thomas": {"tom", "tommy"},
    "charles": {"charlie", "chuck"}, "edward": {"ed", "eddie", "ted"},
    "daniel": {"dan", "danny"}, "christopher": {"chris"}, "joseph": {"joe", "joey"},
    "anthony": {"tony"}, "kenneth": {"ken"}, "steven": {"steve"},
    "stephen": {"steve"}, "andrew": {"andy", "drew"}, "matthew": {"matt"},
    "nicholas": {"nick"}, "benjamin": {"ben"}, "samuel": {"sam"},
    "patricia": {"pat", "patty"}, "elizabeth": {"liz", "beth", "betsy"},
    "katherine": {"kate", "kathy", "katie"}, "margaret": {"maggie", "peggy"},
    "jennifer": {"jen", "jenny"}, "deborah": {"deb", "debbie"},
    "susan": {"sue", "susie"}, "rebecca": {"becky"}, "jeffrey": {"jeff"},
    "gregory": {"greg"}, "lawrence": {"larry"}, "ronald": {"ron"},
    "donald": {"don"}, "timothy": {"tim"}, "frederick": {"fred"},
    "roland": {"ron"}, "lawrence2": set(), "francis": {"frank"},
    "theodore": {"ted", "teddy"}, "eugene": {"gene"}, "arthur": {"art"},
    "albert": {"al"}, "alexander": {"alex", "sandy"}, "vincent": {"vince"},
    "raymond": {"ray"}, "harold": {"hal", "harry"}, "henry": {"hank", "harry"},
    "leonard": {"len", "lenny"}, "walter": {"walt"}, "philip": {"phil"},
    "peter": {"pete"}, "douglas": {"doug"}, "russell": {"russ"},
    "bradley": {"brad"}, "cynthia": {"cindy"}, "barbara": {"barb"},
    "victoria": {"vicki", "vicky"}, "veronica": {"ronnie"},
    "kimberly": {"kim"}, "pamela": {"pam"}, "sandra": {"sandy"},
    "theresa": {"terry", "teri"}, "teresa": {"terry", "teri"},
}

SUFFIXES = {"jr", "sr", "ii", "iii", "iv", "v", "phd", "md", "cpa", "esq"}

SMART_PUNCT = str.maketrans({
    "\u2019": "'", "\u2018": "'", "\u02bc": "'",   # curly apostrophes
    "\u201c": '"', "\u201d": '"',
    "\u2010": "-", "\u2011": "-", "\u2012": "-",
    "\u2013": "-", "\u2014": "-",
})

def normalize_name(raw: str) -> list[str]:
    """-> ordered list of lowercase name tokens, suffixes and initials dropped."""
    # Typographic punctuation first. Filings set apostrophes as U+2019, and a
    # curly one falls outside the allowed characters below and becomes a
    # SPACE -- so Gilead's "Daniel P. O\u2019Day" tokenised as ["o", "day"]
    # while the certification's straight-quoted "O'Day" gave ["oday"], and
    # the CEO was never found in his own ownership table.
    name = (raw or "").translate(SMART_PUNCT)
    # Accents next, and for exactly the same reason as the punctuation above.
    # A letter outside A-Za-z becomes a SPACE, so "Stephane" and "Stephane"
    # written with an acute accent tokenise as ["stephane"] and ["st",
    # "phane"] -- 0.50, below the 0.7 threshold -- and Moderna's CEO was not
    # found in his own ownership table. "Carol Tome" with an accent lost its
    # final letter entirely, becoming ["carol", "tom"], and EDGAR's
    # "TOME CAROL B" scored 0.00 against it.
    #
    # Decomposing to NFKD splits an accented letter into the plain letter
    # plus a combining mark, and the combining marks are then dropped -- so
    # the accented and unaccented spellings converge instead of diverging.
    # Filers and EDGAR disagree about accents constantly: EDGAR's own indexes
    # are ASCII, while proxies typeset names properly.
    name = "".join(c for c in unicodedata.normalize("NFKD", name)
                   if not unicodedata.combining(c))
    name = re.sub(r"\([^)]*\)", " ", name)
    name = re.sub(r"[^A-Za-z,\s'\-]", " ", name)
    if "," in name:  # "Iger, Robert A." -> "Robert A. Iger"
        last, _, rest = name.partition(",")
        name = f"{rest} {last}"
    # Apostrophes are removed, not merely trimmed: EDGAR writes "DAmaro
    # Joshua W" while the certification says "Josh D'Amaro", and an internal
    # apostrophe made those different tokens. Same for O'Brien, O'Leary.
    tokens = [t.strip(".'-").replace("'", "").lower() for t in name.split()]
    # Single letters are KEPT. Proxy tables routinely abbreviate given names
    # to an initial -- Johnson & Johnson lists "J. Duato" for Joaquin Duato --
    # and dropping the initial collapsed the name to a lone surname, which
    # scored 0.60 and fell just under the 0.70 accept threshold. Five
    # companies failed that way, including J&J and GE.
    return [t for t in tokens if t and t not in SUFFIXES]

def _interpretations(tokens: list[str]) -> list[tuple[str, str]]:
    """Candidate (given_name, surname) readings of a token list.

    The two sources disagree on convention: proxies write "Ron M. Vachris"
    (surname last) while EDGAR's rptOwnerName writes "Vachris Roland Michael"
    -- surname FIRST, no comma, and the given name in the MIDDLE. An earlier
    version only paired the first and last tokens, so it read that as
    given="Michael" and never tried "Roland". Every three-token EDGAR name
    was silently unmatchable.

    So: fix each end as the surname in turn, and allow any other token to be
    the given name. The surname must still match exactly, which keeps this
    from collapsing distinct people together.
    """
    if not tokens:
        return []
    if len(tokens) == 1:
        return [(tokens[0], tokens[0])]
    out = []
    for g in tokens[:-1]:          # surname last  (proxy convention)
        out.append((g, tokens[-1]))
    for g in tokens[1:]:           # surname first (EDGAR convention)
        out.append((g, tokens[0]))
    return out

def _score_pair(fa: str, fb: str) -> float:
    """Confidence that two given names are the same person."""
    if fa == fb:
        return 1.0
    if fb in NICKNAMES.get(fa, set()) or fa in NICKNAMES.get(fb, set()):
        return 0.9
    # Diminutive by truncation: Ron/Roland, Tim/Timothy, Chris/Christopher,
    # Dan/Daniel, Greg/Gregory, Jeff/Jeffrey. Generalises past any fixed list.
    short, long_ = sorted((fa, fb), key=len)
    if len(short) >= 3 and long_.startswith(short):
        return 0.85
    # A bare initial, e.g. "R. Vachris" vs "Roland".
    if len(fa) == 1 or len(fb) == 1:
        return 0.75 if fa[0] == fb[0] else 0.0
    # Two different full names sharing a letter is weak -- deliberately below
    # the 0.7 accept threshold, so it surfaces as a near miss instead of a
    # false positive between, say, John and Jane Smith.
    return 0.5 if fa[0] == fb[0] else 0.0

def names_match(a: str, b: str) -> float:
    """0.0-1.0 confidence that two name strings refer to the same person.

    Both the surname and the given name must agree under some reading. That
    keeps family members at the same company from colliding, which matters --
    founder-controlled firms frequently have several relatives in the table.
    """
    ta = join_name_prefix(normalize_name(a))
    tb = join_name_prefix(normalize_name(b))
    if not ta or not tb:
        return 0.0
    if len(ta) == 1 or len(tb) == 1:
        # Genuinely only one usable token -- a surname alone. It can support
        # the match but cannot confirm it, so this stays below the threshold.
        lone = ta[0] if len(ta) == 1 else tb[0]
        other = tb if len(ta) == 1 else ta
        return 0.6 if lone in other else 0.0

    best = 0.0
    for given_a, sur_a in _interpretations(ta):
        for given_b, sur_b in _interpretations(tb):
            if sur_a != sur_b:
                continue
            best = max(best, _score_pair(given_a, given_b))
    return best


# A plain chief-executive title has nothing left once the words that make it
# one are removed. "CEO Microsoft Commercial" leaves "microsoft commercial";
# "EVP; CEO State Street Int'l" leaves "evp state street intl". Both are
# scoped roles, and v1 picked exactly those over the real chief executive.
_TITLE_NOISE = {"chief", "executive", "officer", "ceo", "and", "the", "of",
                "president", "chairman", "chair", "co", "founder", "cofounder",
                "interim", "principal", "acting"}


def is_plain_ceo_title(title: str) -> bool:
    """Is this THE chief executive, rather than a chief executive of some part?"""
    t = re.sub(r"[^a-z ]", " ", (title or "").lower())
    words = [w for w in t.split() if w]
    if not words:
        return False
    if not ({"ceo"} & set(words) or ("chief" in words and "executive" in words)):
        return False
    return not [w for w in words if w not in _TITLE_NOISE]


# EDGAR is inconsistent about the apostrophe in Irish and French surnames:
# "O'Hanley" is sometimes written "O HANLEY", which splits one surname into
# two tokens and makes State Street's chief executive unmatchable against his
# own certification. Only a LEADING single letter is joined, because EDGAR
# writes surname first -- a trailing "L" in "RICHARDS MICHAEL L" is a middle
# initial and joining it would invent a name.
_PREFIX = {"o", "d", "l"}


def join_name_prefix(tokens: list[str]) -> list[str]:
    if len(tokens) >= 2 and len(tokens[0]) == 1 and tokens[0] in _PREFIX:
        return [tokens[0] + tokens[1]] + list(tokens[2:])
    return list(tokens)


def token_overlap(a: str, b: str) -> float:
    """Shared name parts, over the shorter name.

    "Ravi Kumar S" and "Singisetti Ravi Kumar" share two of three. A
    certification often gives a working name where EDGAR holds the legal one,
    and the surname itself can be the part that differs.
    """
    ta = set(join_name_prefix(normalize_name(a)))
    tb = set(join_name_prefix(normalize_name(b)))
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / min(len(ta), len(tb))
