import pytest

from src.processing import categoriser
from src.storage import db


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_categoriser.db")


def test_seed_categories_inserts_one_row_per_taxonomy_group(db_path):
    engine = db.init_db(db_path)
    categoriser.seed_categories(engine)
    with engine.connect() as conn:
        from sqlalchemy import text

        names = {row[0] for row in conn.execute(text("SELECT name FROM categories"))}
    assert names == set(categoriser.TAXONOMY.keys())


def test_seed_categories_is_idempotent(db_path):
    engine = db.init_db(db_path)
    categoriser.seed_categories(engine)
    categoriser.seed_categories(engine)
    with engine.connect() as conn:
        from sqlalchemy import text

        count = conn.execute(text("SELECT COUNT(*) FROM categories")).scalar()
    assert count == len(categoriser.TAXONOMY)


def test_exact_match_finds_known_keyword():
    assert categoriser.exact_match("oversized") == "Silhouettes"


def test_exact_match_is_case_insensitive():
    assert categoriser.exact_match("BARBIECORE") == "Aesthetics"


def test_exact_match_returns_none_for_unknown_keyword():
    assert categoriser.exact_match("some_made_up_term_xyz") is None


def test_fuzzy_match_finds_close_variant_above_threshold():
    # "oversize" is a close variant of "oversized"
    assert categoriser.fuzzy_match("oversize") == "Silhouettes"


def test_fuzzy_match_returns_none_below_threshold():
    assert categoriser.fuzzy_match("completely unrelated phrase") is None


def test_categorise_keyword_exact_match():
    result = categoriser.categorise_keyword("cargo pants")
    assert result["category"] == "Clothing Items"
    assert result["match_type"] == "exact"
    assert result["confidence"] == 1.0


def test_categorise_keyword_fuzzy_match():
    result = categoriser.categorise_keyword("cargo pant")  # missing trailing 's'
    assert result["category"] == "Clothing Items"
    assert result["match_type"] == "fuzzy"
    assert result["confidence"] >= 0.85


def test_categorise_keyword_unmatched_is_emerging():
    result = categoriser.categorise_keyword("some_brand_new_micro_trend_2026")
    assert result["category"] is None
    assert result["match_type"] == "emerging"
