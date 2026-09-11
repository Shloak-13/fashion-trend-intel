"""Brand Monitor — Page 5 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8.2. Streamlit auto-discovers this as a page alongside
src/dashboard/app.py (Page 1).

Data-reality note (same honesty pattern as Pages 1-4): the brands and
brand_mentions tables were empty and unpopulated by any pipeline step --
CLAUDE.md Section 6.2 Step 4 (NER for brands) was deferred, same as
sentiment (Step 5). src/processing/brand_tagger.py fills that gap with a
seeded-brand-list matcher (not general NER) and real TextBlob sentiment per
mention -- see that module's docstring. "Emerging brands" is the spec's
term, but with ~2 weeks of data there's no real momentum to measure per
brand (same constraint as Page 1's keyword momentum), so this page shows
low-history brands (few total mentions so far) instead of a fabricated
rising/falling signal.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.storage import db  # noqa: E402

st.set_page_config(page_title="Brand Monitor", page_icon="🏷️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

BAR_COLORS = ["#C9A99A", "#8FA6A3", "#D4B896", "#A9A3C9", "#B3C99A", "#C99AA3"]
DARK_LAYOUT = dict(plot_bgcolor="#1A1A2E", paper_bgcolor="#1A1A2E", font_color="#F5F3F0")
LOW_HISTORY_THRESHOLD = 2


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("Brand Monitor")

    with st.spinner("Loading brand mentions..."):
        brands = db.get_top_brands(engine, limit=1000)

    if not brands:
        st.info("No brand mentions tagged yet. Run `python -m src.processing.brand_tagger`.")
        return

    # --- Most-mentioned brands ---
    st.header("Most-mentioned brands")
    table = [
        {
            "Brand": b["brand"],
            "Tier": b["tier"],
            "Mentions": b["mention_count"],
            "Sources": b["source_diversity"],
            "Avg Sentiment": round(b["avg_sentiment"], 3) if b["avg_sentiment"] is not None else None,
        }
        for b in brands
    ]
    st.dataframe(table, use_container_width=True, hide_index=True)
    st.caption(
        "Ranked by mention count across all ingested content. Detected via a seeded brand-name "
        "matcher (31 tracked brands), not general-purpose entity recognition -- brands outside "
        "that list won't appear here."
    )

    # --- Sentiment by brand ---
    st.header("Sentiment by brand")
    top_n = brands[:15]
    df = pd.DataFrame(
        [{"Brand": b["brand"], "Avg Sentiment": b["avg_sentiment"]} for b in top_n]
    ).sort_values("Avg Sentiment")
    fig = px.bar(
        df,
        x="Avg Sentiment",
        y="Brand",
        orientation="h",
        color_discrete_sequence=[BAR_COLORS[0]],
        labels={"Avg Sentiment": "Average sentiment (-1 to 1)"},
    )
    fig.update_layout(**DARK_LAYOUT)
    st.plotly_chart(fig, use_container_width=True)
    st.caption(
        "Real TextBlob polarity computed per mention's source text (title + body), averaged per "
        "brand -- a lightweight lexical sentiment score, not the Section 6.2 Step 5 transformer model."
    )

    # --- Low-history brands ---
    st.header("Emerging brands")
    low_history = [b for b in brands if b["mention_count"] <= LOW_HISTORY_THRESHOLD]
    if not low_history:
        st.info("No low-history brands right now -- every tracked brand has more than "
                 f"{LOW_HISTORY_THRESHOLD} mentions.")
    else:
        st.dataframe(
            [{"Brand": b["brand"], "Tier": b["tier"], "Mentions": b["mention_count"]} for b in low_history],
            use_container_width=True,
            hide_index=True,
        )
    st.caption(
        f"Brands with {LOW_HISTORY_THRESHOLD} or fewer total mentions so far -- a proxy for "
        "newcomers/low-signal names, not measured momentum. With ~2 weeks of data there isn't "
        "enough history yet to compute a real week-over-week growth rate per brand."
    )

    # --- Brand <-> trend associations ---
    st.header("Brand ↔ trend associations")
    brand_names = [b["brand"] for b in brands]
    selected_brand = st.selectbox("Select a brand", brand_names)

    with st.spinner("Loading co-occurring keywords..."):
        cooccurring = db.get_brand_keyword_cooccurrence(engine, selected_brand)

    if not cooccurring:
        st.info(f"No co-occurring taxonomy keywords found for {selected_brand} yet.")
    else:
        st.dataframe(
            [
                {"Keyword": r["keyword"], "Category": r["category"], "Co-mentions": r["co_mention_count"]}
                for r in cooccurring
            ],
            use_container_width=True,
            hide_index=True,
        )
        st.caption(
            f"Taxonomy-matched keywords appearing in the same content as {selected_brand} mentions, "
            "ranked by how often they co-occur."
        )


if __name__ == "__main__":
    main()
