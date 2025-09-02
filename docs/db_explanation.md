
# Overview

This schema is designed so **any content** (email, documents, images, voice transcripts, notes, web clippings) lands in one place, becomes **semantically searchable** (vector + BM25), and is enriched into **entities**, **relations**, and **facts** you can use for precise, “one-shot” answers (e.g., “What’s my VAT number?”) or context-aware tasks (e.g., “Reply to my estate agent Bruce—bring the latest email.”).

Below, each table/function/trigger is explained in English, with **what it stores**, **why it exists**, and **how it’s used in the workflow** (ingestion → enrichment → retrieval → RAG).

---

# Core Knowledge Graph

## `entities`
**What:** Canonical records for people, organizations, and places.  
**Why:** Gives you stable IDs to link emails, docs, and photos to **who/what** they are about.  
**Fields to notice:**
- `type`: `'person' | 'org' | 'place'`
- `name`, `aliases[]`: names and alternative spellings
- `emails[]`, `phones[]`, `domains[]`: contact and domain evidence
- `meta`: free-form JSON (e.g., { "preferred_channel": "email" })

**Workflow:**
- During ingestion, parse headers/footers/NER → upsert entities by email/domain/name.
- Later, queries like “message my wife” or “Davis Tate emails” resolve to entity IDs.

---

## `rel_predicates`, `rel_predicate_labels`, `rel_predicate_alias_map`
**What:** A **generic, self-growing dictionary** of relation types (predicates) and their multilingual labels/aliases.
- `rel_predicates`: canonical predicate codes (e.g., `service_provider_of`, `spouse`).
- `direction`: `symmetric` (friend/colleague) vs `asymmetric` (client_of/works_for).
- `inverse_id`: pointer to reverse predicate (client_of ↔ service_provider_of).
- `rel_predicate_labels`: human labels per language (e.g., TR “emlakçısı”, EN “estate agent”).
- `rel_predicate_alias_map`: raw terms seen in queries mapped to a predicate (e.g., “lettings agent” → `service_provider_of`).

**Why:** Lets the system learn new relation words **without schema changes**; supports TR/EN (and any language) and synonymy.

**Workflow:**
- In ingestion or query-time parsing, if you meet a new term (“camcısı”), call `get_or_create_predicate(...)` to create/find a predicate and seed labels/aliases.
- Use `link_inverse_predicates(a, b)` to wire reverses (once), then the trigger will mirror relations automatically.

---

## `entity_relations`
**What:** The actual **edges** between entities: `(subject) —[predicate]→ (object)` with time and qualifiers.
**Why:** Captures **who is who to whom**, generically. This powers queries like “my estate agent,” “my landlord,” “my colleague,” **and** domain/role nuance.

**Fields to notice:**
- `predicate_id`: FK into `rel_predicates`
- `start_at`, `end_at`: time-bounded relations (e.g., “former landlord”)
- `qualifiers` JSONB: **free attributes** like `{"role":"glazier","city":"Giresun","firm":"Davis Tate"}`
- `role_id` / `role_free`: optional normalized role (from `roles`) or raw label
- `source_item_id`: provenance (which email/doc/image suggested this relation)
- `confidence`: scoring for conflict resolution

**Workflow:**
- Ingestion creates high-confidence relations from headers/domains (“Bruce” employee_of “Davis Tate”), signatures, and patterns (“estate agent”).
- Query-time, phrases like “my accountant” map to `service_provider_of(subject=Me, role≈accountant)`.

---

## `alias_index`
**What:** User-specific **call-phrases** (e.g., “my wife”, “karım”, “emlakçım”) pointing to a target entity or default predicate.
**Why:** Natural language varies per user. You can bind “my wife” → Ayşe, “emlakçım” → predicate `service_provider_of` (target resolved via relations).

