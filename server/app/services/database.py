from __future__ import annotations

from contextlib import contextmanager
from typing import Any

from app.config import get_settings


READ_ONLY_CONTEXT_QUERIES: dict[str, str] = {
    "site_health": """
        SELECT * FROM omni9.site_health_summary
        WHERE site_id = %(site_id)s
        LIMIT %(limit)s
    """,
    "machine_cards": """
        SELECT * FROM omni9.app_machine_cards
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR id = %(machine_id)s::text)
        ORDER BY state, name
        LIMIT %(limit)s
    """,
    "open_alerts": """
        SELECT id, site_id, machine_id, severity, title, body, target_type, target_id, created_at
        FROM omni9.alerts
        WHERE site_id = %(site_id)s
          AND cleared_at IS NULL
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """,
    "recent_actions": """
        SELECT id, site_id, machine_id, type, source, reason, payload, created_at
        FROM omni9.actions
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """,
    "work_orders": """
        SELECT id, site_id, machine_id, title, status, priority, due_at, created_at, updated_at
        FROM omni9.work_orders
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY updated_at DESC
        LIMIT %(limit)s
    """,
    "impact": """
        SELECT id, site_id, machine_id, metric, value, unit, reason, created_at
        FROM omni9.impact_records
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """,
    "mesh_nodes": """
        SELECT id, site_id, gateway_id, machine_id, friendly_name, coverage_state, peer_count, last_seen_at
        FROM omni9.mesh_nodes
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY last_seen_at DESC NULLS LAST
        LIMIT %(limit)s
    """,
    "media_assets": """
        SELECT id, site_id, machine_id, storage_driver, storage_bucket, storage_key, content_type, size_bytes, kind, created_at
        FROM omni9.media_assets
        WHERE site_id = %(site_id)s
          AND (%(machine_id)s::text IS NULL OR machine_id = %(machine_id)s::text)
        ORDER BY created_at DESC
        LIMIT %(limit)s
    """,
    "automation_rules": """
        SELECT id, site_id, name, enabled, trigger_type, action_type, config, created_at, updated_at
        FROM omni9.automation_rules
        WHERE site_id = %(site_id)s
        ORDER BY updated_at DESC
        LIMIT %(limit)s
    """,
}


def normalized_database_url() -> str:
    value = get_settings().database_url.strip()
    if value.startswith("postgres://"):
        return "postgresql://" + value[len("postgres://") :]
    return value


@contextmanager
def connection():
    database_url = normalized_database_url()
    if not database_url:
        yield None
        return

    import psycopg
    from psycopg.rows import dict_row

    with psycopg.connect(database_url, row_factory=dict_row, connect_timeout=10) as conn:
        conn.execute("SET statement_timeout = '3000ms'")
        conn.execute("SET TRANSACTION READ ONLY")
        yield conn


def fetch_sql_context(site_id: str, machine_id: str | None = None, limit: int | None = None) -> dict[str, Any]:
    settings = get_settings()
    if not settings.ai_enable_sql_context:
        return {"enabled": False, "source": "postgresql", "tables": {}}
    if not normalized_database_url():
        return {"enabled": False, "source": "postgresql", "reason": "DATABASE_URL is not configured", "tables": {}}

    row_limit = limit or settings.ai_context_row_limit
    result: dict[str, Any] = {"enabled": True, "source": "postgresql", "tables": {}}
    params = {"site_id": site_id, "machine_id": machine_id, "limit": row_limit}
    try:
        with connection() as conn:
            if conn is None:
                return {"enabled": False, "source": "postgresql", "tables": {}}
            for name, sql in READ_ONLY_CONTEXT_QUERIES.items():
                rows = conn.execute(sql, params).fetchall()
                result["tables"][name] = [dict(row) for row in rows]
    except Exception as exc:
        return {"enabled": False, "source": "postgresql", "error": str(exc), "tables": {}}
    return result


def run_health_query() -> dict[str, Any]:
    if not normalized_database_url():
        return {"ok": False, "reason": "DATABASE_URL is not configured"}
    try:
        with connection() as conn:
            if conn is None:
                return {"ok": False, "reason": "DATABASE_URL is not configured"}
            rows = conn.execute("SELECT current_database() AS database, current_schema() AS schema, now() AS checked_at").fetchall()
            return {"ok": True, "database": rows[0] if rows else None}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}

