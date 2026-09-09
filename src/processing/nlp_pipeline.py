"""NLP processing steps 1-3 from CLAUDE.md Section 6.2: cleaning, language
detection, and keyword extraction. NER (step 4) and sentiment (step 5) are
deferred to a later iteration per the Phase 2 build order ("keyword
extraction only first") — see CLAUDE.md Section 13.
"""

from functools import lru_cache

from keybert import KeyBERT
from langdetect import LangDetectException, detect
from loguru import logger

from src.processing import categoriser, cleaner
from src.processing.categoriser import TAXONOMY
from src.storage import db

KEYBERT_MODEL_NAME = "all-MiniLM-L6-v2"
DEFAULT_TOP_N = 10

SEED_KEYWORDS = [kw for keywords in TAXONOMY.values() for kw in keywords]


def is_english(text: str) -> bool:
    """Return True if text is detected as English. Empty/undetectable text is False."""
    if not text or not text.strip():
        return False
    try:
        return detect(text) == "en"
    except LangDetectException:
        return False


@lru_cache(maxsize=1)
def _keybert_model() -> KeyBERT:
    return KeyBERT(model=KEYBERT_MODEL_NAME)


def extract_keywords(text: str, top_n: int = DEFAULT_TOP_N) -> list[dict]:
    """Extract up to top_n fashion-relevant keywords/phrases from text using KeyBERT,
    seeded with the taxonomy vocabulary. Returns [{"keyword": str, "score": float}]."""
    if not text or not text.strip():
        return []

    model = _keybert_model()
    results = model.extract_keywords(
        text,
        keyphrase_ngram_range=(1, 2),
        stop_words="english",
        top_n=top_n,
        seed_keywords=SEED_KEYWORDS,
    )
    return [{"keyword": kw, "score": round(score, 4)} for kw, score in results]


def process_document(text: str) -> dict:
    """Run cleaning, language detection, and (English-only) keyword extraction on a
    document. Non-English documents are flagged and skipped for extraction — v1 is
    English-only per CLAUDE.md's known limitations (v2 expands language coverage)."""
    cleaned = cleaner.clean_text(text)
    language = "en" if is_english(text) else "other"

    if language != "en":
        logger.info("Skipping keyword extraction for non-English document")
        return {"cleaned_text": cleaned, "language": language, "keywords": []}

    keywords = extract_keywords(text)
    return {"cleaned_text": cleaned, "language": language, "keywords": keywords}


def process_and_store_content(engine, content_id: int, text: str) -> list[dict]:
    """Run the NLP pipeline on one document and persist its keywords to the
    keywords table, categorised against the taxonomy. Replaces any keywords
    previously extracted for this content_id, so re-processing is idempotent.
    Returns the list of stored {keyword, keyword_type, confidence} dicts.
    """
    result = process_document(text)
    db.delete_keywords_for_content(engine, content_id)

    stored = []
    for kw in result["keywords"]:
        match = categoriser.categorise_keyword(kw["keyword"])
        keyword_type = match["category"] or "emerging"
        confidence = match["confidence"] if match["confidence"] is not None else kw["score"]
        db.insert_keyword(
            engine,
            content_id=content_id,
            keyword=kw["keyword"],
            keyword_type=keyword_type,
            confidence=confidence,
        )
        stored.append({"keyword": kw["keyword"], "keyword_type": keyword_type, "confidence": confidence})

    return stored


def run(engine=None) -> int:
    """Process every raw_content row through the NLP pipeline, extracting and
    persisting keywords. Continues past per-document failures instead of
    crashing the whole run. Returns the total number of keywords stored."""
    engine = engine or db.init_db()
    rows = db.get_all_raw_content(engine)

    total_keywords = 0
    emerging_count = 0
    for row in rows:
        try:
            text = f"{row.get('title') or ''} {row.get('body') or ''}".strip()
            stored = process_and_store_content(engine, row["id"], text)
            total_keywords += len(stored)
            emerging_count += sum(1 for kw in stored if kw["keyword_type"] == "emerging")
        except Exception:
            logger.exception("Failed to process raw_content id={}", row["id"])

    logger.info(
        "NLP pipeline complete: {} keywords stored ({} matched taxonomy, {} emerging)",
        total_keywords,
        total_keywords - emerging_count,
        emerging_count,
    )
    return total_keywords


if __name__ == "__main__":
    run()
