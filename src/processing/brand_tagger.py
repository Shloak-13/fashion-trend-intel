"""Brand mention tagging for Page 5 (Brand Monitor): detects seeded brand
names in raw_content text and computes real per-mention sentiment.

CLAUDE.md Section 6.2 Step 4 (NER for brands) was never built (see
nlp_pipeline.py's docstring -- deferred to a later iteration, same as
sentiment/Step 5). This is a lighter-weight substitute: word-boundary,
case-insensitive matching against a fixed brand seed list, rather than a
general-purpose NER model. It won't catch brands outside BRAND_SEED, but
what it does report is real (an actual name match in real text), and
sentiment is a real TextBlob polarity score on that same text, not a
fabricated number.
"""

import re

from loguru import logger
from textblob import TextBlob

from src.storage import db

# (display name, tier, match term). match_term defaults to the display name
# when omitted -- only set separately where the two need to differ (e.g. to
# match "Levi's" in running text via the stem "Levi").
BRAND_SEED = [
    ("Zara", "fast-fashion", None),
    ("H&M", "fast-fashion", None),
    ("Shein", "fast-fashion", None),
    ("Uniqlo", "fast-fashion", None),
    ("Gucci", "luxury", None),
    ("Prada", "luxury", None),
    ("Chanel", "luxury", None),
    ("Louis Vuitton", "luxury", None),
    ("Dior", "luxury", None),
    ("Balenciaga", "luxury", None),
    ("Burberry", "luxury", None),
    ("Versace", "luxury", None),
    ("Fendi", "luxury", None),
    ("Miu Miu", "luxury", None),
    ("Coach", "premium", None),
    ("Marc Jacobs", "premium", None),
    ("Calvin Klein", "premium", None),
    ("Ralph Lauren", "premium", None),
    ("Tommy Hilfiger", "premium", None),
    ("Stuart Weitzman", "premium", None),
    ("Amiri", "premium", None),
    ("Levi's", "mid", "Levi"),
    ("Nike", "mid", None),
    ("Adidas", "mid", None),
    ("Puma", "mid", None),
    ("Reebok", "mid", None),
    ("Vans", "mid", None),
    ("Converse", "mid", None),
    ("Supreme", "indie", None),
    ("Stussy", "indie", None),
    ("Beams", "indie", None),
]

_BRAND_PATTERNS = [
    (name, re.compile(r"\b" + re.escape(match_term or name) + r"\b", re.IGNORECASE))
    for name, _tier, match_term in BRAND_SEED
]


def seed_brands(engine) -> None:
    """Insert one brands row per BRAND_SEED entry, if not already present.
    Safe to call repeatedly."""
    for name, tier, _match_term in BRAND_SEED:
        if db.get_brand_id_by_name(engine, name) is None:
            db.insert_brand(engine, name=name, tier=tier)
    logger.info("Seeded {} brands", len(BRAND_SEED))


def detect_brands(text: str) -> list[str]:
    """Return the distinct seeded brand names mentioned in text, in BRAND_SEED
    order. Word-boundary, case-insensitive matching."""
    if not text:
        return []
    return [name for name, pattern in _BRAND_PATTERNS if pattern.search(text)]


def compute_sentiment(text: str) -> float | None:
    """Return TextBlob polarity (-1 to 1) for text, or None if there's no text
    to score (distinct from a real neutral 0.0)."""
    if not text or not text.strip():
        return None
    return TextBlob(text).sentiment.polarity


def process_and_store_content(engine, content_id: int, text: str, published_at: str | None) -> list[dict]:
    """Detect brand mentions in one document and persist them to
    brand_mentions, with a real sentiment score. Replaces any brand mentions
    previously stored for this content_id, so re-tagging is idempotent.
    Returns the list of stored {brand, sentiment} dicts."""
    db.delete_brand_mentions_for_content(engine, content_id)

    brands = detect_brands(text)
    if not brands:
        return []

    sentiment = compute_sentiment(text)
    mention_context = text[:280] if text else None

    stored = []
    for brand in brands:
        brand_id = db.get_brand_id_by_name(engine, brand)
        if brand_id is None:
            continue
        db.insert_brand_mention(
            engine,
            brand_id=brand_id,
            content_id=content_id,
            mention_context=mention_context,
            sentiment=sentiment,
            mentioned_at=published_at,
        )
        stored.append({"brand": brand, "sentiment": sentiment})

    return stored


def run(engine=None) -> int:
    """Seed brands, then tag every raw_content row for brand mentions.
    Continues past per-document failures instead of crashing the whole run.
    Returns the total number of brand mentions stored."""
    engine = engine or db.init_db()
    seed_brands(engine)
    rows = db.get_all_raw_content(engine)

    total_mentions = 0
    for row in rows:
        try:
            text = f"{row.get('title') or ''} {row.get('body') or ''}".strip()
            stored = process_and_store_content(engine, row["id"], text, row.get("published_at"))
            total_mentions += len(stored)
        except Exception:
            logger.exception("Failed to tag brands for raw_content id={}", row["id"])

    logger.info("Brand tagging complete: {} mentions stored", total_mentions)
    return total_mentions


if __name__ == "__main__":
    run()
