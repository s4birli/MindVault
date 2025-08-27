# api/routers/ask.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Tuple, Dict, Any
import os
import re
import psycopg2
import json
from datetime import datetime, timedelta, timezone

router = APIRouter(prefix="/ask", tags=["ask"])
PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")

# OpenAI (opsiyonel)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=OPENAI_API_KEY)
        CHAT_MODEL = os.getenv("ASK_CHAT_MODEL", "gpt-4o-mini")
    except Exception:
        oai = None
else:
    oai = None

try:
    from langdetect import detect
except Exception:
    detect = None

# ---- Request/Response ----


class AskRequest(BaseModel):
    query: str = Field(..., description="Kullanıcı sorusu / talebi")
    final_n: int = Field(default=5, ge=1, le=50,
                         description="Bağlam için kaç doküman kullanılacak")
    language: str = Field(default="auto", description="'auto' | 'tr' | 'en'")
    mode: str = Field(default="summary", description="summary | email")
    # Email modu
    email_tone: Optional[str] = Field(
        default="neutral", description="formal | neutral | friendly")
    email_subject_hint: Optional[str] = None
    email_recipient: Optional[str] = None
    email_sender: Optional[str] = None
    # Tuning
    decay_days: Optional[int] = Field(default=None, ge=1, le=365)
    decay_weight: Optional[float] = Field(default=0.15, ge=0.0, le=1.0)
    boost_tags: Optional[List[str]] = Field(
        default=None, description="Skorlama için pozitif etiketler")
    # Cevap formatı
    max_sentences: int = Field(
        default=1, ge=1, le=8, description="Cevap cümle üst sınırı")


class SourceRef(BaseModel):
    id: str
    title: Optional[str] = None
    url: Optional[str] = None


class AskResponse(BaseModel):
    answer: str
    used_ids: List[str]
    sources: Optional[List[SourceRef]] = None
    # email modu
    subject: Optional[str] = None
    body: Optional[str] = None
    format: Optional[str] = None

# ---- Helpers ----


def _connect():
    return psycopg2.connect(PG_DSN)


def _auto_lang(s: str) -> str:
    s = (s or "").strip()
    if not s:
        return "simple_unaccent"
    # Türkçe harf heuristiği
    if any(ch in "ıİğĞşŞöÖçÇüÜ" for ch in s):
        return "turkish_unaccent"
    # langdetect mevcutsa
    if detect:
        try:
            lang = detect(s)
            if lang == "tr":
                return "turkish_unaccent"
        except Exception:
            pass
    return "simple_unaccent"


_RELATIVE_TR = [
    (re.compile(r"\bson\s+(\d+)\s*gün\b", re.I), "days"),
    (re.compile(r"\bson\s+(\d+)\s*hafta\b", re.I), "weeks"),
    (re.compile(r"\bson\s+(\d+)\s*ay\b", re.I), "months"),
    (re.compile(r"\bson\s+(\d+)\s*yıl\b", re.I), "years"),
    (re.compile(r"\bdün\b", re.I), ("days", 1)),
    (re.compile(r"\bbugün\b", re.I), ("days", 0)),
]
_RELATIVE_EN = [
    (re.compile(r"\blast\s+(\d+)\s*days?\b", re.I), "days"),
    (re.compile(r"\blast\s+(\d+)\s*weeks?\b", re.I), "weeks"),
    (re.compile(r"\blast\s+(\d+)\s*months?\b", re.I), "months"),
    (re.compile(r"\blast\s+(\d+)\s*years?\b", re.I), "years"),
    (re.compile(r"\byesterday\b", re.I), ("days", 1)),
    (re.compile(r"\btoday\b", re.I), ("days", 0)),
]


def _parse_time_window(text: str, lang_cfg: str) -> Tuple[Optional[str], Optional[str], str]:
    """
    Sorgudaki 'son 3 gün/hafta/...' gibi ifadeleri yakalar, date_from/to üretir, metinden çıkarır.
    """
    now = datetime.now(timezone.utc)
    cleaned = text
    date_from: Optional[datetime] = None
    rules = _RELATIVE_TR if lang_cfg == "turkish_unaccent" else _RELATIVE_EN

    for rx, unit in rules:
        m = rx.search(cleaned)
        if not m:
            continue
        if isinstance(unit, tuple):  # yesterday/today
            u, n = unit
            if u == "days":
                start = now - timedelta(days=n)
                end = now
        else:
            n = int(m.group(1))
            if unit == "days":
                start = now - timedelta(days=n)
            elif unit == "weeks":
                start = now - timedelta(weeks=n)
            elif unit == "months":
                start = now - timedelta(days=30*n)
            elif unit == "years":
                start = now - timedelta(days=365*n)
            end = now
        date_from = start
        cleaned = rx.sub(" ", cleaned)
        break

    df = date_from.isoformat() if date_from else None
    dt = now.isoformat() if date_from else None
    return df, dt, " ".join(cleaned.split())


