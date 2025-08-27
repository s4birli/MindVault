# Agent Framework - Step 1 Implementation (Enhanced)

This document describes the newly added Agent Framework to MindVault, focusing on the search agent functionality with LLM-based intent detection and robust parameter handling.

## What was added

### 1. Agent Registry (`api/agents/registry.py`)
- Minimal agent registry with global `REGISTRY` dict
- `register(name: str, fn: Callable)` - Register an agent function
- `get(name: str) -> Callable | None` - Get an agent function by name
- `list_agents()` - Get all registered agents

### 2. Search Agents

#### 2.1. Latest From Agent (`api/agents/search_local.py`)
- Implements `search.latest_from` agent
- **Function signature:** `def run(params: dict) -> dict`
- **Accepted params:**
  - `sender` (optional): Filter by sender name (ILIKE search in metadata and content)
  - `domain` (optional): Filter by domain (LIKE search in source_url or metadata)
  - `limit` (optional): Max results (default 5, capped at 50)
  - `date_from`/`date_to` (optional): ISO datetime filters
  - `language` (optional): Language for text search config ("tr" or "en")
- **Returns:** `{"items": [{"id": str, "title": str|null, "ts": iso8601|null, "provider": str|null, "url": str|null}]}`

#### 2.2. General Search Agent (`api/agents/search_find.py`)
- Implements `search.find` agent
- **Function signature:** `def run(params: dict) -> dict`
- **Accepted params:**
  - `keywords` (optional): List of search terms/phrases
  - `query` (optional): Single query string (alternative to keywords)
  - `limit` (optional): Max results (default 10, capped at 200)
  - `offset` (optional): Pagination offset (default 0)
  - `tags` (optional): Hard filter tags (AND ANY)
  - `boost_tags` (optional): Soft boost tags (scoring boost only)
  - `date_from`/`date_to` (optional): ISO datetime filters
  - `language` (optional): Language for text search config
  - `decay_days` (optional): Time decay window (default 7, max 30)
  - `highlight` (optional): Enable highlighting (default false)
- **Returns:** `{"items": [...], "total": int, "has_more": bool, "next_offset": int|null}`
- **Features:**
  - Hybrid search (BM25 + vector similarity)
  - Tag-based filtering and boosting
  - Time decay scoring
  - Deduplication
  - Pagination support
  - Highlighting support

Both agents use existing DB connection pattern and automatically register themselves at module import time.

### 3. Agent Router (`api/routers/agent.py`)
- FastAPI router with prefix="/agent", tags=["agent"]
- **POST /agent/act** endpoint
- **Input model:**
  ```json
  {
    "text": "string (required)",
    "thread_id": "string (optional)",
    "confirm": "boolean (optional)",
    "params": "object (optional)"
  }
  ```
- **Rule-based intent detection:**
  - If text contains both "hmrc" and "email" (case-insensitive):
    - intent = "search.latest_from"
    - default params = `{"sender":"hmrc", "domain":"hmrc.gov.uk", "limit": 1}`
    - User params override defaults via shallow merge
  - Else: returns fallback message
- **Response model:**
  ```json
  {
    "intent": "string|null",
    "params_used": "object|null", 
    "result": "object|null"
  }
  ```

### 4. Integration
- Agent router wired into main FastAPI app (`api/main.py`)
- Existing `/search` and `/ask` endpoints remain unchanged
- New `/agent` endpoint added to root endpoint list

### 5. Tests (`tests/test_agent_search.py`)
- Comprehensive pytest test cases
- Tests HMRC email intent detection
- Tests custom parameter merging
- Tests fallback for unrecognized queries
- Tests response structure validation
- Non-brittle tests (only check structure/types, not specific DB content)

## Manual Testing Commands

### Test 1: HMRC email search (default params)
```bash
curl -s http://localhost:8000/agent/act -H "Content-Type: application/json" \
  -d '{"text":"latest email from HMRC"}'
```

**Expected response structure:**
```json
{
  "intent": "search.latest_from",
  "params_used": {
    "sender": "hmrc",
    "domain": "hmrc.gov.uk", 
    "limit": 1
  },
  "result": {
    "items": [...]
  }
}
```

### Test 2: HMRC email search with custom limit
```bash
curl -s http://localhost:8000/agent/act -H "Content-Type: application/json" \
  -d '{"text":"show me hmrc email", "params":{"limit":3}}'
```

**Expected:** Same as Test 1 but with `"limit": 3` in params_used.

### Test 3: General search (search.find)
```bash
curl -s http://localhost:8000/agent/act -H "Content-Type: application/json" \
  -d '{"text":"proje raporu ara"}'
```

**Expected response:**
```json
{
  "intent": "search.find",
  "params_used": {
    "keywords": ["proje", "raporu"],
    "language": "tr",
    "limit": 5
  },
  "result": {
    "items": [...],
    "total": 1807,
    "has_more": true,
    "next_offset": 5
  }
}
```

### Test 4: English keyword search
```bash
curl -s http://localhost:8000/agent/act -H "Content-Type: application/json" \
  -d '{"text":"search for meeting notes about quarterly review"}'
```

**Expected response:**
```json
{
  "intent": "search.find", 
  "params_used": {
    "keywords": ["meeting", "notes", "quarterly", "review"],
    "language": "en",
    "limit": 5
  },
  "result": {
    "items": [...],
    "total": 1804,
    "has_more": true
  }
}
```

### Test 5: Unrecognized query (fallback)
```bash
curl -s http://localhost:8000/agent/act -H "Content-Type: application/json" \
  -d '{"text":"nonsense query"}'
```

**Expected response:**
```json
{
  "intent": null,
  "params_used": null,
  "result": {
    "message": "No matching agent in this step."
  }
}
```

## Architecture Notes

### Extensibility
- New agents can be added by:
  1. Creating new agent files in `api/agents/`
  2. Implementing `run(params: dict) -> dict` function
  3. Calling `register("agent.name", run)` at module import
  4. Adding intent detection rules to `_detect_intent_and_params()` in agent router

### Database Connection
- Follows existing MindVault pattern using psycopg2
- Uses `DATABASE_URL` environment variable
- Proper error handling with structured error responses

### Error Handling
- Database errors return structured error responses
- HTTP 500 for unexpected agent execution errors
- Graceful fallback for unrecognized intents

## Running Tests

```bash
# Run the agent framework tests
pytest tests/test_agent_search.py -v

# Run structure validation
python validate_simple.py
```

## Future Extensions

The framework is designed to easily accommodate new agents such as:
- `email.send` - Send emails
- `todo.add` - Add todo items  
- `calendar.create` - Create calendar events
- etc.

Each agent just needs to implement the `run(params: dict) -> dict` interface and register itself.
