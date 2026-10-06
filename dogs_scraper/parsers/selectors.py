"""Every CSS/XPath selector in the project lives here.

thedogs.com.au changes its markup from time to time, so each field is a list
of candidates tried in order. When the site changes, this is the only file
that should need editing - run `python tools/dump_html.py` to grab a fresh
sample and add the new selector to the front of the relevant list.

The leading candidate in each list was confirmed against the live site on
2026-09-01, for both page states a race goes through:

    upcoming   table.race-runners                      - the field
    run        table.race-runners.race-runners--result - the result

Both use the same row and cell classes; the result table adds a finish
position, time and margin, and wraps the dog name in a link.
"""

# --- day index: /racing/<date> -------------------------------------------
MEETING_LINKS = [
    'a[href*="/racing/"][href*="20"]',
    'a.meeting-link',
    '[data-testid="meeting-card"] a',
]
MEETING_CARD = [
    '.meeting-header__races__meeting',
    '[data-testid="meeting-card"]',
    '.meeting-card',
    '.meeting',
]
MEETING_STATE = [
    '::attr(data-state)',
    '.state::text',
    '.meeting-state::text',
]

# --- meeting page: /racing/<track>/<date> ---------------------------------
RACE_LINKS = [
    'a[href*="/racing/"]',
    'a.race-link',
    '[data-testid="race-row"] a',
]
MEETING_TITLE = [
    'h1::text',
    '.meeting-title::text',
    '[data-testid="meeting-title"]::text',
]
MEETING_TRACK_CONDITION = [
    '.track-condition::text',
    '[data-testid="track-condition"]::text',
]

# --- race page: /racing/<track>/<date>/<n>/<slug> --------------------------
RACE_TITLE = [
    '.race-header__info__name::text',
    'h1::text',
    '.race-title::text',
]
RACE_HEADER_BLOCK = [
    '.race-header',
    '[data-testid="race-header"]',
    'header',
]
# "Maiden 342m" - carries both the grade and the distance.
RACE_GRADE_DISTANCE = [
    '.race-header__info__grade::text',
]
RACE_DISTANCE = [
    '.race-header__info__grade::text',
    '.race-distance::text',
]
RACE_GRADE = [
    '.race-header__info__grade::text',
    '.race-grade::text',
]
# Full ISO-8601 with offset, e.g. "2026-09-02T11:48:00+10:00" - the best
# start-time source on the page. The epoch fallback is UTC seconds.
# A race page carries the whole meeting's race strip - a .race-box per race -
# so this must pick THIS race, not the first one on the page. The header's own
# box is `--large`; `--active` marks the current race within the strip. Taking
# a bare `.race-box` gives you race 1's time on every page.
RACE_START_ISO = [
    '.race-box--large[data-race-box]::attr(data-race-box)',
    '.race-box--active[data-race-box]::attr(data-race-box)',
]
RACE_START_EPOCH = [
    '.race-header__info__time formatted-time::attr(data-timestamp)',
]
RACE_TIME = [
    '.race-header__info__time formatted-time::text',
    'time::attr(datetime)',
    '.race-time::text',
]
RACE_NUMBER = [
    '.race-box__number::text',
]
RACE_PRIZE = [
    '.race-header__prize__total::text',
    '.prize-money::text',
]
RACE_PRIZE_PLACES = [
    '.race-header__prize__places::text',
]
RACE_TRACK_RECORD = [
    '.race-header__record th + th::text',
]
RACE_COMMENT = [
    '.race-comment::text',
    '[data-testid="race-comment"]::text',
]

# --- runner rows ----------------------------------------------------------
# One <tr class="race-runner"> per box. Rows in between carry the expanded
# form accordion and have no class - selecting on .race-runner skips them.
RUNNER_ROWS = [
    'tr.race-runner',
    '[data-testid="runner-row"]',
    'table.race-runners tbody tr',
    '.runner-card',
]
# The box number is not text: it is the rug graphic's name, "rug_4".
RUNNER_BOX_SPRITE = [
    'td.race-runners__box sprite-svg::attr(name)',
    '.race-runners__box sprite-svg::attr(name)',
]
RUNNER_BOX = [
    '.box-number::text',
    '[data-testid="box"]::text',
    '.rug::text',
]
# Linked on a run race, a bare text node on an upcoming one - try both.
RUNNER_NAME = [
    '.race-runners__name__dog a::text',
    '.dog-name::text',
    'a[href*="/dogs/"]::text',
]
RUNNER_NAME_BLOCK = [
    '.race-runners__name__dog',
]
# A reserve promoted into a scratching keeps a reserve rug (9, 10) but runs
# from the box it replaced, which the site prints beside the name - as either
# "(from box 5)" or "(into box 6)". That box is the one a market is made on.
RUNNER_FROM_BOX = [
    'td.race-runners__name',
    '.race-runners__name__dog',
]
RUNNER_LINK = [
    '.race-runners__name__dog a::attr(href)',
    'a[href*="/dogs/"]::attr(href)',
]
RUNNER_DOG_ID = [
    'blackbook-dog::attr(data-dog-id)',
]
RUNNER_TRAINER = [
    'td.race-runners__trainer a::text',
    'td.race-runners__trainer::text',
    '.trainer::text',
    'a[href*="/trainers/"]::text',
]
RUNNER_WEIGHT = [
    'td.race-runners__weight::text',
    '.weight::text',
]
RUNNER_FORM = [
    'td.race-runners__last-four::text',
    '.form::text',
]
# Sits inside the name cell: the dog's best time, or "NBT" if it has none.
RUNNER_BEST_TIME = [
    '.race-runners__name__time::text',
    '.best-time::text',
]
RUNNER_GRADE = [
    'td.race-runners__grade::text',
]
RUNNER_TRACK_DIST = [
    'td.race-runners__track-dist::text',
]
# Empty <runner-odd> element - the price is fetched by JavaScript, so it is
# never present for the plain HTTP fetcher. Kept for the dynamic fetcher.
RUNNER_ODDS = [
    'td.race-runners__odds runner-odd::text',
    '.odds::text',
    '.price::text',
]
# A vacant box is a row-level class, not a per-field flag.
RUNNER_SCRATCHED_ROW = [
    'race-runner--scratched',
]
RUNNER_SCRATCHED = [
    '.scratched',
    '[data-scratched="true"]',
    '.is-scratched',
]
# Result pages only.
RUNNER_FINISH = [
    'td.race-runners__finish-position::text',
]

# Text the site puts in the name cell when a box has no dog in it.
VACANT_BOX_TEXT = "vacant box"

# Header keywords used by the generic-table fallback parser, mapped to the
# Runner field they populate.
COLUMN_ALIASES = {
    "box": "box",
    "rug": "box",
    "no": "box",
    "no.": "box",
    "dog": "name",
    "greyhound": "name",
    "name": "name",
    "runner": "name",
    "trainer": "trainer",
    "wgt": "weight_kg",
    "weight": "weight_kg",
    "form": "form",
    "last 4": "form",
    "last starts": "form",
    "bt": "best_time",
    "best": "best_time",
    "best time": "best_time",
    "odds": "odds",
    "price": "odds",
    "$": "odds",
    "prize": "prize_money",
    "prizemoney": "prize_money",
}
