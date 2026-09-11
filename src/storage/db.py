"""SQLite/PostgreSQL connection and query helpers for the fashion trend pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import bindparam, create_engine, inspect, text

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

load_dotenv()


def _database_url(db_path: str | None) -> str:
    """Resolve the SQLAlchemy database URL, preferring an explicit path over DATABASE_URL."""
    if db_path:
        return f"sqlite:///{db_path}"
    return os.getenv("DATABASE_URL", "sqlite:///data/fashion_trends.db")


def init_db(db_path: str | None = None):
    """Create the engine and apply schema.sql (idempotent via CREATE TABLE IF NOT EXISTS)."""
    engine = create_engine(_database_url(db_path))
    schema_sql = SCHEMA_PATH.read_text()
    with engine.begin() as conn:
        for statement in schema_sql.split(";"):
            statement = statement.strip()
            if statement:
                conn.execute(text(statement))
    logger.info("Database initialised at {}", engine.url)
    return engine


def get_table_names(engine) -> list[str]:
    """Return the list of table names currently present in the database."""
    return inspect(engine).get_table_names()


def insert_raw_content(
    engine,
    source: str,
    source_id: str | None = None,
    url: str | None = None,
    title: str | None = None,
    body: str | None = None,
    author: str | None = None,
    published_at: str | None = None,
    raw_json: str | None = None,
) -> int:
    """Insert a row into raw_content and return its new id."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO raw_content
                    (source, source_id, url, title, body, author, published_at, raw_json)
                VALUES
                    (:source, :source_id, :url, :title, :body, :author, :published_at, :raw_json)
                """
            ),
            {
                "source": source,
                "source_id": source_id,
                "url": url,
                "title": title,
                "body": body,
                "author": author,
                "published_at": published_at,
                "raw_json": raw_json,
            },
        )
        return result.lastrowid


def get_all_raw_content(engine) -> list[dict]:
    """Return every raw_content row, as a list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM raw_content"))
        return [dict(row._mapping) for row in result]


def get_raw_content_filtered(
    engine,
    source: str | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    search: str | None = None,
) -> list[dict]:
    """Return raw_content rows (excluding the raw_json blob), newest
    published first, optionally filtered by source, a published_at range,
    and/or a case-insensitive substring search over title/body. Filters
    combine with AND."""
    conditions = []
    params: dict = {}

    if source:
        conditions.append("source = :source")
        params["source"] = source
    if published_after:
        conditions.append("published_at >= :published_after")
        params["published_after"] = published_after
    if published_before:
        conditions.append("published_at <= :published_before")
        params["published_before"] = published_before
    if search:
        conditions.append("(LOWER(title) LIKE :search OR LOWER(body) LIKE :search)")
        params["search"] = f"%{search.lower()}%"

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
                SELECT id, source, source_id, url, title, body, author, published_at, ingested_at
                FROM raw_content
                {where_clause}
                ORDER BY published_at DESC
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in result]


def delete_raw_content_by_source(engine, source: str) -> int:
    """Delete all raw_content rows for a given source, along with any keywords
    extracted from them (SQLite doesn't cascade-delete by default). Used to
    clear stale data before a re-run with different ingestion parameters.
    Returns the number of raw_content rows deleted."""
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                DELETE FROM keywords
                WHERE content_id IN (SELECT id FROM raw_content WHERE source = :source)
                """
            ),
            {"source": source},
        )
        result = conn.execute(
            text("DELETE FROM raw_content WHERE source = :source"), {"source": source}
        )
        return result.rowcount


def insert_keyword(
    engine, content_id: int, keyword: str, keyword_type: str, confidence: float | None
) -> int:
    """Insert a row into keywords and return its new id."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO keywords (content_id, keyword, keyword_type, confidence)
                VALUES (:content_id, :keyword, :keyword_type, :confidence)
                """
            ),
            {
                "content_id": content_id,
                "keyword": keyword,
                "keyword_type": keyword_type,
                "confidence": confidence,
            },
        )
        return result.lastrowid


def get_keywords_by_content_id(engine, content_id: int) -> list[dict]:
    """Return all keywords rows extracted for a given raw_content id."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM keywords WHERE content_id = :content_id"),
            {"content_id": content_id},
        )
        return [dict(row._mapping) for row in result]


