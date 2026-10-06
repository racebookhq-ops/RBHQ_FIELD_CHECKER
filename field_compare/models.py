"""The report an agent reads.

One record per difference, each carrying both sides' values so the reader can
act without going back to either source.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class Severity(str, Enum):
    """How much a difference matters to someone taking bets.

    CRITICAL  money is at risk right now - a bet could go on the wrong dog
    WARNING   the card is wrong but not yet dangerous
    INFO      data quality; worth knowing, not worth waking anyone
    """

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


#: Sort order for the report - the things worth acting on come first.
_RANK = {Severity.CRITICAL: 0, Severity.WARNING: 1, Severity.INFO: 2}


@dataclass
class Discrepancy:
    type: str                              # machine-readable, e.g. wrong_dog_in_box
    severity: Severity
    message: str                           # one line, readable as-is
    track: str | None = None
    race_number: int | None = None
    box: int | None = None
    field: str | None = None               # which attribute differs, when relevant
    reference: Any = None                  # what thedogs.com.au publishes
    ours: Any = None                       # what the RBHQ feed shows
    race_url: str | None = None
    start_time_local: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d = {
            "type": self.type,
            "severity": self.severity.value,
            "message": self.message,
            "track": self.track,
            "race_number": self.race_number,
            "box": self.box,
            "field": self.field,
            "reference": self.reference,
            "ours": self.ours,
            "race_url": self.race_url,
            "start_time_local": self.start_time_local,
        }
        # Drop the keys that do not apply to this kind of finding, so a record
        # is not mostly nulls.
        return {k: v for k, v in d.items() if v is not None}


@dataclass
class ComparisonReport:
    meeting_date: str
    generated_at: str
    reference_source: str = "thedogs.com.au"
    our_source: str = "rbhq-api"
    discrepancies: list[Discrepancy] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def add(self, d: Discrepancy) -> None:
        self.discrepancies.append(d)

    @property
    def critical(self) -> list[Discrepancy]:
        return [d for d in self.discrepancies if d.severity is Severity.CRITICAL]

    def counts(self) -> dict[str, int]:
        return {
            s.value: sum(1 for d in self.discrepancies if d.severity is s)
            for s in Severity
        }

    def sorted(self) -> list[Discrepancy]:
        """Criticals first, then by track, race and box - stable and readable."""
        return sorted(self.discrepancies, key=lambda d: (
            _RANK[d.severity],
            (d.track or "").lower(),
            d.race_number if d.race_number is not None else 0,
            d.box if d.box is not None else 0,
            d.type,
        ))

    def to_dict(self) -> dict[str, Any]:
        return {
            "meeting_date": self.meeting_date,
            "generated_at": self.generated_at,
            "reference_source": self.reference_source,
            "our_source": self.our_source,
            "summary": {**self.stats, "counts": self.counts()},
            "discrepancies": [d.to_dict() for d in self.sorted()],
        }
