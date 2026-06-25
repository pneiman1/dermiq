"""Launch the DermIQ API with uvicorn.

    python scripts/run_api.py

Equivalent to `make api-run`. Connection settings come from platform-core's
Settings (env / .env).
"""
from __future__ import annotations

import uvicorn


def main() -> None:
    uvicorn.run(
        "dermiq.api.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
    )


if __name__ == "__main__":
    main()