**Workflow:**
- When you **confirm** that “karım” means Ayşe, insert `(alias='karım', owner=Me, target=Ayşe)`.
- At query-time, resolve alias → target immediately, or fall back to predicate+relation search.

---

# Content Layer

## `items`
**What:** The **root record** for anything ingested: email, doc, image, voice, note, web.
**Why:** Every piece of content has a single ID you can attach chunks, facts, and relations to.

**Fields to notice:**
- `source_type`: `'email'|'doc'|'image'|'voice'|'note'|'web'`
- `origin_source` / `origin_id`: where it came from (gmail account, path, etc.)
- `event_at`: the **real** occurrence time (email sent time, EXIF time)
- `people[]`, `orgs[]`, `domains[]`: quick filters from NER/headers
- `thread_id`: email conversation grouping
- `deleted_at`: soft deletion (to track GDPR and cleanup)

**Workflow:**
- Create one `items` row per ingested asset.
- Use `event_at` for recency boosts and “latest email” logic.
- Soft-delete when the source is deleted; GC later.

---

## `emails`, `docs`, `images`, `voices`
**What:** Type-specific metadata for the corresponding `items` rows.
- `emails`: `message_id`, `from`, `to[]`, `cc[]`, `sender_domain`, `has_attachment`
- `docs`: `mime_type`, `file_path`, `pages`
- `images`: `width`, `height`, `ocr_text`, `caption_text`, `img_embedding` (for visual similarity)
- `voices`: `duration_sec`, `transcript`, `speaker_meta`

**Why:** Preserve structured details you’ll use in filters, relation inference, and facts extraction.

**Workflow examples:**
- **Email:** derive domain → org; write relations (employee_of, service_provider_of), build chunks.
- **Image:** OCR + caption → `ocr_text`/`caption_text`, optionally `img_embedding`; add place/role facts (“BUSINESS_NAME”).
- **Voice:** store transcript; classify **command vs info**; info becomes chunks/facts, commands route to your to-do system.

---

## `chunks`
**What:** The **searchable text** (split into small pieces) with **vector** and **BM25** columns.
**Why:** Powers **hybrid semantic + keyword** retrieval.

**Fields to notice:**
- `ord`: ordering; put `subject/title` as `ord=0` to weight it higher at ranking time
- `embedding vector(384)`: multilingual sentence embedding (e.g., e5-small)
- `bm25_tsv`: `tsvector` for BM25 keyword search

**Workflow:**
- For each item: clean → split (subject/title, first 1K body chars, then 512–1K chunks) → embed → build BM25.
- Hybrid retrieval: top-N by vector + top-M by BM25 → union → rescore → (optionally) cross-encode re-rank.

---

## `facts`
**What:** **Atomic, structured facts** (subject/predicate/value) extracted from text/images/emails.
**Why:** Instant answers to narrow questions: **VAT number**, **company number**, **rent amount**, **tenancy dates**, **phone**, **address**, **business name**, **invoice number/amount**, etc.

**Fields to notice:**
- `subject_entity`: who/what this fact is about (e.g., “me”, “Moon Faced Ltd”, “Davis Tate”, `place:xyz`)
- `predicate`: e.g., `'VAT_NUMBER'`, `'BUSINESS_NAME'`, `'PHONE'`
- `value_norm`: normalized canonical value (e.g., `GB123456789`)
- `item_id` + `span_start/end`: provenance and exact snippet location
- `confidence`: scoring

**Workflow:**
1. Regex + NER capture candidate values.
2. Contextual cues around matches (“VAT”, “Invoice”, currency symbols).
3. Normalize (dates, currency, VAT, IBAN) → write `facts`.
4. Prefer “facts-first” for exact-lookup queries; if missing, fallback to hybrid text search + on-the-fly regex.

---

## (Optional) `roles`, `role_labels`
**What:** A normalization dictionary for **professions/roles** (glazier/plumber/accountant).
**Why:** If you want strong typing beyond free `qualifiers.role` in relations.

