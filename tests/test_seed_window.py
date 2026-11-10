"""Regimen's data window has to stay current, and this is what makes that true.

Eleven places in the dbt project measure against current_date. Three of them
fail as cliffs rather than slopes, which is why a stale window here is not a
cosmetic problem:

  int_patient_lifetime_value  recency_days = today - last_visit, which drives
                              the active / lapsing / lapsed / dormant tiers.
  mart_expiring_soon          `where expiry_date >= current_date` — lots drop
                              out of the table silently as real time passes.
  the trailing-twelve-month windows in mart_inventory_status,
  mart_true_margin_by_service and mart_channel_attribution.

The window was found 101 days behind. "Active patients — seen in last 120 days"
still read 1,812 only because 101 < 120; it would have reached zero on its own,
with no code change and no error, once the gap passed 120.

Unlike the sibling verticals these fixtures live in Snowflake rather than in
CSV seeds, so the check reads the warehouse. It skips without credentials,
which makes it a pre-deploy gate rather than a CI gate.
"""
from __future__ import annotations

import datetime
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]

pytestmark = pytest.mark.skipif(
    not os.environ.get("SNOWFLAKE_ACCOUNT"),
    reason="requires live Snowflake credentials",
)

#: Must match scripts/roll_seed_window.py. Comfortably under the 120-day
#: "active patient" definition, which is the first thing that breaks.
MAX_STALENESS_DAYS = 60


def _roll(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(REPO / "scripts" / "roll_seed_window.py"), *args],
        capture_output=True,
        text=True,
        cwd=REPO,
    )


def _freshest() -> datetime.date:
    sys.path.insert(0, str(REPO / "scripts"))
    from roll_seed_window import _connect, _freshest as freshest  # noqa: E402

    conn = _connect()
    try:
        cur = conn.cursor()
        try:
            return freshest(cur)
        finally:
            cur.close()
    finally:
        conn.close()


def test_the_data_window_is_current():
    """The headline guard. If this fails, run the roll script."""
    today = datetime.date.today()
    staleness = (today - _freshest()).days
    assert staleness <= MAX_STALENESS_DAYS, (
        f"the freshest record is {staleness} days behind {today}. "
        "Recency tiers and every trailing-twelve-month window are measured "
        "against current_date, so they drift silently.\n"
        "Fix: python scripts/roll_seed_window.py && make dbt-build"
    )


def test_nothing_is_dated_in_the_future():
    """A roll that overshoots is worse than one that lags: a clinic reporting
    tomorrow's appointments is obviously fake."""
    assert _freshest() < datetime.date.today(), "the freshest record is not in the past"


def test_the_roll_is_settled():
    """Running it again must not move the window again."""
    r = _roll("--dry-run")
    assert r.returncode == 0, r.stderr
    line = next(l for l in r.stdout.splitlines() if l.startswith("shift available"))
    assert int(line.split()[2]) < 7, f"the window is not settled: {line}"


def test_check_mode_agrees_with_these_tests():
    """--check is what a human or a cron runs; it must not disagree with CI."""
    r = _roll("--check")
    assert r.returncode == 0, f"--check reports the window stale:\n{r.stdout}{r.stderr}"
