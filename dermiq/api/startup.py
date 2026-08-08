"""Startup configuration guards.

The slim API image (ADR-014) ships exactly one embedding backend: ONNX. Nothing
stops a deploy-time env var from naming a different one, and when that happened
in production the failure mode was bad — a stale ``EMBEDDING_PROVIDER`` Fly
secret survived the ONNX rollout and overrode the image's own ``ENV``, so every
/chat request raised ``ModuleNotFoundError: No module named
'sentence_transformers'`` while ``/api/v1/health`` stayed green and the deploy
reported success. The embedding backend is imported lazily on the first query,
so nothing touched it until real traffic did.

These guards run that import check at process startup instead. A misconfigured
provider now fails the container before it can serve, which fails Fly's health
check and halts the rolling deploy, rather than surfacing as 500s later.
"""
from __future__ import annotations

import importlib.util

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger

log = get_logger(__name__)

# The import each embedding backend performs at request time. Mirrors the lazy
# imports in platform_core.rag.embedder — when a backend is added there, add it
# here too, or it will pass this guard and fail on the first query instead.
EMBEDDING_PROVIDER_MODULES: dict[str, tuple[str, ...]] = {
    "onnx": ("onnxruntime", "tokenizers"),
    "sentence_transformers": ("sentence_transformers",),
    "voyage": ("voyageai",),
}


class StartupConfigError(RuntimeError):
    """Configuration this process cannot serve with.

    Raised out of the lifespan handler, which aborts uvicorn's startup and exits
    non-zero — the container never reaches a listening state.
    """


def _missing_modules(modules: tuple[str, ...]) -> list[str]:
    """Return the subset of ``modules`` that cannot be imported.

    Uses find_spec rather than a real import: it answers the only question we
    have without paying to initialize the backend (importing onnxruntime or
    torch at startup would cost seconds and memory for no benefit). find_spec
    itself raises when an intermediate parent package is missing, which is just
    another way of being unimportable.
    """
    missing = []
    for module in modules:
        try:
            if importlib.util.find_spec(module) is None:
                missing.append(module)
        except (ImportError, ValueError):
            missing.append(module)
    return missing


def verify_embedding_provider() -> None:
    """Fail startup unless the configured embedding backend can actually load.

    Raises:
        StartupConfigError: the provider is unknown to this guard, or its
            module(s) are not installed in this image.
    """
    settings = get_settings()
    provider = settings.embedding_provider

    required = EMBEDDING_PROVIDER_MODULES.get(provider)
    if required is None:
        # Reachable if platform-core's Literal gains a provider before this map
        # does. Refusing to start beats starting and failing per-request.
        known = ", ".join(sorted(EMBEDDING_PROVIDER_MODULES))
        log.error(
            "startup_config_invalid",
            setting="EMBEDDING_PROVIDER",
            provider=provider,
            reason="unknown_provider",
            known_providers=known,
        )
        raise StartupConfigError(
            f"EMBEDDING_PROVIDER={provider!r} is not a provider this API knows how "
            f"to validate. Known providers: {known}."
        )

    missing = _missing_modules(required)
    if missing:
        log.error(
            "startup_config_invalid",
            setting="EMBEDDING_PROVIDER",
            provider=provider,
            reason="missing_module",
            missing_modules=", ".join(missing),
            required_modules=", ".join(required),
        )
        raise StartupConfigError(
            f"EMBEDDING_PROVIDER={provider!r} needs the "
            f"{', '.join(repr(m) for m in missing)} module(s), which are not installed "
            f"in this image. The API image ships the 'onnx' backend only (ADR-014) — "
            f"either set EMBEDDING_PROVIDER=onnx, or check for a stale env var or "
            f"platform secret overriding the image's own ENV."
        )

    log.info(
        "startup_config_ok",
        setting="EMBEDDING_PROVIDER",
        provider=provider,
        modules=", ".join(required),
    )
