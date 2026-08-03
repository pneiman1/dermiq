# Deployment Readiness Audit

**Date:** Aug 2, 2026
**Target deployment:**
- Frontend: Vercel
- Backend API: Fly.io
- Auth: Snowflake keypair (works on Linux)
- LLM: Anthropic API with $20/month budget cap
- Mode: Static demo (single Del Mar tenant)

---

## Summary

| Area | Status | Effort | Priority |
|------|--------|--------|----------|
| 1. CORS Configuration | **BLOCKER** | Small | Must fix |
| 2. Rate Limiting | **BLOCKER** | Medium | Must fix |
| 3. Anthropic Error Handling | Partial | Small | High |
| 4. Snowflake Connection | Ready | None | — |
| 5. Environment Configuration | Ready | None | — |
| 6. Frontend Configuration | Ready | None | — |
| 7. Tenant Isolation | Ready | None | — |
| 8. Deployment Artifacts | **BLOCKER** | Medium | Must fix |
| 9. Cost Controls | Missing | Medium | High |
| 10. Health Check | Partial | Small | High |

**Blockers to fix before deploy:** 3 items (CORS, rate limiting, Dockerfile)

---

## 1. CORS Configuration

### What exists

`dermiq/api/main.py:21-48`:
```python
ALLOWED_ORIGINS = ["http://localhost:3000"]  # hardcoded

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    ...
)
```

### What's missing

- No `CORS_ORIGINS` env var support
- Cannot accept Vercel URL without code change

### Recommended fix

```python
import os

ALLOWED_ORIGINS = os.getenv(
    "CORS_ORIGINS",
    "http://localhost:3000"
).split(",")
```

Then set `CORS_ORIGINS=https://dermiq.vercel.app,http://localhost:3000` in Fly.io secrets.

### Effort: Small (5 lines)
### Priority: **BLOCKER** — API will reject all frontend requests without this

---

## 2. Rate Limiting

### What exists

Nothing. No rate limiting on any endpoint.

### What's missing

Both LLM endpoints (`/canvas/generate`, `/chat`) call Anthropic with no throttling:
- `dermiq/api/routers/canvas.py:60-74` — no rate limit
- `dermiq/api/routers/chat.py:60-104` — no rate limit

A malicious actor (or overeager demo visitor) could run up the Anthropic bill quickly.

### Recommended fix

Add `slowapi` to `pyproject.toml` and implement per-IP rate limits:

```python
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

@router.post("/canvas/generate")
@limiter.limit("10/hour")  # LLM endpoints: tight limit
def canvas_generate(...): ...

@router.post("/chat")
@limiter.limit("10/hour")
def chat(...): ...

@router.get("/revenue/daily")
@limiter.limit("100/hour")  # read endpoints: looser
def revenue_daily(...): ...
```

### Effort: Medium (~30 min)
### Priority: **BLOCKER** — uncontrolled costs without this

---

## 3. Anthropic Call Safety

### What exists

**Error handling** is partially implemented:

`dermiq/api/routers/canvas.py:73-74`:
```python
except anthropic.APIError as exc:
    raise HTTPException(status_code=503, detail="...temporarily unavailable...")
```

`dermiq/api/routers/chat.py:91-93`:
```python
except Exception as exc:
    log.error("chat_generation_failed", error=str(exc), exc_info=True)
    raise HTTPException(status_code=502, detail="chat generation failed")
```

**Token usage logging** exists:

`dermiq/canvas/generation.py:136-138`:
```python
log.info("canvas_generate", ..., input_tokens=total_in, output_tokens=total_out, ...)
```

`platform_core/llm/anthropic_client.py:67-72`:
```python
log.info("llm_complete", model=self.model, input_tokens=..., output_tokens=...)
```

### What's missing

1. **No timeout configuration** — defaults to SDK timeout (~10 min); long-running requests could hang
2. **No max_tokens enforcement** — uses 1024 default; safe for now but worth documenting
3. **No cumulative usage tracking** — tokens are logged but not aggregated

### Recommended fix

Add timeout to Anthropic client calls:
```python
resp = client.messages.create(..., timeout=30.0)  # 30 second timeout
```

### Effort: Small
### Priority: High (graceful degradation)

---

## 4. Snowflake Connection in Production

### What exists

`platform_core/warehouse/connection.py:24`:
```python
key_path = Path(path).expanduser()  # handles ~ correctly
```

`connection.py:104`:
```python
client_session_keep_alive=True  # good for long-lived Fly.io process
```

Keypair auth is fully implemented and works with env vars:
- `SNOWFLAKE_PRIVATE_KEY_PATH` — can point to `/app/secrets/snowflake.p8`
- `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` — from Fly secrets

### What's missing

Nothing blocking. The implementation handles container paths correctly.

### Fly.io secret file setup

