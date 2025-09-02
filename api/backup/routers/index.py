# api/routers/index.py  (özet patch)
import os
import hashlib
from typing import List
import numpy as np
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

try:
    from openai import OpenAI
    from openai import AuthenticationError as OAIAuthError
except Exception:
    OpenAI = None
    OAIAuthError = Exception

router = APIRouter(prefix="/index", tags=["index"])

EMB_MODEL = os.getenv("EMBED_MODEL", "text-embedding-3-small")
EMB_DIM_ENV = int(os.getenv("EMBED_DIM", "1536"))
USE_LOCAL = os.getenv("LOCAL_EMBED", "0") == "1"
OAI_KEY = os.getenv("OPENAI_API_KEY", "")

oai = OpenAI(api_key=OAI_KEY) if (
    OpenAI and OAI_KEY and not USE_LOCAL) else None


class EmbedItem(BaseModel):
    id: str
    text: str


class EmbedReq(BaseModel):
    items: List[EmbedItem]
    dim: int = Field(default=EMB_DIM_ENV)


def _fake_vec(text: str, dim: int) -> List[float]:
    h = hashlib.blake2b(text.encode("utf-8"), digest_size=16).digest()
    seed = int.from_bytes(h, "big") % (2**32)
    rng = np.random.default_rng(seed)
    v = rng.standard_normal(dim)
    n = float(np.linalg.norm(v)) or 1.0
    return (v / n).astype(np.float32).tolist()


def _embed_texts(texts: List[str], dim: int) -> List[List[float]]:
    # Fallback: local/dummy
    if USE_LOCAL or not OAI_KEY or oai is None:
        return [_fake_vec(t, dim) for t in texts]

    # OpenAI
    try:
        resp = oai.embeddings.create(model=EMB_MODEL, input=texts)
        vecs = [d.embedding for d in resp.data]
        if any(len(v) != dim for v in vecs):
            # model boyutu ile istenen dim uyuşmuyorsa kullanıcıya bildir
            raise HTTPException(
                status_code=400, detail=f"dim_mismatch: got {len(vecs[0])}, expected {dim}")
        return vecs
    except OAIAuthError:
        # Daha okunur hata
        raise HTTPException(
            status_code=502, detail="embedding_provider_auth_error")
    except Exception as e:
        raise HTTPException(
            status_code=502, detail=f"embedding_provider_error:{e.__class__.__name__}")


@router.post("/embed")
def embed(req: EmbedReq):
    # DIM guard: model ile uyum
    if not USE_LOCAL and OAI_KEY and EMB_MODEL == "text-embedding-3-small" and req.dim != 1536:
        raise HTTPException(
            status_code=400, detail="dim_must_be_1536_for_text-embedding-3-small")
    if not USE_LOCAL and OAI_KEY and EMB_MODEL == "text-embedding-3-large" and req.dim != 3072:
        raise HTTPException(
            status_code=400, detail="dim_must_be_3072_for_text-embedding-3-large")

    texts = [it.text or "" for it in req.items]
    ids = [it.id for it in req.items]
    if any(t == "" for t in texts):
        # Boş text geldiyse sinyal verelim (n8n tarafında prune et)
        raise HTTPException(status_code=400, detail="empty_text_item")

    vecs = _embed_texts(texts, req.dim)

    # DB yazımı (var olan upsert kodunu burada kullanıyorsun)
    # örnek:
    # with _connect() as conn:
    #   cur.execute("UPDATE documents SET embedding = %s WHERE id = %s", (vec, uuid))
    #   ...

    return {"ok": True, "count": len(vecs)}
