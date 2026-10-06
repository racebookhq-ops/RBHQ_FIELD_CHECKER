"""Turn a race page into a Race with its full field of Runners.

Two strategies, tried in order:

1. `parse_runner_rows`  - targeted selectors from selectors.py.
2. `parse_runner_table` - generic: read the <table> header row, map the
   columns onto Runner fields via COLUMN_ALIASES, then read each body row.

Strategy 2 is the safety net: it survives a class-name change because it keys
off the visible column headings instead.

Two things about this page are worth knowing before editing:

* The box number is not text anywhere on the page. It is the name of the rug
  graphic in the first cell, `<sprite-svg name="rug_4">`.
* A box with no dog in it is a row-level state, `tr.race-runner--scratched`,
  whose name cell reads "Vacant Box". Those come back as a Runner with the
  box set, `name=None` and `scratched=True`, so an empty box 3 stays visible
  to a consumer rather than going missing from the field.
"""

from __future__ import annotations

import re
from datetime import date as _date, datetime, timezone

from ..models import Race, Runner
from ..utils.dates import RACING_TZ, combine_local
from ..utils.logging import get_logger
from ..utils.text import clean, distance_m, to_float, to_int
from . import selectors as S
from ._common import absolute, has_any, node_text, try_selectors, try_selectors_all

log = get_logger("parsers.race")

SCRATCH_RE = re.compile(r"\bscratch(ed|ing)?\b", re.I)
GRADE_RE = re.compile(r"\b(maiden|grade\s*\d|group\s*\d|free for all|ffa|mixed \d/\d|novice|restricted)\b", re.I)
RUG_RE = re.compile(r"rug[_\-]?(\d+)", re.I)
# The site annotates a promoted reserve two ways - "(from box 5)" and
# "(into box 6)" - both naming the box the dog actually runs from.
FROM_BOX_RE = re.compile(r"(?:from|into)\s+box\s+(\d+)", re.I)

#: Greyhounds race from eight boxes; 9 and 10 are reserve rugs. A runner still
#: wearing one has not been promoted into the field proper.
MAX_BOX = 8


def parse_race_page(page, race: Race, meeting_date: _date, base_url: str) -> Race:
    """Populate `race` in place from its own page and return it."""
    _parse_header(page, race, meeting_date)

    runners = _parse_runner_rows(page, base_url)
    if not runners:
        runners = _parse_runner_table(page, base_url)

    race.runners = runners
    if not runners:
        log.warning("no runners parsed for %s", race.url)
    else:
        log.debug("race %s: %d runners (%d vacant)", race.race_number,
                  len(runners), sum(1 for r in runners if r.scratched))
    return race


# --------------------------------------------------------------------------
# header
# --------------------------------------------------------------------------
def _parse_header(page, race: Race, meeting_date: _date) -> None:
    title = try_selectors(page, S.RACE_TITLE)
    if title:
        race.name = race.name or clean(re.sub(r"^R?\d+\s*[-–]\s*", "", title))

    # "Maiden 342m" carries the grade and the distance in one string.
    grade_distance = try_selectors(page, S.RACE_GRADE_DISTANCE)

    race.distance_m = race.distance_m or distance_m(
        grade_distance or try_selectors(page, S.RACE_DISTANCE) or title
    )

    grade = grade_distance or try_selectors(page, S.RACE_GRADE)
    if grade:
        grade = clean(re.sub(r"\b\d{3,4}\s*m\b", "", grade, flags=re.I))
    if not grade:
        haystack = " ".join(filter(None, [title, race.name]))
        m = GRADE_RE.search(haystack or "")
        grade = m.group(0) if m else None
    race.grade = race.grade or clean(grade)

    race.start_time_local = race.start_time_local or _parse_start_time(page, meeting_date)

    race.prize_money = race.prize_money or try_selectors(page, S.RACE_PRIZE)
    race.track_condition = race.track_condition or try_selectors(page, S.MEETING_TRACK_CONDITION)
    race.comment = race.comment or try_selectors(page, S.RACE_COMMENT)


