"""CSV and JSON output: data/harness/{date}/fields.{csv,json}, one row per runner."""

from __future__ import annotations

import csv
import json
from pathlib import Path

from .logging import get_logger
from .models import COLUMNS, DayCard

log = get_logger("exporters")


def _dir(output_root: Path, card: DayCard) -> Path:
    out = Path(output_root) / card.meeting_date
    out.mkdir(parents=True, exist_ok=True)
    return out


def write_csv(card: DayCard, output_root: Path, name: str = "fields") -> Path:
    """`name` lets a second source (e.g. the RBHQ feed) sit beside fields.csv."""
    path = _dir(output_root, card) / f"{name}.csv"
    rows = card.rows()
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    log.info("wrote %s (%d rows)", path, len(rows))
    return path


def write_json(card: DayCard, output_root: Path, pretty: bool = True, name: str = "fields") -> Path:
    path = _dir(output_root, card) / f"{name}.json"
    path.write_text(
        json.dumps(card.to_dict(), indent=2 if pretty else None, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("wrote %s (%d runners)", path, card.total_runners)
    return path
