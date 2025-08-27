# api/agents/intent_llm.py
"""
LLM-based generic intent detection module for MindVault Agent Framework.

- Prefers `search.find` when BOTH a sender and a topic/keywords are present
  (e.g., "Bruce'a fare ile ilgili mail neydi?").
- Falls back to `search.latest_from` when only sender/domain is present.
- When LLM is unavailable, uses lightweight multilingual regex heuristics.

This module returns a dict:
{
  "intent": "agent.name" | None,
  "params": {...},
  "confidence": float (0..1),
  "reason": "optional brief string",
  "error": "optional string on error"
}
"""
import os
import json
import re
from typing import Dict, Any, List, Optional

# OpenAI client (optional)
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


def extract_intent_and_params(text: str, available_agents: Optional[List[str]] = None) -> Dict[str, Any]:
    """
    Extract intent and parameters from natural language text using LLM (if available),
    otherwise use a robust fallback.

    Args:
        text: user input (any language)
        available_agents: list of agent names allowed in this environment

    Returns:
        dict with intent/params/confidence and optional reason/error
    """
    if not available_agents:
        available_agents = [
            "search.latest_from",
            "search.find",
            "search.summarize",
            "email.send",
            "calendar.create",
            "todo.add",
        ]

    if not oai:
        return _fallback_intent_detection(text)

    prompt = _build_intent_prompt(text, available_agents)

    try:
        response = oai.chat.completions.create(
            model=INTENT_MODEL,
            messages=[
                {"role": "system", "content": "You are an expert intent detection system. Always respond with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"},  # ask for strict JSON
        )

        result_text = response.choices[0].message.content.strip()
        try:
            result = json.loads(result_text)
        except json.JSONDecodeError:
            # Try to extract JSON inside a fenced block
            json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', result_text, re.DOTALL)
            if not json_match:
                return {"intent": None, "params": {}, "confidence": 0.0, "error": "Invalid JSON response"}
            result = json.loads(json_match.group(1))

        return _validate_and_normalize_result(result, available_agents)

    except Exception as e:
        return {"intent": None, "params": {}, "confidence": 0.0, "error": f"LLM error: {str(e)}"}


def _build_intent_prompt(text: str, available_agents: List[str]) -> str:
    """Build the LLM prompt for intent detection (multilingual-friendly)."""
    agent_descriptions = {
        "search.latest_from": "Search for latest documents/emails from specific senders or domains",
        "search.find": "General hybrid search with keywords, tag boost, decay, and filters",
        "search.summarize": "Summarize a set of documents/IDs into a short brief with source references",
        "email.send": "Send email messages",
        "calendar.create": "Create calendar events or meetings",
        "todo.add": "Add tasks or todo items",
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
1) intent: Which agent should handle this? (or null if none match)
2) params: Concrete parameters for that agent
3) confidence: 0.0–1.0
4) reason: brief explanation

For search.latest_from, extract:
- sender: person/organization (lowercase if possible)
- domain: email domain if mentioned (no leading @)
- limit: number of results (default 5, max 50)
- date_window_days: if "last N days/weeks" mentioned (convert weeks to days)
- language: "tr" or "en" (auto-detect)

For search.find, extract:
- sender: optional sender (lowercase)
- query: single string OR
- keywords: array of search terms/phrases
- limit: default 10 (max 200)
- offset: default 0
- tags: required tags (hard filter)
- boost_tags: boost-only tags
- date_window_days: if "last N days/weeks" mentioned
- language: "tr" or "en"
- decay_days: time-decay window (default 7, max 30)
- highlight: boolean

For search.summarize, extract:
- doc_ids: array of document IDs to summarize (required)
- language: "tr" or "en" (auto-detect)
- summary_type: "brief", "detailed", or "bullet_points" (default "brief")
- max_docs: maximum documents to process (default 10, max 20)

Decision rule:
- If the input contains BOTH a sender/person/organization (e.g., "Bruce", "HMRC", "THY") AND a topic/keywords
  (e.g., "fare", "section 21", "uçuş", "pnr"), then choose **search.find** (NOT search.latest_from).
- Choose **search.latest_from** only when there is a sender/domain but NO explicit topic/keywords.

