# api/agents/intent_llm.py
"""
LLM-based generic intent detection module.
"""
import os
import json
from typing import Dict, Any, Optional, List
import re

# OpenAI client
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
if OPENAI_API_KEY:
    try:
        from openai import OpenAI
        oai = OpenAI(api_key=OPENAI_API_KEY)
        INTENT_MODEL = os.getenv("INTENT_MODEL", "gpt-4o-mini")
    except Exception:
        oai = None
else:
    oai = None


def extract_intent_and_params(text: str, available_agents: List[str] = None) -> Dict[str, Any]:
    """
    Extract intent and parameters from natural language text using LLM.
    
    Args:
        text: User input text in any language
        available_agents: List of available agent names
        
    Returns:
        Dictionary with intent, params, and confidence
    """
    if not oai:
        return _fallback_intent_detection(text)
    
    if not available_agents:
        available_agents = ["search.latest_from", "email.send", "calendar.create", "todo.add"]
    
    # Create the prompt for intent detection
    prompt = _build_intent_prompt(text, available_agents)
    
    try:
        response = oai.chat.completions.create(
            model=INTENT_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert intent detection system. Always respond with valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"}  # JSON guarantee
        )
        
        result_text = response.choices[0].message.content.strip()
        
        # Parse JSON response
        try:
            result = json.loads(result_text)
            return _validate_and_normalize_result(result, available_agents)
        except json.JSONDecodeError:
            # Try to extract JSON from response if it's wrapped in markdown
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if json_match:
                result = json.loads(json_match.group(1))
                return _validate_and_normalize_result(result, available_agents)
            else:
                return {"intent": None, "params": {}, "confidence": 0.0, "error": "Invalid JSON response"}
                
    except Exception as e:
        return {"intent": None, "params": {}, "confidence": 0.0, "error": f"LLM error: {str(e)}"}


def _build_intent_prompt(text: str, available_agents: List[str]) -> str:
    """Build the LLM prompt for intent detection."""
    
    agent_descriptions = {
        "search.latest_from": "Search for documents/emails from specific senders or domains",
        "email.send": "Send email messages", 
        "calendar.create": "Create calendar events or meetings",
        "todo.add": "Add tasks or todo items"
    }
    
    agents_info = []
    for agent in available_agents:
        desc = agent_descriptions.get(agent, "Generic agent")
        agents_info.append(f"- {agent}: {desc}")
    
    return f"""
Analyze this user input and extract the intent and parameters.

User Input: "{text}"

Available Agents:
{chr(10).join(agents_info)}

Extract:
1. Intent: Which agent should handle this? (or null if none match)
2. Parameters: What specific parameters can you extract?
3. Confidence: How confident are you (0.0-1.0)?

For search.latest_from agent, extract:
- sender: person/organization name (lowercase)
- domain: email domain if mentioned (without @)
- limit: number of results (default 5, max 50)
- date_window_days: if "last N days/weeks" mentioned (convert weeks to days)
- language: "tr" for Turkish, "en" for English (auto-detect)
- keywords: array of search terms (for future use)

For email.send agent, extract:
- to: recipient email/name
- subject: email subject
- body: email content

For calendar.create agent, extract:
- title: event title
- date: event date/time
- duration: event duration

For todo.add agent, extract:
- task: task description
- priority: priority level
- due_date: due date if mentioned

Examples:
- "Michael'dan gelen son 2 mailler" → search.latest_from, sender="michael", limit=2, language="tr"
- "latest emails from john@company.com" → search.latest_from, sender="john", domain="company.com", language="en"
- "HMRC'den gelen en son email neydi?" → search.latest_from, sender="hmrc", limit=1, language="tr"
- "latest email from wearedjr.com" → search.latest_from, domain="wearedjr.com", limit=1, language="en"
- "son 3 günde gelen mailler" → search.latest_from, date_window_days=3, language="tr"
- "send email to ali about meeting" → email.send, to="ali", subject="meeting"
- "create meeting tomorrow 2pm" → calendar.create, title="meeting", date="tomorrow 2pm"

Respond ONLY with valid JSON:
{{
    "intent": "agent_name_or_null",
    "params": {{"key": "value"}},
    "confidence": 0.9,
    "reason": "brief explanation of intent detection"
}}
"""


