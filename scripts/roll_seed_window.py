"""Roll Regimen's data window forward so the demo tracks the current date.

Same job as the sibling verticals' roll scripts, different mechanism. Barrel and
Yield keep their fixtures in CSV seeds, so rolling them rewrites files. Regimen's
data lives in RAW_<TENANT> Snowflake tables — only marketing_spend is a seed —
so the roll is a set of UPDATE statements against the warehouse plus one CSV.

    python scripts/roll_seed_window.py            # roll the window to now
    python scripts/roll_seed_window.py --check     # exit 1 if it has gone stale
    python scripts/roll_seed_window.py --dry-run   # report the shift, change nothing

WHY IT MATTERS HERE MORE THAN ANYWHERE ELSE. Eleven places in the dbt project
measure against current_date, and three of them are cliffs rather than slopes:

  int_patient_lifetime_value  recency_days = today - last_visit, which drives the
                              active / lapsing / lapsed / dormant tiers. Every
                              patient's recency inflates by exactly the staleness.
  mart_expiring_soon          `where expiry_date >= current_date` — lots silently
                              drop out of the table as real time passes.
  mart_inventory_status,      trailing-twelve-month windows anchored on today,
  mart_true_margin_by_service which quietly stop overlapping the data.
  mart_channel_attribution

The Executive page reports "Active patients — seen in last 120 days". With the
window 101 days behind, that count was still 1,812 only because 101 < 120. It
reaches zero on its own, with no code change and no error, once the gap passes
120 days.

THE SHIFT IS A WHOLE NUMBER OF WEEKS. This clinic is closed Sundays — 76 of the
76 Sundays in the window have no activity — so a shift that is not a multiple of
seven books appointments on a day the practice does not open. The remaining
missing weekdays are scattered closures and are preserved by the same rule.

WHAT IS NOT SHIFTED, and why:

  PATIENTS.DATE_OF_BIRTH   A birth date does not move when the clock moves.
                           Leaving it is what lets patients age by the shift,
                           which is what actually happens to a patient list.
  _INGESTED_AT             The lineage stamp for when the load really ran. It
                           describes our pipeline, not the practice's calendar.

Everything else moves together, including CREATED_AT/UPDATED_AT, so record
history stays consistent with the business events it describes.
"""
from __future__ import annotations

import argparse
import calendar
import csv
import datetime
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SEEDS = REPO / "transform" / "seeds"

#: Business dates that define the window. The freshest of these is what the
#: roll targets.
ANCHOR = [
    ("APPOINTMENTS", "SCHEDULED_START"),
    ("TRANSACTIONS", "TRANSACTION_DATE"),
]

#: Every column that moves with the clock, per RAW table.
SHIFT: dict[str, tuple[str, ...]] = {
    "APPOINTMENTS": ("SCHEDULED_START", "SCHEDULED_END", "ACTUAL_ARRIVAL",
                     "ACTUAL_DEPARTURE", "CREATED_AT", "UPDATED_AT"),
    "TRANSACTIONS": ("TRANSACTION_DATE", "CREATED_AT"),
    "INVENTORY_TRANSACTIONS": ("CONSUMED_DATE", "CREATED_AT"),
    "INVENTORY_LOTS": ("RECEIVED_DATE", "EXPIRY_DATE", "CREATED_AT"),
    "INVENTORY_CURRENT_STOCK": ("OLDEST_LOT_EXPIRY", "LAST_TRANSACTION_AT", "CREATED_AT"),
    "INVENTORY_UNITS": ("CREATED_AT", "UPDATED_AT"),
    "PATIENTS": ("CREATED_AT", "UPDATED_AT", "DELETED_AT"),
    "PROVIDERS": ("HIRE_DATE", "TERMINATION_DATE", "CREATED_AT", "UPDATED_AT"),
    "SERVICES": ("CREATED_AT", "UPDATED_AT"),
}

#: Columns deliberately left where they are — see the module docstring.
FROZEN = {("PATIENTS", "DATE_OF_BIRTH")}

#: Beyond this the recency tiers and the trailing windows have drifted far
#: enough to misreport. 120 days is the "active patient" definition, so the
#: limit sits comfortably under it.
MAX_STALENESS_DAYS = 60


