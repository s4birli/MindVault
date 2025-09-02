"""Gmail ingestion router for processing emails."""

import hashlib
import re
import asyncio
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any, Union
from fastapi import APIRouter, HTTPException, status, Depends, Body
from pydantic import BaseModel, Field
from email.utils import parsedate_to_datetime

from ..core.security_jwt import get_current_user_id
from ..core.db import engine
from ..core.config import settings
import asyncpg

router = APIRouter()


async def get_db_connection():
    """Get a direct asyncpg database connection."""
    # Extract connection parameters from DATABASE_URL
    # postgresql+asyncpg://postgres:postgres@db:5432/mindvault
    url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://")
    return await asyncpg.connect(url)


class EmailTags(BaseModel):
    """Tag structure for emails."""
    topics: List[str] = Field(default_factory=list)
    doc_kinds: List[str] = Field(default_factory=list)
    entities: Dict[str, List[str]] = Field(default_factory=lambda: {
        "people": [],
        "orgs": [],
        "places": []
    })
    facts: Dict[str, Any] = Field(default_factory=lambda: {
        "invoice_no": None,
        "amount": {
            "currency": None,
            "total": None,
            "account_balance": None
        },
        "due_date": None,
        "period": None,
        "summary": None
    })
    signals: List[str] = Field(default_factory=list)
    projects: List[str] = Field(default_factory=list)


class EmailData(BaseModel):
    """Email data structure for ingestion."""
    gmail_id: str
    message_id: str
    account_email: str
    subject: str
    from_addr: str
    to_addrs: List[str] = Field(default_factory=list)
    cc_addrs: List[str] = Field(default_factory=list)
    date: str  # RFC2822 format
    plain_text_top: Optional[str] = None
    plain_text_full: Optional[str] = None
    raw_html: Optional[str] = None
    has_attachment: bool = False
    thread_id: Optional[str] = None
    
    # New fields for tags and snippet
    snippet: Optional[str] = None
    labels: List[str] = Field(default_factory=list)
    tags: Optional[EmailTags] = None


class EmailBatch(BaseModel):
    """Batch of emails for ingestion."""
    items: List[EmailData]


class IngestionResponse(BaseModel):
    """Response structure for ingestion endpoint."""
    ok: bool
    processed: int
    inserted_items: int
    updated_items: int
    inserted_chunks: int
    skipped_embedding: int
    item_ids: List[int]
    errors: List[str] = Field(default_factory=list)


class OllamaEmbeddingService:
    """Service for generating embeddings using Ollama."""
    
    def __init__(self, base_url: str = "http://ollama:11434"):
        self.base_url = base_url
        self.model = "bge-m3:latest"
        self._warmed_up = False
    
    async def warmup(self):
        """Warm up the Ollama service."""
        if self._warmed_up:
            return
            
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": "warmup",
                        "keep_alive": -1
                    }
                )
                response.raise_for_status()
                self._warmed_up = True
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to warm up Ollama service: {str(e)}"
            )
    
    async def get_embedding(self, text: str) -> List[float]:
        """Get embedding for a text chunk."""
        await self.warmup()
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{self.base_url}/api/embeddings",
                    json={
                        "model": self.model,
                        "prompt": f"passage: {text}",
                        "keep_alive": -1
                    }
                )
                response.raise_for_status()
                data = response.json()
                return data["embedding"]
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"Failed to generate embedding: {str(e)}"
            )


# Global embedding service instance
embedding_service = OllamaEmbeddingService()


