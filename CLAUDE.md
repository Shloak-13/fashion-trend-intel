# Fashion Trend Intelligence Dashboard
## CLAUDE.md — Full Project Scope

---

## 1. PROJECT OVERVIEW

### What This Is
A data pipeline + analytics dashboard that tracks, monitors, and visualises emerging fashion trends in near-real-time using publicly available data sources. It does NOT predict the future. It surfaces what is gaining momentum RIGHT NOW — faster and more structured than any human manually browsing Instagram or Vogue.

### What This Is NOT
- A trend prediction oracle
- A guaranteed revenue tool
- A replacement for human creative judgement

### Why It Matters (Job Angle)
This project demonstrates:
- Cross-domain data science (fashion + analytics)
- End-to-end pipeline ownership (ingestion → processing → visualisation)
- Industry awareness — you built something for THEIR world
- Tangible output — a live dashboard, not just a notebook

Target roles this supports: Data Analyst, Business Analyst, Marketing Analyst, Brand Analyst at fashion/retail companies.

---

## 2. ARCHITECTURE OVERVIEW

```
[Data Sources]
      │
      ▼
[Ingestion Layer]     ← Python scrapers + API clients
      │
      ▼
[Raw Storage]         ← SQLite (local dev) → PostgreSQL (production)
      │
      ▼
[Processing Layer]    ← Cleaning, NLP, scoring, deduplication
      │
      ▼
[Analytics Layer]     ← Trend scoring, momentum calculation, category tagging
      │
      ▼
[Serving Layer]       ← FastAPI or Flask REST endpoints
      │
      ▼
[Dashboard]           ← Streamlit (fast) or Power BI (portfolio credibility)
```

---

## 3. DATA SOURCES

### 3.1 Free / No Auth Required
| Source | What You Get | Method |
|--------|-------------|--------|
| Google Trends | Search volume over time for fashion keywords | `pytrends` library |
| Reddit (r/femalefashionadvice, r/malefashionadvice, r/streetwear) | Real user conversations about what they're wearing | `praw` (Reddit API — free) |
| Hacker News / Product Hunt | Not fashion-specific but surfaces emerging DTC brands | Public API |
| Common Crawl | Bulk web text including fashion blogs | S3 access, free |

### 3.2 Requires Free Account / API Key
| Source | What You Get | Method |
|--------|-------------|--------|
| Pinterest API | Pin volume, board trends, visual categories | Pinterest Developer API (apply for access) |
| Twitter/X Basic API | Hashtag velocity, influencer mentions | X API v2 free tier (limited) |
| NewsAPI | Fashion magazine articles, press releases | newsapi.org free tier (100 req/day) |
| Unsplash API | Fashion image metadata (tags, categories) | Free API key |

### 3.3 Scrapeable (Respect robots.txt)
| Source | What You Get | Notes |
|--------|-------------|-------|
| Vogue Runway (vogue.com/runway) | Season collections, designer names, categories | Check robots.txt first |
| WGSN Blog (public posts only) | Trend reports (partial) | Limited public content |
| Who What Wear | Street style trend articles | Scrapeable headlines + tags |
| Hypebeast / Highsnobiety | Streetwear and hype trend signals | Good for youth/Gen Z angle |
| SSENSE Editorial | Luxury/avant-garde signals | Low volume, high signal |

### 3.4 Datasets (Download Once)
| Dataset | Source | Use |
|---------|--------|-----|
| Fashion-MNIST | Hugging Face / Kaggle | Clothing category classification model |
| DeepFashion | MMLAB (HK) | Attribute detection (colour, silhouette, pattern) |
| FARFETCH Open Data | Kaggle | Product attribute tags at scale |
| Stylepedia | Academic dataset | Fashion concept taxonomy |

### 3.5 What NOT to Scrape
- Instagram (aggressively blocks, account bans)
- TikTok (no public API, scraping violates ToS)
- Amazon (blocks aggressively)
- Any source with explicit no-scrape in robots.txt

---

