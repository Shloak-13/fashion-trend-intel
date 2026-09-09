"""Text cleaning and deduplication for raw ingested content."""

import hashlib
import re
import unicodedata

URL_PATTERN = re.compile(r"https?://\S+")
HTML_TAG_PATTERN = re.compile(r"<[^>]+>")
NON_ALPHANUMERIC_PATTERN = re.compile(r"[^a-z0-9\s]")
WHITESPACE_PATTERN = re.compile(r"\s+")


def clean_text(text: str) -> str:
    """Strip URLs/HTML, normalise unicode to ASCII, lowercase, and collapse whitespace."""
    text = URL_PATTERN.sub("", text)
    text = HTML_TAG_PATTERN.sub(" ", text)
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    text = text.lower()
    text = NON_ALPHANUMERIC_PATTERN.sub(" ", text)
    return WHITESPACE_PATTERN.sub(" ", text).strip()


def content_hash(text: str) -> str:
    """Return a stable hash of cleaned text, used to detect duplicate content."""
    return hashlib.sha256(clean_text(text).encode("utf-8")).hexdigest()


def dedupe_content(rows: list[dict]) -> list[dict]:
    """Remove rows with a duplicate url or duplicate body content_hash, keeping the first."""
    seen_urls: set[str] = set()
    seen_hashes: set[str] = set()
    deduped = []
    for row in rows:
        url = row.get("url")
        body_hash = content_hash(row.get("body", "")) if row.get("body") else None

        if url and url in seen_urls:
            continue
        if body_hash and body_hash in seen_hashes:
            continue

        if url:
            seen_urls.add(url)
        if body_hash:
            seen_hashes.add(body_hash)
        deduped.append(row)
    return deduped
