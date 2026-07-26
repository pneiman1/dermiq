# DermIQ — Project Status

Snapshot of what's shipped, what's known tech debt, and where DermIQ is headed.
Last refreshed alongside the chunk-11 inventory work + top-bar shimmer.

## What's shipped

All eleven chunks are implemented and running end-to-end (Postgres → Snowflake →
dbt → FastAPI → Next.js, orchestrated by Airflow):

| Chunk | Shipped |
|---|---|
| 1 | Repo skeleton, package config, structured logging, platform-core wiring |
| 2 | Postgres source DB (Nextech-shaped) + synthetic Del Mar seed; RAW ingestion |
| 3 | dbt staging (typed 1:1 views over RAW) |
| 4 | dbt intermediate (visit economics, patient LTV, provider daily) |
| 5 | dbt marts + marketing_spend seed |
| 5.5 | Explicit Snowflake column types on RAW load (ADR-005) |
| 6 | FastAPI backend over marts |
| 7 | Next.js dashboard, 7 tabs |
| 7.5 | Cross-platform setup docs |
| 8 | Airflow via Astronomer + Cosmos (daily pipeline) |
| 9 | Unsupervised patient clustering (k-means, 7 segments) |
| 10 | RAG chat over marts (Claude + local embeddings) |
| 11 | Real inventory data: lots, stock, waste, expiry, true margin |

Also shipped outside the chunk sequence: Snowflake key-pair auth migration
(ADR-009), Node 20→22, and the shimmer gradient wordmark (ADR-012).

## Known tech debt

- **Snowflake reconnect-on-expiry (TODO).** The API's queries rely on one
  long-lived connection; when Snowflake's master token expires (~1–2 days) queries
  fail with `390114` until the API is restarted. Fix: reconnect on
  `ReauthenticationRequest`/expired-token instead of a pinned connection.
- **Single in-memory connection.** The API holds one `app.state.sf_conn`; no
  pooling, so it's a single point of failure and a concurrency bottleneck.
- **X-Tenant-ID stub auth.** Tenancy is resolved from an `X-Tenant-ID` header with
  no real authentication — a development stub, not production auth.
- **k=7 clustering heuristic.** The patient-segmentation cluster count is a fixed
  heuristic, not chosen by silhouette/elbow analysis.
- **Manual corpus rebuild.** The RAG corpus is cached in the API process; a rebuild
  (`scripts/build_rag_corpus.py`) requires an API restart to take effect. Airflow
  refreshes it daily, but ad-hoc rebuilds are manual.
- **Inventory data is synthetic fixtures.** chunk-11's lots/stock/expiry numbers are
  hand-calibrated generators, not a recovery of any prior report's figures.

## Roadmap

- **SSE streaming** for `/chat` (currently non-streaming + client typewriter).
- **Real authentication** replacing the X-Tenant-ID stub.
- **Connection pooling** + reconnect-on-expiry for the warehouse.
- **Multi-tenant** support (schemas already namespace by tenant; needs auth + routing).
- **LLM-generated cluster names** (segments are currently rule-named).
- **Dashboard drill-downs** across the marts (deeper interactivity per tab).

## Where DermIQ could go

- **SaaS deployment** — host the dashboard (e.g. Cloudflare Pages) and API for real
  practices, with per-tenant onboarding.
- **Multi-vertical expansion** — the platform-core split is deliberate; the same
  core could power BrewIQ (breweries), FitIQ (fitness studios), etc.
- **Real customer onboarding** — replace synthetic Del Mar data with a real
  clinic's EMR/marketing/loyalty feeds through the same ingestion → dbt → marts path.
