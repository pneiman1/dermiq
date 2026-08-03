"""Monthly Anthropic API budget guard (chunk-13).

Simple in-memory tracker that estimates monthly spend based on Sonnet 5 pricing
and rejects LLM calls after the configured cap is reached. Resets automatically
on the first day of each new month.

Pricing (as of 2026-07):
- Sonnet 5: $3 / 1M input tokens, $15 / 1M output tokens

This is a best-effort guard for a portfolio demo — not a replacement for
Anthropic dashboard alerts or hard limits in production.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger

log = get_logger(__name__)

# Sonnet 5 pricing: $3/1M input, $15/1M output
INPUT_COST_PER_TOKEN = 3.0 / 1_000_000
OUTPUT_COST_PER_TOKEN = 15.0 / 1_000_000


@dataclass
class BudgetTracker:
    """In-memory monthly spend tracker."""

    current_month: date = field(default_factory=lambda: date.today().replace(day=1))
    input_tokens: int = 0
    output_tokens: int = 0

    def _maybe_reset(self) -> None:
        """Reset counters if we've rolled into a new month."""
        this_month = date.today().replace(day=1)
        if this_month > self.current_month:
            log.info(
                "budget_reset",
                prev_month=self.current_month.isoformat(),
                input_tokens=self.input_tokens,
                output_tokens=self.output_tokens,
                estimated_spend_usd=self.estimated_spend_usd,
            )
            self.current_month = this_month
            self.input_tokens = 0
            self.output_tokens = 0

    @property
    def estimated_spend_usd(self) -> float:
        """Estimated spend this month based on token counts."""
        return (
            self.input_tokens * INPUT_COST_PER_TOKEN
            + self.output_tokens * OUTPUT_COST_PER_TOKEN
        )

    def check_budget(self) -> tuple[bool, str]:
        """Check if budget is available.

        Returns (ok, message). If ok is False, message explains why.
        """
        self._maybe_reset()
        settings = get_settings()
        budget = settings.anthropic_monthly_budget_usd

        if budget <= 0:
            return True, "budget checking disabled"

        if self.estimated_spend_usd >= budget:
            msg = (
                f"Monthly Anthropic budget exceeded (${self.estimated_spend_usd:.2f} / "
                f"${budget:.2f}). Resets on the 1st of next month."
            )
            return False, msg

        return True, "ok"

    def record_usage(self, input_tokens: int, output_tokens: int) -> None:
        """Record token usage from an Anthropic call."""
        self._maybe_reset()
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        log.info(
            "budget_usage",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            month_input_total=self.input_tokens,
            month_output_total=self.output_tokens,
            estimated_spend_usd=round(self.estimated_spend_usd, 4),
            budget_usd=get_settings().anthropic_monthly_budget_usd,
        )


# Global singleton tracker (resets on process restart, which is acceptable for
# a portfolio demo — Fly.io machines restart infrequently).
_tracker: BudgetTracker | None = None


def get_budget_tracker() -> BudgetTracker:
    """Get or create the global budget tracker."""
    global _tracker
    if _tracker is None:
        _tracker = BudgetTracker()
    return _tracker
