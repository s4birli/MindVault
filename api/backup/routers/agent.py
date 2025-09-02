# api/routers/agent.py
"""
Agent router for handling agent execution requests.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Dict, Any, Optional, Tuple
import re
import logging
import time
from datetime import datetime, timedelta, timezone

# Import the agents module (this will trigger agent registration)
from ..agents import registry
from ..agents.intent_llm import extract_intent_and_params
# Import agents to ensure they are registered
from .. import agents

router = APIRouter(prefix="/agent", tags=["agent"])


class AgentRequest(BaseModel):
    text: str
    thread_id: Optional[str] = None
    confirm: Optional[bool] = None
    params: Optional[Dict[str, Any]] = None


class AgentResponse(BaseModel):
    intent: Optional[str]
    params_used: Optional[Dict[str, Any]]
    result: Optional[Dict[str, Any]]





def _detect_intent_and_params_llm(text: str, user_params: Optional[Dict[str, Any]] = None) -> Tuple[Optional[str], Optional[Dict[str, Any]], Dict[str, Any]]:
    """
    LLM-based generic intent detection.
    
    Args:
        text: User input text
        user_params: Optional user-provided parameters
    
    Returns:
        Tuple of (intent, merged_params, debug_info) or (None, None, debug_info) if no match
    """
    start_time = time.time()
    
    # Get available agents from registry
    available_agents = registry.list_agents()
    
    # Use LLM to extract intent and parameters
    result = extract_intent_and_params(text, available_agents)
    
    intent = result.get("intent")
    llm_params = result.get("params", {})
    confidence = result.get("confidence", 0.0)
    reason = result.get("reason", "")
    
    # Process date_window_days if present
    if "date_window_days" in llm_params:
        try:
            days = int(llm_params["date_window_days"])
            now_utc = datetime.now(timezone.utc)
            date_from = now_utc - timedelta(days=days)
            llm_params["date_from"] = date_from.isoformat()
            # Remove date_window_days as it's converted to date_from
            del llm_params["date_window_days"]
        except (ValueError, TypeError):
            pass
    
    elapsed_ms = round((time.time() - start_time) * 1000, 2)
    
    debug_info = {
        "confidence": confidence,
        "reason": reason,
        "elapsed_ms": elapsed_ms,
        "available_agents": available_agents
    }
    
    # If no intent detected or low confidence, return None
    if not intent or confidence < 0.3:
        return None, None, debug_info
    
    # Merge user params with LLM-extracted params (user params override)
    if user_params:
        merged_params = llm_params.copy()
        merged_params.update(user_params)
    else:
        merged_params = llm_params
    
    return intent, merged_params, debug_info


@router.post("/act", response_model=AgentResponse)
def act(request: AgentRequest):
    """
    Execute an agent based on the input text and parameters.
    
    Args:
        request: Agent request containing text, optional thread_id, confirm flag, and params
        
    Returns:
        AgentResponse with intent, params_used, and result
    """
    try:
        # Detect intent and merge parameters using LLM
        intent, params_used, debug_info = _detect_intent_and_params_llm(request.text, request.params)
        
        # Log debug info
        logging.debug(f"Agent intent detection: intent={intent}, confidence={debug_info.get('confidence')}, "
                     f"reason={debug_info.get('reason')}, elapsed_ms={debug_info.get('elapsed_ms')}")
        
        # If no intent detected, return fallback (soft error)
        if intent is None:
            logging.debug(f"No intent detected for text: {request.text}")
            return AgentResponse(
                intent=None,
                params_used=None,
                result={"message": "No matching agent in this step.", "debug": debug_info}
            )
        
        # Get agent function from registry
        agent_fn = registry.get(intent)
        if agent_fn is None:
            logging.warning(f"Agent '{intent}' not found in registry")
            return AgentResponse(
                intent=intent,
                params_used=params_used,
                result={"message": f"Agent '{intent}' not found in registry.", "debug": debug_info}
            )
        
        # Execute the agent
        agent_start = time.time()
        result = agent_fn(params_used or {})
        agent_elapsed = round((time.time() - agent_start) * 1000, 2)
        
        # Log successful execution
        logging.debug(f"Agent execution successful: intent={intent}, params={params_used}, "
                     f"agent_elapsed_ms={agent_elapsed}")
        
        return AgentResponse(
            intent=intent,
            params_used=params_used,
            result=result
        )
        
    except Exception as e:
        # Soft error handling - return 200 with error in result
        logging.error(f"Agent execution error: {str(e)}")
        return AgentResponse(
            intent=None,
            params_used=None,
            result={"error": str(e), "message": "Agent execution failed."}
        )
