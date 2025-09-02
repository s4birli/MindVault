"""Items router with external item existence check."""

from typing import Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, status, Response
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from ..core.db import get_session
from ..core.security_jwt import require_jwt
from ..services.items import check_item_exists

router = APIRouter()

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@router.get("/external")
async def check_external_item(
    source_type: str,
    origin_source: Optional[str] = None,
    external_id: Optional[str] = None,
    session: AsyncSession = Depends(get_session),
    jwt_claims: Dict[str, Any] = Depends(require_jwt)
):
    """
    Check if an external item exists.
    
    Query Parameters:
        source_type: Type of source (required) - 'email', 'doc', 'image', 'voice', 'note', 'web'
        origin_source: Origin source identifier (optional) - e.g., 'gmail:sabirli31@gmail.com', 'localfs'
        external_id: External identifier (optional) - e.g., message_id, file_path, etc.
        
    Returns:
        200: Item exists (empty body)
        404: Item not found or unsupported source_type (empty body)
        401: Authentication failed
    """
    logger.info(f"Checking item: source_type='{source_type}', origin_source='{origin_source}', external_id='{external_id}'")
    
    # Validate source_type
    valid_source_types = ['email', 'doc', 'image', 'voice', 'note', 'web']
    if source_type not in valid_source_types:
        logger.warning(f"Unsupported source_type: {source_type}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unsupported source_type. Must be one of: {', '.join(valid_source_types)}"
        )
    
    # Check if item exists with flexible parameters
    logger.info(f"Querying database for source_type='{source_type}' with origin_source='{origin_source}', external_id='{external_id}'")
    item_id = await check_item_exists(session, source_type, origin_source, external_id)
    logger.info(f"Database query result: item_id={item_id}")
    
    if item_id is None:
        logger.info("Item not found, returning 404")
        return Response(
            status_code=status.HTTP_404_NOT_FOUND,
            content=f'{{"external_id": "{external_id}", "found": false}}',
            media_type="application/json"
        )
    
    logger.info(f"Item found with id={item_id}, returning 200")
    # Return 200 with external_id in body
    return Response(
        status_code=status.HTTP_200_OK,
        content=f'{{"external_id": "{external_id}", "found": true, "item_id": {item_id}}}',
        media_type="application/json"
    )