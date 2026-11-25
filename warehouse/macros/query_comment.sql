{# JSON query comment; with job-label: true, dbt-bigquery turns each key into a job label. #}
{% macro query_comment(node) -%}
    {%- set comment = {"app": "dbt", "dbt_target": target.name, "dbt_invocation": invocation_id} -%}
    {%- if node is not none -%}
        {%- do comment.update({"dbt_node": node.name, "dbt_resource": node.resource_type}) -%}
    {%- endif -%}
    {{ return(tojson(comment)) }}
{%- endmacro %}
