# MindVault Minimal API

A minimal FastAPI service that provides secure access to check external item existence with JWT authentication.

## Features

- **Single Endpoint**: `HEAD /items/external` - Check if Gmail messages exist in the database
- **JWT Authentication**: HS256 bearer token validation
- **Async Database**: PostgreSQL with SQLAlchemy 2 async engine
- **Production Ready**: Environment-based configuration, Docker support

## Quick Start

### 1. Environment Setup

Copy the example environment file and configure it:

```bash
cp .env.example .env
```

Edit `.env` and set your values:
- `JWT_SECRET`: A strong secret key for JWT signing
- `DATABASE_URL`: Your PostgreSQL connection string
- Other optional JWT settings (issuer, audience, etc.)

### 2. Install Dependencies

```bash
# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

### 3. Run the API

```bash
python3 -m app.main
```

The API will start on `http://localhost:8000`

## API Documentation

### Authentication

All endpoints require a valid JWT Bearer token in the Authorization header:

```
Authorization: Bearer <your-jwt-token>
```

### Endpoints

#### `HEAD /items/external`

Check if an external item exists in the database.

**Query Parameters:**
- `source` (required): Source system. Currently only `"gmail"` is supported.
- `external_id` (required): External identifier (e.g., Gmail message ID).

**Responses:**
- `200`: Item exists (empty body)
- `401`: Authentication failed (missing/invalid/expired token)
- `404`: Item not found or unsupported source
- `500`: Server error

**Example:**
```bash
curl -I -H "Authorization: Bearer <token>" \
  "http://localhost:8000/items/external?source=gmail&external_id=message123"
```

#### `GET /health`

Health check endpoint (no authentication required).

**Response:**
```json
{"status": "healthy"}
```

## Testing

### 1. Generate Test JWT Token

```python
import jwt
from datetime import datetime, timedelta

secret = "your-super-secret-jwt-signing-key-change-this-in-production"
payload = {
    'iss': 'mindvault-api',
    'aud': 'mindvault-client', 
    'exp': datetime.utcnow() + timedelta(hours=1),
    'iat': datetime.utcnow(),
    'sub': 'test-user'
}

token = jwt.encode(payload, secret, algorithm='HS256')
print(token)
```

### 2. Test the API

```bash
# Test health endpoint
curl http://localhost:8000/health

# Test without authentication (should return 403)
curl -I "http://localhost:8000/items/external?source=gmail&external_id=test123"

# Test with valid JWT (should return 404 if item doesn't exist)
curl -I -H "Authorization: Bearer <your-token>" \
  "http://localhost:8000/items/external?source=gmail&external_id=test123"

# Test with unsupported source (should return 404)
curl -I -H "Authorization: Bearer <your-token>" \
  "http://localhost:8000/items/external?source=dropbox&external_id=test123"
```

## Docker Deployment

### Build and Run

```bash
# Build the image
docker build -t mindvault-api .

# Run the container
docker run -p 8000:8000 \
  -e JWT_SECRET="your-secret" \
  -e DATABASE_URL="postgresql+asyncpg://user:pass@host:5432/db" \
  mindvault-api
```

### Docker Compose

The API is designed to work with the existing MindVault docker-compose setup. Update your `docker-compose.yml` to use the new API service.

## Database Schema

The API expects the following database structure:

```sql
-- Items table (from existing schema)
CREATE TABLE items (
    item_id BIGSERIAL PRIMARY KEY,
    source_type TEXT NOT NULL,
    origin_source TEXT,
    origin_id TEXT,
    deleted_at TIMESTAMPTZ,
    -- other columns...
);

-- Index for performance
CREATE INDEX idx_items_lookup ON items(source_type, origin_source, origin_id)
WHERE deleted_at IS NULL;
```

The API queries for:
- `source_type = 'email'`
- `origin_source = 'gmail'` (for Gmail messages)
- `origin_id = <external_id>` (the message ID)
- `deleted_at IS NULL` (active items only)

## Security

- **JWT Validation**: Tokens are validated for signature, expiration, issuer, and audience
- **Environment Secrets**: All secrets loaded from environment variables
- **No Data Exposure**: HEAD endpoint returns no data, only existence status
- **CORS**: Currently permissive for development (should be restricted in production)

## Configuration

All configuration is done via environment variables:

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `API_HOST` | Server host | `0.0.0.0` | No |
| `API_PORT` | Server port | `8000` | No |
| `DATABASE_URL` | PostgreSQL connection string | Docker network default | No |
| `JWT_SECRET` | JWT signing secret | None | **Yes** |
| `JWT_ALG` | JWT algorithm | `HS256` | No |
| `JWT_ISS` | JWT issuer claim | None | No |
| `JWT_AUD` | JWT audience claim | None | No |
| `JWT_LEEWAY_SEC` | JWT expiration leeway | `60` | No |

## Architecture

```
app/
├── core/
│   ├── config.py      # Environment configuration
│   ├── db.py          # Database session management
│   └── security_jwt.py # JWT authentication
├── routers/
│   └── items.py       # API endpoints
├── services/
│   └── items.py       # Business logic
└── main.py           # FastAPI application
```

## Limitations

- Only supports Gmail (`source=gmail`) currently
- Single endpoint implementation
- No logging framework (can be added later)
- No rate limiting (can be added later)
- Permissive CORS (should be restricted for production)

## Future Enhancements

- Add support for other sources (Dropbox, local files, etc.)
- Implement additional CRUD endpoints
- Add structured logging
- Add rate limiting and request validation
- Add health checks with database connectivity
- Add metrics and monitoring endpoints
