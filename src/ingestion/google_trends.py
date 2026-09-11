"""Google Trends ingester: pulls interest-over-time for tracked fashion keywords.

Run: daily at 6am (see scheduler/cron_jobs.py).
No API key required — pytrends scrapes the public Google Trends endpoint.
"""

import time

from loguru import logger
from pytrends.request import TrendReq

from src.storage import db

RATE_LIMIT_SECONDS = 5
DEFAULT_GEO = "IN"
DEFAULT_TIMEFRAME = "today 3-m"  # ~90 day rolling window

DEFAULT_KEYWORDS = [
    "oversized",
    "barbiecore",
    "cargo pants",
    "Y2K",
    "quiet luxury",
    # Colours (added for Page 4: Colour Trends -- CLAUDE.md Section 8.2)
    "black",
    "white",
    "beige",
    "brown",
    "red",
    "pink",
    "blue",
    "green",
    "purple",
    "yellow",
]


def fetch_keyword_interest(pytrends: TrendReq, keyword: str, geo: str = DEFAULT_GEO) -> list[dict]:
    """Fetch daily interest-over-time for one keyword. Returns a list of {date, interest_value}."""
    pytrends.build_payload([keyword], timeframe=DEFAULT_TIMEFRAME, geo=geo)
    data = pytrends.interest_over_time()
    if data.empty:
        return []
    return [
        {"date": str(idx.date()), "interest_value": int(row[keyword])}
        for idx, row in data.iterrows()
    ]


def run(keywords: list[str] | None = None, geo: str = DEFAULT_GEO) -> int:
    """Ingest Google Trends interest-over-time for each keyword into the google_trends table.

    Continues past individual keyword failures instead of crashing the whole run.
    Returns the number of rows inserted.
    """
    keywords = keywords or DEFAULT_KEYWORDS
    engine = db.init_db()
    pytrends = TrendReq(hl="en-US", tz=330)

    rows_inserted = 0
    for i, keyword in enumerate(keywords):
        try:
            points = fetch_keyword_interest(pytrends, keyword, geo=geo)
            # Re-fetches the full rolling window every run, so replace (not
            # accumulate) this keyword's existing rows to stay idempotent.
            db.delete_google_trends_by_keyword(engine, keyword, geo=geo)
            for point in points:
                db.insert_google_trend(
                    engine,
                    keyword=keyword,
                    date=point["date"],
                    interest_value=point["interest_value"],
                    geo=geo,
                )
            rows_inserted += len(points)
            logger.info("Ingested {} points for keyword '{}'", len(points), keyword)
        except Exception:
            logger.exception("Failed to ingest Google Trends data for keyword '{}'", keyword)

        if i < len(keywords) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    logger.info("Google Trends ingestion complete: {} rows inserted", rows_inserted)
    return rows_inserted


if __name__ == "__main__":
    run()
