# api/agents/search_local.py
"""
Local search agent for finding latest documents from specific senders/domains.
"""
from typing import Dict, Any, List, Optional
import psycopg2
import os
from datetime import datetime

# Database connection using existing pattern
PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")


def _connect():
    """Connect to PostgreSQL database using existing pattern."""
    return psycopg2.connect(PG_DSN)


def run(params: Dict[str, Any]) -> Dict[str, Any]:
    """
    Search for latest documents from specific senders or domains.
    
    Args:
        params: Dictionary with optional keys:
            - sender: str - Filter by sender name (ILIKE search in metadata and content)
            - domain: str - Filter by domain (LIKE search in source_url or metadata)
            - limit: int - Max number of results (default 5, capped at 50)
            - date_from: str - ISO datetime filter for start date
            - date_to: str - ISO datetime filter for end date
            - language: str - Language for text search config ("tr" or "en")
    
    Returns:
        Dictionary with:
            - items: List of document items with id, title, ts, provider, url
    """
    sender = params.get("sender", "").strip()
    domain = params.get("domain", "").strip()
    limit = min(50, max(1, params.get("limit", 5)))  # Cap at 50, min 1
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    language = params.get("language", "en")
    
    # Build WHERE conditions
    where_conditions = ["1=1"]
    query_params: Dict[str, Any] = {"limit": limit}
    
    # Filter by sender (comprehensive search in metadata and content)
    if sender:
        sender_condition = """(
            LOWER(COALESCE(d.metadata->>'from_name', '')) LIKE %(sender_pattern)s OR
            LOWER(COALESCE(d.metadata->>'from_email', '')) LIKE %(sender_pattern)s OR
            LOWER(COALESCE(d.metadata->>'display_name', '')) LIKE %(sender_pattern)s OR
            LOWER(COALESCE(d.title, '')) LIKE %(sender_pattern)s OR
            LOWER(COALESCE(d.preview, '')) LIKE %(sender_pattern)s
        )"""
        where_conditions.append(sender_condition)
        query_params["sender_pattern"] = f"%{sender.lower()}%"
    
    # Filter by domain (search in source_url and metadata)
    if domain:
        domain_condition = """(
            LOWER(COALESCE(d.source_url, '')) LIKE %(domain_pattern)s OR
            LOWER(COALESCE(d.metadata->>'from_email', '')) LIKE %(domain_at_pattern)s OR
            LOWER(COALESCE(d.metadata->>'from_domain', '')) = %(domain_exact)s
        )"""
        where_conditions.append(domain_condition)
        query_params["domain_pattern"] = f"%{domain.lower()}%"
        query_params["domain_at_pattern"] = f"%@{domain.lower()}"
        query_params["domain_exact"] = domain.lower()
    
    # Date filters
    if date_from:
        where_conditions.append("d.ts >= %(date_from)s")
        query_params["date_from"] = date_from
    
    if date_to:
        where_conditions.append("d.ts < %(date_to)s")
        query_params["date_to"] = date_to
    
    # SQL query to get latest documents (following requirements format)
    sql = f"""
        SELECT 
            d.id::text,
            COALESCE(NULLIF(d.title, ''), '(no title)') AS title,
            d.ts,
            s.provider,
            d.source_url
        FROM documents d
        JOIN sources s ON s.id = d.source_id
        WHERE {' AND '.join(where_conditions)}
        ORDER BY d.ts DESC NULLS LAST
        LIMIT %(limit)s
    """
    
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute(sql, query_params)
            rows = cur.fetchall()
            
            items: List[Dict[str, Any]] = []
            for row in rows:
                doc_id, title, ts, provider, url = row
                items.append({
                    "id": doc_id,
                    "title": title,
                    "ts": ts.isoformat() if ts else None,
                    "provider": provider,
                    "url": url
                })
            
            return {"items": items}
            
    except psycopg2.Error as e:
        # Return error information in a structured way
        return {
            "items": [],
            "error": f"Database error: {str(e)}"
        }
    except Exception as e:
        return {
            "items": [],
            "error": f"Unexpected error: {str(e)}"
        }


# Register the agent at module import time
try:
    from .registry import register
    register("search.latest_from", run)
except ImportError:
    # Fallback for when called directly
    import registry
    registry.register("search.latest_from", run)
