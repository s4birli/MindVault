-- =============================
-- MindVault DB Init Migration
-- =============================

-- Extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;  -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS unaccent;  -- normalize text
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector

-- ==============
-- Core Tables
-- ==============
CREATE TABLE IF NOT EXISTS sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,         -- gmail, outlook, telegram, gcal...
    account_id text NOT NULL,       -- external account identifier
    created_at timestamptz DEFAULT now()
);

ALTER TABLE sources
  ADD CONSTRAINT sources_provider_account_unique
  UNIQUE (provider, account_id);

CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid REFERENCES sources(id) ON DELETE CASCADE,
    external_id text,
    title text,
    preview text,
    plain_text text,
    ts timestamptz,
    source_url text,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding vector(1536)          -- OpenAI text-embedding-3-small
);

ALTER TABLE documents
  ADD CONSTRAINT documents_unique_external_per_source
  UNIQUE (source_id, external_id);

-- ==============
-- Tags
-- ==============
CREATE TABLE IF NOT EXISTS tags (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_lower
  ON tags (lower(name));

CREATE TABLE IF NOT EXISTS document_tags (
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    tag_id uuid REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

-- ==============
-- Query Log
-- ==============
CREATE TABLE IF NOT EXISTS qlog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query text NOT NULL,
    lang text,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qresults (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    rank int,
    score float,
    clicked bool DEFAULT false
);

CREATE TABLE IF NOT EXISTS qfeedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    feedback text,
    created_at timestamptz DEFAULT now()
);

CREATE TABLE IF NOT EXISTS qoutcome (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    action text,
    outcome text,
    created_at timestamptz DEFAULT now()
);

-- ==============
-- Indexes
-- ==============
-- Full-text (multi-lingual, with unaccent fallback)
CREATE INDEX IF NOT EXISTS idx_documents_fts_simple
ON documents USING gin (
  to_tsvector('simple_unaccent',
    coalesce(title,'') || ' ' || coalesce(preview,'') || ' ' || coalesce(plain_text,'')
  )
);

-- Vector index (IVFFLAT)
CREATE INDEX IF NOT EXISTS idx_documents_embedding
ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Speed up tag/doc lookups
CREATE INDEX IF NOT EXISTS idx_document_tags_doc ON document_tags(document_id);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag_id);

-- =============================
-- Done
-- =============================