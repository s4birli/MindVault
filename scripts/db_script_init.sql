-- =========================================
-- ENTITIES (kişi / organizasyon / mekan)
-- =========================================
CREATE TABLE IF NOT EXISTS entities (
  entity_id    BIGSERIAL PRIMARY KEY,
  type         TEXT NOT NULL CHECK (type IN ('person','org','place')),
  name         TEXT NOT NULL,
  aliases      TEXT[]          DEFAULT '{}',
  emails       TEXT[]          DEFAULT '{}',
  phones       TEXT[]          DEFAULT '{}',
  domains      TEXT[]          DEFAULT '{}',
  meta         JSONB           DEFAULT '{}'::jsonb,
  created_at   TIMESTAMPTZ     DEFAULT now(),
  updated_at   TIMESTAMPTZ     DEFAULT now()
);

-- İsim ve alanlar için yardımcı indexler
CREATE INDEX IF NOT EXISTS idx_entities_name_trgm ON entities USING GIN (name gin_trgm_ops);
CREATE INDEX IF NOT EXISTS idx_entities_aliases   ON entities USING GIN (aliases);
CREATE INDEX IF NOT EXISTS idx_entities_domains   ON entities USING GIN (domains);

-- updated_at dokunuşu
CREATE OR REPLACE FUNCTION trg_entities_touch()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at := now();
  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entities_touch ON entities;
CREATE TRIGGER trg_entities_touch
BEFORE UPDATE ON entities
FOR EACH ROW EXECUTE FUNCTION trg_entities_touch();

-- =========================================
-- PREDICATES (tam generik ilişki tipleri)
-- =========================================
CREATE TABLE IF NOT EXISTS rel_predicates (
  predicate_id  BIGSERIAL PRIMARY KEY,
  code          TEXT UNIQUE NOT NULL,   -- 'service_provider_of','mentor_of','camcısı','advisor_of', ...
  direction     TEXT NOT NULL CHECK (direction IN ('symmetric','asymmetric')) DEFAULT 'asymmetric',
  inverse_id    BIGINT REFERENCES rel_predicates(predicate_id) ON DELETE SET NULL, -- ters yön pointer
  cardinality   TEXT CHECK (cardinality IN ('one_to_one','one_to_many','many_to_many')) DEFAULT 'many_to_many',
  parent_id     BIGINT REFERENCES rel_predicates(predicate_id) ON DELETE SET NULL, -- hiyerarşi (opsiyonel)
  is_personal   BOOLEAN DEFAULT TRUE,
  created_at    TIMESTAMPTZ DEFAULT now()
);

-- Çok dilli etiket/sinonimler
CREATE TABLE IF NOT EXISTS rel_predicate_labels (
  predicate_id  BIGINT NOT NULL REFERENCES rel_predicates(predicate_id) ON DELETE CASCADE,
  lang          TEXT   NOT NULL,        -- 'tr','en',...
  label         TEXT   NOT NULL,        -- birincil etiket (örn: 'emlakçısı')
  aliases       TEXT[] DEFAULT '{}',    -- sinonimler
  PRIMARY KEY (predicate_id, lang)
);

-- Serbest terim → predicate eşlemesi (oto oluşum)
CREATE TABLE IF NOT EXISTS rel_predicate_alias_map (
  lang          TEXT NOT NULL,
  term          TEXT NOT NULL,          -- duyulan ham ifade: 'camcısı','advisor','lettings agent'
  predicate_id  BIGINT NOT NULL REFERENCES rel_predicates(predicate_id) ON DELETE CASCADE,
  UNIQUE (lang, term)
);

