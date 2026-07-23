# DermIQ — Setup from scratch

This guide takes a **fresh machine** to the full stack running locally: Postgres
source DB seeded → Snowflake RAW → dbt (stg/int/mart) → FastAPI → Next.js
dashboard at `http://localhost:3000`. Budget ~60–90 minutes the first time.

**Prerequisite:** set up [`platform-core`](https://github.com/pneiman1/platform-core)
**first** — see `platform-core/docs/SETUP.md`. DermIQ imports it from a sibling
checkout in editable mode (ADR-001); it is not on a package index.

**Supported platforms:** macOS (Intel & Apple Silicon), Linux, and Windows via
WSL2. Steps are identical except where a callout marks **macOS** vs
**Linux / WSL2**. On Apple Silicon, also skim [`MACOS-NOTES.md`](MACOS-NOTES.md).

> WSL2: run everything inside your Ubuntu distro, and ensure Docker Desktop's
> **WSL Integration** is enabled for it.

---

## 1. Install Node.js 22 (for the frontend)

platform-core setup already covered Python 3.12, git, Docker, AWS/Astronomer.
DermIQ's frontend additionally needs **Node.js 22+**.

**macOS**
```bash
brew install node            # or: brew install node@22
node --version               # v22.x or newer
```

**Linux / WSL2**
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt install -y nodejs
node --version
```

## 2. Clone DermIQ next to platform-core

The editable install uses the relative path `../platform-core`, so keep them
siblings:

```
~/projects/
├── platform-core/      ← already set up
└── dermiq/             ← this repo
```

```bash
cd ~/projects
git clone git@github.com:pneiman1/dermiq.git
cd dermiq
```

## 3. Create a virtualenv and install (platform-core first)

```bash
python3.12 -m venv .venv
source .venv/bin/activate            # macOS & Linux/WSL2

pip install --upgrade pip
pip install -e ../platform-core      # the shared library, FIRST
pip install -e ".[dev,transform,api]"  # DermIQ + dbt + API + dev tools
```

> macOS: invoke `python3.12` explicitly so the venv isn't built from a shadowing
> Homebrew/system Python — see [MACOS-NOTES](MACOS-NOTES.md).

## 4. Configure environment

Reuse the Snowflake credentials you already put in platform-core's `.env`:

```bash
cp ../platform-core/.env .env
```

The Postgres source defaults already match `docker-compose.yml`, so no edits are
needed for local dev.

## 5. Start the Postgres source database

```bash
docker compose up -d
docker compose ps        # STATUS should show "healthy"
```

This launches `dermiq-postgres` and auto-loads the Nextech-shaped schema. The
image (`postgres:16-alpine`) is **multi-arch**, so it runs natively on both Intel
and Apple Silicon Macs and on Linux/WSL2.

## 6. Seed the source database

```bash
python scripts/seed_postgres.py
```

Generates ~18 months of deterministic (seed=42) Del Mar data and loads it into
Postgres (~7 providers, 38 services, 3,500 patients, and their appointments &
transactions). Safe to re-run (truncates first).

## 7. Land the source into Snowflake (RAW)

```bash
python scripts/ingest_raw.py
```

Reads every `nextech_source` table via the read-only role and full-refreshes it
into `DERMIQ_DEV.RAW_DEL_MAR` with explicit column types (ADR-005).

## 8. Transform through dbt (stg → int → mart)

```bash
make dbt-deps        # install dbt packages (dbt_utils)
make dbt-debug       # validate config + Snowflake connectivity
make dbt-build       # build all models + run tests
```

> The Makefile loads `.env` and uses GNU make features (`include`, `wildcard`,
> `ifneq`). macOS ships GNU make (3.81) by default, so this works as-is; recipe
> commands are POSIX `sh` (`cd … && …`) with no bash-only syntax.

## 9. Run the API and the frontend (two terminals)

**Terminal 1 — API** (FastAPI on `:8000`):
```bash
make api-install     # first time only: pip install -e ".[api,dev]"
make api-run
```

**Terminal 2 — frontend** (Next.js on `:3000`):
```bash
cd frontend
npm install          # first time only
npm run dev
```

The frontend defaults to `http://localhost:8000/api/v1`; to override, create
`frontend/.env.local` with `NEXT_PUBLIC_API_BASE_URL=...`.

## 10. Open the dashboard

```
http://localhost:3000
```

You should land on the **Executive** tab with live KPIs, the revenue line chart,
and the category breakdown.

---

## Resetting

```bash
docker compose down -v       # wipe the postgres_data volume
docker compose up -d
python scripts/seed_postgres.py
python scripts/ingest_raw.py
make dbt-build
```

---

## Cross-platform validation checklist

Run these at the end of setup to confirm every layer works. All should pass on
macOS, Linux, and WSL2.

| # | Command | Expected |
|---|---|---|
| 1 | `docker compose ps` | `dermiq-postgres` STATUS **healthy** |
| 2 | `python scripts/seed_postgres.py` | prints loaded counts, exits 0 |
| 3 | `make dbt-debug` | `All checks passed!` |
| 4 | `python scripts/ingest_raw.py` | prints RAW row counts, exits 0 |
| 5 | `make dbt-build` | `Done. PASS=… ERROR=0` |
| 6 | `make api-run`, then `curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health` | `{"status":"ok","snowflake_reachable":true}` |
| 7 | `cd frontend && npm run dev`, then open `localhost:3000` | Executive tab renders with data |

---

## Troubleshooting

- **`ModuleNotFoundError: platform_core`** — venv not active or editable install
  missing. Re-activate `.venv`, re-run step 3.
- **Connection refused on 5432** — container not healthy, or another Postgres is
  bound to 5432. Check `docker compose ps`.
- **API returns `internal error querying warehouse` after a while** — the dev
  server's Snowflake session token expired; restart `make api-run` (real fix is
  pooling/keep-alive, see `docs/API.md` → Future work).
- **Apple Silicon specifics** — see [`MACOS-NOTES.md`](MACOS-NOTES.md).