**Workflow:**
- When ingestion detects a new role word, call `get_or_create_role('tr','camcı', ['camci','cam ustası','glazier'])` and attach `role_id` on the relation.

---

# Helper Functions & Triggers

## `get_or_create_predicate(...)`
**What:** Idempotent creation of a predicate, its labels, and alias mappings (multilingual).  
**Why:** Allows the system to **learn new relation terms** from data/queries, no schema change.

**Workflow:**
- On encountering a new term (“advisor,” “camcısı”), call this with `p_label`/`p_aliases` and language.
- It updates `rel_predicates`, `rel_predicate_labels`, and `rel_predicate_alias_map`.

---

## `link_inverse_predicates(a, b)`
**What:** Wires **inverse** directions (A ↔ B) so insertion of one auto-creates the reverse edge.

**Workflow:** Call once per pair (e.g., `service_provider_of` ↔ `client_of`).

---

## `trg_entity_relations_inverse`
**What:** Trigger that **auto-inserts the reverse edge** based on predicate direction/inverse.  
**Why:** Keeps the graph consistent with no extra application code.

**Workflow:**
- When you insert `(Me) —[service_provider_of]→ (Bruce)`, it auto-inserts `(Bruce) —[client_of]→ (Me)`.

---

## `trg_entities_touch`
**What:** Maintains `updated_at` on `entities`.  
**Why:** Bookkeeping for sync and confidence updates.

---

# Views for Common Use-Cases

## `v_search_chunks`
**What:** Joins `chunks` with `items` (filters out deleted).  
**Why:** A single view to feed your hybrid search (vector + BM25) with metadata filters (type, dates, domains, thread).

---

## `v_latest_email_per_thread`
**What:** For each `thread_id`, gives `last_item_id` and `last_event_at`.  
**Why:** “Bring the latest email in this conversation” is a one-liner.

---

## `v_facts_current`
**What:** Deduplicated **latest** fact per `(subject_entity, predicate)` pair.  
**Why:** “What’s my current VAT number?”—no scanning needed.

---

# End-to-End Workflow

## 1) Ingestion

### Email
1. **Parse headers** (`From`, `To`, `Cc`, `Date`, `Message-ID`, `Thread-ID`):  
   - Upsert `entities` for each person (name/email) and org (by domain → org mapping).
   - Create `items(source_type='email', event_at=Date, thread_id=...)` + `emails`.
2. **Clean body** (strip quotes/signatures), **detect language**.
3. **Chunk** subject/body; write `chunks` with **embeddings** and **bm25_tsv**.
4. **NER & regex**: extract phone, address, VAT, invoice no, amounts → write `facts`.
5. **Relations**:  
   - `employee_of` by domain/signature;  
   - `service_provider_of(Me→org/person)` by keywords (“estate agent”, “lettings”, “property manager”), mail frequency, labels;  
   - attach `qualifiers` (e.g., `{ "firm":"Davis Tate" }`) and `source_item_id`.
6. **Deletion sync**: if email deleted at source → set `items.deleted_at` (soft), later GC.

### Document (PDF/DOCX)
1. Extract text (OCR if needed) → create `items('doc')` + `docs`.
2. Chunk + embed + bm25.
3. Facts: VAT, company no., tenancy dates, invoice amounts.
4. Relations: detect named persons/orgs, lexicon matches (“contractor”, “landlord”), add edges.

### Image
1. Read EXIF → `event_at`, (geo if you enable PostGIS), `city/country`.
2. OCR (signs/menus) + caption → `images.ocr_text`, `images.caption_text` (+ optional `img_embedding`).
3. Facts (e.g., `BUSINESS_NAME`, `PHONE`, `ADDRESS`) extracted from OCR.
4. Relations (optional): tie place to org/person; qualifiers with `{ "role":"pideci" }`.

