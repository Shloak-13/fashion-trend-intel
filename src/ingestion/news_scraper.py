"""NewsAPI ingester: pulls fashion news articles into raw_content.

Run: daily at 7am (see scheduler/cron_jobs.py).
Requires NEWS_API_KEY in .env (free tier at newsapi.org, 100 req/day).

NOTE: CLAUDE.md Section 7.3 specifies filtering by
sources=vogue,elle,harpersbazaar,businessoffashion. None of these exist as
NewsAPI source IDs — confirmed via client.get_sources(): NewsAPI's ~125
registered sources skew toward general news/tech/business, with no
fashion-specific publishers at all. Passing an invalid `sources` param
errors the whole request, so this ingester queries by keyword only, relying
on `q` to surface fashion-relevant coverage from NewsAPI's full index rather
than a curated source allowlist.

NOTE: the spec's QUERIES list also included ambiguous single words —
"runway" (matches airport/aircraft runways) and "designer" (matches
software/game/interior designers) — which measurably dominated the noise in
the first real ingestion run (only 20% of 133 articles had any
fashion-taxonomy-matched keyword; manual review confirmed most were
off-topic: real estate, PyPI packages, Sensex, F1 racing, TV recaps). Below
are the same 8 topics, rephrased as quoted exact phrases (NewsAPI supports
`"..."` for exact-phrase and `AND`/`OR`/`NOT` operators in `q`) so each
query is unambiguous on its own rather than relying on downstream filtering
to compensate for query-level noise.
"""

import json
import os
import time

from loguru import logger
from newsapi import NewsApiClient

from src.processing.cleaner import dedupe_content
from src.storage import db

RATE_LIMIT_SECONDS = 2
PAGE_SIZE = 20

QUERIES = [
    '"fashion trends"',
    '"street style"',
    '"fashion week"',
    '"runway show"',
    '"fashion designer"',
    "Zara AND fashion",
    "H&M AND fashion",
    '"luxury fashion"',
]


class MissingNewsAPIKeyError(RuntimeError):
    """Raised when NEWS_API_KEY is not configured."""


def get_client() -> NewsApiClient:
    """Build a NewsAPI client from NEWS_API_KEY in the environment."""
    api_key = os.getenv("NEWS_API_KEY")
    if not api_key:
        raise MissingNewsAPIKeyError(
            "NEWS_API_KEY must be set in .env. Get a free key at https://newsapi.org."
        )
    return NewsApiClient(api_key=api_key)


def _map_article(article: dict) -> dict:
    """Map a raw NewsAPI article dict into a raw_content-ready dict."""
    return {
        "source_id": article.get("url"),
        "url": article.get("url"),
        "title": article.get("title"),
        "body": article.get("description") or "",
        "author": article.get("author"),
        "published_at": article.get("publishedAt"),
        "raw_json": json.dumps(article),
    }


def fetch_articles_for_query(
    client: NewsApiClient, query: str, page_size: int = PAGE_SIZE
) -> list[dict]:
    """Fetch and map articles for a single query into raw_content-ready dicts."""
    response = client.get_everything(
        q=query, language="en", sort_by="publishedAt", page_size=page_size
    )
    return [_map_article(a) for a in response.get("articles", [])]


def run(queries: list[str] | None = None) -> int:
    """Ingest fashion news articles across all tracked queries into raw_content.

    Deduplicates by URL/body across queries before inserting (the same article
    often surfaces under multiple queries, e.g. "fashion week" and "runway").
    Continues past per-query failures instead of crashing the whole run.
    Returns the number of rows inserted.
    """
    queries = queries or QUERIES
    engine = db.init_db()
    client = get_client()

    all_articles: list[dict] = []
    for i, query in enumerate(queries):
        try:
            articles = fetch_articles_for_query(client, query)
            all_articles.extend(articles)
            logger.info("Fetched {} articles for query '{}'", len(articles), query)
        except Exception:
            logger.exception("Failed to fetch news for query '{}'", query)

        if i < len(queries) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    deduped = dedupe_content(all_articles)
    logger.info("{} articles after dedup (from {} raw)", len(deduped), len(all_articles))

    rows_inserted = 0
    for article in deduped:
        try:
            db.insert_raw_content(engine, source="news", **article)
            rows_inserted += 1
        except Exception:
            logger.exception("Failed to insert article: {}", article.get("url"))

    logger.info("News ingestion complete: {} rows inserted", rows_inserted)
    return rows_inserted


if __name__ == "__main__":
    run()