_FILTER_RE = re.compile(r"\b(from|sender|tag|is):(\"[^\"]+\"|\S+)", re.I)


def _parse_inline_filters(text: str) -> Tuple[Dict[str, Any], str]:
    """
    from:hmrc.gov.uk  sender:\"HMRC\"  tag:sent  is:sent|inbox
    """
    filters: Dict[str, Any] = {"from": [], "sender": [], "tag": [], "is": []}
    cleaned = text
    for m in _FILTER_RE.finditer(text):
        key = m.group(1).lower()
        raw = m.group(2)
        val = raw.strip("\"")
        filters[key].append(val)
        cleaned = cleaned.replace(m.group(0), " ")
    # normalize
    filters["from"] = list(set(filters["from"]))
    filters["sender"] = list(set(filters["sender"]))
    filters["tag"] = list(set(filters["tag"]))
    filters["is"] = list(set(filters["is"]))
    return filters, " ".join(cleaned.split())


def _wants_latest(text: str, lang_cfg: str) -> bool:
    if lang_cfg == "turkish_unaccent":
        return bool(re.search(r"\ben son\b|\bson (posta|email|e-?posta)\b", text, re.I))
    return bool(re.search(r"\b(latest|most recent)\b", text, re.I))


def _lang_to_answer_prefix(lang_cfg: str, none_case: bool = False) -> str:
    if lang_cfg == "turkish_unaccent":
        return "Eşleşen doküman bulunamadı." if none_case else "Özet:"
    return "No matching documents found." if none_case else "Summary:"

# ---- DB retrieval (hybrid, hafifletilmiş) ----


