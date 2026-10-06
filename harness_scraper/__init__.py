"""harness.org.au fields scraper - Australian harness racing.

    python -m harness_scraper scrape --date 2026-10-06

The site is a JavaScript app behind Cloudflare, so pages are loaded in a real
browser (Scrapling's StealthyFetcher) and the JSON the page itself requests
from api.harness.org.au is captured off the wire. See scraper.py for the flow.

The card is a `harness_scraper.models.DayCard`. It has the same outer shape as
`dogs_scraper.models.DayCard` (meeting_date / scraped_at / source / meetings /
errors) but harness runners are not greyhounds - saddlecloth, driver, handicap -
so the inner models are this package's own.
"""
