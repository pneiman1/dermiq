"""Daily Del Mar pipeline: Postgres source → Snowflake RAW → dbt (stg/int/mart).

Runs at 6am. platform-core and dermiq are bind-mounted (see
docker-compose.override.yml) and added to sys.path below; dbt runs from an
isolated venv via Cosmos. See docs/DECISIONS.md ADR-009.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

# Bind-mounted sibling repos (docker-compose.override.yml) — importable at both
# DAG-parse and task-execution time.
for _p in ("/usr/local/airflow/vendor/platform-core", "/usr/local/airflow/vendor/dermiq"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor
from cosmos import DbtTaskGroup, ExecutionConfig, ProfileConfig, ProjectConfig, RenderConfig

DBT_PROJECT_PATH = "/usr/local/airflow/vendor/dermiq/transform"
DBT_EXECUTABLE = "/usr/local/airflow/dbt_venv/bin/dbt"

DEFAULT_ARGS = {"retries": 2, "retry_delay": timedelta(minutes=2)}


def _wait_for_postgres() -> bool:
    import os

    import psycopg2

    url = os.environ.get("POSTGRES_SOURCE_READER_URL") or os.environ["POSTGRES_SOURCE_URL"]
    try:
        psycopg2.connect(url).close()
        return True
    except Exception:
        return False


def _extract(**context) -> dict:
    from platform_core.config import get_settings
    from platform_core.warehouse.connection import get_snowflake_connection

    from dermiq.ingestion.source_to_raw import ingest_source_to_raw

    settings = get_settings()
    with get_snowflake_connection(database=settings.snowflake_database) as conn:
        counts = ingest_source_to_raw(conn, tenant_id=settings.default_tenant_id)
    context["ti"].xcom_push(key="row_counts", value=counts)
    return counts


def _notify(**context) -> None:
    counts = context["ti"].xcom_pull(task_ids="extract_postgres_to_snowflake", key="row_counts")
    total = sum(counts.values()) if counts else 0
    print(f"Del Mar pipeline complete. Rows ingested: {counts} (total {total:,}).")


with DAG(
    dag_id="del_mar_pipeline",
    description="Postgres source → Snowflake RAW → dbt stg/int/mart, daily at 6am.",
    schedule="0 6 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["dermiq", "del_mar"],
) as dag:
    wait_for_postgres = PythonSensor(
        task_id="wait_for_postgres",
        python_callable=_wait_for_postgres,
        timeout=300,
        poke_interval=15,
        mode="reschedule",
    )

    extract = PythonOperator(
        task_id="extract_postgres_to_snowflake",
        python_callable=_extract,
    )

    dbt_build = DbtTaskGroup(
        group_id="dbt_build",
        project_config=ProjectConfig(DBT_PROJECT_PATH),
        profile_config=ProfileConfig(
            profile_name="dermiq",
            target_name="dev",
            profiles_yml_filepath=Path(DBT_PROJECT_PATH) / "profiles.yml",
        ),
        execution_config=ExecutionConfig(dbt_executable_path=DBT_EXECUTABLE),
        render_config=RenderConfig(dbt_executable_path=DBT_EXECUTABLE),
        default_args=DEFAULT_ARGS,
    )

    notify = PythonOperator(task_id="notify_complete", python_callable=_notify)

    wait_for_postgres >> extract >> dbt_build >> notify
