import json

from src.ingestion import news_scraper

SAMPLE_ARTICLE = {
    "source": {"id": None, "name": "Vogue Business"},
    "author": "Jane Doe",
    "title": "Quiet luxury dominates fall runways",
    "description": "A look at how quiet luxury took over fashion week.",
    "url": "https://voguebusiness.com/articles/quiet-luxury-fall",
    "publishedAt": "2026-09-01T12:00:00Z",
    "content": "Full article text truncated by NewsAPI free tier [+2000 chars]",
}


def test_map_article_extracts_expected_fields():
    mapped = news_scraper._map_article(SAMPLE_ARTICLE)
    assert mapped["url"] == SAMPLE_ARTICLE["url"]
    assert mapped["source_id"] == SAMPLE_ARTICLE["url"]
    assert mapped["title"] == SAMPLE_ARTICLE["title"]
    assert mapped["body"] == SAMPLE_ARTICLE["description"]
    assert mapped["author"] == "Jane Doe"
    assert mapped["published_at"] == SAMPLE_ARTICLE["publishedAt"]


def test_map_article_preserves_full_payload_in_raw_json():
    mapped = news_scraper._map_article(SAMPLE_ARTICLE)
    assert json.loads(mapped["raw_json"]) == SAMPLE_ARTICLE


def test_map_article_handles_missing_author_and_description():
    article = dict(SAMPLE_ARTICLE)
    article["author"] = None
    article["description"] = None
    mapped = news_scraper._map_article(article)
    assert mapped["author"] is None
    assert mapped["body"] == ""
