"""Jinja2 prompt templates for git diff analysis."""

from __future__ import annotations

from jinja2 import Environment, StrictUndefined

from ..models import DiffBundle

_ENV = Environment(undefined=StrictUndefined, trim_blocks=True, lstrip_blocks=True)


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT_TEMPLATE = _ENV.from_string(
    """\
You are an expert software engineer and database architect specialising in code review \
and Snowflake data warehousing.

Your task is to analyse a git diff and produce a structured JSON report describing:
1. A plain-English summary of what changed and why.
2. An impact assessment (technical + business).
3. Any database schema changes (DDL) implied by the code.
4. Any data manipulation changes (DML) required as a consequence.
5. Recommendations for the team.

## Output format

Respond with ONLY a valid JSON object — no markdown fences, no explanation outside the JSON.
The JSON must conform exactly to this schema:

```json
{
  "summary": "<string — 2-5 sentence description of changes>",
  "impact_assessment": "<string — technical and business impact>",
  "schema_changes": [
    {
      "table": "UPPER_SNAKE_CASE_TABLE",
      "change_type": "ADD_COLUMN | DROP_COLUMN | CREATE_TABLE | ALTER_COLUMN | DROP_TABLE | CREATE_INDEX | DROP_INDEX",
      "description": "<what and why>",
      "snowflake_sql": "<valid Snowflake DDL statement>",
      "is_breaking": true | false,
      "migration_notes": "<any caveats>"
    }
  ],
  "data_changes": [
    {
      "table": "UPPER_SNAKE_CASE_TABLE",
      "operation": "INSERT | UPDATE | DELETE | MERGE | TRUNCATE",
      "description": "<what and why>",
      "snowflake_sql": "<valid Snowflake DML statement>",
      "requires_ddl_first": true | false,
      "depends_on_table": "<table name or null>"
    }
  ],
  "recommendations": [
    {
      "category": "Performance | Data Quality | Security | Maintainability | Monitoring",
      "text": "<actionable recommendation>",
      "priority": "low | medium | high"
    }
  ],
  "affected_db_objects": [
    {
      "object_type": "TABLE | VIEW | STORED_PROCEDURE | INDEX | SEQUENCE",
      "object_name": "DATABASE.SCHEMA.OBJECT_NAME",
      "action": "CREATED | ALTERED | DROPPED | REFERENCED",
      "description": "<brief description of how this object is affected>"
    }
  ],
  "affected_code_objects": [
    {
      "object_type": "FILE | CLASS | FUNCTION | MODULE | API_ENDPOINT",
      "object_name": "<path::ClassName.method() or route path>",
      "action": "ADDED | MODIFIED | DELETED | RENAMED",
      "description": "<brief description of what changed in this object>"
    }
  ]
}
```

## Snowflake conventions to follow

- Table and column names: UPPER_CASE_SNAKE_CASE.
- Use Snowflake-compatible types: VARCHAR, NUMBER, BOOLEAN, TIMESTAMP_NTZ, DATE, VARIANT, ARRAY, OBJECT.
- Use VARIANT for JSON/semi-structured columns.
- Default database: {{ database }}, schema: {{ schema_name }}.
- Qualify objects as {{ database }}.{{ schema_name }}.TABLE_NAME.
- Always include NOT NULL constraints where appropriate.
- For CREATE TABLE: include a surrogate key column (e.g. ID NUMBER AUTOINCREMENT PRIMARY KEY).
- For ALTER TABLE ADD COLUMN: include data type and constraints.

## Detection heuristics

Look for these signals of schema changes:
- ORM model class definitions (SQLAlchemy, Django models, etc.)
- Pydantic/dataclass models that map to DB tables
- Migration files (Alembic, Django migrations, Flyway)
- Raw SQL in the diff that references new tables/columns
- DTOs, serializers referencing new fields
- Test fixtures creating new table structures

If no schema or data changes are detected, return empty arrays for those fields.
Do not fabricate schema changes that are not implied by the diff.

## Code object detection heuristics

Populate `affected_code_objects` by scanning the diff for:
- Changed file paths (each modified/added/deleted file is at minimum a FILE object)
- Class definitions added or modified (`class Foo`, `class Foo(Base)`, etc.)
- Function/method definitions changed (`def foo`, `async def foo`)
- Route or endpoint decorators (`@app.route`, `@router.get`, `@app.post`, `@api_view`, etc.)
- Module-level changes that affect exported interfaces

For `affected_db_objects`, look for explicit object names referenced alongside schema changes
(table names, view names, stored procedure calls, index definitions).
"""
)

# ── User prompt ───────────────────────────────────────────────────────────────

USER_PROMPT_TEMPLATE = _ENV.from_string(
    """\
## Commit Metadata

- **Repository**: {{ bundle.repo_path }}
- **Commit**: {{ bundle.commit_hash }}
- **Author**: {{ bundle.author }}
- **Date**: {{ bundle.timestamp.strftime('%Y-%m-%d %H:%M:%S UTC') }}
- **Message**: {{ bundle.commit_message }}
- **Files changed**: {{ bundle.files | length }}
- **Total additions**: {{ bundle.total_additions }}
- **Total deletions**: {{ bundle.total_deletions }}

## File Changes

{% for file in bundle.files %}
### {{ loop.index }}. {{ file.change_type.value | upper }}: `{{ file.path }}`
{% if file.old_path %}*(renamed from `{{ file.old_path }}`)*{% endif %}

```diff
{{ file.diff_text }}
```

{% endfor %}

Analyse the above diff and return the JSON report as instructed.
"""
)


def render_system_prompt(database: str, schema_name: str) -> str:
    return SYSTEM_PROMPT_TEMPLATE.render(database=database, schema_name=schema_name)


def render_user_prompt(bundle: DiffBundle) -> str:
    return USER_PROMPT_TEMPLATE.render(bundle=bundle)
