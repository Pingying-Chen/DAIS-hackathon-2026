from __future__ import annotations

import argparse
import os
from typing import Any

import pandas as pd

from src.agent.tools import (
    DEFAULT_SEARCH_RESULT_TABLE,
    DEFAULT_TRUST_REVIEW_TABLE,
    DEFAULT_WEBSITE_SIGNAL_TABLE,
    SEARCH_RESULT_COLUMNS,
    TRUST_REVIEW_COLUMNS,
    WEBSITE_SIGNAL_COLUMNS,
    _build_facility_review_frame,
    _clean_facility_candidates,
    _facility_candidate_sql,
    _resolve_entity_frame,
    build_trust_reviews,
    collect_website_signals,
    joined_facility_table_name,
    search_facility_sources,
    search_result_table_name,
    trust_review_table_name,
    website_signal_table_name,
)
from src.db.warehouse import run_sql
from src.pipelines.entity_index import _execute_sql, _sql_literal, _workspace_client


def _create_search_result_table_sql(table_name: str) -> str:
    return f"""
    create or replace table {table_name} (
      resolved_entity_id string,
      facility_id string,
      facility_name string,
      query string,
      selection_source string,
      result_rank int,
      selected boolean,
      result_title string,
      result_url string,
      result_domain string,
      match_confidence double
    )
    using delta
    """


def _create_website_signal_table_sql(table_name: str) -> str:
    return f"""
    create or replace table {table_name} (
      resolved_entity_id string,
      facility_id string,
      primary_url string,
      primary_domain string,
      verification_source string,
      page_status string,
      page_title string,
      meta_description string,
      website_excerpt string,
      social_link_count int,
      contact_signal_count int,
      capability_mentions int,
      name_match_score double,
      domain_matches_dataset boolean
    )
    using delta
    """


def _create_trust_review_table_sql(table_name: str) -> str:
    return f"""
    create or replace table {table_name} (
      resolved_entity_id string,
      facility_id string,
      facility_name string,
      canonical_name string,
      entity_record_count int,
      entity_match_confidence double,
      entity_match_reasons string,
      duplicate_review_required boolean,
      search_query string,
      selection_source string,
      website_verification_status string,
      primary_url string,
      primary_domain string,
      website_excerpt string,
      social_link_count int,
      contact_signal_count int,
      capability_mentions int,
      name_match_score double,
      dataset_social_score double,
      website_signal_score double,
      resolution_signal_score double,
      freshness_signal_score double,
      trust_score_v2 double,
      review_status string,
      risk_flags string
    )
    using delta
    """


def _insert_batches(
    client: object,
    warehouse_id: str,
    table_name: str,
    frame: pd.DataFrame,
    columns: list[str],
    batch_size: int,
) -> None:
    if frame.empty:
        return
    column_list = ", ".join(columns)
    for start in range(0, len(frame), batch_size):
        batch = frame.iloc[start : start + batch_size]
        values = []
        for _, row in batch.iterrows():
            values.append("(" + ", ".join(_sql_literal(row[column]) for column in columns) + ")")
        _execute_sql(
            client,
            warehouse_id,
            f"insert into {table_name} ({column_list}) values {', '.join(values)}",
        )


def _source_rows_sql(source_table: str, limit: int, state_filter: str, district_filter: str) -> tuple[str, dict[str, object]]:
    parameters: dict[str, object] = {}
    filters = ["1 = 1"]
    if state_filter:
        filters.append("(coalesce(lower(f.joined_state), '') like lower(:state_filter) or coalesce(lower(f.address_stateOrRegion), '') like lower(:state_filter))")
        parameters["state_filter"] = f"%{state_filter}%"
    if district_filter:
        filters.append("(coalesce(lower(f.joined_district), '') like lower(:district_filter) or coalesce(lower(f.address_city), '') like lower(:district_filter))")
        parameters["district_filter"] = f"%{district_filter}%"

    previous_window = os.environ.get("FACILITY_REVIEW_WINDOW")
    os.environ["FACILITY_REVIEW_WINDOW"] = str(max(limit, 0))
    try:
        sql = _facility_candidate_sql(
            "general_access",
            " and ".join(filters),
            "1 = 1",
            source_table,
            use_entity_index=True,
            use_scoring_cache=True,
            require_keyword_match=False,
        )
    finally:
        if previous_window is None:
            os.environ.pop("FACILITY_REVIEW_WINDOW", None)
        else:
            os.environ["FACILITY_REVIEW_WINDOW"] = previous_window
    return sql, parameters


