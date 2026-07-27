# From Fresh Clone to Running Demo (~60 minutes)

Speed run, not a tutorial. For the "why," see [`SETUP.md`](SETUP.md). macOS
(Apple Silicon or Intel); Linux/WSL2 works the same. Commands assume
`~/projects/`.

Realistic budget: ~35 min hands-on + ~20 min of downloads/builds (docker pull,
`npm install`, torch wheels, dbt builds). Plan for **~60 min** the first time.

---

## 1. Prerequisites (5 min)

- **Anthropic API key** with a **$10 prepaid credit** — [console.anthropic.com](https://console.anthropic.com).
- **Snowflake account** with a key-pair-authed user (public key already `ALTER USER … SET RSA_PUBLIC_KEY`), or the ability to run `ALTER USER`.
- **Docker Desktop** installed and **running** (check the menu-bar whale).
- **Python 3.12**, **Node 22**, **git**, and the **Astro CLI** (`astro`) installed and on `PATH`.

```bash
python3.12 --version && node --version && docker info >/dev/null && astro version
```

## 2. Clone (2 min)

```bash
mkdir -p ~/projects && cd ~/projects
git clone git@github.com:pneiman1/platform-core.git
git clone git@github.com:pneiman1/dermiq.git
```

## 3. Environment (5 min)

```bash
# Restore both .env files from secure storage:
cp <secure>/platform-core.env ~/projects/platform-core/.env
cp <secure>/dermiq.env        ~/projects/dermiq/.env

# Restore the Snowflake private key and lock it down:
cp <secure>/snowflake_rsa_key.p8 ~/.ssh/snowflake_rsa_key.p8
chmod 600 ~/.ssh/snowflake_rsa_key.p8
```

Confirm `.env` has `SNOWFLAKE_PRIVATE_KEY_PATH`, `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE`,
and `ANTHROPIC_API_KEY` set. Install both packages editable and verify key-pair auth:

```bash
cd ~/projects/dermiq
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e ../platform-core -e ".[api,dev]"
python -c "from platform_core.warehouse.connection import test_connection; print(test_connection())"
# → a dict with version/account/user/role/warehouse, and NO MFA prompt = key-pair works
```

## 4. Data pipeline (15 min)

Run from `~/projects/dermiq` with `.venv` active. Note the **two dbt passes** around
clustering (the segment marts read the clustering output):

```bash
docker compose up -d                     # source Postgres (auto-loads 01_schema + 02_inventory)
python scripts/seed_postgres.py          # ~3,500 patients, ~9,261 transactions
python scripts/seed_inventory.py         # lots / stock / consumption (chunk-11)
python scripts/ingest_raw.py             # Postgres → Snowflake RAW (explicit types)

make dbt-deps                            # first time only
make dbt-build                           # pass 1 — segment marts ERROR here (expected)
python scripts/run_clustering.py         # k-means → INT_..._CLUSTER_ASSIGNMENTS
make dbt-build                           # pass 2 — now ERROR=0
python scripts/build_rag_corpus.py       # build + embed + write RAG_CORPUS (local embeddings)
```

Optional (only for Canvas Save/Load) — create the layouts table:

```bash
python - <<'PY'
from platform_core.warehouse.connection import get_snowflake_connection
with get_snowflake_connection(database="DERMIQ_DEV") as c:
    c.cursor().execute("CREATE TABLE IF NOT EXISTS DERMIQ_DEV.MART_DEL_MAR.CANVAS_LAYOUTS "
                       "(canvas_id VARCHAR PRIMARY KEY, tenant_id VARCHAR, title VARCHAR, "
                       "layout_json VARIANT, created_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(), "
                       "updated_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP())")
print("CANVAS_LAYOUTS ready")
PY
```

## 5. Services (5 min — up to 3 terminals)

```bash
# Terminal 1 — API on :8000
cd ~/projects/dermiq && source .venv/bin/activate && make api-run

# Terminal 2 — frontend on :3000
cd ~/projects/dermiq/frontend && npm install && npm run dev

# Terminal 3 — Airflow (OPTIONAL; the pipeline above already ran manually)
cd ~/projects/dermiq/airflow && astro dev start   # webserver at http://localhost:8080
```

> Airflow is **optional for the demo** — you ran the pipeline by hand in step 4.
> Start it only to show the three DAGs. `astro dev start` prints the webserver URL
> (default `:8080`); it also needs Docker and takes a minute to bring up 4 containers.

## 6. Verify (5 min)

```bash
curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health
# → {"status":"ok","snowflake_reachable":true}
```

In the browser:
- **`localhost:3000/executive`** — KPIs render; both story callouts show.
- **`localhost:3000/canvas`** — empty state ("Type a request below…").
- In Canvas, type **"Revenue by provider"** → a bar chart renders in ~4s.
- **`localhost:3000/ai-studio`** — segment cards render (and try "How do I build a custom chart?").

## 7. Troubleshooting

| Symptom | Fix |
|---|---|
| **Snowflake auth fails / MFA prompt** | Check `SNOWFLAKE_PRIVATE_KEY_PATH` + `PRIVATE_KEY_PASSPHRASE` in `.env`; confirm `chmod 600 ~/.ssh/snowflake_rsa_key.p8`; confirm the public key is on the user (`DESC USER`). |
| **API 500 / `snowflake_reachable:false` after a while** | Long-lived connection's token expired — restart `make api-run` (known tech debt; see PROJECT_STATUS). |
| **Port 3000 in use** | Kill the old dev server: `lsof -ti :3000 \| xargs kill -9`, then `npm run dev`. Don't let two dev servers share `.next`. |
| **Docker won't start** | Confirm Docker Desktop is running (menu-bar whale); `docker info` should succeed. |
| **Anthropic 401 / `credit_balance`** | Verify `ANTHROPIC_API_KEY` in `.env` and that the account has ≥$10 prepaid at console.anthropic.com. |
| **dbt segment marts error** | Expected on the **first** `make dbt-build` — run `scripts/run_clustering.py` then `make dbt-build` again. |
| **Canvas `WidthProvider is not a function`** | `react-grid-layout` got upgraded past v1 — reinstall the pin: `npm i react-grid-layout@1.5.0`. |
| **`/chat` says "corpus is empty"** | Run `python scripts/build_rag_corpus.py`, then restart the API (corpus is cached in-process). |
| **Airflow UI won't load** | Check `astro dev start` logs; all 4 containers (webserver, scheduler, triggerer, postgres) must be healthy. |
