from __future__ import annotations

import argparse
import os

from src.agent.tools import (
    CATALOG,
    DEFAULT_JOINED_DISTRICT_TABLE,
    DEFAULT_JOINED_FACILITY_TABLE,
    FACILITY_NUMERIC_COLUMNS,
    FACILITY_TEXT_COLUMNS,
    SCHEMA,
    joined_district_table_name,
    _source_row_fingerprint_sql,
    joined_facility_table_name,
)
from src.db.warehouse import run_sql

FACILITY_SOURCE_URI = f"unity-catalog://{CATALOG}.{SCHEMA}.facilities"
PINCODE_SOURCE_URI = f"unity-catalog://{CATALOG}.{SCHEMA}.india_post_pincode_directory"
NFHS_SOURCE_URI = f"unity-catalog://{CATALOG}.{SCHEMA}.nfhs_5_district_health_indicators"


def _numeric_sql(expression: str) -> str:
    normalized = f"lower(trim(cast({expression} as string)))"
    return f"""
    case
      when {normalized} in ('true', 'yes', 'y') then 1.0
      when {normalized} in ('false', 'no', 'n') then 0.0
      else coalesce(try_cast(regexp_extract(cast({expression} as string), '-?[0-9]+[.]?[0-9]*', 0) as double), 0.0)
    end
    """


def _location_key_sql(expression: str) -> str:
    return f"regexp_replace(lower(coalesce(cast({expression} as string), '')), '[^a-z0-9]', '')"


def _state_key_sql(expression: str) -> str:
    key_expression = _location_key_sql(expression)
    return f"case when {key_expression} = 'maharastra' then 'maharashtra' else {key_expression} end"


def _facility_projection_sql() -> str:
    text_columns = [f"cast(f.{column} as string) as {column}" for column in FACILITY_TEXT_COLUMNS]
    numeric_columns = [f"{_numeric_sql(f'f.{column}')} as {column}" for column in FACILITY_NUMERIC_COLUMNS]
    return ",\n      ".join(text_columns + numeric_columns)


def _create_joined_table_sql(table_name: str) -> str:
    return f"""
    create or replace table {table_name}
    using delta
    as
    with source_facilities as (
      select
        {_facility_projection_sql()},
        regexp_replace(coalesce(cast(f.address_zipOrPostcode as string), ''), '[^0-9]', '') as normalized_pincode
      from {CATALOG}.{SCHEMA}.facilities f
      where coalesce(lower(cast(f.address_country as string)), '') like '%india%'
    ),
    pincode_geo as (
      select
        regexp_replace(cast(pincode as string), '[^0-9]', '') as normalized_pincode,
        min(nullif(trim(cast(district as string)), '')) as pincode_district,
        min(nullif(trim(cast(statename as string)), '')) as pincode_state,
        avg({_numeric_sql('latitude')}) as pincode_latitude,
        avg({_numeric_sql('longitude')}) as pincode_longitude
      from {CATALOG}.{SCHEMA}.india_post_pincode_directory
      where pincode is not null
      group by regexp_replace(cast(pincode as string), '[^0-9]', '')
    ),
    nfhs as (
      select
        cast(district_name as string) as nfhs_district_name,
        cast(state_ut as string) as nfhs_state,
        {_location_key_sql('district_name')} as nfhs_district_key,
        {_state_key_sql('state_ut')} as nfhs_state_key,
        {_numeric_sql('households_surveyed')} as households_surveyed,
        {_numeric_sql('women_15_49_interviewed')} as women_15_49_interviewed,
        {_numeric_sql('men_15_54_interviewed')} as men_15_54_interviewed,
        {_numeric_sql('child_u5_who_are_underweight_weight_for_age_18_pct')} as child_underweight_pct,
        {_numeric_sql('hh_member_covered_health_insurance_pct')} as insurance_pct,
        {_numeric_sql('institutional_birth_5y_pct')} as institutional_birth_pct,
        {_numeric_sql('w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct')} as high_bp_pct,
        {_numeric_sql('mothers_who_had_at_least_4_anc_visits_lb5y_pct')} as mothers_four_anc_pct,
        {_numeric_sql('births_delivered_by_csection_5y_pct')} as csection_birth_pct,
        {_numeric_sql('all_w15_49_who_are_anaemic_pct')} as women_anaemia_pct
      from {CATALOG}.{SCHEMA}.nfhs_5_district_health_indicators
    ),
    facility_geo as (
      select
        sf.*,
        pg.pincode_district,
        pg.pincode_state,
        pg.pincode_latitude,
        pg.pincode_longitude,
        coalesce(nullif(pg.pincode_district, ''), nullif(sf.address_city, '')) as joined_district,
        coalesce(nullif(pg.pincode_state, ''), nullif(sf.address_stateOrRegion, '')) as joined_state,
        case
          when pg.pincode_district is not null then 'pincode'
          when sf.address_city is not null and sf.address_city <> '' then 'facility_city'
          else 'missing'
        end as joined_district_source
      from source_facilities sf
      left join pincode_geo pg
        on sf.normalized_pincode = pg.normalized_pincode
    ),
    facility_keys as (
      select
        fg.*,
        {_location_key_sql('fg.joined_district')} as joined_district_key,
        {_state_key_sql('fg.joined_state')} as joined_state_key
      from facility_geo fg
    )
    select
      fk.*,
      n.nfhs_district_name,
      n.nfhs_state,
      n.households_surveyed,
      n.women_15_49_interviewed,
      n.men_15_54_interviewed,
      n.child_underweight_pct,
      n.insurance_pct,
      n.institutional_birth_pct,
      n.high_bp_pct,
      n.mothers_four_anc_pct,
      n.csection_birth_pct,
      n.women_anaemia_pct,
      case when fk.normalized_pincode <> '' and fk.pincode_district is not null then true else false end as has_pincode_join,
      case when n.nfhs_district_name is not null then true else false end as has_nfhs_join,
      {_source_row_fingerprint_sql('fk.')} as source_row_fingerprint,
      cast('{FACILITY_SOURCE_URI}' as string) as facility_source_uri,
      cast('{PINCODE_SOURCE_URI}' as string) as pincode_source_uri,
      cast('{NFHS_SOURCE_URI}' as string) as nfhs_source_uri,
      cast(current_timestamp() as string) as joined_at
    from facility_keys fk
    left join nfhs n
      on fk.joined_district_key = n.nfhs_district_key
      and fk.joined_state_key = n.nfhs_state_key
    """


