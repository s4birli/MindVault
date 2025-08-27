-- scripts/patch_2025_08_24_content_hash.sql
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name = 'documents' AND column_name = 'content_hash'
  ) THEN
    ALTER TABLE documents
      ADD COLUMN content_hash text;
  END IF;
END$$;

CREATE INDEX IF NOT EXISTS idx_documents_content_hash
  ON documents(content_hash);