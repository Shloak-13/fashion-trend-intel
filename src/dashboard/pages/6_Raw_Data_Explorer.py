"""Raw Data Explorer — Page 6 of the Fashion Trend Intelligence Dashboard.

Per CLAUDE.md Section 8.2. Streamlit auto-discovers this as a page alongside
src/dashboard/app.py (Page 1). A filterable table of every ingested
raw_content row plus a CSV export, for manual verification and interview
demos. raw_json (the full original API/scrape payload) is excluded from
both the table and the export -- it's a large blob, not useful in a demo
CSV, and it's what raw_content already stores if someone needs to go dig
into a specific row's original source.
"""

import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from src.storage import db  # noqa: E402

st.set_page_config(page_title="Raw Data Explorer", page_icon="🗃️", layout="wide")

st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def get_engine():
    return db.init_db()


def main():
    engine = get_engine()

    st.title("Raw Data Explorer")

    with st.spinner("Loading sources..."):
        sources = db.get_available_sources(engine)

    col1, col2, col3 = st.columns([1, 1, 2])
    with col1:
        source = st.selectbox("Source", ["All"] + sources)
    with col2:
        date_range = st.date_input("Published date range", value=())
    with col3:
        search = st.text_input("Search title/body", placeholder="e.g. oversized, Zara, quiet luxury...")

    published_after = None
    published_before = None
    if isinstance(date_range, tuple) and len(date_range) == 2:
        published_after = date_range[0].isoformat()
        published_before = date_range[1].isoformat()

    with st.spinner("Loading content..."):
        rows = db.get_raw_content_filtered(
            engine,
            source=None if source == "All" else source,
            published_after=published_after,
            published_before=published_before,
            search=search or None,
        )

    if not rows:
        st.info("No content matches the current filters.")
        return

    df = pd.DataFrame(rows)
    st.caption(f"{len(df)} rows")
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.download_button(
        "Export filtered results to CSV",
        data=df.to_csv(index=False).encode("utf-8"),
        file_name="raw_content_export.csv",
        mime="text/csv",
    )


if __name__ == "__main__":
    main()
