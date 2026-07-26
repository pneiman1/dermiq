# DermIQ Interview Study Guide — Snowflake, dbt, Airflow/Cosmos

This is my (Phil's) defense document for the DermIQ data platform. It exists so I can
answer, in depth and without hand-waving, any question about how the warehouse,
transformation layer, and orchestration actually work — the mechanism under the
hood, why I chose it for *this* project, and what I'd say when pressed.

Ground rules I hold myself to when answering:
- I explain the mechanism first, then the tradeoff, then our concrete usage.
- I don't claim a feature I didn't build. Where something is a design intent
  rather than a shipped control, I say so.
- I keep the medallion vocabulary consistent: RAW → STG → INT → MART.

The stack in one breath: a Nextech-shaped **Postgres** source DB is seeded with
synthetic Del Mar data; a Python ingestion job full-refreshes it into
**Snowflake** RAW with explicit types; **dbt** (Core, dbt-snowflake) transforms
RAW → staging → intermediate → marts; **FastAPI** serves the marts; **Next.js**
renders seven-plus tabs; **Airflow** (Astronomer + Cosmos) orchestrates the daily
pipeline, a weekly clustering job, and a daily RAG-corpus refresh. Everything
authenticates to Snowflake with **key-pair (JWT)** auth.

---

# SECTION 1 — SNOWFLAKE

## 1.1 The architecture: storage and compute are separate

The single most important thing to understand about Snowflake is that it splits
into three independent layers, and they scale independently:

1. **Storage layer.** Table data lives in cloud object storage (S3 on our AWS
   account). It's not attached to any server. It's columnar, compressed, and
   immutable at the file level.
2. **Compute layer (virtual warehouses).** A "warehouse" is a cluster of compute
   nodes that Snowflake spins up on demand to run queries. It reads from the
   storage layer over the network. Multiple warehouses can read the same table
   at the same time without contending, because none of them *owns* the data.
3. **Cloud services layer.** The brain: the query optimizer, metadata store,
   transaction manager, security/auth, and the result cache. This is what makes
   pruning and Time Travel possible — it tracks metadata about every micro-partition.

**Why this matters for us.** Our workload is bursty and read-heavy: a dbt build
writes a few dozen small tables once a day, and the FastAPI app runs small point
queries against marts. Separated compute means I run an extra-small warehouse
that auto-suspends between bursts, so I pay for seconds of compute, not a
running server. If I later added a heavy ML job, I could give it its own bigger
warehouse without touching or slowing the dashboard's warehouse — same data,
isolated compute.

**Interview answer.** "Snowflake decouples storage from compute. Data sits in
columnar files in cloud object storage; virtual warehouses are ephemeral compute
that read those files. That's why you can have independent warehouses hitting the
same tables with no contention, and why you pay for compute by the second only
when a warehouse is running."

## 1.2 Columnar storage and micro-partitions

Snowflake stores table data in **micro-partitions**: immutable files of roughly
50–500 MB of *uncompressed* data (~16 MB compressed is the number people quote),
each holding a contiguous set of rows but organized **columnar** internally.
Because it's columnar, a query that touches 3 of 20 columns only reads those 3
columns' bytes.

Crucially, for every micro-partition Snowflake keeps **metadata** in the cloud
services layer: the min and max value of every column in that file, distinct
counts, null counts. This is what powers **partition pruning**: when I filter
`WHERE transaction_date >= '2026-01-01'`, the optimizer looks at each
micro-partition's min/max for `transaction_date` and skips any file that can't
contain a matching row — without opening the file.

**Why this matters for us.** Several marts have a natural date grain
(`mart_revenue_daily` is one row per day). When the API asks for "the last 90
days," pruning means Snowflake only scans the recent micro-partitions. Our tables
are tiny (hundreds to a few thousand rows), so this is not a performance
lifesaver yet — but it's the mechanism I'd point to for why the design scales:
the same query shape stays cheap as the data grows because the work is bounded by
what you filter to, not the table size.

**Interview answer.** "Data lands in immutable micro-partitions, columnar
internally, with per-partition min/max metadata. Queries prune partitions using
that metadata before reading anything, and only the referenced columns are
scanned. So cost scales with what you select and filter, not with total rows."

## 1.3 Virtual warehouses: COMPUTE_WH, sizing, auto-suspend, credits

`COMPUTE_WH` is our virtual warehouse. It's **X-Small (XS)** — one cluster of one
node, the smallest unit. Sizes go XS, S, M, L, … and each step up roughly doubles
the node count and the **credit-per-hour** burn (XS = 1 credit/hour, S = 2,
M = 4, and so on). Bigger warehouses don't make a single small query "more
correct" — they add parallelism for large scans and concurrency.

**Auto-suspend / auto-resume.** The warehouse suspends after a short idle window
and resumes automatically when the next query arrives. Credits are billed **per
second while running**, with a 60-second minimum each time it resumes. So the
cost model is: (size in credits/hour) × (seconds running / 3600), with that
one-minute floor per resume.

**Why this matters for us.** An XS warehouse that auto-suspends is exactly right
for a bursty dev/demo workload. A full `dbt build` of our project runs in well
under a minute of warehouse time; the dashboard's queries are sub-second. Between
those, the warehouse is suspended and costs nothing. My concrete cost controls
are: XS sizing + aggressive auto-suspend. The intended guardrail on top is a
**resource monitor** with a monthly credit quota that suspends the warehouse if
exceeded — that's the mechanism (see 1.11), and it's how I'd cap spend in prod.

**Interview answer.** "COMPUTE_WH is an XS warehouse — one credit an hour, billed
per second with a 60-second minimum, auto-suspends when idle. Sizing is about
parallelism and concurrency, not correctness; for a bursty analytics workload the
right answer is the smallest warehouse that finishes your build plus auto-suspend,
and a resource monitor as the hard cap."

## 1.4 The database → schema → table hierarchy in our project

Snowflake's namespace is `DATABASE.SCHEMA.OBJECT`. We use one database per
environment and medallion **schemas** inside it, one set per tenant:

```
DERMIQ_DEV                         (database — the dev environment)
├── RAW_DEL_MAR                    faithful, typed copy of the Postgres source
├── STG_DEL_MAR                    cleaned/renamed/typed views over RAW
├── INT_DEL_MAR                    intermediate business-logic tables
├── MART_DEL_MAR                   consumer-ready marts (+ RAG_CORPUS, CANVAS_LAYOUTS)
└── SEED_DEL_MAR                   static fixtures (marketing_spend)
```

The naming convention is `<LAYER>_<TENANT>`. The vertical is implied by the
database name (`DERMIQ_DEV` vs a future `DERMIQ_PROD`), so the tenant id carries
only the clinic (`del_mar`), not the vertical. I deliberately keep every layer in
**one database** rather than a database-per-tenant, because at this scale it keeps
cross-layer dbt `ref`s and grants simple; tenant isolation comes from the schema
split (and, in prod, row-access policies). This exact convention is codified once
in `platform_core.warehouse.schemas.schema_name()` and mirrored on the dbt side
by a custom `generate_schema_name` macro, so ingestion (Python) and transformation
(dbt) never disagree about where a tenant's data lives.

**Interview answer.** "One database per environment, medallion schemas named
`LAYER_TENANT` inside it — RAW/STG/INT/MART/SEED for Del Mar. The convention lives
in one Python function and a matching dbt macro so both sides of the pipeline
resolve the same schema names."

## 1.5 Tables vs views: which layer uses what, and why

- **RAW**: base **tables**, created `CREATE OR REPLACE` on each ingest
  (full-refresh). Physical copies of the source.
- **STG (staging)**: **views**. Staging only trims, renames, and casts — it's a
  thin, deterministic transform. A view is free to store and always reflects the
  latest RAW without a rebuild step. I never pay to materialize staging.
- **INT (intermediate)**: **tables**. These compose real business logic (visit
  economics, patient LTV, provider-daily rollups) and are queried by *multiple*
  marts, so I materialize them once as tables for consistent downstream
  performance rather than re-computing the logic inside every mart's view chain.
- **MART**: **tables**. Marts are consumer-facing (one per dashboard tab / the
  RAG corpus builder). Materializing as tables gives a stable snapshot at build
  time and fast reads for the API. Where a mart has a real date grain I can
  cluster it by date.

**Interview answer.** "Views where the transform is cheap and I want live
pass-through (staging); tables where the logic is expensive or reused
(intermediate) or where a consumer reads it repeatedly (marts). It's a
cost-vs-freshness-vs-read-latency call at each layer."

## 1.6 The objects we materialize, and roughly how big

Staging views (9): `stg_nextech__{patients, providers, services, appointments,
transactions}` plus the inventory set `{inventory_units, inventory_lots,
inventory_transactions, inventory_current_stock}`.

Intermediate tables (6): `int_visit_economics` (~5.3k rows, one per completed
visit), `int_patient_lifetime_value` (~3.5k, one per patient),
`int_patient_features`, `int_provider_daily` (~2k, provider×day),
`int_appointment_disposition` (~5.7k), `int_inventory_movements` (~9.6k, one per
consumption/waste/expiry event).

Marts (9 tables): `mart_revenue_daily` (~420 days), `mart_provider_scorecard`
(7 providers), `mart_channel_attribution` (7 channels), `mart_recall_queue`
(~1.1k patients), `mart_patient_segments` (7 segments),
`mart_patient_segment_members` (~2.8k patients), `mart_inventory_status`
(33 SKUs), `mart_true_margin_by_service` (33 services), `mart_expiring_soon`
(~46 lots). Plus `RAG_CORPUS` (~31 docs) and `CANVAS_LAYOUTS` (saved canvases).

Source scale feeding all of this: 7 providers, 38 services, 3,500 patients,
~5,754 appointments, ~9,261 transactions, and the inventory layer (33 units,
~254 lots, ~9.6k movements). This is intentionally small — it's synthetic, story-
driven demo data. I'm honest in interviews that the *interesting* engineering is
the shape of the pipeline, not the row counts.

**Interview answer.** The warehouse holds 9 staging views, 6 intermediate tables, and 9 marts, fed by ~3,500 patients and ~9,261 transactions over 18 months. It's deliberately small synthetic data — the engineering is in the shape of the pipeline, not the row counts, and I'm upfront about that.

## 1.7 Data types we use, and why explicit types matter (ADR-005)

- `NUMBER(18,4)` — the **monetary standard** across every derived layer. Revenue,
  cost, margin, unit cost, quantities all normalize to this precision so
  arithmetic never collides.
- `NUMBER(10,2)` — source-side prices/costs as they arrive from Postgres
  `NUMERIC(10,2)`.
- Deliberately wider source precisions in the inventory raw layer —
  `NUMBER(20,4)` (unit cost) and `NUMBER(38,4)` (a computed transaction value) —
  which is exactly why staging normalizes everything to `NUMBER(18,4)`: to kill
  the precision spread before it reaches the marts.
- `TIMESTAMP_TZ` — timezone-aware timestamps (appointment start/end, ingest
  lineage).
- `DATE`, `VARCHAR`, `INTEGER`, `BOOLEAN` — the rest.
- `VARIANT` — semi-structured JSON, used for `CANVAS_LAYOUTS.layout_json`.
- **No `VECTOR` type.** For RAG I store embeddings as a **JSON string in a
  `VARCHAR`** column (`RAG_CORPUS.embedding`) and rank with an in-process cosine
  top-k. That's a deliberate portability choice (see ADR-008): the store is
  backend-agnostic, so a pgvector or Snowflake-native VECTOR backend could drop
  in later without changing the interface. The same JSON-in-VARCHAR pattern
  appears in `inventory_current_stock.on_hand_lots`.

**Why explicit types matter (ADR-005).** Our ingestion creates each RAW table
from an **explicit type map**, not from pandas dtype inference. The bug this
prevents: an all-NULL or sparse source column (e.g. `hire_date`, which is never
populated) gets inferred by `write_pandas` as `NUMBER`, and then the staging cast
`NUMBER → DATE` fails. By declaring `hire_date DATE` up front, the raw table has
the right type regardless of the data, and staging casts cleanly. ADR-005 also
adds a contract test (`source_column_data_type`) on the sparse columns so a
regression to inference fails loudly.

**Interview answer.** "Every derived monetary column is `NUMBER(18,4)` so
arithmetic is collision-free. RAW types are declared explicitly, not inferred,
because pandas would mis-type sparse columns and break downstream casts — that's
ADR-005. And I store embeddings as JSON in VARCHAR rather than a VECTOR type to
keep the RAG store portable."

## 1.8 Authentication: key-pair (JWT) — the mechanism (ADR-009)

Snowflake started enforcing MFA on the account (the trial-to-paid transition is a
common trigger for tightened security defaults). MFA breaks every **headless**
connection — the API's startup connection, ingestion, dbt, Airflow — because the
first authentication needs a fresh TOTP code that a background process can't
supply. MFA caching doesn't save you: the *initial* auth after the cache expires
still needs a code. So I migrated everything to **key-pair (JWT)** auth.

How it works mechanically:
1. I generated a 2048-bit RSA key-pair. The **private key** (encrypted PKCS#8,
   passphrase-protected) stays on the machine; the **public key** is registered
   on the Snowflake user with `ALTER USER pneiman1 SET RSA_PUBLIC_KEY='…'`.
2. On each connection, the client builds a **JWT** — a short-lived token whose
   claims identify the account+user — and **signs it with the private key**.
3. It sends the JWT to Snowflake with `authenticator=SNOWFLAKE_JWT`. Snowflake
   verifies the signature against the registered public key. No password, no
   TOTP, fully headless.

The private key is decrypted in memory (via the `cryptography` library) and never
leaves the process; the passphrase only decrypts it locally. Password auth remains
as a fallback for non-MFA accounts, but key-pair is the default everywhere,
including dbt's `profiles.yml`.

**Interview answer.** "Public key on the Snowflake user, private key on the
client. Each connection mints a short-lived JWT and signs it with the private
key; Snowflake verifies against the public key. It's the standard for
service/headless auth because it needs no interactive second factor — which is
exactly why I moved to it when MFA enforcement broke the pipeline."

## 1.9 Query execution: what happens on a SELECT

1. The client sends SQL over the (JWT-authenticated) session.
2. The **cloud services layer** parses and optimizes it, and consults
   micro-partition **metadata** to prune partitions the filter can't match.
3. If an identical query ran recently and the underlying data is unchanged, the
   **result cache** returns instantly with no warehouse compute at all.
4. Otherwise the **virtual warehouse** (COMPUTE_WH) resumes if suspended, reads
   only the surviving partitions' referenced columns from storage, executes, and
   returns results. Warehouse-local SSD caches hot data for repeat scans.

**Interview answer.** "Optimize and prune in the services layer using partition
metadata; short-circuit via the result cache if possible; otherwise resume the
warehouse and scan only the pruned partitions and selected columns."

## 1.10 Session and connection lifecycle — the gotcha I actually hit

A Snowflake session has a **session token** (renewed periodically) and a
**master token** with a hard lifetime (~a couple of days) that can't be renewed
forever. The FastAPI app holds one long-lived connection on `app.state` for the
whole process. `client_session_keep_alive=True` keeps the *session* token fresh so
the connection survives overnight idle. But when the **master** token hits its
hard cap, the connection dies with `390114: Authentication token has expired`, and
`/health` flips `snowflake_reachable: false` until the API restarts.

I hit this in practice after ~2 days of uptime. The honest state: the fix today is
restarting the API (it re-mints a fresh JWT connection at startup); the *proper*
fix, which I have documented as tech debt, is to reconnect on
`ReauthenticationRequest` rather than pinning one connection for the process
lifetime. This is a good interview story because it shows I understand the token
model and I'm candid about the current limitation.

**Interview answer.** "Keep-alive refreshes the session token, but the master
token has a hard expiry, so a pinned long-lived connection eventually dies. Right
now I restart to re-auth; the real fix is catching the reauth error and
reconnecting, or moving to a short-lived-connection-per-request with pooling."

## 1.11 Resource monitors and cost control

A **resource monitor** is Snowflake's spend guardrail: you assign it a **credit
quota** over an interval (e.g. monthly) and attach it to one or more warehouses.
As consumption crosses thresholds you configure (say 80%, 100%), it can notify
and then **suspend** the warehouse — either letting running queries finish
(`SUSPEND`) or killing them (`SUSPEND_IMMEDIATE`). It's the hard cap that makes a
credit card safe to attach to a demo account.

Our concrete controls today are XS sizing + auto-suspend, which keep steady-state
cost near zero. The monitor is the guardrail I'd (and would recommend to)
configure on top — e.g. a ~20-credit monthly quota that suspends COMPUTE_WH if a
runaway query or a stuck warehouse blows past it. I describe it as the mechanism
and the intent; I don't claim a specific dollar figure I didn't set.

**Interview answer.** "Resource monitors cap credit consumption over an interval
and can auto-suspend the warehouse at a threshold. Combined with an auto-
suspending XS warehouse, that's belt-and-suspenders cost control: normal usage is
seconds of compute, and the monitor stops any runaway."

## 1.12 Time Travel, Fail-safe, and zero-copy cloning — the free wins

- **Time Travel.** Because storage is immutable and metadata tracks versions,
  Snowflake lets you query a table AS OF a past timestamp or offset, and UNDROP a
  dropped table, within a retention window (1 day on standard). If a bad dbt run
  corrupted a mart, I could `SELECT … AT(OFFSET => -3600)` to see it an hour ago,
  or clone it as-of that point. I don't lean on this because my marts are
  full-rebuilt and reproducible, but it's a real safety net.
- **Fail-safe.** A further ~7-day, Snowflake-operated recovery window after Time
  Travel expires — disaster recovery only, not self-serve.
- **Zero-copy cloning.** `CREATE DATABASE DERMIQ_DEV_PHIL CLONE DERMIQ_DEV`
  creates a full logical copy **instantly and for ~no storage cost**, because the
  clone just points at the same immutable micro-partitions; only diverging writes
  allocate new storage (copy-on-write). This is how I'd give each developer an
  isolated dev database off prod without duplicating terabytes.

**Interview answer.** "Time Travel and cloning fall out of immutable storage +
metadata for free. Cloning is copy-on-write — instant, cheap, perfect for
spinning up isolated dev environments off a prod database."

## 1.13 Snowflake gotchas we actually hit

- **MFA enforcement** broke all headless auth → drove the key-pair migration
  (ADR-009). This is the biggest one.
- **JSON stored as VARCHAR** for embeddings (`RAG_CORPUS.embedding`) and remaining
  lots (`inventory_current_stock.on_hand_lots`) — a deliberate portability choice,
  not a limitation, but worth naming.
- **`background` shorthand isn't a Snowflake thing** — that was a CSS footgun
  elsewhere; the Snowflake-specific footgun was the `VARIANT` insert: you can't
  bind a VARIANT directly in a `VALUES` clause, you insert via
  `INSERT … SELECT PARSE_JSON(%s)`. That's how `CANVAS_LAYOUTS` gets written.
- **Case handling.** Unquoted identifiers uppercase; the connector returns
  uppercase column names, so the API lowercases them when mapping rows to models.

**Interview answer.** The big one was MFA enforcement breaking headless password auth, which drove the key-pair migration. Beyond that: JSON stored as VARCHAR for embeddings and remaining lots (a portability choice, not a limitation), VARIANT columns needing PARSE_JSON on insert, and the connector returning uppercase columns so the API lowercases them when mapping to models.

---

# SECTION 2 — DBT

## 2.1 What dbt actually is

dbt (data build tool) is a **SQL compilation and execution framework**. It does
not have its own compute — it compiles templated SQL and hands it to the warehouse
(Snowflake) to run. What it adds on top of "SQL files":

- **Dependency management** — you reference models with `ref()`, and dbt builds a
  DAG and runs models in topological order.
- **Templating (Jinja)** — `ref`, `source`, `config`, macros, `env_var`.
- **Testing** — declarative data tests (unique, not_null, relationships, …).
- **Documentation & lineage** — generated from the models + YAML.
- **Materialization strategies** — view/table/incremental/ephemeral as a config,
  not hand-written DDL.

We use **dbt Core** (the open-source CLI) with the **dbt-snowflake adapter**,
version ~1.11. Everything runs from the project's venv; there's no dbt Cloud.

**Interview answer.** "dbt is a transformation framework that compiles Jinja-
templated SQL into warehouse SQL, manages dependencies via a ref-based DAG, and
layers on testing, docs, and materialization strategies. The warehouse does the
compute; dbt orchestrates and governs the SQL."

## 2.2 Medallion architecture: what each layer means for us

- **Bronze / RAW** — a faithful, untransformed, *typed* copy of the source system
  (Postgres `nextech_source`). No business logic. If it's wrong here, it's wrong
  because the source is wrong. Landed by the Python ingestion job, not dbt.
- **Silver / STG (staging)** — one model per source table, one-to-one with RAW.
  Trim strings, rename to our conventions (`role` → `provider_role`), cast to
  standard types (`NUMBER(18,4)` money). Views. No joins, no aggregation.
- **INT (intermediate)** — reusable business-logic building blocks that compose
  staging: visit economics, patient LTV, provider-daily rollups, inventory
  movements. Tables, because multiple marts read them.
- **Gold / MART** — purpose-built, consumer-ready outputs: one per dashboard tab
  or the RAG corpus. Aggregated, denormalized, snapshot at build time. Tables.

**Why medallion over star-schema/Kimball as the organizing principle.** Kimball
(conformed facts + dimensions, star schemas) is about the *shape* of the analytics
layer; medallion is about the *flow and separation of concerns* from source to
consumer. They're not mutually exclusive — several marts are effectively facts
(`int_visit_economics`) or dimension-like rollups (`mart_provider_scorecard`). I
chose medallion as the top-level structure because it gives a clean, testable
boundary at each stage (raw fidelity → cleaning → logic → serving), which is
exactly what you want when the source is a simulated EMR and each layer has a
different failure mode. A strict Kimball star would over-model a demo with 7
providers; medallion lets me be pragmatic per mart while keeping the pipeline
legible. The tradeoff is some denormalization and per-consumer marts rather than
one conformed star — acceptable and arguably better for a dashboard-per-tab product.

**Interview answer.** "Medallion is my top-level structure — raw fidelity,
staging cleaning, intermediate logic, serving marts — because each stage has a
distinct responsibility and failure mode and is independently testable. Kimball
modeling shows up *within* the layers where it helps (facts, dimension rollups);
I didn't impose a strict conformed star on a demo-scale dataset."

## 2.3 Sources vs staging vs intermediate vs marts

- **Sources** (`_sources.yml`) declare the RAW tables to dbt: database
  `DERMIQ_DEV`, schema `RAW_DEL_MAR`, and each table. Referenced with
  `{{ source('nextech', 'transactions') }}`. Sources are also where I put
  **freshness** config (`loaded_at_field: _ingested_at`) and the ADR-005 contract
  tests.
- **Staging** reads sources, one model per source table.
- **Intermediate** reads staging (never sources directly).
- **Marts** read intermediate and staging.

This layering is a rule, not a suggestion: it means a source-column rename only
has to be absorbed once, in staging, and everything downstream refers to our
clean names.

**Interview answer.** Sources declare the RAW tables and carry freshness plus contract tests; staging reads sources one-to-one; intermediate reads staging; marts read intermediate and staging. The layering is a rule, so a source rename is absorbed once in staging and everything downstream uses clean names.

## 2.4 Every model, one line each

Staging (views):
- `stg_nextech__patients` — typed/renamed patients; `is_deleted` from `deleted_at`.
- `stg_nextech__providers` — typed providers; `role` → `provider_role`.
- `stg_nextech__services` — service catalog with `default_price`/`default_cost`.
- `stg_nextech__appointments` — visits with status + actual arrival/departure.
- `stg_nextech__transactions` — line-item revenue events (money → NUMBER(18,4)).
- `stg_nextech__inventory_units` — consumable SKU master + par level + shelf life.
- `stg_nextech__inventory_lots` — received lots with per-lot cost + expiry.
- `stg_nextech__inventory_transactions` — consumption/waste/expiry movements.
- `stg_nextech__inventory_current_stock` — derived on-hand per SKU.

Intermediate (tables):
- `int_visit_economics` — one row per completed visit: net revenue, category
  split, cross-sell flags, duration.
- `int_patient_lifetime_value` — per-patient totals, run-rate, recency/LTV tiers.
- `int_patient_features` — per-patient feature vector feeding clustering.
- `int_provider_daily` — provider×day productivity (visits, revenue, per-hour).
- `int_appointment_disposition` — per-appointment completed/no-show/cancelled flags.
- `int_inventory_movements` — enriched movement grain (service+product+lot context).

Marts (tables):
- `mart_revenue_daily` — one row per day: revenue, category mix, funnel, no-show rate.
- `mart_provider_scorecard` — per-provider TTM scorecard (revenue/hour, cross-sell…).
- `mart_channel_attribution` — per-channel TTM economics (spend, CAC, LTV:CAC).
- `mart_recall_queue` — ranked lapsing patients with revenue at risk.
- `mart_patient_segments` — k-means segment overview (size, value, dominant category).
- `mart_patient_segment_members` — per-patient segment membership.
- `mart_inventory_status` — per-SKU on-hand vs par, days of supply, status.
- `mart_true_margin_by_service` — revenue vs real consumables cost vs catalog margin.
- `mart_expiring_soon` — on-hand lots near expiry with value at risk.

**Interview answer.** Nine staging views mirror the source tables; six intermediate tables hold reusable logic — visit economics, patient LTV, provider-daily, inventory movements; nine marts each serve one dashboard tab. Every mart's grain is one row per the thing it describes — a day, a provider, a channel, a SKU.

## 2.5 Materializations: view / table / incremental / ephemeral

- **view** — a stored query; no data stored, always fresh, but re-runs on every
  read. We use it for **staging** (cheap transform, want live pass-through).
- **table** — fully rebuilt (`CREATE OR REPLACE TABLE AS`) on `dbt run`; stores
  the result. We use it for **intermediate** (reused logic) and **marts**
  (consumer reads). Cost is paid once at build; reads are fast.
- **incremental** — a table that only processes *new/changed* rows on each run
  (via an `is_incremental()` filter and a unique key), for large append-heavy
  facts. We don't use it — our largest table is ~9.6k rows, so a full rebuild is
  cheaper and simpler than the correctness burden of incremental logic. I know
  exactly when I'd switch: when a full rebuild stops fitting the warehouse-minute
  budget.
- **ephemeral** — not materialized at all; inlined as a CTE into downstream
  models. Good for small helper logic you don't want as an object. We don't use
  it; intermediate-as-table is clearer for reuse and debuggability.

Config lives in `dbt_project.yml` (per-layer defaults) and can be overridden
per-model with `{{ config(materialized='table') }}` at the top of the file.

**Interview answer.** "Staging is views — cheap, always current. Intermediate and
marts are tables — pay the build once, fast reads, snapshot semantics. I skip
incremental because full rebuilds are trivially cheap at my scale and avoid the
merge-correctness overhead; I'd adopt it when a rebuild no longer fits the compute
budget."

## 2.6 The Jinja layer: ref, source, config

Real code from `mart_true_margin_by_service.sql`:

```sql
{{ config(materialized='table') }}

with services as (
    select s.* from {{ ref('stg_nextech__services') }} s
    where s.service_code in (select service_code from {{ ref('stg_nextech__inventory_units') }})
),
consumables_ttm as (
    select service_code, sum(quantity) as units_consumed_ttm,
           sum(movement_cost) as consumables_cost_ttm
    from {{ ref('int_inventory_movements') }}
    where consumed_date >= dateadd('month', -12, current_date)
      and movement_type in ('consumption', 'waste')
    group by 1
)
...
```

- `{{ source('nextech', 'transactions') }}` → compiles to the fully-qualified RAW
  table name and registers a dependency on that source.
- `{{ ref('int_inventory_movements') }}` → compiles to
  `DERMIQ_DEV.INT_DEL_MAR.int_inventory_movements` **and** tells dbt this model
  depends on that one.
- `{{ config(...) }}` → sets materialization/schema/etc. for this model.

The key insight: `ref()` isn't just a name-substitution convenience — it's how the
dependency graph is *declared*. I never write a schema name by hand in a model;
`ref` and the `generate_schema_name` macro resolve it.

**Interview answer.** `ref` and `source` aren't just name substitution — they're how dependencies are declared. I never hand-write a schema name in a model: `ref` resolves the fully-qualified name and registers the edge, `config` sets materialization, and the schema macro fills in `LAYER_TENANT`.

## 2.7 How ref() builds the DAG, and execution order

When I run `dbt build`, dbt first **parses** every `.sql` file and extracts each
`ref()` and `source()` call. From those it constructs a **directed acyclic graph**:
an edge from A to B means B `ref`s A. It then executes in **topological order** —
every model runs only after its dependencies, and independent models run in
parallel up to the thread count (we run 4 threads via `profiles.yml`).

So for our project, dbt knows without me telling it: build the staging views
first, then `int_inventory_movements`, then `mart_true_margin_by_service` (which
refs both). If I add a model that refs a mart, dbt slots it after that mart
automatically. This is also what powers **selection**: `dbt build --select
mart_true_margin_by_service+` means "this model and everything downstream";
`+model` means "this and everything upstream."

**Interview answer.** "dbt statically parses every ref/source, builds a DAG, and
runs it in topological order with parallelism across independent branches. The
graph is derived from the code, so dependencies can't drift out of sync with what
the SQL actually reads."

## 2.8 Tests: what we use and where

dbt data tests are just SQL that must return **zero rows** to pass. We use:

- **`unique`** / **`not_null`** — on every primary key (e.g.
  `mart_provider_scorecard.provider_id`, `stg_*` PKs). Severity `error`.
- **`relationships`** — referential integrity: e.g.
  `stg_nextech__inventory_transactions.transaction_id` must exist in
  `stg_nextech__transactions`. This catches orphaned FKs.
- **`accepted_values`** — enumerations: `stock_status` ∈ {out, low, adequate,
  overstock}; `movement_type` ∈ {consumption, waste, expiry}. Severity `warn`.
- **`dbt_utils.expression_is_true`** — arbitrary invariants: on
  `mart_true_margin_by_service`, `true_margin_ttm = revenue_ttm -
  consumables_cost_ttm` and `true_margin_pct <= 1`. This is where I encode
  business rules the schema alone can't.

A real nuance I hit: `inventory_transactions.transaction_id` is `not_null` for
consumption/waste but **null** for expiry write-offs (no sale). A plain `not_null`
test failed. I replaced it with a model-level
`expression_is_true: transaction_id is not null or movement_type = 'expiry'` —
the correct, condition-aware invariant. That's a good "I understand my data" story.

**Interview answer.** "Tests are SQL that must return no rows. I put unique/
not_null on keys, relationships for FK integrity, accepted_values for enums, and
expression_is_true for real business invariants like margin identities. When a
plain not_null didn't fit expiry rows, I wrote a conditional invariant instead."

## 2.9 The generate_schema_name macro

By default dbt names a model's schema `<target_schema>_<custom_schema>`. I override
that so it matches the platform convention `<LAYER>_<TENANT>`:

```jinja
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set tenant = (var('tenant', '') | trim) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif tenant == '' -%}
        {{ custom_schema_name | trim | upper }}
    {%- else -%}
        {{ (custom_schema_name ~ '_' ~ tenant) | trim | upper }}
    {%- endif -%}
{%- endmacro %}
```

The `+schema:` config on each layer supplies the layer part (`stg`/`int`/`mart`);
the `tenant` var (from `DEFAULT_TENANT_ID`) supplies the tenant. So a staging model
lands in `STG_DEL_MAR`, a mart in `MART_DEL_MAR`. This is the dbt-side mirror of
`platform_core.warehouse.schemas.schema_name`, so ingestion and dbt agree.

**Interview answer.** "I override `generate_schema_name` so schemas are
`LAYER_TENANT`, not dbt's default concatenation. Layer comes from each model's
schema config, tenant from a var — the same convention my Python ingestion uses,
enforced in one macro."

## 2.10 Compiled SQL vs source SQL, and the manifest

When I run dbt, it **compiles** each model — resolves all Jinja (`ref`, `source`,
`config`, macros) into plain Snowflake SQL — and writes the result to
`target/compiled/…`. The **run** step wraps that compiled SELECT in the
materialization DDL (`CREATE OR REPLACE TABLE … AS <compiled select>` for a table,
`CREATE VIEW` for a view) and executes it. `target/run/…` holds that final DDL.

`target/manifest.json` is the compiled representation of the whole project — every
node, its dependencies, config, columns, and tests. It's what powers docs,
lineage, state-based selection (`--select state:modified`), and any external tool
that wants to understand the project. When I debug "what did dbt actually send to
Snowflake," I read `target/compiled` and `target/run`.

**Interview answer.** "dbt compiles Jinja to raw SQL in `target/compiled`, wraps
it in materialization DDL in `target/run`, and emits a `manifest.json` describing
the whole DAG. That manifest is the backbone for docs, lineage, and incremental
selection."

## 2.11 Seeds

`marketing_spend` is a **seed**: a CSV checked into the repo that dbt loads into
`SEED_DEL_MAR.marketing_spend` with `dbt seed` (and as part of `dbt build`). I
declare explicit column types in `dbt_project.yml`
(`month_start: date, spend_usd: number(12,2)`) so it doesn't get type-inferred.

Why track it in git: ad spend per channel per month is small, static reference
data that isn't in the EMR source — it belongs with the code, is versioned, and
`mart_channel_attribution` joins to it for CAC/LTV:CAC. Seeds are for exactly this:
small, hand-maintained lookup/reference data, not for loading real fact volume.

**Interview answer.** `marketing_spend` is a CSV seed with explicit column types, versioned in git because ad spend is small, static reference data that isn't in the EMR source. Seeds are for exactly that — hand-maintained lookups — not for loading real fact volume.

## 2.12 Snapshots — why we don't (yet)

dbt **snapshots** implement slowly-changing-dimension (Type 2) history: they watch
a table and, on each run, record changes with validity ranges
(`dbt_valid_from`/`dbt_valid_to`). We don't use them because our source is
full-refreshed and we don't need point-in-time history of, say, a patient's tier
over time. I'd add a snapshot the moment a stakeholder asked "what was this
provider's scorecard as of last quarter" and I needed to reconstruct it — that's
the SCD-2 use case.

**Interview answer.** Snapshots are dbt's SCD-2 history capture. I don't use them because the source is full-refreshed and I don't need point-in-time history yet — I'd add one the moment someone asked 'what was this scorecard as of last quarter.'

## 2.13 dbt Core vs Cloud; the adapter; profiles.yml

- **Core vs Cloud.** We use **Core** — the CLI, self-hosted, free, orchestrated by
  Airflow/Cosmos. dbt Cloud adds a hosted scheduler, IDE, and CI. I don't need
  Cloud's scheduler because Airflow already owns orchestration; Core keeps the
  stack self-contained and the cost at zero.
- **Adapter.** `dbt-snowflake` is the plugin that translates dbt's generic
  operations into Snowflake SQL and manages the connection. It knows Snowflake's
  DDL dialect, its `CREATE OR REPLACE`, clustering keys, and — importantly for us
  — key-pair auth.
- **profiles.yml.** Holds the connection config, fully env-driven. The key detail
  is that it uses **key-pair**, not password:

```yaml
outputs:
  dev:
    type: snowflake
    account: "{{ env_var('SNOWFLAKE_ACCOUNT') }}"
    user: "{{ env_var('SNOWFLAKE_USER') }}"
    private_key_path: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PATH') | replace('~', env_var('HOME')) }}"
    private_key_passphrase: "{{ env_var('SNOWFLAKE_PRIVATE_KEY_PASSPHRASE') }}"
    role: "{{ env_var('SNOWFLAKE_ROLE', 'ACCOUNTADMIN') }}"
    warehouse: "{{ env_var('SNOWFLAKE_WAREHOUSE', 'COMPUTE_WH') }}"
    database: "{{ env_var('SNOWFLAKE_DATABASE', 'DERMIQ_DEV') }}"
    threads: 4
```

Password auth would set `password:` instead of the two `private_key_*` keys. A
subtlety I had to handle: the connector doesn't expand `~`, so I replace it with
`$HOME` in the Jinja. This was a real fix — dbt was still on password auth after
the platform-core keypair migration, so `dbt build` would have failed under MFA
until I migrated the profile too.

**Interview answer.** I run dbt Core because Airflow already owns scheduling, so I don't need dbt Cloud's hosted scheduler; Core keeps the stack self-contained and free. The dbt-snowflake adapter translates to Snowflake SQL and handles key-pair auth, which `profiles.yml` is configured for — the practical difference from password auth being `private_key_path`/`passphrase` instead of a `password`.

## 2.14 Documentation generation

`dbt docs generate` compiles the project + reads the YAML descriptions and column
docs, producing `catalog.json` + `manifest.json`; `dbt docs serve` serves a
browsable site with a searchable model list, column-level descriptions, test
coverage, and an **interactive lineage graph** (the DAG). It's how I'd onboard
someone: the lineage view shows source → staging → int → mart at a glance.

**Interview answer.** `dbt docs generate` + `serve` produces a browsable site with column-level descriptions, test coverage, and an interactive lineage graph straight from the manifest — it's how I'd onboard someone to the model DAG.

---

# SECTION 3 — AIRFLOW + ASTRONOMER COSMOS

## 3.1 What Airflow is, mechanically

Airflow is a workflow orchestrator with four moving parts:

- **Scheduler** — the loop that reads DAG definitions, decides which DAG runs and
  tasks are due, and queues task instances. It continuously evaluates schedules
  and dependencies.
- **Executor** — the component that actually runs queued tasks. In our local dev
  it's the **LocalExecutor** (subprocesses on one machine); in prod you'd use
  **Celery** (a worker pool) or **Kubernetes** (one pod per task).
- **Metadata database** — a Postgres DB where Airflow stores all state: DAG runs,
  task instance states, XComs, connections, variables. This is the source of
  truth; the scheduler and webserver are stateless against it.
- **Webserver** — the Flask UI that renders DAGs, run history, logs, and lets you
  trigger/clear tasks. It reads the metadata DB.

A **DAG** is a Python file defining tasks and their dependencies. A **Task** is one
node; an **Operator** is the template that defines what a task *does*
(`PythonOperator` runs a Python callable, `PythonSensor` polls a condition, a
`BashOperator` runs a shell command). Airflow is "config as code" — the DAG is
Python, evaluated at parse time to build the graph.

**Interview answer.** "Scheduler decides what runs and when; executor runs it;
a metadata Postgres holds all state; a webserver visualizes it. DAGs are Python
files; tasks are instances of operators. It's declarative dependencies over
imperative task bodies."

## 3.2 Our daily DAG: `del_mar_pipeline`

```python
with DAG(
    dag_id="del_mar_pipeline",
    schedule="0 6 * * *",          # daily at 06:00
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["dermiq", "del_mar"],
) as dag:
    wait_for_postgres >> extract >> dbt_build >> notify
```

- **Schedule `0 6 * * *`** — cron for 6am daily. I picked 6am so the warehouse and
  marts are fresh before the practice's business day; the RAG refresh runs at 7am
  *after* it, and weekly clustering runs Monday 3am *before* it. `catchup=False`
  means if the scheduler was down, I don't backfill every missed day — I only run
  the next scheduled interval.
- **`wait_for_postgres`** — a `PythonSensor` that tries to connect to the source
  Postgres. `mode="reschedule"` (frees the worker slot between pokes instead of
  holding it), `poke_interval=15s`, `timeout=300s`. If Postgres never comes up in
  5 minutes, the sensor fails and the downstream tasks don't run.
- **`extract_postgres_to_snowflake`** — a `PythonOperator` calling
  `ingest_source_to_raw`, which full-refreshes every source table into
  `RAW_DEL_MAR` with explicit types. It **xcom_pushes** the per-table row counts.
- **`dbt_build`** — a **Cosmos `DbtTaskGroup`** (see 3.6) that renders every dbt
  model as its own Airflow task and runs stg → int → mart.
- **`notify_complete`** — a `PythonOperator` that xcom_pulls the row counts and
  logs a summary.

**What happens on failure.** Each task has `retries=2, retry_delay=2min`. If
`extract` fails (e.g. Snowflake token expired), Airflow retries it twice with a
2-minute backoff before marking it failed. A failed task **stops its downstream**
— `dbt_build` won't run if `extract` failed — but upstream/parallel branches are
unaffected. Because Cosmos renders dbt as per-model tasks, a failure *inside* the
dbt build (say `mart_recall_queue` errors) fails only that task and its
downstream; the marts that already built are done and don't rebuild on retry. And
because every task is idempotent (full-refresh / `CREATE OR REPLACE`), a retry is
safe — it just recomputes from source.

**Interview answer.** `del_mar_pipeline` runs 06:00 daily: a reschedule-mode sensor waits for the source, `extract` full-refreshes RAW and xcom-pushes row counts, a Cosmos task group runs dbt stg→int→mart, and `notify` summarizes. Each task retries twice; a failure stops only its downstream, and idempotent full-refresh makes retries safe.

## 3.3 The Astronomer distribution and the 4-container architecture

**Astro CLI** (`astro dev start`) is Astronomer's local dev wrapper around
Airflow. Beyond vanilla Airflow it gives a project scaffold (`Dockerfile`,
`requirements.txt`, `packages.txt`, `airflow_settings.yaml`), a reproducible image
build, and one-command local spin-up. `astro dev start` brings up **four
containers**:

1. **webserver** — the UI (port 8080).
2. **scheduler** — the scheduling loop + (with LocalExecutor) task execution.
3. **triggerer** — runs **deferrable** tasks/async sensors off the worker,
   efficiently waiting on external events without holding a slot.
4. **postgres** — the **metadata database** (separate from our *source* Postgres;
   this one is Airflow's own state store).

**Why each exists:** separation of concerns — the UI shouldn't schedule, the
scheduler shouldn't hold the web session, deferred waits shouldn't burn worker
slots, and state must be durable and shared, hence its own DB.

**Local vs production.** Locally, state lives in that container Postgres and dies
with `astro dev kill` (ephemeral); executor is Local. In prod (Astro Cloud or
self-managed), the metadata DB is an external managed Postgres (durable), the
executor is Celery/Kubernetes for horizontal scale, and deploys ship the image to
the platform. The DAG code doesn't change — only where state lives and how tasks
are distributed.

**Interview answer.** "`astro dev start` runs four containers — webserver,
scheduler, triggerer, and a metadata Postgres — each isolating one concern. Prod
swaps the ephemeral metadata DB for a managed one and LocalExecutor for
Celery/Kubernetes, but the DAGs are identical."

## 3.4 Connections and config — how our tasks actually get credentials

A subtlety worth being precise about in an interview: Airflow has a built-in
**Connections** store (typed credentials in the metadata DB, e.g. a
`snowflake_default` conn), and `airflow_settings.yaml` is where the Astro CLI can
seed those for local dev. In **our** project, `airflow_settings.yaml` is still the
default template — I did **not** wire connections through it. Instead, the task
bodies get their config the same way the rest of the codebase does: through
**platform-core's env-driven Settings** and the shared `.env`. `_extract` calls
`get_snowflake_connection()` (which reads `SNOWFLAKE_*` env, key-pair auth), and
`_wait_for_postgres` reads `POSTGRES_SOURCE_READER_URL` from the environment. The
sibling repos are **bind-mounted** into the container (`docker-compose.override.yml`)
and added to `sys.path`, and dbt runs from an isolated venv.

I'm candid about this: it's a deliberate simplification for a single-tenant demo —
one config surface (`.env`) drives platform-core, ingestion, dbt, and the DAGs. In
a multi-tenant prod deploy I'd move Snowflake/Postgres creds into Airflow
Connections (encrypted in the metadata DB, referenced by conn_id) so secrets
aren't in a mounted file and can be rotated per environment.

**Interview answer.** In this project config comes from env/`.env` via platform-core Settings, not Airflow Connections — one config surface drives ingestion, dbt, and the DAGs for a single-tenant demo. In prod I'd move the Snowflake/Postgres creds into Airflow Connections so secrets are encrypted in the metadata DB and rotatable per environment.

## 3.5 Sensors, retries, idempotency, backfills

- **Sensor** — `wait_for_postgres` polls until the source DB is reachable. In
  `reschedule` mode it releases the worker between pokes (poke every 15s, give up
  after 300s), which is the efficient choice for anything that might wait a while.
- **Retries / backoff** — `retries=2, retry_delay=2min` on every task. Airflow
  reschedules a failed task after the delay, up to the retry count, then marks it
  failed (and its downstream `upstream_failed`). You can configure exponential
  backoff; I use a flat 2-minute delay, which is plenty for transient Snowflake/
  network blips.
- **Idempotency** — a task is idempotent if running it twice yields the same state
  as running it once. Ours are: ingestion is `CREATE OR REPLACE` full-refresh; dbt
  models are `CREATE OR REPLACE`; the seed generators are deterministic
  (fixed RNG seed). So a retry (or a manual re-run) never double-counts or
  corrupts — it recomputes from source. This is *why* retries are safe.
- **Backfill** — to (re)run a historical range you'd `airflow dags backfill -s
  <start> -e <end> del_mar_pipeline`. Because `catchup=False`, Airflow won't do
  this automatically for missed schedules; a backfill is an explicit operator
  action. For us backfilling is mostly moot — full-refresh means "yesterday's run"
  and "today's run" produce the same marts from the current source.

**Interview answer.** Sensors poll in reschedule mode so waiting doesn't hold a worker slot; tasks retry twice with a 2-minute backoff; every task is idempotent (full-refresh / CREATE OR REPLACE / seeded RNG), which is why retries and re-runs are safe; and with `catchup=False`, backfills are an explicit operator action, not automatic.

## 3.6 Astronomer Cosmos — what it actually does

Cosmos is the library that turns a dbt project into **native Airflow tasks**. In
the DAG:

```python
dbt_build = DbtTaskGroup(
    group_id="dbt_build",
    project_config=ProjectConfig(DBT_PROJECT_PATH),
    profile_config=ProfileConfig(
        profile_name="dermiq", target_name="dev",
        profiles_yml_filepath=Path(DBT_PROJECT_PATH) / "profiles.yml",
    ),
    execution_config=ExecutionConfig(dbt_executable_path=DBT_EXECUTABLE),
    render_config=RenderConfig(dbt_executable_path=DBT_EXECUTABLE),
)
```

Mechanically: at **DAG parse time**, Cosmos reads `dbt_project.yml` and discovers
the dbt DAG (its default render mode runs `dbt ls` / parses the manifest to
enumerate models and their dependencies). It then **renders one Airflow task per
dbt model** inside a task group, wiring the Airflow dependencies to mirror the dbt
`ref` graph. At **run time**, each task invokes dbt for just that node (effectively
`dbt run --select <model>` via the configured executable), plus its tests.

**Why Cosmos over `BashOperator` + `dbt build`.** The naive approach is one
`BashOperator` that shells out to `dbt build`. Cosmos gives me:
- **Per-model task granularity** — I see exactly which model failed in the Airflow
  UI, and retry *only* that model and its downstream, not the whole build.
- **Native task-graph visibility** — the dbt lineage shows up as the Airflow graph,
  not as opaque logs inside one task.
- **Per-model retries/observability** — each model gets Airflow's retry, timing,
  and logging.
The tradeoff is more moving parts and parse-time overhead (Cosmos has to render
the graph), but for anything beyond a trivial project the observability wins.

**Cosmos vs the dbt-cloud operator.** The dbt-cloud operator triggers a job in
dbt **Cloud** and polls it — it needs a dbt Cloud account and runs the build as
one remote job (no per-model Airflow tasks). I use dbt **Core**, so Cosmos is the
natural fit: it keeps execution local/self-hosted and gives the per-model graph
that dbt Cloud's single-job model doesn't surface in Airflow.

**Interview answer.** "Cosmos parses the dbt project at DAG-parse time and renders
each dbt model as its own Airflow task in a task group, mirroring the ref graph. I
chose it over a single `dbt build` BashOperator for per-model retries and native
graph visibility, and over the dbt-cloud operator because I run dbt Core, not
Cloud."

## 3.7 Task groups, XComs, the metadata DB, the scheduler loop, the executor

- **Task groups** — a UI/organizational grouping of tasks (Cosmos puts the whole
  dbt graph in a `dbt_build` group). They collapse into one node you can expand;
  purely visual/logical, not a separate execution unit.
- **XComs** — "cross-communication": small values tasks pass through the metadata
  DB. We use one: `extract` pushes `row_counts`, `notify` pulls it. XComs are for
  *small* metadata, not data payloads — the actual data goes through Snowflake, not
  XCom.
- **Metadata DB contents** — DAG definitions' run history, task instance states
  (queued/running/success/failed/up_for_retry), XComs, connections, variables,
  pools. It's the durable brain.
- **Scheduler loop** — continuously: parse DAG files, for each DAG compute which
  intervals are due (based on `schedule` + `start_date` + last run), create DAG
  runs, and queue task instances whose upstream dependencies are met. It hands
  queued tasks to the executor.
- **Executor** — LocalExecutor here (subprocesses on the scheduler host). In prod,
  Celery pulls tasks off a broker to a worker fleet, or Kubernetes launches a pod
  per task for full isolation and elastic scale.

**Interview answer.** Task groups organize the UI; XComs pass small metadata through the metadata DB (I use one — row counts); the scheduler loop evaluates schedules and queues due tasks whose upstreams are met; the executor runs them — LocalExecutor here, Celery or Kubernetes in prod.

## 3.8 The other two DAGs

- **`weekly_clustering`** (ADR-007) — `schedule="0 3 * * MON"` (Monday 3am, ahead
  of the daily 6am so fresh segments feed the day). Tasks:
  `wait_for_snowflake` (PythonSensor) → `run_clustering` (PythonOperator calling
  `scripts.run_clustering.main`, which refits k-means and writes the assignments)
  → `dbt_rebuild_segments` (a Cosmos `DbtTaskGroup` with
  `select=["mart_patient_segments", "mart_patient_segment_members"]` — I select
  both explicitly because they're siblings, not a parent+downstream) → `notify`.
  It's separate from the daily pipeline because re-clustering is expensive and
  doesn't need to run daily; weekly cadence keeps segments stable.
- **`rag_corpus_refresh`** (ADR-008) — `schedule="0 7 * * *"` (7am, after the daily
  pipeline so the corpus snapshots track the latest marts). Tasks:
  `wait_for_snowflake` → `build_corpus` (PythonOperator calling
  `scripts.build_rag_corpus.main`, which rebuilds the documents from the marts,
  re-embeds with sentence-transformers, and full-refreshes `RAG_CORPUS`) →
  `notify`. No Cosmos — it's pure Python, not dbt.

**Cross-DAG lineage.** Monday: 3am clustering → 6am daily pipeline (ingest + dbt) →
7am RAG refresh. Other days: 6am daily → 7am RAG. The DAGs are decoupled (no direct
task dependencies across DAGs); their **ordering by clock** is the coordination
mechanism, with each starting with a `wait_for_*` sensor so a late upstream just
delays, rather than breaks, the dependent job.

**Interview answer.** Two more DAGs: `weekly_clustering` (Mon 3am) refits k-means and rebuilds the segment marts; `rag_corpus_refresh` (7am) rebuilds and re-embeds the RAG corpus. They're decoupled and coordinated by clock — each opens with a `wait_for` sensor, so a late upstream delays rather than breaks the dependent job.

## 3.9 What could go wrong, and how I'd debug it

- **`extract` fails with token expired** → Snowflake JWT/session issue; check the
  task log, confirm `.env` key-pair vars, that the public key is still on the user.
  Retries usually ride out transient blips.
- **A dbt model task fails** → open that specific Cosmos task's log; it shows the
  compiled SQL and the Snowflake error. Fix the model, `clear` that task and its
  downstream in the UI to re-run just the affected subgraph.
- **Sensor times out** → source Postgres never came up; the daily pipeline
  correctly does nothing rather than ingesting a stale/empty source.
- **Scheduler not triggering** → check it's running, the DAG isn't paused, and the
  file parses (a parse error hides the DAG from the UI).

**Interview answer.** Most failures are a token expiry on `extract` (a retry usually rides it out; otherwise check the `.env` key-pair vars) or a single dbt model erroring (open that Cosmos task's log for the compiled SQL and Snowflake error, fix it, and `clear` just that subgraph). A sensor timeout means the source never came up, and the pipeline correctly does nothing rather than ingest stale data.

---

# APPENDICES

## Appendix A — Interview questions and canned answers

**1. Why medallion architecture?** Each stage has one responsibility and a
distinct failure mode — RAW is source fidelity, staging is cleaning/typing,
intermediate is reusable logic, marts are serving. That makes every boundary
independently testable and keeps a source change absorbed once (in staging). I use
Kimball-style modeling *within* layers where it helps, but medallion is the flow.

**2. How does dbt do dependency resolution?** It statically parses every `ref()`
and `source()` at parse time, builds a DAG, and executes in topological order with
parallelism across independent branches. The graph is derived from the SQL, so it
can't drift from what the code actually reads.

**3. What happens if the dbt_build task fails partway through?** Because Cosmos
renders each model as its own Airflow task, only the failing model and its
downstream stop; already-built models are done. Each task retries twice with
backoff. On a manual re-run I `clear` just the failed subgraph. And because every
model is `CREATE OR REPLACE`, re-running is idempotent — no partial-state
corruption.

**4. Why Cosmos over a BashOperator running `dbt build`?** Per-model task
granularity (see and retry the exact model that failed), native graph visibility
in the Airflow UI, and per-model retries/logging — versus one opaque task where
any failure means rerunning everything.

**5. How does Snowflake charge you?** Compute by the **credit-second** while a
warehouse runs (XS = 1 credit/hour, 60-second minimum per resume), plus storage
by the terabyte-month, plus some cloud-services overage. Auto-suspend means you pay
only for the seconds of query time; a resource monitor caps the credits.

**6. Walk me through what happens when a user visits localhost:3000.** Next.js
serves the page shell; a client component fires TanStack-Query calls to the FastAPI
`/api/v1/*` endpoints with an `X-Tenant-ID` header. FastAPI resolves the tenant,
takes a cursor off its long-lived key-pair Snowflake connection, runs a
parameterized SELECT against a `MART_DEL_MAR` table, maps rows (lowercasing
columns) to Pydantic models — money as Decimal strings for precision — and returns
JSON. The component renders it with Recharts.

**7. Where does Snowflake store data physically?** In immutable, columnar,
compressed **micro-partitions** in cloud object storage (S3), with per-partition
min/max metadata in the cloud-services layer. No warehouse owns the data;
warehouses read it over the network.

**8. Walk me through Postgres → Snowflake.** The daily DAG's sensor confirms the
source is up; the `extract` task calls `ingest_source_to_raw`, which for each
source table reads it via the least-privilege reader role, `CREATE OR REPLACE`s
the RAW table from an **explicit type map** (not inference), and `write_pandas`
appends the rows — full-refresh. It stamps lineage columns (`_ingested_at`,
`_source_table`). Then dbt takes over from RAW.

**9. How does dbt know what depends on what?** The `ref()`/`source()` calls. dbt
parses them into a DAG; I never hand-write a schema or declare an order.

**10. Why views for staging, tables for marts?** Staging transforms are cheap and
I want live pass-through, so views cost nothing to store and are always current.
Marts are read repeatedly by consumers and want a stable build-time snapshot, so
tables — pay the build once, fast reads.

**11. What's a micro-partition and why does it matter?** A ~16MB-compressed
immutable columnar file with min/max metadata per column. It matters because
queries **prune** partitions using that metadata and read only referenced columns,
so cost scales with the filter, not the table.

**12. How does key-pair auth work?** Public key on the Snowflake user; the client
signs a short-lived JWT with the private key each connection; Snowflake verifies
the signature. No interactive second factor, so it works headless — which is why I
adopted it when MFA enforcement broke password auth.

**13. What happens if an Airflow task fails halfway?** It retries per its config
(2×, 2-min backoff), then marks failed and sets downstream `upstream_failed`.
Parallel branches are unaffected. Idempotent tasks make retries safe.

**14. How does Cosmos translate dbt to Airflow?** At parse time it reads the dbt
project (via `dbt ls`/manifest), enumerates models + dependencies, and renders one
Airflow task per model in a task group, wiring Airflow deps to match the dbt ref
graph. At run time each task runs dbt for that single node.

**15. Why not incremental models?** My largest table is ~9.6k rows; a full rebuild
runs in seconds and avoids incremental's merge-correctness complexity. I'd switch
when a rebuild stops fitting the compute budget.

**16. How do you control Snowflake cost?** XS warehouse + aggressive auto-suspend
(steady-state ≈ zero), and a resource monitor as the hard credit cap.

**17. What's the difference between a database, schema, and warehouse?** Database
and schema are the *namespace* for data (logical). A warehouse is *compute*.
They're orthogonal — a warehouse can query any database it has grants on.

**18. Why one database with tenant schemas, not a database per tenant?** At this
scale it keeps cross-layer `ref`s and grants simple; isolation comes from the
schema split (and row-access policies in prod). Database-per-tenant is heavier
operationally than a demo needs.

**19. How do you test data quality?** dbt tests that must return zero rows:
unique/not_null on keys, relationships for FKs, accepted_values for enums,
expression_is_true for business invariants like the margin identity.

**20. What's the RAG storage design and why not a VECTOR type?** Embeddings are
JSON strings in a VARCHAR column, ranked by in-process cosine. It's portable — the
store interface is backend-agnostic, so pgvector or a native VECTOR can drop in
later without changing callers.

**21. How does the schema naming stay consistent between Python and dbt?** One
convention, two mirrors: `platform_core.warehouse.schemas.schema_name` (Python)
and the `generate_schema_name` macro (dbt), both producing `LAYER_TENANT`.

**22. What does the triggerer container do?** Runs deferrable/async tasks and
sensors off the worker so waiting on external events doesn't hold an execution
slot.

**23. What's in Airflow's metadata database?** DAG-run and task-instance state,
XComs, connections, variables, pools — all durable orchestration state. The
scheduler and webserver are stateless against it.

**24. Do you use XComs, and for what?** One: the extract task pushes per-table row
counts, the notify task pulls them for a summary. XComs are for small metadata; the
real data moves through Snowflake.

**25. Why 6am for the daily run?** Fresh marts before the practice's business day;
RAG refresh at 7am after it; weekly clustering Monday 3am before it. The clock is
the cross-DAG coordination, with a sensor at each start so a late upstream delays
rather than breaks the dependent job.

**26. What's zero-copy cloning good for?** Instant, near-free dev environments:
`CREATE DATABASE … CLONE` points at the same immutable partitions (copy-on-write),
so each dev gets an isolated database off prod without duplicating storage.

**27. What happens on a Snowflake token expiry in the API?** The pinned long-lived
connection eventually dies (master-token hard cap); `/health` reports unreachable;
today I restart to re-auth; the real fix is reconnect-on-reauth-error. I'm explicit
that this is known tech debt.

**28. What's the compiled vs source SQL distinction?** Source has Jinja; dbt
compiles it to raw SQL (`target/compiled`), wraps it in materialization DDL
(`target/run`), and executes. `manifest.json` describes the whole project.

**29. Why Recharts, and how does the Canvas generate charts?** Recharts is in the
stack with a simple component model. Canvas uses LLM **tool-use** (one tool per
chart type) to produce a validated chart spec over a curated mart schema, which
resolves to a parameterized query — no model-authored SQL, no hallucinated columns.

**30. How would you make this multi-tenant?** The schema convention already
namespaces by tenant; I'd add real auth (replace the `X-Tenant-ID` stub),
per-tenant row-access policies, move creds into Airflow Connections, and
parameterize the tenant var across ingestion/dbt/DAGs.

**31. What's the difference between LocalExecutor and Celery/Kubernetes?** Local
runs tasks as subprocesses on one host (fine for dev). Celery distributes tasks to
a worker pool via a broker; Kubernetes launches a pod per task for isolation and
elastic scale — both for prod throughput.

**32. Why full-refresh ingestion instead of CDC?** The source is a small simulated
EMR; a faithful full copy is simplest and idempotent. CDC (log-based incremental)
is the answer at real volume where re-copying everything is too expensive.

## Appendix B — End-to-end data flow (ASCII)

```
 ┌──────────────────────┐
 │ Postgres source DB   │  nextech_source schema (fake Nextech EMR)
 │ (docker-compose)     │  seeded by scripts/seed_postgres.py + seed_inventory.py
 └──────────┬───────────┘
            │  scripts/ingest_raw.py → dermiq/ingestion/source_to_raw.py
            │  (least-privilege read; CREATE OR REPLACE with explicit types; full refresh)
            ▼
 ┌──────────────────────┐
 │ Snowflake RAW_DEL_MAR│  typed 1:1 copy + lineage cols (_ingested_at, _source_table)
 └──────────┬───────────┘
            │  dbt (Cosmos-orchestrated): ref() DAG, topological order
            ▼
 STG_DEL_MAR (views)  →  INT_DEL_MAR (tables)  →  MART_DEL_MAR (tables)
   rename/typecast        visit economics,          revenue_daily, provider_scorecard,
                          patient LTV, provider      channel_attribution, recall_queue,
                          daily, inventory mvmts     segments(+members), inventory_status,
                                                     true_margin, expiring_soon
            │                                         │
            │                                         ├── FastAPI /api/v1/* (key-pair conn,
            │                                         │     parameterized SELECTs over marts)
            │                                         │        │
            │                                         │        ▼
            │                                         │   Next.js dashboard (localhost:3000)
            │                                         │   7 tabs + Canvas + AI Studio
            │                                         │
            │   scripts/build_rag_corpus.py           │   Canvas: NL prompt → LLM tool-use →
            │   (marts → docs → sentence-transformer  │   validated chart spec → /canvas/query
            │    embeddings → JSON in VARCHAR)        │   → parameterized SELECT over marts
            ▼                                         │
 MART_DEL_MAR.RAG_CORPUS  ──── /chat: embed query, in-process cosine top-k,
                               Claude (claude-sonnet-5) generates grounded answer

 Orchestration (Airflow / Astronomer + Cosmos):
   weekly_clustering   Mon 03:00  → refit k-means → rebuild segment marts
   del_mar_pipeline    daily 06:00 → wait_for_postgres → extract → dbt_build(Cosmos) → notify
   rag_corpus_refresh  daily 07:00 → wait_for_snowflake → build_corpus → notify
```

## Appendix C — Key files in both repos

**dermiq/**
- `dermiq/ingestion/source_to_raw.py` — Postgres → Snowflake RAW, explicit typed load.
- `dermiq/ingestion/types.py` — the explicit RAW column type map (ADR-005).
- `dermiq/seed/{catalog,patients,appointments,inventory}.py` — synthetic data generators.
- `dermiq/canvas/{schema,schemas,query,generation}.py` — Canvas: mart schema, chart grammar, SQL resolver, LLM tool-use.
- `dermiq/rag/corpus.py` — builds RAG documents from the marts.
- `dermiq/api/main.py` — FastAPI app + lifespan-managed Snowflake connection.
- `dermiq/api/routers/{meta,marts,segments,chat,inventory,canvas}.py` — endpoints.
- `dermiq/api/fqn.py` / `deps.py` — schema-name resolution + shared deps (tenant, cursor, fetch_models).
- `transform/dbt_project.yml` — dbt config (per-layer materializations, tenant var).
- `transform/profiles.yml` — dbt Snowflake connection (key-pair).
- `transform/macros/generate_schema_name.sql` — LAYER_TENANT schema naming.
- `transform/models/{staging,intermediate,marts}/` — the dbt models + `_*.yml` tests.
- `transform/seeds/marketing_spend.csv` — ad-spend reference seed.
- `airflow/dags/{del_mar_pipeline,weekly_clustering,rag_corpus_refresh}.py` — the 3 DAGs.
- `airflow/{Dockerfile,requirements.txt,docker-compose.override.yml}` — Astro project.
- `infra/postgres/init/{01_schema,02_inventory}.sql` — source DB schema.
- `frontend/src/app/(tabs)/*/page.tsx` — dashboard tabs incl. `canvas/`.
- `frontend/src/components/canvas/*` — 6 Recharts chart components.
- `frontend/src/lib/{api,types}.ts` — typed API client + types.
- `scripts/{seed_postgres,seed_inventory,ingest_raw,run_clustering,build_rag_corpus,run_api}.py`.
- `docs/{SETUP,API,DECISIONS,PROJECT_STATUS,DEMO_SCRIPT,STUDY_GUIDE}.md`.

**platform-core/**
- `platform_core/config/__init__.py` — Pydantic Settings (env-driven).
- `platform_core/warehouse/connection.py` — Snowflake connection (key-pair/password).
- `platform_core/warehouse/schemas.py` — `schema_name(layer, tenant)` convention.
- `platform_core/rag/{embedder,store,retrieve}.py` — RAG toolkit.
- `platform_core/llm/anthropic_client.py` — Claude client.
- `platform_core/utils/logging.py` — structlog JSON logging.

## Appendix D — Glossary

- **Medallion architecture** — layered data design: raw → staging → intermediate → marts, each with one responsibility.
- **DAG** — directed acyclic graph; in Airflow, a workflow of tasks with dependencies; in dbt, the model dependency graph.
- **Mart** — a consumer-ready, aggregated/denormalized analytics table (gold layer).
- **Dimension** — a categorical attribute you group/slice by (provider, channel, category).
- **Measure** — a numeric value you aggregate (revenue, count, margin).
- **Micro-partition** — Snowflake's immutable ~16MB-compressed columnar storage file with per-column min/max metadata.
- **Partition pruning** — skipping micro-partitions that can't match a filter, using their metadata.
- **Virtual warehouse** — Snowflake's on-demand compute cluster; billed per credit-second.
- **Credit** — Snowflake's compute billing unit (XS warehouse = 1/hour).
- **Auto-suspend** — a warehouse pausing after idle to stop billing.
- **Resource monitor** — a credit-quota guardrail that can suspend a warehouse at a threshold.
- **Time Travel** — querying/restoring table state within a retention window.
- **Zero-copy clone** — an instant copy-on-write copy of a DB/schema/table.
- **JWT** — JSON Web Token; a signed, short-lived credential.
- **Key-pair auth** — auth via a private key signing a JWT verified by a registered public key.
- **VARIANT** — Snowflake's semi-structured (JSON) column type.
- **dbt** — SQL transformation framework: compiles Jinja SQL, manages a ref DAG, tests, docs.
- **Materialization** — how a dbt model is persisted (view/table/incremental/ephemeral).
- **ref() / source()** — dbt functions that resolve a name *and* declare a dependency.
- **Seed** — a CSV loaded by dbt as a small reference table.
- **Snapshot** — dbt's SCD-2 history capture (we don't use it yet).
- **Manifest** — dbt's compiled project description (`target/manifest.json`).
- **Adapter** — dbt plugin translating to a specific warehouse (dbt-snowflake).
- **Operator** — an Airflow task template (PythonOperator, PythonSensor, …).
- **Sensor** — an operator that waits/polls for a condition.
- **Executor** — the Airflow component that runs queued tasks (Local/Celery/Kubernetes).
- **Scheduler** — the Airflow loop that decides what to run and when.
- **XCom** — small cross-task value passed via the metadata DB.
- **Triggerer** — the container running deferrable/async tasks off the worker.
- **Cosmos** — Astronomer library rendering a dbt project as native Airflow tasks.
- **Astro CLI** — Astronomer's local Airflow dev tooling (`astro dev start`).
- **Idempotent** — running twice yields the same state as once.
- **Backfill** — running a DAG over a historical date range.
- **RAG** — retrieval-augmented generation: retrieve grounding docs, then have an LLM answer.
- **Tool-use** — forcing an LLM to return structured output by "calling" typed tools.

## Appendix E — Rapid-fire flashcards (50)

1. Q: Storage/compute in Snowflake? A: Separated — data in object storage, warehouses are ephemeral compute.
2. Q: What is COMPUTE_WH? A: Our XS virtual warehouse, auto-suspending.
3. Q: XS credit rate? A: ~1 credit/hour, billed per second, 60s minimum per resume.
4. Q: Micro-partition size? A: ~16MB compressed, columnar, immutable.
5. Q: What enables pruning? A: Per-partition min/max metadata in the services layer.
6. Q: Our database? A: DERMIQ_DEV.
7. Q: Schema naming? A: LAYER_TENANT (RAW/STG/INT/MART/SEED _DEL_MAR).
8. Q: Staging materialization? A: Views.
9. Q: Marts materialization? A: Tables.
10. Q: Intermediate materialization? A: Tables (reused by multiple marts).
11. Q: Monetary type standard? A: NUMBER(18,4).
12. Q: Why explicit RAW types? A: Avoid pandas mis-typing sparse columns (ADR-005).
13. Q: Embedding storage? A: JSON string in VARCHAR, in-process cosine (no VECTOR type).
14. Q: Auth method? A: Key-pair (JWT) — ADR-009.
15. Q: Why key-pair? A: MFA enforcement broke headless password auth.
16. Q: JWT auth flow? A: Private key signs a JWT; Snowflake verifies vs the public key on the user.
17. Q: Token expiry gotcha? A: Master token hard-caps (~2 days); pinned API connection dies; restart to re-auth.
18. Q: client_session_keep_alive? A: Keeps the session token fresh; doesn't beat the master-token cap.
19. Q: Cost cap tool? A: Resource monitor (credit quota → suspend).
20. Q: Zero-copy clone? A: Instant copy-on-write DB copy for dev envs.
21. Q: Time Travel? A: Query/restore past table state within retention.
22. Q: What is dbt? A: A SQL compile+run framework: Jinja, ref-DAG, tests, docs, materializations.
23. Q: dbt Core vs Cloud? A: We use Core (CLI, self-hosted); Airflow owns scheduling.
24. Q: Adapter? A: dbt-snowflake translates to Snowflake SQL + handles key-pair.
25. Q: How is the dbt DAG built? A: From parsed ref()/source() calls, run in topological order.
26. Q: ref() does what? A: Resolves the FQN and declares a dependency.
27. Q: source() does what? A: Declares/reads a RAW source table (+ freshness/tests).
28. Q: generate_schema_name override? A: Produces LAYER_TENANT instead of dbt's default.
29. Q: Tests that must return? A: Zero rows to pass.
30. Q: Test types we use? A: unique, not_null, relationships, accepted_values, expression_is_true.
31. Q: Conditional not_null example? A: transaction_id null only when movement_type='expiry'.
32. Q: Seed we track? A: marketing_spend (CSV → SEED_DEL_MAR).
33. Q: Snapshots? A: SCD-2 history; not used yet.
34. Q: Manifest? A: target/manifest.json — the compiled project graph.
35. Q: Compiled vs run dir? A: compiled = raw SQL; run = materialization DDL.
36. Q: Airflow four parts? A: Scheduler, executor, metadata DB, webserver.
37. Q: DAG vs task vs operator? A: Workflow / node / node template.
38. Q: Daily DAG id + schedule? A: del_mar_pipeline, 0 6 * * *.
39. Q: Daily DAG tasks? A: wait_for_postgres → extract → dbt_build → notify.
40. Q: Retry config? A: retries=2, retry_delay=2min.
41. Q: Sensor mode? A: reschedule (frees the worker slot between pokes).
42. Q: XCom we use? A: extract pushes row_counts; notify pulls it.
43. Q: astro dev start containers? A: webserver, scheduler, triggerer, metadata postgres.
44. Q: Triggerer purpose? A: Run deferrable/async tasks off the worker.
45. Q: What Cosmos does? A: Renders each dbt model as an Airflow task in a task group.
46. Q: Cosmos vs BashOperator? A: Per-model retries + native graph visibility.
47. Q: Weekly DAG? A: weekly_clustering, Mon 3am — refit k-means, rebuild segment marts.
48. Q: RAG DAG? A: rag_corpus_refresh, 7am — rebuild + re-embed corpus.
49. Q: Idempotency source? A: Full-refresh / CREATE OR REPLACE + deterministic seeds.
50. Q: LocalExecutor vs prod? A: Subprocesses on one host vs Celery/Kubernetes workers.
