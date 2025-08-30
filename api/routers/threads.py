# api/routers/threads.py
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import os
import psycopg2
import json
from datetime import datetime
import uuid

router = APIRouter(prefix="/threads", tags=["threads"])
PG_DSN = os.getenv(
    "DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/mindvault")

# ---- Request/Response Models ----

class MessageModel(BaseModel):
    id: str
    threadId: str = Field(alias="thread_id")
    content: str
    type: str  # 'user' | 'assistant'
    timestamp: datetime
    attachments: Optional[List[Dict[str, Any]]] = None
    sources: Optional[List[Dict[str, Any]]] = None

class ThreadModel(BaseModel):
    id: str
    title: str
    createdAt: datetime = Field(alias="created_at")
    updatedAt: datetime = Field(alias="updated_at")
    messages: List[MessageModel] = []

class CreateThreadRequest(BaseModel):
    title: Optional[str] = "New Chat"

class UpdateThreadRequest(BaseModel):
    title: Optional[str] = None

class AddMessageRequest(BaseModel):
    content: str
    type: str
    attachments: Optional[List[Dict[str, Any]]] = None
    sources: Optional[List[Dict[str, Any]]] = None

# ---- Database Helpers ----

def _connect():
    return psycopg2.connect(PG_DSN)

def _init_tables():
    """Initialize thread and message tables if they don't exist"""
    with _connect() as conn, conn.cursor() as cur:
        # Create threads table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_threads (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                title TEXT NOT NULL,
                created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()
            )
        """)
        
        # Create messages table
        cur.execute("""
            CREATE TABLE IF NOT EXISTS chat_messages (
                id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                thread_id UUID REFERENCES chat_threads(id) ON DELETE CASCADE,
                content TEXT NOT NULL,
                type TEXT NOT NULL,
                timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
                attachments JSONB,
                sources JSONB
            )
        """)
        
        # Create index for better performance
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_thread_id 
            ON chat_messages(thread_id)
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_messages_timestamp 
            ON chat_messages(timestamp DESC)
        """)
        
        conn.commit()

# Initialize tables on startup
try:
    _init_tables()
except Exception as e:
    print(f"Warning: Could not initialize thread tables: {e}")

# ---- API Endpoints ----

