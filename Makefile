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

.PHONY: dbt-debug dbt-deps dbt-run dbt-test dbt-build dbt-docs

# Validate config + warehouse connectivity.
dbt-debug:
	cd $(DBT_DIR) && $(DBT) debug

# Install package dependencies (dbt_utils, etc.) into dbt_packages/.
dbt-deps:
	cd $(DBT_DIR) && $(DBT) deps

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
