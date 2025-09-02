# api/routers/ingest.py
from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime
import os
import time
import math
import hashlib
import json
import psycopg2
from psycopg2.extras import Json

# ---- Optional langdetect (graceful fallback) ----
try:
    from langdetect import detect as _ld_detect  # pip install langdetect
except Exception:
    _ld_detect = None

# ---- OpenAI client ----
try:
    from openai import OpenAI
    from openai import RateLimitError
except Exception as _e:
    OpenAI = None
    RateLimitError = Exception  # fallback type

router = APIRouter(prefix="/ingest", tags=["ingest"])

PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")
OAI_KEY = os.getenv("OPENAI_API_KEY", "")
EMBED_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")  # 1536 dims
EMBED_DIM = int(os.getenv("EMBED_DIM", "1536"))

# Toggle: generate tags with OpenAI
ENABLE_OAI_TAGS = os.getenv("ENABLE_OAI_TAGS", "1") == "1"
TAG_MODEL = os.getenv("TAG_MODEL", "gpt-4o-mini")  # compact & cheap
# Max chars to send for tagging to keep cost very low
TAG_TEXT_BUDGET = int(os.getenv("TAG_TEXT_BUDGET", "4000"))

# Chunking
CHUNK_TARGET = int(os.getenv("CHUNK_TARGET_CHARS", "1200")
                   )   # target chunk size (chars)
CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP_CHARS", "150"))  # overlap (chars)
# if chunk < this, merge with next/prev
CHUNK_MIN_JOIN = int(os.getenv("CHUNK_MIN_JOIN_CHARS", "120"))
# final too-short chunks dropped
CHUNK_MIN_KEEP = int(os.getenv("CHUNK_MIN_KEEP_CHARS", "20"))

# Embedding batching / retry
# how many chunks per embed call
EMBED_BATCH = int(os.getenv("EMBED_BATCH", "64"))
RETRY_MAX = int(os.getenv("RETRY_MAX", "4"))
RETRY_BASE_SLEEP = float(os.getenv("RETRY_BASE_SLEEP", "1.0"))

# ------------------ DB utils ------------------


def _connect():
    return psycopg2.connect(PG_DSN)


def _upsert_source(cur, provider: str, account_id: str) -> str:
    """Upsert source; requires UNIQUE(provider, account_id)."""
    cur.execute(
        """
        INSERT INTO sources(id, provider, account_id)
        VALUES (gen_random_uuid(), %(provider)s, %(account_id)s)
        ON CONFLICT (provider, account_id)
        DO UPDATE SET account_id = EXCLUDED.account_id
        RETURNING id
        """,
        {"provider": provider, "account_id": account_id},
    )
    return cur.fetchone()[0]


def _ensure_tag(cur, name: str) -> Optional[int]:
    """Create tag if not exists (case-insensitive)."""
    if not name:
        return None
    cur.execute("INSERT INTO tags(name) VALUES (%(name)s) ON CONFLICT DO NOTHING", {
                "name": name})
    cur.execute(
        "SELECT id FROM tags WHERE lower(name) = lower(%(name)s)", {"name": name})
    row = cur.fetchone()
    return row[0] if row else None


def _attach_tag(cur, document_id: str, tag_id: int):
    """Attach tag to document (dedup)."""
    cur.execute(
        """
        INSERT INTO document_tags(document_id, tag_id)
        VALUES (%(doc_id)s, %(tag_id)s)
        ON CONFLICT ON CONSTRAINT uq_document_tags DO NOTHING
        """,
        {"doc_id": document_id, "tag_id": tag_id},
    )

# ------------------ Models ------------------


class GmailIngest(BaseModel):
    account_id: str = Field(..., description="Gmail account id (owner/email)")
    external_id: str = Field(..., description="Gmail message id")
    subject: Optional[str] = None
    snippet: Optional[str] = None
    plain_text: str
    ts: datetime
    tags: Optional[List[str]] = None
    source_url: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    content_hash: Optional[str] = None

# ------------------ Helpers ------------------


def _compute_hash(subject: str, plain_text: str, account_id: str, external_id: str) -> str:
    """
    Stable content hash for dedupe. We include subject + text + account + external id,
    but you can remove external_id if you want cross-thread dedupe.
    """
    h = hashlib.sha256()
    for part in (subject or "", plain_text or "", account_id or "", external_id or ""):
        h.update(part.encode("utf-8", errors="ignore"))
        h.update(b"\x1e")  # unit separator
    return h.hexdigest()


