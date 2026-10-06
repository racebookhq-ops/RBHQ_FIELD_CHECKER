"""Nested JSON output - the file the comparison agent reads."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import DayCard
from ..utils.logging import get_logger

log = get_logger("exporters.json")


def write_json(card: DayCard, output_dir: Path, pretty: bool = True,
               prefix: str = "thedogs") -> Path:
    """`prefix` names the source, so a second scraper writing the same shape
    lands beside this one instead of overwriting it."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_{card.meeting_date}.json"

    payload = card.to_dict()
    path.write_text(
        json.dumps(payload, indent=2 if pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("wrote %s (%d meetings, %d races, %d runners)",
             path.name, len(card.meetings), card.total_races, card.total_runners)
    return path