class EmailProcessor:
    """Email processing and ingestion logic."""
    
    def __init__(self, db):
        self.db = db
    
    def normalize_email(self, email: EmailData) -> Dict[str, Any]:
        """Normalize email data."""
        # Parse RFC2822 date to datetime object
        try:
            event_at = parsedate_to_datetime(email.date)
        except:
            event_at = datetime.utcnow()
        
        # Extract sender domain
        sender_domain = None
        if email.from_addr and "@" in email.from_addr:
            sender_domain = email.from_addr.split("@")[-1].lower()
        
        # Clean body text
        body = email.plain_text_top or email.plain_text_full or ""
        cleaned_body = self.clean_email_body(body)
        
        # Generate content hash
        content_hash = hashlib.sha256(
            (email.subject + cleaned_body).encode('utf-8')
        ).hexdigest()
        
        return {
            "email": email,
            "event_at": event_at,
            "sender_domain": sender_domain,
            "cleaned_body": cleaned_body,
            "content_hash": content_hash,
            "body": body
        }
    
    def clean_email_body(self, body: str) -> str:
        """Clean email body by removing quotes, signatures, etc."""
        if not body:
            return ""
        
        lines = body.split('\n')
        cleaned_lines = []
        
        for line in lines:
            line = line.strip()
            
            # Skip common quote patterns
            if line.startswith('>') or line.startswith('On ') and 'wrote:' in line:
                break
            
            # Skip signature separators
            if line in ['--', '---', '____']:
                break
            
            # Skip common signature patterns
            if re.match(r'^(Best|Kind|Warm)\s+(regards|wishes)', line, re.IGNORECASE):
                break
            
            cleaned_lines.append(line)
        
        return '\n'.join(cleaned_lines).strip()
    
    def create_chunks(self, subject: str, cleaned_body: str) -> List[Dict[str, Any]]:
        """Create text chunks for embedding."""
        chunks = []
        
        # Chunk 0: Subject (max 300 chars)
        if subject:
            chunks.append({
                "ord": 0,
                "text": subject[:300],
                "lang": "auto"  # Will be detected later
            })
        
        # Chunk 1: First part of body (max 1000 chars)
        if cleaned_body:
            first_chunk = cleaned_body[:1000]
            chunks.append({
                "ord": 1,
                "text": first_chunk,
                "lang": "auto"
            })
            
            # Additional chunks: 1200 chars with 160 overlap
            remaining = cleaned_body[1000:]
            ord_counter = 2
            
            while remaining and len(remaining) > 160:
                chunk_text = remaining[:1200]
                chunks.append({
                    "ord": ord_counter,
                    "text": chunk_text,
                    "lang": "auto"
                })
                
                # Move forward with overlap
                remaining = remaining[1040:]  # 1200 - 160 overlap
                ord_counter += 1
        
        return chunks
    
    async def upsert_email(self, normalized_data: Dict[str, Any]) -> Dict[str, Any]:
        """Upsert email to database."""
        email = normalized_data["email"]
        
        # Check if item already exists with same content hash
        existing_query = """
            SELECT i.item_id, i.content_hash, i.title
            FROM items i
            WHERE (i.origin_source = $1 AND i.origin_id = $2)
               OR EXISTS (
                   SELECT 1 FROM emails e 
                   WHERE e.item_id = i.item_id AND e.message_id = $3
               )
        """
        
        origin_source = email.account_email
        existing = await self.db.fetchrow(
            existing_query, 
            origin_source, 
            email.gmail_id,
            email.message_id
        )
        
        is_update = False
        skip_embedding = False
        
        if existing:
            if existing["content_hash"] == normalized_data["content_hash"]:
                # Content unchanged, skip re-embedding
                skip_embedding = True
                return {
                    "item_id": existing["item_id"],
                    "is_update": False,
                    "skip_embedding": True
                }
            else:
                # Content changed, update needed
                is_update = True
                item_id = existing["item_id"]
                
                # Update content_hash in items table
                await self.db.execute(
                    "UPDATE items SET content_hash = $1 WHERE item_id = $2",
                    normalized_data["content_hash"],
                    item_id
                )
                
                # Delete old chunks
                await self.db.execute(
                    "DELETE FROM chunks WHERE item_id = $1", 
                    item_id
                )
        
        if not is_update:
            # Insert new item
            item_insert = """
                INSERT INTO items (
                    source_type, origin_source, origin_id, title, snippet, content_hash,
                    event_at, thread_id, people, orgs, domains
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                RETURNING item_id
            """
            
            # Extract people and orgs from email addresses
            people = [email.from_addr] + email.to_addrs + email.cc_addrs
            people = [p for p in people if p]  # Remove empty strings
            
            orgs = []
            domains = []
            if normalized_data["sender_domain"]:
                domains.append(normalized_data["sender_domain"])
            
            item_row = await self.db.fetchrow(
                item_insert,
                "email",                          # source_type
                origin_source,                    # origin_source
                email.gmail_id,                   # origin_id
                email.subject,                    # title
                email.snippet,                    # snippet
                normalized_data["content_hash"],  # content_hash
                normalized_data["event_at"],      # event_at
                email.thread_id,                  # thread_id
                people,                           # people
                orgs,                             # orgs
                domains                           # domains
            )
            item_id = item_row["item_id"]
        
        # Insert/update email record
        email_upsert = """
            INSERT INTO emails (
                item_id, message_id, from_addr, to_addrs, cc_addrs,
                sender_domain, has_attachment, raw_text, raw_html,
                cleaned_body, content_hash, subject, plain_text_top, plain_text_full
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14)
            ON CONFLICT (item_id) DO UPDATE SET
                message_id = EXCLUDED.message_id,
                from_addr = EXCLUDED.from_addr,
                to_addrs = EXCLUDED.to_addrs,
                cc_addrs = EXCLUDED.cc_addrs,
                sender_domain = EXCLUDED.sender_domain,
                has_attachment = EXCLUDED.has_attachment,
                raw_text = EXCLUDED.raw_text,
                raw_html = EXCLUDED.raw_html,
                cleaned_body = EXCLUDED.cleaned_body,
                content_hash = EXCLUDED.content_hash,
                subject = EXCLUDED.subject,
                plain_text_top = EXCLUDED.plain_text_top,
                plain_text_full = EXCLUDED.plain_text_full
        """
        
        await self.db.execute(
            email_upsert,
            item_id,                              # item_id
            email.message_id,                     # message_id
            email.from_addr,                      # from_addr
            email.to_addrs,                       # to_addrs
            email.cc_addrs,                       # cc_addrs
            normalized_data["sender_domain"],     # sender_domain
            email.has_attachment,                 # has_attachment
            normalized_data["body"],              # raw_text
            email.raw_html,                       # raw_html
            normalized_data["cleaned_body"],      # cleaned_body
            normalized_data["content_hash"],      # content_hash
            email.subject,                        # subject
            email.plain_text_top,                 # plain_text_top
            email.plain_text_full                 # plain_text_full
        )
        
        return {
            "item_id": item_id,
            "is_update": is_update,
            "skip_embedding": skip_embedding
        }
    
    async def process_chunks(self, item_id: int, chunks: List[Dict[str, Any]]) -> int:
        """Process and insert chunks with embeddings."""
        inserted_chunks = 0
        
        for chunk in chunks:
            try:
                # Generate embedding
                embedding = await embedding_service.get_embedding(chunk["text"])
                
                # Insert chunk
                chunk_insert = """
                    INSERT INTO chunks (item_id, ord, text, lang, embedding, bm25_tsv)
                    VALUES ($1, $2, $3, $4, $5::vector, to_tsvector('simple', $6))
                """
                
                await self.db.execute(
                    chunk_insert,
                    item_id,           # item_id
                    chunk["ord"],      # ord
                    chunk["text"],     # text
                    chunk["lang"],     # lang
                    str(embedding),    # embedding as string
                    chunk["text"]      # text for bm25_tsv
                )
                
                inserted_chunks += 1
                
            except Exception as e:
                print(f"Error processing chunk {chunk['ord']} for item {item_id}: {e}")
                # Continue with other chunks even if one fails
                continue
        
        return inserted_chunks
    
    async def process_tags(self, item_id: int, email: EmailData) -> None:
        """Process and insert tags for the email."""
        if not email.labels and not email.tags:
            return  # No tags to process
        
        # Prepare tag data
        labels = email.labels or []
        tags = email.tags or EmailTags()
        
        # Extract structured data from tags
        topics = tags.topics
        doc_kinds = tags.doc_kinds
        people = tags.entities.get("people", [])
        orgs = tags.entities.get("orgs", [])
        places = tags.entities.get("places", [])
        
        # Extract facts
        facts = tags.facts
        invoice_no = facts.get("invoice_no")
        amount = facts.get("amount", {})
        amount_currency = amount.get("currency") if amount else None
        amount_total = amount.get("total") if amount else None
        amount_account_balance = amount.get("account_balance") if amount else None
        due_date = facts.get("due_date")
        period = facts.get("period")
        summary = facts.get("summary")
        
        # Parse due_date if it's a string
        due_date_parsed = None
        if due_date:
            try:
                from datetime import datetime
                if isinstance(due_date, str):
                    # Try to parse various date formats
                    for fmt in ["%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y-%m-%d %H:%M:%S"]:
                        try:
                            due_date_parsed = datetime.strptime(due_date, fmt).date()
                            break
                        except ValueError:
                            continue
                else:
                    due_date_parsed = due_date
            except:
                pass  # Keep as None if parsing fails
        
        signals = tags.signals
        projects = tags.projects
        
        # Store raw tags as JSONB
        tags_raw = {
            "topics": topics,
            "doc_kinds": doc_kinds,
            "entities": {
                "people": people,
                "orgs": orgs,
                "places": places
            },
            "facts": facts,
            "signals": signals,
            "projects": projects
        }
        
        # Upsert item_tags
        tags_upsert = """
            INSERT INTO item_tags (
                item_id, labels, topics, doc_kinds, people, orgs, places,
                invoice_no, amount_currency, amount_total, amount_account_balance,
                due_date, period, summary, tags_raw, signals, projects
            ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15, $16, $17)
            ON CONFLICT (item_id) DO UPDATE SET
                labels = EXCLUDED.labels,
                topics = EXCLUDED.topics,
                doc_kinds = EXCLUDED.doc_kinds,
                people = EXCLUDED.people,
                orgs = EXCLUDED.orgs,
                places = EXCLUDED.places,
                invoice_no = EXCLUDED.invoice_no,
                amount_currency = EXCLUDED.amount_currency,
                amount_total = EXCLUDED.amount_total,
                amount_account_balance = EXCLUDED.amount_account_balance,
                due_date = EXCLUDED.due_date,
                period = EXCLUDED.period,
                summary = EXCLUDED.summary,
                tags_raw = EXCLUDED.tags_raw,
                signals = EXCLUDED.signals,
                projects = EXCLUDED.projects,
                updated_at = now()
        """
        
        import json
        
        await self.db.execute(
            tags_upsert,
            item_id,                    # item_id
            labels,                     # labels
            topics,                     # topics
            doc_kinds,                  # doc_kinds
            people,                     # people
            orgs,                       # orgs
            places,                     # places
            invoice_no,                 # invoice_no
            amount_currency,            # amount_currency
            amount_total,               # amount_total
            amount_account_balance,     # amount_account_balance
            due_date_parsed,            # due_date
            period,                     # period
            summary,                    # summary
            json.dumps(tags_raw),       # tags_raw as JSON string
            signals,                    # signals
            projects                    # projects
        )


