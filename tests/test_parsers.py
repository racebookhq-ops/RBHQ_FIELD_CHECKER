"""Selector tests, run against saved fixtures so they stay offline and fast.

Refresh the fixtures with tools/dump_html.py when the site changes:

    python tools/dump_html.py --day 2026-09-02 --name day_index.html
    python tools/dump_html.py --race angle-park 2026-09-02 1 <slug> --name race_page.html

`race_page.html` is an upcoming race (the field), `race_page_result.html` is
one that has already been run. The two use different markup for the dog name
and carry different columns, so both are worth keeping.
"""

from datetime import date

from dogs_scraper.models import Race
from dogs_scraper.parsers import parse_meeting_list, parse_race_page

BASE = "https://www.thedogs.com.au"


def test_day_index_yields_meetings(fixture_loader):
    page = fixture_loader("day_index.html")
    meetings = parse_meeting_list(page, "2026-09-02", BASE)
    assert meetings, "no meetings parsed from the day index"
    assert all(m.track_slug for m in meetings)
    assert all(m.url and m.url.startswith(BASE) for m in meetings)


def test_race_page_yields_a_full_field(fixture_loader):
    page = fixture_loader("race_page.html")
    race = parse_race_page(page, Race(race_number=1), date(2026, 9, 2), BASE)

    assert race.runners, "no runners parsed from the race page"
    assert 1 <= len(race.runners) <= 10
    # A vacant box is a Runner with a box but no dog, so only the live ones
    # are required to be named.
    assert all(r.name for r in race.runners if not r.scratched)

    boxes = [r.box for r in race.runners if r.box]
    assert len(boxes) == len(set(boxes)), "duplicate box numbers - check the dedupe logic"
    assert boxes == sorted(boxes), "runners should come back in box order"


def test_box_numbers_come_from_the_rug_graphic(fixture_loader):
    """The box is an attribute on a <sprite-svg>, not text - easy to regress."""
    page = fixture_loader("race_page.html")
    race = parse_race_page(page, Race(race_number=1), date(2026, 9, 2), BASE)

    assert all(r.box is not None for r in race.runners), "a runner is missing its box"
    assert not any(r.raw.get("box_inferred") for r in race.runners), \
        "boxes were inferred from row order - the rug selector stopped matching"


def test_vacant_boxes_are_kept_and_flagged(fixture_loader):
    """An empty box must survive as a scratching, not vanish from the field."""
    page = fixture_loader("race_page.html")
    race = parse_race_page(page, Race(race_number=1), date(2026, 9, 2), BASE)

    vacant = [r for r in race.runners if r.scratched]
    assert vacant, "fixture has two vacant boxes - none were detected"
    assert all(r.name is None for r in vacant), "a vacant box should hold no dog name"
    assert all(r.box for r in vacant), "a vacant box still has a box number"

    assert race.scratchings == sorted(r.box for r in vacant)
    assert race.field_size == len(race.runners) - len(vacant)


def test_race_header_fields(fixture_loader):
    page = fixture_loader("race_page.html")
    race = parse_race_page(page, Race(race_number=1), date(2026, 9, 2), BASE)

    assert race.distance_m and 200 <= race.distance_m <= 1000
    assert race.grade and "m" != race.grade.lower()
    # Distance must not be left glued onto the grade ("Maiden 342m").
    assert not any(ch.isdigit() for ch in race.grade)
    assert race.start_time_local and race.start_time_local.startswith("2026-09-02T")
    assert "+" in race.start_time_local, "start time should carry a UTC offset"


def test_result_page_still_parses(fixture_loader):
    """A race that has been run uses a linked dog name and extra columns."""
    page = fixture_loader("race_page_result.html")
    race = parse_race_page(page, Race(race_number=2), date(2026, 9, 1), BASE)

    assert race.runners, "no runners parsed from the result page"
    assert all(r.name for r in race.runners if not r.scratched)
    assert any(r.dog_url and "/dogs/" in r.dog_url for r in race.runners), \
        "the result page links each dog - none were captured"

    boxes = [r.box for r in race.runners if r.box]
    assert boxes == sorted(boxes), "runners should come back in box order"

def test_start_time_is_this_race_not_the_first_on_the_page():
    """A race page lists the whole meeting's race strip.

    Reading a bare `.race-box` gives race 1's time on every page, which shows up
    downstream as every race drifting by a different amount.
    """
    from scrapling import Selector

    page = Selector(content="""
      <div class="meeting-header__races">
        <a class="race-box" data-race-box="2026-09-02T11:48:00+10:00">R1</a>
        <a class="race-box" data-race-box="2026-09-02T12:09:00+10:00">R2</a>
        <a class="race-box race-box--active" data-race-box="2026-09-02T12:25:00+10:00">R3</a>
      </div>
      <div class="race-header">
        <div class="race-box race-box--large" data-race-box="2026-09-02T12:25:00+10:00">
          <div class="race-box__number">R3</div>
        </div>
        <div class="race-header__info__grade">Maiden 400m</div>
      </div>
      <table class="race-runners"><tbody>
        <tr class="race-runner">
          <td class="race-runners__box"><sprite-svg name="rug_1"></sprite-svg></td>
          <td class="race-runners__name"><div class="race-runners__name__dog">A Dog</div></td>
        </tr>
      </tbody></table>
    """)
    race = parse_race_page(page, Race(race_number=3), date(2026, 9, 2), BASE)
    assert race.start_time_local == "2026-09-02T12:25:00+10:00"

def test_promoted_reserve_runs_from_the_box_it_replaced():
    """A reserve keeps rug 9 or 10 but runs from the box it took over.

    The site says so two different ways, and the box - not the rug - is what a
    market is made on, so both phrasings have to be read.
    """
    from scrapling import Selector

    def box_of(annotation):
        page = Selector(content=f"""
          <table class="race-runners"><tbody>
            <tr class="race-runner">
              <td class="race-runners__box"><sprite-svg name="rug_10"></sprite-svg></td>
              <td class="race-runners__name">
                <div class="race-runners__name__dog">Lazy Dynamite
                  <span class="race-runners__name__time">22.69</span> {annotation}</div>
              </td>
            </tr>
          </tbody></table>
        """)
        race = parse_race_page(page, Race(race_number=1), date(2026, 9, 22), BASE)
        return race.runners[0].box if race.runners else None

    assert box_of("(into box 6)") == 6
    assert box_of("(from box 5)") == 5
    # Un-annotated it is still a reserve, kept with its rug and flagged as one:
    # whether the dog is running is what matters, not the rug it wears.
    assert box_of("") == 10

def test_unpromoted_reserves_are_kept_and_flagged():
    """A reserve is still a runner - dropping it loses a dog that may be in."""
    from scrapling import Selector

    page = Selector(content="""
      <table class="race-runners"><tbody>
        <tr class="race-runner">
          <td class="race-runners__box"><sprite-svg name="rug_1"></sprite-svg></td>
          <td class="race-runners__name"><div class="race-runners__name__dog">In The Field</div></td>
        </tr>
        <tr class="race-runner">
          <td class="race-runners__box"><sprite-svg name="rug_9"></sprite-svg></td>
          <td class="race-runners__name"><div class="race-runners__name__dog">A Reserve</div></td>
        </tr>
      </tbody></table>
    """)
    race = parse_race_page(page, Race(race_number=1), date(2026, 9, 22), BASE)

    names = {r.name for r in race.runners}
    assert names == {"In The Field", "A Reserve"}
    reserve = next(r for r in race.runners if r.name == "A Reserve")
    assert reserve.raw.get("reserve") is True
    assert reserve.box == 9
