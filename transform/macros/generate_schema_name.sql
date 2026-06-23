{#
    Override dbt's default schema naming to match the platform-core convention:
    schemas are named <LAYER>_<TENANT> (e.g. STG_DEL_MAR), NOT the dbt default of
    <target_schema>_<custom_schema>. The layer comes from each model's +schema
    config (stg/int/mart); the tenant comes from the `tenant` var.

    This is the dbt-side mirror of platform_core.warehouse.schemas.schema_name, so
    ingestion and transformation agree on where each tenant's data lives.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- set tenant = (var('tenant', '') | trim) -%}
    {%- if custom_schema_name is none -%}
        {{ target.schema }}
    {%- elif tenant == '' -%}
        {{ custom_schema_name | trim | upper }}
    {%- else -%}
        {{ (custom_schema_name ~ '_' ~ tenant) | trim | upper }}
    {%- endif -%}
{%- endmacro %}
