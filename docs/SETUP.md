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

**Snowflake auth is key-pair (JWT), not password.** Snowflake enforces MFA, which
password auth can't satisfy for headless services (API, ingestion, dbt, Airflow),
so key-pair is the primary path (see [DECISIONS](DECISIONS.md) ADR-009). Generate a
key-pair once and register the public key on your Snowflake user:

```bash
# 2048-bit RSA, encrypted private key
openssl genrsa 2048 | openssl pkcs8 -topk8 -inform PEM -outform PEM \
  -out ~/.ssh/snowflake_rsa_key.p8 -passout pass:<passphrase>
openssl rsa -in ~/.ssh/snowflake_rsa_key.p8 -passin pass:<passphrase> \
  -pubout -out ~/.ssh/snowflake_rsa_key.pub
# In Snowsight: ALTER USER <you> SET RSA_PUBLIC_KEY='<public key body, no headers>';
```

Then set in `.env` (both repos share these var names):

```
SNOWFLAKE_PRIVATE_KEY_PATH=~/.ssh/snowflake_rsa_key.p8
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=<passphrase>
# SNOWFLAKE_PASSWORD is legacy — a fallback for non-MFA accounts only. Leave it
# unset when SNOWFLAKE_PRIVATE_KEY_PATH is set; key-pair takes precedence.
```

**Anthropic API key (chunk-10 — AI Studio + Canvas).** The RAG assistant and the
Canvas chart composer call Anthropic Claude. Create a key at
[console.anthropic.com](https://console.anthropic.com) → API Keys, and note that
Anthropic requires a **minimum $10 prepaid credit** on the account before the API
will serve requests. Add it to `.env`:

```
ANTHROPIC_API_KEY=sk-ant-...
```

This key is only needed at query time (serving `/chat` and `/canvas/generate`).
Building the RAG corpus does **not** use it — embeddings are computed locally with
sentence-transformers. If it's missing, the dashboard still runs; only AI Studio
and Canvas generation return errors.

The Postgres source defaults already match `docker-compose.yml`, so no edits are
needed for local dev.

## 5. Start the Postgres source database

```bash
docker compose up -d
docker compose ps        # STATUS should show "healthy"
```

This launches `dermiq-postgres` and auto-loads the source schema on first start
via `/docker-entrypoint-initdb.d`: both `infra/postgres/init/01_schema.sql`
(providers/patients/appointments/transactions) and
`infra/postgres/init/02_inventory.sql` (the chunk-11 inventory tables) run
automatically — no manual DDL. The image (`postgres:16-alpine`) is **multi-arch**,
so it runs natively on both Intel and Apple Silicon Macs and on Linux/WSL2.

> Init scripts run **only on an empty data volume**. If you added the inventory
> schema to an already-running container, either `docker compose down -v` and back
> up, or let `scripts/seed_inventory.py` create the tables (it applies the same DDL).

## 6. Seed the source database

```bash
python scripts/seed_postgres.py
```

Generates ~18 months of deterministic (seed=42) Del Mar data and loads it into
Postgres (~7 providers, 38 services, 3,500 patients, and their appointments &
transactions). Safe to re-run (truncates first).

Then load the inventory / consumables lifecycle (chunk-11), which attaches lots,
stock, and consumption to the existing transactions:

```bash
python scripts/seed_inventory.py
```

## 7. Land the source into Snowflake (RAW)

```bash
python scripts/ingest_raw.py
```

Reads every `nextech_source` table via the read-only role and full-refreshes it
into `DERMIQ_DEV.RAW_DEL_MAR` with explicit column types (ADR-005).

## 8. Build the warehouse: dbt → clustering → RAG corpus

The warehouse artifacts have an ordering dependency: the patient-segment marts read
the clustering output, and clustering reads a dbt intermediate model — so it's
**dbt → cluster → dbt** (two dbt passes), then the RAG corpus.

**a. First dbt build** (staging → intermediate → marts):

```bash
make dbt-deps        # install dbt packages (dbt_utils) — first time only
make dbt-debug       # validate config + Snowflake connectivity (key-pair)
make dbt-build       # build all models + run tests (also loads the marketing_spend seed)
```

> On a **fresh warehouse, `mart_patient_segments` and `mart_patient_segment_members`
> fail on this first pass** — they read `INT_..._CLUSTER_ASSIGNMENTS`, which the
> clustering step hasn't written yet. That's expected; steps (b)–(c) fix it.

**b. Run patient clustering (chunk-9):**

```bash
python scripts/run_clustering.py
```

Reads `int_patient_features` (built in step a), fits k-means (7 segments), and
writes `INT_DEL_MAR.INT_PATIENT_CLUSTER_ASSIGNMENTS` — the `ml` source the segment
marts read.

**c. Second dbt build** so the segment marts pick up the assignments:

```bash
make dbt-build       # now completes with ERROR=0
```

**d. Build the RAG corpus (chunk-10):**

```bash
python scripts/build_rag_corpus.py
```

One script does it all — rebuilds the knowledge documents from the marts, embeds
them locally with sentence-transformers (no Anthropic key needed here), and writes
`MART_DEL_MAR.RAG_CORPUS`. There is **no separate embedding/ingest script**. The
corpus is cached in the API process, so re-run this after any data refresh and then
restart the API.

**e. Canvas layouts table (chunk-12) — optional.** Canvas generates and queries
charts with no setup, but *saving* a canvas needs a table that isn't auto-created.
Create it once (needed only if you'll demo Save/Load):

```bash
python - <<'PY'
from platform_core.warehouse.connection import get_snowflake_connection
with get_snowflake_connection(database="DERMIQ_DEV") as c:
    c.cursor().execute("""
        CREATE TABLE IF NOT EXISTS DERMIQ_DEV.MART_DEL_MAR.CANVAS_LAYOUTS (
            canvas_id   VARCHAR PRIMARY KEY,
            tenant_id   VARCHAR,
            title       VARCHAR,
            layout_json VARIANT,
            created_at  TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(),
            updated_at  TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP()
        )
    """)
print("CANVAS_LAYOUTS ready")
PY
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
| 2 | `python scripts/seed_postgres.py && python scripts/seed_inventory.py` | prints loaded counts, exits 0 |
| 3 | `make dbt-debug` | `All checks passed!` |
| 4 | `python scripts/ingest_raw.py` | prints RAW row counts (incl. inventory), exits 0 |
| 5 | `make dbt-build` (first pass) | builds; the two `mart_patient_segment*` models **error** (expected — no clustering yet) |
| 6 | `python scripts/run_clustering.py` | writes cluster assignments, exits 0 |
| 7 | `make dbt-build` (second pass) | `Done. PASS=… ERROR=0` |
| 8 | `python scripts/build_rag_corpus.py` | prints documents embedded + written, exits 0 |
| 9 | `make api-run`, then `curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health` | `{"status":"ok","snowflake_reachable":true}` |
| 10 | `curl -s -H "X-Tenant-ID: del_mar" -X POST localhost:8000/api/v1/chat -d '{"question":"top revenue provider?"}' -H 'Content-Type: application/json'` | JSON with an `answer` (verifies `ANTHROPIC_API_KEY`) |
| 11 | `cd frontend && npm run dev`, then open `localhost:3000/executive` | Executive tab renders KPIs + both story callouts |
| 12 | open `localhost:3000/canvas`, type "Revenue by provider" | a bar chart renders (verifies Canvas end-to-end) |
| 13 | open `localhost:3000/ai-studio` | segment cards render |

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