@router.post("/gmail", response_model=IngestionResponse)
async def ingest_gmail(
    data: Any = Body(...),
    current_user_id: int = Depends(get_current_user_id)
):
    """
    Ingest Gmail emails into the system.
    
    Accepts either a single email object or a batch with 'items' array.
    """
    
    
    # Extract emails from input data (handle all formats)
    emails = []
    
    try:
        if isinstance(data, dict):
            # Check if it's a batch format: {"items": [...]}
            if "items" in data:
                emails = [EmailData(**email) for email in data["items"]]
            else:
                # Single email format
                emails = [EmailData(**data)]
        elif isinstance(data, list) and len(data) > 0:
            # N8N array format: [{"items": [...]}]
            first_item = data[0]
            
            if isinstance(first_item, dict) and "items" in first_item:
                # Standard batch format: [{"items": [...]}]
                emails = [EmailData(**email) for email in first_item["items"]]
            elif isinstance(first_item, dict) and "gmail_id" in first_item:
                # Direct email array: [email1, email2, ...]
                emails = [EmailData(**email) for email in data]
            else:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Invalid array format. Expected either [{'items': [...]}] or direct email array"
                )
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid data format"
            )
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to parse email data: {str(e)}"
        )
    
    if not emails:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No emails provided for ingestion"
        )
    
    # Get database connection
    db = await get_db_connection()
    
    try:
        processor = EmailProcessor(db)
        
        # Initialize response counters
        response = IngestionResponse(
            ok=True,
            processed=0,
            inserted_items=0,
            updated_items=0,
            inserted_chunks=0,
            skipped_embedding=0,
            item_ids=[]
        )
        
        # Process each email
        for email in emails:
            try:
                # Normalize email data
                normalized_data = processor.normalize_email(email)
                
                # Upsert email to database
                upsert_result = await processor.upsert_email(normalized_data)
                
                item_id = upsert_result["item_id"]
                response.item_ids.append(item_id)
                
                if upsert_result["skip_embedding"]:
                    response.skipped_embedding += 1
                else:
                    if upsert_result["is_update"]:
                        response.updated_items += 1
                    else:
                        response.inserted_items += 1
                    
                    # Create and process chunks
                    chunks = processor.create_chunks(
                        email.subject, 
                        normalized_data["cleaned_body"]
                    )
                    
                    if chunks:
                        inserted_chunks = await processor.process_chunks(item_id, chunks)
                        response.inserted_chunks += inserted_chunks
                
                # Process tags and labels
                await processor.process_tags(item_id, email)
                
                response.processed += 1
                
            except Exception as e:
                error_msg = f"Failed to process email {email.gmail_id}: {str(e)}"
                response.errors.append(error_msg)
                print(error_msg)  # Log error
                continue
        
        # Set ok=False if there were any errors
        if response.errors:
            response.ok = len(response.errors) < len(emails)
        
        return response
    
    finally:
        await db.close()