def _connect():
    import snowflake.connector
    from cryptography.hazmat.primitives import serialization

    kp = os.path.expanduser(
        os.environ.get("SNOWFLAKE_PRIVATE_KEY_PATH", "~/.ssh/snowflake_mac_key.p8")
    )
    pw = os.environ.get("SNOWFLAKE_PRIVATE_KEY_PASSPHRASE") or None
    key = serialization.load_pem_private_key(
        open(kp, "rb").read(), password=pw.encode() if pw else None
    )
    pk = key.private_bytes(
        serialization.Encoding.DER,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return snowflake.connector.connect(
        account=os.environ["SNOWFLAKE_ACCOUNT"],
        user=os.environ["SNOWFLAKE_USER"],
        private_key=pk,
        role=os.environ["SNOWFLAKE_ROLE"],
        warehouse=os.environ["SNOWFLAKE_WAREHOUSE"],
        database=os.environ["SNOWFLAKE_DATABASE"],
    )


def _schema() -> str:
    return f"RAW_{os.environ.get('DEFAULT_TENANT_ID', 'del_mar').upper()}"


def _freshest(cur) -> datetime.date:
    best = None
    for table, col in ANCHOR:
        cur.execute(f"select max(cast({col} as date)) from {_schema()}.{table}")
        v = cur.fetchone()[0]
        if v and (best is None or v > best):
            best = v
    assert best, "no business dates found in RAW — nothing to roll"
    return best


def _add_months(d: datetime.date, months: int) -> datetime.date:
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    day = min(d.day, calendar.monthrange(year, month + 1)[1])
    return datetime.date(year, month + 1, day)


def _plan(freshest: datetime.date, today: datetime.date) -> dict:
    target = today - datetime.timedelta(days=1)
    slack = (target - freshest).days
    weeks = slack // 7 if slack > 0 else 0
    shift_days = weeks * 7
    # The seed is month grain and is only ever summed over a trailing-twelve-month
    # window, never joined month-to-month against daily data. So it moves by whole
    # months, chosen so its last month is the month the new window ends in — which
    # is what keeps twelve months of spend inside the CAC denominator.
    new_max = freshest + datetime.timedelta(days=shift_days)
    return {
        "freshest": freshest,
        "target": target,
        "staleness": (today - freshest).days,
        "shift_days": shift_days,
        "weeks": weeks,
        "new_max": new_max,
    }


def _seed_month_shift(new_max: datetime.date) -> int:
    rows = list(csv.DictReader((SEEDS / "marketing_spend.csv").open()))
    last = max(datetime.date.fromisoformat(r["month_start"]) for r in rows)
    return (new_max.year * 12 + new_max.month) - (last.year * 12 + last.month)


def _roll_seed(months: int, dry: bool) -> str:
    path = SEEDS / "marketing_spend.csv"
    rows = list(csv.DictReader(path.open()))
    header = list(rows[0].keys())
    before = max(r["month_start"] for r in rows)
    for r in rows:
        r["month_start"] = _add_months(
            datetime.date.fromisoformat(r["month_start"]), months
        ).isoformat()
    after = max(r["month_start"] for r in rows)
    if not dry:
        path.write_text(
            ",".join(header) + "\n"
            + "".join(",".join(r[h] for h in header) + "\n" for r in rows)
        )
    return f"  marketing_spend.csv      {before} -> {after}  (+{months} months, {len(rows)} rows)"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    today = datetime.date.today()
    conn = _connect()
    cur = conn.cursor()
    try:
        freshest = _freshest(cur)
        p = _plan(freshest, today)

        print(f"today            {today}")
        print(f"freshest record  {p['freshest']}  ({p['staleness']} days behind)")
        print(f"newest complete  {p['target']}")
        print(f"shift available  {p['shift_days']} days ({p['weeks']} weeks)")

        if args.check:
            if p["staleness"] > MAX_STALENESS_DAYS:
                print(
                    f"\nSTALE: {p['staleness']} days behind, past the "
                    f"{MAX_STALENESS_DAYS}-day limit.\n"
                    "Recency tiers and every trailing-twelve-month window are "
                    "measured against current_date, so they drift silently.\n"
                    "Fix: python scripts/roll_seed_window.py && make dbt-build",
                    file=sys.stderr,
                )
                return 1
            print("\nOK: the window is current.")
            return 0

        if p["shift_days"] == 0:
            print("\nNothing to do: already as current as a whole-week roll allows.")
            return 0

        assert p["shift_days"] % 7 == 0, "shift must be whole weeks; the clinic is closed Sundays"
        assert p["new_max"] <= p["target"], "roll would move activity into the future"

        n = p["shift_days"]
        print()
        for table in sorted(SHIFT):
            cols = [c for c in SHIFT[table] if (table, c) not in FROZEN]
            sets = ", ".join(f"{c} = dateadd('day', {n}, {c})" for c in cols)
            sql = f"update {_schema()}.{table} set {sets}"
            if args.dry_run:
                print(f"  {table:<26} {len(cols)} column(s)  [dry run]")
            else:
                cur.execute(sql)
                print(f"  {table:<26} {len(cols)} column(s)  {cur.rowcount} rows")

        print(_roll_seed(_seed_month_shift(p["new_max"]), args.dry_run))

        if args.dry_run:
            print("\n(dry run — nothing written)")
            return 0

        after = _freshest(cur)
        assert after <= p["target"], f"post-roll freshest {after} is in the future"
        assert after.isoweekday() == freshest.isoweekday(), "weekday grid broke"
        print(f"\nfreshest record now {after}  ({(today - after).days} days behind)")
        print("next: make dbt-build")
        return 0
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
