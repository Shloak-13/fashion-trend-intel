# Screenshots

Images embedded in the project's main [README.md](../README.md) under "Dashboard Preview".

## Current screenshots

| File | Page | Shows |
|---|---|---|
| `trend-radar-top-keywords.jpg` | Page 1 — Trend Radar | Header, filters, Top Trending Keywords table |
| `trend-radar-bubble-momentum.jpg` | Page 1 — Trend Radar | Trend Map bubble chart, Momentum (Google Trends) table |
| `keyword-deep-dive.jpg` | Page 2 — Keyword Deep Dive | Search results for "fashion": time series chart |

## How to add a screenshot

1. Run the dashboard locally: `streamlit run src/dashboard/app.py`
2. Open it in a browser at `http://localhost:8501` and navigate to the page you want to capture.
3. Take a screenshot (window screenshot, not full-screen — keep it to the browser content area for a clean crop).
4. Save it here as a `.jpg` or `.png` with a descriptive `kebab-case` filename indicating the page and what it shows, e.g. `category-analysis-heatmap.png`.
5. Reference it from the main [README.md](../README.md)'s "Dashboard Preview" section with standard Markdown image syntax:
   ```markdown
   ![Alt text describing the screenshot](screenshots/your-filename.jpg)
   ```
6. Keep file sizes reasonable (a few hundred KB each) — this is a public repo, and large images slow down cloning.

## As more pages get built

Add one screenshot per new page (Category Analysis, Colour Trends, Brand Monitor, Raw Data Explorer per `CLAUDE.md` Section 8.2) following the same naming pattern (`page-name-what-it-shows.jpg`), and add a row to the table above plus an entry in the README's Dashboard Preview section.