## 4. DATA PIPELINE SPECIFICATION

### 4.1 Directory Structure
```
fashion-trend-intel/
├── CLAUDE.md                    ← this file
├── README.md
├── .env                         ← API keys (never commit)
├── .env.example                 ← template with key names only
├── .gitignore
├── requirements.txt
├── data/
│   ├── raw/                     ← untouched ingested data
│   ├── processed/               ← cleaned, structured
│   └── exports/                 ← CSVs for Power BI / Tableau
├── src/
│   ├── ingestion/
│   │   ├── google_trends.py
│   │   ├── reddit_scraper.py
│   │   ├── news_scraper.py
│   │   ├── web_scraper.py
│   │   └── pinterest_client.py
│   ├── processing/
│   │   ├── cleaner.py           ← deduplication, null handling
│   │   ├── nlp_pipeline.py      ← keyword extraction, entity recognition
│   │   ├── categoriser.py       ← map to taxonomy
│   │   └── scorer.py            ← trend momentum scoring
│   ├── storage/
│   │   ├── db.py                ← SQLite/PostgreSQL connection
│   │   └── schema.sql           ← table definitions
│   ├── api/
│   │   └── app.py               ← FastAPI endpoints for dashboard
│   └── dashboard/
│       └── app.py               ← Streamlit dashboard
├── notebooks/
│   ├── 01_data_exploration.ipynb
│   ├── 02_nlp_experiments.ipynb
│   └── 03_trend_scoring_logic.ipynb
├── tests/
│   ├── test_ingestion.py
│   ├── test_processing.py
│   └── test_scoring.py
└── scheduler/
    └── cron_jobs.py             ← APScheduler for automated runs
```

### 4.2 Database Schema

```sql
-- Raw ingested content
CREATE TABLE raw_content (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,              -- 'reddit', 'google_trends', 'news', etc.
    source_id TEXT,                    -- original ID from source
    url TEXT,
    title TEXT,
    body TEXT,
    author TEXT,
    published_at TIMESTAMP,
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    raw_json TEXT                      -- full original payload
);

-- Extracted keywords and entities
CREATE TABLE keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER REFERENCES raw_content(id),
    keyword TEXT NOT NULL,
    keyword_type TEXT,                 -- 'item', 'colour', 'pattern', 'brand', 'style'
    confidence FLOAT,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trend taxonomy
CREATE TABLE categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                -- e.g. 'Silhouette', 'Colour', 'Pattern', 'Item'
    parent_id INTEGER REFERENCES categories(id),
    level INTEGER                      -- 1=top, 2=mid, 3=leaf
);

-- Trend signals (aggregated)
CREATE TABLE trend_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    category_id INTEGER REFERENCES categories(id),
    date DATE NOT NULL,
    mention_count INTEGER DEFAULT 0,
    sentiment_score FLOAT,             -- -1 to 1
    momentum_score FLOAT,              -- week-over-week velocity
    source_diversity INTEGER,          -- how many different sources mentioned it
    computed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Google Trends specific
CREATE TABLE google_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    date DATE NOT NULL,
    interest_value INTEGER,            -- 0-100 Google scale
    geo TEXT DEFAULT 'IN',
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Brand tracking
CREATE TABLE brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tier TEXT,                         -- 'luxury', 'premium', 'mid', 'fast-fashion', 'indie'
    country_of_origin TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE brand_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER REFERENCES brands(id),
    content_id INTEGER REFERENCES raw_content(id),
    mention_context TEXT,
    sentiment FLOAT,
    mentioned_at TIMESTAMP
);
```

---

## 5. TAXONOMY (Fashion Keyword Categories)

Claude Code must maintain this taxonomy throughout. Every extracted keyword maps to one of these.

