"""DermIQ API application: lifespan-managed Snowflake connection, CORS, request
logging, and the /api/v1 routers."""
from __future__ import annotations

import time
from contextlib import ExitStack, asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from platform_core.config import get_settings
from platform_core.utils.logging import configure_logging, get_logger
from platform_core.warehouse.connection import get_snowflake_connection

from dermiq.api.routers import canvas, chat, inventory, marts, meta, segments

log = get_logger(__name__)

API_PREFIX = "/api/v1"
# The Next.js dev server (chunk-7).
ALLOWED_ORIGINS = ["http://localhost:3000"]


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
        log.info("api_startup", database=settings.snowflake_database)
        yield
        log.info("api_shutdown")


app = FastAPI(title="DermIQ API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
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
