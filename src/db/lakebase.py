from __future__ import annotations

from contextlib import contextmanager
from functools import lru_cache
import os
import re
from typing import Iterator

import pandas as pd

try:
    import psycopg2
    from psycopg2 import sql as pg_sql
except ImportError:  # pragma: no cover
    psycopg2 = None
    pg_sql = None

try:
    from databricks.sdk import WorkspaceClient
except ImportError:  # pragma: no cover
    WorkspaceClient = None


_SCHEMA_FALLBACK = "care_convoy"
_IDENTIFIER_PATTERN = re.compile(r"[^a-z0-9_]+")
_USER_DECISION_COLUMNS = [
    "created_at",
    "mission_type",
    "district",
    "facility_id",
    "decision",
    "note",
    "metadata_json",
]
_AGENT_FEEDBACK_COLUMNS = [
    "created_at",
    "updated_at",
    "run_id",
    "mission_type",
    "district",
    "facility_id",
    "recommended_action",
    "confidence_label",
    "provenance",
    "feedback_json",
]


def _schema_name() -> str:
    raw_name = os.environ.get("LAKEBASE_SCHEMA", _SCHEMA_FALLBACK).strip().lower()
    sanitized = _IDENTIFIER_PATTERN.sub("_", raw_name).strip("_")
    if not sanitized:
        return _SCHEMA_FALLBACK
    if sanitized[0].isdigit():
        sanitized = f"app_{sanitized}"
    return sanitized


def _schema_identifier() -> object:
    return pg_sql.Identifier(_schema_name())


def _table_identifier() -> object:
    return pg_sql.Identifier(_schema_name(), "user_decisions")


def _agent_feedback_table_identifier() -> object:
    return pg_sql.Identifier(_schema_name(), "agent_feedback")


def _index_identifier() -> object:
    return pg_sql.Identifier(f"{_schema_name()}_user_decisions_run_facility_idx")


def _agent_feedback_index_identifier() -> object:
    return pg_sql.Identifier(f"{_schema_name()}_agent_feedback_run_idx")


def _workspace_client() -> object | None:
    if WorkspaceClient is None:
        return None

    try:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
        if profile and not os.environ.get("DATABRICKS_AUTH_STORAGE"):
            os.environ["DATABRICKS_AUTH_STORAGE"] = "plaintext"
        if profile:
            return WorkspaceClient(profile=profile)
        return WorkspaceClient()
    except Exception:
        return None


@lru_cache(maxsize=1)
def _resolve_local_connection_settings() -> dict[str, str] | None:
    endpoint_name = os.environ.get("LAKEBASE_ENDPOINT")
    if not endpoint_name:
        return None

    client = _workspace_client()
    if client is None:
        return None

    try:
        endpoint = client.postgres.get_endpoint(name=endpoint_name)
        current_user = client.current_user.me().user_name
    except Exception:
        return None
    return {
        "host": endpoint.status.hosts.host,
        "port": os.environ.get("PGPORT", "5432"),
        "database": os.environ.get("PGDATABASE", "databricks_postgres"),
        "user": os.environ.get("PGUSER", current_user),
        "sslmode": os.environ.get("PGSSLMODE", "require"),
        "endpoint_name": endpoint.name,
    }


def _connection_settings() -> dict[str, str] | None:
    if os.environ.get("PGHOST") and os.environ.get("PGUSER") and os.environ.get("PGPASSWORD"):
        return {
            "host": os.environ["PGHOST"],
            "port": os.environ.get("PGPORT", "5432"),
            "database": os.environ.get("PGDATABASE", "databricks_postgres"),
            "user": os.environ["PGUSER"],
            "sslmode": os.environ.get("PGSSLMODE", "require"),
            "password": os.environ["PGPASSWORD"],
        }
    if os.environ.get("PGHOST") and os.environ.get("PGUSER") and os.environ.get("LAKEBASE_ENDPOINT"):
        return {
            "host": os.environ["PGHOST"],
            "port": os.environ.get("PGPORT", "5432"),
            "database": os.environ.get("PGDATABASE", "databricks_postgres"),
            "user": os.environ["PGUSER"],
            "sslmode": os.environ.get("PGSSLMODE", "require"),
            "endpoint_name": os.environ["LAKEBASE_ENDPOINT"],
        }
    try:
        return _resolve_local_connection_settings()
    except Exception:
        return None


