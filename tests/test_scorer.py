import pytest

from src.processing import categoriser, scorer
from src.storage import db


def test_compute_momentum_score_positive_growth():
    # (120 - 100) / 100 = 0.2 growth, diversity_multiplier for 1 source = 1.0
    assert scorer.compute_momentum_score("oversized", 120, 100, 1) == 0.2


def test_compute_momentum_score_zero_prev_week_with_mentions():
    assert scorer.compute_momentum_score("new_term", 10, 0, 1) == 1.0


def test_compute_momentum_score_zero_prev_week_no_mentions():
    assert scorer.compute_momentum_score("dead_term", 0, 0, 1) == 0.0


def test_compute_momentum_score_source_diversity_bonus():
    # 0.2 growth * diversity_multiplier for 3 sources (1 + 2*0.1 = 1.2)
    assert scorer.compute_momentum_score("oversized", 120, 100, 3) == pytest.approx(0.24)


def test_compute_momentum_score_diversity_capped_at_1_5():
    # diversity 10 -> 1 + 9*0.1 = 1.9, capped to 1.5
    assert scorer.compute_momentum_score("oversized", 200, 100, 10) == pytest.approx(1.5)


@pytest.mark.parametrize(
    "momentum,mention_count,expected",
    [
        (0.6, 50, "emerging"),
        (0.3, 500, "rising"),
        (0.0, 2000, "peak"),
        (-0.2, 300, "declining"),
    ],
)
def test_classify_trend(momentum, mention_count, expected):
    assert scorer.classify_trend(momentum, mention_count) == expected


def test_aggregate_weekly_counts_averages_interest_by_week():
    rows = [
        {"date": "2026-08-31", "interest_value": 40},  # Mon, week of 2026-08-31
        {"date": "2026-09-02", "interest_value": 60},  # same week
        {"date": "2026-09-07", "interest_value": 80},  # next week (Mon)
    ]
    weekly = scorer.aggregate_weekly_counts(rows)
    assert weekly["2026-08-31"] == 50
    assert weekly["2026-09-07"] == 80


def test_full_weeks_only_drops_partial_trailing_week():
    rows = [
        {"date": "2026-08-24", "interest_value": 50},  # full week: 7 days
        {"date": "2026-08-25", "interest_value": 50},
        {"date": "2026-08-26", "interest_value": 50},
        {"date": "2026-08-27", "interest_value": 50},
        {"date": "2026-08-28", "interest_value": 50},
        {"date": "2026-08-29", "interest_value": 50},
        {"date": "2026-08-30", "interest_value": 50},
        {"date": "2026-08-31", "interest_value": 70},  # full week: 7 days
        {"date": "2026-09-01", "interest_value": 70},
        {"date": "2026-09-02", "interest_value": 70},
        {"date": "2026-09-03", "interest_value": 70},
        {"date": "2026-09-04", "interest_value": 70},
        {"date": "2026-09-05", "interest_value": 70},
        {"date": "2026-09-06", "interest_value": 70},
        {"date": "2026-09-07", "interest_value": 20},  # partial week: 1 day, today
    ]
    full_weeks = scorer.full_weeks_only(rows)
    assert "2026-09-07" not in full_weeks
    assert set(full_weeks) == {"2026-08-24", "2026-08-31"}


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_scorer.db")


def test_score_keyword_from_google_trends_writes_trend_signal(db_path):
    engine = db.init_db(db_path)
    categoriser.seed_categories(engine)
    # Two full weeks of data: week 1 avg=40, week 2 avg=60 -> growth = 0.5
    for date, value in [
        ("2026-08-24", 40), ("2026-08-25", 40), ("2026-08-26", 40), ("2026-08-27", 40),
        ("2026-08-28", 40), ("2026-08-29", 40), ("2026-08-30", 40),
        ("2026-08-31", 60), ("2026-09-01", 60), ("2026-09-02", 60), ("2026-09-03", 60),
        ("2026-09-04", 60), ("2026-09-05", 60), ("2026-09-06", 60),
    ]:
        db.insert_google_trend(engine, keyword="oversized", date=date, interest_value=value)

    signal = scorer.score_keyword_from_google_trends(engine, "oversized")

    assert signal is not None
    assert signal["momentum_score"] == pytest.approx(0.5)
    assert signal["mention_count"] == 60
    assert signal["source_diversity"] == 1
    # NOTE: Google Trends' 0-100 interest scale sits below the mention_count
    # bands (100-1000 for "rising", >1000 for "peak") that CLAUDE.md tunes for
    # raw document counts. Until Reddit/News mention counts are flowing, single
    # -source Google Trends signals will classify as "stable" by default even
    # with strong momentum. This is a known limitation, not a bug.
    assert signal["trend_status"] == "stable"
    # "oversized" is an exact taxonomy match under "Silhouettes"
    assert signal["category_id"] is not None
    with engine.connect() as conn:
        from sqlalchemy import text

        category_name = conn.execute(
            text("SELECT name FROM categories WHERE id = :id"), {"id": signal["category_id"]}
        ).scalar()
    assert category_name == "Silhouettes"


def test_score_keyword_from_google_trends_is_idempotent(db_path):
    engine = db.init_db(db_path)
    for date, value in [
        ("2026-08-24", 40), ("2026-08-25", 40), ("2026-08-26", 40), ("2026-08-27", 40),
        ("2026-08-28", 40), ("2026-08-29", 40), ("2026-08-30", 40),
        ("2026-08-31", 60), ("2026-09-01", 60), ("2026-09-02", 60), ("2026-09-03", 60),
        ("2026-09-04", 60), ("2026-09-05", 60), ("2026-09-06", 60),
    ]:
        db.insert_google_trend(engine, keyword="oversized", date=date, interest_value=value)

    scorer.score_keyword_from_google_trends(engine, "oversized")
    scorer.score_keyword_from_google_trends(engine, "oversized")

    with engine.connect() as conn:
        from sqlalchemy import text

        count = conn.execute(
            text("SELECT COUNT(*) FROM trend_signals WHERE keyword = 'oversized'")
        ).scalar()
    assert count == 1


def test_score_keyword_from_google_trends_handles_unseeded_categories(db_path):
    engine = db.init_db(db_path)  # categories table intentionally not seeded
    for date, value in [
        ("2026-08-24", 40), ("2026-08-25", 40), ("2026-08-26", 40), ("2026-08-27", 40),
        ("2026-08-28", 40), ("2026-08-29", 40), ("2026-08-30", 40),
        ("2026-08-31", 60), ("2026-09-01", 60), ("2026-09-02", 60), ("2026-09-03", 60),
        ("2026-09-04", 60), ("2026-09-05", 60), ("2026-09-06", 60),
    ]:
        db.insert_google_trend(engine, keyword="oversized", date=date, interest_value=value)

    signal = scorer.score_keyword_from_google_trends(engine, "oversized")
    assert signal["category_id"] is None