def _district_need_projection_sql() -> str:
    return f"""
        cast(district_name as string) as district,
        cast(state_ut as string) as state,
        {_location_key_sql('district_name')} as district_key,
        {_state_key_sql('state_ut')} as state_key,
        {_numeric_sql('households_surveyed')} as households_surveyed,
        {_numeric_sql('women_15_49_interviewed')} as women_15_49_interviewed,
        {_numeric_sql('men_15_54_interviewed')} as men_15_54_interviewed,
        {_numeric_sql('child_u5_who_are_underweight_weight_for_age_18_pct')} as child_underweight_pct,
        {_numeric_sql('hh_member_covered_health_insurance_pct')} as insurance_pct,
        {_numeric_sql('institutional_birth_5y_pct')} as institutional_birth_pct,
        {_numeric_sql('w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct')} as high_bp_pct,
        {_numeric_sql('mothers_who_had_at_least_4_anc_visits_lb5y_pct')} as mothers_four_anc_pct,
        {_numeric_sql('births_delivered_by_csection_5y_pct')} as csection_birth_pct,
        {_numeric_sql('all_w15_49_who_are_anaemic_pct')} as women_anaemia_pct
    """


def _mission_count_sql(mission_type: str) -> str:
    keywords = {
        "maternal_health": ["maternal", "obstetric", "delivery", "nicu"],
        "surgery": ["surgery", "surgical", "operating", "trauma"],
        "emergency_care": ["emergency", "icu", "critical", "ambulance"],
        "general_access": ["general", "primary", "community", "outpatient"],
    }[mission_type]
    fields = ["specialties", "procedure", "equipment", "capability", "description"]
    clauses = [
        f"coalesce(lower({field}), '') like '%{keyword}%'"
        for keyword in keywords
        for field in fields
    ]
    return f"count(distinct case when {' or '.join(clauses)} then unique_id end) as {mission_type}_facility_count"


def _create_joined_district_table_sql(table_name: str, facility_table_name: str) -> str:
    return f"""
    create or replace table {table_name}
    using delta
    as
    with nfhs as (
      select
        {_district_need_projection_sql()}
      from {CATALOG}.{SCHEMA}.nfhs_5_district_health_indicators
    ),
    facility_density as (
      select
        joined_district_key as district_key,
        joined_state_key as state_key,
        count(distinct unique_id) as facility_count,
        {_mission_count_sql('maternal_health')},
        {_mission_count_sql('surgery')},
        {_mission_count_sql('emergency_care')},
        {_mission_count_sql('general_access')},
        avg(coalesce(latitude, pincode_latitude)) as latitude,
        avg(coalesce(longitude, pincode_longitude)) as longitude
      from {facility_table_name}
      where joined_district_key <> ''
        and joined_state_key <> ''
      group by joined_district_key, joined_state_key
    )
    select
      n.*,
      coalesce(fd.facility_count, 0) as facility_count,
      coalesce(fd.maternal_health_facility_count, 0) as maternal_health_facility_count,
      coalesce(fd.surgery_facility_count, 0) as surgery_facility_count,
      coalesce(fd.emergency_care_facility_count, 0) as emergency_care_facility_count,
      coalesce(fd.general_access_facility_count, 0) as general_access_facility_count,
      fd.latitude,
      fd.longitude,
      case when fd.facility_count is not null then true else false end as density_matched,
      cast('{NFHS_SOURCE_URI}' as string) as nfhs_source_uri,
      cast('{facility_table_name}' as string) as facility_readiness_table,
      cast(current_timestamp() as string) as joined_at
    from nfhs n
    left join facility_density fd
      on n.district_key = fd.district_key
      and n.state_key = fd.state_key
    """


