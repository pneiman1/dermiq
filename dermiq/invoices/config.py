"""Where the extraction service lives, and which tenant's documents we send it.

Three environment variables, read straight off ``os.environ``:

======================================  ==================================================
``INVOICE_SERVICE_MODE``                ``stub`` (default) or ``medex``
``INVOICE_SERVICE_URL``                 Base URL. Required in ``medex`` mode, unused in stub.
``INVOICE_SERVICE_TENANT``              Tenant the documents belong to. Required in ``medex``.
======================================  ==================================================

The default is ``stub``, and the stub needs neither of the other two — that is
what lets ``InvoiceIntake()`` work in a test or a demo with nothing switched on.
In ``medex`` mode both are required with no fallback: a base URL defaulted to
somebody's production host is how a demo run posts real documents at a real
service, and a defaulted tenant is how one practice's cost lands in another's
warehouse.

WHY ``medex`` AND NOT A GENERIC ``http``. The sibling verticals carry an
``http`` mode against a wire contract of their own definition — POST
``/v1/invoices``, poll ``/v1/invoices/{job_id}``. Nothing implements that
contract. What exists is medex, whose shape is genuinely different: the upload
is the whole transaction, there is no job id to poll, and the document it reads
is a billing packet rather than a purchase order. Naming the mode after the
service it actually talks to is honest; calling it ``http`` would imply a
service could be swapped in behind it, and one could not. The adapter and its
mapping live in :mod:`dermiq.invoices.service`.

Read off the process environment rather than through platform-core's
``Settings``, which parses ``.env``: a document leaving the building is the
wrong place for "it worked locally because a stale ``.env`` was lying around".
A missing variable names itself instead.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

#: Env var names, in one place so the error messages and the docs cannot drift.
MODE_VAR = "INVOICE_SERVICE_MODE"
URL_VAR = "INVOICE_SERVICE_URL"
TENANT_VAR = "INVOICE_SERVICE_TENANT"

STUB_MODE = "stub"
MEDEX_MODE = "medex"
MODES: frozenset[str] = frozenset({STUB_MODE, MEDEX_MODE})

#: Variables each mode requires. The stub requires nothing, by design.
REQUIRED_VARS: dict[str, tuple[str, ...]] = {
    STUB_MODE: (),
    MEDEX_MODE: (URL_VAR, TENANT_VAR),
}


class InvoiceConfigError(RuntimeError):
    """The invoice service is configured in a way that cannot be acted on."""


@dataclass(frozen=True)
class InvoiceServiceConfig:
    """Resolved service configuration. ``url`` and ``tenant`` are "" in stub mode."""

    mode: str = STUB_MODE
    url: str = ""
    tenant: str = ""

    @property
    def is_stub(self) -> bool:
        return self.mode == STUB_MODE


def required_variables(mode: str | None = None) -> tuple[str, ...]:
    """Env vars that must be set for ``mode`` (defaults to the current mode)."""
    resolved = read_mode() if mode is None else _normalize_mode(mode)
    return REQUIRED_VARS[resolved]


def _normalize_mode(raw: str) -> str:
    mode = raw.strip().lower()
    if mode not in MODES:
        raise InvoiceConfigError(
            f"{MODE_VAR}={raw!r} is not a known mode; expected one of {sorted(MODES)}"
        )
    return mode


def read_mode(env: dict[str, str] | None = None) -> str:
    """Resolve the mode, defaulting to the stub. Case and whitespace insensitive."""
    source = os.environ if env is None else env
    raw = source.get(MODE_VAR, "")
    if not raw.strip():
        return STUB_MODE
    return _normalize_mode(raw)


def load_service_config(env: dict[str, str] | None = None) -> InvoiceServiceConfig:
    """Build the service config from the environment, failing on what is missing.

    Every missing variable for the chosen mode is named in one message, so a
    misconfigured deployment is fixed in one pass rather than one restart per
    variable. A variable set to blank counts as missing.
    """
    source = dict(os.environ if env is None else env)
    mode = read_mode(source)

    missing = [name for name in REQUIRED_VARS[mode] if not source.get(name, "").strip()]
    if missing:
        raise InvoiceConfigError(
            f"{MODE_VAR}={mode} needs {', '.join(missing)}: set them, or leave "
            f"{MODE_VAR} unset to run against the local stub"
        )

    return InvoiceServiceConfig(
        mode=mode,
        url=source.get(URL_VAR, "").strip().rstrip("/"),
        tenant=source.get(TENANT_VAR, "").strip(),
    )
