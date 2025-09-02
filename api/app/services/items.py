"""Service layer for items operations."""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import text


async def check_item_exists(
    session: AsyncSession,
    source_type: str,
    origin_source: Optional[str] = None,
    external_id: Optional[str] = None
) -> Optional[int]:
    """
    Check if an item exists in the database with flexible parameters.
    
    Args:
        session: Database session
        source_type: Type of source (e.g., 'email', 'doc', 'image', 'voice', 'note', 'web')
        origin_source: Origin source identifier (optional) - e.g., 'gmail:sabirli31@gmail.com', 'localfs'
        external_id: External identifier (optional) - e.g., message_id, file_path, etc.
        
    Returns:
        item_id if found, None otherwise
    """
    # Build dynamic query based on provided parameters
    conditions = ["i.source_type = :source_type", "i.deleted_at IS NULL"]
    params = {"source_type": source_type}
    
    # Add origin_source condition if provided
    if origin_source:
        conditions.append("i.origin_source = :origin_source")
        params["origin_source"] = origin_source
    
    # Add external_id condition if provided
    if external_id:
        if source_type == "email":
            # For emails, search both origin_id and message_id
            conditions.append("(i.origin_id = :external_id OR e.message_id = :external_id)")
            params["external_id"] = external_id
        else:
            # For other types, search only origin_id
            conditions.append("i.origin_id = :external_id")
            params["external_id"] = external_id
    
    # Build the query
    if source_type == "email" and external_id:
        # For emails with external_id, join with emails table
        query = text(f"""
            SELECT i.item_id 
            FROM items i
            LEFT JOIN emails e ON i.item_id = e.item_id
            WHERE {' AND '.join(conditions)}
            LIMIT 1
        """)
    else:
        # For other cases, simple items table query
        query = text(f"""
            SELECT i.item_id 
            FROM items i
            WHERE {' AND '.join(conditions)}
            LIMIT 1
        """)
    
    result = await session.execute(query, params)
    
    row = result.fetchone()
    return row[0] if row else None
