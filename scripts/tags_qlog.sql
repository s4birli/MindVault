-- Tags
CREATE TABLE IF NOT EXISTS tags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_lower
  ON tags (lower(name));

-- Document ↔ Tag
CREATE TABLE IF NOT EXISTS document_tags (
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    tag_id UUID REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

-- Query Log
CREATE TABLE IF NOT EXISTS qlog (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    query_text TEXT NOT NULL,
    lang TEXT DEFAULT 'en',
    user_id TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Query Results
CREATE TABLE IF NOT EXISTS qresults (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id UUID REFERENCES qlog(id) ON DELETE CASCADE,
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    rank INT,
    score FLOAT,
    clicked BOOLEAN DEFAULT false,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Query Feedback (thumbs up/down, rating)
CREATE TABLE IF NOT EXISTS qfeedback (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id UUID REFERENCES qlog(id) ON DELETE CASCADE,
    feedback TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Query Outcome (actions taken)
CREATE TABLE IF NOT EXISTS qoutcome (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id UUID REFERENCES qlog(id) ON DELETE CASCADE,
    outcome TEXT,
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Indexes for FTS (TR + EN with unaccent)
CREATE INDEX IF NOT EXISTS idx_documents_fts_tr
  ON documents USING gin (to_tsvector('turkish_unaccent', coalesce(plain_text,'')));

CREATE INDEX IF NOT EXISTS idx_documents_fts_unaccent
  ON documents USING gin (to_tsvector('simple_unaccent', coalesce(plain_text,'')));

ANALYZE tags;