Examples:
- "Michael'dan gelen son 2 mailler" → search.latest_from, sender="michael", limit=2, language="tr"
- "latest emails from john@company.com" → search.latest_from, sender="john", domain="company.com", language="en"
- "HMRC'den gelen en son email neydi?" → search.latest_from, sender="hmrc", limit=1, language="tr"
- "latest email from wearedjr.com" → search.latest_from, domain="wearedjr.com", limit=1, language="en"
- "Bruce'a fare ile ilgili mail neydi?" → search.find, sender="bruce", keywords=["fare"], limit=5, language="tr"
- "proje raporu ara" → search.find, keywords=["proje", "raporu"], language="tr"
- "search for meeting notes about quarterly review" → search.find, keywords=["meeting","notes","quarterly","review"], language="en"
- "son 3 günde gelen belgeler" → search.find, date_window_days=3, language="tr"
- "find documents tagged with important" → search.find, tags=["important"], language="en"
- "bu belgeleri özetle" → search.summarize, doc_ids=["id1","id2"], language="tr"
- "summarize these documents briefly" → search.summarize, doc_ids=["id1","id2"], summary_type="brief", language="en"
- "send email to ali about meeting" → email.send, to="ali", subject="meeting"
- "create meeting tomorrow 2pm" → calendar.create, title="meeting", date="tomorrow 2pm"

