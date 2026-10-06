"""Orchestration: index -> meetings -> races -> runners -> DayCard.

    1. Load  /racing/fields?date=YYYY-MM-DD  (the day tab). Links give meeting
       codes and race ids; the page's own `/racing/fields?date=` JSON adds
       state and trial flags.
    2. Load each meeting page once. The page requests `/racing/{meetingCode}/`
       which already contains every race and runner (checked live), so that one
       response is captured and split into per-race files under data/raw/.
    3. If that response is not captured, load each race page and capture
       `/racing/{meetingCode}/{raceId}`.
    4. If that is not captured either, parse the rendered runner grid
       (fallback.py).

Pages are loaded one at a time in one browser context.
"""

from __future__ import annotations

import json
from datetime import date as _date
from pathlib import Path

from dogs_scraper.utils.dates import now_local

from .browser import Capture, FetchError, HarnessBrowser
from .config import Settings
from .discovery import (DiscoveredMeeting, merge_discovery, parse_index_json,
                        parse_index_links)
from .fallback import FallbackError, parse_race_text
from .logging import get_logger
from .mapper import map_meeting, map_race, split_races
from .models import DayCard, Meeting, Race

log = get_logger("scraper")


class HarnessScraper:
    def __init__(self, settings: Settings):
        self.settings = settings

    # -- entry points ---------------------------------------------------------
    def scrape_day(self, day: _date) -> DayCard:
        day_str = day.isoformat()
        card = DayCard(meeting_date=day_str, scraped_at=now_local().isoformat())

        with HarnessBrowser(self.settings) as browser:
            discovered = self._discover(browser, day_str, card)
            for dm in discovered:
                try:
                    meeting = self._scrape_meeting(browser, dm, card)
                except Exception as exc:  # noqa: BLE001 - one bad track shouldn't kill the run
                    card.errors.append({"stage": "meeting", "meeting": dm.meeting_code, "error": str(exc)})
                    log.exception("failed on meeting %s", dm.meeting_code)
                    continue
                if meeting is not None:
                    card.meetings.append(meeting)

        self._log_done(card)
        return card

    def scrape_from_raw(self, day: _date) -> DayCard:
        """Rebuild a card from data/raw/{date}/*.json without touching the site."""
        day_str = day.isoformat()
        card = DayCard(meeting_date=day_str, scraped_at=now_local().isoformat())
        raw_dir = Path(self.settings.raw_root) / day_str
        files = sorted(raw_dir.glob("*.json"))
        if not files:
            card.errors.append({"stage": "raw", "error": f"no raw files in {raw_dir}"})
            return card

        by_code: dict[str, Meeting] = {}
        for path in files:
            try:
                meeting = map_meeting(json.loads(path.read_text(encoding="utf-8")))
            except Exception as exc:  # noqa: BLE001
                card.errors.append({"stage": "raw", "file": path.name, "error": str(exc)})
                continue
            key = meeting.meeting_code or path.stem
            if key in by_code:
                by_code[key].races.extend(meeting.races)
            else:
                by_code[key] = meeting

        for meeting in by_code.values():
            meeting.races.sort(key=lambda r: (r.race_no is None, r.race_no or 0))
            if self._keep(meeting):
                card.meetings.append(meeting)
        self._log_done(card)
        return card

    # -- discovery ------------------------------------------------------------
    def _discover(self, browser: HarnessBrowser, day_str: str, card: DayCard) -> list[DiscoveredMeeting]:
        url = f"{self.settings.base_url}/racing/fields?date={day_str}"
        try:
            cap = browser.fetch(url, expect=r"/racing/fields\?date=")
        except FetchError as exc:
            card.errors.append({"stage": "index", "url": url, "error": str(exc)})
            log.error("could not load the index: %s", exc)
            return []

        links = parse_index_links(cap.html, day_str, self.settings.base_url)
        listing = parse_index_json(cap.find(r"/racing/fields\?date="), self.settings.base_url)
        listing = [m for m in listing if m.date == day_str]
        found = merge_discovery(links, listing, include_trials=self.settings.include_trials,
                                states=self.settings.states)
        log.info("index: %d meeting(s) from links, %d from the page's JSON -> %d to scrape",
                 len(links), len(listing), len(found))
        if not found:
            card.errors.append({"stage": "index", "url": url, "error": "no meetings found for this date"})
        return found

    # -- one meeting ----------------------------------------------------------
    def _scrape_meeting(self, browser: HarnessBrowser, dm: DiscoveredMeeting,
                        card: DayCard) -> Meeting | None:
        code = dm.meeting_code
        cap = browser.fetch(dm.url, expect=rf"/racing/{code}/?$")
        payload = cap.find(rf"/racing/{code}/?$")

        if isinstance(payload, dict) and payload.get("races"):
            meeting = self._from_meeting_json(payload, dm, card)
        else:
            log.warning("%s: meeting JSON not captured - loading race pages", code)
            meeting = self._from_race_pages(browser, dm, card)

        if not self._keep(meeting):
            return None
        return meeting

    def _from_meeting_json(self, payload: dict, dm: DiscoveredMeeting, card: DayCard) -> Meeting:
        for doc in split_races(payload):
            self._save_raw(dm.date, doc["races"][0].get("rise_race_code"), doc)
        meeting = map_meeting(payload, self.settings.base_url)

        got = {r.race_id for r in meeting.races}
        missing = [r.race_id for r in dm.races if r.race_id not in got]
        if missing:
            card.errors.append({"stage": "race", "meeting": dm.meeting_code,
                                "error": f"races on the index but not in the API response: {missing}"})
        return meeting

    def _from_race_pages(self, browser: HarnessBrowser, dm: DiscoveredMeeting, card: DayCard) -> Meeting:
        meeting = Meeting(date=dm.date, track_name=dm.track_name, track_slug=dm.track_slug,
                          state=dm.state, meeting_code=dm.meeting_code, is_trial=dm.is_trial,
                          url=dm.url)
        for ir in dm.races:
            url = f"{self.settings.base_url}/racing/{dm.date}/{dm.track_slug}/{dm.meeting_code}/meeting/{ir.race_id}/{ir.race_no}/fields"
            try:
                cap = browser.fetch(url, expect=rf"/racing/{dm.meeting_code}/{ir.race_id}$")
                race = self._race_from_capture(cap, dm, ir.race_id, ir.race_no, meeting)
            except (FetchError, FallbackError) as exc:
                card.errors.append({"stage": "race", "meeting": dm.meeting_code,
                                    "race": ir.race_no, "url": url, "error": str(exc)})
                log.warning("skipping race %s: %s", url, exc)
                continue
            race.url = url
            meeting.races.append(race)
        return meeting

    def _race_from_capture(self, cap: Capture, dm: DiscoveredMeeting, race_id: str, race_no: int,
                           meeting: Meeting) -> Race:
        payload = cap.find(rf"/racing/{dm.meeting_code}/{race_id}$")
        if isinstance(payload, dict) and payload.get("races"):
            self._save_raw(dm.date, race_id, payload)
            mapped = map_meeting(payload, self.settings.base_url)
            for field_name in ("track_name", "state", "circumference_m", "straight_length_m",
                               "front_line_mobile", "front_line_standing", "is_trial"):
                if getattr(mapped, field_name) is not None:
                    setattr(meeting, field_name, getattr(mapped, field_name))
            return mapped.races[0]
        log.warning("%s: race JSON not captured - parsing rendered text", race_id)
        return parse_race_text(cap.html, race_id=race_id, race_no=race_no)

    # -- helpers --------------------------------------------------------------
    def _keep(self, meeting: Meeting) -> bool:
        """Final filters, applied on what the meeting JSON itself says."""
        if meeting.is_trial and not self.settings.include_trials:
            log.info("dropping trial meeting %s", meeting.meeting_code)
            return False
        if self.settings.states and meeting.state and meeting.state not in self.settings.states:
            return False
        return True

    def _save_raw(self, day_str: str, race_id: str | None, doc: dict) -> None:
        if not race_id:
            return
        path = Path(self.settings.raw_root) / day_str / f"{race_id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(doc, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _log_done(card: DayCard) -> None:
        log.info("done: %d meetings, %d races, %d runners, %d errors",
                 len(card.meetings), card.total_races, card.total_runners, len(card.errors))
