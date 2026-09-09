-- Raw ingested content
CREATE TABLE IF NOT EXISTS raw_content (
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
CREATE TABLE IF NOT EXISTS keywords (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id INTEGER REFERENCES raw_content(id),
    keyword TEXT NOT NULL,
    keyword_type TEXT,                 -- 'item', 'colour', 'pattern', 'brand', 'style'
    confidence FLOAT,
    extracted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trend taxonomy
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                -- e.g. 'Silhouette', 'Colour', 'Pattern', 'Item'
    parent_id INTEGER REFERENCES categories(id),
    level INTEGER                      -- 1=top, 2=mid, 3=leaf
);

-- Trend signals (aggregated)
CREATE TABLE IF NOT EXISTS trend_signals (
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
CREATE TABLE IF NOT EXISTS google_trends (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    keyword TEXT NOT NULL,
    date DATE NOT NULL,
    interest_value INTEGER,            -- 0-100 Google scale
    geo TEXT DEFAULT 'IN',
    ingested_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Brand tracking
CREATE TABLE IF NOT EXISTS brands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    tier TEXT,                         -- 'luxury', 'premium', 'mid', 'fast-fashion', 'indie'
    country_of_origin TEXT,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS brand_mentions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    brand_id INTEGER REFERENCES brands(id),
    content_id INTEGER REFERENCES raw_content(id),
    mention_context TEXT,
    sentiment FLOAT,
    mentioned_at TIMESTAMP
);
