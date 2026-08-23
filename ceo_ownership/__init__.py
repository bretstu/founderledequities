"""CEO ownership dataset pipeline (SEC EDGAR)."""
__version__ = "0.1.0"

from .edgar import EdgarClient
from .pipeline import build_record, run_tickers, OwnershipRecord

__all__ = ["EdgarClient", "build_record", "run_tickers", "OwnershipRecord"]
