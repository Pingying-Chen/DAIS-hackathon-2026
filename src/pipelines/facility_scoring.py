from __future__ import annotations

import argparse
import os

import pandas as pd

from src.agent.tools import (
    SCORING_COLUMNS,
    SCORING_VERSION,
    build_facility_scoring_frame,
    scoring_table_name,
)
from src.db.warehouse import run_sql
from src.pipelines.entity_index import (
    _add_missing_column,
    _execute_sql,
    _load_source_rows,
    _sql_literal,
    _workspace_client,
)
from src.pipelines.feedback import append_only_frame

DEFAULT_SCORING_TABLE = "workspace.default.care_convoy_facility_scoring"
SCORING_KEY_COLUMNS = ["scoring_version", "facility_id", "source_row_fingerprint"]


def _create_table_sql(table_name: str) -> str:
    return f"""
    create table if not exists {table_name} (
      scoring_version string,
      facility_id string,
      facility_name string,
      candidate_seed_score double,
      evidence_count int,
      capability_fit double,
      dataset_trust_score double,
      freshness_signal double,
      confidence_label string,
      risk_flags string,
      source_row_fingerprint string,
      source_table string,
      built_at string
    )
    using delta
    """


def _existing_rows_sql(table_name: str) -> str:
    return f"""
    select {", ".join(SCORING_COLUMNS)}
    from {table_name}
    where scoring_version = '{SCORING_VERSION}'
    """


def _load_existing_rows(table_name: str) -> pd.DataFrame:
    existing = run_sql(_existing_rows_sql(table_name), timeout_seconds=20)
    if existing.empty:
        return pd.DataFrame(columns=SCORING_COLUMNS)
    for column in SCORING_COLUMNS:
        if column not in existing:
            existing[column] = None
    return existing[SCORING_COLUMNS]


def _insert_scoring_batches(
    client: object,
    warehouse_id: str,
    table_name: str,
    frame: pd.DataFrame,
    batch_size: int,
) -> None:
    columns = ", ".join(SCORING_COLUMNS)
    for start in range(0, len(frame), batch_size):
        batch = frame.iloc[start : start + batch_size]
        values = []
        for _, row in batch.iterrows():
            values.append("(" + ", ".join(_sql_literal(row[column]) for column in SCORING_COLUMNS) + ")")
        _execute_sql(
            client,
            warehouse_id,
            f"insert into {table_name} ({columns}) values {', '.join(values)}",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build the append-only Care Convoy facility scoring table.")
    parser.add_argument(
        "--table",
        default=os.environ.get("SCORING_TABLE", DEFAULT_SCORING_TABLE),
        help="Three-part Delta table name for cached facility scores.",
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
    parser.add_argument("--full-refresh", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    table_name = scoring_table_name(args.table)
    if not table_name:
        print("SCORING_TABLE must be a safe three-part table name such as workspace.default.care_convoy_facility_scoring.")
        return 2
    if not args.warehouse_id:
        print("DATABRICKS_WAREHOUSE_ID is required.")
        return 2

    os.environ["DATABRICKS_WAREHOUSE_ID"] = args.warehouse_id
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile

    raw = _load_source_rows(args.limit, max(args.page_size, 1))
    if raw.empty:
        print("No facility rows were returned; refusing to publish an empty scoring table.")
        return 1

    scoring = build_facility_scoring_frame(raw)
    existing = pd.DataFrame(columns=SCORING_COLUMNS) if args.full_refresh else _load_existing_rows(table_name)
    append_frame = scoring if args.full_refresh else append_only_frame(scoring, existing, SCORING_KEY_COLUMNS)
    print(f"Built {len(scoring)} facility scoring rows with version {SCORING_VERSION}.")
    print(f"Existing scoring rows skipped: {len(scoring) - len(append_frame)}. New scoring rows to append: {len(append_frame)}.")
    print(append_frame[["facility_id", "facility_name", "candidate_seed_score"]].head(5).to_string(index=False))
    if args.dry_run:
        return 0

    client = _workspace_client(args.profile)
    catalog, schema, _ = table_name.split(".")
    _execute_sql(client, args.warehouse_id, f"create schema if not exists {catalog}.{schema}")
    _execute_sql(client, args.warehouse_id, _create_table_sql(table_name))
    _add_missing_column(client, args.warehouse_id, table_name, "source_row_fingerprint string")
    if args.full_refresh:
        _execute_sql(client, args.warehouse_id, f"delete from {table_name} where scoring_version = '{SCORING_VERSION}'")
    if not append_frame.empty:
        _insert_scoring_batches(client, args.warehouse_id, table_name, append_frame, max(args.batch_size, 1))
    print(f"Published {len(append_frame)} new scoring rows to {table_name}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
