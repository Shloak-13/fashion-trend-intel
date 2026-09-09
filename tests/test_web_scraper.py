import json

from protego import Protego

from src.ingestion import web_scraper

# Real robots.txt has two separate `User-agent: *` blocks (checked live before
# writing this scraper). Python's stdlib urllib.robotparser silently drops
# everything but the last such block instead of merging them (confirmed via
# manual inspection of rp.entries/rp.default_entry) — a real correctness bug,
# not a hypothetical one. This fixture reproduces that exact shape so the
# test catches a regression back to stdlib's robotparser.
ROBOTS_TXT_WITH_MULTIPLE_USERAGENT_BLOCKS = """
User-agent: *
Disallow: */comments/*
Disallow: */deals/compare

User-agent: *
Disallow: *searchTerm=*
"""

SAMPLE_HTML = """
<html>
<head>
<title>The Elevated Basic | Who What Wear</title>
<meta property="og:title" content="Better Than a White Tee&mdash;A Polished Basic">
<meta property="og:description" content="If anyone knows how to look chic, it's her.">
<meta property="og:url" content="https://www.whowhatwear.com/fashion/celebrity-style/sample-article">
<meta property="article:published_time" content="2026-09-08T01:00:00Z">
<meta property="article:section" content="Celebrity Style">
<meta property="article:tag" content="Fashion">
<meta property="article:tag" content="Celebrity">
<meta property="article:tag" content="Wardrobe Essentials">
<meta property="mrf:authors" content="Eliza Huber">
</head>
<body><p>Article body text not used.</p></body>
</html>
"""

SAMPLE_HTML_MISSING_FIELDS = """
<html>
<head>
<title>Untitled | Who What Wear</title>
</head>
<body></body>
</html>
"""


def test_extract_article_metadata_parses_all_fields():
    url = "https://www.whowhatwear.com/fashion/celebrity-style/sample-article"
    result = web_scraper.extract_article_metadata(SAMPLE_HTML, url)

    assert result["url"] == url
    assert result["source_id"] == url
    assert result["title"] == "Better Than a White Tee—A Polished Basic"
    assert result["author"] == "Eliza Huber"
    assert result["published_at"] == "2026-09-08T01:00:00Z"
    assert result["body"] == "If anyone knows how to look chic, it's her."


def test_extract_article_metadata_captures_tags_in_raw_json():
    url = "https://www.whowhatwear.com/fashion/celebrity-style/sample-article"
    result = web_scraper.extract_article_metadata(SAMPLE_HTML, url)

    raw = json.loads(result["raw_json"])
    assert raw["tags"] == ["Fashion", "Celebrity", "Wardrobe Essentials"]
    assert raw["section"] == "Celebrity Style"


def test_extract_article_metadata_falls_back_to_title_tag_when_og_title_missing():
    url = "https://www.whowhatwear.com/fashion/untitled"
    result = web_scraper.extract_article_metadata(SAMPLE_HTML_MISSING_FIELDS, url)

    assert result["title"] == "Untitled"


def test_extract_article_metadata_handles_missing_author_and_tags_gracefully():
    url = "https://www.whowhatwear.com/fashion/untitled"
    result = web_scraper.extract_article_metadata(SAMPLE_HTML_MISSING_FIELDS, url)

    assert result["author"] is None
    assert result["published_at"] is None
    assert result["body"] == ""
    raw = json.loads(result["raw_json"])
    assert raw["tags"] == []


SAMPLE_SITEMAP_XML = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
        xmlns:image="http://www.google.com/schemas/sitemap-image/1.1"
        xmlns:news="http://www.google.com/schemas/sitemap-news/0.9">
<url>
<loc>https://www.whowhatwear.com/fashion/article-one</loc>
<news:news><news:title>Article One</news:title></news:news>
<image:image><image:loc>https://cdn.mos.cms.futurecdn.net/imageone.png</image:loc></image:image>
</url>
<url>
<loc>https://www.whowhatwear.com/fashion/article-two</loc>
<news:news><news:title>Article Two</news:title></news:news>
<image:image><image:loc>https://cdn.mos.cms.futurecdn.net/imagetwo.jpg</image:loc></image:image>
</url>
</urlset>
"""


def test_parse_sitemap_article_urls_excludes_image_locs():
    urls = web_scraper.parse_sitemap_article_urls(SAMPLE_SITEMAP_XML)
    assert urls == [
        "https://www.whowhatwear.com/fashion/article-one",
        "https://www.whowhatwear.com/fashion/article-two",
    ]
    assert not any("cdn.mos.cms.futurecdn.net" in u for u in urls)


def test_can_fetch_merges_rules_across_multiple_useragent_blocks():
    rp = Protego.parse(ROBOTS_TXT_WITH_MULTIPLE_USERAGENT_BLOCKS)

    assert web_scraper.can_fetch(
        "https://www.whowhatwear.com/fashion/some-article", rp
    ) is True
    assert web_scraper.can_fetch(
        "https://www.whowhatwear.com/fashion/some-article/comments/123", rp
    ) is False
    assert web_scraper.can_fetch(
        "https://www.whowhatwear.com/deals/compare/x", rp
    ) is False
    assert web_scraper.can_fetch(
        "https://www.whowhatwear.com/search?searchTerm=blazer", rp
    ) is False
