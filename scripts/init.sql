-- =========================
-- FTS CONFIGS (unaccent + simple / turkish)
-- =========================

-- Basit & stabil: simple + unaccent (karma dil içerik için ideal)
DO $do$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'simple_unaccent') THEN
    EXECUTE 'CREATE TEXT SEARCH CONFIGURATION simple_unaccent ( COPY = simple )';
  END IF;

  -- Mapping'i güvenceye al (varsa da sorun olmaz)
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'simple_unaccent') THEN
    EXECUTE 'ALTER TEXT SEARCH CONFIGURATION simple_unaccent
             ALTER MAPPING FOR hword, hword_part, word WITH unaccent, simple';
  END IF;
END
$do$ LANGUAGE plpgsql;

-- Türkçe config varsa: turkish_unaccent (turkish_stem sözlüğü kurulu olan distrolarda)
DO $do$
BEGIN
  IF EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish') THEN
    IF NOT EXISTS (SELECT 1 FROM pg_ts_config WHERE cfgname = 'turkish_unaccent') THEN
      EXECUTE 'CREATE TEXT SEARCH CONFIGURATION turkish_unaccent ( COPY = turkish )';
    END IF;

    -- turkish_stem varsa onu, yoksa turkish sözlüğünü kullan
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

-- (Dilersen burada GIN indexlerini de aynı dosyada bırakmaya devam et)