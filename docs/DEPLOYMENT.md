# DermIQ — Production Operations Runbook

How to deploy, redeploy, rotate secrets, troubleshoot production, and add a new
frontend domain. Written for future-me or a collaborator with repo access and
credentials, arriving cold.

For first-time machine setup see [`CLONE_TO_DEMO.md`](CLONE_TO_DEMO.md). For why
things are built the way they are, see [`DECISIONS.md`](DECISIONS.md).

---

## Production topology

```
                          ┌──────────────────────────────┐
   Browser  ──────────────►  Vercel                       │
                          │  derm-iq.io / www.derm-iq.io  │
                          │  Next.js frontend             │
                          │  auto-deploys from main       │
                          └───────────────┬──────────────┘
                                          │  HTTPS
                                          │  NEXT_PUBLIC_API_BASE_URL
                                          ▼
                          ┌──────────────────────────────┐
                          │  Fly.io  dermiq-api.fly.dev  │
                          │  FastAPI (uvicorn), region sjc│
                          │  1 shared-CPU VM, 512MB       │
                          │  manual deploy via flyctl     │
                          └───────┬──────────────┬───────┘
                                  │              │
                    key-pair JWT  │              │  HTTPS
                                  ▼              ▼
                   ┌───────────────────┐  ┌──────────────────────┐
                   │  Snowflake        │  │  Anthropic API       │
                   │  DERMIQ_DEV       │  │  claude-sonnet-5     │
                   │  COMPUTE_WH       │  │  chat + canvas specs │
                   │  marts + corpus   │  └──────────────────────┘
                   └───────────────────┘
                                  ▲
                                  │  embeddings computed in-process
                   ┌──────────────┴───────────────┐
                   │  ONNX Runtime (in API image) │
                   │  all-MiniLM-L6-v2, 384-dim   │
                   └──────────────────────────────┘
```

**Vercel — frontend.** Serves the Next.js dashboard at `derm-iq.io` (and
`www.derm-iq.io`). Deploys automatically on every push to `main`; there is no
manual deploy step and no `vercel.json` in the repo — the project is configured
entirely in the Vercel dashboard.

**Fly.io — API.** Serves FastAPI at `dermiq-api.fly.dev` from a single
shared-CPU 512MB VM in `sjc`. Deploys are **manual** — nothing pushes on merge.
The app holds one long-lived Snowflake connection opened in the FastAPI lifespan
(`dermiq/api/main.py`).

**Snowflake — data plane.** Database `DERMIQ_DEV`, warehouse `COMPUTE_WH`
(auto-suspends when idle). Holds the dbt marts the API reads and the `rag_corpus`
table backing `/chat`. Auth is key-pair JWT (ADR-009) — the private key arrives
as a base64 Fly secret and is decoded to disk at container start by
`docker-entrypoint.sh`.

> **Note:** production reads the database literally named `DERMIQ_DEV`. There is
> no separate prod database — the name is historical, not a mistake to "fix"
> without also moving the data and re-pointing `SNOWFLAKE_DATABASE`.

**Anthropic — LLM.** `claude-sonnet-5` answers `/chat` and composes Canvas chart
specs. Calls carry a 30s timeout and pass through an in-process monthly budget
guard (`dermiq/api/budget.py`).

**Embeddings — ONNX, not sentence-transformers.** `/chat` embeds the incoming
question server-side at request time. Since chunk-13 that runs the same
`all-MiniLM-L6-v2` weights through ONNX Runtime instead of torch, which is what
made a 512MB VM viable (ADR-014). The corpus itself is embedded offline, where
the torch backend is still used. `EMBEDDING_PROVIDER=onnx` is baked into the
image as `ENV`, but **a Fly secret overrides it** — see the startup guard below.

---

## Prerequisites (before any deploy)

- **Docker Desktop 4.34.x running.** Monterey 12.x only supports up to 4.34.x —
  4.35+ dropped macOS 12. See `CLONE_TO_DEMO.md` for the download link.
- **flyctl installed and authenticated:**
  ```bash
  flyctl version
  flyctl auth whoami        # → pneiman1@gmail.com
  ```
