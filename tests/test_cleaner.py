from src.processing import cleaner


def test_clean_text_removes_urls():
    assert cleaner.clean_text("check this out https://vogue.com/article") == "check this out"


def test_clean_text_removes_html_tags():
    assert cleaner.clean_text("<p>oversized <b>blazers</b></p>") == "oversized blazers"


def test_clean_text_normalises_unicode():
    assert cleaner.clean_text("café society") == "cafe society"


def test_clean_text_lowercases():
    assert cleaner.clean_text("BARBIECORE Is Back") == "barbiecore is back"


def test_clean_text_strips_special_characters():
    assert cleaner.clean_text("Y2K!! #streetwear @user") == "y2k streetwear user"


def test_content_hash_is_stable_for_identical_text():
    assert cleaner.content_hash("oversized blazers") == cleaner.content_hash("oversized blazers")


def test_content_hash_differs_for_different_text():
    assert cleaner.content_hash("oversized blazers") != cleaner.content_hash("cargo pants")


def test_dedupe_content_removes_duplicate_urls():
    rows = [
        {"url": "https://a.com/1", "body": "text one"},
        {"url": "https://a.com/1", "body": "text one duplicate"},
        {"url": "https://a.com/2", "body": "text two"},
    ]
    deduped = cleaner.dedupe_content(rows)
    assert len(deduped) == 2
    assert {r["url"] for r in deduped} == {"https://a.com/1", "https://a.com/2"}


def test_dedupe_content_removes_duplicate_body_text():
    rows = [
        {"url": "https://a.com/1", "body": "same body text"},
        {"url": "https://a.com/2", "body": "same body text"},
    ]
    deduped = cleaner.dedupe_content(rows)
    assert len(deduped) == 1