def _normalize_tags(tags: List[str]) -> List[str]:
    """Lowercase + trim + deduplicate; ignore empties."""
    out = []
    seen = set()
    for t in tags or []:
        tt = (t or "").strip().lower()
        if not tt:
            continue
        if tt not in seen:
            seen.add(tt)
            out.append(tt)
    return out


def _detect_lang(text: str) -> Optional[str]:
    """Return ISO code like 'en','tr'… if langdetect available."""
    if not text:
        return None
    if _ld_detect is None:
        return None
    try:
        return _ld_detect(text[:4000])  # small sample is fine
    except Exception:
        return None


def _chunk_text(s: str) -> List[str]:
    """
    Char-based chunking with overlap and short-fragment merge.
    1) slide window with overlap
    2) merge very short chunks with neighbors
    3) drop ultra-short residuals
    """
    s = (s or "").strip()
    if not s:
        return []

    chunks = []
    n = len(s)
    i = 0
    while i < n:
        j = min(n, i + CHUNK_TARGET)
        chunk = s[i:j].strip()
        if chunk:
            chunks.append(chunk)
        if j >= n:
            break
        i = j - CHUNK_OVERLAP  # overlap

    # Merge too-short chunks forward
    merged = []
    buf = ""
    for c in chunks:
        if len(c) < CHUNK_MIN_JOIN:
            buf = (buf + "\n" + c).strip() if buf else c
            # do not flush yet
        else:
            if buf:
                # merge buffer with current if buffer still small
                candidate = (buf + "\n" + c).strip()
                if len(buf) < CHUNK_MIN_JOIN:
                    merged.append(candidate)
                    buf = ""
                else:
                    merged.append(buf)
                    merged.append(c)
                    buf = ""
            else:
                merged.append(c)
    if buf:
        merged.append(buf)

    # Drop ultra-short
    final = [c for c in merged if len(c) >= CHUNK_MIN_KEEP]
    return final


def _oai_client() -> OpenAI:
    if not OAI_KEY or OpenAI is None:
        raise HTTPException(status_code=500, detail="openai_not_configured")
    return OpenAI(api_key=OAI_KEY)


def _embed_with_retry(client: OpenAI, inputs: List[str]) -> List[List[float]]:
    """Batch embed with retry/backoff for 429/5xx."""
    out: List[List[float]] = []
    for k in range(0, len(inputs), EMBED_BATCH):
        batch = inputs[k: k + EMBED_BATCH]
        attempt = 0
        while True:
            try:
                resp = client.embeddings.create(model=EMBED_MODEL, input=batch)
                out.extend([d.embedding for d in resp.data])
                break
            except RateLimitError:
                if attempt >= RETRY_MAX:
                    raise
                time.sleep(RETRY_BASE_SLEEP * (2 ** attempt))
                attempt += 1
            except Exception as e:
                # Retry on probable transient errors
                msg = str(e).lower()
                if any(x in msg for x in ("timeout", "503", "bad gateway", "temporarily")) and attempt < RETRY_MAX:
                    time.sleep(RETRY_BASE_SLEEP * (2 ** attempt))
                    attempt += 1
                    continue
                raise
    return out


def _avg_vectors(vecs: List[List[float]]) -> List[float]:
    """Simple arithmetic mean of vectors."""
    if not vecs:
        return []
    dim = len(vecs[0])
    acc = [0.0] * dim
    for v in vecs:
        for i in range(dim):
            acc[i] += v[i]
    n = float(len(vecs))
    return [x / n for x in acc]


