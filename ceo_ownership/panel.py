"""Batch panel builder: run the pipeline across a universe, resumably.

A 5,000-company run takes hours and will be interrupted -- a dropped
connection, a laptop lid, a keyboard interrupt. Losing that work is the
difference between a dataset you can build and one you keep almost building.

So results are appended to a JSONL file as each company completes, and a
restart reads that file, skips what is already done, and continues. Crash on
company 3,412 and you resume at 3,412.

Design choices worth knowing:

  * JSONL, not JSON. One line per company, flushed immediately. A partial
    file is still valid up to the last complete line, so a hard kill costs at
    most one row.
  * Failures are recorded, not skipped. A company that errors is a result --
    it has a reason, and reasons are what tell you where the remaining work
    is. Skipping them would mean re-fetching them on every restart forever.
  * NOTHING IS EXCLUDED BY DEFAULT. Roughly a fifth of DEF 14A filers look
    like closed-end funds and ETF trusts, and skipping them would save hours
    -- but the test for "not an operating company" rests partly on the
    ABSENCE of a 10-K, and absence has too many innocent causes: a company
    that filed a proxy before its first annual report, older 10-KSB filers,
    Reg A+ issuers, or a partial filing history from a failed page fetch.
    Excluding an equity by mistake is far worse than carrying a fund through
    to a clean error, so classification is recorded as a flag and the
    decision is left to whoever builds the universe. Opt in with
    --skip-funds once you have satisfied yourself it is safe.
"""
from __future__ import annotations

import json
import os
import signal
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

from .edgar import EdgarClient
from .pipeline import build_record, OwnershipRecord


@dataclass
class PanelProgress:
    total: int = 0
    done: int = 0
    resumed: int = 0
    ok: int = 0
    errored: int = 0
    started: float = field(default_factory=time.monotonic)

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def eta_seconds(self) -> float | None:
        fresh = self.done - self.resumed
        if fresh <= 0:
            return None
        rate = self.elapsed / fresh
        return rate * (self.total - self.done)

    def line(self) -> str:
        eta = self.eta_seconds()
        eta_txt = "--:--" if eta is None else _hms(eta)
        return (
            f"[{self.done}/{self.total}] ok={self.ok} err={self.errored} "
            f"elapsed={_hms(self.elapsed)} eta={eta_txt}"
        )


def _hms(seconds: float) -> str:
    s = int(seconds)
    return f"{s // 3600:d}:{(s % 3600) // 60:02d}:{s % 60:02d}"


# --------------------------------------------------------------- checkpoint


def load_completed(path: str) -> dict[int, dict]:
    """Read the checkpoint file. Tolerates a truncated final line."""
    done: dict[int, dict] = {}
    if not os.path.exists(path):
        return done
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                # Killed mid-write. Everything before this point is intact.
                break
            if rec.get("cik"):
                done[int(rec["cik"])] = rec
    return done


def append_record(path: str, record: dict) -> None:
    """Append one result and flush, so a kill costs at most this row."""
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, default=str) + "\n")
        fh.flush()
        os.fsync(fh.fileno())


# ------------------------------------------------------------------ filter


def classify_filer(client: EdgarClient, cik: int) -> tuple[str, str]:
    """-> (classification, evidence). Never decides anything by itself.

    "operating" and "foreign_private_issuer" rest on the PRESENCE of a
    mandated filing, which is sound. "investment_company" rests on presence
    too. Only "unknown" rests on absence -- and absence is not evidence of
    anything, so it is reported as unknown rather than as exclusion.
    """
    try:
        subs = client.submissions(cik)
    except Exception as exc:  # noqa: BLE001
        return "unknown", f"could not check ({exc})"

    forms = {f.get("form") for f in subs.get("_filings", [])}

    # Checked FIRST, deliberately: a business development company files both
    # a 10-K and N-2, and it has a real chief executive. Testing the fund
    # forms first would misclassify every BDC.
    if forms & {"10-K", "10-Q", "10-K/A", "10-Q/A", "10-KSB", "10-QSB"}:
        return "operating", "files 10-K/10-Q"
    # Foreign private issuers file 20-F or 40-F instead of a 10-K. Treating
    # the absence of a 10-K as disqualifying would drop every ADR.
    if forms & {"20-F", "40-F", "20-F/A", "40-F/A"}:
        return "foreign_private_issuer", "files 20-F/40-F"
    if forms & {"N-CSR", "N-CSRS", "N-CEN", "N-PORT", "N-1A", "N-2"}:
        return "investment_company", "files N-CSR/N-CEN"
    # No positive evidence either way. Could be a company that filed a proxy
    # before its first annual report, a Reg A+ issuer, or a truncated filing
    # history. Not a basis for exclusion.
    return "unknown", "no recognised periodic report found"


