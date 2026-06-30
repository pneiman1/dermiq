# DermIQ developer Makefile.
#
# dbt targets run the transform/ project against Snowflake. Connection settings
# are env-driven (see transform/profiles.yml); we load .env here so a contributor
# with a populated .env can run `make dbt-build` without exporting vars by hand.

# Load .env into the environment if present (KEY=VALUE lines), exported to recipes.
ifneq (,$(wildcard .env))
include .env
export
endif

# Use the project virtualenv's dbt and keep profiles.yml alongside the project.
DBT := $(CURDIR)/.venv/bin/dbt
DBT_DIR := $(CURDIR)/transform
export DBT_PROFILES_DIR := $(CURDIR)/transform

PIP := $(CURDIR)/.venv/bin/pip
PYTEST := $(CURDIR)/.venv/bin/pytest
UVICORN := $(CURDIR)/.venv/bin/uvicorn

.PHONY: dbt-debug dbt-deps dbt-seed dbt-run dbt-test dbt-build dbt-docs \
        api-install api-run api-test \
        frontend-install frontend-dev frontend-build

# Validate config + warehouse connectivity.
dbt-debug:
	cd $(DBT_DIR) && $(DBT) debug

# Install package dependencies (dbt_utils, etc.) into dbt_packages/.
dbt-deps:
	cd $(DBT_DIR) && $(DBT) deps

# Load CSV seeds (e.g. marketing_spend) into the warehouse. Note: `dbt build`
# already runs seeds in DAG order, so this is for loading seeds on their own.
dbt-seed:
	cd $(DBT_DIR) && $(DBT) seed

# Build models only.
dbt-run:
	cd $(DBT_DIR) && $(DBT) run

# Run data tests only.
dbt-test:
	cd $(DBT_DIR) && $(DBT) test

# Build models then run their tests (the everyday command).
dbt-build:
	cd $(DBT_DIR) && $(DBT) build

# Generate and serve the docs site.
dbt-docs:
	cd $(DBT_DIR) && $(DBT) docs generate && $(DBT) docs serve

# Install the FastAPI backend (and dev tools) into the project virtualenv.
api-install:
	$(PIP) install -e ".[api,dev]"

# Run the API with autoreload. .env is loaded above, so Snowflake creds are set.
api-run:
	$(UVICORN) dermiq.api.main:app --reload --port 8000 --host 0.0.0.0

# Run the API test suite (hits real Snowflake; .env is loaded above).
api-test:
	$(PYTEST) tests/api/ -v

# --- Frontend (Next.js, in frontend/) ---
frontend-install:
	cd frontend && npm install

frontend-dev:
	cd frontend && npm run dev

frontend-build:
	cd frontend && npm run build