### Voice
1. Transcribe (multilingual).  
2. Classify **command vs info**: commands go to your task system (not indexed), info becomes `items('voice')`.
3. Chunk + embed + bm25; facts/relations same as docs/emails.

---

## 2) Retrieval & Orchestration

### Intent routing
- **FACT_LOOKUP** (e.g., “What’s my VAT number?”):  
  1) Hit `v_facts_current` (fast path).  
  2) If missing, hybrid search → regex on-the-fly → propose candidates with provenance.
- **PERSON/ORG-CENTRIC** (e.g., “Reply to Bruce; bring the latest email. Include whole firm Davis Tate.”):  
  - Resolve **alias** (“my wife”, “emlakçım”) or match predicate+relation to get target **entity_id(s)**.  
  - Filter by `emails.sender_domain`/`items.domains` and `entities`.  
  - Hybrid search to collect candidates; group by `thread_id`; take `v_latest_email_per_thread.last_item_id`.
- **GENERAL SEARCH** (e.g., “all conversations with estate agent”):  
  - Use hybrid search with predicate/org filters + recency boost.  
  - Diversify across threads (MMR) if needed.

### Ranking signals
- Vector similarity + BM25 + **recency boost** + domain/org match + role/predicate match.
- Prioritize `ord=0` (subject/title) hits.

### RAG packaging
- **Primary**: the **latest** email body top segment (quotes stripped).  
- **Supporting**: 3–5 previous messages in thread (ordered), + any **facts** (VAT, address) needed to answer.  
- **System prompt**: style/formatting constraints (UK English, concise, cite sources by `item_id`).

---

## 3) Maintenance

- **Re-embedding**: when you upgrade models, re-embed incrementally (only new/changed items). If needed, schedule a full re-embed off-hours.  
- **Conflict resolution**: for facts/relations, prefer the latest or highest-confidence; keep provenance.  
- **Soft delete & GC**: regularly hard-delete rows with `deleted_at IS NOT NULL`.  
- **Learning new terms**: unseen relationship words are auto-added through `get_or_create_predicate`; same for roles via `get_or_create_role`.

---

# Example Scenarios (How the Schema Answers)

### “Bring all conversations with my estate agent and show the latest email from Bruce.”
- Resolve **“my estate agent”** via:
  - `alias_index(owner=Me, alias in ['emlakçım','my agent'])` → direct target, or
  - `entity_relations(subject=Me, predicate=service_provider_of, qualifiers.role ~ 'estate agent')` → set of agents (Bruce + Davis Tate).
- Filter `items/emails` by `sender_domain='davistate.co.uk'` and/or `people[] ~ 'Bruce'`.  
- Use `v_latest_email_per_thread` to pick the latest per thread.

### “What was my VAT number?”
- Query `v_facts_current` where `subject_entity in ('me','my_company',...) and predicate='VAT_NUMBER'`.  
- If not found, hybrid search for VAT patterns → normalize → store in `facts` for next time.

### “What was the name of the pide place in Giresun?”
- First try `facts` where `predicate='BUSINESS_NAME' AND city='Giresun' AND (qualifiers.role ~ 'pide')`.  
- If missing, hybrid-search on images/docs OCR chunks with geo filter (if PostGIS) and extract the name; store as fact.

---

# Design Principles Recap

- **Single root (`items`)** for all sources → simple lineage & deletes.  
- **Hybrid search (`chunks`)** = **semantic + keyword** → best recall & precision.  
- **Knowledge graph** (`entities` + **generic** `entity_relations`) → robust, language-agnostic reference resolution.  
- **Self-growing dictionaries** (`rel_predicates`, `role_labels`) via helper functions → **no schema changes** as vocabulary expands.  
- **Facts table** → instant answers for structured queries.  
- **Triggers** keep relations consistent (inverse edges).  
- **Soft delete** respects source-of-truth deletions and privacy.

This documentation is intentionally detailed so an AI (and your future self) can operate and extend the system confidently without schema churn.