Respond ONLY with valid JSON:
{{
  "intent": "agent_name_or_null",
  "params": {{ "key": "value" }},
  "confidence": 0.9,
  "reason": "brief explanation"
}}
"""


def _validate_and_normalize_result(result: Dict[str, Any], available_agents: List[str]) -> Dict[str, Any]:
    """Validate + normalize the LLM result. Enforce allowlist & clamp values."""
    # defaults
    intent = result.get("intent")
    params = result.get("params", {}) or {}
    confidence = float(result.get("confidence", 0.5))
    reason = result.get("reason", "No reason provided")

    # allowlist
    if intent and intent not in available_agents:
        intent = None
        confidence = 0.0

    # normalize confidence
    confidence = max(0.0, min(1.0, confidence))

    # normalize parameters
    normalized: Dict[str, Any] = {}

    # language (optional, pass through if valid)
    lang = params.get("language")
    if isinstance(lang, str) and lang.lower() in ("tr", "en"):
        normalized["language"] = lang.lower()

    # sender (lowercase)
    if "sender" in params and params["sender"]:
        normalized["sender"] = str(params["sender"]).lower().strip()

    # domain (strip leading '@', lowercase)
    if "domain" in params and params["domain"]:
        dom = str(params["domain"]).strip().lower()
        if dom.startswith("@"):
            dom = dom[1:]
        normalized["domain"] = dom

    # limit
    if "limit" in params:
        try:
            lim = int(params["limit"])
            normalized["limit"] = max(1, min(200 if intent == "search.find" else 50, lim))
        except (TypeError, ValueError):
            normalized["limit"] = 10 if intent == "search.find" else 5
    else:
        normalized["limit"] = 10 if intent == "search.find" else 5

    # offset (search.find)
    if intent == "search.find":
        try:
            off = int(params.get("offset", 0))
            normalized["offset"] = max(0, off)
        except (TypeError, ValueError):
            normalized["offset"] = 0

    # date_window_days
    if "date_window_days" in params:
        try:
            days = int(params["date_window_days"])
            normalized["date_window_days"] = max(1, min(365, days))
        except (TypeError, ValueError):
            pass

    # decay_days
    if "decay_days" in params:
        try:
            dd = int(params["decay_days"])
            normalized["decay_days"] = max(1, min(30, dd))
        except (TypeError, ValueError):
            pass

    # highlight
    if "highlight" in params:
        normalized["highlight"] = bool(params["highlight"])

    # query / keywords / tags / boost_tags (search.find)
    if intent == "search.find":
        if "query" in params and isinstance(params["query"], str) and params["query"].strip():
            normalized["query"] = params["query"].strip()
        if "keywords" in params and isinstance(params["keywords"], list):
            kws = [str(kw).strip() for kw in params["keywords"] if str(kw).strip()]
            if kws:
                normalized["keywords"] = kws
        if "tags" in params and isinstance(params["tags"], list):
            tags = [str(t).strip().lower() for t in params["tags"] if str(t).strip()]
            if tags:
                normalized["tags"] = tags
        if "boost_tags" in params and isinstance(params["boost_tags"], list):
            bts = [str(t).strip().lower() for t in params["boost_tags"] if str(t).strip()]
            if bts:
                normalized["boost_tags"] = bts

    return {
        "intent": intent,
        "params": normalized,
        "confidence": confidence,
        "reason": reason,
    }


def _fallback_intent_detection(text: str) -> Dict[str, Any]:
    """
    Fallback intent detection when LLM is not available.
    Multilingual regex:
      - If sender + topic ⇒ search.find
      - Else if sender only ⇒ search.latest_from
    """
    t = text or ""
    tlow = t.lower()

    # very light language hint
    tr_chars = set("ıİğĞşŞöÖçÇüÜ")
    language = "tr" if any(ch in tr_chars for ch in t) else "en"

    # email/search cue words
    email_keywords = ["email", "e-mail", "mail", "mailler", "emailleri", "posta", "mesaj", "mails"]

    sender_patterns = [
        r"(\w+)'dan\s+gelen",      # TR: "Michael'dan gelen"
        r"(\w+)'den\s+gelen",      # TR: "Ali'den gelen"
        r"from\s+([a-z0-9_.-]+)",  # EN: "from michael" or domain-ish
        r"([a-z0-9_.-]+)@([a-z0-9_.-]+)",  # john@company.com
        r"([a-z0-9_.-]+)\s+email", # "Michael email"
        r"([a-z0-9_.-]+)\s+(?:emailleri|mailler)",  # TR
    ]

    topic_patterns = [
        r"(?:ile\s+ilgili|hakkında|about)\s+([^\?\.]+)",  # "fare ile ilgili", "about section 21"
        r"(?:konu|topic)\s*[:：]\s*([^\?\.]+)",
    ]

    has_email_cue = any(k in tlow for k in email_keywords)

    # Try to extract sender/domain
    sender: Optional[str] = None
    domain: Optional[str] = None

    for pat in sender_patterns:
        m = re.search(pat, tlow)
        if m:
            if "@" in m.group(0) and m.lastindex and m.lastindex >= 2:
                # john@company.com
                sender = m.group(1).lower()
                domain = m.group(2).lower()
            else:
                candidate = (m.group(1) or "").lower()
                # if looks like domain
                if "." in candidate:
                    domain = candidate.lstrip("@")
                else:
                    sender = candidate
            break

    # Try to extract a topic (keywords)
    topic: Optional[str] = None
    for pat in topic_patterns:
        m = re.search(pat, tlow)
        if m:
            topic = m.group(1).strip()
            break

    # limit
    limit = 5
    for lp in [r"son\s+(\d+)", r"last\s+(\d+)", r"(\d+)\s+tane"]:
        lm = re.search(lp, tlow)
        if lm:
            try:
                limit = min(50, max(1, int(lm.group(1))))
            except Exception:
                pass
            break

    if has_email_cue or sender or domain:
        # If sender/domain + topic ⇒ search.find
        if (sender or domain) and topic:
            kws = [w.strip() for w in re.split(r"[,\s]+", topic) if w.strip()]
            params: Dict[str, Any] = {"limit": limit, "language": language}
            if sender:
                params["sender"] = sender
            if domain:
                params["domain"] = domain
            if kws:
                params["keywords"] = kws
            return {
                "intent": "search.find",
                "params": params,
                "confidence": 0.8,
                "reason": "sender+topic detected → search.find",
            }

        # If only sender/domain ⇒ search.latest_from
        if sender or domain:
            params = {"limit": limit, "language": language}
            if sender:
                params["sender"] = sender
            if domain:
                params["domain"] = domain
            return {
                "intent": "search.latest_from",
                "params": params,
                "confidence": 0.7,
                "reason": "sender/domain detected → search.latest_from",
            }

    # No intent
    return {"intent": None, "params": {}, "confidence": 0.0, "reason": "no match"}