- **Both repos on `main` with a clean working tree.** The build context spans
  `platform-core` and `dermiq`; uncommitted changes in *either* repo ship in the
  image.
  ```bash
  cd ~/projects/platform-core && git status --short && git rev-parse --abbrev-ref HEAD
  cd ~/projects/dermiq        && git status --short && git rev-parse --abbrev-ref HEAD
  ```
- **Secrets configured on Fly.** There is no `docs/fly-secrets-reference.md`;
  the authoritative list is the comment block at the bottom of `fly.toml`, and
  the live state is `flyctl secrets list`. Currently set (14):

  | Secret | Purpose |
  |---|---|
  | `ANTHROPIC_API_KEY` | Claude auth |
  | `ANTHROPIC_MODEL_SONNET` | model id |
  | `ANTHROPIC_MONTHLY_BUDGET_USD` | budget-guard cap |
  | `CORS_ORIGINS` | comma-separated allowed origins |
  | `DEFAULT_TENANT_ID` | tenant for schema routing |
  | `EMBEDDING_PROVIDER` | must be `onnx` on the slim image |
  | `LLM_PROVIDER` | LLM backend selector |
  | `SNOWFLAKE_ACCOUNT` | warehouse account |
  | `SNOWFLAKE_USER` | service user |
  | `SNOWFLAKE_PRIVATE_KEY_CONTENT` | base64 of the `.p8` |
  | `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | decrypts the `.p8` |
  | `SNOWFLAKE_ROLE` | role |
  | `SNOWFLAKE_WAREHOUSE` | `COMPUTE_WH` |
  | `SNOWFLAKE_DATABASE` | `DERMIQ_DEV` |

  `fly.toml` also lists `EMBEDDING_MODEL`, which is **not currently set**.
  Production works without it because the image supplies its own default; either
  set it or drop it from the `fly.toml` checklist.

---

## Deploying the API to Fly.io

Run from the **parent** directory, not from `dermiq/`:

```bash
cd ~/projects
DOCKER_HOST=unix://$HOME/.docker/run/docker.sock flyctl deploy \
  --config dermiq/fly.toml --dockerfile dermiq/Dockerfile.api --local-only
```

**Why from `~/projects` and not `dermiq/`.** `Dockerfile.api` COPYs *both*
`platform-core/` and `dermiq/`, so the build context has to contain both repos.
`--config` and `--dockerfile` are therefore relative to `~/projects`.

**Why `--local-only`.** Fly's remote builder is reached over a WireGuard tunnel
that is unreliable from typical residential networks. Building locally is faster
and does not depend on that tunnel. (The same tunnel is why `flyctl ssh console`
often fails from here — see Troubleshooting.)

**Why `DOCKER_HOST`.** Docker Desktop on Mac exposes its socket at
`~/.docker/run/docker.sock`, not `/var/run/docker.sock`, so flyctl cannot find
the daemon without being told.

### If the push fails with `docker-credential-desktop` not found

The build succeeds and then the push to `registry.fly.io` dies:

```
failed authenticating with registry.fly.io: Error saving credentials -
err: exec: "docker-credential-desktop": executable file not found in $PATH
```

Docker Desktop's binaries are not on the default `PATH`. Either:

```bash
export PATH="/Applications/Docker.app/Contents/Resources/bin:$PATH"
```

or edit `~/.docker/config.json` and remove the `"credsStore": "desktop"` line.

This failure mode is easy to misread as a build problem — the build output is
entirely green and the failure appears only at the push step.

### Verifying a deploy

```bash
flyctl status                      # machine state + current deployment tag
flyctl releases | head -5          # release history
curl -s https://dermiq-api.fly.dev/api/v1/health          # → {"status":"ok"}
curl -s -X POST https://dermiq-api.fly.dev/api/v1/chat \
  -H "Content-Type: application/json" -H "X-Tenant-ID: del_mar" \
  -d '{"question":"What were the top revenue-generating services?"}'
