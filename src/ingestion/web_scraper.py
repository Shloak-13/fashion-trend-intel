"""Web scraper: pulls Who What Wear articles into raw_content.

Run: daily at 8am (see scheduler/cron_jobs.py).
Targets Who What Wear first per CLAUDE.md Section 7.4 (Highsnobiety and
Hypebeast follow later, added to this same module).

robots.txt (https://www.whowhatwear.com/robots.txt, checked before writing
this): `User-agent: *` disallows only deal-comparison pages, embeds,
outlinks, comments, infinite-scroll endpoints, and search/sort/product query
strings — normal article URLs and the sitemap are not disallowed. A named
list of AI-crawler user-agents is fully blocked, but this scraper identifies
as FASHIONBOT_USER_AGENT below, which isn't in that list.

Article discovery uses sitemap-news.xml rather than scraping category/
listing pages, both because it's simpler and because it avoids the
disallowed infinite-scroll paths entirely. can_fetch() re-checks robots.txt
live via robotparser before every fetch, so a future robots.txt change is
respected automatically rather than relying on today's one-time read.

Headline/author/tags/published-date are pulled from standard <head> meta
tags (og:title, mrf:authors, article:tag, article:published_time) rather
than scraping visible page structure — more robust against a CSS/layout
redesign, and how Future plc sites (which run Who What Wear) already expose
this data. article:tag has no dedicated raw_content column (the CLAUDE.md
Section 4.2 schema doesn't define one), so tags go into raw_json alongside
the article section, matching how reddit_scraper.py stores its extra fields
(score, num_comments) in raw_json rather than adding new columns.
"""

import json
import time
from html import unescape

import requests
from bs4 import BeautifulSoup
from loguru import logger
from protego import Protego

from src.processing.cleaner import dedupe_content
from src.storage import db

BASE_URL = "https://www.whowhatwear.com"
SITEMAP_URL = f"{BASE_URL}/sitemap-news.xml"
ROBOTS_URL = f"{BASE_URL}/robots.txt"
USER_AGENT = "FashionTrendBot/1.0 (+research project; contact: shloakshetty1@gmail.com)"
REQUEST_HEADERS = {"User-Agent": USER_AGENT}

RATE_LIMIT_SECONDS = 2
LIMIT = 20


def _robot_parser() -> Protego:
    """Fetch and parse robots.txt.

    Uses protego, not stdlib urllib.robotparser: whowhatwear.com's robots.txt
    has two separate `User-agent: *` blocks (a "vanilla-wide" one with
    /comments/, /deals/compare, etc., and a "site-specific" one with query
    -string rules). robotparser silently keeps only the last such block
    instead of merging them — confirmed by inspecting its parsed entries —
    which would make can_fetch() wrongly allow disallowed paths. protego
    correctly merges rules across multiple same-agent blocks per RFC 9309.
    """
    response = requests.get(ROBOTS_URL, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    return Protego.parse(response.text)


def can_fetch(url: str, rp: Protego | None = None) -> bool:
    """Check whether robots.txt permits fetching url for our user agent."""
    rp = rp or _robot_parser()
    return rp.can_fetch(url, USER_AGENT)


def parse_sitemap_article_urls(xml_text: str) -> list[str]:
    """Parse sitemap-news.xml, returning only article page URLs.

    Each <url> entry also contains an <image:image><image:loc> for the
    article's thumbnail. BeautifulSoup's XML parser matches tag names without
    namespace prefixes, so a naive find_all("loc") over the whole document
    also matches those nested image:loc tags — confirmed by running it
    against the real sitemap: every other "article" URL was actually a CDN
    image URL from cdn.mos.cms.futurecdn.net. Scoping to each <url>'s direct
    child <loc> (not recursive into nested <image:image>) avoids that.
    """
    soup = BeautifulSoup(xml_text, "xml")
    urls = []
    for url_tag in soup.find_all("url"):
        loc = url_tag.find("loc", recursive=False)
        if loc:
            urls.append(loc.text)
    return urls


def fetch_sitemap_article_urls(limit: int = LIMIT) -> list[str]:
    """Fetch sitemap-news.xml and return up to limit article URLs."""
    response = requests.get(SITEMAP_URL, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    return parse_sitemap_article_urls(response.text)[:limit]


def extract_article_metadata(html: str, url: str) -> dict:
    """Parse an article page's <head> meta tags into a raw_content-ready dict.

    Pure function — no network. Missing fields degrade gracefully (None /
    empty string / empty list) rather than raising.
    """
    soup = BeautifulSoup(html, "html.parser")

    def meta_content(property_name: str) -> str | None:
        tag = soup.find("meta", property=property_name)
        return tag.get("content") if tag else None

    title = meta_content("og:title")
    if not title and soup.title:
        title = soup.title.text.split("|")[0].strip()
    if title:
        title = unescape(title)

    tags = [
        tag.get("content")
        for tag in soup.find_all("meta", property="article:tag")
        if tag.get("content")
    ]

    return {
        "source_id": url,
        "url": url,
        "title": title,
        "body": meta_content("og:description") or "",
        "author": meta_content("mrf:authors"),
        "published_at": meta_content("article:published_time"),
        "raw_json": json.dumps(
            {
                "tags": tags,
                "section": meta_content("article:section"),
            }
        ),
    }


def run(limit: int = LIMIT) -> int:
    """Ingest Who What Wear articles into raw_content.

    Discovers article URLs via sitemap-news.xml, checks each against
    robots.txt, fetches with a 2-second delay between requests, and skips
    (logs, continues) on any per-article failure instead of crashing the
    whole run. Returns the number of rows inserted.
    """
    engine = db.init_db()
    rp = _robot_parser()

    try:
        urls = fetch_sitemap_article_urls(limit)
    except Exception:
        logger.exception("Failed to fetch sitemap: {}", SITEMAP_URL)
        return 0

    articles: list[dict] = []
    for i, url in enumerate(urls):
        try:
            if not can_fetch(url, rp):
                logger.warning("robots.txt disallows fetching {}, skipping", url)
                continue

            response = requests.get(url, headers=REQUEST_HEADERS, timeout=10)
            response.raise_for_status()
            articles.append(extract_article_metadata(response.text, url))
            logger.info("Fetched article: {}", url)
        except Exception:
            logger.exception("Failed to fetch/parse article: {}", url)

        if i < len(urls) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    deduped = dedupe_content(articles)
    logger.info("{} articles after dedup (from {} raw)", len(deduped), len(articles))

    rows_inserted = 0
    for article in deduped:
        try:
            db.insert_raw_content(engine, source="whowhatwear", **article)
            rows_inserted += 1
        except Exception:
            logger.exception("Failed to insert article: {}", article.get("url"))

    logger.info("Who What Wear ingestion complete: {} rows inserted", rows_inserted)
    return rows_inserted


if __name__ == "__main__":
    run()
