# api/agents/search_find.py
"""
General hybrid search agent using keywords, tag boost, decay, and filters.
Based on the existing /search endpoint functionality.
"""
from typing import Dict, Any, List, Optional
import psycopg2
import os
import math

# Database connection using existing pattern
PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")

# OpenAI for embeddings (same as search.py)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=OPENAI_API_KEY)
        EMB_MODEL = "text-embedding-3-small"
    except Exception:
        oai = None
else:
    oai = None


def _connect():
    """Connect to PostgreSQL database using existing pattern."""
    return psycopg2.connect(PG_DSN)


def _qvec(text: str):
    """Generate query vector for semantic search (same as search.py)."""
    if not oai:
        return None
    try:
        resp = oai.embeddings.create(model=EMB_MODEL, input=[text])
        return resp.data[0].embedding
    except Exception:
        return None


def _auto_lang_from_query(q: str) -> str:
    """Auto-detect language from query (same as search.py)."""
    tr_chars = set("ıİğĞşŞöÖçÇüÜ")
    return "turkish_unaccent" if any(ch in tr_chars for ch in q) else "simple_unaccent"


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    General hybrid search with keywords, tag boost, decay, and filters.
    
    Args:
        params: Dictionary with optional keys:
            - keywords: List[str] - Search keywords/query terms
            - query: str - Single query string (alternative to keywords)
            - limit: int - Max number of results (default 10, capped at 200)
            - offset: int - Pagination offset (default 0)
            - tags: List[str] - Hard filter tags (AND ANY)
            - boost_tags: List[str] - Soft boost tags (no filter, just scoring boost)
            - date_from: str - ISO datetime filter for start date
            - date_to: str - ISO datetime filter for end date
            - language: str - Language for text search config ("tr" or "en")
            - decay_days: int - Time decay window in days (default 7, 1-30)
            - highlight: bool - Enable highlighting in results (default False)
    
    Returns:
        Dictionary with:
            - items: List of search hits with id, title, preview, ts, provider, url, score, snippet
            - total: Total number of matching documents
            - has_more: Boolean indicating if there are more results
            - next_offset: Next offset for pagination (if has_more)
    """
    # Extract and normalize parameters
    keywords = params.get("keywords", [])
    query = params.get("query", "").strip()
    
    # Build query string from keywords or use provided query
    if keywords and isinstance(keywords, list):
        q = " ".join(str(kw).strip() for kw in keywords if str(kw).strip())
    elif query:
        q = query
    else:
        return {"items": [], "total": 0, "has_more": False, "next_offset": None}
    
    if not q:
        return {"items": [], "total": 0, "has_more": False, "next_offset": None}
    
    # Normalize parameters
    limit = min(200, max(1, params.get("limit", 10)))  # Default 10, cap at 200
    offset = max(0, params.get("offset", 0))
    tags = [str(t).lower() for t in (params.get("tags") or []) if str(t).strip()]
    boost_tags = [str(t).lower() for t in (params.get("boost_tags") or []) if str(t).strip()]
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    language = params.get("language", "en")
    decay_days = max(1, min(30, params.get("decay_days", 7)))
    highlight = bool(params.get("highlight", False))
    
    # Auto-detect language if not provided
    lang_cfg = language
    if language == "auto" or not language:
        lang_cfg = _auto_lang_from_query(q)
    elif language == "tr":
        lang_cfg = "turkish_unaccent"
    elif language == "en":
        lang_cfg = "simple_unaccent"
    else:
        lang_cfg = "simple_unaccent"
    
    # Build WHERE conditions
    where = ["1=1"]
    query_params: Dict[str, Any] = {
        "qtext": q,
        "cfg": lang_cfg,
        "top_k": limit,
        "offset": offset,
        "decay_days": decay_days,
    }
    
    # Date filters
    if date_from:
        where.append("d.ts >= %(date_from)s")
        query_params["date_from"] = date_from
    if date_to:
        where.append("d.ts <= %(date_to)s")
        query_params["date_to"] = date_to
    
    # Tag join for hard filters
    tag_join = ""
    if tags:
        tag_join = """
          JOIN document_tags dt ON dt.document_id = d.id
          JOIN tags t ON t.id = dt.tag_id AND lower(t.name) = ANY(%(tags)s)
        """
        query_params["tags"] = tags
    
    # Soft-boost tags
    if boost_tags:
        query_params["boost_tags"] = boost_tags
    else:
        query_params["boost_tags"] = None
    
    # Vector search
    qvec = _qvec(q)
    vec_select = "0.0 AS vec_score"
    vec_order = "0.0"
    if qvec is not None:
        query_params["qvec"] = qvec
        vec_select = """
          CASE
            WHEN d.embedding IS NULL THEN 0.0
            ELSE (1.0 - (d.embedding <=> %(qvec)s::vector))
          END AS vec_score
        """
        vec_order = "vec_score"
    
    # Highlighting setup
    headline_opts = "StartSel='<mark>', StopSel='</mark>', MaxFragments=2, MinWords=3, MaxWords=20, ShortWord=2, HighlightAll=TRUE"
    query_params["headline_opts"] = headline_opts
    query_params["highlight"] = highlight
    
    # Hybrid search SQL (based on search.py)
    sql = f"""
    WITH scored AS (
      SELECT
        d.id::text,
        d.title,
        d.preview,
        d.ts,
        s.provider,
        d.source_url,
        d.plain_text,

        -- Full-text fields
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.title,'')), 'A') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.preview,'')), 'B') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.plain_text,'')), 'C') AS doc_fts,

        -- Query
        websearch_to_tsquery(%(cfg)s::regconfig, %(qtext)s) AS q_fts,

        -- Vector
        {vec_select},

        -- Time-decay: linear [0..1] over last N days
        GREATEST(
          0.0,
          1.0 - (EXTRACT(EPOCH FROM (now() - d.ts)) / (60*60*24*%(decay_days)s))
        ) AS decay_score,

        -- Tag boost: boost_tags matched gives 1.0, else 0
        CASE
          WHEN %(boost_tags)s IS NULL THEN 0.0
          WHEN EXISTS (
            SELECT 1
            FROM document_tags bdt
            JOIN tags bt ON bt.id = bdt.tag_id
            WHERE bdt.document_id = d.id
              AND lower(bt.name) = ANY(%(boost_tags)s)
          ) THEN 1.0
          ELSE 0.0
        END AS tag_score

      FROM documents d
      JOIN sources s ON s.id = d.source_id
      {tag_join}
      WHERE {' AND '.join(where)}
    ),
    ranked AS (
      SELECT
        id, title, preview, ts, provider, source_url, plain_text,
        ts_rank_cd(doc_fts, q_fts, 32) AS bm25_score,
        {vec_order}::float AS vec_score,
        tag_score,
        decay_score,
        q_fts,

        -- Final score (weighted combination)
        (0.55 * ts_rank_cd(doc_fts, q_fts, 32)
       + 0.35 * {vec_order}
       + 0.07 * tag_score
       + 0.03 * decay_score) AS final_score
      FROM scored
      WHERE q_fts @@ doc_fts
         OR {vec_order} > 0.0
    ),
    dedup AS (
      SELECT
        *,
        ROW_NUMBER() OVER (
          PARTITION BY COALESCE(title,''), COALESCE(preview,'')
          ORDER BY final_score DESC, ts DESC, length(COALESCE(plain_text,'')) ASC
        ) AS rn
      FROM ranked
    ),
    ordered AS (
      SELECT
        id, title, preview, ts, provider, source_url, plain_text,
        final_score, q_fts,
        COUNT(*) OVER () AS total_rows
      FROM dedup
      WHERE rn = 1
      ORDER BY final_score DESC, ts DESC, length(COALESCE(plain_text,'')) ASC
    )
    SELECT
      id, title, preview, ts, provider, source_url, final_score, total_rows,
      CASE
        WHEN %(highlight)s THEN
          NULLIF(
            ts_headline(
              %(cfg)s::regconfig,
              COALESCE(title,'') || ' ' || COALESCE(preview,'') || ' ' || COALESCE(plain_text,''),
              q_fts,
              %(headline_opts)s
            ),
            ''
          )
        ELSE NULL
      END AS hl
    FROM ordered
    LIMIT %(top_k)s OFFSET %(offset)s;
    """
    
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, query_params)
            rows = cur.fetchall()
            
            items = []
            total = 0
            for row in rows:
                _id, _title, _preview, _ts, _prov, _src, _score, _total, _hl = row
                total = _total or total
                if _score is None or not math.isfinite(float(_score)):
                    _score = 0.0
                snippet = _hl if (highlight and _hl) else (_preview or None)
                
                items.append({
                    "id": _id,
                    "title": _title,
                    "preview": _preview,
                    "ts": (_ts.isoformat() if _ts else None),
                    "provider": _prov,
                    "url": _src,
                    "score": float(_score),
                    "snippet": snippet
                })
            
            total = int(total or 0)
            seen = offset + len(items)
            has_more = seen < total
            next_offset = seen if has_more else None
            
            return {
                "items": items,
                "total": total,
                "has_more": has_more,
                "next_offset": next_offset
            }
            
    except psycopg2.Error as e:
        return {
            "items": [],
            "total": 0,
            "has_more": False,
            "next_offset": None,
            "error": f"Database error: {str(e)}"
        }
    except Exception as e:
        return {
            "items": [],
            "total": 0,
            "has_more": False,
            "next_offset": None,
            "error": f"Unexpected error: {str(e)}"
        }


# Register the agent at module import time
from .registry import register
register("search.find", run)
