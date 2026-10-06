"""Writing the report out: a JSON file for an agent, a summary for a human."""

from __future__ import annotations

import json
from pathlib import Path

from dogs_scraper.utils.logging import get_logger

from .models import ComparisonReport, Severity

log = get_logger("compare.report")

ICON = {Severity.CRITICAL: "!!", Severity.WARNING: " !", Severity.INFO: "  "}


def write_report(report: ComparisonReport, output_dir: Path, pretty: bool = True,
                 filename: str | None = None) -> Path:
    """`filename` overrides the greyhound default (discrepancies_{date}.json)."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / (filename or f"discrepancies_{report.meeting_date}.json")
    path.write_text(
        json.dumps(report.to_dict(), indent=2 if pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )
    counts = report.counts()
    log.info("wrote %s (%d critical, %d warning, %d info)", path.name,
             counts["critical"], counts["warning"], counts["info"])
    return path


def print_report(report: ComparisonReport, limit: int = 40) -> None:
    counts = report.counts()
    print()
    print(f"  Field comparison - {report.meeting_date}")
    print(f"  reference : {report.reference_source}")
    print(f"  ours      : {report.our_source}")
    print(f"  matched   : {report.stats.get('meetings_matched', 0)} meetings, "
          f"{report.stats.get('races_compared', 0)} races, "
          f"{report.stats.get('runners_compared', 0)} runners "
          f"(on {report.stats.get('matched_on', 'runner name')})")
    print()

    if not report.discrepancies:
        print("  No differences found. Our fields match the published fields.")
        print()
        return

    print(f"  {counts['critical']} critical   {counts['warning']} warning   "
          f"{counts['info']} info")
    print("  " + "-" * 68)
    for d in report.sorted()[:limit]:
        print(f"  {ICON[d.severity]} {d.message}")

    remaining = len(report.discrepancies) - limit
    if remaining > 0:
        print(f"     ... and {remaining} more (see the JSON report)")

    unmatched = report.stats.get("unmatched") or {}
    if unmatched.get("reference_only") or unmatched.get("ours_only"):
        print()
        print("  Unmatched tracks - add these to the track alias file if they are")
        print("  the same venue:")
        for m in unmatched.get("reference_only", []):
            print(f"     reference only : {m['track']}  ({m['slug']})")
        for m in unmatched.get("ours_only", []):
            print(f"     ours only      : {m['track']}  ({m['slug']})")
    print()