```

`/chat` requires the `X-Tenant-ID` header (`del_mar` is the only known tenant)
and takes ~20s end-to-end. Health alone is **not** a sufficient check — the whole
point of the chunk-13.1 incident was that `/health` stayed green while `/chat`
was broken.

Confirm the startup guard ran:

```bash
flyctl logs --no-tail | grep startup_config
# → {"setting":"EMBEDDING_PROVIDER","provider":"onnx",
#    "modules":"onnxruntime, tokenizers","event":"startup_config_ok"}
```

### Reading `flyctl status` correctly

**`VERSION` is a release counter, not a code version.** It increments on *any*
release, including secret-only changes that rebuild nothing, and a **failed**
deploy consumes a number too. A machine can report a version several higher than
the code it is actually running.

To find out what code is really live, inspect the image:

```bash
flyctl image show                                  # get the deployment-* tag
flyctl auth docker                                 # credential expires in ~2 min
docker pull registry.fly.io/dermiq-api:<tag>
docker run --rm --entrypoint sh registry.fly.io/dermiq-api:<tag> \
  -c 'ls /usr/local/lib/python3.12/site-packages/dermiq/api'
```

Note the app is installed into `site-packages`, **not** `/app` — `WORKDIR` is
`/app` but the runtime stage deliberately copies no source there (ADR-014).

---

## Deploying the frontend to Vercel

The frontend auto-deploys on every push to `main`. No manual step.

To force a rebuild without a code change:

```bash
git commit --allow-empty -m "chore: trigger vercel rebuild"
git push
```

`NEXT_PUBLIC_API_BASE_URL` is set in the Vercel dashboard. It must include the
API prefix — the code reads it as a full base:

```ts
// frontend/src/lib/api.ts
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
```

So the production value is `https://dermiq-api.fly.dev/api/v1`, **not**
`https://dermiq-api.fly.dev`. Dropping `/api/v1` produces 404s on every request
with no other symptom.

---

## Setting and rotating secrets

Same command for sensitive and non-sensitive values:

```bash
flyctl secrets set SECRET_NAME='value'
```

Fly restarts the machine with the new value automatically, roughly 30 seconds
after the change. Setting a secret creates a **new release** — this is why
release numbers advance without any code being rebuilt.

```bash
flyctl secrets list                 # names + digests only; values never retrievable
flyctl secrets unset SECRET_NAME    # remove a stale secret
```

Set several at once to trigger only one restart:

```bash
flyctl secrets set A='1' B='2' C='3'
```

> **Stale secrets cause outages that look like code bugs.** A Fly secret
> overrides the image's own `ENV`, silently. That is exactly what happened after
> the ONNX rollout: a leftover `EMBEDDING_PROVIDER` survived the migration,
> overrode `ENV EMBEDDING_PROVIDER=onnx`, and every `/chat` request raised
> `ModuleNotFoundError` while `/health` stayed green and the deploy reported
> success. The chunk-13.1 startup guard (`dermiq/api/startup.py`) now catches
> this class of problem at boot instead of at first real traffic.

---

## Configuring a new frontend domain

1. Buy the domain (Cloudflare or the Vercel registrar).
2. Vercel dashboard → project → **Settings → Domains → Add domain**.
3. If bought through Vercel, DNS is configured automatically. Otherwise add the
   records Vercel shows you at your registrar.
4. Wait for the SSL certificate — usually 2–5 minutes.
5. **Update Fly CORS.** `CORS_ORIGINS` is a full replacement, not an append, so
   list every origin you still want to work:
   ```bash
   flyctl secrets set CORS_ORIGINS='https://new-domain.com,https://www.new-domain.com,https://derm-iq.io,https://www.derm-iq.io,http://localhost:3000'
   ```
   Forgetting an existing origin here silently breaks it. Check the current
   value in the boot log rather than guessing:
   ```bash
   flyctl logs --no-tail | grep api_startup
   ```

---

## Troubleshooting production issues

### API returns 500 on `/chat`

Check the embedding provider:

```bash
flyctl logs --no-tail | grep startup_config
```

`startup_config_ok` with `provider: onnx` means the guard ran and passed. If you
see `startup_config_invalid`, the machine refused to start — fix with:

```bash
flyctl secrets set EMBEDDING_PROVIDER=onnx
```