### 5.1 Clothing Items
- Tops: blouse, crop top, corset, bodysuit, tank, shirt, turtleneck, cardigan, blazer, jacket, coat, trench, bomber, hoodie, sweater, vest
- Bottoms: jeans, trousers, shorts, skirt, mini skirt, midi skirt, maxi skirt, leggings, cargo pants, wide leg, straight leg, flared
- Dresses: mini dress, midi dress, maxi dress, slip dress, wrap dress, shirt dress, co-ord set
- Footwear: sneakers, boots, loafers, mules, heels, platforms, mary janes, sandals, ballet flats
- Accessories: bag, tote, shoulder bag, clutch, crossbody, belt, scarf, hat, cap, beret, jewellery, sunglasses, watch

### 5.2 Silhouettes
- oversized, slim fit, tailored, relaxed, fitted, boxy, draped, structured, fluid, layered, asymmetric

### 5.3 Colours (Track These Specifically)
- neutrals: beige, cream, ecru, camel, sand, white, off-white, black, grey, charcoal
- brights: cobalt blue, electric blue, hot pink, fuchsia, lime green, tangerine, cherry red
- pastels: lavender, sage green, dusty pink, powder blue, mint, butter yellow
- trends (seasonal): track whatever colour is appearing most frequently

### 5.4 Patterns & Textures
- floral, stripe, check, plaid, houndstooth, animal print, leopard, zebra, snake, tie-dye, colour block, graphic print, abstract, solid, burnout velvet, crochet, lace, leather, denim, linen, silk, satin, velvet, sequin, mesh, knit

### 5.5 Aesthetics / Style Movements
- quiet luxury, old money, streetwear, Y2K, cottagecore, dark academia, coastal grandmother, barbiecore, gorpcore, bimbocore, mob wife, clean girl, minimalism, maximalism, avant-garde, preppy, grunge, boho

### 5.6 Occasions
- workwear, casual, evening, resort, athleisure, loungewear, occasion wear, bridal, festival

---

## 6. NLP PIPELINE SPECIFICATION

### 6.1 Libraries Required
```
spacy>=3.7.0
transformers>=4.40.0
sentence-transformers>=2.7.0
nltk>=3.8.0
textblob>=0.18.0
keybert>=0.8.0
```

### 6.2 Processing Steps (in order)

**Step 1 — Text Cleaning**
- Remove URLs, HTML tags, special characters
- Normalise unicode (é → e for matching)
- Lowercase
- Remove duplicates by URL and content hash

**Step 2 — Language Detection**
- Use `langdetect`
- Keep English only for v1. Flag others for v2 expansion.

**Step 3 — Keyword Extraction**
- Use KeyBERT with fashion-specific seed keywords
- Extract 5-15 keywords per document
- Match against taxonomy above
- Flag unmatched keywords as "emerging" — these are valuable

**Step 4 — Named Entity Recognition**
- Use spaCy `en_core_web_sm`
- Extract: brand names (ORG), people (PERSON — designers/influencers), locations (GPE — fashion weeks)
- Custom entity ruler for fashion brands not in spaCy default

**Step 5 — Sentiment Analysis**
- Use `cardiffnlp/twitter-roberta-base-sentiment` from HuggingFace
- Score each document: positive / neutral / negative
- Aggregate to keyword level

**Step 6 — Category Mapping**
- Map extracted keywords to taxonomy using:
  1. Exact match (fast)
  2. Fuzzy match with `rapidfuzz` (threshold 85)
  3. Semantic similarity with sentence-transformers (fallback)

**Step 7 — Trend Scoring**
```python
def compute_momentum_score(keyword, current_week_count, prev_week_count, source_diversity):
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
```

**Step 8 — Trend Classification**
Based on momentum score:
- `emerging`: momentum > 0.5, mention count < 100 (new, catching fire)
- `rising`: momentum > 0.2, mention count 100-1000
- `peak`: momentum -0.1 to 0.2, mention count > 1000
- `declining`: momentum < -0.1
- `stable`: consistent mention count, low variance

---

## 7. INGESTION SCRIPTS SPECIFICATION

