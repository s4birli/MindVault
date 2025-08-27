-- Enable required extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS unaccent;
CREATE EXTENSION IF NOT EXISTS vector;    -- pgvector
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Sources (email accounts, telegram, calendar, etc.)
CREATE TABLE IF NOT EXISTS sources (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    provider TEXT NOT NULL,               -- gmail, outlook, telegram, gcal, etc.
    account_id TEXT NOT NULL,             -- unique per provider
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE sources
  ADD CONSTRAINT sources_provider_account_unique
  UNIQUE (provider, account_id);

-- Documents (normalized items across all providers)
CREATE TABLE IF NOT EXISTS documents (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id UUID REFERENCES sources(id) ON DELETE CASCADE,
    external_id TEXT,                      -- provider-specific id
    title TEXT,
    preview TEXT,
    plain_text TEXT,
    ts TIMESTAMPTZ,
    source_url TEXT,
    metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),                -- OpenAI text-embedding-3-small
    created_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now()
);

ALTER TABLE documents
  ADD CONSTRAINT documents_unique_external_per_source
  UNIQUE (source_id, external_id);

-- Chunks (for long docs split into embeddings)
CREATE TABLE IF NOT EXISTS document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    chunk_index INT NOT NULL,
    content TEXT NOT NULL,
    embedding VECTOR(1536),
    created_at TIMESTAMPTZ DEFAULT now()
);

-- Entities (optional: people/orgs extracted)
CREATE TABLE IF NOT EXISTS entities (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    kind TEXT,                             -- person, org, location, etc.
    metadata JSONB DEFAULT '{}'::jsonb
);

-- Actions (email reply, calendar create, etc.)
CREATE TABLE IF NOT EXISTS actions (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID REFERENCES documents(id) ON DELETE CASCADE,
    action_type TEXT NOT NULL,             -- email_reply, calendar_create
    payload JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMPTZ DEFAULT now(),
    executed_at TIMESTAMPTZ
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_documents_ts ON documents(ts DESC);
CREATE INDEX IF NOT EXISTS idx_documents_source ON documents(source_id);
CREATE INDEX IF NOT EXISTS idx_documents_fts
  ON documents USING gin (to_tsvector('simple', coalesce(plain_text,'')));
CREATE INDEX IF NOT EXISTS idx_documents_embedding
  ON documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

ANALYZE documents;