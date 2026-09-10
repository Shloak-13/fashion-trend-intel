"""Trend Radar — Page 1 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8. Run: streamlit run src/dashboard/app.py

Data-reality note (confirmed with the project owner before building this):
the spec's "Top 10 emerging" / "Top 10 rising" split assumes trend_signals
has broad momentum data. It doesn't yet — only the 5 hardcoded Google Trends
seed keywords have real week-over-week momentum. The 433 taxonomy-matched
keywords extracted by the NLP pipeline have no temporal baseline to classify
by (nlp_pipeline.run() re-processes and overwrites extracted_at to "now" on
every run, so there's no history to diff against). So this page shows a
single "Top Trending Keywords" list ranked by real mention count and source
diversity instead of a fabricated emerging/rising split, and gives the 5
real Google-Trends-backed signals their own clearly-labeled section.
"""

import sys
from datetime import date
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.processing.categoriser import TAXONOMY  # noqa: E402
from src.processing.scorer import classify_trend  # noqa: E402
from src.storage import db  # noqa: E402

st.set_page_config(page_title="Fashion Trend Radar", page_icon="📡", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

BUBBLE_COLORS = ["#C9A99A", "#8FA6A3", "#D4B896", "#A9A3C9", "#B3C99A", "#C99AA3"]


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("What's Trending in Fashion Right Now")

    with st.spinner("Checking last update time..."):
        last_updated = db.get_last_updated(engine)
    st.caption(f"Last updated: {last_updated or 'never'}")

    # --- Sidebar filters ---
    st.sidebar.header("Filters")

    category_options = ["All"] + list(TAXONOMY.keys())
    selected_category = st.sidebar.selectbox("Category", category_options)

    with st.spinner("Loading sources..."):
        available_sources = db.get_available_sources(engine)
    selected_source = st.sidebar.selectbox("Source", ["All"] + available_sources)

    date_range = st.sidebar.date_input(
        "Published date range",
        value=(date(2020, 1, 1), date.today()),
    )

    st.sidebar.selectbox(
        "Market",
        ["IN"],
        disabled=True,
        help="Only India (IN) has been ingested so far via Google Trends — more markets in a future phase.",
    )

    category_filter = None if selected_category == "All" else selected_category
    source_filter = None if selected_source == "All" else selected_source
    published_after = published_before = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        published_after, published_before = date_range[0].isoformat(), date_range[1].isoformat()

    # --- Top Trending Keywords ---
    st.header("Top Trending Keywords")
    with st.spinner("Loading keywords..."):
        top_keywords = db.get_top_keywords(
            engine,
            category=category_filter,
            source=source_filter,
            published_after=published_after,
            published_before=published_before,
            min_source_diversity=2,
            limit=20,
        )

    if not top_keywords:
        st.info("No taxonomy-matched keywords for the selected filters.")
    else:
        table_rows = [
            {
                "Keyword": r["keyword"],
                "Category": r["category"],
                "Mentions": r["mention_count"],
                "Sources": r["source_diversity"],
                "Avg. Confidence": round(r["avg_confidence"], 2)
                if r["avg_confidence"] is not None
                else None,
            }
            for r in top_keywords
        ]
        st.dataframe(table_rows, use_container_width=True, hide_index=True)

        # --- Trend Map bubble chart ---
        st.header("Trend Map")
        st.caption(
            "Y-axis shows match confidence, not momentum — momentum isn't "
            "computable at this granularity yet (see Momentum section below)."
        )
        fig = px.scatter(
            table_rows,
            x="Mentions",
            y="Avg. Confidence",
            size="Sources",
            color="Category",
            hover_name="Keyword",
            size_max=40,
            color_discrete_sequence=BUBBLE_COLORS,
        )
        fig.update_layout(
            plot_bgcolor="#1A1A2E",
            paper_bgcolor="#1A1A2E",
            font_color="#F5F3F0",
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Momentum (Google Trends) ---
    st.header("Momentum (Google Trends)")
    with st.spinner("Loading momentum data..."):
        trend_signals = db.get_all_trend_signals(engine)

    if not trend_signals:
        st.info("No momentum data yet.")
    else:
        momentum_rows = [
            {
                "Keyword": r["keyword"],
                "Momentum Score": r["momentum_score"],
                "Trend Status": classify_trend(r["momentum_score"], r["mention_count"]),
                "Mentions": r["mention_count"],
            }
            for r in trend_signals
        ]
        st.dataframe(momentum_rows, use_container_width=True, hide_index=True)

    st.caption(
        "Scoring based on Google Trends 0-100 scale. Near-zero baselines can "
        "inflate momentum (e.g. quiet luxury: 333% growth from a low-activity "
        "week). More reliable once multi-source mention counts accumulate."
    )


if __name__ == "__main__":
    main()
