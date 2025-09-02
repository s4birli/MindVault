# api/routers/search.py
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional
import psycopg2
import os
import math

router = APIRouter(prefix="/search", tags=["search"])
PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")

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


class SearchRequest(BaseModel):
    query: str
    top_k: int = 24
    offset: int = 0
    tags: Optional[List[str]] = None          # hard filter (AND ANY)
    boost_tags: Optional[List[str]] = None    # soft boost (no filter)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    lang: Optional[str] = None
    highlight: bool = False
    decay_days: int = 7                       # time-decay penceresi (gün)


class SearchHit(BaseModel):
    id: str
    title: Optional[str] = None
    preview: Optional[str] = None
    ts: Optional[str] = None
    provider: Optional[str] = None
    source_url: Optional[str] = None
    score: float
    snippet: Optional[str] = None


class SearchResponse(BaseModel):
    hits: List[SearchHit]
    total: int
    has_more: bool
    next_offset: Optional[int]


def _connect():
    return psycopg2.connect(PG_DSN)


def _qvec(text: str):
    if not oai:
        return None
    try:
        resp = oai.embeddings.create(model=EMB_MODEL, input=[text])
        return resp.data[0].embedding
    except Exception:
        return None


def _auto_lang_from_query(q: str) -> str:
    tr_chars = set("ıİğĞşŞöÖçÇüÜ")
    return "turkish_unaccent" if any(ch in tr_chars for ch in q) else "simple_unaccent"


@router.post("", response_model=SearchResponse)
def search(req: SearchRequest):
    q = (req.query or "").strip()
    if not q:
        return SearchResponse(hits=[], total=0, has_more=False, next_offset=None)

    tags = [t.lower() for t in (req.tags or [])]
    boost_tags = [t.lower() for t in (req.boost_tags or [])]
    lang_cfg = (req.lang or _auto_lang_from_query(q)).strip()
    decay_days = max(1, min(30, int(req.decay_days)))  # 1..30 gün sınırı

    where = ["1=1"]
    params: dict = {
        "qtext": q,
        "cfg": lang_cfg,
        "top_k": max(1, min(200, req.top_k)),
        "offset": max(0, req.offset),
        "decay_days": decay_days,
    }

    if req.date_from:
        where.append("d.ts >= %(date_from)s")
        params["date_from"] = req.date_from
    if req.date_to:
        where.append("d.ts <= %(date_to)s")
        params["date_to"] = req.date_to

    tag_join = ""
    if tags:
        tag_join = """
          JOIN document_tags dt ON dt.document_id = d.id
          JOIN tags t ON t.id = dt.tag_id AND lower(t.name) = ANY(%(tags)s)
        """
        params["tags"] = tags

    # Soft-boost edilecek tag listesi (filtre değil)
    if boost_tags:
        params["boost_tags"] = boost_tags

    qvec = _qvec(q)
    vec_select = "0.0 AS vec_score"
    vec_order = "0.0"
    if qvec is not None:
        params["qvec"] = qvec
        vec_select = """
          CASE
            WHEN d.embedding IS NULL THEN 0.0
            ELSE (1.0 - (d.embedding <=> %(qvec)s::vector))
          END AS vec_score
        """
        vec_order = "vec_score"

    headline_opts = "StartSel='<mark>', StopSel='</mark>', MaxFragments=2, MinWords=3, MaxWords=20, ShortWord=2, HighlightAll=TRUE"
    params["headline_opts"] = headline_opts
    params["highlight"] = bool(req.highlight)

    # Ağırlıklar (toplam=1.0): BM25 0.55 + Vec 0.35 + Tag 0.07 + Decay 0.03
    # İleride istersen parametreleştiririz.
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

        -- Full-text alanları
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.title,'')), 'A') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.preview,'')), 'B') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.plain_text,'')), 'C') AS doc_fts,

        -- Sorgu
        websearch_to_tsquery(%(cfg)s::regconfig, %(qtext)s) AS q_fts,

        -- Vektör
        {vec_select},

        -- Time-decay: son N günde lineer [0..1] (şu an küçük bonus veriyoruz)
        GREATEST(
          0.0,
          1.0 - (EXTRACT(EPOCH FROM (now() - d.ts)) / (60*60*24*%(decay_days)s))
        ) AS decay_score,

        -- Tag boost: boost_tags'den herhangi biri dokümana atanmışsa 1.0 (aksi 0)
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

        -- Final skor (MVP ayarları)
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

    with _connect() as conn, conn.cursor() as cur:
        try:
            # psycopg2 NULL listleri kabul etmediği için None atanmalı
            if not boost_tags:
                params["boost_tags"] = None
            cur.execute(sql, params)
            rows = cur.fetchall()
        except Exception as e:
            raise RuntimeError(f"db_error: {e}")

    hits: List[SearchHit] = []
    total = 0
    for row in rows:
        _id, _title, _preview, _ts, _prov, _src, _score, _total, _hl = row
        total = _total or total
        if _score is None or not math.isfinite(float(_score)):
            _score = 0.0
        snippet = _hl if (req.highlight and _hl) else (_preview or None)
        hits.append(SearchHit(
            id=_id,
            title=_title,
            preview=_preview,
            ts=(_ts.isoformat() if _ts else None),
            provider=_prov,
            source_url=_src,
            score=float(_score),
            snippet=snippet,
        ))

    total = int(total or 0)
    seen = req.offset + len(hits)
    has_more = seen < total
    next_offset = seen if has_more else None

    return SearchResponse(hits=hits, total=total, has_more=has_more, next_offset=next_offset)