-- Yardımcı: predicate oluştur/çek (etiket/alias ile)
CREATE OR REPLACE FUNCTION get_or_create_predicate(
  p_code       TEXT,
  p_lang       TEXT DEFAULT NULL,
  p_label      TEXT DEFAULT NULL,
  p_aliases    TEXT[] DEFAULT NULL,
  p_direction  TEXT DEFAULT 'asymmetric',
  p_cardinality TEXT DEFAULT 'many_to_many'
) RETURNS BIGINT AS $$
DECLARE v_id BIGINT;
BEGIN
  INSERT INTO rel_predicates(code, direction, cardinality)
  VALUES (p_code, p_direction, p_cardinality)
  ON CONFLICT (code) DO UPDATE SET code = EXCLUDED.code
  RETURNING predicate_id INTO v_id;

  IF p_lang IS NOT NULL AND p_label IS NOT NULL THEN
    INSERT INTO rel_predicate_labels(predicate_id, lang, label, aliases)
    VALUES (v_id, p_lang, p_label, COALESCE(p_aliases,'{}'))
    ON CONFLICT (predicate_id, lang) DO UPDATE
      SET label   = EXCLUDED.label,
          aliases = COALESCE(rel_predicate_labels.aliases,'{}') || COALESCE(EXCLUDED.aliases,'{}');

    INSERT INTO rel_predicate_alias_map(lang, term, predicate_id)
    VALUES (p_lang, lower(p_label), v_id)
    ON CONFLICT (lang, term) DO NOTHING;

    IF p_aliases IS NOT NULL THEN
      INSERT INTO rel_predicate_alias_map(lang, term, predicate_id)
      SELECT p_lang, lower(a), v_id FROM unnest(p_aliases) a
      ON CONFLICT (lang, term) DO NOTHING;
    END IF;
  END IF;

  RETURN v_id;
END$$ LANGUAGE plpgsql;

-- Yardımcı: iki predicate'i inverse olarak bağla (code üzerinden)
CREATE OR REPLACE FUNCTION link_inverse_predicates(p_code TEXT, p_inverse_code TEXT)
RETURNS VOID AS $$
DECLARE a BIGINT; DECLARE b BIGINT;
BEGIN
  a := get_or_create_predicate(p_code);
  b := get_or_create_predicate(p_inverse_code);
  UPDATE rel_predicates SET inverse_id = b WHERE predicate_id = a;
  UPDATE rel_predicates SET inverse_id = a WHERE predicate_id = b;
END$$ LANGUAGE plpgsql;

-- =========================================
-- GENERIC RELATIONS (özne–yüklem–nesne)
-- =========================================
CREATE TABLE IF NOT EXISTS entity_relations (
  rel_id          BIGSERIAL PRIMARY KEY,
  subject_id      BIGINT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  predicate_id    BIGINT NOT NULL REFERENCES rel_predicates(predicate_id) ON DELETE RESTRICT,
  object_id       BIGINT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
  start_at        TIMESTAMPTZ,
  end_at          TIMESTAMPTZ,
  confidence      REAL DEFAULT 1.0,
  source_item_id  BIGINT,                                   -- items'a FK aşağıda
  evidence_span   INT4RANGE,
  qualifiers      JSONB DEFAULT '{}'::jsonb,                -- {"role":"camcı","city":"Giresun"} gibi
  role_id         BIGINT,                                   -- opsiyonel: normalize rol (roles tablosu varsa)
  role_free       TEXT,                                     -- normalize yoksa serbest etiket
  created_by_system BOOLEAN NOT NULL DEFAULT FALSE,         -- inverse auto-insert kontrolü
  created_at      TIMESTAMPTZ DEFAULT now(),
  UNIQUE(subject_id, predicate_id, object_id)
);

-- Inverse ilişkileri otomatik yazan trigger (tam generik)
CREATE OR REPLACE FUNCTION trg_entity_relations_inverse()
RETURNS TRIGGER AS $$
DECLARE pred RECORD;
BEGIN
  IF NEW.created_by_system THEN
    RETURN NEW;
  END IF;

  SELECT * INTO pred FROM rel_predicates WHERE predicate_id = NEW.predicate_id;

  IF pred.direction = 'symmetric' THEN
    INSERT INTO entity_relations(subject_id, predicate_id, object_id, start_at, end_at, confidence,
                                 source_item_id, evidence_span, qualifiers, role_id, role_free, created_by_system)
    VALUES (NEW.object_id, NEW.predicate_id, NEW.subject_id, NEW.start_at, NEW.end_at, NEW.confidence,
            NEW.source_item_id, NEW.evidence_span, NEW.qualifiers, NEW.role_id, NEW.role_free, TRUE)
    ON CONFLICT (subject_id, predicate_id, object_id) DO NOTHING;

  ELSIF pred.direction = 'asymmetric' AND pred.inverse_id IS NOT NULL THEN
    INSERT INTO entity_relations(subject_id, predicate_id, object_id, start_at, end_at, confidence,
                                 source_item_id, evidence_span, qualifiers, role_id, role_free, created_by_system)
    VALUES (NEW.object_id, pred.inverse_id, NEW.subject_id, NEW.start_at, NEW.end_at, NEW.confidence,
            NEW.source_item_id, NEW.evidence_span, NEW.qualifiers, NEW.role_id, NEW.role_free, TRUE)
    ON CONFLICT (subject_id, predicate_id, object_id) DO NOTHING;
  END IF;

  RETURN NEW;
