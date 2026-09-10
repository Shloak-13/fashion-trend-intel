"""SQLite/PostgreSQL connection and query helpers for the fashion trend pipeline."""

import os
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger
from sqlalchemy import create_engine, inspect, text

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
