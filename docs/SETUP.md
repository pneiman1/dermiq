# DermIQ — Setup from scratch

This guide takes you from a fresh machine to a loaded source database with
realistic Del Mar Cosmetic Dermatology data.

DermIQ is the first vertical product built on
[`platform-core`](https://github.com/pneiman1/platform-core). It does **not**
vendor platform-core — it imports it from a sibling checkout installed in
editable mode (see [`docs/DECISIONS.md`](DECISIONS.md), ADR-001). The two repos
are developed side by side.

## Prerequisites

- WSL2 (or Linux/macOS), Python 3.11+, and git
- Docker + Docker Compose (for the local Postgres source database)

## 1. Clone both repos as siblings

The editable install relies on the relative path `../platform-core`, so the two
checkouts must live next to each other:

```
projects/
├── platform-core/
└── dermiq/
```

```bash
cd ~/projects
git clone git@github.com:pneiman1/platform-core.git
git clone git@github.com:pneiman1/dermiq.git
```

## 2. Create a virtual environment

A single shared virtualenv at the `projects/` level keeps both editable
installs visible to each other. (A per-repo venv works too — just install
platform-core into it as shown below.)

```bash
cd ~/projects/dermiq
python3 -m venv .venv
source .venv/bin/activate
```

## 3. Install platform-core, then DermIQ — in that order

platform-core must be installed first because DermIQ imports from it and does
not declare it as a resolvable dependency (it is not on a package index).

```bash
pip install -e ../platform-core        # the shared library
pip install -e ".[dev]"                # DermIQ itself + dev tools
```

Verify the import resolves:

```bash
python -c "from platform_core.utils.logging import get_logger; print('platform-core OK')"
```

## 4. Configure environment

```bash
cp .env.example .env
```

For the data-seeding workflow below, the defaults work out of the box — the only
variable that matters is `POSTGRES_SOURCE_URL`, which already matches the
docker-compose credentials. Fill in Snowflake / Anthropic values later, when you
start building ingestion and the LLM features.

## 5. Start the Postgres source database

```bash
docker compose up -d
```

This launches `dermiq-postgres` and auto-loads the Nextech-shaped schema from
`infra/postgres/init/01_schema.sql` (schema `nextech_source`, plus a read-only
`dermiq_reader` role). Confirm it is healthy:

```bash
docker compose ps          # STATUS should show "healthy"
```

## 6. Seed the source database

Generate ~18 months of synthetic Del Mar data and load it into Postgres:

```bash
python scripts/seed_postgres.py
```

The generators are deterministic (seed=42), so re-running produces the same
data. The script truncates existing rows first, so it is safe to re-run.

Expected output (approximate — exact counts depend on the generator):

```
=== Postgres source database loaded ===
  providers      : 7
  services       : 38
  patients       : 3,500
  appointments   : ...
  transactions   : ...
```

## 7. Verify the data landed

```bash
docker compose exec postgres \
  psql -U dermiq -d del_mar_source -c \
  "SELECT count(*) AS transactions FROM nextech_source.transactions;"
```

If you see a non-zero count, the source database is ready and the analytics
pipeline (ingestion → dbt → marts) can be built on top of it.

## Resetting

To wipe everything and start clean:

```bash
docker compose down -v     # removes the postgres_data volume
docker compose up -d       # re-creates the schema from scratch
python scripts/seed_postgres.py
```

## Troubleshooting

- **`ModuleNotFoundError: platform_core`** — platform-core was not installed, or
  the venv is not active. Re-run step 3 with the venv activated.
- **Connection refused on port 5432** — the container is not up/healthy, or
  another Postgres is already bound to 5432. Check `docker compose ps`.
- **Imports behave oddly after editing platform-core** — editable installs pick
  up source changes live; if not, re-run `pip install -e ../platform-core`.
