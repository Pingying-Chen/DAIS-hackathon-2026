from __future__ import annotations

import os
from typing import Mapping

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format, StatementParameterListItem


def _workspace_client() -> WorkspaceClient:
    profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
    if profile:
        return WorkspaceClient(profile=profile)
    return WorkspaceClient()


def _extract_response_rows(response: object) -> pd.DataFrame:
    result = getattr(response, "result", None)
    manifest = getattr(response, "manifest", None)
    if result is None or manifest is None:
        return pd.DataFrame()

    schema = getattr(manifest, "schema", None)
    columns = []
    if schema is not None and getattr(schema, "columns", None):
        columns = [column.name or f"col_{index}" for index, column in enumerate(schema.columns)]
    rows = getattr(result, "data_array", None) or []
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
    timeout_seconds: int = 20,
    parameters: Mapping[str, object] | None = None,
) -> pd.DataFrame:
    warehouse_id = os.environ.get("DATABRICKS_WAREHOUSE_ID", "")
    if not warehouse_id:
        return pd.DataFrame()

    try:
        response = _workspace_client().statement_execution.execute_statement(
            statement=statement,
            warehouse_id=warehouse_id,
            disposition=Disposition.INLINE,
            format=Format.JSON_ARRAY,
            parameters=_statement_parameters(parameters),
            wait_timeout=f"{min(timeout_seconds, 20)}s",
        )
    except Exception:
        return pd.DataFrame()
    return _extract_response_rows(response)