def build_scrape_cache_frames(
    source_rows: pd.DataFrame,
    *,
    allow_search: bool,
    allow_scrape: bool,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    if source_rows.empty:
        return (
            pd.DataFrame(columns=SEARCH_RESULT_COLUMNS),
            pd.DataFrame(columns=WEBSITE_SIGNAL_COLUMNS),
            pd.DataFrame(columns=TRUST_REVIEW_COLUMNS),
        )

    cleaned = _clean_facility_candidates(source_rows)
    resolved, _ = _resolve_entity_frame(cleaned)
    search_results = search_facility_sources(
        resolved,
        allow_search=allow_search,
        max_facilities=0,
    )
    website_signals = collect_website_signals(
        resolved,
        search_results,
        allow_web_enrichment=allow_scrape,
        max_facilities=0,
    )
    trust_reviews = build_trust_reviews(resolved, search_results, website_signals, source="live")
    return search_results, website_signals, trust_reviews


def publish_scrape_cache(
    *,
    source_table: str,
    search_table: str,
    website_table: str,
    trust_table: str,
    profile: str,
    warehouse_id: str,
    limit: int,
    batch_size: int,
    state_filter: str,
    district_filter: str,
    allow_search: bool,
    allow_scrape: bool,
) -> dict[str, int]:
    sql, parameters = _source_rows_sql(source_table, limit, state_filter, district_filter)
    source_rows = run_sql(sql, timeout_seconds=120, parameters=parameters)
    if source_rows.attrs.get("error"):
        raise RuntimeError(str(source_rows.attrs["error"]))
    if source_rows.empty:
        raise RuntimeError("No source rows returned for scrape cache.")

    search_results, website_signals, trust_reviews = build_scrape_cache_frames(
        source_rows,
        allow_search=allow_search,
        allow_scrape=allow_scrape,
    )

    client = _workspace_client(profile)
    for table_name in [search_table, website_table, trust_table]:
        catalog, schema, _ = table_name.split(".")
        _execute_sql(client, warehouse_id, f"create schema if not exists {catalog}.{schema}")
    _execute_sql(client, warehouse_id, _create_search_result_table_sql(search_table))
    _execute_sql(client, warehouse_id, _create_website_signal_table_sql(website_table))
    _execute_sql(client, warehouse_id, _create_trust_review_table_sql(trust_table))
    _insert_batches(client, warehouse_id, search_table, search_results, SEARCH_RESULT_COLUMNS, batch_size)
    _insert_batches(client, warehouse_id, website_table, website_signals, WEBSITE_SIGNAL_COLUMNS, batch_size)
    _insert_batches(client, warehouse_id, trust_table, trust_reviews, TRUST_REVIEW_COLUMNS, batch_size)

    return {
        "source_rows": int(len(source_rows)),
        "search_rows": int(len(search_results)),
        "website_signal_rows": int(len(website_signals)),
        "trust_review_rows": int(len(trust_reviews)),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Precompute and store Care Convoy search/scrape/trust evidence.")
    parser.add_argument("--source-table", default=os.environ.get("JOINED_FACILITY_TABLE", joined_facility_table_name()))
    parser.add_argument("--search-table", default=os.environ.get("SEARCH_RESULT_TABLE", DEFAULT_SEARCH_RESULT_TABLE))
    parser.add_argument("--website-table", default=os.environ.get("WEBSITE_SIGNAL_TABLE", DEFAULT_WEBSITE_SIGNAL_TABLE))
    parser.add_argument("--trust-table", default=os.environ.get("TRUST_REVIEW_TABLE", DEFAULT_TRUST_REVIEW_TABLE))
    parser.add_argument("--profile", default=os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE", ""))
    parser.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    parser.add_argument("--limit", type=int, default=1000)
    parser.add_argument("--batch-size", type=int, default=100)
    parser.add_argument("--state", default="")
    parser.add_argument("--district", default="")
    parser.add_argument("--allow-search", action="store_true")
    parser.add_argument("--allow-scrape", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    source_table = joined_facility_table_name(args.source_table)
    search_table = search_result_table_name(args.search_table)
    website_table = website_signal_table_name(args.website_table)
    trust_table = trust_review_table_name(args.trust_table)
    if not all([source_table, search_table, website_table, trust_table]):
        print("All scrape cache table names must be safe three-part table names.")
        return 2
    if not args.warehouse_id:
        print("DATABRICKS_WAREHOUSE_ID is required.")
        return 2

    os.environ["DATABRICKS_WAREHOUSE_ID"] = args.warehouse_id
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile

    summary = publish_scrape_cache(
        source_table=source_table,
        search_table=search_table,
        website_table=website_table,
        trust_table=trust_table,
        profile=args.profile,
        warehouse_id=args.warehouse_id,
        limit=args.limit,
        batch_size=max(args.batch_size, 1),
        state_filter=args.state,
        district_filter=args.district,
        allow_search=args.allow_search,
        allow_scrape=args.allow_scrape,
    )
    print(
        "Published scrape cache: source rows {source_rows}; search rows {search_rows}; website signal rows {website_signal_rows}; trust review rows {trust_review_rows}.".format(
            **summary
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
