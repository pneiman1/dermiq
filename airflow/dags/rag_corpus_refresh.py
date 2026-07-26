"""Daily RAG corpus refresh: rebuild + re-embed the knowledge base.

Runs 7am (after the 6am daily pipeline) so the corpus snapshots track the latest
marts. platform-core + dermiq are bind-mounted (docker-compose.override.yml) and
added to sys.path; embedding runs locally via sentence-transformers. See
docs/DECISIONS.md ADR-008.
"""
from __future__ import annotations

import sys
from datetime import datetime, timedelta

for _p in ("/usr/local/airflow/vendor/platform-core", "/usr/local/airflow/vendor/dermiq"):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.sensors.python import PythonSensor

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


def _build_corpus() -> None:
    from scripts.build_rag_corpus import main

    main()


with DAG(
    dag_id="rag_corpus_refresh",
    description="Daily rebuild + re-embed of the RAG knowledge corpus.",
    schedule="0 7 * * *",
    start_date=datetime(2026, 1, 1),
    catchup=False,
    default_args=DEFAULT_ARGS,
    tags=["dermiq", "del_mar", "rag"],
) as dag:
    wait_for_snowflake = PythonSensor(
        task_id="wait_for_snowflake",
        python_callable=_wait_for_snowflake,
        timeout=300,
        poke_interval=30,
        mode="reschedule",
    )

    build_corpus = PythonOperator(task_id="build_corpus", python_callable=_build_corpus)

    def _notify() -> None:
        print("RAG corpus refresh complete — documents rebuilt and re-embedded.")

    notify_complete = PythonOperator(task_id="notify_complete", python_callable=_notify)

    wait_for_snowflake >> build_corpus >> notify_complete
