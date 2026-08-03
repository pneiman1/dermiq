"""DermIQ API application: lifespan-managed Snowflake connection, CORS, request
logging, rate limiting, and the /api/v1 routers."""
from __future__ import annotations

import time
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import Limiter
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from platform_core.config import get_settings
from platform_core.utils.logging import configure_logging, get_logger
from platform_core.warehouse.connection import get_snowflake_connection

from dermiq.api.routers import canvas, chat, inventory, marts, meta, segments

log = get_logger(__name__)

API_PREFIX = "/api/v1"


def _get_allowed_origins() -> list[str]:
    """Parse CORS_ORIGINS from settings (comma-separated string)."""
    settings = get_settings()
    origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    return origins or ["http://localhost:3000"]


# Rate limiter: in-memory, keyed by client IP.
limiter = Limiter(key_func=get_remote_address)


def _rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    """Return 429 with Retry-After header on rate limit hit."""
    retry_after = getattr(exc, "retry_after", 60)
    log.warning("rate_limit_exceeded", path=request.url.path, client=get_remote_address(request))
    return JSONResponse(
        status_code=429,
        content={"detail": f"Rate limit exceeded. Retry after {retry_after} seconds."},
        headers={"Retry-After": str(retry_after)},
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Open one shared Snowflake connection for the app's lifetime; close on exit."""
    configure_logging()
    settings = get_settings()
    with ExitStack() as stack:
        conn = stack.enter_context(
            get_snowflake_connection(database=settings.snowflake_database)
        )
        app.state.sf_conn = conn
        app.state.settings = settings
        log.info("api_startup", database=settings.snowflake_database,
                 cors_origins=_get_allowed_origins())
        yield
        log.info("api_shutdown")


app = FastAPI(title="DermIQ API", version="1.0.0", lifespan=lifespan)

# Rate limiter state and exception handler.
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=_get_allowed_origins(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log request entry/exit with latency."""
    start = time.perf_counter()
    response = await call_next(request)
    latency_ms = round((time.perf_counter() - start) * 1000, 2)
    log.info(
        "request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        latency_ms=latency_ms,
    )
    return response


app.include_router(meta.router, prefix=API_PREFIX)
app.include_router(marts.router, prefix=API_PREFIX)
app.include_router(segments.router, prefix=API_PREFIX)
app.include_router(chat.router, prefix=API_PREFIX)
app.include_router(inventory.router, prefix=API_PREFIX)
app.include_router(canvas.router, prefix=API_PREFIX)
