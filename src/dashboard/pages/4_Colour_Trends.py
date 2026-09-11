"""Colour Trends — Page 4 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8.2. Streamlit auto-discovers this as a page alongside
src/dashboard/app.py (Page 1).

Data-reality note (confirmed with the project owner before building this):
the spec also asks for a "seasonal comparison: this season vs last season"
and a "market split: India vs US vs UK." Neither is buildable honestly right
now -- all ingested content spans about two weeks (no season boundary in the
data), and Google Trends colour data was only ever pulled for geo='IN' (see
src/ingestion/google_trends.py DEFAULT_KEYWORDS). So seasonal comparison is
omitted entirely, and "market split" is a single-market (India) view instead
of a real three-way comparison.
"""

import sys
from pathlib import Path

import pandas as pd
import plotly.express as px
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.processing.scorer import classify_trend  # noqa: E402
from src.storage import db  # noqa: E402

st.set_page_config(page_title="Colour Trends", page_icon="🎨", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)

DARK_LAYOUT = dict(plot_bgcolor="#1A1A2E", paper_bgcolor="#1A1A2E", font_color="#F5F3F0")

# The 10 colours seeded into Google Trends (geo=IN) for this page -- see
# src/ingestion/google_trends.py DEFAULT_KEYWORDS.
BASE_COLOURS = [
    "black", "white", "beige", "brown", "red",
    "pink", "blue", "green", "purple", "yellow",
]
HEX_MAP = {
    "black": "#1A1A1A",
    "white": "#F0EDE6",
    "beige": "#D9C6A5",
    "brown": "#6B4423",
    "red": "#B03A2E",
    "pink": "#D98EA8",
    "blue": "#3B6E9E",
    "green": "#4E7A51",
    "purple": "#7B5EA7",
    "yellow": "#D9B84E",
}


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("Colour Trends")

    # --- Top colours by mention volume ---
    st.header("Top colours by mention volume")
    with st.spinner("Loading colour keywords..."):
        rows = db.get_keywords_by_category(engine, "Colours")

    if not rows:
        st.info("No taxonomy-matched colour keywords yet.")
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
            "Ranked by mention count across all ingested content (news, blogs, forums). "
            "Includes NLP-matched phrases like 'dusty pink' or 'sacred white,' not just base "
            "colour names -- Momentum is only populated for the seeded Google Trends colours below."
        )

    # --- Palette with trend status ---
    st.header("Colour palette — trend status (India, Google Trends)")
    with st.spinner("Loading trend signals..."):
        signals = {s["keyword"]: s for s in db.get_all_trend_signals(engine)}

    cols = st.columns(5)
    for i, colour in enumerate(BASE_COLOURS):
        signal = signals.get(colour)
        with cols[i % 5]:
            st.markdown(
                f'<div style="background-color:{HEX_MAP[colour]}; height:56px; '
                f'border-radius:6px; border:1px solid #3A3A52;"></div>',
                unsafe_allow_html=True,
            )
            st.markdown(f"**{colour.capitalize()}**")
            if signal:
                status = classify_trend(signal["momentum_score"], signal["mention_count"])
                st.caption(f"{status} · momentum {signal['momentum_score']:+.3f}")
            else:
                st.caption("No trend data yet")

    st.caption(
        "Trend status from real week-over-week Google Trends interest (India). "
        "mention_count here is Google's 0-100 normalised interest score, not a document count."
    )

    # --- India interest over time ---
    st.header("India interest over time (Google Trends)")
    selected = st.multiselect("Colours to show", BASE_COLOURS, default=BASE_COLOURS)

    if not selected:
        st.caption("Select at least one colour.")
    else:
        frames = []
        for colour in selected:
            for point in db.get_google_trends_by_keyword(engine, colour):
                if point["geo"] == "IN":
                    frames.append(
                        {"date": point["date"], "interest_value": point["interest_value"], "colour": colour}
                    )

        if not frames:
            st.info("No India Google Trends data for the selected colours.")
        else:
            df = pd.DataFrame(frames)
            fig = px.line(
                df,
                x="date",
                y="interest_value",
                color="colour",
                labels={"date": "Date", "interest_value": "Interest (0-100)", "colour": "Colour"},
                color_discrete_map=HEX_MAP,
            )
            fig.update_layout(**DARK_LAYOUT)
            st.plotly_chart(fig, use_container_width=True)


if __name__ == "__main__":
    main()