Since chunk-13.1 this failure is caught at boot, so a misconfigured provider
shows up as a failed deploy rather than runtime 500s. A 500 on `/chat` *with* a
passing guard is something else — check the logs for Anthropic errors (503 on
API failure, 429 when the budget guard trips) or a Snowflake error reading
`rag_corpus`.

### API returns 500 on Snowflake queries

Check the logs for key decryption or auth errors. If the private key content or
passphrase is wrong:

1. Generate a fresh keypair:
   ```bash
   openssl genrsa 2048 | openssl pkcs8 -topk8 -v2 aes-256-cbc \
     -inform PEM -out ~/.ssh/snowflake_fly_key.p8
   openssl rsa -in ~/.ssh/snowflake_fly_key.p8 -pubout \
     -out ~/.ssh/snowflake_fly_key.pub
   chmod 600 ~/.ssh/snowflake_fly_key.p8
   ```
2. Register the public key on Snowflake (strip the header/footer lines and
   newlines from the `.pub` first):
   ```sql
   ALTER USER pneiman1 SET RSA_PUBLIC_KEY_2 = '<base64 body of the .pub>';
   ```
   Using `RSA_PUBLIC_KEY_2` rather than `RSA_PUBLIC_KEY` lets the old key keep
   working through the rotation; drop it afterward with
   `ALTER USER pneiman1 UNSET RSA_PUBLIC_KEY;`.
3. Base64-encode the private key:
   ```bash
   base64 -i ~/.ssh/snowflake_fly_key.p8 > ~/snowflake_key.txt
   ```
4. Set both secrets together so the machine restarts once:
   ```bash
   flyctl secrets set \
     SNOWFLAKE_PRIVATE_KEY_CONTENT="$(cat ~/snowflake_key.txt)" \
     SNOWFLAKE_PRIVATE_KEY_PASSPHRASE='newpassphrase'
   ```

The passphrase must match the key you just encoded. A mismatched pair decrypts
fine on the machine where the key was generated and fails only in the container,
which reads as a Fly problem when it is not.

Deeper check, if the key is fine but queries still fail:

```bash
curl -s https://dermiq-api.fly.dev/api/v1/health/snowflake
# → {"status":"ok","snowflake_reachable":true|false}
```

Known tech debt: the API holds **one** long-lived connection with no reconnect.
When Snowflake's master token expires (~1–2 days) queries fail with `390114`
until the machine restarts (`flyctl machine restart <id>`). See
`PROJECT_STATUS.md`.

### Fly machine stopped

Current `fly.toml` sets `min_machines_running = 1` with
`auto_stop_machines = 'stop'`, so Fly is instructed to keep one machine up and
this should be rare. If the machine *is* stopped:

```bash
flyctl status                       # find the machine id and state
flyctl machine start <machine_id>
```

A stopped machine wakes on the first request (`auto_start_machines = true`), at
the cost of a cold start. To make the machine truly always-on, keep
`min_machines_running = 1`; to allow scale-to-zero and trade latency for cost,
set it to `0`.

### Frontend not loading

1. Check the Vercel deployment status in the dashboard.
2. Chrome DevTools → Console for CORS errors. A CORS failure means the origin is
   missing from `CORS_ORIGINS` on Fly, not a Vercel problem.
3. Verify `NEXT_PUBLIC_API_BASE_URL` includes the `/api/v1` suffix.
4. Verify `CORS_ORIGINS` on Fly includes the exact origin, scheme included.

Confirm what the API actually believes:

```bash
flyctl logs --no-tail | grep api_startup   # logs database + cors_origins at boot
```

### `flyctl ssh console` fails

```
Error: ssh: can't build tunnel for personal: websocket: failed to WebSocket dial ...
```

The WireGuard tunnel is unreachable — the same constraint that makes
`--local-only` necessary. Do not treat this as the app being down. To inspect
the running container, pull its image locally instead (see *Reading `flyctl
status` correctly*).

---

## Known operational quirks

- **Fly WireGuard tunnel is unreachable from typical residential networks** →
  use `--local-only` for deploys; expect `flyctl ssh console` to fail.
