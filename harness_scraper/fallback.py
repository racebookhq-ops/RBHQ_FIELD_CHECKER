"""Fallback: read a race from the rendered page text when the JSON was not captured.

The page has no <table> and its class names are generated and unstable, so
nothing here touches CSS classes. The visible text is flattened into a token
list and the runner grid is located by its header labels:

    No.  Form  Horse  Trainer  Driver  Class  Hcp  Odds

Each runner then follows in that order. Observed quirks (6 Oct 2026):

* horse names are upper-cased ("DRAGON"), handicaps too ("10M") - compare
  case-insensitively against the JSON mapper's output;
* a small status token (ODS, RODS, ODM) can sit between the horse and trainer;
* a scratched runner shows "SCRATCHED" in the Driver slot and "SCR" as odds;
* the Odds column is the API's `woo_average_odds`.

NOT covered by a fixture yet: a runner with no form, or a blank trainer/driver
cell. Those would shift the columns; the parser re-syncs on the next saddlecloth
but may drop that runner - check the log line it emits.

The start time is left empty: the page shows a clock time with no stated zone
(see _race_header), and guessing would be worse than a gap.
"""

from __future__ import annotations

import re

from .logging import get_logger
from .models import Race, Runner

log = get_logger("fallback")

GRID_HEADER = ["no.", "form", "horse", "trainer", "driver", "class", "hcp", "odds"]

_FORM_RE = re.compile(r"^[0-9a-z]{1,5}$")                  # lower-case: horse names are upper-case
_STATUS_RE = re.compile(r"^R?OD[A-Z]?$")                   # ODS, RODS, ODM ...
_ODDS_RE = re.compile(r"^(\d+\.\d+|SCR)$")
_CLAIM_RE = re.compile(r"^(?P<name>.*?)\s*(?P<claim>\([^)]*\))$")
_INFO_RE = re.compile(r"^\$(?P<prize>[\d,]+(?:\.\d+)?)\s+(?P<text>.*?)\s*(?:(?P<start>Mobile|Standing) Start)?$", re.I)
_DIST_RE = re.compile(r"^(\d+)\s*m$", re.I)


class FallbackError(ValueError):
    """The rendered text did not have the shape the fallback expects."""


def rendered_tokens(html: str) -> list[str]:
    """Visible text of the page as a flat list of non-empty strings."""
    from scrapling import Selector

    page = Selector(content=html)
    parts = page.css("body *:not(script):not(style)::text").getall()
    return [t.strip() for t in parts if t and t.strip()]


def _find_grid(tokens: list[str]) -> int:
    n = len(GRID_HEADER)
    lowered = [t.lower() for t in tokens]
    for i in range(len(tokens) - n + 1):
        if lowered[i:i + n] == GRID_HEADER:
            return i
    raise FallbackError("runner grid header (No. Form Horse Trainer Driver Class Hcp Odds) not found")


def _race_header(tokens: list[str], grid_at: int, race: Race) -> None:
    """Best-effort race fields from the tokens just above the grid."""
    head = tokens[:grid_at]
    info_at = next((i for i in range(len(head) - 1, -1, -1) if head[i].startswith("$")), None)
    if info_at is None:
        return
    if m := _INFO_RE.match(head[info_at]):
        race.prizemoney = float(m["prize"].replace(",", "")) if "." in m["prize"] else int(m["prize"].replace(",", ""))
        race.class_text = m["text"] or None
        race.start_type = m["start"].lower() if m["start"] else None
    if info_at >= 1:
        race.name = head[info_at - 1]
    # "Track Record:" HORSE 1:55.5 2647m
    for i, t in enumerate(head):
        if t.lower().startswith("track record") and i + 3 < len(head) + 1:
            horse, time_ = head[i + 1], head[i + 2] if i + 2 < len(head) else None
            dist = head[i + 3] if i + 3 < len(head) else None
            race.track_record_horse = horse
            race.track_record_time = time_
            if dist and (dm := _DIST_RE.match(dist)):
                race.track_record_distance_m = int(dm.group(1))
            # bet types are the token after the record, just above the grid
            tail = head[i + 4:]
            race.bet_types = tail[-1] if tail else None
            break
    # race number is the lone digit token before the clock time above the name
    for t in reversed(head[:max(info_at - 1, 0)]):
        if t.isdigit():
            race.race_no = int(t)
            break


def _parse_runner(tokens: list[str], i: int) -> tuple[Runner | None, int]:
    """Parse one runner starting at tokens[i] (its saddlecloth). Returns (runner, next index)."""
    start = i
    runner = Runner(saddlecloth=int(tokens[i]))
    i += 1
    if i < len(tokens) and _FORM_RE.match(tokens[i]):
        runner.form = tokens[i]
        i += 1
    if i >= len(tokens):
        return None, start + 1
    runner.horse = tokens[i]
    i += 1
    while i < len(tokens) and _STATUS_RE.match(tokens[i]):
        i += 1
    if i + 3 >= len(tokens):
        return None, start + 1
    runner.trainer = tokens[i]
    driver = tokens[i + 1]
    runner.class_rating = tokens[i + 2]
    runner.handicap = tokens[i + 3]
    i += 4

    if driver.upper() == "SCRATCHED":
        runner.scratched = True
        runner.driver = None
    elif m := _CLAIM_RE.match(driver):
        runner.driver, runner.driver_claim = m["name"], m["claim"]
    else:
        runner.driver = driver

    if i < len(tokens) and _ODDS_RE.match(tokens[i]):
        if tokens[i] == "SCR":
            runner.scratched = True
        else:
            runner.odds = float(tokens[i])
        i += 1
    return runner, i


def parse_race_text(source: str | list[str], *, race_id: str | None = None,
                    race_no: int | None = None) -> Race:
    """Parse a rendered race page (HTML string) or its token list into a Race."""
    tokens = rendered_tokens(source) if isinstance(source, str) else source
    grid_at = _find_grid(tokens)

    race = Race(race_id=race_id, race_no=race_no, parsed_from="text")
    _race_header(tokens, grid_at, race)
    if race_no is not None:
        race.race_no = race_no

    i = grid_at + len(GRID_HEADER)
    while i < len(tokens) and tokens[i].isdigit():
        runner, nxt = _parse_runner(tokens, i)
        if runner is None:
            log.warning("could not parse the runner at token %d (%r)", i, tokens[i:i + 8])
            i = nxt
            continue
        race.runners.append(runner)
        i = nxt

    if not race.runners:
        raise FallbackError("runner grid found but no runners could be parsed")
    return race
