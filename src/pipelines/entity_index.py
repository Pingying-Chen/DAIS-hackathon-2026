from __future__ import annotations

import argparse
from base64 import b64encode
import os
from typing import Any

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.sql import Disposition, Format

from src.agent.tools import (
    CATALOG,
    ENTITY_INDEX_COLUMNS,
    ENTITY_INDEX_VERSION,
    FACILITY_NUMERIC_COLUMNS,
    FACILITY_TEXT_COLUMNS,
    SCHEMA,
    build_entity_index_frame,
    entity_index_table_name,
)
from src.db.warehouse import run_sql

DEFAULT_ENTITY_INDEX_TABLE = "workspace.default.care_convoy_facility_entity_index"


def _workspace_client(profile: str) -> WorkspaceClient:
    return WorkspaceClient(profile=profile) if profile else WorkspaceClient()


def _source_columns_sql() -> str:
    text_columns = []
    for column in FACILITY_TEXT_COLUMNS:
        if column == "source_urls":
            expression = """
            case
              when trim(cast(source_urls as string)) like '[%'
                then coalesce(get_json_object(cast(source_urls as string), '$[0]'), cast(source_urls as string))
              else cast(source_urls as string)
            end as source_urls
            """
        elif column == "description":
            expression = "left(cast(description as string), 2000) as description"
        else:
            expression = f"cast({column} as string) as {column}"
        text_columns.append(expression)

    numeric_columns = [f"{column}" for column in FACILITY_NUMERIC_COLUMNS]
    return ", ".join(text_columns + numeric_columns)


def _source_sql(limit: int) -> str:
    limit_clause = f"limit {limit}" if limit > 0 else ""
    return f"""
    select
      {_source_columns_sql()}
    from {CATALOG}.{SCHEMA}.facilities
    where coalesce(lower(address_country), '') like '%india%'
    order by coalesce(name, '') asc, coalesce(unique_id, '') asc
    {limit_clause}
    """


def _source_page_sql(start_row: int, end_row: int) -> str:
    return f"""
    select * except (row_number)
    from (
      select
        {_source_columns_sql()},
        row_number() over (order by coalesce(name, '') asc, coalesce(unique_id, '') asc) as row_number
      from {CATALOG}.{SCHEMA}.facilities
      where coalesce(lower(address_country), '') like '%india%'
    )
    where row_number between {start_row} and {end_row}
    order by row_number
    """


def _load_source_rows(limit: int, page_size: int) -> pd.DataFrame:
    if limit > 0:
        return run_sql(_source_sql(limit), timeout_seconds=20)

    pages: list[pd.DataFrame] = []
    start_row = 1
    while True:
        end_row = start_row + page_size - 1
        page = run_sql(_source_page_sql(start_row, end_row), timeout_seconds=20)
        if page.empty:
            break
        pages.append(page)
        print(f"Loaded source rows {start_row}-{start_row + len(page) - 1}.")
        if len(page) < page_size:
            break
        start_row = end_row + 1

    if not pages:
        return pd.DataFrame()
    return pd.concat(pages, ignore_index=True)


def _execute_sql(client: WorkspaceClient, warehouse_id: str, statement: str, timeout_seconds: int = 50) -> None:
    response = client.statement_execution.execute_statement(
        statement=statement,
        warehouse_id=warehouse_id,
        disposition=Disposition.INLINE,
        format=Format.JSON_ARRAY,
        wait_timeout=f"{min(timeout_seconds, 50)}s",
    )
    status = getattr(response, "status", None)
    state = str(getattr(status, "state", "")).lower()
    if "failed" in state or "canceled" in state:
        message = getattr(getattr(status, "error", None), "message", "SQL statement failed")
        raise RuntimeError(message)
    if "succeeded" not in state:
        raise RuntimeError(f"SQL statement did not finish before timeout: {state}")


def _sql_literal(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, float) and pd.isna(value):
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    encoded = b64encode(str(value).encode("utf-8")).decode("ascii")
    return f"cast(unbase64('{encoded}') as string)"


def _create_table_sql(table_name: str) -> str:
    return f"""
    create table if not exists {table_name} (
      entity_index_version string,
      facility_id string,
      facility_name string,
      resolved_entity_id string,
      canonical_name string,
      entity_record_count int,
      entity_match_confidence double,
      entity_match_reasons string,
      duplicate_review_required boolean,
      entity_search_text string,
      address_city string,
      address_stateOrRegion string,
      address_zipOrPostcode string,
      website_domain string,
      primary_source_url string,
      source_row_fingerprint string,
      source_table string,
      built_at string
    )
    using delta
    """


def _add_missing_column(
    client: WorkspaceClient,
    warehouse_id: str,
    table_name: str,
    column_definition: str,
) -> None:
    try:
        _execute_sql(client, warehouse_id, f"alter table {table_name} add columns ({column_definition})")
    except RuntimeError as exc:
        message = str(exc).lower()
        if "already exists" not in message and "duplicate" not in message:
            raise


def _insert_batches(
    client: WorkspaceClient,
    warehouse_id: str,
    table_name: str,
    frame: pd.DataFrame,
    batch_size: int,
) -> None:
    columns = ", ".join(ENTITY_INDEX_COLUMNS)
    for start in range(0, len(frame), batch_size):
        batch = frame.iloc[start : start + batch_size]
        values = []
        for _, row in batch.iterrows():
            values.append("(" + ", ".join(_sql_literal(row[column]) for column in ENTITY_INDEX_COLUMNS) + ")")
        _execute_sql(
            client,
            warehouse_id,
            f"insert into {table_name} ({columns}) values {', '.join(values)}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the cached Care Convoy facility entity index table.")
    parser.add_argument(
        "--table",
        default=os.environ.get("ENTITY_INDEX_TABLE", DEFAULT_ENTITY_INDEX_TABLE),
        help="Three-part Delta table name for the cached entity index.",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE", ""),
    )
    parser.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    parser.add_argument("--limit", type=int, default=0, help="Optional source row limit for smoke testing.")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    table_name = entity_index_table_name(args.table)
    if not table_name:
        print("ENTITY_INDEX_TABLE must be a safe three-part table name such as workspace.default.care_convoy_facility_entity_index.")
        return 2
    if not args.warehouse_id:
        print("DATABRICKS_WAREHOUSE_ID is required.")
        return 2

    os.environ["DATABRICKS_WAREHOUSE_ID"] = args.warehouse_id
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile

    raw = _load_source_rows(args.limit, max(args.page_size, 1))
    if raw.empty:
        print("No facility rows were returned; refusing to publish an empty entity index.")
        return 1

    index = build_entity_index_frame(raw)
    print(f"Built {len(index)} entity-index rows with version {ENTITY_INDEX_VERSION}.")
    print(index[["facility_id", "facility_name", "resolved_entity_id", "entity_record_count"]].head(5).to_string(index=False))
    if args.dry_run:
        return 0

    client = _workspace_client(args.profile)
    catalog, schema, _ = table_name.split(".")
    _execute_sql(client, args.warehouse_id, f"create schema if not exists {catalog}.{schema}")
    _execute_sql(client, args.warehouse_id, _create_table_sql(table_name))
    _add_missing_column(client, args.warehouse_id, table_name, "source_row_fingerprint string")
    _execute_sql(client, args.warehouse_id, f"delete from {table_name} where entity_index_version = '{ENTITY_INDEX_VERSION}'")
    _insert_batches(client, args.warehouse_id, table_name, index, max(args.batch_size, 1))
    print(f"Published {len(index)} rows to {table_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