def lakebase_available() -> bool:
    return bool(psycopg2 is not None and _connection_settings() is not None)


@contextmanager
def get_connection() -> Iterator[object | None]:
    settings = _connection_settings()
    if psycopg2 is None or settings is None:
        yield None
        return

    password = settings.get("password")
    if password is None:
        client = _workspace_client()
        if client is None or "endpoint_name" not in settings:
            yield None
            return
        password = client.postgres.generate_database_credential(endpoint=settings["endpoint_name"]).token
    connection = psycopg2.connect(
        host=settings["host"],
        port=int(settings["port"]),
        dbname=settings["database"],
        user=settings["user"],
        password=password,
        sslmode=settings["sslmode"],
        connect_timeout=10,
    )
    try:
        yield connection
        connection.commit()
    finally:
        connection.close()


def ensure_tables() -> None:
    try:
        with get_connection() as connection:
            if connection is None or pg_sql is None:
                return
            with connection.cursor() as cursor:
                cursor.execute(
                    pg_sql.SQL("create schema if not exists {}").format(_schema_identifier())
                )
                cursor.execute(
                    pg_sql.SQL(
                        """
                        create table if not exists {} (
                          id bigserial primary key,
                          run_id text not null,
                          mission_type text not null,
                          district text not null,
                          facility_id text not null,
                          decision text not null,
                          note text not null,
                          metadata_json text not null,
                          created_at timestamptz not null default now()
                        )
                        """
                    ).format(_table_identifier())
                )
                cursor.execute(
                    pg_sql.SQL(
                        "create unique index if not exists {} on {} (run_id, facility_id)"
                    ).format(_index_identifier(), _table_identifier())
                )
                cursor.execute(
                    pg_sql.SQL(
                        """
                        create table if not exists {} (
                          id bigserial primary key,
                          run_id text not null,
                          mission_type text not null,
                          district text not null,
                          facility_id text not null,
                          recommended_action text not null,
                          confidence_label text not null,
                          provenance text not null,
                          feedback_json text not null,
                          created_at timestamptz not null default now(),
                          updated_at timestamptz not null default now()
                        )
                        """
                    ).format(_agent_feedback_table_identifier())
                )
                cursor.execute(
                    pg_sql.SQL(
                        "create unique index if not exists {} on {} (run_id)"
                    ).format(_agent_feedback_index_identifier(), _agent_feedback_table_identifier())
                )
    except Exception:
        return


def save_user_decision_record(
    run_id: str,
    mission_type: str,
    district: str,
    facility_id: str,
    decision: str,
    note: str,
    metadata_json: str,
) -> bool:
    try:
        ensure_tables()
        with get_connection() as connection:
            if connection is None or pg_sql is None:
                return False
            with connection.cursor() as cursor:
                cursor.execute(
                    pg_sql.SQL(
                        """
                        insert into {} (
                          run_id,
                          mission_type,
                          district,
                          facility_id,
                          decision,
                          note,
                          metadata_json
                        ) values (%s, %s, %s, %s, %s, %s, %s)
                        on conflict (run_id, facility_id) do update
                        set mission_type = excluded.mission_type,
                            district = excluded.district,
                            decision = excluded.decision,
                            note = excluded.note,
                            metadata_json = excluded.metadata_json
                        """
                    ).format(_table_identifier()),
                    (run_id, mission_type, district, facility_id, decision, note, metadata_json),
                )
        return True
    except Exception:
        return False