def delete_keywords_for_content(engine, content_id: int) -> None:
    """Delete all keywords rows for a given raw_content id (used to keep
    re-processing idempotent)."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM keywords WHERE content_id = :content_id"), {"content_id": content_id}
        )


def get_existing_urls(engine, source: str) -> set[str]:
    """Return the set of URLs already ingested for a source, so ingesters can
    filter out duplicates before inserting (raw_content has no unique
    constraint on url, and insert_raw_content doesn't check for one)."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT url FROM raw_content WHERE source = :source AND url IS NOT NULL"),
            {"source": source},
        )
        return {row[0] for row in result}


def get_raw_content_by_source(engine, source: str) -> list[dict]:
    """Return all raw_content rows for a given source, as a list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM raw_content WHERE source = :source"), {"source": source}
        )
        return [dict(row._mapping) for row in result]


def insert_google_trend(
    engine, keyword: str, date: str, interest_value: int, geo: str = "IN"
) -> int:
    """Insert a row into google_trends and return its new id."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO google_trends (keyword, date, interest_value, geo)
                VALUES (:keyword, :date, :interest_value, :geo)
                """
            ),
            {"keyword": keyword, "date": date, "interest_value": interest_value, "geo": geo},
        )
        return result.lastrowid


def get_google_trends_by_keyword(engine, keyword: str) -> list[dict]:
    """Return all google_trends rows for a given keyword, as a list of dicts."""
    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT * FROM google_trends WHERE keyword = :keyword"), {"keyword": keyword}
        )
        return [dict(row._mapping) for row in result]


def get_latest_google_trends(engine, keywords: list[str], geo: str = "IN") -> list[dict]:
    """Return the most recent google_trends row (date, interest_value) for each
    keyword in the given list that has data for the given geo. Batched to avoid
    an N+1 query when rendering many keywords at once (e.g. a colour palette)."""
    if not keywords:
        return []
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT keyword, date, interest_value
                FROM google_trends
                WHERE keyword IN :keywords AND geo = :geo
                    AND date = (
                        SELECT MAX(date) FROM google_trends g2
                        WHERE g2.keyword = google_trends.keyword AND g2.geo = :geo
                    )
                """
            ).bindparams(bindparam("keywords", expanding=True)),
            {"keywords": keywords, "geo": geo},
        )
        return [dict(row._mapping) for row in result]


def delete_google_trends_by_keyword(engine, keyword: str, geo: str = "IN") -> int:
    """Delete all google_trends rows for a given keyword/geo. Used to keep
    re-ingestion idempotent (google_trends.py re-fetches the full rolling
    window every run, so stale rows should be replaced, not accumulated).
    Returns the number of rows deleted."""
    with engine.begin() as conn:
        result = conn.execute(
            text("DELETE FROM google_trends WHERE keyword = :keyword AND geo = :geo"),
            {"keyword": keyword, "geo": geo},
        )
        return result.rowcount


# --- Dashboard query helpers (Phase 4, Trend Radar) ---


def get_top_keywords(
    engine,
    category: str | None = None,
    source: str | None = None,
    published_after: str | None = None,
    published_before: str | None = None,
    min_confidence: float = 0.6,
    min_source_diversity: int = 1,
    limit: int = 20,
) -> list[dict]:
    """Return the top taxonomy-matched keywords ranked by mention count, with
    source diversity and average match confidence. Always excludes
    keyword_type='emerging' (those are unmatched/novel terms, not trending
    taxonomy categories).

    min_confidence filters individual keyword *mentions* (rows), not the
    per-keyword average — same per-match threshold semantics as
    categoriser.py's FUZZY_THRESHOLD/SEMANTIC_THRESHOLD. Default 0.6 exists
    to drop low-confidence KeyBERT bigram artifacts (e.g. "york fashion"
    from "New York Fashion Week") whose *average* confidence can clear a
    naive aggregate cutoff even though most individual mentions don't.

    min_source_diversity filters on the aggregated source count (a HAVING
    clause, not WHERE, since it's evaluated post-GROUP BY) — requiring a
    keyword to be corroborated by more than one outlet before counting as a
    real trend, not a single publication's idiosyncratic phrasing. Default 1
    keeps existing single-source-tolerant behaviour; the dashboard passes 2.

    Filters are optional and combine with AND."""
    conditions = ["k.keyword_type != 'emerging'", "k.confidence >= :min_confidence"]
    params: dict = {
        "limit": limit,
        "min_confidence": min_confidence,
        "min_source_diversity": min_source_diversity,
    }

    if category:
        conditions.append("k.keyword_type = :category")
        params["category"] = category
    if source:
        conditions.append("rc.source = :source")
        params["source"] = source
    if published_after:
        conditions.append("rc.published_at >= :published_after")
        params["published_after"] = published_after
    if published_before:
        conditions.append("rc.published_at <= :published_before")
        params["published_before"] = published_before

    where_clause = " AND ".join(conditions)

    with engine.connect() as conn:
        result = conn.execute(
            text(
                f"""
                SELECT
                    k.keyword AS keyword,
                    k.keyword_type AS category,
                    COUNT(*) AS mention_count,
                    COUNT(DISTINCT rc.source) AS source_diversity,
                    AVG(k.confidence) AS avg_confidence
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE {where_clause}
                GROUP BY k.keyword, k.keyword_type
                HAVING COUNT(DISTINCT rc.source) >= :min_source_diversity
                ORDER BY mention_count DESC
                LIMIT :limit
                """
            ),
            params,
        )
        return [dict(row._mapping) for row in result]


