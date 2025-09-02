-- =============================
-- PostgreSQL Extensions Setup
-- =============================
-- This script installs all required extensions for MindVault
-- Run this before other migration scripts

-- Core extensions
-- =========================================
CREATE EXTENSION IF NOT EXISTS vector;          -- pgvector (semantic search)
CREATE EXTENSION IF NOT EXISTS pg_trgm;         -- trigram (fuzzy ad eşleşmeleri)
CREATE EXTENSION IF NOT EXISTS postgis;     -- geo (isteğe bağlı)


-- Verify extensions are installed
SELECT 
    extname as "Extension Name",
    extversion as "Version"
FROM pg_extension 
WHERE extname IN ('vector', 'pg_trgm', 'postgis')
ORDER BY extname;