@router.get("", response_model=List[ThreadModel])
def get_threads():
    """Get all threads ordered by most recent"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            # Get threads with message counts
            cur.execute("""
                SELECT t.id, t.title, t.created_at, t.updated_at,
                       COALESCE(m.message_count, 0) as message_count
                FROM chat_threads t
                LEFT JOIN (
                    SELECT thread_id, COUNT(*) as message_count
                    FROM chat_messages
                    GROUP BY thread_id
                ) m ON t.id = m.thread_id
                ORDER BY t.updated_at DESC
            """)
            
            threads = []
            for row in cur.fetchall():
                thread_id, title, created_at, updated_at, message_count = row
                
                # Get messages for this thread
                cur.execute("""
                    SELECT id, content, type, timestamp, attachments, sources
                    FROM chat_messages
                    WHERE thread_id = %s
                    ORDER BY timestamp ASC
                """, (thread_id,))
                
                messages = []
                for msg_row in cur.fetchall():
                    msg_id, content, msg_type, timestamp, attachments, sources = msg_row
                    messages.append(MessageModel(
                        id=str(msg_id),
                        thread_id=str(thread_id),
                        content=content,
                        type=msg_type,
                        timestamp=timestamp,
                        attachments=attachments,
                        sources=sources
                    ))
                
                threads.append(ThreadModel(
                    id=str(thread_id),
                    title=title,
                    created_at=created_at,
                    updated_at=updated_at,
                    messages=messages
                ))
            
            return threads
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.post("", response_model=ThreadModel)
def create_thread(request: CreateThreadRequest):
    """Create a new thread"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""
                INSERT INTO chat_threads (title)
                VALUES (%s)
                RETURNING id, title, created_at, updated_at
            """, (request.title,))
            
            row = cur.fetchone()
            thread_id, title, created_at, updated_at = row
            
            conn.commit()
            
            return ThreadModel(
                id=str(thread_id),
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                messages=[]
            )
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.get("/{thread_id}", response_model=ThreadModel)
def get_thread(thread_id: str):
    """Get a specific thread with its messages"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            # Get thread info
            cur.execute("""
                SELECT id, title, created_at, updated_at
                FROM chat_threads
                WHERE id = %s
            """, (thread_id,))
            
            thread_row = cur.fetchone()
            if not thread_row:
                raise HTTPException(status_code=404, detail="Thread not found")
            
            thread_id_db, title, created_at, updated_at = thread_row
            
            # Get messages
            cur.execute("""
                SELECT id, content, type, timestamp, attachments, sources
                FROM chat_messages
                WHERE thread_id = %s
                ORDER BY timestamp ASC
            """, (thread_id,))
            
            messages = []
            for msg_row in cur.fetchall():
                msg_id, content, msg_type, timestamp, attachments, sources = msg_row
                messages.append(MessageModel(
                    id=str(msg_id),
                    thread_id=str(thread_id_db),
                    content=content,
                    type=msg_type,
                    timestamp=timestamp,
                    attachments=attachments,
                    sources=sources
                ))
            
            return ThreadModel(
                id=str(thread_id_db),
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                messages=messages
            )
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.put("/{thread_id}", response_model=ThreadModel)
def update_thread(thread_id: str, request: UpdateThreadRequest):
    """Update thread title"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            updates = []
            params = []
            
            if request.title is not None:
                updates.append("title = %s")
                params.append(request.title)
            
            if not updates:
                raise HTTPException(status_code=400, detail="No updates provided")
            
            updates.append("updated_at = NOW()")
            params.append(thread_id)
            
            cur.execute(f"""
                UPDATE chat_threads
                SET {', '.join(updates)}
                WHERE id = %s
                RETURNING id, title, created_at, updated_at
            """, params)
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Thread not found")
            
            thread_id_db, title, created_at, updated_at = row
            conn.commit()
            
            # Get messages
            cur.execute("""
                SELECT id, content, type, timestamp, attachments, sources
                FROM chat_messages
                WHERE thread_id = %s
                ORDER BY timestamp ASC
            """, (thread_id,))
            
            messages = []
            for msg_row in cur.fetchall():
                msg_id, content, msg_type, timestamp, attachments, sources = msg_row
                messages.append(MessageModel(
                    id=str(msg_id),
                    thread_id=str(thread_id_db),
                    content=content,
                    type=msg_type,
                    timestamp=timestamp,
                    attachments=attachments,
                    sources=sources
                ))
            
            return ThreadModel(
                id=str(thread_id_db),
                title=title,
                created_at=created_at,
                updated_at=updated_at,
                messages=messages
            )
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.delete("/{thread_id}")
def delete_thread(thread_id: str):
    """Delete a thread and all its messages"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            cur.execute("""
                DELETE FROM chat_threads
                WHERE id = %s
                RETURNING id
            """, (thread_id,))
            
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="Thread not found")
            
            conn.commit()
            return {"message": "Thread deleted successfully"}
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")

@router.post("/{thread_id}/messages", response_model=MessageModel)
def add_message(thread_id: str, request: AddMessageRequest):
    """Add a message to a thread"""
    try:
        with _connect() as conn, conn.cursor() as cur:
            # Check if thread exists
            cur.execute("SELECT id FROM chat_threads WHERE id = %s", (thread_id,))
            if not cur.fetchone():
                raise HTTPException(status_code=404, detail="Thread not found")
            
            # Insert message
            cur.execute("""
                INSERT INTO chat_messages (thread_id, content, type, attachments, sources)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id, timestamp
            """, (
                thread_id,
                request.content,
                request.type,
                json.dumps(request.attachments) if request.attachments else None,
                json.dumps(request.sources) if request.sources else None
            ))
            
            msg_id, timestamp = cur.fetchone()
            
            # Update thread's updated_at
            cur.execute("""
                UPDATE chat_threads
                SET updated_at = NOW()
                WHERE id = %s
            """, (thread_id,))
            
            # Auto-generate title from first user message if title is still default
            if request.type == 'user':
                cur.execute("""
                    UPDATE chat_threads
                    SET title = %s
                    WHERE id = %s AND title = 'New Chat'
                """, (
                    request.content[:47] + '...' if len(request.content) > 50 else request.content,
                    thread_id
                ))
            
            conn.commit()
            
            return MessageModel(
                id=str(msg_id),
                thread_id=thread_id,
                content=request.content,
                type=request.type,
                timestamp=timestamp,
                attachments=request.attachments,
                sources=request.sources
            )
            
    except psycopg2.Error as e:
        raise HTTPException(status_code=500, detail=f"Database error: {e}")
