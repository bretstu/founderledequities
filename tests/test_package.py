"""Structural checks, because the code was moved here mechanically.

Carrying v1's modules across by walking the syntax tree lost a decorator: an
AST node's line number points at `class`, not at the `@dataclass` above it.
So CertificationPeo arrived as a plain class with annotations, and every one
of five hundred companies failed with "takes no arguments" -- a whole panel
run, wasted on a one-line omission that no unit test was looking for.
"""
import ast
import importlib
import pkgutil
from pathlib import Path

import fle

ROOT = Path(fle.__file__).parent


def test_every_module_imports():
    for mod in pkgutil.iter_modules([str(ROOT)]):
        importlib.import_module(f"fle.{mod.name}")


def test_no_class_with_annotations_lost_its_decorator():
    """The exact failure. A class carrying only annotated fields and no
    decorator is a dataclass that stopped being one."""
    offenders = []
    for path in ROOT.glob("*.py"):
        for node in ast.parse(path.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.ClassDef) or node.decorator_list:
                continue
            annotated = [b for b in node.body if isinstance(b, ast.AnnAssign)]
            methods = [b for b in node.body
                       if isinstance(b, (ast.FunctionDef, ast.AsyncFunctionDef))]
            if annotated and not any(m.name == "__init__" for m in methods):
                offenders.append(f"{path.name}:{node.name}")
    assert not offenders, f"undecorated dataclasses: {offenders}"


def test_the_dataclasses_actually_construct():
    """Importing proves nothing -- the broken class imported fine."""
    from fle.identity import CertificationPeo
    from fle.ledger import Line, Ledger
    from fle.outstanding import Outstanding
    from fle.ownership import Ownership
    from fle.universe import Member

    assert CertificationPeo(name="Satya Nadella", form="10-Q",
                            filing_date="2026-07-23", period_end="2026-06-30",
                            accession="a", exhibit="e", exhibit_type="EX-31.1").name
    assert Line("Common Stock", "D", None, "", "", 0.0, True, 1.0).security
    assert Ledger().total == 0
    assert Outstanding().ok is False
    assert Ownership(cik=1).as_dict()["cik"] == 1
    assert Member(1, "T", "C").ticker == "T"


def test_nothing_still_imports_from_v1():
    for path in ROOT.glob("*.py"):
        src = path.read_text(encoding="utf-8")
        assert "ceo_ownership" not in src, path.name