# -------------------------------------------------------------------- main


def build_panel(
    ciks: list[int],
    checkpoint: str,
    user_agent: str | None = None,
    as_of: str | None = None,
    llm_mode: str = "never",
    model: str | None = None,
    continuity: bool = True,
    with_form4: bool = False,
    skip_non_operating: bool = False,
    progress_every: int = 10,
    on_progress=None,
) -> PanelProgress:
    """Run the pipeline over `ciks`, appending to `checkpoint` as it goes."""
    client = EdgarClient(user_agent=user_agent)
    completed = load_completed(checkpoint)

    todo = [c for c in ciks if c not in completed]
    prog = PanelProgress(
        total=len(ciks), done=len(ciks) - len(todo), resumed=len(ciks) - len(todo)
    )
    for rec in completed.values():
        if rec.get("error"):
            prog.errored += 1
        else:
            prog.ok += 1

    if prog.resumed:
        print(f"Resuming: {prog.resumed} already done, {len(todo)} to go.")

    stopping = {"now": False}

    def _handle_sigint(signum, frame):  # noqa: ARG001
        # First Ctrl-C finishes the company in flight and exits cleanly, so
        # the checkpoint is never left mid-write.
        if stopping["now"]:
            raise KeyboardInterrupt
        stopping["now"] = True
        print("\nStopping after this company. Ctrl-C again to force.")

    try:
        signal.signal(signal.SIGINT, _handle_sigint)
    except Exception:  # noqa: BLE001
        pass  # not available on every platform/thread

    for cik in todo:
        if stopping["now"]:
            break

        record: dict
        # Classification is always recorded. It only causes a SKIP when the
        # caller has explicitly opted in, and never for "unknown".
        kind, why = classify_filer(client, cik)
        if skip_non_operating and kind == "investment_company":
            record = OwnershipRecord(
                cik=cik, ticker=None, company=None, ceo_name=None,
                ceo_source=None, confidence="LOW",
                error=f"skipped by --skip-funds: {why}",
                flags=[f"filer_kind:{kind}", "prefilter_skipped"],
            ).as_dict()
            append_record(checkpoint, record)
            prog.done += 1
            prog.errored += 1
            continue

        try:
            rec = build_record(
                client, cik, as_of=as_of, model=model, llm_mode=llm_mode,
                with_form4=with_form4, continuity=continuity,
            )
            record = rec.as_dict()
            record.setdefault("flags", []).append(f"filer_kind:{kind}")
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            record = OwnershipRecord(
                cik=cik, ticker=None, company=None, ceo_name=None,
                ceo_source=None, confidence="LOW",
                error=f"unhandled: {type(exc).__name__}: {exc}",
            ).as_dict()

        record["_processed_at"] = datetime.now(timezone.utc).isoformat()
        append_record(checkpoint, record)

        prog.done += 1
        if record.get("error"):
            prog.errored += 1
        else:
            prog.ok += 1

        if on_progress:
            on_progress(prog, record)
        elif prog.done % progress_every == 0:
            print("  " + prog.line())

    print("  " + prog.line())
    return prog


def panel_records(checkpoint: str) -> list[dict]:
    """All results from a checkpoint file, newest entry per CIK."""
    return list(load_completed(checkpoint).values())
