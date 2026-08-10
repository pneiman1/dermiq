# DermIQ — Development Journey

What I built, in what order, and what it cost me. Written first-person and
honestly, mostly so I can answer interview questions about tradeoffs without
reconstructing them from memory. Dates come from the git history; the effort
numbers at the end are reconstructions, not a tracked timesheet.

---

## Overview

DermIQ is an analytics product for a cosmetic-dermatology practice: it ingests
an EMR-shaped source database, models it through a medallion warehouse, serves
the result as an API, and puts a dashboard and two LLM features on top. The
demo tenant is "Del Mar Cosmetic Dermatology" — synthetic data shaped to look
like a real Nextech export, because I wanted the modeling problems to be real
even though the patients aren't.

It sits on **platform-core**, a separate repo holding the vertical-agnostic
pieces: config, structured logging, the Snowflake connection, the LLM client,
and the RAG embedder/store. The split was deliberate from commit one. The bet
is that the same core could power a different vertical — a brewery, a fitness
studio — with only the dbt models, the marts, and the frontend changing. That
bet is untested, and I want to be honest that "it would probably work" is not
the same as "it works."

The work ran from **June 6 to August 9, 2026** — about two months of evenings
and weekends — in numbered chunks, each one a coherent slice ending in a
commit. Fourteen chunks plus two half-chunks and one point-release. It ends
with the thing actually deployed: Vercel serving the frontend at `derm-iq.io`,
Fly.io serving the API at `dermiq-api.fly.dev`, both live against Snowflake and
Claude. Getting from "runs on my machine" to "runs on the internet" turned out
to be roughly a third of the total effort, which is the single most useful thing
I learned.

---

## Chunks in order

### Chunk 1 — Repo skeleton and platform-core wiring (Jun 6–12)

**Built.** Package config, structured logging, the editable install of
platform-core, and the decision log itself.

**Why it mattered.** Deciding the two-repo split before writing any features is
the reason the split held. Retrofitting a core library out of a working
monolith is a rewrite; declaring it up front is a `pyproject.toml` line.

**Hard part.** Nothing technically, but ADR-001 records real hesitation about
consuming platform-core as a local editable install with no version pin. That
is convenient and it is also a trap — the two repos can drift, and nothing
catches it. It stayed unpinned. It is still unpinned.

