"""Maps extracted keywords onto the CLAUDE.md Section 5 fashion taxonomy.

Matching cascade: exact match (fast) -> fuzzy match via rapidfuzz (threshold 85)
-> semantic similarity via sentence-transformers (fallback). Keywords that clear
none of these tiers are "emerging" — new terms not yet in the taxonomy.
"""

from functools import lru_cache

from loguru import logger
from rapidfuzz import fuzz, process
from sentence_transformers import SentenceTransformer, util
from sqlalchemy import text

FUZZY_THRESHOLD = 85
SEMANTIC_THRESHOLD = 0.6
EMBEDDING_MODEL_NAME = "all-MiniLM-L6-v2"

TAXONOMY: dict[str, list[str]] = {
    "Clothing Items": [
        "blouse", "crop top", "corset", "bodysuit", "tank", "shirt", "turtleneck",
        "cardigan", "blazer", "jacket", "coat", "trench", "bomber", "hoodie",
        "sweater", "vest", "jeans", "trousers", "shorts", "skirt", "mini skirt",
        "midi skirt", "maxi skirt", "leggings", "cargo pants", "wide leg",
        "straight leg", "flared", "mini dress", "midi dress", "maxi dress",
        "slip dress", "wrap dress", "shirt dress", "co-ord set", "sneakers",
        "boots", "loafers", "mules", "heels", "platforms", "mary janes",
        "sandals", "ballet flats", "bag", "tote", "shoulder bag", "clutch",
        "crossbody", "belt", "scarf", "hat", "cap", "beret", "jewellery",
        "sunglasses", "watch",
    ],
    "Silhouettes": [
        "oversized", "slim fit", "tailored", "relaxed", "fitted", "boxy",
        "draped", "structured", "fluid", "layered", "asymmetric",
    ],
    "Colours": [
        "beige", "cream", "ecru", "camel", "sand", "white", "off-white",
        "black", "grey", "charcoal", "cobalt blue", "electric blue", "hot pink",
        "fuchsia", "lime green", "tangerine", "cherry red", "lavender",
        "sage green", "dusty pink", "powder blue", "mint", "butter yellow",
    ],
    "Patterns & Textures": [
        "floral", "stripe", "check", "plaid", "houndstooth", "animal print",
        "leopard", "zebra", "snake", "tie-dye", "colour block", "graphic print",
        "abstract", "solid", "burnout velvet", "crochet", "lace", "leather",
        "denim", "linen", "silk", "satin", "velvet", "sequin", "mesh", "knit",
    ],
    "Aesthetics": [
        "quiet luxury", "old money", "streetwear", "y2k", "cottagecore",
        "dark academia", "coastal grandmother", "barbiecore", "gorpcore",
        "bimbocore", "mob wife", "clean girl", "minimalism", "maximalism",
        "avant-garde", "preppy", "grunge", "boho",
    ],
    "Occasions": [
        "workwear", "casual", "evening", "resort", "athleisure", "loungewear",
        "occasion wear", "bridal", "festival",
    ],
}


def seed_categories(engine) -> None:
    """Insert one top-level categories row per taxonomy group (level=1), if not
    already present. Safe to call repeatedly."""
    with engine.begin() as conn:
        existing = {row[0] for row in conn.execute(text("SELECT name FROM categories"))}
        for name in TAXONOMY:
            if name not in existing:
                conn.execute(
                    text("INSERT INTO categories (name, parent_id, level) VALUES (:name, NULL, 1)"),
                    {"name": name},
                )
    logger.info("Seeded {} taxonomy categories", len(TAXONOMY))


def _flat_keywords() -> list[tuple[str, str]]:
    """Return (keyword, category) pairs flattened across the whole taxonomy."""
    return [(kw, category) for category, keywords in TAXONOMY.items() for kw in keywords]


def exact_match(keyword: str) -> str | None:
    """Return the taxonomy category for an exact (case-insensitive) keyword match."""
    keyword = keyword.strip().lower()
    for kw, category in _flat_keywords():
        if kw == keyword:
            return category
    return None


def fuzzy_match(keyword: str, threshold: int = FUZZY_THRESHOLD) -> str | None:
    """Return the taxonomy category for the closest fuzzy match above threshold."""
    keyword = keyword.strip().lower()
    flat = _flat_keywords()
    choices = [kw for kw, _ in flat]
    best = process.extractOne(keyword, choices, scorer=fuzz.ratio)
    if best is None or best[1] < threshold:
        return None
    matched_kw = best[0]
    return next(category for kw, category in flat if kw == matched_kw)


@lru_cache(maxsize=1)
def _embedding_model() -> SentenceTransformer:
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


@lru_cache(maxsize=1)
def _category_embeddings():
    model = _embedding_model()
    categories = list(TAXONOMY.keys())
    category_text = [" ".join(TAXONOMY[c]) for c in categories]
    return categories, model.encode(category_text, convert_to_tensor=True)


def semantic_match(keyword: str, threshold: float = SEMANTIC_THRESHOLD) -> str | None:
    """Return the taxonomy category most semantically similar to keyword, if above threshold."""
    model = _embedding_model()
    categories, category_embeddings = _category_embeddings()
    keyword_embedding = model.encode(keyword, convert_to_tensor=True)
    scores = util.cos_sim(keyword_embedding, category_embeddings)[0]
    best_idx = int(scores.argmax())
    best_score = float(scores[best_idx])
    if best_score < threshold:
        return None
    return categories[best_idx]


def categorise_keyword(keyword: str) -> dict:
    """Map a keyword to a taxonomy category via exact -> fuzzy -> semantic matching.

    Returns {"keyword", "category", "match_type", "confidence"}. Unmatched
    keywords get category=None, match_type="emerging" — these are valuable
    signals of new terms not yet in the taxonomy.
    """
    category = exact_match(keyword)
    if category:
        return {"keyword": keyword, "category": category, "match_type": "exact", "confidence": 1.0}

    category = fuzzy_match(keyword)
    if category:
        score = process.extractOne(
            keyword.strip().lower(), [kw for kw, _ in _flat_keywords()], scorer=fuzz.ratio
        )[1]
        return {
            "keyword": keyword,
            "category": category,
            "match_type": "fuzzy",
            "confidence": round(score / 100, 4),
        }

    category = semantic_match(keyword)
    if category:
        return {"keyword": keyword, "category": category, "match_type": "semantic", "confidence": None}

    logger.info("Keyword '{}' did not match taxonomy — flagged as emerging", keyword)
    return {"keyword": keyword, "category": None, "match_type": "emerging", "confidence": None}
