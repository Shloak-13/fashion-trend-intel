"""NLP processing steps 1-3 from CLAUDE.md Section 6.2: cleaning, language
detection, and keyword extraction. NER (step 4) and sentiment (step 5) are
deferred to a later iteration per the Phase 2 build order ("keyword
extraction only first") — see CLAUDE.md Section 13.
"""

from functools import lru_cache

from keybert import KeyBERT
from langdetect import LangDetectException, detect
from loguru import logger

from src.processing import cleaner
from src.processing.categoriser import TAXONOMY

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
