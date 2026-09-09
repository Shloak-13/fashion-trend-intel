"""Reddit ingester: pulls hot posts from fashion subreddits into raw_content.

Run: every 6 hours (see scheduler/cron_jobs.py).
Requires REDDIT_CLIENT_ID / REDDIT_CLIENT_SECRET / REDDIT_USER_AGENT in .env
(create an app at https://reddit.com/prefs/apps).
"""

import json
import os
import time
from datetime import datetime, timezone

import praw
from loguru import logger

from src.storage import db

RATE_LIMIT_SECONDS = 2
POST_LIMIT = 25

DEFAULT_SUBREDDITS = [
    "femalefashionadvice",
]


class MissingRedditCredentialsError(RuntimeError):
    """Raised when REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET are not configured."""


def get_reddit_client() -> praw.Reddit:
    """Build an authenticated read-only praw client from environment variables."""
    client_id = os.getenv("REDDIT_CLIENT_ID")
    client_secret = os.getenv("REDDIT_CLIENT_SECRET")
    user_agent = os.getenv("REDDIT_USER_AGENT", "FashionTrendBot/1.0")

    if not client_id or not client_secret:
        raise MissingRedditCredentialsError(
            "REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET must be set in .env. "
            "Create an app at https://reddit.com/prefs/apps to obtain them."
        )

    reddit = praw.Reddit(
        client_id=client_id, client_secret=client_secret, user_agent=user_agent
    )
    reddit.read_only = True
    return reddit


def fetch_hot_posts(reddit: praw.Reddit, subreddit_name: str, limit: int = POST_LIMIT) -> list[dict]:
    """Fetch hot posts from one subreddit as plain dicts ready for raw_content."""
    subreddit = reddit.subreddit(subreddit_name)
    posts = []
    for submission in subreddit.hot(limit=limit):
        posts.append(
            {
                "source_id": submission.id,
                "url": f"https://reddit.com{submission.permalink}",
                "title": submission.title,
                "body": submission.selftext,
                "author": str(submission.author) if submission.author else None,
                "published_at": datetime.fromtimestamp(
                    submission.created_utc, tz=timezone.utc
                ).isoformat(),
                "raw_json": json.dumps(
                    {
                        "score": submission.score,
                        "num_comments": submission.num_comments,
                        "subreddit": subreddit_name,
                    }
                ),
            }
        )
    return posts


def run(subreddits: list[str] | None = None) -> int:
    """Ingest hot posts from each subreddit into raw_content.

    Continues past individual subreddit failures instead of crashing the whole run.
    Returns the number of rows inserted.
    """
    subreddits = subreddits or DEFAULT_SUBREDDITS
    engine = db.init_db()
    reddit = get_reddit_client()

    rows_inserted = 0
    for i, subreddit_name in enumerate(subreddits):
        try:
            posts = fetch_hot_posts(reddit, subreddit_name)
            for post in posts:
                db.insert_raw_content(engine, source="reddit", **post)
            rows_inserted += len(posts)
            logger.info("Ingested {} posts from r/{}", len(posts), subreddit_name)
        except Exception:
            logger.exception("Failed to ingest posts from r/{}", subreddit_name)

        if i < len(subreddits) - 1:
            time.sleep(RATE_LIMIT_SECONDS)

    logger.info("Reddit ingestion complete: {} rows inserted", rows_inserted)
    return rows_inserted


if __name__ == "__main__":
    run()