def get_available_sources(engine) -> list[str]:
    """Return the distinct raw_content sources currently ingested, sorted."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT DISTINCT source FROM raw_content ORDER BY source"))
        return [row[0] for row in result]


def get_all_trend_signals(engine) -> list[dict]:
    """Return every trend_signals row (real Google-Trends-backed momentum data)."""
    with engine.connect() as conn:
        result = conn.execute(text("SELECT * FROM trend_signals ORDER BY momentum_score DESC"))
        return [dict(row._mapping) for row in result]


def get_last_updated(engine) -> str | None:
    """Return the most recent raw_content.ingested_at timestamp, or None if
    raw_content is empty."""
    with engine.connect() as conn:
        return conn.execute(text("SELECT MAX(ingested_at) FROM raw_content")).scalar()


# --- Dashboard query helpers (Phase 4, Page 2: Keyword Deep Dive) ---


def get_all_keyword_names(engine) -> list[str]:
    """Return every distinct keyword in the keywords table (matched and
    emerging alike — this is for a free-text search box, not a curated
    trending list), most-mentioned first."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT keyword, COUNT(*) AS n
                FROM keywords
                GROUP BY keyword
                ORDER BY n DESC, keyword ASC
                """
            )
        )
        return [row[0] for row in result]


def get_keyword_time_series(engine, keyword: str) -> list[dict]:
    """Return daily mention counts for a keyword across all sources, ordered
    by date. Grouped on raw_content.published_at (real dates), not
    keywords.extracted_at (always "now" — see get_top_keywords for why)."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT date(rc.published_at) AS date, COUNT(*) AS mention_count
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE LOWER(k.keyword) = LOWER(:keyword) AND rc.published_at IS NOT NULL
                GROUP BY date(rc.published_at)
                ORDER BY date
                """
            ),
            {"keyword": keyword},
        )
        return [dict(row._mapping) for row in result]


def get_keyword_source_breakdown(engine, keyword: str) -> list[dict]:
    """Return mention counts per source for a keyword, most-mentioned first."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT rc.source AS source, COUNT(*) AS mention_count
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE LOWER(k.keyword) = LOWER(:keyword)
                GROUP BY rc.source
                ORDER BY mention_count DESC
                """
            ),
            {"keyword": keyword},
        )
        return [dict(row._mapping) for row in result]


def get_keywords_by_category(
    engine, category: str, min_confidence: float = 0.6, limit: int = 50
) -> list[dict]:
    """Return taxonomy-matched keywords in one category, ranked by mention
    count, with source diversity and the most recent real momentum_score for
    that keyword (NULL for the vast majority of keywords, which only have
    Google-Trends-backed momentum if they're one of the seeded keywords --
    see trend_signals). Same min_confidence semantics as get_top_keywords."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                    k.keyword AS keyword,
                    COUNT(*) AS mention_count,
                    COUNT(DISTINCT rc.source) AS source_diversity,
                    AVG(k.confidence) AS avg_confidence,
                    (
                        SELECT ts.momentum_score FROM trend_signals ts
                        WHERE ts.keyword = k.keyword
                        ORDER BY ts.date DESC
                        LIMIT 1
                    ) AS momentum_score
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE k.keyword_type = :category AND k.confidence >= :min_confidence
                GROUP BY k.keyword
                ORDER BY mention_count DESC
                LIMIT :limit
                """
            ),
            {"category": category, "min_confidence": min_confidence, "limit": limit},
        )
        return [dict(row._mapping) for row in result]


def get_category_week_heatmap(engine, min_confidence: float = 0.6) -> list[dict]:
    """Return mention counts grouped by taxonomy category and week (SQLite
    strftime '%Y-W%W' -- Monday-anchored week-of-year, not ISO-8601 week
    numbering). Excludes 'emerging' keywords, same as get_top_keywords."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                    k.keyword_type AS category,
                    strftime('%Y-W%W', rc.published_at) AS week,
                    COUNT(*) AS mention_count
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE k.keyword_type != 'emerging'
                    AND k.confidence >= :min_confidence
                    AND rc.published_at IS NOT NULL
                GROUP BY k.keyword_type, week
                ORDER BY week, category
                """
            ),
            {"min_confidence": min_confidence},
        )
        return [dict(row._mapping) for row in result]


def get_keyword_recent_mentions(engine, keyword: str, limit: int = 5) -> list[dict]:
    """Return the most recent raw_content rows mentioning a keyword (title,
    url, source, author, published_at), newest first."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT DISTINCT rc.title, rc.url, rc.source, rc.author, rc.published_at
                FROM keywords k
                JOIN raw_content rc ON k.content_id = rc.id
                WHERE LOWER(k.keyword) = LOWER(:keyword)
                ORDER BY rc.published_at DESC
                LIMIT :limit
                """
            ),
            {"keyword": keyword, "limit": limit},
        )
        return [dict(row._mapping) for row in result]


# --- Dashboard query helpers (Phase 4, Page 5: Brand Monitor) ---


def insert_brand(engine, name: str, tier: str | None = None, country_of_origin: str | None = None) -> int:
    """Insert a row into brands and return its new id."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO brands (name, tier, country_of_origin)
                VALUES (:name, :tier, :country_of_origin)
                """
            ),
            {"name": name, "tier": tier, "country_of_origin": country_of_origin},
        )
        return result.lastrowid


def get_brand_id_by_name(engine, name: str) -> int | None:
    """Look up a brand's id by name, case-insensitively. Returns None if unseeded."""
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id FROM brands WHERE LOWER(name) = LOWER(:name)"), {"name": name}
        ).scalar()


