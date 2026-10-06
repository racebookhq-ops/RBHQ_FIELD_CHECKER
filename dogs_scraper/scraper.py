"""Orchestration: day index -> meetings -> races -> runners -> DayCard."""

from __future__ import annotations

from datetime import date as _date

from .config import Settings
from .discovery import extract_embedded_json
from .fetcher import FetchError, PageFetcher
from .models import DayCard, Meeting
from .parsers import parse_meeting_list, parse_meeting_page, parse_race_page
from .utils.dates import now_local
from .utils.logging import get_logger

log = get_logger("scraper")


class DogsScraper:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.fetcher = PageFetcher(settings)

    # -- entry point ---------------------------------------------------------
    def scrape_day(self, day: _date) -> DayCard:
        day_str = day.isoformat()
        card = DayCard(meeting_date=day_str, scraped_at=now_local().isoformat())

        index_url = f"{self.settings.base_url}/racing/{day_str}"
        try:
            index_page = self.fetcher.get(index_url)
        except FetchError as exc:
            card.errors.append({"stage": "index", "url": index_url, "error": str(exc)})
            log.error("could not load the day index: %s", exc)
            return card

        if self.settings.extraction_mode in ("auto", "json"):
            payload = extract_embedded_json(index_page)
            if payload:
                log.info("page exposes an embedded JSON payload "
                         "(run tools/inspect_json.py to map it)")

        meetings = parse_meeting_list(index_page, day_str, self.settings.base_url)
        meetings = self._filter(meetings)

        for meeting in meetings:
            try:
                self._scrape_meeting(meeting, day, card)
            except Exception as exc:  # noqa: BLE001 - one bad track shouldn't kill the run
                card.errors.append({"stage": "meeting", "track": meeting.track_slug, "error": str(exc)})
                log.exception("failed on meeting %s", meeting.track_slug)
            card.meetings.append(meeting)

        log.info("done: %d meetings, %d races, %d runners, %d errors",
                 len(card.meetings), card.total_races, card.total_runners, len(card.errors))
        return card

    # -- internals -----------------------------------------------------------
    def _filter(self, meetings: list[Meeting]) -> list[Meeting]:
        wanted_tracks = {t.lower() for t in self.settings.tracks}
        wanted_states = {s.upper() for s in self.settings.states}
        out = []
        for m in meetings:
            if wanted_tracks and (m.track_slug or "").lower() not in wanted_tracks:
                continue
            if wanted_states and (m.state or "").upper() not in wanted_states:
                continue
            out.append(m)
        if len(out) != len(meetings):
            log.info("filtered %d -> %d meetings", len(meetings), len(out))
        return out

    def _scrape_meeting(self, meeting: Meeting, day: _date, card: DayCard) -> None:
        page = self.fetcher.get(meeting.url)
        parse_meeting_page(page, meeting, self.settings.base_url)

        for race in meeting.races:
            if not race.url:
                continue
            try:
                race_page = self.fetcher.get(race.url)
                parse_race_page(race_page, race, day, self.settings.base_url)
            except FetchError as exc:
                card.errors.append({
                    "stage": "race", "track": meeting.track_slug,
                    "race": race.race_number, "url": race.url, "error": str(exc),
                })
                log.warning("skipping race %s: %s", race.url, exc)