### 7.1 Google Trends Ingester
```python
# src/ingestion/google_trends.py
# Library: pytrends
# Run: daily at 6am
# Keywords to track: pull from taxonomy + top 50 current keywords from DB
# Geo: IN (India) + US + GB — compare across markets
# Timeframe: past 90 days rolling window
# Store in: google_trends table
# Rate limit: 1 request per 5 seconds (avoid 429s)
```

### 7.2 Reddit Ingester
```python
# src/ingestion/reddit_scraper.py
# Library: praw
# Subreddits: r/femalefashionadvice, r/malefashionadvice, r/streetwear, 
#             r/india (fashion posts), r/IndianFashionAddicts
# What to pull: top posts (week), new posts, hot posts
# Fields: title, selftext, score, num_comments, created_utc, url
# Run: every 6 hours
# Store in: raw_content table
```

### 7.3 News Ingester
```python
# src/ingestion/news_scraper.py
# Library: newsapi-python
# Queries: ["fashion trends", "street style", "runway", "designer", 
#           "fashion week", "Zara", "H&M", "luxury fashion"]
# Sources: vogue, elle, harpersbazaar, businessoffashion
# Run: daily at 7am
# Store in: raw_content table
```

### 7.4 Web Scraper
```python
# src/ingestion/web_scraper.py
# Library: requests + BeautifulSoup4
# Targets (check robots.txt before running):
#   - Who What Wear article headlines + tags
#   - Highsnobiety articles
#   - Hypebeast articles
# What to extract: headline, tags, published date, author
# Run: daily at 8am
# Respect: 2 second delay between requests, honour robots.txt
```

---

## 8. DASHBOARD SPECIFICATION

### 8.1 Technology Choice
**Use Streamlit for v1** — faster to build, Python-native, easy to demo.
**Export CSVs for Power BI** — for portfolio credibility in interviews.

### 8.2 Dashboard Pages

#### Page 1 — Trend Radar (Home)
- Header: "What's Trending in Fashion Right Now"
- Top 10 emerging keywords (momentum score, WoW change, sparkline)
- Top 10 rising keywords (same metrics)
- Trend map: bubble chart — x=mention volume, y=momentum, size=source diversity, colour=category
- Last updated timestamp
- Filters: Date range, Category, Source, Market (IN/US/GB)

#### Page 2 — Keyword Deep Dive
- Search bar: type any keyword
- Time series: mention volume over past 90 days
- Sentiment over time (positive/neutral/negative stacked area)
- Source breakdown: where is this being talked about?
- Co-occurring keywords: what appears alongside this term?
- Sample content: 5 most recent mentions with links

#### Page 3 — Category Analysis
- Select category from taxonomy (Silhouettes, Colours, Items, etc.)
- Ranked list: all keywords in category by momentum
- Heatmap: category × week — which categories are heating up?
- Comparison: select 2-5 keywords to compare over time

#### Page 4 — Colour Trends
- Dedicated page because colour is a primary hiring-manager conversation in fashion
- Current top colours by mention volume
- Palette visualisation: actual colour swatches with trend status
- Seasonal comparison: this season vs last season same period
- Market split: India vs US vs UK colour preferences

#### Page 5 — Brand Monitor
- Track which brands are being mentioned most
- Sentiment by brand
- Emerging brands: new names appearing in data (low history, rising fast)
- Association map: which trends are associated with which brands?

#### Page 6 — Raw Data Explorer
- Filterable table of all ingested content
- Export to CSV button
- Useful for manual verification and interview demos

