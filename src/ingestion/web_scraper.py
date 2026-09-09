"""Web scraper: pulls articles from Who What Wear, Highsnobiety, and
Hypebeast into raw_content, per CLAUDE.md Section 7.4.

Run: daily at 8am (see scheduler/cron_jobs.py).

robots.txt was checked live for every site before writing any scraping code
for it (see SITES below and the git history of this file for what each
robots.txt said). All three permit a generic user agent to fetch normal
article URLs and their sitemap; each blocks a handful of admin/search/embed/
shop-filter paths and a few named bots this scraper doesn't identify as.

Article discovery uses each site's news sitemap rather than scraping
category/listing pages — simpler, and avoids disallowed paths (e.g. Who
What Wear's infinite-scroll endpoints) entirely. can_fetch() re-checks
robots.txt live via protego before every fetch, so a future robots.txt
change is respected automatically rather than relying on a one-time read.

Headline/description/published-date/tags are pulled from standard <head>
meta tags (og:title, og:description / meta[name=description],
article:published_time, article:tag) where a site exposes them — more
robust against a CSS/layout redesign than scraping visible structure.
Author and tags aren't consistently in meta tags across all three sites
(checked live per site), so extract_article_metadata() falls back through
site-specific sources in order:
  - author: meta[property=mrf:authors] -> inline `dataLayer.push({...})`
    analytics blob (Highsnobiety) -> first <a rel="author"> in the DOM
    (Hypebeast; picks the real byline over a later recirculation-module link
    because it appears first)
  - tags: meta[property=article:tag] (repeated tag) -> dataLayer tags/
    categories
  - body: og:description -> meta[name=description]
None of these has a dedicated raw_content column for tags (the CLAUDE.md
Section 4.2 schema doesn't define one), so tags go into raw_json alongside
the article section, matching how reddit_scraper.py stores its extra fields
(score, num_comments) in raw_json rather than adding new columns.
"""

import json
import re
import time
from html import unescape

import requests
from bs4 import BeautifulSoup
from loguru import logger
from protego import Protego

from src.processing.cleaner import dedupe_content
from src.storage import db

USER_AGENT = "FashionTrendBot/1.0 (+research project; contact: shloakshetty1@gmail.com)"
REQUEST_HEADERS = {"User-Agent": USER_AGENT}

RATE_LIMIT_SECONDS = 2
LIMIT = 20

# Sitemap/robots URLs checked live (see module docstring) before adding each site.
SITES = {
    "whowhatwear": {
        "sitemap_url": "https://www.whowhatwear.com/sitemap-news.xml",
        "robots_url": "https://www.whowhatwear.com/robots.txt",
    },
    "highsnobiety": {
        "sitemap_url": "https://highsnobiety.com/sitemap-news.xml",
        "robots_url": "https://highsnobiety.com/robots.txt",
    },
    "hypebeast": {
        # Filename differs from the other two sites' sitemaps (checked live).
        "sitemap_url": "https://hypebeast.com/news-sitemap.xml",
        "robots_url": "https://hypebeast.com/robots.txt",
    },
}


