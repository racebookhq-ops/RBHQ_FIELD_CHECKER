# Greyhound field checker

Checks our own greyhound fields against the fields the sport publishes, and
reports anything that disagrees.

1. **`dogs_scraper`** — scrapes [thedogs.com.au](https://www.thedogs.com.au).
   This is the *reference*: what the fields should be.
2. **`rbhq_scraper`** — maps the RBHQ JSON feed onto the same card. This is
   *ours*: what we are actually showing.
3. **`field_compare`** — checks one against the other, box by box, and writes a
   severity-ranked JSON report for an agent to read and act on.

Both scrapers produce a `DayCard` — the same class, not a lookalike — and
serialise through the same exporters, so the two cards cannot drift apart.

## The check in one line

> A race is correct when the same greyhounds are running on both sides.

It is the **set of active runners** that is compared, by name — not the boxes.

```bash
python run.py                    # today, end to end
python run.py --date tomorrow
python run.py --strict
```

`run.py` is just a shortcut for `python -m field_compare`. It fetches the RBHQ
feed first (one request) and only then scrapes thedogs (a few hundred), so a
bad key or a changed endpoint fails in a second rather than after minutes of
scraping.

Exit code is **1 when anything critical is found**, so a scheduled run fails
rather than passing quietly. The report lands in
`output/discrepancies_YYYY-MM-DD.json`.

Either half can be run on its own when you only want one card:

```bash
python -m dogs_scraper --date today     # what thedogs.com.au publishes
python -m rbhq_scraper --date today     # what the RBHQ feed shows
```

Built on [Scrapling](https://github.com/D4Vinci/Scrapling).

## Quick start

```bash
# from the project root, with the venv active
venv\Scripts\activate                 # Windows
pip install -r requirements.txt
scrapling install                     # only needed for the browser fetchers

python -m dogs_scraper scrape         # today's fields from thedogs.com.au
```

Output lands in `output/`:

- `thedogs_YYYY-MM-DD.json` — nested meetings → races → runners
- `thedogs_YYYY-MM-DD_runners.csv` — one row per greyhound

## CLI

```bash
python -m dogs_scraper --date today
python -m dogs_scraper --date 2026-08-29
python -m dogs_scraper --state NSW VIC
python -m dogs_scraper --track goulburn wagga
python -m dogs_scraper --no-cache --log-level DEBUG --save-raw-html
python -m dogs_scraper --json-only
```

| Flag | What it does |
|---|---|
| `--date` | `today` / `tomorrow` / `yesterday` / `YYYY-MM-DD` |
| `--state` | limit to state codes, e.g. `NSW VIC` — **currently a no-op filter, see below** |
| `--track` | limit to track slugs, e.g. `goulburn wagga` |
| `--fetcher` | `fetcher` (plain HTTP, default), `stealthy` (anti-bot browser), `dynamic` |
| `--extraction-mode` | `auto` (JSON if available, else HTML), `json`, `html` |
| `--no-cache` | ignore the 10-minute page cache |
| `--save-raw-html` | dump each page to `.cache/raw/` for selector work |
| `--json-only` / `--csv-only` | write just one of the two outputs |
| `--delay` | seconds between requests (default: 1.0) |

> **`--state` does not work yet.** The day index no longer publishes a state
> for each meeting — the page carries only the track name and race times — so
> `Meeting.state` is always `null` and `--state NSW` filters every meeting
> out. Use `--track` instead. Populating state needs either a lookup table of
> track → state or a second request per meeting.

Persistent settings live in `config.yaml`; CLI flags override it.

Running with no subcommand does `scrape`, so bare `python -m dogs_scraper`
still works.

## Use from Python

```python
from dogs_scraper import scrape

card = scrape("today")
for meeting in card.meetings:
    for race in meeting.races:
        print(meeting.track, race.race_number, race.field_size, race.scratchings)
```

## Output shape

```jsonc
{
  "meeting_date": "2026-08-28",
  "scraped_at": "2026-08-28T09:12:03+10:00",
  "source": "thedogs.com.au",
  "summary": { "meetings": 12, "races": 138, "runners": 1104, "errors": 0 },
  "meetings": [
    {
      "track": "Goulburn",
      "track_slug": "goulburn",
      "state": "NSW",
      "meeting_date": "2026-08-28",
      "url": "https://www.thedogs.com.au/racing/goulburn/2026-08-28",
      "race_count": 11,
      "races": [
        {
          "race_number": 1,
          "name": "Red TV Maiden",
          "distance_m": 350,
          "grade": "Maiden",
          "start_time_local": "2026-08-28T12:34:00+10:00",
          "prize_money": "$1,865",
          "field_size": 6,
          "scratchings": [3, 6],
          "runners": [
            {
              "box": 1,
              "name": "Get Them Jimmy",
              "trainer": "Tamica Dunn",
              "weight_kg": null,
              "form": "4454",
              "best_time": "20.79",
              "odds": null,
              "scratched": false,
              "dog_url": null,
              "raw": { "dog_id": "443947", "grade": "M", "track_dist": "3: 0-0-1" }
            },
            {
              "box": 3,
              "name": null,
              "scratched": true,
              "raw": { "vacant": true }
            }
          ]
        }
      ]
    }
  ],
  "errors": []
}
```

`box` is the field to match on - it is the one value every runner always has,
and runners always come back sorted by it. `dog_name_normalised` in the CSV
(upper-cased, punctuation stripped) is there for fuzzy name matching.

### Empty boxes

A box with no dog in it comes back as a runner with `"name": null`,
`"scratched": true` and `"raw": {"vacant": true}` rather than being dropped,
so box 3 being empty is something a consumer can see rather than infer from a
gap. `field_size` counts only live runners and `scratchings` lists the empty
boxes, so a race with boxes 3 and 6 vacant reports `field_size: 6` and
`scratchings: [3, 6]`.

### What is not in the output

Odds are rendered by JavaScript - the page ships an empty
`<runner-odd data-market="fixed_win">` element and fills it after load. The
default HTTP fetcher never sees a price, so `odds` is `null`. Use
`--fetcher dynamic` if you need them. Everything else (box, dog, trainer,
grade, form, best time, scratchings, start time) is in the static HTML.

Weight is only published on a race that has already been run, so `weight_kg`
is `null` on an upcoming card.

## Comparing the two

```bash
python -m field_compare --date today
python -m field_compare --date today --strict            # + trainer
python -m field_compare --date today --track angle-park
python -m field_compare --reference-file output/thedogs_2026-09-22.json                         --ours-file response.json
```

Both sides are fetched live by default — thedogs.com.au is scraped and the RBHQ
feed is called. `--reference-file` and `--ours-file` replay saved cards instead,
which makes debugging a report free.

### What gets checked

| Check | Severity | Why |
|---|---|---|
| In the field, we have it scratched | critical | No market on a dog that is running |
| In the field, we do not have it at all | critical | No market on a dog that is running |
| We have it running, it is not in the field | critical | Market on a non-runner |
| Scratched in the field, still running on ours | critical | Taking bets on a scratching |
| Meeting or race missing from our card | critical | No market at all |
| Distance or field size mismatch | warning | The card is wrong, not yet dangerous |
| A race or meeting we show that thedogs doesn't | warning | Usually a missing track alias |
| Same dog, different box | info | Recorded, not worth acting on — see below |
| Start time drift over 2 min | info | Timing, not correctness |
| Name spelling, trainer (`--strict`) | info | Data quality |

### Why boxes are not compared

The two sources disagree about boxes constantly and harmlessly. When a reserve
is promoted into a scratching, thedogs keeps it on rug 9 or 10 and annotates
the name `(from box 5)` or `(into box 6)`, while the feed may move it straight
into the vacated barrier. Both are telling the truth, and box-by-box matching
turned that into a stream of "wrong dog in box" criticals that were nothing of
the sort.

What cannot differ is **who is in the race**. So runners are paired on
normalised name, and a dog in a different box on each side is recorded as
`box_mismatch` at info level — visible if you want it, filtered out if you
don't. Reserves are kept on both sides for the same reason: a dog on rug 10 is
still a dog that may be running.

Three things keep the report honest rather than noisy:

- **A field is only compared when both sides publish it.** The feed carries no
  weight, form, best time or price, so those are skipped outright instead of
  firing on every runner.
- **Names are normalised first** — upper-cased, punctuation stripped — so
  `O'Reilly's Boy` and `OReillys Boy` never raise a flag. A spelling difference
  that survives normalisation is reported as info, not as a wrong dog.

### Matching the venues

Tracks pair on the slugified name first (`ANGLE PARK` and `Angle Park` both
become `angle-park`), then on the same name with a sponsor prefix stripped
(thedogs calls it `Ladbrokes Q Straight`, the feed calls it `Q Straight`), then
on the `AlternateVenueNames` the feed ships for each meeting, then on
`track_aliases.yaml` for the pairs nobody could guess. Anything still unpaired
lands in the report's `unmatched` block with the exact spelling each side used,
so the first run tells you what to add.

Sponsorships change more often than tracks do, which is why the prefix is
stripped when matching rather than chased in the alias file.

### The report

`output/discrepancies_YYYY-MM-DD.json` is the file for the agent:

```jsonc
{
  "meeting_date": "2026-09-22",
  "reference_source": "thedogs.com.au",
  "our_source": "rbhq-api",
  "summary": { "meetings_matched": 12, "races_compared": 138,
               "boxes_compared": 1104,
               "counts": { "critical": 3, "warning": 2, "info": 0 },
               "unmatched": { "reference_only": [], "ours_only": [] } },
  "discrepancies": [
    {
      "type": "runner_missing",
      "severity": "critical",
      "message": "Angle Park R1: Sutton Jet is in the field, we have it scratched",
      "track": "Angle Park", "race_number": 1, "box": 4, "field": "name",
      "reference": "Sutton Jet", "ours": "Sutton Jet",
      "race_url": "https://www.thedogs.com.au/racing/angle-park/2026-09-22/1/...",
      "start_time_local": "2026-09-22T11:10:00+10:00"
    }
  ]
}
```

Criticals sort first. Every record carries both values and a link to the race,
so an agent can decide and message without going back to either source. Keys
that do not apply to a finding are omitted rather than left null.

## The RBHQ feed

`rbhq_scraper` calls the feed for a racing day and emits the same card shape
under an `rbhq_` prefix, so both land in `output/` side by side:

```bash
python -m rbhq_scraper --date today
python -m rbhq_scraper --date 2026-09-22 --state SA WA
python -m rbhq_scraper --file response.json          # replay a saved one
```

| Flag | What it does |
|---|---|
| `--date` | which racing day to fetch (default: today) |
| `--file` | replay a saved response instead of calling the API |
| `--url` | override `rbhq.base_url` for this run |
| `--save-response` | write the raw payload out, so the run can be replayed |
| `--show-endpoint` | print the URL that would be called, and exit |
| `--state` / `--track` | same meaning as the scraper's |
| `--country` | countries to keep (default `AU`) |
| `--all-days` | keep every day a saved payload contains |

Output: `output/rbhq_YYYY-MM-DD.json` and `rbhq_YYYY-MM-DD_runners.csv`.

### The endpoint

```
POST https://api.racebookhq.com/api/host/events/full
{ "dates": ["2026-09-22T00:00:00"], "raceTypes": ["G"] }
```

`raceTypes` selects the codes — **G** greyhounds, **R** thoroughbreds,
**H** harness. Only `G` is requested: the other two have nothing on
thedogs.com.au to compare against, and asking for them makes the response
several times larger for no gain. Widen it in `config.yaml` if you ever need to.

**Authentication is required.** The endpoint answers a correctly-shaped request
with a bare `401` and an empty body, so a key has to be supplied. Copy the
template and fill it in:

```bash
copy .env.example .env          # Windows
cp   .env.example .env          # bash
```

```
RBHQ_API_KEY=your-key-here
```

`.env` is gitignored and never committed; `.env.example` is the committed
template. The key is also **never** written to `config.yaml`, and is kept out
of logs and error messages.

**An exported variable always beats the file**, so a scheduled run, a
container or CI can supply the key its own way without anyone editing a
checked-out `.env`:

```
setx RBHQ_API_KEY "..."          # wins over .env
```

By default the key is sent as `Authorization: Bearer <key>`. Change
`auth_header`, `auth_prefix` or `auth_param` in the `rbhq:` block if the API
expects it some other way.

Everything about the call is configurable there — path, method, the body field
carrying the date, its format — so a change at the API end does not need a code
change. Check what will be sent, without sending it:

```bash
$ python -m rbhq_scraper --show-endpoint
  POST  https://api.racebookhq.com/api/host/events/full
  body      {"dates": ["2026-09-22T00:00:00"], "raceTypes": ["G"]}
  auth      Authorization header from $RBHQ_API_KEY (.env)
```

The last line names where the key was found — `.env`, `environment`, or
`not set` — which is usually the first thing you want to know when a call comes
back 401.

Nothing is cached. The point of the comparison is to catch a scratching or a
box change soon after it happens, so serving a card from a cache would quietly
defeat it.

### What the feed calls things

Four parts of the translation are not a field copy, and each has a test:

- **The box is `barrier`, not `runnerNumber`.** `runnerNumber` keeps counting
  past the field into the reserves; `barrier` is the rug the dog runs from.
  A reserve that has not been given a box carries `barrier: 0` and comes
  through with `box: null` and `raw.reserve: true` — **not** dropped. It is
  still a greyhound that may be running, and the feed numbers it 9 or 10.
- **An empty box is a runner named `"...."`** with no trainer — the feed's
  spelling of thedogs' "Vacant Box". It becomes `name: null`,
  `scratched: true`, `raw.vacant: true`, so an empty box 3 stays visible.
- **Two entries can share a barrier.** When a dog is scratched, a reserve is
  promoted into its box and the feed keeps both rows. Both are reported — the
  live one and the one that came out — because the comparison matches on who
  is running, not on what sits in each box.
- **Times are UTC.** thedogs publishes every start in Australia/Sydney
  regardless of the track's own state, so starts are converted to that zone
  and the two cards line up without any timezone reasoning downstream.

### What the feed does not carry

`weight_kg`, `form`, `best_time` and `odds` are not published — `prices` is
`{}` on every runner in every sample seen. They come back `null` rather than
guessed at, so a comparison skips those fields instead of reporting a
difference that isn't one. There is also no public race page, so `url` is
`null`.

What it *does* carry that the scraper cannot get: **`state`**, on every
meeting.

## Housekeeping

A daily run leaves five files in `output/` and the page cache keeps every page
it fetched, so both are swept at the end of each run:

| Flag | What it does |
|---|---|
| `--keep-days N` | racing days of results to keep (default 14; `0` = today only, `-1` = keep everything) |
| `--no-prune` | leave old results and cached pages alone |
| `--prune-dry-run` | report what would be deleted, delete nothing |

Defaults live in `config.yaml` as `output_retention_days` and
`cache_retention_hours`. Cached pages go after 24 hours — they are only ever
read within a 10-minute TTL, so anything older is dead weight.

It is deliberately timid, because it deletes things:

- **Only names this project writes** — matched against an exact pattern
  (`thedogs_2026-09-22.json`, `rbhq_2026-09-22_runners.csv`,
  `discrepancies_2026-09-22.json`), never a glob. Anything else in the
  directory, `.gitkeep` and your own files included, is left alone.
- **Only that directory**, never a subdirectory and never a parent.
- **Never today, and never the future.** Age comes from the racing date in the
  filename rather than the modification time, so re-running an old day does not
  reprieve it and tomorrow's card is never swept up.
- **It runs last**, so a failed run never takes the previous good result with
  it.

Check before trusting it:

```bash
python run.py --prune-dry-run
```

## Layout

```
dogs_scraper/
  cli.py            argparse entry point
  config.py         Settings dataclass + config.yaml loading
  scraper.py        orchestration: index → meetings → races → runners
  fetcher.py        Scrapling wrapper: retries, throttling, caching, HTML dumps
  discovery.py      looks for an embedded JSON payload before parsing HTML
  models.py         DayCard / Meeting / Race / Runner dataclasses
  parsers/
    selectors.py    EVERY CSS selector lives here — edit this when the site changes
    meetings.py     day index → meetings, meeting page → race stubs
    race.py         race page → runners (targeted selectors, then table fallback)
  sources/
    base.py         the Source contract every data source implements
    thedogs.py      the scraper behind that contract
  exporters/        json_export.py, csv_export.py
  utils/            dates (Australia/Sydney), text, logging, housekeeping
rbhq_scraper/
  cli.py            argparse entry point
  client.py         calls the feed; replays a saved response for tests
  config.py         where the endpoint lives and how to authenticate
  env.py            reads the API key out of a gitignored .env
  mapper.py         feed JSON -> the same DayCard, box semantics and all
field_compare/
  matcher.py        pairs meetings by venue, races by number, runners by box
  rules.py          the checks and their severities - box is truth
  models.py         Discrepancy / ComparisonReport
  report.py         the JSON file for the agent, and a console summary
track_aliases.yaml  venue names that differ between the two sources
tools/
  dump_html.py      save a live page to tests/fixtures/ for offline selector work
  inspect_json.py   map an embedded JSON payload if the site ships one
config.yaml         scraper settings (committed - no secrets)
.env                API key (gitignored; copy .env.example)
tests/              pytest suite; parser tests skip until fixtures exist
output/             scraped cards
```

## When the site changes

The parsers are written defensively — each field tries a list of candidate
selectors, and the race parser falls back to reading the runner table by its
column headings. If a run reports 0 runners:

```bash
python tools/dump_html.py --race goulburn 2026-08-28 1 red-tv-maiden --name race_page.html
python tools/inspect_json.py https://www.thedogs.com.au/racing/goulburn/2026-08-28/1/red-tv-maiden
```

Then add the correct selector to the front of the relevant list in
`dogs_scraper/parsers/selectors.py` and run `pytest` — the fixtures make the
loop offline and fast.

`tests/fixtures/` holds a saved upcoming race (`race_page.html`), a race that
has already been run (`race_page_result.html`) and a day index. The two race
pages use different markup for the dog name and carry different columns, so
keep both when you refresh them.

Two details are easy to regress, and each has a test guarding it:

- The box number is not text. It is the rug graphic's name attribute,
  `<sprite-svg name="rug_4">`.
- A cell's text usually lives in a nested link or span, so reading `.text`
  returns an empty string. Use `node_text()` from `parsers/_common.py`.

## Notes

- Requests are throttled to one per second by default. Leave it there.
- Pages are cached for 10 minutes, so re-runs while you're iterating don't
  re-hit the site. `--no-cache` bypasses it.
- Start on `--fetcher fetcher`. Only move to `stealthy` if you start getting
  blocked; it's an order of magnitude slower.
- Odds shown on the site are the site's own display prices, useful as a
  sanity check but not a pricing source.

## harness.org.au fields (`harness_scraper`)

Full field of every Australian harness race for a date, one row per runner.

    python -m harness_scraper scrape --date 2026-10-06
    python -m harness_scraper scrape --state NSW,VIC --include-trials
    python -m harness_scraper scrape --date 2026-10-06 --from-raw     # re-parse saved JSON, no network
    python -m harness_scraper scrape --headful                        # watch the browser

The site is a JavaScript app behind Cloudflare, so pages load in a real browser
(Scrapling `StealthySession`) and the JSON the page itself requests from
`api.harness.org.au` is captured - we never call the API directly. One page load
per meeting is enough: `/racing/{meetingCode}/` holds every race and runner.
If that capture fails it loads each race page, and if that fails too it parses
the rendered runner grid.

Output: `data/harness/{date}/fields.csv` (one row per runner) and `fields.json` (nested meetings > races > runners); raw API JSON per race in
`data/raw/{date}/{raceId}.json`. Settings: the `harness:` block in `config.yaml`.

Refresh test fixtures (needs access to the site) and run the tests:

    python tools/dump_harness.py --date <today> --meeting <code> --race-no 4
    python tools/inspect_harness_json.py tests/fixtures/harness/meeting_api.json
    python -m pytest tests

TODO (out of scope for now): form tab, gear changes, scratchings tab, the
per-meeting `.rtf` form guide (`form_rtf` in the meeting JSON), comparison and
Slack alerts.

### Harness from the RBHQ feed

    python -m rbhq_scraper --harness --date today --save-response raw_h.json

Requests race type `H` and writes `data/harness/{date}/rbhq_fields.{csv,json}`
in the same columns as `harness_scraper`'s `fields.*`, so the two can be diffed.
**The field mapping is unverified** (`rbhq_scraper/harness_mapper.py`) - capture a
real response with `--save-response` and check it before relying on it.
`field_compare` is still greyhound-only.

### Harness field comparison

    python -m field_compare --harness --date today
    python -m field_compare --harness --reference-file data/harness/2026-10-06/fields.json --ours-file raw_h.json

Checks the RBHQ harness field (ours) against harness.org.au: race exists, runner in the field, runner in the right race (matched on horse name + race number). Writes `data/harness/{date}/discrepancies.json`; exit 1 on any critical. Venue spelling differences go in `harness_track_aliases.yaml`.