```bash
# Create secret from local key file
fly secrets set SNOWFLAKE_PRIVATE_KEY="$(cat ~/.ssh/snowflake_rsa_key.p8)"

# Or mount as a file (preferred for large keys)
# In Dockerfile or fly.toml, write secret to /app/secrets/snowflake.p8
```

### Effort: None needed
### Priority: Ready

---

## 5. Environment Configuration

### What exists

Full pydantic-settings config in `platform_core/config/__init__.py`.

### Required env vars for production

| Variable | Description | Example |
|----------|-------------|---------|
| `SNOWFLAKE_ACCOUNT` | Snowflake account identifier | `abc12345.us-west-2` |
| `SNOWFLAKE_USER` | Snowflake username | `DERMIQ_SVC` |
| `SNOWFLAKE_PRIVATE_KEY_PATH` | Path to .p8 key file | `/app/secrets/snowflake.p8` |
| `SNOWFLAKE_PRIVATE_KEY_PASSPHRASE` | Key passphrase | (secret) |
| `SNOWFLAKE_ROLE` | Role to use | `ACCOUNTADMIN` |
| `SNOWFLAKE_WAREHOUSE` | Warehouse | `COMPUTE_WH` |
| `SNOWFLAKE_DATABASE` | Database | `DERMIQ_DEV` |
| `ANTHROPIC_API_KEY` | Anthropic API key | `sk-ant-...` |
| `CORS_ORIGINS` | Allowed origins (after fix) | `https://dermiq.vercel.app` |
| `ENVIRONMENT` | Environment name | `prod` |
| `LOG_LEVEL` | Log verbosity | `INFO` |

### What points to localhost

Only the fallback in `config/__init__.py:72`:
```python
database_url: str = "postgresql://dermiq:dermiq@localhost:5432/dermiq"
```

This is the app database URL (Postgres + pgvector), **not used by the API** — the API only talks to Snowflake. Safe to ignore for Vercel+Fly deployment.

### API host binding

`Makefile:62`:
```makefile
$(UVICORN) dermiq.api.main:app --reload --port 8000 --host 0.0.0.0
```

Binds to `0.0.0.0` — correct for containers.

### Effort: None needed
### Priority: Ready

---

## 6. Frontend Production Configuration

### What exists

`frontend/src/lib/api.ts:30-31`:
```typescript
const BASE = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1";
const TENANT = process.env.NEXT_PUBLIC_TENANT_ID ?? "del_mar";
```

Both are configurable via env vars with sensible defaults.

### Vercel environment variables

Set in Vercel dashboard or `vercel.json`:
```
NEXT_PUBLIC_API_BASE_URL=https://dermiq-api.fly.dev/api/v1
NEXT_PUBLIC_TENANT_ID=del_mar
```

### next.config.mjs

Currently empty — no special configuration needed. Vercel auto-detects Next.js.

### Effort: None needed
### Priority: Ready

---

## 7. Data Safety / Tenant Isolation

### What exists

**All queries use the tenant-scoped `fq()` helper:**

`dermiq/api/fqn.py:12-15`:
```python
def fq(layer: str, table: str, tenant: str) -> str:
    database = get_settings().snowflake_database
    return f"{database}.{schema_name(layer, tenant)}.{table}"
```

This produces `DERMIQ_DEV.MART_DEL_MAR.mart_revenue_daily` — schema name includes tenant.

**Tenant validation:**

`dermiq/api/deps.py:16-28`:
```python
KNOWN_TENANTS = {"del_mar"}

def current_tenant(x_tenant_id: str | None = Header(...)) -> str:
    if x_tenant_id is None or x_tenant_id not in KNOWN_TENANTS:
        raise HTTPException(status_code=400, detail="missing or invalid X-Tenant-ID header")
    return x_tenant_id
```

**Canvas persistence uses tenant in WHERE clause:**

`dermiq/api/routers/canvas.py:117`:
```python
cur.execute(
    f"select ... where canvas_id = %s and tenant_id = %s",
    (canvas_id, tenant),
)
```

### What's missing

Nothing. Tenant isolation is properly implemented via:
1. Schema-level separation (schemas named `LAYER_TENANT`)
2. Whitelist validation on `X-Tenant-ID` header
3. Parameterized queries with tenant in WHERE clauses

### Credentials in responses

No endpoints expose raw credentials. Snowflake connection details stay server-side.

### Effort: None needed
### Priority: Ready

---

## 8. Deployment Artifacts

### What exists

- `airflow/Dockerfile` — for Astronomer, not the API
- `Makefile` — development commands only

### What's missing

**API Dockerfile** — **BLOCKER**

Recommended `Dockerfile`:
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install system deps for cryptography + snowflake-connector
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libffi-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install platform-core first (sibling repo)
COPY platform-core /app/platform-core
RUN pip install --no-cache-dir /app/platform-core

# Copy and install dermiq
COPY dermiq /app/dermiq
RUN pip install --no-cache-dir "/app/dermiq[api,rag]"

EXPOSE 8000