def _search_ids(
    query: str,
    final_n: int,
    lang_cfg: str,
    date_from: Optional[str],
    date_to: Optional[str],
    filters: Dict[str, Any],
    want_latest: bool,
) -> List[str]:
    """
    Hybrid arama: BM25 + vektör (eğer docs.embedding var). Filtreler:
      - from domain/name (LIKE)
      - tag (document_tags/tags)
      - is:sent/inbox (tag tablosundan)
    En yeni tek kaydı istiyorsa want_latest=True → LIMIT 1, ts DESC.
    """
    where = ["1=1"]
    params: Dict[str, Any] = {"qtext": query,
                              "cfg": lang_cfg, "k": max(1, final_n)}
    if date_from:
        where.append("d.ts >= %(date_from)s")
        params["date_from"] = date_from
    if date_to:
        where.append("d.ts <= %(date_to)s")
        params["date_to"] = date_to

    joins = ["JOIN sources s ON s.id = d.source_id"]
    # tag filtresi
    if filters.get("tag") or filters.get("is"):
        joins.append("LEFT JOIN document_tags dt ON dt.document_id = d.id")
        joins.append("LEFT JOIN tags tg ON tg.id = dt.tag_id")

    # sender / from filtresi (basit LIKE)
    if filters.get("from"):
        where.append(
            "(" + " OR ".join([f"LOWER(COALESCE(d.from_email,'')) LIKE %(from_{i})s" for i, _ in enumerate(filters["from"])]) + ")")
        for i, v in enumerate(filters["from"]):
            params[f"from_{i}"] = f"%{v.lower()}%"
    if filters.get("sender"):
        where.append(
            "(" + " OR ".join([f"LOWER(COALESCE(d.from_name,'')) LIKE %(sender_{i})s" for i, _ in enumerate(filters["sender"])]) + ")")
        for i, v in enumerate(filters["sender"]):
            params[f"sender_{i}"] = f"%{v.lower()}%"
    if filters.get("tag"):
        where.append(
            "(" + " OR ".join([f"LOWER(tg.name) = %(tag_{i})s" for i, _ in enumerate(filters["tag"])]) + ")")
        for i, v in enumerate(filters["tag"]):
            params[f"tag_{i}"] = v.lower()
    if filters.get("is"):
        # is:sent / is:inbox gibi — etiketlerden yakala
        term_map = {"sent": "sent", "inbox": "inbox", "important": "important"}
        valids = [term_map.get(v.lower())
                  for v in filters["is"] if term_map.get(v.lower())]
        if valids:
            where.append(
                "(" + " OR ".join([f"LOWER(tg.name) = %(is_{i})s" for i, _ in enumerate(valids)]) + ")")
            for i, v in enumerate(valids):
                params[f"is_{i}"] = v

    # vektör skoru (docs.embedding mevcutsa)
    vec_select = "0.0 AS vec_score"
    vec_order = "0.0"
    try:
        # query embedding al
        if OPENAI_API_KEY:
            from openai import OpenAI
            _oai = OpenAI(api_key=OPENAI_API_KEY)
            resp = _oai.embeddings.create(
                model="text-embedding-3-small", input=[query])
            qvec = resp.data[0].embedding
            params["qvec"] = qvec
            vec_select = "CASE WHEN d.embedding IS NULL THEN 0.0 ELSE (1.0 - (d.embedding <=> %(qvec)s::vector)) END AS vec_score"
            vec_order = "vec_score"
    except Exception:
        pass

    # Başlık/özet/metin → FTS
    sql = f"""
    WITH scored AS (
      SELECT
        d.id::text,
        d.ts,
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.title,'')), 'A') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.preview,'')), 'B') ||
        setweight(to_tsvector(%(cfg)s::regconfig, COALESCE(d.plain_text,'')), 'C') AS doc_fts,
        websearch_to_tsquery(%(cfg)s::regconfig, %(qtext)s) AS q_fts,
        {vec_select}
      FROM documents d
      {' '.join(joins)}
      WHERE {' AND '.join(where)}
    ),
    ranked AS (
      SELECT
        id, ts,
        ts_rank_cd(doc_fts, q_fts, 32) AS bm25,
        {vec_order}::float AS vs,
        (0.6 * ts_rank_cd(doc_fts, q_fts, 32) + 0.4 * {vec_order}) AS score
      FROM scored
      WHERE q_fts @@ doc_fts OR {vec_order} > 0.0
    )
    SELECT id
    FROM ranked
    ORDER BY {"ts DESC, score DESC" if want_latest else "score DESC, ts DESC"}
    LIMIT %(k)s;
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    return [r[0] for r in rows]


def _fetch_docs(ids: List[str]) -> List[dict]:
    if not ids:
        return []
    sql = """
      SELECT d.id::text, s.provider, d.title, d.preview, d.plain_text, d.ts, d.source_url
      FROM documents d
      JOIN sources s ON s.id = d.source_id
      WHERE d.id = ANY(%s::uuid[])
    """
    with _connect() as conn, conn.cursor() as cur:
        cur.execute(sql, (ids,))
        rows = cur.fetchall()
    out = []
    for r in rows:
        out.append({
            "id": r[0], "provider": r[1], "title": r[2],
            "preview": r[3], "plain_text": r[4],
            "ts": r[5].isoformat() if r[5] else None,
            "url": r[6]
        })
    # En yeni önce
    out.sort(key=lambda x: x["ts"] or "", reverse=True)
    return out

# ---- Prompting ----


def _limit_sentences(text: str, n: int) -> str:
    # Çok kaba bir cümle bölme; pratikte yeterli
    parts = re.split(r'(?<=[.!?])\s+', text.strip())
    return " ".join(parts[:max(1, n)]).strip()


def _build_summary_prompt(query: str, language_cfg: str, context_docs: List[dict], max_sentences: int) -> List[dict]:
    tr = (language_cfg == "turkish_unaccent")
    sys = "You are a helpful assistant. Use ONLY the provided context. If insufficient, say so."
    sys += " Respond in Turkish." if tr else " Respond in English."
    sys += f" Answer in at most {max_sentences} sentence(s)."
    ctx = []
    for i, d in enumerate(context_docs, 1):
        chunk = d.get("plain_text") or d.get("preview") or ""
        ctx.append(f"[{i}] {d.get('title') or '(no title)'}\n{chunk}\n")
    user = f"Question: {query}\n\nContext:\n" + \
        ("\n\n".join(ctx) if ctx else "(no context)")
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _build_email_prompt(req: AskRequest, language_cfg: str, context_docs: List[dict]) -> List[dict]:
    tr = (language_cfg == "turkish_unaccent")
    tone = (req.email_tone or "neutral").lower()
    if tone not in ("formal", "neutral", "friendly"):
        tone = "neutral"
    sys = (
        "Profesyonel bir e-posta asistanısın. Kısa, açık ve nazik taslaklar üret."
        if tr else
        "You are a professional email assistant. Generate concise, clear and polite drafts."
    )
    ctx = []
    for i, d in enumerate(context_docs, 1):
        chunk = d.get("plain_text") or d.get("preview") or ""
        ctx.append(f"[{i}] {d.get('title') or '(no title)'}\n{chunk}\n")
    if tr:
        user = (
            f"Konu ipucu: {req.email_subject_hint or '-'}\n"
            f"Hitap: {req.email_recipient or '-'}\n"
            f"İmza: {req.email_sender or '-'}\n"
            f"İstek: {req.query}\n\nBağlam:\n" + ("\n\n".join(ctx) if ctx else "(no context)") +
            "\n\nSUBJECT: <tek satır>\nBODY:\n<4–8 cümle; paragraflı>"
        )
    else:
        user = (
            f"Subject hint: {req.email_subject_hint or '-'}\n"
            f"Greeting: {req.email_recipient or '-'}\n"
            f"Signature: {req.email_sender or '-'}\n"
            f"Request: {req.query}\n\nContext:\n" + ("\n\n".join(ctx) if ctx else "(no context)") +
            "\n\nSUBJECT: <one line>\nBODY:\n<4–8 sentences; paragraphs>"
        )
    return [{"role": "system", "content": sys}, {"role": "user", "content": user}]


def _call_llm(messages: List[dict]) -> str:
    if not oai:
        # Model yoksa son mesajı kırpıp döndür
        return messages[-1]["content"][:800]
    resp = oai.chat.completions.create(
        model=CHAT_MODEL, messages=messages, temperature=0.2, max_tokens=400
    )
    return (resp.choices[0].message.content or "").strip()


def _parse_email_output(text: str) -> Tuple[str, str]:
    subject, body = "", text
    lower = text.lower()
    if "subject:" in lower:
        parts = text.split("\n")
        for i, line in enumerate(parts):
            if line.strip().lower().startswith("subject:"):
                subject = line.split(":", 1)[1].strip()
                body_lines, seen = [], False
                for j in range(i+1, len(parts)):
                    if parts[j].strip().lower().startswith("body:"):
                        seen = True
                        continue
                    if seen:
                        body_lines.append(parts[j])
                if seen:
                    body = "\n".join(body_lines).strip()
                break
    return subject, body

# ---- Endpoint ----


@router.post("", response_model=AskResponse)
def ask(req: AskRequest):
    try:
        # 1) Dil seçimi
        lang_cfg = "turkish_unaccent" if req.language.lower().startswith("tr") else \
                   ("simple_unaccent" if req.language.lower().startswith(
                       "en") else _auto_lang(req.query))

        # 2) Inline filtreler + doğal zaman penceresi
        filters, q_clean = _parse_inline_filters(req.query)
        df, dt, q2 = _parse_time_window(q_clean, lang_cfg)
        want_latest = _wants_latest(req.query, lang_cfg)

        # 3) İlgili id'leri çek
        ids = _search_ids(
            query=q2 or req.query,
            final_n=req.final_n,
            lang_cfg=lang_cfg,
            date_from=df, date_to=dt,
            filters=filters,
            want_latest=want_latest
        )

        # 4) Bağlam
        docs = _fetch_docs(ids)

        # 5) Kaynak listesi (UI için)
        sources = [SourceRef(id=d["id"], title=d.get(
            "title"), url=d.get("url")) for d in docs]

        # 6) Modlar
        if req.mode == "email":
            msgs = _build_email_prompt(req, lang_cfg, docs)
            raw = _call_llm(msgs)
            subject, body = _parse_email_output(raw)
            if not subject:
                subject = (
                    req.email_subject_hint or req.query or "Re:").strip()
            if not body:
                if lang_cfg == "turkish_unaccent":
                    body = f"{(req.email_recipient or 'Merhaba')},\n\n{req.query}\n\nSaygılarımla,\n{req.email_sender or ''}"
                else:
                    body = f"{(req.email_recipient or 'Hi')},\n\n{req.query}\n\nBest regards,\n{req.email_sender or ''}"
            return AskResponse(
                answer=f"Subject: {subject}\n\n{body}",
                used_ids=[d["id"] for d in docs],
                sources=sources,
                subject=subject,
                body=body,
                format="email"
            )

        # summary
        msgs = _build_summary_prompt(
            q2 or req.query, lang_cfg, docs, req.max_sentences)

        # 7) Hiç doküman yoksa bile tek cümlelik fallback
        if not docs:
            ans = _lang_to_answer_prefix(lang_cfg, none_case=True)
            return AskResponse(answer=ans, used_ids=[], sources=[])

        raw = _call_llm(msgs)
        answer = _limit_sentences(
            raw or "", req.max_sentences) or _lang_to_answer_prefix(lang_cfg)
        return AskResponse(answer=answer, used_ids=[d["id"] for d in docs], sources=sources)

    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"db_error: {e}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
