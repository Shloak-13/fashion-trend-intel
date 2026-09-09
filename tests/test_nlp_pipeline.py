import pytest

from src.processing import nlp_pipeline
from src.storage import db

FASHION_TEXT_EN = (
    "Oversized blazers are everywhere this fall, paired with wide leg trousers "
    "and chunky loafers. Quiet luxury is still dominating street style."
)
FASHION_TEXT_FR = "Les blazers oversize sont partout cet automne, avec des pantalons larges."


def test_is_english_detects_english_text():
    assert nlp_pipeline.is_english(FASHION_TEXT_EN) is True


def test_is_english_detects_non_english_text():
    assert nlp_pipeline.is_english(FASHION_TEXT_FR) is False


def test_is_english_handles_empty_text_without_crashing():
    assert nlp_pipeline.is_english("") is False


def test_extract_keywords_returns_relevant_fashion_terms():
    keywords = nlp_pipeline.extract_keywords(FASHION_TEXT_EN, top_n=5)
    assert 1 <= len(keywords) <= 5
    assert all("keyword" in k and "score" in k for k in keywords)
    found = " ".join(k["keyword"] for k in keywords).lower()
    assert "blazer" in found or "oversized" in found or "luxury" in found


def test_process_document_skips_extraction_for_non_english():
    result = nlp_pipeline.process_document(FASHION_TEXT_FR)
    assert result["language"] != "en"
    assert result["keywords"] == []


def test_process_document_extracts_keywords_for_english():
    result = nlp_pipeline.process_document(FASHION_TEXT_EN)
    assert result["language"] == "en"
    assert len(result["keywords"]) > 0
    assert result["cleaned_text"] == nlp_pipeline.cleaner.clean_text(FASHION_TEXT_EN)


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_nlp_pipeline.db")


def test_process_and_store_content_persists_keywords(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title=FASHION_TEXT_EN)

    stored = nlp_pipeline.process_and_store_content(engine, content_id, FASHION_TEXT_EN)

    assert len(stored) > 0
    rows = db.get_keywords_by_content_id(engine, content_id)
    assert len(rows) == len(stored)
    assert {r["keyword"] for r in rows} == {kw["keyword"] for kw in stored}


def test_process_and_store_content_is_idempotent(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title=FASHION_TEXT_EN)

    nlp_pipeline.process_and_store_content(engine, content_id, FASHION_TEXT_EN)
    nlp_pipeline.process_and_store_content(engine, content_id, FASHION_TEXT_EN)

    rows = db.get_keywords_by_content_id(engine, content_id)
    assert len(rows) == len(nlp_pipeline.extract_keywords(FASHION_TEXT_EN))


def test_process_and_store_content_skips_non_english(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title=FASHION_TEXT_FR)

    stored = nlp_pipeline.process_and_store_content(engine, content_id, FASHION_TEXT_FR)

    assert stored == []
    assert db.get_keywords_by_content_id(engine, content_id) == []


def test_run_processes_all_raw_content(db_path):
    engine = db.init_db(db_path)
    id1 = db.insert_raw_content(engine, source="news", title=FASHION_TEXT_EN)
    id2 = db.insert_raw_content(engine, source="news", title=FASHION_TEXT_FR)

    total_keywords = nlp_pipeline.run(engine=engine)

    assert total_keywords > 0
    assert len(db.get_keywords_by_content_id(engine, id1)) > 0
    assert len(db.get_keywords_by_content_id(engine, id2)) == 0