def _robot_parser(robots_url: str) -> Protego:
    """Fetch and parse a site's robots.txt.

    Uses protego, not stdlib urllib.robotparser: whowhatwear.com's robots.txt
    has two separate `User-agent: *` blocks (a "vanilla-wide" one with
    /comments/, /deals/compare, etc., and a "site-specific" one with query
    -string rules). robotparser silently keeps only the last such block
    instead of merging them — confirmed by inspecting its parsed entries —
    which would make can_fetch() wrongly allow disallowed paths. protego
    correctly merges rules across multiple same-agent blocks per RFC 9309.
    """
    response = requests.get(robots_url, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    return Protego.parse(response.text)


def can_fetch(url: str, rp: Protego | None = None) -> bool:
    """Check whether robots.txt permits fetching url for our user agent."""
    if rp is None:
        raise ValueError("rp is required (pass a Protego instance from _robot_parser())")
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


def fetch_sitemap_article_urls(sitemap_url: str, limit: int = LIMIT) -> list[str]:
    """Fetch a site's news sitemap and return up to limit article URLs."""
    response = requests.get(sitemap_url, headers=REQUEST_HEADERS, timeout=10)
    response.raise_for_status()
    return parse_sitemap_article_urls(response.text)[:limit]


def _extract_datalayer_author_and_tags(html: str) -> tuple[str | None, list[str]]:
    """Some sites (Highsnobiety, checked live) don't expose author/tags via
    meta tags at all — only in an inline analytics blob:
    `window['dataLayer'].push({"article_id": ..., "author": ..., "tags": [...]})`.
    A page can have multiple dataLayer.push calls (other analytics events);
    this picks the one identifiable as article metadata via "article_id"/
    "post_title" keys and ignores the rest. Returns (None, []) if not found.
    """
    for match in re.finditer(r"dataLayer[\"']\]\.push\(", html):
        start = html.find("{", match.end())
        if start == -1:
            continue
        depth = 0
        end = None
        for i in range(start, len(html)):
            if html[i] == "{":
                depth += 1
            elif html[i] == "}":
                depth -= 1
                if depth == 0:
                    end = i + 1
                    break
        if end is None:
            continue
        try:
            data = json.loads(html[start:end])
        except json.JSONDecodeError:
            continue
        if "article_id" in data or "post_title" in data:
            tags = list(dict.fromkeys((data.get("tags") or []) + (data.get("categories") or [])))
            return data.get("author"), tags
    return None, []


def extract_article_metadata(html: str, url: str) -> dict:
    """Parse an article page into a raw_content-ready dict.

    Pure function — no network. Prefers <head> meta tags; falls back through
    site-specific sources for fields that aren't consistently in meta tags
    across Who What Wear / Highsnobiety / Hypebeast (see module docstring).
    Missing fields degrade gracefully (None / empty string / empty list)
    rather than raising.
    """
    soup = BeautifulSoup(html, "html.parser")

    def meta_content(property_name: str) -> str | None:
        tag = soup.find("meta", property=property_name)
        return tag.get("content") if tag else None

    def meta_name(name: str) -> str | None:
        tag = soup.find("meta", attrs={"name": name})
        return tag.get("content") if tag else None

    def clean(text: str | None) -> str | None:
        return unescape(text) if text else text

    title = meta_content("og:title")
    if not title and soup.title:
        title = soup.title.text.split("|")[0].strip()

    tags = [
        tag.get("content")
        for tag in soup.find_all("meta", property="article:tag")
        if tag.get("content")
    ]

    author = meta_content("mrf:authors")
    datalayer_author, datalayer_tags = _extract_datalayer_author_and_tags(html)
    author = author or datalayer_author
    tags = tags or datalayer_tags

    if not author:
        byline = soup.find("a", attrs={"rel": "author"})
        if byline:
            author = byline.get_text(strip=True)

    body = meta_content("og:description") or meta_name("description") or ""

    return {
        "source_id": url,
        "url": url,
        "title": clean(title),
        "body": clean(body) or "",
        "author": clean(author),
        "published_at": meta_content("article:published_time"),
        "raw_json": json.dumps(
            {
                "tags": [clean(t) for t in tags],
                "section": meta_content("article:section"),
            }
        ),
    }


def run(site: str, limit: int = LIMIT) -> int:
    """Ingest articles from one configured site (a key in SITES) into raw_content.

    Discovers article URLs via that site's news sitemap, checks each against
    its robots.txt, fetches with a 2-second delay between requests, and skips
    (logs, continues) on any per-article failure instead of crashing the
    whole run. Returns the number of rows inserted.
    """
    if site not in SITES:
        raise ValueError(f"Unknown site '{site}'. Known sites: {list(SITES)}")
    config = SITES[site]

    engine = db.init_db()
    rp = _robot_parser(config["robots_url"])

    try:
        urls = fetch_sitemap_article_urls(config["sitemap_url"], limit)
    except Exception:
        logger.exception("Failed to fetch sitemap for {}: {}", site, config["sitemap_url"])
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
            db.insert_raw_content(engine, source=site, **article)
            rows_inserted += 1
        except Exception:
            logger.exception("Failed to insert article: {}", article.get("url"))

    logger.info("{} ingestion complete: {} rows inserted", site, rows_inserted)
    return rows_inserted


def run_all(limit: int = LIMIT) -> dict[str, int]:
    """Run every configured site's scraper. Returns {site: rows_inserted}."""
    return {site: run(site, limit) for site in SITES}


if __name__ == "__main__":
    run_all()
