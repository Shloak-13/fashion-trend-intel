from src.processing import nlp_pipeline

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
