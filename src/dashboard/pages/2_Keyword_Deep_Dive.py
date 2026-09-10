"""Keyword Deep Dive — Page 2 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8.2. Streamlit auto-discovers this as a page alongside
src/dashboard/app.py (Page 1). Run: streamlit run src/dashboard/app.py

Scoped to what the underlying data actually supports (per the project
owner): search + mention-volume time series + source breakdown + recent
linked mentions, all sourced from keywords + raw_content. The full spec
also lists "sentiment over time" and "co-occurring keywords" — sentiment
isn't built (Section 6.2 Step 5 is deferred, sentiment_score is never
populated, so a sentiment chart would be showing fabricated/empty data) and
co-occurring keywords wasn't requested for this page.
"""

import sys
from pathlib import Path

import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.storage import db  # noqa: E402

st.set_page_config(page_title="Keyword Deep Dive", page_icon="🔍", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

SOURCE_COLORS = ["#C9A99A", "#8FA6A3", "#D4B896", "#A9A3C9", "#B3C99A", "#C99AA3"]


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("Keyword Deep Dive")

    with st.spinner("Loading keyword list..."):
        all_keywords = db.get_all_keyword_names(engine)

    if not all_keywords:
        st.info("No keywords ingested yet.")
        return

    keyword = st.selectbox(
        "Search for a keyword",
        all_keywords,
        index=None,
        placeholder="Type to search any ingested keyword...",
    )

    if not keyword:
        st.caption(f"{len(all_keywords)} keywords available — start typing to search.")
        return

    # --- Time series ---
    st.header(f'"{keyword}" over time')
    with st.spinner("Loading mention history..."):
        series = db.get_keyword_time_series(engine, keyword)

    if not series:
        st.info("No dated mentions for this keyword (its source content has no published date).")
    else:
        fig = px.bar(
            series,
            x="date",
            y="mention_count",
            labels={"date": "Date", "mention_count": "Mentions"},
            color_discrete_sequence=[SOURCE_COLORS[0]],
        )
        fig.update_layout(
            plot_bgcolor="#1A1A2E",
            paper_bgcolor="#1A1A2E",
            font_color="#F5F3F0",
        )
        st.plotly_chart(fig, use_container_width=True)
        st.caption(
            "Mention volume by the date each piece of content was published — "
            "not a rolling trend, just how many pieces mentioning this keyword "
            "were published on each day covered by the current data."
        )

    # --- Source breakdown ---
    st.header("Where it's being talked about")
    with st.spinner("Loading source breakdown..."):
        breakdown = db.get_keyword_source_breakdown(engine, keyword)

    if not breakdown:
        st.info("No source data for this keyword.")
    else:
        fig = px.pie(
            breakdown,
            names="source",
            values="mention_count",
            color_discrete_sequence=SOURCE_COLORS,
            hole=0.4,
        )
        fig.update_layout(
            plot_bgcolor="#1A1A2E",
            paper_bgcolor="#1A1A2E",
            font_color="#F5F3F0",
        )
        st.plotly_chart(fig, use_container_width=True)

    # --- Recent mentions ---
    st.header("Recent mentions")
    with st.spinner("Loading recent mentions..."):
        mentions = db.get_keyword_recent_mentions(engine, keyword, limit=5)

    if not mentions:
        st.info("No linked mentions found for this keyword.")
    else:
        for m in mentions:
            published = m["published_at"] or "unknown date"
            author = f" · {m['author']}" if m["author"] else ""
            st.markdown(
                f"**[{m['title'] or m['url']}]({m['url']})**  \n"
                f"{m['source']} · {published}{author}"
            )


if __name__ == "__main__":
    main()
