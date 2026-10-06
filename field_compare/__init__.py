"""Check the RBHQ fields against the fields published on thedogs.com.au.

    from field_compare import compare_cards

    report = compare_cards(reference_card, our_card)
    if report.critical:
        ...

A race is correct when every box holds the same greyhound on both sides.
"""

from __future__ import annotations

from .matcher import match_cards, match_races, match_runners
from .models import ComparisonReport, Discrepancy, Severity
from .report import print_report, write_report
from .rules import compare_cards

__version__ = "0.1.0"

__all__ = [
    "compare_cards", "ComparisonReport", "Discrepancy", "Severity",
    "match_cards", "match_races", "match_runners",
    "write_report", "print_report",
]