def _execute_statement(statement: str, timeout_seconds: int = 180) -> None:
    result = run_sql(statement, timeout_seconds=timeout_seconds)
    if result.attrs.get("error"):
        raise RuntimeError(str(result.attrs["error"]))


def publish_joined_dataset(facility_table_name: str, district_table_name: str) -> dict[str, int]:
    catalog, schema, _ = facility_table_name.split(".")
    _execute_statement(f"create schema if not exists {catalog}.{schema}", timeout_seconds=60)
    district_catalog, district_schema, _ = district_table_name.split(".")
    _execute_statement(f"create schema if not exists {district_catalog}.{district_schema}", timeout_seconds=60)
    _execute_statement(_create_joined_table_sql(facility_table_name), timeout_seconds=240)
    _execute_statement(_create_joined_district_table_sql(district_table_name, facility_table_name), timeout_seconds=180)
    summary = run_sql(
        f"""
        select
          count(*) as facility_rows,
          count(distinct unique_id) as distinct_facilities,
          sum(case when has_pincode_join then 1 else 0 end) as pincode_joined_rows,
          sum(case when has_nfhs_join then 1 else 0 end) as nfhs_joined_rows
        from {facility_table_name}
        """,
        timeout_seconds=60,
    )
    if summary.attrs.get("error"):
        raise RuntimeError(str(summary.attrs["error"]))
    if summary.empty:
        raise RuntimeError("Joined dataset published, but validation returned no rows.")
    district_summary = run_sql(
        f"""
        select
          count(*) as district_rows,
          sum(case when density_matched then 1 else 0 end) as districts_with_facility_density
        from {district_table_name}
        """,
        timeout_seconds=60,
    )
    if district_summary.attrs.get("error"):
        raise RuntimeError(str(district_summary.attrs["error"]))
    if district_summary.empty:
        raise RuntimeError("Joined district dataset published, but validation returned no rows.")
    values = summary.iloc[0].to_dict() | district_summary.iloc[0].to_dict()
    return {key: int(float(value or 0)) for key, value in values.items()}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish the app-ready joined Care Convoy facility dataset.")
    parser.add_argument(
        "--table",
        default=os.environ.get("JOINED_FACILITY_TABLE", DEFAULT_JOINED_FACILITY_TABLE),
        help="Three-part Delta table name for the joined app dataset.",
    )
    parser.add_argument(
        "--district-table",
        default=os.environ.get("JOINED_DISTRICT_TABLE", DEFAULT_JOINED_DISTRICT_TABLE),
        help="Three-part Delta table name for the joined district readiness dataset.",
    )
    parser.add_argument(
        "--profile",
        default=os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE", ""),
    )
    parser.add_argument("--warehouse-id", default=os.environ.get("DATABRICKS_WAREHOUSE_ID", ""))
    parser.add_argument("--dry-run", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    table_name = joined_facility_table_name(args.table)
    district_table_name = joined_district_table_name(args.district_table)
    if not table_name:
        print("JOINED_FACILITY_TABLE must be a safe three-part table name such as workspace.default.care_convoy_joined_facility_readiness.")
        return 2
    if not district_table_name:
        print("JOINED_DISTRICT_TABLE must be a safe three-part table name such as workspace.default.care_convoy_joined_district_readiness.")
        return 2
    if not args.warehouse_id:
        print("DATABRICKS_WAREHOUSE_ID is required.")
        return 2

    os.environ["DATABRICKS_WAREHOUSE_ID"] = args.warehouse_id
    if args.profile:
        os.environ["DATABRICKS_CONFIG_PROFILE"] = args.profile

    if args.dry_run:
        print(_create_joined_table_sql(table_name))
        print(_create_joined_district_table_sql(district_table_name, table_name))
        return 0

    summary = publish_joined_dataset(table_name, district_table_name)
    print(f"Published joined dataset to {table_name}.")
    print(f"Published joined district dataset to {district_table_name}.")
    print(
        "Facility rows: {facility_rows}; distinct facilities: {distinct_facilities}; pincode joined: {pincode_joined_rows}; NFHS joined: {nfhs_joined_rows}; district rows: {district_rows}; districts with facility density: {districts_with_facility_density}.".format(
            **summary
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