### 8.3 Dashboard Design Principles
- Palette: deep charcoal (#1A1A2E) background, soft white text, accent in dusty rose (#C9A99A) — fashion-appropriate, not generic SaaS blue
- Typography: clean sans-serif (Inter), editorial feel
- No unnecessary decoration — data is the product
- Mobile-responsive (Streamlit handles this)
- Loading states on every data fetch

---

## 9. METRICS AND ANALYTICS DEFINITIONS

Every metric shown on the dashboard must be defined here. No ambiguity.

| Metric | Definition | Formula |
|--------|-----------|---------|
| Mention Count | Total documents containing keyword in period | COUNT(content_id) WHERE keyword matches |
| Momentum Score | Week-over-week growth adjusted for source diversity | See Section 6 Step 7 |
| Sentiment Score | Average sentiment across all mentions | AVG(sentiment) range -1 to 1 |
| Source Diversity | Number of unique sources mentioning keyword | COUNT(DISTINCT source) |
| Trend Status | Classification based on momentum + volume | See Section 6 Step 8 |
| WoW Change | Week-over-week mention count change | (this_week - last_week) / last_week × 100 |
| MoM Change | Month-over-month mention count change | Same formula, monthly |
| Co-occurrence Score | How often two keywords appear in same document | COUNT(both) / COUNT(either) |

---

## 10. SCHEDULER SPECIFICATION

```python
# scheduler/cron_jobs.py
# Library: APScheduler

SCHEDULE = {
    "google_trends": "0 6 * * *",        # daily 6am
    "reddit_ingestion": "0 */6 * * *",   # every 6 hours
    "news_ingestion": "0 7 * * *",       # daily 7am
    "web_scraper": "0 8 * * *",          # daily 8am
    "nlp_pipeline": "0 10 * * *",        # daily 10am (after ingestion done)
    "trend_scoring": "0 11 * * *",       # daily 11am (after NLP done)
    "csv_export": "0 12 * * *",          # daily noon (for Power BI refresh)
}
```

---

## 11. ENVIRONMENT VARIABLES

```bash
# .env.example — copy to .env and fill in values

# Reddit API (free at reddit.com/prefs/apps)
REDDIT_CLIENT_ID=
REDDIT_CLIENT_SECRET=
REDDIT_USER_AGENT=FashionTrendBot/1.0

# NewsAPI (free at newsapi.org)
NEWS_API_KEY=

# Pinterest (apply at developers.pinterest.com)
PINTEREST_ACCESS_TOKEN=

# Database
DATABASE_URL=sqlite:///data/fashion_trends.db

# Optional: upgrade to PostgreSQL later
# DATABASE_URL=postgresql://user:password@localhost:5432/fashion_trends
```

---

## 12. REQUIREMENTS.TXT

```
# Data ingestion
pytrends==4.9.2
praw==7.7.1
newsapi-python==0.2.7
requests==2.31.0
beautifulsoup4==4.12.3
selenium==4.21.0          # only if JS rendering needed
fake-useragent==1.5.1

# Data processing
pandas==2.2.2
numpy==1.26.4
sqlalchemy==2.0.30
python-dotenv==1.0.1

# NLP
spacy==3.7.4
transformers==4.40.0
sentence-transformers==2.7.0
keybert==0.8.1
textblob==0.18.0
langdetect==1.0.9
rapidfuzz==3.9.0
torch==2.3.0               # for transformers

# Scheduling
apscheduler==3.10.4

# Dashboard
streamlit==1.35.0
plotly==5.22.0
altair==5.3.0

# Testing
pytest==8.2.0
pytest-cov==5.0.0

# Utilities
loguru==0.7.2               # better logging than print()
tqdm==4.66.4                # progress bars
```

---

## 13. BUILD ORDER FOR CLAUDE CODE

Build in this exact sequence. Do not skip ahead.

### Phase 1 — Foundation (Week 1)
1. Set up directory structure exactly as in Section 4.1
2. Create `.env.example` and `.gitignore`
3. Build `storage/schema.sql` and `storage/db.py`
4. Write `tests/test_db.py` — verify schema creates correctly
5. Build Google Trends ingester + test with 5 keywords
6. Build Reddit ingester + test with r/femalefashionadvice
7. Store raw data in DB, verify retrieval

### Phase 2 — Processing (Week 2)
1. Build `processing/cleaner.py`
2. Build `processing/nlp_pipeline.py` — keyword extraction only first
3. Build `processing/categoriser.py` — map to taxonomy
4. Build `processing/scorer.py` — implement momentum formula
5. Run full pipeline on collected data
6. Verify outputs in notebooks/02_nlp_experiments.ipynb

### Phase 3 — More Sources (Week 3)
1. Build news ingester
2. Build web scraper (Who What Wear first)
3. Build scheduler
4. Run full pipeline with all sources
5. Export CSVs for Power BI

### Phase 4 — Dashboard (Week 4)
1. Build Streamlit dashboard Page 1 (Trend Radar)
2. Build Page 2 (Keyword Deep Dive)
3. Build Page 3 (Category Analysis)
4. Build Page 4 (Colour Trends)
5. Add Page 5 and 6
6. Polish UI to match design spec in Section 8.3

### Phase 5 — Portfolio Packaging (Week 5)
1. Write README.md with screenshots
2. Build Power BI report from CSV exports
3. Record a 3-minute demo video
4. Deploy Streamlit to Streamlit Cloud (free)
5. Push to GitHub with clean commit history

---

## 14. WHAT TO TELL INTERVIEWERS

When presenting this project, use this framing:

**The problem**: Fashion buyers and brand analysts spend hours manually browsing Instagram, Vogue, and Reddit to understand what consumers are talking about. There's no structured, data-driven way to do this at scale for teams without large budgets.

**What I built**: An automated pipeline that ingests data from 5+ public sources daily, runs NLP to extract and categorise fashion keywords, scores each trend by momentum, and surfaces it in a dashboard that updates every 24 hours.

**Technical decisions worth discussing**:
- Why SQLite for v1 (simplicity, portability) vs PostgreSQL for production
- KeyBERT vs simple TF-IDF for keyword extraction (semantic understanding)
- Why source diversity is part of the momentum score (single-source spikes are noise)
- The difference between trend tracking and trend prediction (and why you chose tracking)

**Metrics that demonstrate value**:
- X keywords tracked across Y sources
- Pipeline processes Z articles per day
- Identified [specific real trend] N days before it appeared in mainstream coverage (if you find this, highlight it)

---

## 15. KNOWN LIMITATIONS (BE HONEST ABOUT THESE)

Document these. Acknowledging limitations in an interview shows maturity.

1. **English-only**: v1 does not handle Hindi, regional Indian languages — limits relevance for Indian market
2. **No Instagram/TikTok**: The two most important fashion signals are inaccessible via public APIs
3. **Lag**: Pipeline runs daily, not real-time — not suitable for fast-moving hype cycles
4. **No image analysis**: Text-only. Visual trend detection (silhouettes, colours in images) is v2
5. **Small dataset early on**: First 2 weeks of data will have insufficient history for reliable momentum scoring
6. **Survivorship bias in sources**: Public web over-indexes on English-language, Western fashion media

---

## 16. FUTURE EXTENSIONS (V2 IDEAS)

Keep these out of v1 scope but mention them in interviews.

- Image analysis using CLIP or FashionCLIP to extract visual trend signals from product images
- Indian market focus: integrate Myntra, Ajio, Nykaa Fashion product data
- Influencer tracking: identify micro-influencers driving emerging trends
- Price correlation: do trends correlate with price point shifts?
- Real-time alerts: Slack/email notification when a keyword crosses momentum threshold
- Competitor benchmarking: track which trends Brand A vs Brand B is responding to
- Hindi/regional language NLP: expand beyond English sources

---

## CLAUDE CODE INSTRUCTIONS

When building this project:

1. Always check `.env.example` before hardcoding any credentials
2. Every function needs a docstring
3. Every ingester must have a rate limiter — never hammer a source
4. Log everything with `loguru` — not `print()`
5. If a scrape fails, log and continue — never crash the full pipeline
6. Test each component in isolation before integrating
7. Commit after each working phase — clean git history matters for portfolio
8. If blocked on a data source, build the pipeline structure with mock data and continue
9. Keep notebooks clean and narrative — they are also portfolio pieces
10. The dashboard must work with 7 days of data minimum before calling Phase 4 complete
