# DermIQ

DermIQ is a vertical analytics SaaS for cosmetic dermatology practices. It turns a
year of fragmented EMR, marketing, and loyalty data into a single operational
brief: provider productivity, marketing ROI, patient recall, appointment flow,
consumables margin, and an AI assistant that answers questions grounded in the
practice's own numbers. The reference tenant is **Del Mar Cosmetic Dermatology**,
a fictional La Jolla practice whose data is fully synthetic but story-driven —
seasonal revenue swings, a provider on medical leave, a rising star, Botox vial
waste, filler expiry — so every dashboard has something real to show.

DermIQ is the first vertical built on
[`platform-core`](https://github.com/pneiman1/platform-core), a reusable data-platform
toolkit (config, Snowflake connection, RAG, LLM client).

## Architecture

```
  ┌────────────┐   ingestion    ┌──────────────┐      dbt        ┌───────────────┐
  │  Postgres  │  (full-refresh │  Snowflake   │  stg → int →    │   Snowflake   │
  │  source DB │───────────────▶│  RAW_<tenant>│──── mart ──────▶│  MART_<tenant>│
  │ (Nextech-  │   typed load)  └──────────────┘                 └───────┬───────┘
  │  shaped)   │                                                         │
  └────────────┘                                                         │
        ▲                                     ┌───────────────────────────┤
        │ seed_postgres.py                    │                           │
        │ (synthetic Del Mar data)            ▼                           ▼
        │                              ┌──────────────┐          ┌───────────────┐
        │                              │   FastAPI    │          │  RAG corpus   │
        │                              │  /api/v1/*   │          │ (marts → docs │
        │                              │  over marts  │          │ → embeddings  │
        │                              └──────┬───────┘          │ → rag_corpus, │
        │                                     │                  │  JSON vectors)│
        │                                     ▼                  └───────┬───────┘
        │                              ┌──────────────┐                  │
        │                              │  Next.js 14  │◀── /chat ─────────┘
        │                              │  dashboard   │   (in-process cosine
        │                              │  (7 tabs)    │    retrieval → Claude)
        │                              └──────────────┘

  Airflow (Astronomer + Cosmos) orchestrates seed→ingest→dbt daily; a second DAG
  rebuilds + re-embeds the RAG corpus after the pipeline.
```

- **Warehouse auth is key-pair (JWT)** everywhere headless (API, ingestion, dbt,
  Airflow) — Snowflake enforces MFA, which password auth can't satisfy unattended.
- **RAG** embeds ~30 corpus docs (metric definitions + live mart snapshots) with
  `sentence-transformers` (all-MiniLM-L6-v2, 384-dim), stores vectors as JSON in a
  `rag_corpus` table, retrieves top-k by in-process cosine, and generates answers
  with Anthropic Claude. No warehouse-native `VECTOR` type is used (portable by
  design; a pgvector backend can drop in later).

## Feature matrix (7 tabs)

| Tab | What it shows | Status |
|---|---|---|
| **Executive** | Revenue trend, category mix, funnel, KPI strip | Live |
| **Providers** | Per-provider TTM scorecard: revenue/hour, cross-sell, skincare attach | Live |
| **Marketing** | Acquisition by channel, spend, CAC, LTV:CAC, channel health | Live |
| **Flow** | Appointment dispositions, no-show/cancel rates, day×hour heatmap | Live |
| **Recall** | Ranked queue of lapsing patients + revenue at risk | Live |
| **Inventory** | Consumables true margin, waste, stock/par status, expiring lots | Live (chunk-11) |
| **AI Studio** | RAG chat grounded in the practice's marts | Live (chunk-10, see note) |

> **Status note:** chunk-10 (RAG / AI Studio) is implemented and running against
> Snowflake but is **not yet committed to `main`** — it currently lives in the
> working tree. See [`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## Stack

- **Python 3.12** — ingestion, seed, API, clustering, RAG
- **Next.js 14** (React 18, Tailwind, TanStack Query, Recharts) — dashboard
- **Snowflake** — analytics warehouse (RAW / STG / INT / MART / SEED schemas per tenant)
- **Postgres 16** — Nextech-shaped source EMR (docker-compose)
- **dbt 1.11** (dbt-snowflake) — staging / intermediate / marts
- **Apache Airflow** via **Astronomer Astro + astronomer-cosmos** — orchestration
- **Anthropic Claude** (`claude-sonnet-5`) — RAG generation
- **sentence-transformers** (all-MiniLM-L6-v2, 384-dim) — local embeddings

## Repository structure

```
dermiq/
├── dermiq/            Python package
│   ├── api/           FastAPI app (routers: meta, marts, segments, chat, inventory)
│   ├── ingestion/     Postgres source → Snowflake RAW (explicit typed load)
│   ├── seed/          synthetic Del Mar generators (catalog, patients, appts, inventory)
│   └── rag/           RAG corpus builder (marts → documents)
├── transform/         dbt project (staging/ intermediate/ marts/, profiles.yml)
├── airflow/           Astro project + Cosmos DAGs (daily pipeline, RAG refresh)
├── frontend/          Next.js 14 dashboard (7 tabs)
├── scripts/           seed_postgres, seed_inventory, ingest_raw, run_clustering, build_rag_corpus, run_api
├── infra/             Postgres init SQL (source schema)
├── tests/             pytest (ingestion, api, rag)
└── docs/              SETUP, API, DECISIONS, PROJECT_STATUS, DEMO_SCRIPT, MACOS-NOTES
```

## Getting started

Full step-by-step in [`docs/SETUP.md`](docs/SETUP.md): install Node 22, clone
alongside platform-core, install both editable, generate a Snowflake key-pair,
start the Postgres source, seed synthetic data, then run ingestion → dbt → API →
the Next.js dashboard at `localhost:3000`. Supported on macOS (Intel & Apple
Silicon), Linux, and Windows/WSL2 (see [`docs/MACOS-NOTES.md`](docs/MACOS-NOTES.md)).

## Where the work has been

| Chunk | What shipped |
|---|---|
| 1 | Repo skeleton, package config, structured logging, platform-core wiring |
| 2 | Postgres source DB (Nextech-shaped schema) + synthetic seed; RAW ingestion |
| 3 | dbt staging layer (typed 1:1 views over RAW) |
| 4 | dbt intermediate layer (visit economics, patient LTV, provider daily) |
| 5 | dbt marts layer + marketing_spend seed |
| 5.5 | Explicit Snowflake column types on RAW load (resolves ADR-005) |
| 6 | FastAPI backend over the marts |
| 7 | Next.js dashboard, 7 tabs |
| 7.5 | Cross-platform setup docs (macOS / Linux / WSL2) |
| 8 | Apache Airflow orchestration via Astronomer + Cosmos |
| 9 | Unsupervised patient clustering (k-means, 7 segments) |
| — | Snowflake key-pair (JWT) auth migration (ADR-009); Node 20→22 |
| 10 | RAG chat over the marts (Anthropic Claude + local embeddings) — *uncommitted on `main`* |
| 11 | Real inventory data: lots, stock, waste, expiry, true margin |
| — | Shimmer gradient wordmark + top-bar refinement |

Architecture decisions are logged in [`docs/DECISIONS.md`](docs/DECISIONS.md);
current state, tech debt, and roadmap in
[`docs/PROJECT_STATUS.md`](docs/PROJECT_STATUS.md).

## License & contributors

All rights reserved (license TBD). Author: Phil Neiman. Built on
[`platform-core`](https://github.com/pneiman1/platform-core).
