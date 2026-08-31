"""Founder Led Equities, v2.

What a chief executive owns of the company they run, from structured filings
only. Two sources, both XBRL or XML, neither prose:

    numerator     Form 3/4/5 -- the balance each line holds, per the filer
    denominator   dei:EntityCommonStockSharesOutstanding -- the cover page

v1 read the proxy statement, which mandates content but not format, and so
needed a model, table-location heuristics, denominator corroboration and a
verification worksheet. None of that survives here. What does survive is the
Section 302 certification for identity, and the name matching, because both
were right and neither depended on the proxy.
"""
__version__ = "2.0.0"
