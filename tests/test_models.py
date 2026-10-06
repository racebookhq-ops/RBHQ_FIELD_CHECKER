from dogs_scraper.models import DayCard, Meeting, Race, Runner, parse_date


def _race():
    return Race(
        race_number=1, name="Red TV Maiden", distance_m=350,
        runners=[
            Runner(box=1, name="One Hot Chance", trainer="Ruth Matic", weight_kg=29.1),
            Runner(box=2, name="Sutton Jet", trainer="Justin Thorpe", weight_kg=29.1),
            Runner(box=3, name="Captain Corey", scratched=True),
        ],
    )


def test_field_size_excludes_scratchings():
    race = _race()
    assert len(race.runners) == 3
    assert race.field_size == 2
    assert race.scratchings == [3]


def test_daycard_totals_and_serialisation():
    card = DayCard(meeting_date="2026-08-28", scraped_at="2026-08-28T09:00:00+10:00")
    card.meetings.append(Meeting(track="Goulburn", track_slug="goulburn",
                                 meeting_date="2026-08-28", races=[_race()]))
    payload = card.to_dict()
    assert payload["summary"] == {"meetings": 1, "races": 1, "runners": 3, "errors": 0}
    assert payload["meetings"][0]["races"][0]["runners"][0]["name"] == "One Hot Chance"


def test_parse_date_keywords():
    from datetime import date, timedelta
    from dogs_scraper.utils.dates import today_local
    assert parse_date("2026-08-28") == date(2026, 8, 28)
    assert parse_date("today") == today_local()
    assert parse_date("tomorrow") == today_local() + timedelta(days=1)
