import pytest

from src.storage import db

EXPECTED_TABLES = {
    "raw_content",
    "keywords",
    "categories",
    "trend_signals",
    "google_trends",
    "brands",
    "brand_mentions",
}


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_fashion_trends.db")


def test_init_db_creates_all_tables(db_path):
    engine = db.init_db(db_path)
    assert EXPECTED_TABLES.issubset(set(db.get_table_names(engine)))


def test_init_db_is_idempotent(db_path):
    engine1 = db.init_db(db_path)
    engine2 = db.init_db(db_path)
    assert set(db.get_table_names(engine1)) == set(db.get_table_names(engine2))


def test_insert_and_retrieve_raw_content(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(
        engine,
        source="reddit",
        source_id="abc123",
        url="https://reddit.com/r/femalefashionadvice/abc123",
        title="Loving oversized blazers rn",
        body="anyone else obsessed with oversized blazers this fall",
        author="throwaway_fash",
    )
    assert content_id is not None

    rows = db.get_raw_content_by_source(engine, "reddit")
    assert len(rows) == 1
    assert rows[0]["title"] == "Loving oversized blazers rn"


def test_insert_and_retrieve_google_trend(db_path):
    engine = db.init_db(db_path)
    db.insert_google_trend(
        engine, keyword="oversized", date="2026-09-01", interest_value=72, geo="IN"
    )

    rows = db.get_google_trends_by_keyword(engine, "oversized")
    assert len(rows) == 1
    assert rows[0]["interest_value"] == 72


def test_get_all_raw_content_returns_every_row(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="reddit", title="post one")
    db.insert_raw_content(engine, source="news", title="article one")

    rows = db.get_all_raw_content(engine)
    assert len(rows) == 2
    assert {r["title"] for r in rows} == {"post one", "article one"}


def test_insert_and_retrieve_keywords(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title="oversized blazers trend")

    db.insert_keyword(
        engine, content_id=content_id, keyword="oversized", keyword_type="Silhouettes", confidence=1.0
    )
    db.insert_keyword(
        engine, content_id=content_id, keyword="blazers", keyword_type="emerging", confidence=0.6
    )

    rows = db.get_keywords_by_content_id(engine, content_id)
    assert len(rows) == 2
    assert {r["keyword"] for r in rows} == {"oversized", "blazers"}


def test_delete_keywords_for_content_removes_only_that_contents_rows(db_path):
    engine = db.init_db(db_path)
    content_id_1 = db.insert_raw_content(engine, source="news", title="post one")
    content_id_2 = db.insert_raw_content(engine, source="news", title="post two")
    db.insert_keyword(engine, content_id=content_id_1, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)
    db.insert_keyword(engine, content_id=content_id_2, keyword="denim", keyword_type="Patterns & Textures", confidence=1.0)

    db.delete_keywords_for_content(engine, content_id_1)

    assert db.get_keywords_by_content_id(engine, content_id_1) == []
    assert len(db.get_keywords_by_content_id(engine, content_id_2)) == 1
