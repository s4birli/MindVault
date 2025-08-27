-- Patch: qresults qlog_id columna standardize + FK + index

-- 1) qlog_id kolonu yoksa ekle (nullable)
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name='qresults' AND column_name='qlog_id'
  ) THEN
    EXECUTE 'ALTER TABLE qresults ADD COLUMN qlog_id uuid';
  END IF;
END$$;

-- 2) Eski şemada "qlog" isimli bir kolon olabilir; varsa qlog_id'yi ondan doldur
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name='qresults' AND column_name='qlog'
  )
  AND EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name='qresults' AND column_name='qlog_id'
  )
  THEN
    EXECUTE 'UPDATE qresults SET qlog_id = qlog WHERE qlog_id IS NULL';
  END IF;
END$$;

-- 3) qlog_id'yi NOT NULL yap (tüm satırlar doluysa)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.columns
    WHERE table_name='qresults' AND column_name='qlog_id'
  ) THEN
    -- Sadece boş kayıt yoksa NOT NULL uygula
    IF NOT EXISTS (SELECT 1 FROM qresults WHERE qlog_id IS NULL) THEN
      EXECUTE 'ALTER TABLE qresults ALTER COLUMN qlog_id SET NOT NULL';
    END IF;
  END IF;
END$$;

-- 4) FK yoksa ekle
DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint
    WHERE conname = 'qresults_qlog_id_fkey'
  ) THEN
    EXECUTE 'ALTER TABLE qresults
             ADD CONSTRAINT qresults_qlog_id_fkey
             FOREIGN KEY (qlog_id) REFERENCES qlog(id) ON DELETE CASCADE';
  END IF;
END$$;

-- 5) Index yoksa ekle
CREATE INDEX IF NOT EXISTS idx_qresults_qlog ON qresults(qlog_id);

-- 6) Eski "qlog" kolonu varsa ve FK artık qlog_id üzerindeyse, kaldır (opsiyonel)
DO $$
BEGIN
  IF EXISTS (
    SELECT 1
    FROM information_schema.columns
    WHERE table_name='qresults' AND column_name='qlog'
  ) THEN
    EXECUTE 'ALTER TABLE qresults DROP COLUMN qlog';
  END IF;
END$$;