def _validate_and_normalize_result(result: Dict[str, Any], available_agents: List[str]) -> Dict[str, Any]:
    """Validate and normalize the LLM result with extended parameter schema."""
    
    # Ensure required fields exist
    if "intent" not in result:
        result["intent"] = None
    if "params" not in result:
        result["params"] = {}
    if "confidence" not in result:
        result["confidence"] = 0.5
    if "reason" not in result:
        result["reason"] = "No reason provided"
    
    # Whitelist control: intent must be in available_agents or None
    intent = result["intent"]
    if intent and intent not in available_agents:
        result["intent"] = None
        result["confidence"] = 0.0
    
    # Normalize confidence
    confidence = float(result.get("confidence", 0.5))
    result["confidence"] = max(0.0, min(1.0, confidence))
    
    # Normalize and validate parameters
    params = result["params"]
    normalized_params = {}
    
    # sender?: str (lowercase normalize)
    if "sender" in params and params["sender"]:
        normalized_params["sender"] = str(params["sender"]).lower().strip()
    
    # domain?: str (remove leading @, lowercase)
    if "domain" in params and params["domain"]:
        domain = str(params["domain"]).lower().strip()
        if domain.startswith("@"):
            domain = domain[1:]
        normalized_params["domain"] = domain
    
    # limit?: int (default 5, 1..50 clamp)
    if "limit" in params:
        try:
            limit = int(params["limit"])
            normalized_params["limit"] = max(1, min(50, limit))
        except (ValueError, TypeError):
            normalized_params["limit"] = 5
    else:
        normalized_params["limit"] = 5
    
    # date_window_days?: int (e.g., "son 3 gün" → 3)
    if "date_window_days" in params:
        try:
            days = int(params["date_window_days"])
            normalized_params["date_window_days"] = max(1, min(365, days))
        except (ValueError, TypeError):
            pass
    
    # language: "tr" | "en" (auto detect from text)
    if "language" in params and params["language"] in ["tr", "en"]:
        normalized_params["language"] = params["language"]
    
    # keywords?: string[] (for future search.find)
    if "keywords" in params and isinstance(params["keywords"], list):
        keywords = [str(kw).strip() for kw in params["keywords"] if str(kw).strip()]
        if keywords:
            normalized_params["keywords"] = keywords
    
    result["params"] = normalized_params
    return result


def _fallback_intent_detection(text: str) -> Dict[str, Any]:
    """
    Fallback intent detection when LLM is not available.
    Simple keyword-based approach.
    """
    text_lower = text.lower()
    
    # Email/search keywords
    email_keywords = ["email", "emailleri", "e-mail", "posta", "mesaj", "mailler", "mail", "mails"]
    sender_patterns = [
        r"(\w+)'dan\s+gelen",  # Turkish: "Michael'dan gelen"
        r"(\w+)'den\s+gelen",  # Turkish: "Ali'den gelen" 
        r"from\s+(\w+)",       # English: "from Michael"
        r"(\w+)\s+email",      # English: "Michael email"
        r"(\w+)\s+(?:emailleri|mailler)",  # Turkish: "Michael emailleri/mailler"
    ]
    
    if any(keyword in text_lower for keyword in email_keywords):
        # Try to extract sender
        sender = None
        for pattern in sender_patterns:
            match = re.search(pattern, text_lower)
            if match:
                sender = match.group(1).lower()
                break
        
        if sender:
            # Try to extract limit
            limit = 5
            limit_patterns = [
                r"son\s+(\d+)",     # Turkish: "son 2"
                r"last\s+(\d+)",    # English: "last 3"
                r"(\d+)\s+tane",    # Turkish: "2 tane"
            ]
            for limit_pattern in limit_patterns:
                limit_match = re.search(limit_pattern, text_lower)
                if limit_match:
                    limit = min(50, max(1, int(limit_match.group(1))))
                    break
            
            return {
                "intent": "search.latest_from",
                "params": {"sender": sender, "limit": limit},
                "confidence": 0.7
            }
    
    # No intent detected
    return {
        "intent": None,
        "params": {},
        "confidence": 0.0
    }
