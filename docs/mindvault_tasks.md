# MindVault – Delivery Plan & Task Breakdown
*(Cost-first & performance-first; version 2025-08-26)*

> Goal: Stand up **MindVault**, a multi-source personal “second brain” with Gmail/Hotmail, Google/Apple Calendars, Telegram (text/photo/voice), optional notes/files. Indexed in Postgres+pgvector with S3/B2 for raw files. **Hybrid retrieval** (BM25+vector+tags+history), plus **actions** (email replies, calendar events), and **Obsidian-style Markdown export to GitHub**.

---

## 🧭 Guiding Principles
- **Cheapest sensible stack**: managed Postgres (+pgvector) on a low tier, Backblaze B2/Wasabi for object storage, small LLMs by default; burst to bigger model only when needed.
- **RAG not dump**: never send all data to LLM; retrieve → compress → send **only** the minimum.
- **Incremental ingestion**: poll/webhook, dedupe, re-embed changed items only.
- **Schema-first**: one normalized schema across sources (email/event/chat/file), plus tags, senders, and query-history tables.
- **Observability**: logs + simple metrics from day 1 (cheap!).
- **Privacy**: minimum scopes, KMS/Secrets vault, row-level isolation.

---

## 🗺️ Phases Overview
1. **P0 – Foundation**: repo, env, IaC minimal, cost guardrails  
2. **P1 – Data Layer**: Postgres+pgvector, S3/B2, migrations  
3. **P2 – Ingestion**: Gmail/Hotmail, Calendars, Telegram (text/photo/voice) (+ dedupe)  
4. **P3 – Index**: chunking + embeddings + hybrid search plumbing  
5. **P4 – Retrieval & /search**: hybrid scorer, history & tags boost  
6. **P5 – /ask + LLM**: compression → prompt → summary-with-links  
7. **P6 – Actions**: email reply/draft, calendar create  
8. **P7 – Tags & History UX**: add/remove, feedback logging, bandit tuning  
9. **P8 – GitHub Export (Obsidian)**: Markdown vault + push  
10. **P9 – Ops**: backups, monitoring, costs, SLOs, security hardening

---

## ✅ P0 – Foundation (MindVault Repo)
**Status**
- ✅ Repo + folders (`api/`, `n8n/`, `infra/`, `scripts/`, `ui/`, `docs/`)
- ✅ `docker-compose.dev.yml` (Postgres, FastAPI, etc.)
- ✅ `.env.example` (DB URL, API_KEY, etc.)
- ✅ Makefile (`make dev`, `make migrate`, …)

**Acceptance**
- `make dev` brings stack up; `/health` returns OK.

---

## ✅ P1 – Data Layer (DB & Storage)
**Status**
- ✅ Postgres extensions enabled: `pgvector`, `unaccent`, `pg_trgm`
- ✅ Schema + indexes present:
  - `idx_documents_content_hash` → dedupe
  - `idx_documents_ts_desc` → newest-first reads
  - `uq_document_chunks_doc_ord` → unique per (doc_id, ord)
- ⬜ **S3 bucket config** missing (needed for attachments & telegram media)
- ⬜ API ↔ S3 health check missing

**Acceptance**
- DB works; S3 still **pending**.

---

## ✅ P2 – Ingestion (n8n)
**Status**
- ⚠️ Gmail ingest ran **one-shot**; **no periodic job yet**
- ⬜ Hotmail/Outlook ingest **not implemented**
- ⬜ Calendar ingest **not implemented**
- ⬜ Telegram ingest **not implemented**
- ✅ Dedupe (`content_hash`) active
- ✅ Gmail payload includes `tags` + `content_hash`
- ✅ API-side OpenAI tagging **enabled** (`ENABLE_OAI_TAGS=1`)

---

## ✅ P3 – Indexing
**Status**
- ✅ Chunking + embeddings working (`document_chunks` + `documents.embedding` populated)
- ✅ Very short chunks are skipped
- ✅ Document-level embedding written

---

## ✅ P4 – Retrieval (/search)
**Status**
- ✅ `/search` works; highlights returned
- ⚠️ Tag/date/lang filters tested and work, but `simple_unaccent` text search config was missing → **create config** (see Fixes)
- ⚠️ Hybrid scoring now BM25 + optional vector with **hardcoded weights (0.65 / 0.35)** → move to ENV
- ⬜ Time-decay bump (≤7d) not implemented

---

## ⬜ P5 – /ask (Summarize with Links)
**Status**
- Not implemented.

---

## ⬜ P6 – Actions (Email Reply, Calendar)
**Status**
- Not implemented.

---

## ⬜ P7 – Tags & History
**Status**
- Not implemented.

---

## ⬜ P8 – GitHub Export (Obsidian)
**Status**
- Not implemented.

---

## ⚠️ P9 – Ops
**Gaps**
- ⬜ S3 `.env` not filled
- ⬜ Backup folder missing; create then test dump
  ```bash
  mkdir -p backups
  pg_dump "$DATABASE_URL" -Fc -f backups/mindvault_$(date +%F).dump
  ```
- ⬜ Monitoring/metrics not set
- ⬜ Budget guardrails not set

---

## ENV Checklist
```
DATABASE_URL=...
OPENAI_API_KEY=...
ENABLE_OAI_TAGS=1

# S3 — required for attachments & telegram media
S3_ENDPOINT=...
S3_BUCKET=...
S3_REGION=...
S3_ACCESS_KEY_ID=...
S3_SECRET_ACCESS_KEY=...
```

---

## 🔧 Immediate Fixes & TODOs

### 1) Create `simple_unaccent` FTS config (one-time)
```sql
CREATE EXTENSION IF NOT EXISTS unaccent;

CREATE TEXT SEARCH CONFIGURATION IF NOT EXISTS simple_unaccent ( COPY = simple );
ALTER TEXT SEARCH CONFIGURATION simple_unaccent
  ALTER MAPPING FOR hword, hword_part, word
  WITH unaccent, simple;
```

### 2) Make hybrid weights configurable
- Add ENV:
  ```
  SEARCH_WEIGHT_VECTOR=0.55
  SEARCH_WEIGHT_BM25=0.45
  ```
- Use in `/search` SQL formula instead of hardcoded `0.65/0.35`.

### 3) Wire S3
- Fill `.env`, then add a simple health check endpoint that does a `head_bucket`.

### 4) Cron the Gmail ingest
- n8n: every 10 min → search (in:inbox -category:* -is:spam -is:trash + sent) → POST `/ingest/gmail`
- Keep dedupe; batch by 50–100 items per request.

### 5) Backups
- Daily pg_dump (local cron or provider snapshot). Keep 30 days.

---

## 💸 Cost & Performance TL;DR
- **DB**: small managed Postgres (~$10–$25/mo)
- **Storage**: B2/Wasabi 50–100 GB (~$2.5–$6/mo)
- **LLM**: default small model (few $/mo); cap & fallback to local
- **Ingestion**: poll 5–10 min; batch; embed only new items
- **Search**: cache identical queries (10 min); topK=24 → finalN=8
- **Exports**: delta-only Markdown → GitHub

---

## Demo Script
1) Telegram: “Emlakçı ile sıcak su konusunda son konuştuğumuzu özetle.”  
2) `/ask` logs qlog, runs `/search`, shows 8 links.  
3) LLM returns summary + links; UI shows actions.  
4) Click “Reply Draft” → Gmail draft created via n8n; `/feedback` updates outcome.  
5) Exporter pushes Markdown to GitHub; Obsidian opens vault.