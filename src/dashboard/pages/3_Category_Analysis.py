"""Category Analysis — Page 3 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8.2. Streamlit auto-discovers this as a page alongside
src/dashboard/app.py (Page 1).

Data-reality note (same constraint as Page 1 — confirmed with the project
owner): the spec asks to rank keywords "by momentum," but real momentum only
exists for 5 Google-Trends-seeded keywords (see trend_signals). Everything
else only has real mention count / source diversity / confidence. So the
ranked list here sorts by mention count (real, available for every keyword)
and surfaces momentum as its own column, populated only where trend_signals
has a row for that keyword. The heatmap is real mention volume by category
and week, not momentum.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.processing.categoriser import TAXONOMY  # noqa: E402
from src.storage import db  # noqa: E402

st.set_page_config(page_title="Category Analysis", page_icon="🗂️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

LINE_COLORS = ["#C9A99A", "#8FA6A3", "#D4B896", "#A9A3C9", "#B3C99A"]
DARK_LAYOUT = dict(plot_bgcolor="#1A1A2E", paper_bgcolor="#1A1A2E", font_color="#F5F3F0")


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("Category Analysis")

    # --- Ranked list ---
    st.header("Keywords by category")
    category = st.selectbox("Select a category", list(TAXONOMY.keys()))

    with st.spinner("Loading category keywords..."):
        rows = db.get_keywords_by_category(engine, category)

    if not rows:
        st.info(f"No taxonomy-matched keywords for '{category}' yet.")
    else:
        table = [
            {
                "Keyword": r["keyword"],
                "Mentions": r["mention_count"],
                "Sources": r["source_diversity"],
                "Momentum": r["momentum_score"],
            }
            for r in rows
        ]
        st.dataframe(table, use_container_width=True, hide_index=True)
        st.caption(
            "Ranked by mention count — real momentum (week-over-week growth) is only "
            "available for the small set of keywords tracked via Google Trends, shown "
            "where present. A blank Momentum cell doesn't mean no momentum, it means "
            "no data yet."
        )

    # --- Heatmap ---
    st.header("Category heat over time")
    with st.spinner("Loading heatmap data..."):
        heatmap_rows = db.get_category_week_heatmap(engine)

    if not heatmap_rows:
        st.info("No dated content to build a heatmap from yet.")
    else:
        df = pd.DataFrame(heatmap_rows)
        pivot = df.pivot(index="category", columns="week", values="mention_count").fillna(0)
        fig = px.imshow(
            pivot,
            labels=dict(x="Week", y="Category", color="Mentions"),
            color_continuous_scale=[[0, "#1A1A2E"], [1, "#C9A99A"]],
            aspect="auto",
        )
        fig.update_layout(**DARK_LAYOUT)
        st.plotly_chart(fig, use_container_width=True)
        st.caption("Mention volume by category and week — which categories are getting talked about more.")

    # --- Comparison ---
    st.header("Compare keywords")
    with st.spinner("Loading keyword list..."):
        all_keywords = db.get_all_keyword_names(engine)

    selected = st.multiselect(
        "Pick 2-5 keywords to compare over time",
        all_keywords,
        max_selections=5,
    )

    if len(selected) < 2:
        st.caption("Select at least 2 keywords to compare.")
    else:
        frames = []
        for kw in selected:
            series = db.get_keyword_time_series(engine, kw)
            for point in series:
                frames.append({"date": point["date"], "mention_count": point["mention_count"], "keyword": kw})

        if not frames:
            st.info("No dated mentions for the selected keywords.")
        else:
            df = pd.DataFrame(frames)
            fig = px.line(
                df,
                x="date",
                y="mention_count",
                color="keyword",
                markers=True,
                labels={"date": "Date", "mention_count": "Mentions", "keyword": "Keyword"},
                color_discrete_sequence=LINE_COLORS,
            )
            fig.update_layout(**DARK_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