def _oai_tags(client: OpenAI, subject: str, text: str) -> List[str]:
    """
    Generate up to ~5 concise tags in lowercase.
    Very small prompt, truncated text to keep cost minimal.
    """
    if not ENABLE_OAI_TAGS:
        return []
    # Trim text to budget
    content = (subject or "") + "\n\n" + (text or "")
    if len(content) > TAG_TEXT_BUDGET:
        content = content[:TAG_TEXT_BUDGET]

    prompt = (
        "You are a labeling assistant. Read the email subject+body below and propose 2-5 short topical tags. "
        "Return ONLY a JSON array of lowercase strings (no explanations). "
        "Prefer generic topics like 'billing', 'recruitment', 'meeting', 'github', 'support', 'travel', 'legal', 'security', 'education', 'health', 'housing'. "
        "Avoid personal names and email providers as tags unless central to topic."
    )

    attempt = 0
    while True:
        try:
            resp = client.chat.completions.create(
                model=TAG_MODEL,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": content},
                ],
                temperature=0.2,
                max_tokens=80,
                # helps structured output
                response_format={"type": "json_object"}
            )
            # Try to parse JSON – accept both {"tags":[...]} or raw array
            txt = resp.choices[0].message.content.strip()
            tags: List[str] = []
            try:
                parsed = json.loads(txt)
                if isinstance(parsed, list):
                    tags = parsed
                elif isinstance(parsed, dict):
                    # expect {"tags":[...]} or any single array value
                    if "tags" in parsed and isinstance(parsed["tags"], list):
                        tags = parsed["tags"]
                    else:
                        # get first array found
                        for v in parsed.values():
                            if isinstance(v, list):
                                tags = v
                                break
            except Exception:
                # fallback: try to recover array-looking content
                m = txt.strip()
                if m.startswith("[") and m.endswith("]"):
                    tags = json.loads(m)

            # Normalize & clip
            tags = _normalize_tags(tags)[:5]
            return tags
        except RateLimitError:
            if attempt >= RETRY_MAX:
                return []
            time.sleep(RETRY_BASE_SLEEP * (2 ** attempt))
            attempt += 1
        except Exception:
            # Don't fail the ingest because of tagging
            return []

# ------------------ Exists probe ------------------


@router.head("/gmail/exists")
def gmail_exists(
    hash: str,
    account_id: Optional[str] = None,
    global_search: bool = False,
):
    """HEAD 200 if a document with this content_hash exists (scope by source unless global_search=true)."""
    if not hash:
        raise HTTPException(status_code=400, detail="missing hash")
    try:
        with _connect() as conn, conn.cursor() as cur:
            if global_search:
                cur.execute(
                    "SELECT 1 FROM documents WHERE content_hash=%s LIMIT 1", (hash,))
            else:
                if not account_id:
                    raise HTTPException(
                        status_code=400, detail="missing account_id for non-global search")
                cur.execute(
                    "SELECT id FROM sources WHERE provider='gmail' AND account_id=%s",
                    (account_id,),
                )
                s = cur.fetchone()
                if not s:
                    return Response(status_code=404)
                source_id = s[0]
                cur.execute(
                    "SELECT 1 FROM documents WHERE source_id=%s AND content_hash=%s LIMIT 1",
                    (source_id, hash),
                )
            return Response(status_code=200 if cur.fetchone() else 404)
    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500, detail=f"db_error: {e.pgerror or str(e)}")

# ------------------ Main ingest ------------------