def insert_brand_mention(
    engine,
    brand_id: int,
    content_id: int,
    mention_context: str | None,
    sentiment: float | None,
    mentioned_at: str | None,
) -> int:
    """Insert a row into brand_mentions and return its new id."""
    with engine.begin() as conn:
        result = conn.execute(
            text(
                """
                INSERT INTO brand_mentions (brand_id, content_id, mention_context, sentiment, mentioned_at)
                VALUES (:brand_id, :content_id, :mention_context, :sentiment, :mentioned_at)
                """
            ),
            {
                "brand_id": brand_id,
                "content_id": content_id,
                "mention_context": mention_context,
                "sentiment": sentiment,
                "mentioned_at": mentioned_at,
            },
        )
        return result.lastrowid


def delete_brand_mentions_for_content(engine, content_id: int) -> None:
    """Delete all brand_mentions rows for a given raw_content id (used to keep
    re-tagging idempotent)."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM brand_mentions WHERE content_id = :content_id"),
            {"content_id": content_id},
        )


def get_top_brands(engine, limit: int = 20) -> list[dict]:
    """Return brands ranked by mention count, with source diversity and average
    sentiment (real TextBlob polarity, -1 to 1 -- see brand_tagger.py). Only
    returns brands with at least one mention."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                    b.name AS brand,
                    b.tier AS tier,
                    COUNT(*) AS mention_count,
                    COUNT(DISTINCT rc.source) AS source_diversity,
                    AVG(bm.sentiment) AS avg_sentiment
                FROM brand_mentions bm
                JOIN brands b ON bm.brand_id = b.id
                JOIN raw_content rc ON bm.content_id = rc.id
                GROUP BY b.id
                ORDER BY mention_count DESC
                LIMIT :limit
                """
            ),
            {"limit": limit},
        )
        return [dict(row._mapping) for row in result]


def get_brand_keyword_cooccurrence(engine, brand_name: str, limit: int = 10) -> list[dict]:
    """Return taxonomy-matched keywords that co-occur with a brand's mentions
    (same content_id), ranked by co-mention count. Excludes 'emerging'
    keywords, same as get_top_keywords."""
    with engine.connect() as conn:
        result = conn.execute(
            text(
                """
                SELECT
                    k.keyword AS keyword,
                    k.keyword_type AS category,
                    COUNT(*) AS co_mention_count
                FROM brand_mentions bm
                JOIN brands b ON bm.brand_id = b.id
                JOIN keywords k ON k.content_id = bm.content_id
                WHERE LOWER(b.name) = LOWER(:brand_name) AND k.keyword_type != 'emerging'
                GROUP BY k.keyword, k.keyword_type
                ORDER BY co_mention_count DESC
                LIMIT :limit
                """
            ),
            {"brand_name": brand_name, "limit": limit},
        )
        return [dict(row._mapping) for row in result]
