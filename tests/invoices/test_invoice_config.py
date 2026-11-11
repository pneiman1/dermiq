"""Service URL and tenant come from env, and the default is the local stub.

Two things these tests pin down, because both are load-bearing for a demo:
nothing has to be set for intake to work, and in ``medex`` mode nothing is
defaulted — no base URL, no tenant.
"""
from __future__ import annotations

import pytest

from dermiq.invoices import (
    InvoiceConfigError,
    InvoiceIntake,
    InvoiceServiceConfig,
    MedexExtractionService,
    StubExtractionService,
    build_extraction_service,
    load_service_config,
    required_variables,
)
from dermiq.invoices.config import (
    MEDEX_MODE,
    MODE_VAR,
    STUB_MODE,
    TENANT_VAR,
    URL_VAR,
    read_mode,
)

LIVE_ENV = {
    MODE_VAR: "medex",
    URL_VAR: "https://medex-api.fly.dev/",
    TENANT_VAR: "del_mar",
}


@pytest.fixture(autouse=True)
def clear_invoice_env(monkeypatch):
    """Keep the real environment out of the no-argument code paths."""
    for name in (MODE_VAR, URL_VAR, TENANT_VAR):
        monkeypatch.delenv(name, raising=False)


# --- the default: nothing switched on ----------------------------------------

def test_an_empty_environment_means_the_stub(monkeypatch):
    config = load_service_config()

    assert config.mode == STUB_MODE
    assert config.is_stub is True
    assert config.url == ""
    assert config.tenant == ""


def test_the_stub_requires_no_variables():
    assert required_variables(STUB_MODE) == ()
    assert required_variables() == ()


def test_the_default_service_is_the_stub():
    assert isinstance(build_extraction_service(), StubExtractionService)


def test_an_unconfigured_intake_runs_against_the_stub():
    """``InvoiceIntake()`` with nothing set is the whole point of the default."""
    intake = InvoiceIntake()

    assert isinstance(intake.service, StubExtractionService)
    assert intake.tenant == ""
    assert len(intake.store) == 0


def test_a_blank_mode_is_the_stub_not_an_error():
    assert read_mode({MODE_VAR: "   "}) == STUB_MODE


@pytest.mark.parametrize("raw", ["stub", "STUB", " Medex ", "MEDEX"])
def test_the_mode_is_read_case_and_whitespace_insensitively(raw):
    assert read_mode({MODE_VAR: raw}) in {STUB_MODE, MEDEX_MODE}


def test_an_unknown_mode_is_refused_rather_than_defaulted():
    with pytest.raises(InvoiceConfigError, match="is not a known mode"):
        load_service_config({MODE_VAR: "grpc"})


# --- medex mode: both variables required, neither defaulted ------------------

def test_medex_mode_requires_a_url_and_a_tenant():
    assert required_variables(MEDEX_MODE) == (URL_VAR, TENANT_VAR)


def test_medex_mode_names_every_missing_variable_at_once():
    with pytest.raises(InvoiceConfigError) as excinfo:
        load_service_config({MODE_VAR: "medex"})

    message = str(excinfo.value)
    assert URL_VAR in message and TENANT_VAR in message
    # And says how to get back to a working local setup.
    assert "local stub" in message


def test_a_blank_variable_counts_as_missing():
    with pytest.raises(InvoiceConfigError, match=TENANT_VAR):
        load_service_config({**LIVE_ENV, TENANT_VAR: "   "})


def test_medex_mode_reads_the_url_and_the_tenant(monkeypatch):
    for name, value in LIVE_ENV.items():
        monkeypatch.setenv(name, value)

    config = load_service_config()

    assert config.mode == MEDEX_MODE
    assert config.is_stub is False
    # Trailing slash stripped once, so a path is joined without doubling it.
    assert config.url == "https://medex-api.fly.dev"
    assert config.tenant == "del_mar"


def test_medex_mode_builds_the_medex_service(monkeypatch):
    for name, value in LIVE_ENV.items():
        monkeypatch.setenv(name, value)

    service = build_extraction_service()

    assert isinstance(service, MedexExtractionService)
    assert service.mode == MEDEX_MODE
    assert service.config.tenant == "del_mar"


def test_the_medex_service_refuses_to_be_built_without_a_tenant():
    with pytest.raises(InvoiceConfigError, match="needs both a URL and a tenant"):
        MedexExtractionService(InvoiceServiceConfig(mode=MEDEX_MODE, url="https://x.example"))


def test_a_dotenv_file_on_disk_does_not_configure_a_live_run(tmp_path, monkeypatch):
    """Config comes off the process environment, not a file lying in the checkout.

    An invoice is a document leaving the building; "it posted to the real service
    because a stale .env was in the working directory" is not a failure mode
    worth having.
    """
    (tmp_path / ".env").write_text(
        "\n".join(f"{name}={value}" for name, value in LIVE_ENV.items()), encoding="utf-8"
    )
    monkeypatch.chdir(tmp_path)

    config = load_service_config()

    assert config.is_stub is True
    assert isinstance(build_extraction_service(), StubExtractionService)
