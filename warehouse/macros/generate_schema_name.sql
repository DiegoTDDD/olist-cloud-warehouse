{#
  prod: models land in the dataset named by their folder (staging, marts).
  ci:   every pull request builds into its own throwaway datasets, ci_pr_<n>_staging and
        ci_pr_<n>_marts, which the pr-builder account creates and the workflow deletes.
#}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {%- if target.name == 'ci' -%}
        {{ target.schema }}_{{ custom_schema_name | trim }}
    {%- elif custom_schema_name is none -%}
        {{ target.schema }}
    {%- else -%}
        {{ custom_schema_name | trim }}
    {%- endif -%}
{%- endmacro %}
