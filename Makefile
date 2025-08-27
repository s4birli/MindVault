.PHONY: dev stop logs migrate migrate-all init-db extensions psql psql-docker ftscheck minio health

DB_URL ?= postgresql://postgres:postgres@localhost:5432/mindvault

# --- core targets ---

dev:
	docker compose -f docker-compose.dev.yml up -d

stop:
	docker compose -f docker-compose.dev.yml down

logs:
	docker compose -f docker-compose.dev.yml logs -f

extensions:
	docker compose -f docker-compose.dev.yml exec db psql -U postgres -d mindvault -f /app/scripts/extensions.sql

migrate:
	psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f scripts/complete_init.sql

migrate-all:
	psql "$(DB_URL)" -v ON_ERROR_STOP=1 -f scripts/complete_init.sql

init-db:
	docker compose -f docker-compose.dev.yml exec db psql -U postgres -d mindvault -f /app/scripts/complete_init.sql

psql:
	psql "$(DB_URL)"

psql-docker:
	docker compose -f docker-compose.dev.yml exec db psql -U postgres -d mindvault


DATE := $(shell date +%F_%H%M%S)

backup:
	mkdir -p backups
	docker exec -t mindvault_db pg_dump -U postgres -d mindvault -Fc > backups/mindvault_$(DATE).dump
	ls -lh backups | tail -n 5

restore:
	@if [ -z "$(DUMP)" ]; then echo "Usage: make restore DUMP=backups/FILE.dump"; exit 1; fi
	docker exec -it mindvault_db psql -U postgres -c "DROP DATABASE IF EXISTS mindvault_restore;"
	docker exec -it mindvault_db psql -U postgres -c "CREATE DATABASE mindvault_restore;"
	docker exec -i mindvault_db pg_restore -U postgres -d mindvault_restore --no-owner --no-privileges < $(DUMP)

minio:
	@echo "Open console: http://localhost:9001 (minioadmin/minioadmin)"
	@echo "Or: mc alias set local http://localhost:9000 minioadmin minioadmin && mc mb local/mindvault"

n8n-up:
	docker compose -f docker-compose.dev.yml up -d n8n

n8n-logs:
	docker compose -f docker-compose.dev.yml logs -f n8n

n8n-stop:
	docker compose -f docker-compose.dev.yml stop n8n

health:
	curl -fsS http://localhost:8000/health && echo " OK"

# --- extra checks ---

ftscheck:
	docker compose -f docker-compose.dev.yml exec -T db \
	psql -U postgres -d mindvault -c "\
	  SELECT count(*) docs FROM documents;"