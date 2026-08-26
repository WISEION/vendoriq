# VendorIQ — developer entry points.
#
# Everything runs natively; Docker is optional (see infra/docker-compose.yml). The API and the
# worker share one uv-managed virtual environment at the repository root.
SHELL := /bin/bash
.DEFAULT_GOAL := help

UV        ?= uv
PY        ?= .venv/bin/python
# From the venv, not from PATH. CI runs `uv run ruff`, which resolves the version pinned in
# uv.lock; a different ruff on a developer's PATH silently disagrees with it. It did: 0.15.8
# skips Markdown ("formatting is experimental") while the pinned 0.16.4 formats the Python
# blocks inside it, so `make lint` passed locally on a file CI rejected.
RUFF      ?= .venv/bin/ruff
MYPY      ?= .venv/bin/mypy
API_DIR   := apps/api
WEB_DIR   := apps/web
DB_URL    ?= postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq
TEST_DB_URL ?= postgresql+psycopg://vendoriq:vendoriq@localhost:5432/vendoriq_test
API_PORT  ?= 8000
WEB_PORT  ?= 5173

.PHONY: help setup db-up migrate seed seed-demo seed-form purge-demo create-admin api web worker test e2e \
	lint format screenshots openapi-validate up prod-up prod-down prod-logs backup restore clean

# Compose invocations. The production stack is the base file *plus* the overlay that turns
# every development default into a required variable (infra/docker-compose.prod.yml).
COMPOSE      ?= docker compose -f infra/docker-compose.yml
PROD_COMPOSE ?= $(COMPOSE) -f infra/docker-compose.prod.yml

help: ## Show the available targets
	@grep -hE '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## Install Python and Node dependencies
	$(UV) sync --all-packages --all-groups
	cd $(WEB_DIR) && npm install --no-audit --no-fund

db-up: ## Create the vendoriq role and both databases (needs a local postgres)
	@bash scripts/db-up.sh

migrate: ## Apply migrations to the app and the test database
	cd $(API_DIR) && DATABASE_URL="$(DB_URL)" ../../$(PY) -m alembic upgrade head
	cd $(API_DIR) && DATABASE_URL="$(TEST_DB_URL)" ../../$(PY) -m alembic upgrade head

seed: ## Load the real seed data (idempotent) — phase 1E
	$(PY) -m vendoriq_api.seed load --real

seed-form: ## Re-freeze seed/wesa_form.json from the WESA form workbook
	$(PY) scripts/freeze-wesa-form.py

seed-demo: ## Load the demo layer on top (is_demo=true) — phase 1E
	$(PY) -m vendoriq_api.seed load --demo

purge-demo: ## Remove every is_demo row, leaving only real data — phase 1E
	$(PY) -m vendoriq_api.seed purge-demo

create-admin: ## Create one real staff account — the first user of a live stack (asks for a password)
	$(PY) -m vendoriq_api.seed create-admin --email "$(EMAIL)" --name "$(NAME)"

api: ## Run the API at http://localhost:$(API_PORT) (/health, /api/docs)
	DATABASE_URL="$(DB_URL)" $(PY) -m uvicorn vendoriq_api.main:app \
		--app-dir $(API_DIR) --host 0.0.0.0 --port $(API_PORT) --reload

web: ## Run the web app at http://localhost:$(WEB_PORT)
	WEB_PORT=$(WEB_PORT) bash scripts/web-dev.sh

worker: ## Run the scheduled jobs
	DATABASE_URL="$(DB_URL)" $(PY) -m vendoriq_worker.main

test: ## Run the Python and the frontend unit tests
	DATABASE_URL="$(TEST_DB_URL)" $(PY) -m pytest
	cd $(WEB_DIR) && npm run test

e2e: ## Run the Playwright suite (needs make api and make web running, or CI's servers)
	cd $(WEB_DIR) && npm run e2e

lint: ## ruff + mypy + eslint + tsc
	$(RUFF) check .
	$(RUFF) format --check .
	$(MYPY) .
	cd $(WEB_DIR) && npm run lint && npm run typecheck

format: ## Apply ruff and prettier formatting
	$(RUFF) format .
	$(RUFF) check --fix .
	cd $(WEB_DIR) && npm run format

screenshots: ## Capture all 34 screens × AZ/EN into docs/screens/
	cd $(WEB_DIR) && npm run e2e:screenshots

openapi-validate: ## Validate docs/openapi.yaml against the OpenAPI 3.1 metaschema
	$(PY) -m pytest $(API_DIR)/tests/test_openapi_contract.py -q

up: ## Bring up the development stack in Docker (seeded, http://localhost)
	$(COMPOSE) --profile dev up --build

prod-up: ## Bring up the production stack (needs infra/.env — see docs/RUNBOOK.md)
	$(PROD_COMPOSE) --profile prod up --build -d

prod-down: ## Stop the production stack, keeping its volumes
	$(PROD_COMPOSE) --profile prod down

prod-logs: ## Follow the production logs
	$(PROD_COMPOSE) --profile prod logs -f

backup: ## Snapshot the running stack's database and documents into ./var/backups
	@bash scripts/backup.sh

restore: ## Restore a snapshot: make restore SNAPSHOT=var/backups/vendoriq-...
	@bash scripts/restore.sh "$(SNAPSHOT)"

clean: ## Remove build artefacts and caches
	rm -rf .pytest_cache .ruff_cache .mypy_cache $(WEB_DIR)/dist $(WEB_DIR)/test-results
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