def save_agent_feedback_record(
    run_id: str,
    mission_type: str,
    district: str,
    facility_id: str,
    recommended_action: str,
    confidence_label: str,
    provenance: str,
    feedback_json: str,
) -> bool:
    try:
        ensure_tables()
        with get_connection() as connection:
            if connection is None or pg_sql is None:
                return False
            with connection.cursor() as cursor:
                cursor.execute(
                    pg_sql.SQL(
                        """
                        insert into {} (
                          run_id,
                          mission_type,
                          district,
                          facility_id,
                          recommended_action,
                          confidence_label,
                          provenance,
                          feedback_json
                        ) values (%s, %s, %s, %s, %s, %s, %s, %s)
                        on conflict (run_id) do update
                        set mission_type = excluded.mission_type,
                            district = excluded.district,
                            facility_id = excluded.facility_id,
                            recommended_action = excluded.recommended_action,
                            confidence_label = excluded.confidence_label,
                            provenance = excluded.provenance,
                            feedback_json = excluded.feedback_json,
                            updated_at = now()
                        """
                    ).format(_agent_feedback_table_identifier()),
                    (
                        run_id,
                        mission_type,
                        district,
                        facility_id,
                        recommended_action,
                        confidence_label,
                        provenance,
                        feedback_json,
                    ),
                )
        return True
    except Exception:
        return False


def _empty_user_decisions(error: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(columns=_USER_DECISION_COLUMNS)
    if error:
        df.attrs["error"] = error
    return df


def _empty_agent_feedback(error: str | None = None) -> pd.DataFrame:
    df = pd.DataFrame(columns=_AGENT_FEEDBACK_COLUMNS)
    if error:
        df.attrs["error"] = error
    return df


def list_user_decisions(limit: int = 10) -> pd.DataFrame:
    try:
        ensure_tables()
        with get_connection() as connection:
            if connection is None or pg_sql is None:
                return _empty_user_decisions("Lakebase shortlist is not configured for this runtime.")
            with connection.cursor() as cursor:
                cursor.execute(
                    pg_sql.SQL(
                        """
                        select created_at, mission_type, district, facility_id, decision, note, metadata_json
                        from {}
                        order by created_at desc
                        limit %s
                        """
                    ).format(_table_identifier()),
                    (limit,),
                )
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
            return pd.DataFrame(rows, columns=columns)
    except Exception:
        return _empty_user_decisions(
            "Lakebase shortlist is temporarily unavailable because the current database role cannot manage the decisions table."
        )


def list_agent_feedback(limit: int = 10) -> pd.DataFrame:
    try:
        ensure_tables()
        with get_connection() as connection:
            if connection is None or pg_sql is None:
                return _empty_agent_feedback("Lakebase agent feedback is not configured for this runtime.")
            with connection.cursor() as cursor:
                cursor.execute(
                    pg_sql.SQL(
                        """
                        select
                          created_at,
                          updated_at,
                          run_id,
                          mission_type,
                          district,
                          facility_id,
                          recommended_action,
                          confidence_label,
                          provenance,
                          feedback_json
                        from {}
                        order by updated_at desc
                        limit %s
                        """
                    ).format(_agent_feedback_table_identifier()),
                    (limit,),
                )
                rows = cursor.fetchall()
                columns = [column.name for column in cursor.description]
            return pd.DataFrame(rows, columns=columns)
    except Exception:
        return _empty_agent_feedback(
            "Lakebase agent feedback is temporarily unavailable because the current database role cannot manage the feedback table."
        )


def lakebase_status() -> dict[str, str]:
    settings = _connection_settings()
    if settings is None:
        return {
            "mode": "unconfigured",
            "detail": "Attach the Lakebase resource or inject PostgreSQL credentials to enable persistent shortlist storage.",
        }
    return {
        "mode": "configured",
        "detail": settings.get("endpoint_name", settings["database"]),
    }