CMD ["uvicorn", "dermiq.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**fly.toml** — **BLOCKER**

Recommended `fly.toml`:
```toml
app = "dermiq-api"
primary_region = "sjc"

[build]
  dockerfile = "Dockerfile"

[http_service]
  internal_port = 8000
  force_https = true
  auto_stop_machines = true
  auto_start_machines = true
  min_machines_running = 0

[http_service.concurrency]
  type = "requests"
  hard_limit = 25
  soft_limit = 20

[[vm]]
  cpu_kind = "shared"
  cpus = 1
  memory_mb = 512

[env]
  ENVIRONMENT = "prod"
  LOG_LEVEL = "INFO"
```

**vercel.json** — Optional (Vercel auto-detects Next.js)

### Effort: Medium (~1 hour)
### Priority: **BLOCKER** — cannot deploy without Dockerfile

---

## 9. Cost Controls

### What exists

Token usage is logged per-call:
- `canvas/generation.py:136-138` logs `input_tokens`, `output_tokens`
- `platform_core/llm/anthropic_client.py:67-72` logs same

### What's missing

1. **No budget tracking** — no aggregation of spend
2. **No circuit breaker** — no way to stop calls if budget exceeded
3. **No daily/monthly caps** — relies entirely on rate limiting

### Recommended implementation

Option A: **External monitoring** (simplest for portfolio demo)
- Enable Anthropic dashboard usage alerts at $15 and $20
- Set hard limit in Anthropic console at $25

Option B: **In-app tracking** (more robust)
```python
# Add to a new module: dermiq/api/usage.py
from datetime import date
from collections import defaultdict

_daily_tokens: dict[date, dict[str, int]] = defaultdict(lambda: {"input": 0, "output": 0})
DAILY_INPUT_LIMIT = 500_000  # ~$1.50/day at Sonnet pricing
DAILY_OUTPUT_LIMIT = 100_000

def track_usage(input_tokens: int, output_tokens: int) -> None:
    today = date.today()
    _daily_tokens[today]["input"] += input_tokens
    _daily_tokens[today]["output"] += output_tokens

def check_budget() -> bool:
    today = date.today()
    return (_daily_tokens[today]["input"] < DAILY_INPUT_LIMIT and
            _daily_tokens[today]["output"] < DAILY_OUTPUT_LIMIT)
```

### Effort: Medium
### Priority: High — $20/month budget can be exceeded quickly without controls

---

## 10. Health Check Endpoint

### What exists

`dermiq/api/routers/meta.py:15-26`:
```python
@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    reachable = True
    try:
        cur = request.app.state.sf_conn.cursor()
        cur.execute("select 1")  # <-- hits Snowflake
        cur.fetchone()
        cur.close()
    except Exception:
        reachable = False
    return HealthResponse(status="ok", snowflake_reachable=reachable)
```

### What's missing

**The health check queries Snowflake** — this is slow and can fail if the warehouse is suspended.

Fly.io health checks run every 10s by default. If the warehouse is cold, `select 1` takes 5-10s to wake it, causing:
1. Health check timeouts
2. Container restarts
3. Higher Snowflake costs (constant warehouse wake-ups)

### Recommended fix

Split into two endpoints:

```python
@router.get("/health")  # Fly.io liveness probe — instant
def health() -> dict:
    return {"status": "ok"}

@router.get("/health/snowflake")  # Full check — call manually or infrequently
def health_snowflake(request: Request) -> HealthResponse:
    reachable = True
    try:
        cur = request.app.state.sf_conn.cursor()
        cur.execute("select 1")
        cur.fetchone()
        cur.close()
    except Exception:
        reachable = False
    return HealthResponse(status="ok", snowflake_reachable=reachable)
```

Configure Fly.io to use the fast endpoint:
```toml
[[services.http_checks]]
  path = "/api/v1/health"
  interval = "15s"
  timeout = "2s"
```

### Effort: Small (10 min)
### Priority: High — affects container stability and Snowflake costs

---

## Pre-deployment Checklist

### Must fix before deploy (blockers)

- [ ] Add `CORS_ORIGINS` env var support to `main.py`
- [ ] Add rate limiting with `slowapi` (10/hour on LLM endpoints)
- [ ] Create API `Dockerfile`
- [ ] Create `fly.toml`

### Should fix (high priority)

- [ ] Split `/health` into fast and full versions
- [ ] Add Anthropic request timeout (30s)
- [ ] Set up Anthropic dashboard spending alerts ($15, $20, $25)

### Nice to have

- [ ] In-app daily token budget tracking
- [ ] Request ID correlation in logs
- [ ] Structured error responses (error codes, not just messages)

---

## Estimated effort

| Task | Time |
|------|------|
| CORS env var | 15 min |
| Rate limiting | 45 min |
| Dockerfile + fly.toml | 1 hour |
| Health check split | 15 min |
| Anthropic timeout | 10 min |
| **Total blockers** | **~2.5 hours** |

---

*Generated: Aug 2, 2026*
