"""Flat runner-level CSV - one row per greyhound, easy to eyeball or pivot."""

from __future__ import annotations

import csv
from pathlib import Path

from ..models import DayCard
from ..utils.logging import get_logger
from ..utils.text import normalise_dog_name

log = get_logger("exporters.csv")

COLUMNS = [
    "meeting_date",
    "state",
    "track",
    "track_slug",
    "race_number",
    "race_name",
    "distance_m",
    "grade",
    "start_time_local",
    "field_size",
    "box",
    "dog_name",
    "dog_name_normalised",
    "trainer",
    "weight_kg",
    "form",
    "best_time",
    "odds",
    "scratched",
    "race_url",
]


def write_csv(card: DayCard, output_dir: Path, prefix: str = "thedogs") -> Path:
    """`prefix` names the source - see write_json."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"{prefix}_{card.meeting_date}_runners.csv"

    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=COLUMNS)
        writer.writeheader()
        rows = 0
        for meeting in card.meetings:
            for race in meeting.races:
                for runner in race.runners:
                    writer.writerow({
                        "meeting_date": meeting.meeting_date,
                        "state": meeting.state,
                        "track": meeting.track,
                        "track_slug": meeting.track_slug,
                        "race_number": race.race_number,
                        "race_name": race.name,
                        "distance_m": race.distance_m,
                        "grade": race.grade,
                        "start_time_local": race.start_time_local,
                        "field_size": race.field_size,
                        "box": runner.box,
                        "dog_name": runner.name,
                        "dog_name_normalised": normalise_dog_name(runner.name),
                        "trainer": runner.trainer,
                        "weight_kg": runner.weight_kg,
                        "form": runner.form,
                        "best_time": runner.best_time,
                        "odds": runner.odds,
                        "scratched": runner.scratched,
                        "race_url": race.url,
                    })
                    rows += 1

    log.info("wrote %s (%d rows)", path.name, rows)
    return path
