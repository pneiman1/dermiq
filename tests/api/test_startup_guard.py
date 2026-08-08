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
    with patch("dermiq.api.startup.get_settings", return_value=_settings("voyage")):
        with patch("dermiq.api.startup.importlib.util.find_spec", return_value=None):
            with patch("dermiq.api.startup.log") as mock_log:
                with pytest.raises(StartupConfigError):
                    verify_embedding_provider()

    mock_log.error.assert_called_once()
    event, kwargs = mock_log.error.call_args[0][0], mock_log.error.call_args[1]
    assert event == "startup_config_invalid"
    assert kwargs["setting"] == "EMBEDDING_PROVIDER"
    assert kwargs["provider"] == "voyage"
    assert kwargs["reason"] == "missing_module"
    assert "voyageai" in kwargs["missing_modules"]


def test_app_startup_aborts_on_bad_provider():
    """The guard is actually wired into the lifespan, not just importable."""
    from dermiq.api.main import app

    with patch("dermiq.api.startup.get_settings", return_value=_settings("sentence_transformers")):
        with patch("dermiq.api.startup.importlib.util.find_spec", return_value=None):
            with pytest.raises(StartupConfigError):
                with TestClient(app):
                    pass  # never reached: startup raises before yielding


def test_module_map_covers_every_configurable_provider():
    """A provider pydantic accepts but the map lacks would fail closed at startup;
    catching it here is cheaper than catching it on a deploy."""
    from platform_core.config import Settings

    configurable = set(Settings.model_fields["embedding_provider"].annotation.__args__)
    assert configurable == set(EMBEDDING_PROVIDER_MODULES)


@pytest.mark.slow
def test_uvicorn_exits_nonzero_on_bad_provider():
    """End-to-end: the requirement is a non-zero exit, so Fly's health check fails
    and the rolling deploy halts. Uses voyage because voyageai is genuinely not
    installed — no mocking, the same shape as the production failure."""
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
    assert "voyageai" in combined
