SHELL := /bin/bash
ROOT := $(CURDIR)

# Prefer the local virtualenv; fall back to the system interpreter.
PY ?= $(shell if [ -x "$(ROOT)/.venv/bin/python" ]; then echo "$(ROOT)/.venv/bin/python"; else echo python3; fi)
NPM ?= npm
UVICORN_PORT ?= 8000
FABPULSE_URL ?= http://127.0.0.1:$(UVICORN_PORT)
CI_RAW := data/ci-raw
CI_DB ?= sqlite:///$(ROOT)/data/fabpulse_ci.db

.PHONY: setup gen ingest api web test python-test web-test ci lint schema snapshot report clean

setup: ## Create the Python virtualenv and install backend + frontend deps
	python3.11 -m venv .venv
	$(ROOT)/.venv/bin/pip install --upgrade pip
	$(ROOT)/.venv/bin/pip install -r api/requirements-dev.txt
	cd web && $(NPM) ci

gen: ## Generate the synthetic raw equipment logs (CSV + Parquet)
	$(PY) data/generate.py --out data/raw

ingest: ## Create the star schema and load data/raw into the warehouse
	cd api && $(PY) -m fabpulse.ingest --src ../data/raw --truncate

api: ## Run the FastAPI service on $(UVICORN_PORT)
	cd api && $(PY) -m uvicorn fabpulse.main:app --reload --port $(UVICORN_PORT)

web: ## Run the Vite dev server
	cd web && $(NPM) run dev

test: python-test web-test ## Run all tests

python-test: ## Run pytest with coverage
	cd api && $(PY) -m pytest --cov=fabpulse --cov-report=term-missing

web-test: ## Run vitest with coverage
	cd web && $(NPM) run test -- --run --coverage

ci: ## Reproduce the GitHub Actions pipeline locally
	mkdir -p $(CI_RAW)
	$(PY) data/generate.py --out $(CI_RAW) --days 20 --seed 7
	cd api && FABPULSE_DATABASE_URL="$(CI_DB)" $(PY) -m fabpulse.ingest --src ../$(CI_RAW) --truncate
	cd api && $(PY) -m pytest --cov=fabpulse --cov-report=term-missing --cov-fail-under=0
	cd api && $(PY) -m coverage report --include="fabpulse/stats.py,fabpulse/ingest.py" --fail-under=85
	cd web && $(NPM) run typecheck
	cd web && $(NPM) run lint
	cd web && $(NPM) run test -- --run --coverage
	cd web && $(NPM) run build

lint: ## Lint the frontend and check formatting
	cd web && $(NPM) run lint
	cd web && $(NPM) run format

schema: ## Write the Postgres DDL to scripts/schema.sql
	cd api && $(PY) -m fabpulse.schema --out ../scripts/schema.sql

snapshot: ## Write the OpenAPI contract to api/openapi.json
	$(PY) scripts/openapi_snapshot.py

report: ## Export the engineer report to reports/
	$(PY) scripts/export_report.py --format md --out reports/

clean: ## Remove generated artifacts (keeps the generated raw logs)
	rm -rf api/.pytest_cache api/.coverage api/htmlcov web/dist web/coverage
