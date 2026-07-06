"""Weekly patient re-clustering: refit k-means, rebuild the segment marts.

Runs Monday 3am (ahead of the 6am daily pipeline). platform-core + dermiq are
bind-mounted (docker-compose.override.yml) and added to sys.path. dbt runs from
the isolated venv via Cosmos. See docs/DECISIONS.md ADR-007.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta
from pathlib import Path

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


def _wait_for_snowflake() -> bool:
    from platform_core.config import get_settings
    from platform_core.warehouse.connection import get_snowflake_connection

    try:
        settings = get_settings()
        with get_snowflake_connection(database=settings.snowflake_database) as conn:
            conn.cursor().execute("select 1")
        return True
    except Exception:
        return False


def _run_clustering() -> None:
    from scripts.run_clustering import main

    main()


with DAG(
    dag_id="weekly_clustering",
    description="Weekly k-means re-clustering + segment mart rebuild.",
    schedule="0 3 * * MON",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["dermiq", "del_mar", "ml"],
) as dag:
    wait_for_snowflake = PythonSensor(
        task_id="wait_for_snowflake",
        python_callable=_wait_for_snowflake,
        timeout=300,
        poke_interval=30,
        mode="reschedule",
    )

    run_clustering = PythonOperator(task_id="run_clustering", python_callable=_run_clustering)

    # Re-clustering rewrites the assignments source, so rebuild both segment marts.
    # (The spec's "mart_patient_segments+" has no downstream models — the members
    # mart is a sibling — so we select both explicitly.)
    dbt_rebuild_segments = DbtTaskGroup(
        group_id="dbt_rebuild_segments",
        project_config=ProjectConfig(DBT_PROJECT_PATH),
        profile_config=ProfileConfig(
            profile_name="dermiq",
            target_name="dev",
            profiles_yml_filepath=Path(DBT_PROJECT_PATH) / "profiles.yml",
        ),
        execution_config=ExecutionConfig(dbt_executable_path=DBT_EXECUTABLE),
        render_config=RenderConfig(
            dbt_executable_path=DBT_EXECUTABLE,
            select=["mart_patient_segments", "mart_patient_segment_members"],
        ),
        default_args=DEFAULT_ARGS,
    )

    def _notify() -> None:
        print("Weekly clustering complete — segments refit and marts rebuilt.")

    notify_complete = PythonOperator(task_id="notify_complete", python_callable=_notify)

    wait_for_snowflake >> run_clustering >> dbt_rebuild_segments >> notify_complete
