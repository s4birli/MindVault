-- =============================
-- PostgreSQL Extensions Setup
-- =============================
-- This script installs all required extensions for MindVault
-- Run this before other migration scripts

-- Core extensions
CREATE EXTENSION IF NOT EXISTS pgcrypto;    -- For gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS unaccent;    -- For text normalization (remove accents)
CREATE EXTENSION IF NOT EXISTS vector;      -- For pgvector (embeddings)
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- For trigram matching

-- Verify extensions are installed
SELECT 
    extname as "Extension Name",
    extversion as "Version"
FROM pg_extension 
WHERE extname IN ('pgcrypto', 'unaccent', 'vector', 'pg_trgm')
ORDER BY extname;

-- Show available text search configurations
SELECT cfgname as "Text Search Config" 
FROM pg_ts_config 
WHERE cfgname LIKE '%unaccent%' OR cfgname LIKE '%simple%' OR cfgname LIKE '%turkish%'
ORDER BY cfgname;
