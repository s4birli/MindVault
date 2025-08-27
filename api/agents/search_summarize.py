"""
Search Summarize Agent

Summarizes a set of documents/IDs into a short brief with source references.
"""
import os
import psycopg2
from typing import Dict, Any, List, Optional
import json

# Database connection
PG_DSN = os.getenv("PG_DSN", "postgresql://postgres:password@localhost:5432/mindvault")

# OpenAI client for summarization
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=OPENAI_API_KEY)
        SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "gpt-4o-mini")
    except Exception:
        oai = None
else:
    oai = None


def _connect():
    """Create database connection."""
    return psycopg2.connect(PG_DSN)


def _fetch_documents(doc_ids: List[str]) -> List[Dict[str, Any]]:
    """
    Fetch document details by IDs.
    
    Args:
        doc_ids: List of document IDs to fetch
        
    Returns:
        List of document dictionaries with id, title, preview, content, ts, provider, url
    """
    if not doc_ids:
        return []
    
    # Prepare placeholders for the query
    placeholders = ','.join(['%s'] * len(doc_ids))
    
    sql = f"""
        SELECT 
            d.id::text,
            COALESCE(NULLIF(d.title, ''), '(no title)') AS title,
            COALESCE(d.preview, '') AS preview,
            COALESCE(d.plain_text, '') AS content,
            d.ts,
            s.provider,
            d.source_url,
            COALESCE(d.metadata->>'from_name', '') AS from_name,
            COALESCE(d.metadata->>'from_email', '') AS from_email
        FROM documents d
        JOIN sources s ON s.id = d.source_id
        WHERE d.id::text = ANY(%s)
        ORDER BY d.ts DESC
    """
    
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, (doc_ids,))
            rows = cur.fetchall()
            
            documents = []
            for row in rows:
                doc_id, title, preview, content, ts, provider, url, from_name, from_email = row
                
                documents.append({
                    'id': doc_id,
                    'title': title,
                    'preview': preview,
                    'content': content[:2000] if content else preview[:500],  # Limit content for summarization
                    'ts': ts.isoformat() if ts else None,
                    'provider': provider,
                    'url': url,
                    'from_name': from_name,
                    'from_email': from_email
                })
            
            return documents
    except Exception as e:
        raise RuntimeError(f"Database error: {e}")


def _create_summary_with_llm(documents: List[Dict[str, Any]], language: str = "tr", 
                           summary_type: str = "brief") -> Dict[str, Any]:
    """
    Create summary using LLM.
    
    Args:
        documents: List of document dictionaries
        language: Language for summary ("tr" or "en")
        summary_type: Type of summary ("brief", "detailed", "bullet_points")
        
    Returns:
        Dictionary with summary and source_refs
    """
    if not oai:
        return _create_fallback_summary(documents, language)
    
    # Prepare document content for summarization
    doc_content = []
    for i, doc in enumerate(documents, 1):
        content_text = f"Document {i}:\n"
        content_text += f"Title: {doc['title']}\n"
        if doc.get('from_name') or doc.get('from_email'):
            from_info = doc.get('from_name', '') or doc.get('from_email', '')
            content_text += f"From: {from_info}\n"
        if doc.get('ts'):
            content_text += f"Date: {doc['ts'][:10]}\n"  # Just the date part
        content_text += f"Content: {doc['content']}\n"
        content_text += "---\n"
        doc_content.append(content_text)
    
    combined_content = "\n".join(doc_content)
    
    # Create system prompt based on language and summary type
    if language.startswith("tr"):
        system_prompt = f"""Sen bir uzman belge özetleme asistanısın. Verilen belgeleri analiz edip özetliyorsun.

Görevin:
1. Belgelerin ana konularını ve önemli noktalarını belirle
2. {_get_summary_style_tr(summary_type)} formatında özetle
3. Her önemli nokta için kaynak referansı ver (Document 1, Document 2, vb.)
4. Özet kısa, net ve bilgilendirici olsun

Kaynak referansları için [Doc 1], [Doc 2] formatını kullan."""

        user_prompt = f"""Lütfen aşağıdaki belgeleri özetle:

{combined_content}

Özet dilini Türkçe yap ve kaynak referanslarını belirt."""

    else:
        system_prompt = f"""You are an expert document summarization assistant. You analyze and summarize given documents.

Your task:
1. Identify main topics and important points from the documents
2. Summarize in {_get_summary_style_en(summary_type)} format
3. Provide source references for each important point (Document 1, Document 2, etc.)
4. Keep summary concise, clear, and informative

Use [Doc 1], [Doc 2] format for source references."""

        user_prompt = f"""Please summarize the following documents:

{combined_content}

Provide the summary in English with source references."""

    try:
        response = oai.chat.completions.create(
            model=SUMMARY_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.3,
            max_tokens=800
        )
        
        summary_text = response.choices[0].message.content.strip()
        
        # Extract source references from the summary
        source_refs = []
        for i, doc in enumerate(documents, 1):
            if f"[Doc {i}]" in summary_text or f"Document {i}" in summary_text:
                source_refs.append({
                    "id": doc['id'],
                    "title": doc['title'],
                    "url": doc.get('url'),
                    "reference": f"Doc {i}"
                })
        
        return {
            "summary": summary_text,
            "source_refs": source_refs,
            "summary_type": summary_type,
            "language": language
        }
        
    except Exception as e:
        return _create_fallback_summary(documents, language)


