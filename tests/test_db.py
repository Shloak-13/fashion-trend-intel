import pytest
from sqlalchemy import text

from src.storage import db

EXPECTED_TABLES = {
    "raw_content",
    "keywords",
    "categories",
    "trend_signals",
    "google_trends",
    "brands",
    "brand_mentions",
}


@pytest.fixture
def db_path(tmp_path):
    return str(tmp_path / "test_fashion_trends.db")


def test_init_db_creates_all_tables(db_path):
    engine = db.init_db(db_path)
    assert EXPECTED_TABLES.issubset(set(db.get_table_names(engine)))


def test_init_db_is_idempotent(db_path):
    engine1 = db.init_db(db_path)
    engine2 = db.init_db(db_path)
    assert set(db.get_table_names(engine1)) == set(db.get_table_names(engine2))


def test_insert_and_retrieve_raw_content(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(
        engine,
        source="reddit",
        source_id="abc123",
        url="https://reddit.com/r/femalefashionadvice/abc123",
        title="Loving oversized blazers rn",
        body="anyone else obsessed with oversized blazers this fall",
        author="throwaway_fash",
    )
    assert content_id is not None

    rows = db.get_raw_content_by_source(engine, "reddit")
    assert len(rows) == 1
    assert rows[0]["title"] == "Loving oversized blazers rn"


def test_get_existing_urls_returns_only_that_sources_urls(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="news", url="https://a.com/1", title="one")
    db.insert_raw_content(engine, source="news", url="https://a.com/2", title="two")
    db.insert_raw_content(engine, source="reddit", url="https://reddit.com/x", title="three")

    urls = db.get_existing_urls(engine, "news")

    assert urls == {"https://a.com/1", "https://a.com/2"}


def test_insert_and_retrieve_google_trend(db_path):
    engine = db.init_db(db_path)
    db.insert_google_trend(
        engine, keyword="oversized", date="2026-09-01", interest_value=72, geo="IN"
    )

    rows = db.get_google_trends_by_keyword(engine, "oversized")
    assert len(rows) == 1
    assert rows[0]["interest_value"] == 72


def test_delete_google_trends_by_keyword_removes_only_that_keyword(db_path):
    engine = db.init_db(db_path)
    db.insert_google_trend(engine, keyword="oversized", date="2026-09-01", interest_value=72, geo="IN")
    db.insert_google_trend(engine, keyword="oversized", date="2026-09-02", interest_value=70, geo="IN")
    db.insert_google_trend(engine, keyword="cargo pants", date="2026-09-01", interest_value=50, geo="IN")

    deleted = db.delete_google_trends_by_keyword(engine, "oversized", geo="IN")

    assert deleted == 2
    assert db.get_google_trends_by_keyword(engine, "oversized") == []
    assert len(db.get_google_trends_by_keyword(engine, "cargo pants")) == 1


def test_get_all_raw_content_returns_every_row(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="reddit", title="post one")
    db.insert_raw_content(engine, source="news", title="article one")

    rows = db.get_all_raw_content(engine)
    assert len(rows) == 2
    assert {r["title"] for r in rows} == {"post one", "article one"}


def test_insert_and_retrieve_keywords(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title="oversized blazers trend")

    db.insert_keyword(
        engine, content_id=content_id, keyword="oversized", keyword_type="Silhouettes", confidence=1.0
    )
    db.insert_keyword(
        engine, content_id=content_id, keyword="blazers", keyword_type="emerging", confidence=0.6
    )

    rows = db.get_keywords_by_content_id(engine, content_id)
    assert len(rows) == 2
    assert {r["keyword"] for r in rows} == {"oversized", "blazers"}


def test_delete_keywords_for_content_removes_only_that_contents_rows(db_path):
    engine = db.init_db(db_path)
    content_id_1 = db.insert_raw_content(engine, source="news", title="post one")
    content_id_2 = db.insert_raw_content(engine, source="news", title="post two")
    db.insert_keyword(engine, content_id=content_id_1, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)
    db.insert_keyword(engine, content_id=content_id_2, keyword="denim", keyword_type="Patterns & Textures", confidence=1.0)

    db.delete_keywords_for_content(engine, content_id_1)

    assert db.get_keywords_by_content_id(engine, content_id_1) == []
    assert len(db.get_keywords_by_content_id(engine, content_id_2)) == 1


def test_delete_raw_content_by_source_removes_only_that_sources_rows(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="news", title="news post")
    db.insert_raw_content(engine, source="reddit", title="reddit post")

    deleted = db.delete_raw_content_by_source(engine, "news")

    assert deleted == 1
    assert db.get_raw_content_by_source(engine, "news") == []
    assert len(db.get_raw_content_by_source(engine, "reddit")) == 1


def test_delete_raw_content_by_source_also_deletes_its_keywords(db_path):
    engine = db.init_db(db_path)
    content_id = db.insert_raw_content(engine, source="news", title="news post")
    db.insert_keyword(engine, content_id=content_id, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)

    db.delete_raw_content_by_source(engine, "news")

    assert db.get_keywords_by_content_id(engine, content_id) == []


# --- Dashboard query helpers (Phase 4, Trend Radar) ---


def _seed_dashboard_data(engine):
    """Two 'oversized' mentions (Silhouettes, sources news+whowhatwear) and
    one 'quiet luxury' mention (Aesthetics, source news only)."""
    c1 = db.insert_raw_content(engine, source="news", url="https://a.com/1", title="a", published_at="2026-09-01T00:00:00Z")
    c2 = db.insert_raw_content(engine, source="whowhatwear", url="https://a.com/2", title="b", published_at="2026-09-05T00:00:00Z")
    c3 = db.insert_raw_content(engine, source="news", url="https://a.com/3", title="c", published_at="2026-09-08T00:00:00Z")
    db.insert_keyword(engine, content_id=c1, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)
    db.insert_keyword(engine, content_id=c2, keyword="oversized", keyword_type="Silhouettes", confidence=0.8)
    db.insert_keyword(engine, content_id=c3, keyword="quiet luxury", keyword_type="Aesthetics", confidence=0.6)
    db.insert_keyword(engine, content_id=c3, keyword="random", keyword_type="emerging", confidence=None)


def test_get_top_keywords_ranks_by_mention_count(db_path):
    engine = db.init_db(db_path)
    _seed_dashboard_data(engine)

    rows = db.get_top_keywords(engine)

    assert rows[0]["keyword"] == "oversized"
    assert rows[0]["mention_count"] == 2
    assert rows[0]["source_diversity"] == 2
    assert rows[0]["avg_confidence"] == pytest.approx(0.9)
    assert rows[0]["category"] == "Silhouettes"
    # "emerging" keywords are never included, regardless of mention count
    assert all(r["keyword"] != "random" for r in rows)


def test_get_top_keywords_excludes_mentions_below_confidence_threshold(db_path):
    engine = db.init_db(db_path)
    c1 = db.insert_raw_content(engine, source="news", url="https://b.com/1", title="x")
    c2 = db.insert_raw_content(engine, source="news", url="https://b.com/2", title="y")
    # A bigram artifact: several low-confidence mentions that shouldn't
    # count as real signal, e.g. "york fashion" from "New York Fashion Week".
    db.insert_keyword(engine, content_id=c1, keyword="york fashion", keyword_type="Aesthetics", confidence=0.45)
    db.insert_keyword(engine, content_id=c2, keyword="york fashion", keyword_type="Aesthetics", confidence=0.53)

    rows = db.get_top_keywords(engine)

    assert rows == []


def test_get_top_keywords_default_confidence_threshold_is_0_6(db_path):
    engine = db.init_db(db_path)
    c1 = db.insert_raw_content(engine, source="news", url="https://b.com/1", title="x")
    db.insert_keyword(engine, content_id=c1, keyword="borderline", keyword_type="Aesthetics", confidence=0.599)

    assert db.get_top_keywords(engine) == []
    assert len(db.get_top_keywords(engine, min_confidence=0.5)) == 1


def test_get_top_keywords_excludes_below_min_source_diversity(db_path):
    engine = db.init_db(db_path)
    c1 = db.insert_raw_content(engine, source="news", url="https://c.com/1", title="x")
    c2 = db.insert_raw_content(engine, source="news", url="https://c.com/2", title="y")
    c3 = db.insert_raw_content(engine, source="whowhatwear", url="https://c.com/3", title="z")
    # "single_source" mentioned twice but only ever by "news" -- a real
    # signal shouldn't need to come from just one outlet to count as trending.
    db.insert_keyword(engine, content_id=c1, keyword="single_source", keyword_type="Aesthetics", confidence=0.9)
    db.insert_keyword(engine, content_id=c2, keyword="single_source", keyword_type="Aesthetics", confidence=0.9)
    db.insert_keyword(engine, content_id=c1, keyword="multi_source", keyword_type="Aesthetics", confidence=0.9)
    db.insert_keyword(engine, content_id=c3, keyword="multi_source", keyword_type="Aesthetics", confidence=0.9)

    # Default (min_source_diversity=1) includes both.
    default_rows = {r["keyword"] for r in db.get_top_keywords(engine)}
    assert default_rows == {"single_source", "multi_source"}

    # min_source_diversity=2 drops the single-source keyword.
    filtered_rows = {r["keyword"] for r in db.get_top_keywords(engine, min_source_diversity=2)}
    assert filtered_rows == {"multi_source"}


def test_get_top_keywords_filters_by_category(db_path):
    engine = db.init_db(db_path)
    _seed_dashboard_data(engine)

    rows = db.get_top_keywords(engine, category="Aesthetics")

    assert [r["keyword"] for r in rows] == ["quiet luxury"]


def test_get_top_keywords_filters_by_source(db_path):
    engine = db.init_db(db_path)
    _seed_dashboard_data(engine)

    rows = db.get_top_keywords(engine, source="whowhatwear")

    assert [r["keyword"] for r in rows] == ["oversized"]
    assert rows[0]["mention_count"] == 1


def test_get_top_keywords_filters_by_published_date_range(db_path):
    engine = db.init_db(db_path)
    _seed_dashboard_data(engine)

    rows = db.get_top_keywords(engine, published_after="2026-09-04", published_before="2026-09-06")

    assert [r["keyword"] for r in rows] == ["oversized"]
    assert rows[0]["mention_count"] == 1


def test_get_top_keywords_respects_limit(db_path):
    engine = db.init_db(db_path)
    _seed_dashboard_data(engine)

    rows = db.get_top_keywords(engine, limit=1)

    assert len(rows) == 1


def test_get_top_keywords_empty_when_no_data(db_path):
    engine = db.init_db(db_path)
    assert db.get_top_keywords(engine) == []


def test_get_available_sources_returns_distinct_sorted_sources(db_path):
    engine = db.init_db(db_path)
    db.insert_raw_content(engine, source="news", title="a")
    db.insert_raw_content(engine, source="news", title="b")
    db.insert_raw_content(engine, source="whowhatwear", title="c")

    assert db.get_available_sources(engine) == ["news", "whowhatwear"]


def test_get_all_trend_signals_returns_rows(db_path):
    engine = db.init_db(db_path)
    with engine.begin() as conn:
        from sqlalchemy import text

        conn.execute(
            text(
                """
                INSERT INTO trend_signals (keyword, date, mention_count, momentum_score, source_diversity)
                VALUES ('oversized', '2026-09-01', 65, 0.05, 1)
                """
            )
        )

    rows = db.get_all_trend_signals(engine)
    assert len(rows) == 1
    assert rows[0]["keyword"] == "oversized"
    assert rows[0]["momentum_score"] == 0.05


def test_get_last_updated_returns_max_ingested_at(db_path):
    engine = db.init_db(db_path)
    assert db.get_last_updated(engine) is None

    db.insert_raw_content(engine, source="news", title="a")
    assert db.get_last_updated(engine) is not None


# --- Dashboard query helpers (Phase 4, Page 2: Keyword Deep Dive) ---


def _seed_deep_dive_data(engine):
    """'oversized' mentioned 3x (2 on 2026-09-01 across news+whowhatwear, 1 on
    2026-09-03 on hypebeast); 'denim' mentioned once, unrelated."""
    c1 = db.insert_raw_content(
        engine, source="news", url="https://a.com/1", title="Piece One",
        author="Jane Doe", published_at="2026-09-01T10:00:00Z",
    )
    c2 = db.insert_raw_content(
        engine, source="whowhatwear", url="https://a.com/2", title="Piece Two",
        author="Sam Lee", published_at="2026-09-01T14:00:00Z",
    )
    c3 = db.insert_raw_content(
        engine, source="hypebeast", url="https://a.com/3", title="Piece Three",
        author="Ana Kim", published_at="2026-09-03T09:00:00Z",
    )
    c4 = db.insert_raw_content(engine, source="news", url="https://a.com/4", title="Unrelated")
    db.insert_keyword(engine, content_id=c1, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)
    db.insert_keyword(engine, content_id=c2, keyword="oversized", keyword_type="Silhouettes", confidence=0.9)
    db.insert_keyword(engine, content_id=c3, keyword="oversized", keyword_type="Silhouettes", confidence=0.8)
    db.insert_keyword(engine, content_id=c4, keyword="denim", keyword_type="Patterns & Textures", confidence=1.0)


def test_get_all_keyword_names_returns_distinct_keywords_sorted_by_frequency(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)

    names = db.get_all_keyword_names(engine)

    assert names == ["oversized", "denim"]


def test_get_keyword_time_series_groups_by_published_date(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)

    series = db.get_keyword_time_series(engine, "oversized")

    assert series == [
        {"date": "2026-09-01", "mention_count": 2},
        {"date": "2026-09-03", "mention_count": 1},
    ]


def test_get_keyword_time_series_is_case_insensitive_and_empty_for_unknown(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)

    assert db.get_keyword_time_series(engine, "OVERSIZED") == [
        {"date": "2026-09-01", "mention_count": 2},
        {"date": "2026-09-03", "mention_count": 1},
    ]
    assert db.get_keyword_time_series(engine, "nonexistent") == []


def test_get_keyword_source_breakdown_counts_per_source(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)

    breakdown = db.get_keyword_source_breakdown(engine, "oversized")

    assert {r["source"]: r["mention_count"] for r in breakdown} == {
        "news": 1,
        "whowhatwear": 1,
        "hypebeast": 1,
    }


def test_get_keyword_recent_mentions_orders_by_published_date_desc(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)

    mentions = db.get_keyword_recent_mentions(engine, "oversized", limit=2)

    assert len(mentions) == 2
    assert mentions[0]["title"] == "Piece Three"
    assert mentions[0]["url"] == "https://a.com/3"
    assert mentions[0]["source"] == "hypebeast"
    assert mentions[1]["title"] == "Piece Two"


def test_get_keyword_recent_mentions_empty_for_unknown_keyword(db_path):
    engine = db.init_db(db_path)
    _seed_deep_dive_data(engine)


# --- Dashboard query helpers (Phase 4, Page 3: Category Analysis) ---


def _seed_category_data(engine):
    """'oversized' (Silhouettes) mentioned 2x on 2026-09-01 (news + whowhatwear);
    'draped' (Silhouettes) mentioned once on 2026-09-08 (news only);
    'quiet luxury' (Aesthetics) mentioned once on 2026-09-01 (news only)."""
    c1 = db.insert_raw_content(engine, source="news", url="https://a.com/1", title="a", published_at="2026-09-01T00:00:00Z")
    c2 = db.insert_raw_content(engine, source="whowhatwear", url="https://a.com/2", title="b", published_at="2026-09-01T00:00:00Z")
    c3 = db.insert_raw_content(engine, source="news", url="https://a.com/3", title="c", published_at="2026-09-08T00:00:00Z")
    c4 = db.insert_raw_content(engine, source="news", url="https://a.com/4", title="d", published_at="2026-09-01T00:00:00Z")
    db.insert_keyword(engine, content_id=c1, keyword="oversized", keyword_type="Silhouettes", confidence=1.0)
    db.insert_keyword(engine, content_id=c2, keyword="oversized", keyword_type="Silhouettes", confidence=0.8)
    db.insert_keyword(engine, content_id=c3, keyword="draped", keyword_type="Silhouettes", confidence=0.9)
    db.insert_keyword(engine, content_id=c4, keyword="quiet luxury", keyword_type="Aesthetics", confidence=0.7)


def test_get_keywords_by_category_ranks_by_mention_count(db_path):
    engine = db.init_db(db_path)
    _seed_category_data(engine)

    rows = db.get_keywords_by_category(engine, "Silhouettes")

    assert [r["keyword"] for r in rows] == ["oversized", "draped"]
    assert rows[0]["mention_count"] == 2
    assert rows[0]["source_diversity"] == 2
    assert rows[0]["momentum_score"] is None


def test_get_keywords_by_category_only_returns_that_category(db_path):
    engine = db.init_db(db_path)
    _seed_category_data(engine)

    rows = db.get_keywords_by_category(engine, "Aesthetics")

    assert [r["keyword"] for r in rows] == ["quiet luxury"]


def test_get_keywords_by_category_includes_momentum_score_when_available(db_path):
    engine = db.init_db(db_path)
    _seed_category_data(engine)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO trend_signals (keyword, date, mention_count, momentum_score, source_diversity)
                VALUES ('oversized', '2026-08-31', 66, 0.0522, 1)
                """
            )
        )

    rows = db.get_keywords_by_category(engine, "Silhouettes")

    assert rows[0]["keyword"] == "oversized"
    assert rows[0]["momentum_score"] == pytest.approx(0.0522)
    assert rows[1]["momentum_score"] is None


def test_get_keywords_by_category_respects_limit(db_path):
    engine = db.init_db(db_path)
    _seed_category_data(engine)

    rows = db.get_keywords_by_category(engine, "Silhouettes", limit=1)

    assert len(rows) == 1


def test_get_keywords_by_category_empty_when_no_data(db_path):
    engine = db.init_db(db_path)
    assert db.get_keywords_by_category(engine, "Silhouettes") == []


def test_get_category_week_heatmap_groups_by_category_and_week(db_path):
    engine = db.init_db(db_path)
    _seed_category_data(engine)

    rows = db.get_category_week_heatmap(engine)

    by_key = {(r["category"], r["week"]): r["mention_count"] for r in rows}
    # 2026-09-01 and 2026-09-08 fall in different SQLite %W weeks (strftime
    # '%W' counts Mondays since Jan 1 -- not ISO-8601 week numbering).
    assert by_key[("Silhouettes", "2026-W35")] == 2  # the two 09-01 "oversized" mentions
    assert by_key[("Silhouettes", "2026-W36")] == 1  # the 09-08 "draped" mention
    assert by_key[("Aesthetics", "2026-W35")] == 1


def test_get_category_week_heatmap_excludes_emerging(db_path):
    engine = db.init_db(db_path)
    c1 = db.insert_raw_content(engine, source="news", url="https://c.com/1", title="x", published_at="2026-09-01T00:00:00Z")
    db.insert_keyword(engine, content_id=c1, keyword="novelty term", keyword_type="emerging", confidence=0.9)

    assert db.get_category_week_heatmap(engine) == []


def test_get_category_week_heatmap_empty_when_no_data(db_path):
    engine = db.init_db(db_path)
    assert db.get_category_week_heatmap(engine) == []


# --- Dashboard query helpers (Phase 4, Page 4: Colour Trends) ---


def _seed_colour_trends(engine):
    """'black': two days, latest 88 on 09-03. 'white': one day, 60 on 09-02.
    'red' has no rows at all (never ingested)."""
    db.insert_google_trend(engine, keyword="black", date="2026-09-01", interest_value=70, geo="IN")
    db.insert_google_trend(engine, keyword="black", date="2026-09-03", interest_value=88, geo="IN")
    db.insert_google_trend(engine, keyword="white", date="2026-09-02", interest_value=60, geo="IN")
    # A different geo shouldn't leak into an IN-scoped lookup.
    db.insert_google_trend(engine, keyword="black", date="2026-09-03", interest_value=10, geo="US")


def test_get_latest_google_trends_returns_most_recent_value_per_keyword(db_path):
    engine = db.init_db(db_path)
    _seed_colour_trends(engine)

    rows = db.get_latest_google_trends(engine, ["black", "white", "red"])

    by_keyword = {r["keyword"]: r for r in rows}
    assert by_keyword["black"]["date"] == "2026-09-03"
    assert by_keyword["black"]["interest_value"] == 88
    assert by_keyword["white"]["interest_value"] == 60
    assert "red" not in by_keyword


def test_get_latest_google_trends_filters_by_geo(db_path):
    engine = db.init_db(db_path)
    _seed_colour_trends(engine)

    rows = db.get_latest_google_trends(engine, ["black"], geo="US")

    assert len(rows) == 1
    assert rows[0]["interest_value"] == 10


def test_get_latest_google_trends_only_returns_requested_keywords(db_path):
    engine = db.init_db(db_path)
    _seed_colour_trends(engine)

    rows = db.get_latest_google_trends(engine, ["white"])

    assert [r["keyword"] for r in rows] == ["white"]


def test_get_latest_google_trends_empty_for_empty_keyword_list(db_path):
    engine = db.init_db(db_path)
    _seed_colour_trends(engine)

    assert db.get_latest_google_trends(engine, []) == []


def test_get_latest_google_trends_empty_when_no_data(db_path):
    engine = db.init_db(db_path)
    assert db.get_latest_google_trends(engine, ["black"]) == []

    assert db.get_keyword_recent_mentions(engine, "nonexistent") == []
