-- =============================
-- MindVault Complete Database Initialization
-- =============================
-- This script creates all necessary tables, indexes, extensions, and configurations
-- for the MindVault system. Run this once on a fresh database.

-- =============================
-- Extensions
-- =============================
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- For gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS unaccent;    -- For text normalization (remove accents)
CREATE EXTENSION IF NOT EXISTS vector;      -- For pgvector (embeddings)
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- For trigram matching

-- =============================
-- Text Search Configurations
-- =============================

-- Simple unaccent configuration (multilingual)
DO $do$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'simple_unaccent') THEN
    EXECUTE 'CREATE TEXT SEARCH CONFIGURATION simple_unaccent ( COPY = simple )';
  END IF;

  -- Add unaccent mapping
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'simple_unaccent') THEN
    EXECUTE 'ALTER TEXT SEARCH CONFIGURATION simple_unaccent
             ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple';
  END IF;
END
$do$ LANGUAGE plpgsql;

-- Turkish unaccent configuration (if turkish dictionary is available)
DO $do$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish') THEN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish_unaccent') THEN
      EXECUTE 'CREATE TEXT SEARCH CONFIGURATION turkish_unaccent ( COPY = turkish )';
    END IF;

    -- Use turkish_stem if available, otherwise turkish
    IF EXISTS (SELECT 1 FROM pg_ts_dict WHERE dictname = 'turkish_stem') THEN
      EXECUTE 'ALTER TEXT SEARCH CONFIGURATION turkish_unaccent
               ALTER MAPPING FOR hword, hword_part, word WITH unaccent, turkish_stem';
    ELSE
      EXECUTE 'ALTER TEXT SEARCH CONFIGURATION turkish_unaccent
               ALTER MAPPING FOR hword, hword_part, word WITH unaccent, turkish';
    END IF;
  END IF;
END
$do$ LANGUAGE plpgsql;

-- =============================
-- Core Tables
-- =============================

-- Sources (email accounts, telegram, calendar, etc.)
CREATE TABLE IF NOT EXISTS sources (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    provider text NOT NULL,               -- gmail, outlook, telegram, gcal, etc.
    account_id text NOT NULL,             -- unique per provider
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Unique constraint for provider + account_id
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'sources_provider_account_unique') THEN
    ALTER TABLE sources ADD CONSTRAINT sources_provider_account_unique UNIQUE (provider, account_id);
  END IF;
END$$;

-- Documents (normalized items across all providers)
CREATE TABLE IF NOT EXISTS documents (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id uuid REFERENCES sources(id) ON DELETE CASCADE,
    external_id text,                      -- provider-specific id
    kind text,                            -- email, note, calendar_event, etc.
    title text,
    preview text,
    plain_text text,
    ts timestamptz,
    source_url text,
    metadata jsonb DEFAULT '{}'::jsonb,
    embedding vector(1536),                -- OpenAI text-embedding-3-small
    content_hash text,                     -- For deduplication
    created_at timestamptz DEFAULT now(),
    updated_at timestamptz DEFAULT now()
);

-- Unique constraint for external_id per source
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_unique_external_per_source') THEN
    ALTER TABLE documents ADD CONSTRAINT documents_unique_external_per_source UNIQUE (source_id, external_id);
  END IF;
END$$;

-- Document chunks (for long docs split into embeddings)
CREATE TABLE IF NOT EXISTS document_chunks (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    ord int NOT NULL,                     -- chunk order
    text text NOT NULL,                   -- chunk content
    embedding vector(1536),
    created_at timestamptz DEFAULT now()
);

-- =============================
-- Tags System
-- =============================

-- Tags (topics, labels, categories)
CREATE TABLE IF NOT EXISTS tags (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    created_at timestamptz DEFAULT now()
);

-- Case-insensitive unique index for tag names
CREATE UNIQUE INDEX IF NOT EXISTS idx_tags_name_lower
  ON tags (lower(name));

-- Document-Tag relationships (many-to-many)
CREATE TABLE IF NOT EXISTS document_tags (
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    tag_id uuid REFERENCES tags(id) ON DELETE CASCADE,
    PRIMARY KEY (document_id, tag_id)
);

-- Add named unique constraint for API compatibility
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_document_tags') THEN
    ALTER TABLE document_tags ADD CONSTRAINT uq_document_tags UNIQUE (document_id, tag_id);
  END IF;
END$$;

-- =============================
-- Query Logging & Analytics
-- =============================

-- Query log (search queries)
CREATE TABLE IF NOT EXISTS qlog (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    query text NOT NULL,
    lang text,
    created_at timestamptz DEFAULT now()
);

-- Query results (which documents were returned)
CREATE TABLE IF NOT EXISTS qresults (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    document_id uuid REFERENCES documents(id) ON DELETE CASCADE,
    rank int,
    score float,
    clicked bool DEFAULT false
);

-- Query feedback (user satisfaction)
CREATE TABLE IF NOT EXISTS qfeedback (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    feedback text,
    created_at timestamptz DEFAULT now()
);

-- Query outcomes (actions taken)
CREATE TABLE IF NOT EXISTS qoutcome (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    qlog_id uuid REFERENCES qlog(id) ON DELETE CASCADE,
    action text,
    outcome text,
    created_at timestamptz DEFAULT now()
);

-- =============================
-- Indexes for Performance
-- =============================

-- Document indexes
CREATE INDEX IF NOT EXISTS idx_documents_ts ON documents(ts DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_kind ON documents(kind);
CREATE INDEX IF NOT EXISTS idx_documents_content_hash ON documents(content_hash);

-- Full-text search index (multilingual with unaccent)
CREATE INDEX IF NOT EXISTS idx_documents_fts_simple
ON documents USING gin (
  to_tsvector('simple_unaccent',
    coalesce(title,'') || ' ' || coalesce(preview,'') || ' ' || coalesce(plain_text,'')
  )
);

-- Vector similarity index (IVFFLAT for cosine similarity)
CREATE INDEX IF NOT EXISTS idx_documents_embedding
ON documents
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Document chunks indexes
CREATE INDEX IF NOT EXISTS idx_document_chunks_document ON document_chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
ON document_chunks
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Tag relationship indexes
CREATE INDEX IF NOT EXISTS idx_document_tags_doc ON document_tags(document_id);
CREATE INDEX IF NOT EXISTS idx_document_tags_tag ON document_tags(tag_id);

-- Query log indexes
CREATE INDEX IF NOT EXISTS idx_qlog_created_at ON qlog(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_qresults_qlog ON qresults(qlog_id);
CREATE INDEX IF NOT EXISTS idx_qresults_document ON qresults(document_id);

-- =============================
-- Update Statistics
-- =============================
ANALYZE;

-- =============================
-- Verification
-- =============================

-- Show installed extensions
SELECT 
    extname as "Extension",
    extversion as "Version"
FROM pg_extension 
WHERE extname IN ('pgcrypto', 'unaccent', 'vector', 'pg_trgm')
ORDER BY extname;

-- Show created tables
SELECT 
    tablename as "Table",
    schemaname as "Schema"
FROM pg_tables 
WHERE schemaname = 'public'
ORDER BY tablename;

-- Show text search configurations
SELECT 
    cfgname as "Text Search Config"
FROM pg_ts_config 
WHERE cfgname LIKE '%unaccent%'
ORDER BY cfgname;

-- =============================
-- Complete!
-- =============================
