"""Tests for the EMBEDDING_PROVIDER startup guard (chunk-13.1).

Regression cover for the production incident where a stale EMBEDDING_PROVIDER
secret named a backend the slim image does not ship: every /chat request 500'd
with ModuleNotFoundError while the health check stayed green.

These need no Snowflake credentials — the guard runs ahead of the connection in
the lifespan, which is the point of it.
"""
from __future__ import annotations

import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from dermiq.api.startup import (
    EMBEDDING_PROVIDER_MODULES,
    StartupConfigError,
    verify_embedding_provider,
)


def _settings(provider: str) -> SimpleNamespace:
    return SimpleNamespace(embedding_provider=provider)


def test_passes_when_provider_module_is_installed():
    """onnx is what the API image ships, and what the dev venv has."""
    with patch("dermiq.api.startup.get_settings", return_value=_settings("onnx")):
        verify_embedding_provider()  # does not raise


def test_raises_when_provider_module_is_missing():
    """The actual incident: a valid provider name whose module is absent."""
    with patch("dermiq.api.startup.get_settings", return_value=_settings("sentence_transformers")):
        with patch("dermiq.api.startup.importlib.util.find_spec", return_value=None):
            with pytest.raises(StartupConfigError) as exc:
                verify_embedding_provider()

    message = str(exc.value)
    # The operator needs both halves to act: which setting is wrong, and what is
    # missing because of it.
    assert "sentence_transformers" in message
    assert "onnx" in message, "should point at the backend this image does ship"


def test_error_names_every_missing_module():
    """onnx needs two modules; a partial install must name the one that is gone."""
    def fake_find_spec(name: str):
        return None if name == "tokenizers" else object()

    with patch("dermiq.api.startup.get_settings", return_value=_settings("onnx")):
        with patch("dermiq.api.startup.importlib.util.find_spec", side_effect=fake_find_spec):
            with pytest.raises(StartupConfigError, match="tokenizers"):
                verify_embedding_provider()


def test_raises_on_provider_this_guard_does_not_know():
    """A backend added to platform-core's Literal but not to the module map."""
    with patch("dermiq.api.startup.get_settings", return_value=_settings("some_new_backend")):
        with pytest.raises(StartupConfigError, match="some_new_backend"):
            verify_embedding_provider()


def test_logs_structured_error_before_raising():
    """Fly's logs are the only debugging surface once the container is dead."""
    with patch("dermiq.api.startup.get_settings", return_value=_settings("sentence_transformers")):
        with patch("dermiq.api.startup.importlib.util.find_spec", return_value=None):
            with patch("dermiq.api.startup.log") as mock_log:
                with pytest.raises(StartupConfigError):
                    verify_embedding_provider()

    mock_log.error.assert_called_once()
    event, kwargs = mock_log.error.call_args[0][0], mock_log.error.call_args[1]
    assert event == "startup_config_invalid"
    assert kwargs["setting"] == "EMBEDDING_PROVIDER"
    assert kwargs["provider"] == "sentence_transformers"
    assert kwargs["reason"] == "missing_module"
    assert "sentence_transformers" in kwargs["missing_modules"]


def test_app_startup_aborts_on_bad_provider():
    """The guard is actually wired into the lifespan, not just importable."""
    from dermiq.api.main import app

    with patch("dermiq.api.startup.get_settings", return_value=_settings("sentence_transformers")):
        with patch("dermiq.api.startup.importlib.util.find_spec", return_value=None):
            with pytest.raises(StartupConfigError):
                with TestClient(app):
                    pass  # never reached: startup raises before yielding


def _embedder_settings(provider: str) -> SimpleNamespace:
    """The attributes Embedder.__init__ reads. It does not load a model, so
    constructing one is cheap enough to do per-provider in a unit test."""
    return SimpleNamespace(
        embedding_provider=provider,
        sentence_transformers_model="all-MiniLM-L6-v2",
        onnx_model_dir="/nonexistent",
        onnx_max_seq_length=256,
    )


def _embedder_accepts(provider: str) -> bool:
    """Does platform-core's Embedder actually wire this provider?"""
    from platform_core.rag.embedder import Embedder

    with patch("platform_core.rag.embedder.get_settings",
               return_value=_embedder_settings(provider)):
        try:
            Embedder()
        except NotImplementedError:
            return False
    return True


def test_guard_map_matches_what_the_embedder_implements():
    """The guard's accepted set must equal the Embedder's wired set.

    A provider in the map that the Embedder rejects would sail through startup
    and raise NotImplementedError on the first /chat query — precisely the
    deferred failure this guard was written to eliminate. 'voyage' was in the
    map for exactly that reason until chunk-13.1's cleanup.
    """
    for provider in EMBEDDING_PROVIDER_MODULES:
        assert _embedder_accepts(provider), (
            f"{provider!r} is guard-accepted but not wired in Embedder — it would "
            "pass startup and fail on the first query"
        )


def test_configurable_but_unimplemented_provider_fails_closed():
    """platform-core's Literal is wider than the map, and must fail at startup.

    'voyage' is scaffolded in config with no backend behind it. Configuring it
    has to abort the process, not defer to request time.
    """
    from platform_core.config import Settings

    configurable = set(Settings.model_fields["embedding_provider"].annotation.__args__)
    unimplemented = configurable - set(EMBEDDING_PROVIDER_MODULES)
    assert "voyage" in unimplemented, "guard rejects voyage until a backend exists"

    for provider in unimplemented:
        assert not _embedder_accepts(provider), (
            f"{provider!r} is wired in Embedder but missing from the guard map — "
            "add it to EMBEDDING_PROVIDER_MODULES"
        )
        with patch("dermiq.api.startup.get_settings", return_value=_settings(provider)):
            with pytest.raises(StartupConfigError, match=provider):
                verify_embedding_provider()


@pytest.mark.slow
def test_uvicorn_exits_nonzero_on_bad_provider():
    """End-to-end: the requirement is a non-zero exit, so Fly's health check fails
    and the rolling deploy halts. Uses voyage because config still admits it and
    no backend implements it — no mocking, and it exercises the same abort path
    the production failure took."""
    result = subprocess.run(
        [sys.executable, "-m", "uvicorn", "dermiq.api.main:app", "--port", "8931"],
        env={"PATH": "/usr/bin:/bin", "EMBEDDING_PROVIDER": "voyage", "HOME": "/tmp"},
        capture_output=True,
        text=True,
        timeout=120,
    )

    assert result.returncode != 0, "a misconfigured provider must not exit 0"
    combined = result.stdout + result.stderr
    assert "startup_config_invalid" in combined, "structured error must reach the logs"
    assert "voyage" in combined
    assert "unknown_provider" in combined