def _parse_start_time(page, meeting_date: _date) -> str | None:
    """Best available start time, most trustworthy source first.

    The page gives a full ISO string with offset on the race box, an epoch
    timestamp on the <formatted-time> element, and a rendered "11:48 02 Sep"
    as a last resort.
    """
    iso = try_selectors(page, S.RACE_START_ISO)
    if iso and "T" in iso:
        return iso

    epoch = to_int(try_selectors(page, S.RACE_START_EPOCH))
    if epoch:
        return datetime.fromtimestamp(epoch, tz=timezone.utc).astimezone(RACING_TZ).isoformat()

    raw_time = try_selectors(page, S.RACE_TIME)
    if raw_time:
        if "T" in raw_time and len(raw_time) >= 16:
            return raw_time
        time_part = clean(raw_time.split(",")[0])
        return combine_local(meeting_date, time_part or "")
    return None


# --------------------------------------------------------------------------
# strategy 1: targeted selectors
# --------------------------------------------------------------------------
def _parse_runner_rows(page, base_url: str) -> list[Runner]:
    rows = try_selectors_all(page, S.RUNNER_ROWS)
    runners: list[Runner] = []

    for row in rows:
        box = _parse_box(row)
        name = _parse_name(row)
        scratched = _is_scratched(row)
        vacant = _is_vacant(name)

        if not name and not vacant:
            continue                                    # header row or spacer
        if vacant:
            name = None                                 # an empty box holds no dog

        # Rugs above the eighth belong to reserves. One that got a start has
        # already been resolved to the box it runs from; anything still up here
        # is a reserve, kept because whether the dog is running is what matters
        # - the rug it wears does not.
        reserve = bool(box and box > MAX_BOX)

        runner = Runner(
            box=box,
            name=name,
            trainer=try_selectors(row, S.RUNNER_TRAINER),
            weight_kg=to_float(try_selectors(row, S.RUNNER_WEIGHT)),
            form=try_selectors(row, S.RUNNER_FORM),
            best_time=try_selectors(row, S.RUNNER_BEST_TIME),
            odds=to_float(try_selectors(row, S.RUNNER_ODDS)),
        )

        runner.dog_url = absolute(base_url, try_selectors(row, S.RUNNER_LINK))
        runner.scratched = scratched or vacant

        for key, candidates in (
            ("dog_id", S.RUNNER_DOG_ID),
            ("grade", S.RUNNER_GRADE),
            ("track_dist", S.RUNNER_TRACK_DIST),
            ("finish_position", S.RUNNER_FINISH),
        ):
            value = try_selectors(row, candidates)
            if value:
                runner.raw[key] = value
        if vacant:
            runner.raw["vacant"] = True
        if reserve:
            runner.raw["reserve"] = True

        runners.append(runner)

    return _dedupe(runners)


def _parse_box(row) -> int | None:
    """Box number, read off the rug graphic: <sprite-svg name="rug_4">.

    A reserve promoted into a scratching is rugged 9 or 10 but actually runs
    from the box it replaced, printed as "(from box 5)". That is the box bets
    are struck on, so it wins over the rug.
    """
    for block in try_selectors_all(row, S.RUNNER_FROM_BOX):
        m = FROM_BOX_RE.search(node_text(block) or "")
        if m:
            return int(m.group(1))

    sprite = try_selectors(row, S.RUNNER_BOX_SPRITE)
    if sprite:
        m = RUG_RE.search(sprite)
        if m:
            return int(m.group(1))
    return to_int(try_selectors(row, S.RUNNER_BOX))


def _parse_name(row) -> str | None:
    """Dog name, without the best-time span the site nests beside it.

    Linked on a race that has been run, a bare text node on an upcoming one.
    """
    name = try_selectors(row, S.RUNNER_NAME)
    if name:
        return name
    block = try_selectors_all(row, S.RUNNER_NAME_BLOCK)
    if block:
        # .text is the element's own text, excluding the nested spans.
        return clean(getattr(block[0], "text", None))
    return None


def _is_scratched(row) -> bool:
    """True when this runner is out - whether or not the box is empty.

    A scratched greyhound still has a name; only a genuinely empty box does
    not. Conflating the two loses the name of the dog that was taken out,
    which is exactly what a consumer needs to see.

    The regex is deliberately confined to the name cell: a runner's form or
    last-start cell can mention a scratching in another race, and reading the
    whole row would turn that into a phantom scratching.
    """
    classes = str(row.attrib.get("class", "") or "")
    if any(flag in classes for flag in S.RUNNER_SCRATCHED_ROW):
        return True
    if has_any(row, S.RUNNER_SCRATCHED):
        return True

    block = try_selectors_all(row, S.RUNNER_NAME_BLOCK)
    name_text = node_text(block[0]) if block else None
    return bool(SCRATCH_RE.search(name_text or ""))


