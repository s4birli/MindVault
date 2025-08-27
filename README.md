# MindVault# MindVault 🧠🔒

Your **second brain**: a cost-first, performance-first knowledge hub.

MindVault ingests emails, calendars, Telegram chats, and notes → normalizes → indexes in Postgres+pgvector with cheap object storage → enables **hybrid search** (BM25 + vector + tags + history) and **actions** (email replies, calendar events).  
Plus: automatic export as Obsidian-ready Markdown vault to GitHub.

---

## Features
- **Ingestion (n8n):** Gmail/Hotmail, Google/Apple Calendar, Telegram (text/photo/voice)
- **Index:** Chunk + embeddings → pgvector ANN
- **Search:** hybrid rank (vector+bm25+tags+history)
- **Ask (/ask):** compress → LLM → summary + links + suggested actions
- **Actions:** Gmail reply/draft, Calendar create
- **Tags & History:** user feedback + click logs
- **Export:** GitHub repo as Obsidian vault

---

## Quickstart (dev)
```bash
# copy env
cp .env.example .env

# start stack
docker compose -f docker-compose.dev.yml up -d

# run migrations
make migrate

# smoke test
curl http://localhost:8000/health