FROM quay.io/astronomer/astro-runtime:12.7.1

# dbt runs in an isolated venv (Astronomer Cosmos best practice — keeps dbt's
# dependency tree from clashing with Airflow's). Cosmos is pointed at this dbt
# via ExecutionConfig(dbt_executable_path=...). Pinned to match the repo's dbt.
RUN python -m venv /usr/local/airflow/dbt_venv && \
    /usr/local/airflow/dbt_venv/bin/pip install --no-cache-dir "dbt-snowflake==1.11.*"

# platform-core and dermiq are bind-mounted at runtime (docker-compose.override.yml)
# and added to sys.path in the DAG — the astro build context is airflow/ and can't
# reach the sibling repos, so an in-image `pip install -e` isn't possible. Their
# runtime deps come from requirements.txt. See docs/DECISIONS.md ADR-009.
