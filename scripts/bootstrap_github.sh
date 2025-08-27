#!/usr/bin/env bash
set -euo pipefail
REPO="${1:-}"
PROJECT_TITLE="${2:-MindVault Plan}"
if [[ -z "$REPO" ]]; then
  echo "Usage: scripts/bootstrap_github.sh <owner/repo> [project_title]"
  exit 1
fi

echo "==> Create labels"
while read -r name color desc; do
  gh label create "$name" --color "$color" --description "$desc" 2>/dev/null || gh label edit "$name" --color "$color" --description "$desc"
done <<'EOF'
task 0e8a16 "Atomic task"
bug d73a4a "Defect"
enhancement a2eeef "Feature/Improvement"
P0 5319e7 "Foundation"
P1 5319e7 "Data layer"
P2 5319e7 "Ingestion"
P3 5319e7 "Indexing"
P4 5319e7 "Search"
P5 5319e7 "Ask/LLM"
P6 5319e7 "Actions"
P7 5319e7 "Tags/History"
P8 5319e7 "GitHub Export"
P9 5319e7 "Ops"
EOF

echo "==> Seed issues"
create_issue () {
  gh issue create -R "$REPO" -t "$1" -b "$3" -l "$2"
}
create_issue "[P0] Repo setup & docker-compose" "task,P0" "- Repo layout\n- docker-compose.dev.yml\n- .env.example\n- Makefile"
create_issue "[P1] Postgres + pgvector provisioning" "task,P1" "- Provision DB\n- Enable extensions\n- Run migrations"
create_issue "[P2] Gmail multi-account ingestion" "task,P2" "- OAuth per account\n- Poll INBOX newerThan:2d\n- Normalize → /ingest/gmail"
create_issue "[P2] Telegram intake (text/photo/voice)" "task,P2" "- Webhook trigger\n- S3 upload\n- Whisper transcript\n- /ingest/telegram"
create_issue "[P3] /index/embed (chunk+embed)" "task,P3" "- Chunk (800/12%)\n- Embeddings\n- ANN index"
create_issue "[P4] /search hybrid scorer" "task,P4" "- Vector+BM25+tag+history\n- time-decay\n- filters"
create_issue "[P5] /ask summarize-with-links" "task,P5" "- qlog/qresults\n- compression\n- LLM prompt"
create_issue "[P6] Actions: email reply & calendar" "task,P6" "- Gmail draft/send\n- Calendar create\n- action logs"
create_issue "[P7] Tags & sender memory" "task,P7" "- /tags add/remove/suggest\n- senders EMA\n- UI pills"
create_issue "[P8] GitHub Exporter (Obsidian)" "task,P8" "- MD vault structure\n- PAT push\n- delta-only"
create_issue "[P9] Ops: backups & budget guards" "task,P9" "- DB snapshots\n- B2 lifecycle\n- alerts"