from __future__ import annotations

import os
import time
from typing import Mapping

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem


def _workspace_client() -> WorkspaceClient:
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
    if profile and not os.environ.get("DATABRICKS_AUTH_STORAGE"):
        os.environ["DATABRICKS_AUTH_STORAGE"] = "plaintext"
    if profile:
        return WorkspaceClient(profile=profile)
    return WorkspaceClient()


def _status_state(response: object) -> str:
    status = getattr(response, "status", None)
    state = getattr(status, "state", "")
    return str(getattr(state, "value", state) or "").upper()


def _response_error(response: object) -> str:
    status = getattr(response, "status", None)
    error = getattr(status, "error", None)
    return str(error or "")


def _result_rows(result: object) -> list[list[object]]:
    return list(getattr(result, "data_array", None) or [])


def _extract_response_rows(response: object, client: WorkspaceClient | None = None) -> pd.DataFrame:
    result = getattr(response, "result", None)
    manifest = getattr(response, "manifest", None)
    if result is None or manifest is None:
        return pd.DataFrame()

    schema = getattr(manifest, "schema", None)
    columns = []
    if schema is not None and getattr(schema, "columns", None):
        columns = [column.name or f"col_{index}" for index, column in enumerate(schema.columns)]
    rows = _result_rows(result)
    statement_id = getattr(response, "statement_id", "")
    total_chunks = int(getattr(manifest, "total_chunk_count", 1) or 1)
    if client is not None and statement_id and total_chunks > 1:
        for chunk_index in range(1, total_chunks):
            chunk = client.statement_execution.get_statement_result_chunk_n(statement_id, chunk_index)
            rows.extend(_result_rows(chunk))
    if not columns and rows:
        columns = [f"col_{index}" for index in range(len(rows[0]))]
    if not rows:
        return pd.DataFrame(columns=columns)
    return pd.DataFrame(rows, columns=columns)


def _statement_parameters(parameters: Mapping[str, object] | None) -> list[StatementParameterListItem] | None:
    if not parameters:
        return None
    return [
        StatementParameterListItem(name=name, type="STRING", value=str(value))
        for name, value in parameters.items()
    ]


def run_sql(
    statement: str,
    timeout_seconds: int = 60,
    parameters: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    if not warehouse_id:
        return pd.DataFrame()

    try:
        client = _workspace_client()
        response = client.statement_execution.execute_statement(
            statement=statement,
            warehouse_id=warehouse_id,
            disposition=Disposition.INLINE,
            format=Format.JSON_ARRAY,
            parameters=_statement_parameters(parameters),
            wait_timeout=f"{min(timeout_seconds, 20)}s",
        )
        deadline = time.monotonic() + max(timeout_seconds, 1)
        while _status_state(response) in {"PENDING", "RUNNING"} and time.monotonic() < deadline:
            time.sleep(1)
            response = client.statement_execution.get_statement(getattr(response, "statement_id", ""))
        if _status_state(response) != "SUCCEEDED":
            df = pd.DataFrame()
            error = _response_error(response)
            if error:
                df.attrs["error"] = error
            return df
    except Exception as exc:
        df = pd.DataFrame()
        df.attrs["error"] = str(exc)
        return df
    return _extract_response_rows(response, client)
