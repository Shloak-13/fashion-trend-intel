import pytest

from src.processing import brand_tagger
from src.storage import db


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_brand_tagger.db")


def test_seed_brands_inserts_one_row_per_seed_brand(db_path):
    engine = db.init_db(db_path)
    brand_tagger.seed_brands(engine)

    for name, _tier, _match_term in brand_tagger.BRAND_SEED:
        assert db.get_brand_id_by_name(engine, name) is not None


def test_seed_brands_is_idempotent(db_path):
    engine = db.init_db(db_path)
    brand_tagger.seed_brands(engine)
    brand_tagger.seed_brands(engine)

    rows = db.get_top_brands(engine, limit=1000)
    assert len(rows) == 0  # no mentions yet, but no duplicate brand rows either
    with engine.connect() as conn:
        from sqlalchemy import text

        count = conn.execute(text("SELECT COUNT(*) FROM brands")).scalar()
    assert count == len(brand_tagger.BRAND_SEED)


def test_detect_brands_finds_known_brand_case_insensitive():
    assert brand_tagger.detect_brands("loving this ZARA jacket") == ["Zara"]
    assert brand_tagger.detect_brands("gucci bag of the season") == ["Gucci"]


def test_detect_brands_respects_word_boundaries():
    # "Van" and "Vans" as a brand shouldn't false-positive inside other words.
    assert brand_tagger.detect_brands("we drove in caravans across the desert") == []
    assert brand_tagger.detect_brands("wearing my old Vans today") == ["Vans"]


def test_detect_brands_matches_apostrophe_variant():
    assert brand_tagger.detect_brands("classic Levi's 501s") == ["Levi's"]


def test_detect_brands_returns_empty_for_no_matches():
    assert brand_tagger.detect_brands("a completely unrelated horoscope article") == []
    assert brand_tagger.detect_brands("") == []


def test_detect_brands_dedupes_multiple_mentions_of_same_brand():
    assert brand_tagger.detect_brands("Zara this, Zara that, ZARA everywhere") == ["Zara"]


def test_detect_brands_finds_multiple_distinct_brands():
    found = brand_tagger.detect_brands("Nike and Adidas both dropped new sneakers")
    assert set(found) == {"Nike", "Adidas"}


def test_compute_sentiment_returns_polarity_for_real_text():
    positive = brand_tagger.compute_sentiment("I absolutely love this beautiful stunning dress")
    negative = brand_tagger.compute_sentiment("this is a terrible ugly ruined disaster")
    assert positive > 0
    assert negative < 0


def test_compute_sentiment_returns_none_for_empty_text():
    assert brand_tagger.compute_sentiment("") is None
    assert brand_tagger.compute_sentiment("   ") is None


def test_process_and_store_content_persists_brand_mentions(db_path):
    engine = db.init_db(db_path)
    brand_tagger.seed_brands(engine)
    content_id = db.insert_raw_content(engine, source="news", title="Zara launches lovely new line")

    stored = brand_tagger.process_and_store_content(
        engine, content_id, "Zara launches lovely new line", "2026-09-01T00:00:00Z"
    )

    assert len(stored) == 1
    assert stored[0]["brand"] == "Zara"
    assert stored[0]["sentiment"] > 0

    rows = db.get_top_brands(engine)
    assert rows[0]["brand"] == "Zara"
    assert rows[0]["mention_count"] == 1


def test_process_and_store_content_is_idempotent(db_path):
    engine = db.init_db(db_path)
    brand_tagger.seed_brands(engine)
    content_id = db.insert_raw_content(engine, source="news", title="Zara news")

    brand_tagger.process_and_store_content(engine, content_id, "Zara news", None)
    brand_tagger.process_and_store_content(engine, content_id, "Zara news", None)

    rows = db.get_top_brands(engine)
    assert rows[0]["mention_count"] == 1


def test_process_and_store_content_returns_empty_for_no_brand_mentions(db_path):
    engine = db.init_db(db_path)
    brand_tagger.seed_brands(engine)
    content_id = db.insert_raw_content(engine, source="news", title="unrelated horoscope")

    stored = brand_tagger.process_and_store_content(engine, content_id, "unrelated horoscope", None)

    assert stored == []
    assert db.get_top_brands(engine) == []


def test_run_processes_all_raw_content(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="news", title="Zara drops new collection")
    db.insert_raw_content(engine, source="hypebeast", title="Nike and Adidas collab sneakers")
    db.insert_raw_content(engine, source="news", title="nothing brand-related here")

    total = brand_tagger.run(engine)

    assert total == 3  # 1 Zara + 2 (Nike, Adidas)
    brands = {r["brand"] for r in db.get_top_brands(engine)}
    assert brands == {"Zara", "Nike", "Adidas"}
