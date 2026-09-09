"""Trend momentum scoring: week-over-week growth adjusted for source diversity.

NOTE: mention_count from Google-Trends-only data is Google's 0-100 normalised
interest score, not a raw document count. classify_trend()'s bands (100-1000
for "rising", >1000 for "peak") are tuned for raw_content mention counts, so
single-source Google Trends signals will mostly classify as "stable" until
Reddit/News ingestion contributes real document counts on the same scale.
"""

from collections import defaultdict
from datetime import date, timedelta

from loguru import logger
from sqlalchemy import text

from src.processing import categoriser
from src.storage import db


def compute_momentum_score(
    keyword: str, current_week_count: float, prev_week_count: float, source_diversity: int
) -> float:
    """
    momentum = week-over-week growth × source diversity bonus

    source_diversity: number of unique sources mentioning keyword (1-5+)
    diversity_multiplier: 1.0 to 1.5 (more sources = more reliable signal)
    """
    if prev_week_count == 0:
        wow_growth = 1.0 if current_week_count > 0 else 0.0
    else:
        wow_growth = (current_week_count - prev_week_count) / prev_week_count

    diversity_multiplier = min(1 + (source_diversity - 1) * 0.1, 1.5)
    momentum_score = wow_growth * diversity_multiplier
    return round(momentum_score, 4)


def classify_trend(momentum_score: float, mention_count: float) -> str:
    """Classify a keyword's trend status from its momentum score and mention count."""
    if momentum_score > 0.5 and mention_count < 100:
        return "emerging"
    if momentum_score > 0.2 and 100 <= mention_count <= 1000:
        return "rising"
    if -0.1 <= momentum_score <= 0.2 and mention_count > 1000:
        return "peak"
    if momentum_score < -0.1:
        return "declining"
    return "stable"


def _week_start(iso_date: str) -> str:
    """Return the ISO date of the Monday starting the week containing iso_date."""
    d = date.fromisoformat(iso_date)
    return (d - timedelta(days=d.weekday())).isoformat()


def aggregate_weekly_counts(rows: list[dict]) -> dict[str, float]:
    """Average interest_value/mention counts per ISO week (keyed by week-start date)."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        buckets[_week_start(row["date"])].append(row["interest_value"])
    return {week: sum(values) / len(values) for week, values in buckets.items()}


def full_weeks_only(rows: list[dict]) -> dict[str, float]:
    """Like aggregate_weekly_counts, but drops any week with fewer than 7 days of
    data (i.e. the current in-progress week) so week-over-week comparisons never
    pit a partial week against a full one."""
    buckets: dict[str, list[float]] = defaultdict(list)
    for row in rows:
        buckets[_week_start(row["date"])].append(row["interest_value"])
    return {
        week: sum(values) / len(values)
        for week, values in buckets.items()
        if len(values) >= 7
    }


def _category_id_for_keyword(engine, keyword: str) -> int | None:
    """Look up the categories.id for a keyword's taxonomy match, if any and if seeded."""
    category_name = categoriser.categorise_keyword(keyword)["category"]
    if not category_name:
        return None
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id FROM categories WHERE name = :name"), {"name": category_name}
        ).scalar()


def score_keyword_from_google_trends(engine, keyword: str) -> dict | None:
    """Compute and persist a trend_signals row from the two most recent full weeks
    of google_trends data for a keyword. Returns the computed signal, or None if
    there isn't at least two weeks of data to compare.
    """
    rows = db.get_google_trends_by_keyword(engine, keyword)
    weekly = full_weeks_only(rows)
    if len(weekly) < 2:
        logger.warning("Not enough weekly data to score '{}' (need 2+ weeks)", keyword)
        return None

    weeks_sorted = sorted(weekly.keys())
    prev_week_count = weekly[weeks_sorted[-2]]
    current_week_count = weekly[weeks_sorted[-1]]
    source_diversity = 1  # Google Trends only, until Reddit/News are ingested

    momentum_score = compute_momentum_score(
        keyword, current_week_count, prev_week_count, source_diversity
    )
    trend_status = classify_trend(momentum_score, current_week_count)
    category_id = _category_id_for_keyword(engine, keyword)

    signal = {
        "keyword": keyword,
        "category_id": category_id,
        "date": weeks_sorted[-1],
        "mention_count": round(current_week_count),
        "momentum_score": momentum_score,
        "source_diversity": source_diversity,
        "trend_status": trend_status,
    }

    with engine.begin() as conn:
        # Delete-then-insert keeps this idempotent: re-scoring the same keyword/date
        # (e.g. the daily scheduler re-running, or a manual re-run) replaces the old
        # signal instead of accumulating duplicate rows.
        conn.execute(
            text("DELETE FROM trend_signals WHERE keyword = :keyword AND date = :date"),
            {"keyword": keyword, "date": signal["date"]},
        )
        conn.execute(
            text(
                """
                INSERT INTO trend_signals
                    (keyword, category_id, date, mention_count, sentiment_score,
                     momentum_score, source_diversity)
                VALUES
                    (:keyword, :category_id, :date, :mention_count, NULL,
                     :momentum_score, :source_diversity)
                """
            ),
            signal,
        )

    logger.info(
        "Scored '{}': momentum={} status={}", keyword, momentum_score, trend_status
    )
    return signal


def run(keywords: list[str] | None = None) -> list[dict]:
    """Score every tracked keyword from its Google Trends history. Continues past
    per-keyword failures instead of crashing the whole run."""
    engine = db.init_db()
    if keywords is None:
        with engine.connect() as conn:
            keywords = [
                row[0]
                for row in conn.execute(text("SELECT DISTINCT keyword FROM google_trends"))
            ]

    signals = []
    for keyword in keywords:
        try:
            signal = score_keyword_from_google_trends(engine, keyword)
            if signal:
                signals.append(signal)
        except Exception:
            logger.exception("Failed to score keyword '{}'", keyword)

    logger.info("Trend scoring complete: {} signals computed", len(signals))
    return signals


if __name__ == "__main__":
    run()