**Decisions.** [ADR-001](DECISIONS.md#adr-001-consume-platform-core-as-a-local-editable-install-no-version-pin-yet).

### Chunk 2 — Postgres source + RAW ingestion (Jun 11–12)

**Built.** A Nextech-shaped Postgres database with a synthetic seed loader, and
the ingestion path landing it into Snowflake's RAW layer.

**Why it mattered.** Simulating the EMR as a real database, rather than reading
CSVs, meant the ingestion code was doing the actual job from day one —
least-privilege reads, full refresh, faithful copy — instead of being
retrofitted later.

**Hard part.** Making synthetic data that produces *interesting* analytics.
Random data yields flat, uninformative marts. The seed generator had to be
hand-calibrated so provider performance actually varies, channels actually
differ in ROI, and the dashboard has something to say.

**Decisions.** [ADR-002](DECISIONS.md#adr-002-simulate-the-emr-source-as-a-nextech-shaped-postgres-database),
[ADR-003](DECISIONS.md#adr-003-source--raw-ingestion--least-privilege-read-full-refresh-faithful-copy).

### Chunks 3–5 — dbt staging, intermediate, marts (Jun 23–24)

**Built.** The medallion layers: typed 1:1 staging views over RAW, intermediate
models (visit economics, patient LTV, provider daily), then the marts, plus a
`marketing_spend` seed.

**Why it mattered.** This is the actual data-engineering content of the project.
Everything above it — API, dashboard, RAG, clustering — is a consumer of these
models.

**Hard part.** Discipline about layer boundaries. Staging is *only* cleaning and
typing; business logic that wants to sneak in there has to be pushed to
intermediate. It is constantly tempting to shortcut, and every shortcut costs
later when a mart needs the raw shape.

**Decisions.** [ADR-004](DECISIONS.md#adr-004-dbt-staging-layer--one-to-one-cleanedtyped-views-over-raw).

### Chunk 5.5 — Explicit Snowflake column types (Jun 24)

**Built.** Ingestion declares column types rather than letting the connector
infer them.

**Why it mattered.** Inferred types are stable right up until a batch of data
makes them not stable. This was filed as tech debt in ADR-005 and then actually
paid down, which is worth noting because most tech-debt ADRs never get a
resolution commit.

**Decisions.** [ADR-005](DECISIONS.md#adr-005-ingestion-must-declare-explicit-snowflake-column-types-tech-debtingestion).

### Chunk 6 — FastAPI over the marts (Jun 25)

**Built.** A read-only JSON API under `/api/v1`: lifespan-managed Snowflake
connection, a fresh cursor per request, Pydantic response models, structlog
request logging with latency. 18 tests against real Snowflake.

**Why it mattered.** It forced the marts to be honest. A model that looks fine
in `dbt docs` and awkward to serve over HTTP is usually badly grained.

**Hard part.** The decimal contract. Money and rates are `Decimal` in Python and
serialize to JSON *strings* to preserve precision, which pushes the problem to
the frontend, where `decimal.js` picks it up. Floats would have been easier and
wrong.

**Also.** `X-Tenant-ID` went in as a stub for real auth. It is still a stub. It
is honestly labeled as one everywhere, which is the least I could do.

### Chunk 7 — Next.js dashboard, 7 tabs (Jun 29)

**Built.** Executive, Providers, Marketing, Recall, Flow, plus Inventory and AI
Studio as previews. TanStack Query with a 5-minute stale time, light/dark theme,
a visual template with a warm stone gradient and a clinical teal accent.

**Why it mattered.** Analytics nobody looks at is a pipeline, not a product.

**Hard part.** Story-driven callouts — "provider to watch," "lowest-ROI paid
channel." Computing them is easy; deciding what is worth surfacing without
being wrong or preachy is a judgment call I revisited several times.

### Chunk 7.5 — Cross-platform setup (Jun 30)

**Built.** SETUP.md rewritten per-platform, MACOS-NOTES.md, `.gitattributes`
line-ending normalization, an audit confirming no hardcoded paths anywhere in
scripts, ingestion, or dbt profiles.

**Why it mattered.** This is where the eventual move off Windows started, months
before I made it. Everything env-driven, nothing path-hardcoded, line endings
normalized. When the migration came it was mostly boring, and that was the
point.

### Chunk 8 — Airflow via Astronomer + Cosmos (Jun 30)

**Built.** A daily DAG: wait for Postgres → ingest to RAW → Cosmos-expanded dbt
build (one run+test task per model, 26 models) → row-count notification.

**Why it mattered.** Cosmos expanding dbt into individual Airflow tasks means a
failure points at a model, not at "dbt failed."

**Hard part.** The Astro build context cannot reach sibling repos, so editable
code comes in by bind-mount plus `sys.path`. Ports had to be de-conflicted
(webserver 8081, metadata Postgres 5434) against the services already running.
Fiddly, unglamorous, and about a third of the chunk.

**Decisions.** [ADR-006](DECISIONS.md#adr-006-orchestrate-the-pipeline-with-airflow-astronomer--astronomer-cosmos).

### Chunk 9 — Unsupervised patient clustering (Jul 6)

**Built.** `int_patient_features` with 12 behavioral features per patient,
StandardScaler + KMeans(k=7), auto-labeled clusters written back to Snowflake as
`mart_patient_segments` (7) and `mart_patient_segment_members` (2,781). A weekly
refit DAG.

**Why it mattered.** It is the first thing in the project that is genuinely
*derived* rather than aggregated.

**Hard part.** Cluster naming. A cluster is a centroid; a *segment* is a story.
The auto-labeler reads the centroid and picks a name, with collision suffixes
when two clusters land on the same description. It works and it is a heuristic.

**Honest.** `k=7` is a fixed heuristic, not the output of silhouette or elbow
analysis. It is in the tech-debt list. It has been there a while.

**Decisions.** [ADR-007](DECISIONS.md#adr-007-unsupervised-k-means-for-patient-segmentation-chunk-9).

### Chunk 10 — RAG chat over the marts (built earlier, committed Jul 26)

**Built.** A corpus assembled from the marts — metric definitions plus live
snapshots — embedded with sentence-transformers (`all-MiniLM-L6-v2`, 384-dim),
stored as JSON vectors in a `rag_corpus` table, retrieved top-k by in-process
cosine similarity, answered by Claude Sonnet with the retrieved context.

**Why it mattered.** It is the feature that makes the marts *conversational*,
and it is grounded — answers cite the mart they came from, so the model is
summarizing retrieved rows rather than recalling anything.

**Hard part.** Deciding not to reach for a vector database. In-process cosine
over a ~30-document corpus is a dot product; pgvector or a hosted index would
have been infrastructure serving no purpose at this scale. That decision aged
extremely well and is the direct reason the embedding backend was swappable
later.

**Note.** This chunk sat uncommitted for a while and landed after chunk-11 — the
commit explicitly flips the "chunk-10 uncommitted" notes in the docs. The
numbering is build order, not commit order.

**Decisions.** [ADR-008](DECISIONS.md#adr-008-retrieval-grounded-ai-studio-chat-chunk-10).

### Key-pair auth migration (Jul 22–24)

**Built.** Snowflake key-pair (RSA JWT) auth replacing password auth across the
API, ingestion, dbt, and Airflow.

**Why it mattered.** Snowflake began enforcing MFA on the account. The API opens
its connection headless at startup with no terminal to answer a TOTP challenge,
so `/health` started reporting `snowflake_reachable: false` and the pipeline
broke outright. This was not a nice-to-have; it was an outage.

**Hard part.** Realizing MFA caching could not fix it. The cache helps *after* a
successful authentication, but the first auth after expiry still needs a fresh
code — so a long-lived process that restarts overnight is stranded exactly when
nobody is watching. The `client_session_keep_alive` heartbeat I had added
earlier kept an already-open session alive and was useless for cold start. Two
partial fixes that both looked plausible and neither of which addressed the
actual failure.

**Decisions.** [ADR-009](DECISIONS.md#adr-009-snowflake-key-pair-jwt-authentication-for-headless-services).

### Chunk 11 — Inventory and true margin (Jul 24–25)

**Built.** Consumables inventory — lots, stock, par levels, expiry, waste — and
a true-margin mart that nets consumable cost against service revenue.

**Why it mattered.** True margin is the number that changes decisions. Revenue
per service is vanity when a Botox unit has a cost and a shelf life; margin
after consumables and waste is what a practice owner would act on.

**Hard part.** Modeling lot-level consumption against transaction-level revenue
without a real consumption log. The generator is hand-calibrated to produce
plausible waste and expiry, and I want to be explicit that these are fixtures,
not a reconstruction of any real report.

**Decisions.** [ADR-010](DECISIONS.md#adr-010-inventory--true-margin-layer-built-fresh-chunk-11),
[ADR-011](DECISIONS.md#adr-011-inventory-extension--lots-stock-expiring-chunk-11-extension).

### Chunk 12 — Composable Canvas (Jul 26)

**Built.** Type a request in natural language; Claude composes a chart spec via
tool-use — one tool per chart type, six types total — against a curated schema
of the marts. The spec resolves to a parameterized Snowflake query with
identifiers allowlisted and values bound. Invalid columns get one retry, then
422. The frontend is a drag-and-resize grid of Recharts components with
save/load.

**Why it mattered.** It is the most technically interesting thing in the
project. The LLM never writes SQL. It fills in a constrained grammar, and the
grammar resolves to SQL I control.

**Hard part.** Designing the grammar so it is expressive enough to be useful and
narrow enough to be safe. Allowlisted identifiers and bound values mean a
hallucinated column name is a 422, not an injection.

**Measured.** ~3–5s per chart, ~$0.02–0.05 per chart at Sonnet pricing.

**Decisions.** [ADR-013](DECISIONS.md#adr-013-composable-canvas--llm-composed-visualizations-chunk-12).

### Chunk 13 — Deployment readiness and the slim image (Aug 2–8)

**Built.** In two passes. First (Aug 2): CORS from env, slowapi rate limiting
(`/chat` 20/hour, `/canvas/generate` 10/hour per IP), a health-check split into
a fast dependency-free `/health` and a deep `/health/snowflake`, a 30s Anthropic
timeout, and the monthly budget guard. Then (Aug 3–8): the image itself, plus an
entrypoint that decodes the base64 Snowflake key to disk at boot.

**Why it mattered.** Everything up to here assumed a trusted local caller. None
of that survives contact with a public URL.

**Hard part.** The image. Covered separately below — it is the best story in the
project.

**Decisions.** [ADR-014](DECISIONS.md#adr-014-serving-only-dependency-set-for-the-api-image-onnx-runtime-for-query-embedding-chunk-13).

### Chunk 13.1 — The startup guard (Aug 8)

**Built.** `dermiq/api/startup.py`: at process start, check that the configured
`EMBEDDING_PROVIDER` names a backend whose modules this image can actually
import. If not, raise out of the lifespan handler so uvicorn aborts and the
container never listens.

**Why it mattered.** After the ONNX rollout a stale `EMBEDDING_PROVIDER` Fly
secret survived the migration and overrode the image's own `ENV`. Every `/chat`
request raised `ModuleNotFoundError: No module named 'sentence_transformers'` —
while `/health` stayed green and the deploy reported success. The embedding
backend is imported lazily on the first query, so nothing touched it until real
traffic did.

**Hard part.** Recognizing this as a *class* of bug rather than one bad secret.
The fix that mattered was not correcting the value; it was making a
misconfigured process refuse to start, so Fly's health check fails and the
rolling deploy halts instead of swapping in a broken machine.

**The detail I like.** It uses `importlib.util.find_spec` rather than a real
import — it answers "can this load?" without paying seconds and hundreds of
megabytes to actually initialize onnxruntime at every boot.

### Chunk 14 — Mobile responsive (Aug 8)

**Built.** The sidebar becomes a slide-in drawer below `lg`. Every data table
renders twice — the real `<table>` behind `hidden lg:block`, a card list behind
`lg:hidden` — both reading the same sorted array, with a native `<select>` sort
bar keeping mobile at parity with sortable column headers. Dialogs become
full-screen sheets below `sm`. Canvas collapses to a single read-only column on
touch, with `onLayoutChange` detached so the persisted desktop arrangement
survives.

**Why it mattered.** A portfolio piece gets opened on a phone. If it is broken
there, that is the entire impression.

**Hard part.** The two-rendering approach is honest duplication, and I went back
and forth on it. One responsive table that reflows would be less code and worse
— a table squeezed onto 375px is unreadable regardless of how it reflows.
Detaching `onLayoutChange` on mobile is the subtle one: without it, viewing
Canvas on a phone would silently overwrite the saved desktop layout with a
single-column one.

**Detail.** Buttons ≥44px below `sm` per Apple's HIG; text inputs 56px tall at
16px font, because iOS Safari zooms on focus for anything smaller.

---

## Deployment migration story

### Why I moved off Windows

The project started on Windows with WSL2 and moved to a Mac. The reason was
portability rather than any technical failure — a portfolio project I might
demo anywhere should run on the machine I would actually carry. There are still
fossils in the tree: a stray `docker-compose.yml:Zone.Identifier` file, which is
a Windows NTFS alternate-data-stream artifact that WSL2 surfaces as a real file.

The migration was easier than it deserved to be, entirely because of chunk 7.5 a
month earlier. Everything was env-driven, no hardcoded paths, line endings
normalized via `.gitattributes`. The prep work was speculative at the time.

### Mac Monterey Intel setup

Monterey 12.7.6 on Intel is an old-but-supported target, and the friction was
concentrated in the toolchain rather than the code. From the Aug 2 run:

- **Docker Desktop 4.35+ dropped macOS 12 support.** It installs cleanly and
  then simply fails to start, which reads as a broken install rather than an
  unsupported OS. The fix is pinning **4.34.x** from the release-notes archive.
- **Homebrew emits "Tier 3 support" warnings** on 12.x that look fatal and are
  not.
- **`brew link` fails against stale Python symlinks** from earlier installs.
- **Homebrew vs system Python shadowing** — always invoke `python3.12`
  explicitly when creating a venv, or you get one built from the wrong
  interpreter and discover it much later.
- **`react-grid-layout` had to be pinned to 1.5.0.** v2 removed the
  `WidthProvider` HOC that Canvas uses while `@types/react-grid-layout` was still
  v1, so a fresh `npm install` produced a runtime `WidthProvider is not a
  function` with no type error to warn you.

None of these are interesting problems. All of them cost real time, which is why
`CLONE_TO_DEMO.md` was rewritten against an actual run rather than an idealized
one.

### Getting the Snowflake key to Fly.io

Fly stores secrets as strings, and the Snowflake private key is a
passphrase-encrypted PKCS#8 file. The solution is base64: the key is stored as
`SNOWFLAKE_PRIVATE_KEY_CONTENT`, and `docker-entrypoint.sh` decodes it to
`/secrets/snowflake_rsa_key.p8` at container start, `chmod 600`s it, exports
`SNOWFLAKE_PRIVATE_KEY_PATH`, and execs the real command.

It is a small script and it is the seam where a lot can go wrong quietly — the
passphrase has to match the key that was encoded, and a mismatch only manifests
inside the container.

### The Docker image size crisis

The best debugging story in the project, and the most measured. The API image
reached **11.1GB locally / ~5.6GB pushed**, and Fly deploys were failing on the
oversized layer. Three independent causes, found by measuring rather than
guessing:

1. **CUDA — ~4.5GB.** `pip install sentence-transformers` on linux/amd64 pulls
   the default torch wheel, which drags in `nvidia-*` (2.7GB) and `triton`
   (691MB) for GPUs no Fly shared-CPU VM has. Torch itself added 1.1GB.
2. **Copied virtualenvs — 2.8GB.** `Dockerfile.api` builds from the *parent* of
   the repo so it can reach the sibling platform-core checkout. Docker resolves
   `.dockerignore` relative to the context root, so the repo's own file never
   applied, and `COPY dermiq /build/dermiq/` swept in `dermiq/.venv` (1.8GB) and
   `platform-core/.venv` (430MB) — which the runtime stage then copied into the
   final image.
3. **Union dependencies — ~400MB.** Both packages declared base dependencies
   covering every workload, so serving HTTP requests installed the batch-job
   toolchain: pandas, pyarrow, scikit-learn, scipy, dbt.

The awkward part was (1). `/chat` genuinely embeds its query server-side — the
corpus is embedded offline, but an incoming question has to become a vector at
request time — so "just drop sentence-transformers" would have broken retrieval.

Three fixes, one per cause:

1. **ONNX Runtime for query embedding.** platform-core gained an `onnx` backend
   running the *same* `all-MiniLM-L6-v2` weights, exported to ONNX, mean-pooled
   over the attention mask, L2-normalized — reproducing sentence-transformers'
   pipeline without torch. The model is baked in at build time from its own
   stage, so nothing reaches out to huggingface.co at startup. Corpus builds
   keep the torch backend, where the size is free.
2. **`Dockerfile.api.dockerignore`.** BuildKit reads `<dockerfile>.dockerignore`
   in preference to the context-root one, which is how a file committed inside
   the repo can govern a context rooted above it.
3. **Minimal base dependencies with workload extras.** pandas became a lazy
   import in the two places that need it; `platform_core.rag` resolves
   submodules through PEP 562 so importing it costs only what the caller
   touches.

**Result: 11.1GB → 449MB (−96%).** Build context 2.2GB → 1.06MB. Resident memory
~240MB, comfortably inside the 512MB VM.

The part I am most pleased with is that equivalence was *verified, not assumed*:
ONNX and sentence-transformers agree to cosine 1.000000 across the query set,
max elementwise delta 1.3e-7 — float32 noise. That test lives in
`platform-core/tests/rag/test_embedder_parity.py`.

I also considered CPU-only torch (`--index-url .../whl/cpu`), which needs zero
code changes and eliminates every `nvidia-*` package. Measured: ~1.56GB image. A
7× improvement that still missed the target by 3×, and the difference in
resident memory — ~240MB versus ~1.1GB on a 512MB VM — is what decided it.

### The startup guard, and why it exists

The ONNX rollout is what created the conditions for the outage described in
chunk 13.1. The image sets `ENV EMBEDDING_PROVIDER=onnx`; a Fly secret from
before the migration overrode it; the failure was invisible to `/health` and to
the deploy. That is the worst shape a bug can have — silent, delayed, and
reported as success.

The guard is thirty lines and it is the most valuable thirty lines in the
deployment path.

---

## Debugging highlights

**Fly's release number is not a code version.** Deploying the startup guard, I
found `flyctl status` reporting machine version 7 while the running container
was four days older than the guard commit. Releases increment on *any* change:
a secrets-only release rebuilds nothing, and a *failed* deploy consumes a number
too. In this case v6 was secrets-only and v7 had failed outright, so the machine
had been serving the same image throughout while the counter advanced twice.
Confirming it meant pulling the image from `registry.fly.io` and listing
`site-packages` — the only way to know what is actually running.

**`docker-credential-desktop` not on `PATH`.** A `--local-only` deploy builds
locally and pushes to Fly's registry using Docker's credential helper, which on
this Mac is not on the default `PATH`. The build output is entirely green and
the failure appears only at the push step, which is a genuinely misleading
place for it. This is the most likely cause of that failed v7.

**A Fly secret silently overriding a Dockerfile `ENV`.** Covered above. The
lesson generalizes: any layer that can override configuration should be
enumerable at boot, and the process should refuse to run on a configuration it
cannot serve.

**ONNX versus PyTorch for embeddings.** Not a bug, but the highest-leverage
decision in the deployment work. Replacing the torch backend removed roughly
4.5GB of CUDA and torch from the serving path while keeping retrieval bit-for-bit
equivalent within float32 noise.

**Multi-tenant schema routing in dbt.** `transform/macros/generate_schema_name.sql`
overrides dbt's default so schemas resolve to `<LAYER>_<TENANT>` from a `tenant`
var, defaulting from `DEFAULT_TENANT_ID`. It mirrors
`platform_core.warehouse.schemas`, so ingestion and transformation agree on
where a tenant's data lives. It is a small macro that quietly makes the
multi-tenant story real at the warehouse layer, even though auth above it is
still a stub.

**Rate limiting and budget guarding as separate concerns.** Easy to conflate,
wrong to. Rate limiting is per-IP abuse protection (slowapi, 20/hour on `/chat`,
10/hour on `/canvas/generate`). The budget guard is per-*account* cost
protection — a token counter estimating monthly spend at Sonnet pricing,
returning 429 once the cap is hit and resetting on the 1st. One protects the
service, the other protects the bill; a single mechanism would do neither well.
Both are in-memory and per-process, which is a real limitation I document rather
than pretend away.

---

## What worked well

**The platform-core split.** Declared before any code existed and never
regretted. When ONNX support was needed, it went into
`platform_core.rag.embedder` and both the corpus builder and the API picked it
up. If that code had lived in DermIQ, the "swap the embedding backend" change
would have been a much larger surface.

**ADRs written at decision time.** Fourteen of them, append-only, never edited
retroactively. The value is not documentation — it is that writing down
"alternatives considered" forces you to actually consider alternatives. ADR-014
is the clearest case: the CPU-only-torch option is written up with measured
numbers because I measured it before rejecting it.

**Measuring before fixing.** The image problem could easily have been "torch is
big, remove torch." Measuring found three independent causes, one of which — the
copied virtualenvs — was 2.8GB and had nothing to do with dependencies at all. I
would have shipped a 3GB image feeling like I had solved it.

**Constraining the LLM instead of trusting it.** Canvas never lets the model
write SQL. It fills a fixed grammar; the grammar resolves to parameterized SQL
with allowlisted identifiers. A hallucinated column is a 422. That design has
held up under every adversarial input I have tried.

**Not reaching for infrastructure.** No vector database for a 30-document
corpus. No Kubernetes. No connection pooler for one machine. Every one of those
would have been defensible and every one would have been overhead. The one place
this bit me is the single Snowflake connection, below.

**Doing cross-platform work early.** Chunk 7.5 was speculative and made the Mac
migration nearly boring a month later.

---

## What I'd do differently

**Deploy at chunk 6, not chunk 13.** The single biggest thing. Every deployment
problem — image size, CORS, secrets overriding `ENV`, the health-check split —
was discoverable the moment the API first existed. Instead they arrived
simultaneously, at the end, entangled with each other, at the point where I most
wanted to be finished. A trivially deployed hello-world API at chunk 6 would
have caught the `.dockerignore` context problem before there were 11GB riding on
it.

**Reconnect logic on the Snowflake connection from the start.** The API holds
one long-lived connection with no reconnect. When the master token expires
(~1–2 days) every query fails with `390114` until the machine restarts. I knew
this was wrong when I wrote it, filed it as tech debt, and it is still there —
and it is the single most likely thing to make the live demo fail.

**Set up CI.** There is no `.github/workflows` in either repo. ADR-014
explicitly says the ONNX/sentence-transformers parity test "must keep running in
CI" — and there is no CI for it to run in. The test skips silently when either
backend is missing, which is exactly the shape of a test that quietly stops
protecting you. This is the clearest gap between what the docs claim and what
exists.

**Pin platform-core.** ADR-001 flagged the unpinned editable install as a known
risk and I never came back to it. The two repos can drift and nothing catches
it.

**Choose `k` properly.** `k=7` was a guess that produced good-looking segments.
Silhouette analysis would have taken an hour.

**Not name the production database `DERMIQ_DEV`.** Production reads a database
with `_DEV` in the name. It works, and it is confusing to anyone reading the
config cold, and renaming it now means moving data.

**Keep PROJECT_STATUS.md current.** It still says "all eleven chunks" with a
table ending at chunk 11. Three chunks have shipped since. Status docs that lag
are worse than no status doc, because they are believed.

---

## Total effort

Reconstructed from commit dates and memory. Evenings and weekends across June 6
to August 9, 2026 — not tracked hours, so treat these as honest estimates rather
than measurements.

| Chunk | Focus | Est. hours |
|---|---|---:|
| 1 | Skeleton, platform-core split, ADR process | 6 |
| 2 | Postgres source + synthetic seed + RAW ingestion | 14 |
| 3–5 | dbt staging → intermediate → marts | 24 |
| 5.5 | Explicit Snowflake column types | 3 |
| 6 | FastAPI over the marts + tests | 14 |
| 7 | Next.js dashboard, 7 tabs, visual template | 28 |
| 7.5 | Cross-platform setup + docs | 6 |
| 8 | Airflow / Astronomer / Cosmos | 16 |
| 9 | Patient clustering + segment marts + weekly DAG | 16 |
| 10 | RAG corpus, retrieval, chat endpoint, AI Studio | 20 |
| — | Key-pair auth migration (unplanned, ADR-009) | 8 |
| 11 | Inventory, lots/stock/expiry, true margin | 18 |
| 12 | Composable Canvas (grammar, tool-use, grid UI) | 26 |
| 13 | Deploy readiness + slim image + ONNX backend | 30 |
| 13.1 | Startup guard + tests | 4 |
| 14 | Mobile responsive across all tabs | 14 |
| — | Docs: ADRs, SETUP, STUDY_GUIDE, runbook | 20 |
| — | Actual deployment: Fly + Vercel + DNS + debugging | 12 |
| | **Total** | **~279** |

Roughly **280 hours over nine weeks**. The distribution is the interesting part:
chunk 13 alone (30h) cost more than the entire dbt layer (24h), and deployment
plus deploy-prep plus the startup guard together (~46h) is about 16% of the
project. Nothing in the modeling work was as expensive as making it run
somewhere other than my laptop.

---

## Related docs

- [`DECISIONS.md`](DECISIONS.md) — the fourteen ADRs, in decision order
- [`DEPLOYMENT.md`](DEPLOYMENT.md) — the operations runbook this story ends at
- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — shipped features and tech debt
- [`STUDY_GUIDE.md`](STUDY_GUIDE.md) — the concepts behind the stack
- [`CLONE_TO_DEMO.md`](CLONE_TO_DEMO.md) — fresh machine to running demo
