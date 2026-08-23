"""Configuration for the CEO ownership pipeline."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


def _load_dotenv() -> None:
    """Read a .env file into the environment, if one exists.

    Looked for in the current working directory and in the project root
    (the parent of this package). Real environment variables always win, so
    a value set with `setx` or `$env:` overrides the file -- which is what
    you want when running in CI or a scheduled job.

    Deliberately hand-rolled rather than pulling in python-dotenv: it is
    fifteen lines and one fewer thing to install.
    """
    candidates = [Path.cwd() / ".env", Path(__file__).resolve().parent.parent / ".env"]
    for path in candidates:
        if not path.is_file():
            continue
        # "utf-8-sig" strips a byte-order mark if present. Windows
        # PowerShell 5.1's `Out-File -Encoding utf8` writes one, which would
        # otherwise turn the first key into "\ufeffOWNERSHIP_UA" and silently
        # drop it while every later line loaded fine.
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip().lstrip("\ufeff")
            value = value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value
        break


_load_dotenv()

SEC_BASE = "https://www.sec.gov"
SEC_DATA = "https://data.sec.gov"

# SEC fair-access policy: <=10 requests/second and a descriptive User-Agent
# containing a real contact address. Set OWNERSHIP_UA before running.
DEFAULT_USER_AGENT = os.environ.get(
    "OWNERSHIP_UA", "ceo-ownership-research contact@example.com"
)
MAX_REQUESTS_PER_SECOND = 8.0  # deliberately under the 10/s ceiling

# Proxy-type forms that can carry an Item 403 beneficial ownership table,
# in descending order of preference.
PROXY_FORMS = ["DEF 14A", "DEFR14A", "DEFM14A", "10-K/A", "10-K"]

# Forms that mark a company leaving the public universe. Used by the
# point-in-time universe builder to distinguish "died" from "still here".
EXIT_FORMS = {
    "25": "delisting_notice",
    "25-NSE": "delisting_notice_exchange",
    "15-12B": "deregistration",
    "15-12G": "deregistration",
    "15F-12B": "deregistration_fpi",
    "15F-12G": "deregistration_fpi",
}

# --------------------------------------------------------------------------
# THE METRIC
#
#   shares_13d3 = beneficial ownership as reported under Rule 13d-3 in the
#                 proxy's Item 403 table, divided by shares outstanding.
#
# Rule 13d-3 counts securities over which a person holds VOTING power or
# INVESTMENT power, plus anything they may acquire within 60 days. It is a
# single legal standard, so it means the same thing at every company -- which
# is exactly what "common shares owned" does not, because no filing reports
# that and every filer constructs it differently.
#
# INCLUDED: direct holdings; shares held through trusts or entities the person
#   controls; shares where voting or dispositive power is shared; options and
#   RSUs exercisable/vesting within 60 days; convertible classes; pledged
#   shares; 401(k) holdings.
# EXCLUDED: unvested awards outside 60 days; deferred units payable after
#   service ends; options not yet exercisable; phantom/cash-settled awards;
#   holdings of entities the person does not control.
#
# Known cost: underwater options count at face value, and voting power counts
# even without economic interest. `options_60d` is captured separately so the
# largest distortion can be subtracted when an economic view is wanted.
#
# Form 4 is NOT used by default: Section 16 reports under Rule 16a-1(a)(2)
# ("pecuniary interest"), a different legal test, so comparing the two was
# never like-for-like. Re-enable with --with-form4 to compare.
# --------------------------------------------------------------------------

# securityTitle values on Form 4 Table I that count as "common stock owned".
# Allowlist, not blocklist -- unknown titles are logged and EXCLUDED so the
# pipeline understates rather than silently contaminates.
COMMON_STOCK_PATTERNS = [
    r"^common stock$",
    r"^common shares?$",
    r"^class [a-z] common stock$",
    r"^class [a-z] ordinary shares?$",
    r"^ordinary shares?$",
    r"^common stock,? par value",
    r"^class [a-z] common stock,? par value",
    r"^voting common stock$",
    r"^non-?voting common stock$",
    # Alphabet calls its stock "Class C Capital Stock"; several issuers use
    # "capital stock" for what is plainly common equity. Treating these as
    # unknown silently dropped real ownership.
    r"^class [a-z] capital stock$",
    r"^capital stock$",
    r"^class [a-z] common stock \(.*\)$",
    r"^class [a-z] shares?$",
    r"^common stock class [a-z]$",
    # Walmart reports plain "Common". Treating it as unknown silently zeroed
    # every one of the CEO's eight holding lines.
    r"^common$",
    r"^common stock[,.]?$",
    r"^shares?$",
    r"^class [a-z]$",
    r"^ordinary$",
]

# Titles that look like common stock but are contingent compensation.
# Some filers wrongly report these in Table I; they must never be counted.
CONTINGENT_PATTERNS = [
    r"restricted stock unit",
    r"\brsu\b",
    r"performance (stock|share) unit",
    r"\bpsu\b",
    r"deferred stock unit",
    r"\bdsu\b",
    r"phantom",
    r"stock option",
    r"employee stock option",
    r"\bwarrant\b",
    r"restricted share unit",
    # Catch-all for company-branded equity awards: Alphabet's "Google Stock
    # Units", and any other "<Something> Stock Units". These are compensation,
    # not ownership.
    r"\bstock units?\b",
    r"\bshare units?\b",
]

# Up-C / exchangeable-unit markers. These are real economic ownership held in
# derivative form; we do NOT count them but we DO flag the company so the
# understatement is visible rather than silent.
UPC_PATTERNS = [
    r"(llc|limited liability company) units?",
    r"(lp|partnership) units?",
    r"exchangeable (units?|shares?)",
    r"common units?",
    r"operating partnership units?",
]


@dataclass
class Settings:
    user_agent: str = DEFAULT_USER_AGENT
    cache_dir: str = field(
        default_factory=lambda: os.environ.get("OWNERSHIP_CACHE", ".cache")
    )
    # Model used for ownership-table extraction. Override per-run if needed.
    extraction_model: str = os.environ.get("OWNERSHIP_MODEL", "claude-sonnet-5")
    anthropic_api_key: str | None = field(
        default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY")
    )
    # Tolerance (in percentage points) for the internal reconciliation check.
    pct_tolerance: float = 0.15
    # Max relative divergence between proxy and Form 4 share counts before the
    # record is downgraded from HIGH confidence.
    form4_divergence_tolerance: float = 0.05


SETTINGS = Settings()
