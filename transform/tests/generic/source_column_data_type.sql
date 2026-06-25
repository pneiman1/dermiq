{#
    Generic test: assert a source column's actual Snowflake data type matches an
    expected type, by querying INFORMATION_SCHEMA.COLUMNS. This is the production
    build's guardrail against the ADR-005 failure mode — if ingestion ever lands a
    column with the wrong type (e.g. an all-NULL date inferred as NUMBER), the
    build fails here.

    Expected types are normalized to Snowflake's INFORMATION_SCHEMA families
    (VARCHAR/STRING/CHAR -> TEXT, INT/INTEGER/NUMERIC/DECIMAL -> NUMBER) so callers
    can write the natural type name. Returns a row (failure) on mismatch.
#}
{% test source_column_data_type(model, column_name, expected_type) %}

{%- set aliases = {
    "VARCHAR": "TEXT", "STRING": "TEXT", "CHAR": "TEXT", "TEXT": "TEXT",
    "INT": "NUMBER", "INTEGER": "NUMBER", "BIGINT": "NUMBER",
    "NUMBER": "NUMBER", "NUMERIC": "NUMBER", "DECIMAL": "NUMBER"
} -%}
{%- set expected_norm = aliases.get(expected_type | upper, expected_type | upper) -%}

select
    '{{ column_name }}'   as column_name,
    data_type             as actual_type,
    '{{ expected_norm }}' as expected_type
from {{ model.database }}.information_schema.columns
where table_schema = '{{ model.schema }}'
  and table_name = upper('{{ model.identifier }}')
  and column_name = upper('{{ column_name }}')
  and upper(data_type) != '{{ expected_norm }}'

{% endtest %}