@router.post("/gmail")
def ingest_gmail(doc: GmailIngest):
    """Idempotent Gmail ingest with tags + chunk + embedding."""
    if not OAI_KEY or OpenAI is None:
        raise HTTPException(status_code=500, detail="openai_not_configured")

    if not doc.plain_text or doc.plain_text.strip() == "":
        raise HTTPException(status_code=400, detail="empty_plain_text")

    # Compute hash if absent
    content_hash = doc.content_hash or _compute_hash(
        doc.subject or "", doc.plain_text, doc.account_id, doc.external_id)

    # Build combined tags (client + labelIds)
    incoming_tags = list(doc.tags or [])
    label_ids = []
    if doc.metadata and isinstance(doc.metadata, dict):
        lid = doc.metadata.get("labelIds")
        if isinstance(lid, list):
            label_ids = [str(x).lower() for x in lid]
            incoming_tags.extend(label_ids)
    tags = _normalize_tags(incoming_tags)

    # Lang detect (best effort)
    lang_code = _detect_lang(doc.plain_text)
    # enrich metadata
    metadata = dict(doc.metadata or {})
    if lang_code:
        metadata["lang"] = lang_code

    try:
        with _connect() as conn:
            with conn.cursor() as cur:
                # 1) Source
                source_id = _upsert_source(
                    cur, provider="gmail", account_id=doc.account_id)

                # 1.5) Early dedupe via content_hash within same source
                cur.execute(
                    """
                    SELECT id FROM documents
                    WHERE source_id=%(sid)s AND content_hash=%(h)s
                    LIMIT 1
                    """,
                    {"sid": source_id, "h": content_hash},
                )
                r = cur.fetchone()
                if r:
                    # Already have this exact content
                    existing_id = str(r[0])
                    conn.commit()
                    return {"ok": True, "document_id": existing_id, "dedup": True, "n_chunks": 0}

                # 2) Upsert document by (source_id, external_id)
                cur.execute(
                    """
                    INSERT INTO documents(
                        id, source_id, kind, external_id,
                        title, preview, plain_text, ts, source_url, metadata, content_hash
                    )
                    VALUES (
                        gen_random_uuid(), %(source_id)s, 'email', %(external_id)s,
                        %(title)s, %(preview)s, %(plain_text)s, %(ts)s, %(source_url)s, %(metadata)s, %(content_hash)s
                    )
                    ON CONFLICT (source_id, external_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        preview = EXCLUDED.preview,
                        plain_text = EXCLUDED.plain_text,
                        ts = EXCLUDED.ts,
                        source_url = EXCLUDED.source_url,
                        metadata = EXCLUDED.metadata,
                        content_hash = EXCLUDED.content_hash
                    RETURNING id
                    """,
                    {
                        "source_id": source_id,
                        "external_id": doc.external_id,
                        "title": doc.subject,
                        "preview": doc.snippet,
                        "plain_text": doc.plain_text,
                        "ts": doc.ts,
                        "source_url": doc.source_url,
                        "metadata": Json(metadata),
                        "content_hash": content_hash,
                    },
                )
                document_id = str(cur.fetchone()[0])

                # 3) Merge in OpenAI-generated tags (optional)
                oai = _oai_client()
                extra_tags = _oai_tags(
                    oai, doc.subject or "", doc.plain_text) if ENABLE_OAI_TAGS else []
                if extra_tags:
                    tags = _normalize_tags(tags + extra_tags)

                # 4) Attach tags
                for name in tags:
                    tag_id = _ensure_tag(cur, name)
                    if tag_id:
                        _attach_tag(cur, document_id, tag_id)

                # 5) Chunking
                chunks = _chunk_text(doc.plain_text)

                # 6) Embedding for chunks (batched) + average for document
                embeddings: List[List[float]] = []
                if chunks:
                    embeddings = _embed_with_retry(oai, chunks)
                    if not embeddings or len(embeddings) != len(chunks):
                        raise HTTPException(
                            status_code=502, detail="embedding_error")

                    # clean old chunks (if update path)
                    cur.execute(
                        "DELETE FROM document_chunks WHERE document_id=%s", (document_id,))

                    # insert chunks
                    rows = []
                    for idx, (txt, vec) in enumerate(zip(chunks, embeddings)):
                        rows.append((document_id, idx, txt, vec))

                    psycopg2.extras.execute_batch(
                        cur,
                        "INSERT INTO document_chunks(document_id, ord, text, embedding) VALUES (%s, %s, %s, %s)",
                        rows,
                        page_size=100,
                    )

                    # doc-level vector = mean of chunk vectors
                    mean_vec = _avg_vectors(embeddings)
                    cur.execute(
                        "UPDATE documents SET embedding=%s WHERE id=%s",
                        (mean_vec, document_id),
                    )
                else:
                    # if no chunks, still attempt embedding on (subject + preview or small body)
                    seed_text = (doc.subject or "").strip()
                    if not seed_text:
                        seed_text = (
                            doc.snippet or doc.plain_text[:300]).strip()
                    if seed_text:
                        doc_vec = _embed_with_retry(oai, [seed_text])[0]
                        cur.execute(
                            "UPDATE documents SET embedding=%s WHERE id=%s", (doc_vec, document_id))

                conn.commit()

        return {
            "ok": True,
            "document_id": document_id,
            "dedup": False,
            "n_chunks": len(chunks),
            "tags": tags,
            "lang": lang_code or None,
        }

    except psycopg2.Error as e:
        raise HTTPException(
            status_code=500, detail=f"db_error: {e.pgerror or str(e)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