- **`docker-credential-desktop` is not on `PATH`** → build succeeds, push fails.
  Prepend Docker's bin dir or remove `credsStore` from `~/.docker/config.json`.
- **Fly's `VERSION` is a release counter, not a machine or code version.** Secret
  changes and failed deploys both advance it. Inspect the image to know what is
  running.
- **A Fly secret silently overrides the image's `ENV`.** This is the mechanism
  behind the chunk-13.1 incident.
- **The Anthropic budget guard is in-memory, per process** (`_tracker` singleton
  in `dermiq/api/budget.py`). It resets on restart and is not shared across
  machines — with more than one machine the effective cap is the configured cap
  times the machine count.
- **Rate limiting is also in-memory and per process** (slowapi keyed by client
  IP): `/chat` 20/hour, `/canvas/generate` 10/hour. Same multiplication caveat.
- **Snowflake warehouse cold start.** `COMPUTE_WH` auto-suspends when idle; the
  first query after idle pays the resume. `/health/snowflake` is documented in
  the code as taking 5–10s for this reason, which is why the Fly health check
  points at the dependency-free `/health` instead.
- **`/health` deliberately does not touch Snowflake.** It cannot detect a
  broken warehouse or a broken `/chat`. Verify those separately.
- **The RAG corpus is cached in-process.** Rebuilding it
  (`scripts/build_rag_corpus.py`) requires an API restart to take effect.
- **Docker Desktop 4.35+ does not run on Monterey 12.x.** Stay on 4.34.x.
- **Local Mac dev and production authenticate to Snowflake differently.**
  Key-pair JWT fails on the Monterey 12.7.6 Intel dev machine with `JWT token is
  invalid` — matching fingerprint, correct passphrase, no clock skew, reproduced
  across connector 3.13.2 / 3.14.0 / 4.7.1, root cause undiagnosed. Local dev
  uses password + MFA (Duo) instead; production Linux uses key-pair normally.
  See [ADR-015](DECISIONS.md#adr-015-password--mfa-for-local-mac-development-key-pair-remains-the-headless-default).
  **Operationally this means local success is not evidence that production auth
  works** — a broken `SNOWFLAKE_PRIVATE_KEY_CONTENT` or passphrase on Fly cannot
  be caught from the Mac. Verify it against the deployed API:
  ```bash
  curl -s https://dermiq-api.fly.dev/api/v1/health/snowflake
  ```

---

## Cost model

Approximate monthly, at portfolio traffic:

| Line item | Cost | Notes |
|---|---|---|
| Fly.io | ~$5–10 | one always-on shared-CPU 512MB VM in `sjc` |
| Vercel | $0 | Hobby tier is sufficient |
| Snowflake | $0–5 | `COMPUTE_WH` auto-suspends when idle |
| Anthropic | <$5 | guarded by the in-app monthly budget cap |
| Domain | ~$38–45/yr | `.io` TLD renewal |

The budget guard's default cap is `$20` (`anthropic_monthly_budget_usd` in
platform-core config); the live value is whatever
`ANTHROPIC_MONTHLY_BUDGET_USD` is set to on Fly, which `flyctl secrets list`
will not show you. Setting it to `0` or less disables budget checking entirely.
Pair it with a spend alert in the Anthropic console — the in-app guard is
best-effort and dies with the process.

Rough per-call costs, measured during chunk-12: ~$0.02–0.05 per generated chart
at Sonnet-5 pricing.

---

## Related docs

- [`CLONE_TO_DEMO.md`](CLONE_TO_DEMO.md) — fresh-machine setup, start to demo
- [`DEPLOYMENT_READINESS.md`](DEPLOYMENT_READINESS.md) — the chunk-13
  pre-deployment audit this runbook is the sequel to
- [`DECISIONS.md`](DECISIONS.md) — ADRs, especially **ADR-009** (key-pair auth)
  and **ADR-014** (serving-only deps + ONNX embedder)
- [`API.md`](API.md) — endpoint reference
- [`MACOS-NOTES.md`](MACOS-NOTES.md) — macOS-specific development gotchas
- [`PROJECT_STATUS.md`](PROJECT_STATUS.md) — shipped features and known tech debt