END$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_entity_relations_inverse ON entity_relations;
CREATE TRIGGER trg_entity_relations_inverse
AFTER INSERT ON entity_relations
FOR EACH ROW EXECUTE FUNCTION trg_entity_relations_inverse();

-- =========================================
-- USER-SPECIFIC ALIASES (hitap/çağrı: 'karım','emlakçım'…)
-- =========================================
CREATE TABLE IF NOT EXISTS alias_index (
  alias         TEXT NOT NULL,                    -- 'karım','eşim','emlakçım','my wife','my agent',...
  lang          TEXT NOT NULL,
  owner_id      BIGINT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,  -- konuşan
  default_predicate_code TEXT NOT NULL,           -- 'spouse','service_provider_of', ...
  target_id     BIGINT REFERENCES entities(entity_id) ON DELETE SET NULL,          -- biliniyorsa doğrudan hedef
  PRIMARY KEY (alias, owner_id)
);

-- =========================================
-- ITEMS (üst kimlik) + tür-spec tablolar
-- =========================================
CREATE TABLE IF NOT EXISTS items (
  item_id       BIGSERIAL PRIMARY KEY,
  source_type   TEXT NOT NULL CHECK (source_type IN ('email','doc','image','voice','note','web')),
  origin_source TEXT,                -- 'gmail:sabirli31','localfs','iphone',...
  origin_id     TEXT,                -- message_id / dosya yolu / uuid
  title         TEXT,
  snippet       TEXT,                -- free text snippet
  content_hash  TEXT,                -- SHA256(subject + cleaned_body) - deduplication için
  created_at    TIMESTAMPTZ DEFAULT now(),
  event_at      TIMESTAMPTZ,         -- gerçek zaman (email sent, EXIF time)
  lang          TEXT,
  thread_id     TEXT,
  people        TEXT[] DEFAULT '{}',
  orgs          TEXT[] DEFAULT '{}',
  domains       TEXT[] DEFAULT '{}',
  city          TEXT,
  country       TEXT,
  -- geo        GEOGRAPHY(Point,4326),  -- PostGIS kullanırsan aç
  tags          JSONB DEFAULT '{}'::jsonb,
  deleted_at    TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_items_thread      ON items(thread_id);
CREATE INDEX IF NOT EXISTS idx_items_event_at    ON items(event_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_type        ON items(source_type);
CREATE INDEX IF NOT EXISTS idx_items_deleted     ON items(deleted_at);
CREATE INDEX IF NOT EXISTS idx_items_active_ev   ON items(event_at DESC) WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_items_content_hash ON items(content_hash);

-- entity_relations.source_item_id → items FK
ALTER TABLE entity_relations
  ADD CONSTRAINT fk_entity_rel_source_item
  FOREIGN KEY (source_item_id) REFERENCES items(item_id) ON DELETE SET NULL;

-- EMAIL alanları
CREATE TABLE IF NOT EXISTS emails (
  item_id        BIGINT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
  message_id     TEXT UNIQUE,
  from_addr      TEXT,
  to_addrs       TEXT[] DEFAULT '{}',
  cc_addrs       TEXT[] DEFAULT '{}',
  sender_domain  TEXT,
  has_attachment BOOLEAN DEFAULT FALSE,
  raw_text       TEXT,                -- Ham plain text içeriği
  raw_html       TEXT,                -- Ham HTML içeriği
  cleaned_body   TEXT,                -- Temizlenmiş gövde metni
  content_hash   TEXT,                -- SHA256(subject + cleaned_body)
  subject        TEXT,                -- Email konusu
  plain_text_top TEXT,               -- İlk düz metin parçası
  plain_text_full TEXT              -- Tam düz metin içeriği
);
CREATE INDEX IF NOT EXISTS idx_emails_domain ON emails(sender_domain);
CREATE INDEX IF NOT EXISTS idx_emails_content_hash ON emails(content_hash);
CREATE INDEX IF NOT EXISTS idx_emails_message_id ON emails(message_id);

-- DOCS
CREATE TABLE IF NOT EXISTS docs (
  item_id        BIGINT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
  mime_type      TEXT,
  file_path      TEXT,
  pages          INT
);

-- IMAGES
CREATE TABLE IF NOT EXISTS images (
  item_id        BIGINT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
  width          INT,
  height         INT,
  ocr_text       TEXT,
  caption_text   TEXT,
  img_embedding  vector(512) -- opsiyonel (CLIP/ViT)
);

-- VOICES
CREATE TABLE IF NOT EXISTS voices (
  item_id        BIGINT PRIMARY KEY REFERENCES items(item_id) ON DELETE CASCADE,
  duration_sec   REAL,
  transcript     TEXT,
  speaker_meta   JSONB DEFAULT '{}'::jsonb
);

-- =========================================
-- CHUNKS (aranabilir metin) + hibrit indeksler
-- =========================================
-- Not: bge-m3 model ile 1024-dim
CREATE TABLE IF NOT EXISTS chunks (
  chunk_id    BIGSERIAL PRIMARY KEY,
  item_id     BIGINT NOT NULL REFERENCES items(item_id) ON DELETE CASCADE,
  ord         INT NOT NULL,            -- 0=subject/title, 1=ilk gövde parçası, ...
  text        TEXT NOT NULL,
  lang        TEXT,
  embedding   vector(1024),
  bm25_tsv    tsvector
);
CREATE INDEX IF NOT EXISTS idx_chunks_item     ON chunks(item_id);
CREATE INDEX IF NOT EXISTS idx_chunks_tsv      ON chunks USING GIN (bm25_tsv);
CREATE INDEX IF NOT EXISTS idx_chunks_vec      ON chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX IF NOT EXISTS idx_chunks_active_tsv ON chunks USING GIN (bm25_tsv);

-- =========================================
-- FACTS (tek-atış gerçekler: VAT/IBAN/tarih/tutar/ad/telefon/adres…)
-- =========================================
CREATE TABLE IF NOT EXISTS facts (
  fact_id        BIGSERIAL PRIMARY KEY,
  subject_entity TEXT NOT NULL,                 -- 'me','Moon Faced Ltd','Davis Tate','place:xyz',...
  predicate      TEXT NOT NULL,                 -- 'VAT_NUMBER','COMPANY_NO','PHONE','ADDRESS','BUSINESS_NAME',...
  object_value   TEXT NOT NULL,
  value_norm     TEXT,
  data_type      TEXT,                          -- 'vat','phone','amount_gbp','date','string',...
  lang           TEXT,
  item_id        BIGINT REFERENCES items(item_id) ON DELETE CASCADE,
  span_start     INT,
  span_end       INT,
  confidence     REAL DEFAULT 1.0,
  created_at     TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_facts_pred    ON facts(predicate);
CREATE INDEX IF NOT EXISTS idx_facts_entity  ON facts(subject_entity);
CREATE INDEX IF NOT EXISTS idx_facts_dtype   ON facts(data_type);

-- =========================================
-- (OPSİYONEL) ROLES (normalize edilmiş meslek/rol sözlüğü)
-- =========================================
CREATE TABLE IF NOT EXISTS roles (
  role_id     BIGSERIAL PRIMARY KEY,
  code        TEXT UNIQUE,                 -- 'glazier','accountant','plumber','painter',...
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE IF NOT EXISTS role_labels (
  role_id     BIGINT REFERENCES roles(role_id) ON DELETE CASCADE,
  lang        TEXT NOT NULL,
  label       TEXT NOT NULL,               -- birincil: 'camcı'
  aliases     TEXT[] DEFAULT '{}',         -- {'camci','cam ustası','glazier'}
  PRIMARY KEY (role_id, lang)
);

-- Hızlı rol oluşturucu (varsa getirir)
CREATE OR REPLACE FUNCTION get_or_create_role(p_lang TEXT, p_label TEXT, p_aliases TEXT[] DEFAULT '{}')
RETURNS BIGINT AS $$
DECLARE v_id BIGINT; v_code TEXT;
BEGIN
  SELECT rl.role_id INTO v_id
  FROM role_labels rl
  WHERE rl.lang = p_lang
    AND (rl.label ILIKE p_label OR p_label = ANY(rl.aliases))
  LIMIT 1;

  IF v_id IS NULL THEN
    v_code := regexp_replace(lower(p_label), '\s+', '_', 'g');
    INSERT INTO roles(code) VALUES (v_code)
    ON CONFLICT (code) DO NOTHING;

    SELECT role_id INTO v_id FROM roles WHERE code = v_code;
    INSERT INTO role_labels(role_id, lang, label, aliases)
    VALUES (v_id, p_lang, p_label, COALESCE(p_aliases,'{}'))
    ON CONFLICT DO NOTHING;
  END IF;

  RETURN v_id;
END$$ LANGUAGE plpgsql;

-- entity_relations.role_id FK (roles)
ALTER TABLE entity_relations
  ADD CONSTRAINT fk_entity_rel_role
  FOREIGN KEY (role_id) REFERENCES roles(role_id) ON DELETE SET NULL;

-- =========================================
-- VIEWS (kolay erişim)
-- =========================================
-- Aranabilir birleşik görünüm
CREATE OR REPLACE VIEW v_search_chunks AS
SELECT
  c.chunk_id, c.item_id, c.ord, c.text, c.lang,
  c.embedding, c.bm25_tsv,
  i.source_type, i.title, i.event_at, i.lang AS item_lang,
  i.people, i.orgs, i.domains, i.thread_id, i.city, i.country, i.deleted_at
FROM chunks c
JOIN items i ON i.item_id = c.item_id
WHERE i.deleted_at IS NULL;

-- E-posta thread’inde en son mesaj
CREATE OR REPLACE VIEW v_latest_email_per_thread AS
SELECT
  thread_id,
  MAX(event_at) AS last_event_at,
  (ARRAY_AGG(item_id ORDER BY event_at DESC))[1] AS last_item_id
FROM items
WHERE source_type = 'email' AND thread_id IS NOT NULL AND deleted_at IS NULL
GROUP BY thread_id;

-- Facts için “en güncel”
CREATE OR REPLACE VIEW v_facts_current AS
SELECT DISTINCT ON (subject_entity, predicate)
  subject_entity, predicate, object_value, value_norm, data_type, lang, item_id, confidence, created_at
FROM facts
ORDER BY subject_entity, predicate, created_at DESC;

-- =========================================
-- (İSTEĞE BAĞLI) ÇEKİRDEK PREDICATE BAĞLANTILARI
-- =========================================
-- Minimum çekirdek örnekleri (tamamen opsiyonel):
-- SELECT link_inverse_predicates('service_provider_of','client_of');
-- SELECT link_inverse_predicates('works_for','employs');
-- SELECT link_inverse_predicates('landlord_of','tenant_of');

-- -- Türkçe/İngilizce örnek etiket (opsiyonel, hızlı başlangıç)
-- SELECT get_or_create_predicate('spouse','tr','eş',ARRAY['karısı','kocası','eşim','karım','kocam'],'symmetric','one_to_one');
-- SELECT get_or_create_predicate('friend','tr','arkadaş',ARRAY['kanka','dost'],'symmetric','many_to_many');
-- SELECT get_or_create_predicate('colleague','tr','iş arkadaşı',ARRAY['workmate','mesai arkadaşı'],'symmetric','many_to_many');