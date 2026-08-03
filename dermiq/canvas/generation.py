"""LLM chart composition (chunk-12).

Anthropic tool-use with one tool per chart type — the model must return a
structured, validated chart spec (no free-form SQL, no hallucinated columns). On
a spec that references a missing mart/column, retry once with the error as
feedback; a second failure raises SpecError (→ 422 upstream). See ADR-013.

Reasoning + warnings ride along in each tool's input schema (stripped before the
chart spec is built). We call the Anthropic SDK directly for tool-use because
platform_core.llm's shared client only does single-turn text.
"""
from __future__ import annotations

import time
from typing import Any

import anthropic
from httpx import TimeoutException
from snowflake.connector.cursor import SnowflakeCursor

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger

from dermiq.api.budget import get_budget_tracker
from dermiq.canvas import schema as canvas_schema
from dermiq.canvas.query import SpecError, resolve_and_run
from dermiq.canvas.schemas import (
    BarSpec, KpiSpec, LineSpec, PieSpec, ScatterSpec, TableSpec,
)

# Timeout for Anthropic API calls (seconds)
ANTHROPIC_TIMEOUT = 30.0

log = get_logger(__name__)

_SPEC_MODELS = {
    "kpi": KpiSpec, "bar": BarSpec, "line": LineSpec,
    "scatter": ScatterSpec, "pie": PieSpec, "table": TableSpec,
}

_WHEN_TO_USE = {
    "kpi": "a single headline number (optionally vs the prior period).",
    "bar": "comparing a measure across a dimension's categories (ranked).",
    "line": "a measure over time (a time dimension on x).",
    "scatter": "the relationship between two measures across entities (one point per entity).",
    "pie": "a measure's composition across a small set of categories.",
    "table": "row-level detail across several columns.",
}


def _tools() -> list[dict]:
    """Build one Anthropic tool per chart type from the Pydantic schemas,
    with reasoning + warnings added to each input schema."""
    tools = []
    for name, model in _SPEC_MODELS.items():
        schema = model.model_json_schema()
        props = schema.get("properties", {})
        props.pop("type", None)  # discriminator is implied by the tool name
        props["reasoning"] = {"type": "string",
                              "description": "One sentence: why this chart type + these fields."}
        props["warnings"] = {"type": "array", "items": {"type": "string"},
                            "description": "Any assumptions you had to make (empty if none)."}
        required = [r for r in schema.get("required", []) if r != "type"] + ["reasoning"]
        tools.append({
            "name": name,
            "description": f"Compose a {name} chart. Use when {_WHEN_TO_USE[name]}",
            "input_schema": {"type": "object", "properties": props, "required": required,
                             "$defs": schema.get("$defs", {})},
        })
    return tools


def _system_prompt() -> str:
    return (
        "You are DermIQ Canvas, a visualization composer for a cosmetic dermatology "
        "analytics platform. Turn the user's request into exactly one chart by calling "
        "one of the chart tools.\n\n"
        "You may ONLY reference marts and columns that appear in the schema below. "
        "Use a dimension where a dimension is asked for and a measure where a measure "
        "is asked for. If the request is ambiguous, pick the most likely interpretation "
        "and record the assumption in `warnings`. If the request is out of scope "
        "(weather, general knowledge, anything not about this practice's data), still "
        "call the most relevant tool but explain the redirect in `reasoning` and add a "
        "warning that the request was out of scope.\n\n"
        "Available data:\n" + canvas_schema.as_prompt_text()
    )


def _call(client, model, messages) -> Any:
    return client.messages.create(
        model=model, max_tokens=1024, system=_system_prompt(),
        tools=_tools(), tool_choice={"type": "any"}, messages=messages,
        timeout=ANTHROPIC_TIMEOUT,
    )


def _extract(resp) -> tuple[str, dict]:
    for block in resp.content:
        if getattr(block, "type", None) == "tool_use":
            return block.name, dict(block.input)
    raise SpecError("The model did not return a chart.")


def _build_spec(name: str, payload: dict) -> tuple[Any, str, list[str]]:
    payload = dict(payload)
    reasoning = payload.pop("reasoning", "")
    warnings = payload.pop("warnings", []) or []
    model = _SPEC_MODELS.get(name)
    if model is None:
        raise SpecError(f"Unknown chart type '{name}'.")
    spec = model(**payload)
    return spec, reasoning, warnings


class BudgetExceededError(Exception):
    """Raised when the monthly Anthropic budget has been exceeded."""


def generate(cur: SnowflakeCursor, prompt: str, existing_charts: list[dict] | None = None) -> dict:
    """Compose + resolve a chart for `prompt`. Returns
    {chart_spec, resolved_data, reasoning, warnings, usage}. Raises SpecError if
    the model can't produce a valid spec after one retry, or BudgetExceededError
    if the monthly budget is exhausted."""
    # Check budget before making any Anthropic calls
    tracker = get_budget_tracker()
    ok, msg = tracker.check_budget()
    if not ok:
        log.warning("canvas_generate_budget_exceeded", message=msg)
        raise BudgetExceededError(msg)

    settings = get_settings()
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
    model = settings.anthropic_model_sonnet

    context = ""
    if existing_charts:
        titles = [c.get("title", c.get("type", "chart")) for c in existing_charts]
        context = f"\n\nThe canvas already has: {', '.join(titles)}. Compose a complementary chart."

    messages = [{"role": "user", "content": prompt + context}]
    t0 = time.monotonic()
    total_in = total_out = 0
    last_err = ""

    for attempt in (1, 2):
        try:
            resp = _call(client, model, messages)
        except TimeoutException as exc:
            log.error("canvas_generate_timeout", attempt=attempt, error=str(exc))
            raise anthropic.APIError("Request timed out") from exc

        total_in += resp.usage.input_tokens
        total_out += resp.usage.output_tokens
        name, payload = _extract(resp)
        try:
            spec, reasoning, warnings = _build_spec(name, payload)
            data = resolve_and_run(cur, spec, get_settings().default_tenant_id)
            latency_ms = round((time.monotonic() - t0) * 1000, 1)

            # Record usage after successful call
            tracker.record_usage(total_in, total_out)

            log.info("canvas_generate", prompt=prompt[:200], chart_type=name,
                     attempts=attempt, latency_ms=latency_ms,
                     input_tokens=total_in, output_tokens=total_out, rows=len(data))
            return {
                "chart_spec": spec.model_dump(),
                "resolved_data": data,
                "reasoning": reasoning,
                "warnings": warnings,
                "usage": {"input_tokens": total_in, "output_tokens": total_out,
                          "latency_ms": latency_ms},
            }
        except SpecError as exc:
            last_err = str(exc)
            log.info("canvas_generate_retry", attempt=attempt, error=last_err)
            messages = [{
                "role": "user",
                "content": (prompt + context + f"\n\nYour previous attempt was invalid: {last_err} "
                            "Choose only columns that exist in the schema and try again."),
            }]

    # Record usage even on failure (we still consumed tokens)
    tracker.record_usage(total_in, total_out)
    log.error("canvas_generate_failed", prompt=prompt[:200], error=last_err)
    raise SpecError(last_err or "Could not compose a valid chart for this request.")