def _is_vacant(name: str | None) -> bool:
    """True when the box holds no dog at all - the site prints "Vacant Box"."""
    return (name or "").strip().lower() == S.VACANT_BOX_TEXT


# --------------------------------------------------------------------------
# strategy 2: generic table, keyed off the visible column headings
# --------------------------------------------------------------------------
def _parse_runner_table(page, base_url: str) -> list[Runner]:
    for table in page.css("table"):
        headers = [(node_text(th) or "").lower() for th in table.css("th")]
        if not headers:
            continue

        mapping: dict[int, str] = {}
        for i, header in enumerate(headers):
            for alias, field_name in S.COLUMN_ALIASES.items():
                if header == alias or header.startswith(alias):
                    mapping[i] = field_name
                    break
        if "name" not in mapping.values():
            continue                                    # not the field table

        runners: list[Runner] = []
        for tr in table.css("tbody tr") or table.css("tr"):
            cells = tr.css("td")
            if not cells:
                continue
            runner = Runner()
            for i, cell in enumerate(cells):
                field_name = mapping.get(i)
                if not field_name:
                    continue
                value = node_text(cell)
                if field_name == "box":
                    runner.box = to_int(value)
                elif field_name == "name":
                    runner.name = value
                    runner.dog_url = absolute(
                        base_url, cell.css("a::attr(href)").extract_first())
                elif field_name == "trainer":
                    runner.trainer = value
                elif field_name == "weight_kg":
                    runner.weight_kg = to_float(value)
                elif field_name == "odds":
                    runner.odds = to_float(value)
                else:
                    setattr(runner, field_name, value)

            if runner.box is None:
                runner.box = _parse_box(tr)

            vacant = _is_vacant(runner.name)
            if not runner.name and not vacant:
                continue
            runner.scratched = _is_scratched(tr) or vacant
            if vacant:
                runner.name = None
                runner.raw["vacant"] = True
            runners.append(runner)

        if runners:
            log.debug("parsed %d runners via generic table fallback", len(runners))
            return _dedupe(runners)

    return []


def _one_per_box(runners: list[Runner]) -> list[Runner]:
    """Collapse a box that lists both a scratching and its replacement.

    When a reserve is promoted the site shows two rows for the same box: the
    dog that came out, and the one that went in. A card has one dog per box, so
    the live one wins and the other is kept under `raw.replaced` - the same
    rule the RBHQ mapper applies, which is what lets the two cards be compared
    box for box.
    """
    by_box: dict[int, list[Runner]] = {}
    ordered: list[Runner] = []
    for runner in runners:
        if runner.box is None:
            ordered.append(runner)
            continue
        by_box.setdefault(runner.box, []).append(runner)

    for box, entries in by_box.items():
        if len(entries) == 1:
            ordered.append(entries[0])
            continue
        live = [r for r in entries if not r.scratched]
        named = [r for r in entries if r.name]
        chosen = (live or named or entries)[0]
        chosen.raw["replaced"] = [
            {"name": r.name, "scratched": r.scratched}
            for r in entries if r is not chosen
        ]
        ordered.append(chosen)

    return ordered


def _dedupe(runners: list[Runner]) -> list[Runner]:
    """Drop repeated rows (mobile + desktop markup often duplicates the field)."""
    seen: set[tuple] = set()
    unique: list[Runner] = []
    for r in runners:
        key = ((r.name or "").lower(), r.box)
        if key in seen:
            continue
        seen.add(key)
        unique.append(r)

    unique = _one_per_box(unique)

    # If boxes are missing entirely, fall back to display order (1..n).
    if unique and all(r.box is None for r in unique):
        for i, r in enumerate(unique, start=1):
            r.box = i
            r.raw["box_inferred"] = True

    # Box order, not page order: a result page lists runners by finish, and a
    # consumer comparing box-by-box wants the same sequence every time.
    unique.sort(key=lambda r: (r.box is None, r.box or 0))
    return unique