def _get_summary_style_tr(summary_type: str) -> str:
    """Get Turkish summary style description."""
    styles = {
        "brief": "kısa ve öz",
        "detailed": "detaylı ve kapsamlı",
        "bullet_points": "madde madde"
    }
    return styles.get(summary_type, "kısa ve öz")


def _get_summary_style_en(summary_type: str) -> str:
    """Get English summary style description."""
    styles = {
        "brief": "brief and concise",
        "detailed": "detailed and comprehensive", 
        "bullet_points": "bullet point"
    }
    return styles.get(summary_type, "brief and concise")


def _create_fallback_summary(documents: List[Dict[str, Any]], language: str = "tr") -> Dict[str, Any]:
    """
    Create fallback summary when LLM is not available.
    
    Args:
        documents: List of document dictionaries
        language: Language for summary
        
    Returns:
        Dictionary with basic summary and source references
    """
    if language.startswith("tr"):
        summary_parts = [f"Toplam {len(documents)} belge özetlendi:"]
        
        for i, doc in enumerate(documents, 1):
            title = doc['title']
            date = doc.get('ts', '')[:10] if doc.get('ts') else 'Tarih bilinmiyor'
            from_info = doc.get('from_name') or doc.get('from_email') or 'Gönderen bilinmiyor'
            
            summary_parts.append(f"{i}. {title} ({date}) - {from_info}")
        
        summary_text = "\n".join(summary_parts)
    else:
        summary_parts = [f"Summary of {len(documents)} documents:"]
        
        for i, doc in enumerate(documents, 1):
            title = doc['title']
            date = doc.get('ts', '')[:10] if doc.get('ts') else 'Unknown date'
            from_info = doc.get('from_name') or doc.get('from_email') or 'Unknown sender'
            
            summary_parts.append(f"{i}. {title} ({date}) - {from_info}")
        
        summary_text = "\n".join(summary_parts)
    
    # Create source references
    source_refs = []
    for i, doc in enumerate(documents, 1):
        source_refs.append({
            "id": doc['id'],
            "title": doc['title'],
            "url": doc.get('url'),
            "reference": f"Doc {i}"
        })
    
    return {
        "summary": summary_text,
        "source_refs": source_refs,
        "summary_type": "brief",
        "language": language
    }


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Summarize a set of documents by IDs.
    
    Args:
        params: Dictionary with keys:
            - doc_ids: List[str] - Document IDs to summarize (required)
            - language: str - Summary language ("tr" or "en", default auto-detect)
            - summary_type: str - Type of summary ("brief", "detailed", "bullet_points", default "brief")
            - max_docs: int - Maximum number of documents to process (default 10, max 20)
    
    Returns:
        Dictionary with:
            - summary: str - Generated summary text
            - source_refs: List[Dict] - Source references with id, title, url, reference
            - summary_type: str - Type of summary used
            - language: str - Language used
            - doc_count: int - Number of documents processed
    """
    # Extract and validate parameters
    doc_ids = params.get("doc_ids", [])
    if not doc_ids or not isinstance(doc_ids, list):
        return {
            "error": "doc_ids parameter is required and must be a list",
            "summary": "",
            "source_refs": [],
            "doc_count": 0
        }
    
    # Limit number of documents
    max_docs = min(20, max(1, params.get("max_docs", 10)))
    doc_ids = doc_ids[:max_docs]
    
    # Extract other parameters
    language = params.get("language", "tr").lower()
    summary_type = params.get("summary_type", "brief").lower()
    
    # Validate summary_type
    if summary_type not in ["brief", "detailed", "bullet_points"]:
        summary_type = "brief"
    
    try:
        # Fetch documents
        documents = _fetch_documents(doc_ids)
        
        if not documents:
            error_msg = "Belirtilen ID'lerde belge bulunamadı" if language.startswith("tr") else "No documents found with specified IDs"
            return {
                "error": error_msg,
                "summary": "",
                "source_refs": [],
                "doc_count": 0
            }
        
        # Create summary
        result = _create_summary_with_llm(documents, language, summary_type)
        result["doc_count"] = len(documents)
        
        return result
        
    except Exception as e:
        error_msg = f"Özetleme hatası: {str(e)}" if language.startswith("tr") else f"Summarization error: {str(e)}"
        return {
            "error": error_msg,
            "summary": "",
            "source_refs": [],
            "doc_count": 0
        }


# Register the agent at module import time
try:
    from .registry import register
    register("search.summarize", run)
except ImportError:
    # Fallback for when called directly
    import registry
    registry.register("search.summarize", run)
