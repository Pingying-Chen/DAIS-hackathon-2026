from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
from hashlib import sha1
import json
import os
import re
from typing import Any
from urllib.parse import urlparse

import pandas as pd

from src.connectors.search import scrape_public_page, search_public_web
from src.db.lakebase import save_user_decision_record
from src.db.warehouse import run_sql

CATALOG = os.environ.get("HACKATHON_CATALOG", "databricks_virtue_foundation_dataset_dais_2026")
SCHEMA = os.environ.get("HACKATHON_SCHEMA", "virtue_foundation_dataset")
FACILITY_CANDIDATE_WINDOW = 160
ENTITY_INDEX_VERSION = "care-convoy-entity-index-v1"
SCORING_VERSION = "care-convoy-scoring-v1"
ENTITY_RESOLUTION_PAIRWISE_LIMIT = 350
ENTITY_RESOLUTION_MAX_BLOCK_SIZE = 250
_SQL_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

MISSION_KEYWORDS = {
    "maternal_health": ["maternal", "obstetric", "delivery", "nicu"],
    "surgery": ["surgery", "surgical", "operating", "trauma"],
    "emergency_care": ["emergency", "icu", "critical", "ambulance"],
    "general_access": ["general", "primary", "community", "outpatient"],
}

FACILITY_TEXT_COLUMNS = [
    "unique_id",
    "name",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "address_country",
    "specialties",
    "procedure",
    "equipment",
    "capability",
    "description",
    "source_urls",
    "recency_of_page_update",
]
FACILITY_NUMERIC_COLUMNS = [
    "distinct_social_media_presence_count",
    "affiliated_staff_presence",
    "custom_logo_presence",
    "numberDoctors",
    "capacity",
    "latitude",
    "longitude",
]
TRUST_REVIEW_COLUMNS = [
    "resolved_entity_id",
    "facility_id",
    "facility_name",
    "canonical_name",
    "entity_record_count",
    "entity_match_confidence",
    "entity_match_reasons",
    "duplicate_review_required",
    "search_query",
    "selection_source",
    "website_verification_status",
    "primary_url",
    "primary_domain",
    "website_excerpt",
    "social_link_count",
    "contact_signal_count",
    "capability_mentions",
    "name_match_score",
    "dataset_social_score",
    "website_signal_score",
    "resolution_signal_score",
    "freshness_signal_score",
    "trust_score_v2",
    "review_status",
    "risk_flags",
]
SEARCH_RESULT_COLUMNS = [
    "resolved_entity_id",
    "facility_id",
    "facility_name",
    "query",
    "selection_source",
    "result_rank",
    "selected",
    "result_title",
    "result_url",
    "result_domain",
    "match_confidence",
]
WEBSITE_SIGNAL_COLUMNS = [
    "resolved_entity_id",
    "facility_id",
    "primary_url",
    "primary_domain",
    "verification_source",
    "page_status",
    "page_title",
    "meta_description",
    "website_excerpt",
    "social_link_count",
    "contact_signal_count",
    "capability_mentions",
    "name_match_score",
    "domain_matches_dataset",
]
ENTITY_INDEX_COLUMNS = [
    "entity_index_version",
    "facility_id",
    "facility_name",
    "resolved_entity_id",
    "canonical_name",
    "entity_record_count",
    "entity_match_confidence",
    "entity_match_reasons",
    "duplicate_review_required",
    "entity_search_text",
    "address_city",
    "address_stateOrRegion",
    "address_zipOrPostcode",
    "website_domain",
    "primary_source_url",
    "source_row_fingerprint",
    "source_table",
    "built_at",
]
SCORING_COLUMNS = [
    "scoring_version",
    "facility_id",
    "facility_name",
    "candidate_seed_score",
    "evidence_count",
    "capability_fit",
    "dataset_trust_score",
    "freshness_signal",
    "confidence_label",
    "risk_flags",
    "source_row_fingerprint",
    "source_table",
    "built_at",
]
SOURCE_ROW_FINGERPRINT_COLUMNS = FACILITY_TEXT_COLUMNS
_CACHED_ENTITY_COLUMNS = [
    "resolved_entity_id",
    "canonical_name",
    "entity_record_count",
    "entity_match_confidence",
    "entity_match_reasons",
    "duplicate_review_required",
]
_FACILITY_STOPWORDS = {
    "and",
    "care",
    "centre",
    "centres",
    "center",
    "centers",
    "clinic",
    "clinics",
    "dental",
    "diagnostic",
    "diagnostics",
    "doctor",
    "doctors",
    "dr",
    "foundation",
    "health",
    "healthcare",
    "home",
    "hospital",
    "hospitals",
    "india",
    "institute",
    "lab",
    "labs",
    "medical",
    "multispeciality",
    "multi",
    "nursing",
    "speciality",
    "specialty",
    "surgical",
    "trust",
}
_GENERIC_SOURCE_DOMAINS = {
    "facebook.com",
    "hexahealth.com",
    "hospitalsnearme.in",
    "indiamart.com",
    "justdial.com",
    "latlong.net",
    "mappls.com",
    "medindia.net",
    "medicineindia.org",
    "onefivenine.com",
    "policyx.com",
    "practo.com",
    "quickerala.com",
    "sehat.com",
    "wikipedia.org",
}
_STATE_ALIASES = {
    "maharashtra": ["Maharashtra", "Maharastra"],
    "maharastra": ["Maharashtra", "Maharastra"],
}
_STATE_KEY_ALIASES = {
    "maharastra": "maharashtra",
}
_STATE_CANONICAL_NAMES = {
    "maharastra": "Maharashtra",
}


def _tag_source(df: pd.DataFrame, source: str) -> pd.DataFrame:
    tagged = df.copy()
    tagged.attrs["source"] = source
    return tagged


def entity_index_table_name(value: str | None = None) -> str:
    raw_table = (value if value is not None else os.environ.get("ENTITY_INDEX_TABLE", "")).strip()
    if not raw_table:
        return ""
    parts = raw_table.split(".")
    if len(parts) != 3 or not all(_SQL_IDENTIFIER_PATTERN.fullmatch(part) for part in parts):
        return ""
    return ".".join(parts)


def scoring_table_name(value: str | None = None) -> str:
    raw_table = (value if value is not None else os.environ.get("SCORING_TABLE", "")).strip()
    if not raw_table:
        return ""
    parts = raw_table.split(".")
    if len(parts) != 3 or not all(_SQL_IDENTIFIER_PATTERN.fullmatch(part) for part in parts):
        return ""
    return ".".join(parts)


def _empty_search_results() -> pd.DataFrame:
    return pd.DataFrame(columns=SEARCH_RESULT_COLUMNS)


def _empty_website_signals() -> pd.DataFrame:
    return pd.DataFrame(columns=WEBSITE_SIGNAL_COLUMNS)


def _empty_trust_reviews() -> pd.DataFrame:
    return pd.DataFrame(columns=TRUST_REVIEW_COLUMNS)


def _safe_text(value: Any) -> str:
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def _non_empty_text(value: Any) -> bool:
    return bool(_safe_text(value))


def _truthy_value(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None or pd.isna(value):
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _normalized_name(value: Any) -> str:
    text = _safe_text(value).lower()
    text = re.sub(r"[^a-z0-9\s]", " ", text)
    parts = [part for part in text.split() if part and part not in _FACILITY_STOPWORDS]
    return " ".join(parts)


def _location_key(value: Any) -> str:
    text = _safe_text(value).lower()
    return re.sub(r"[^a-z0-9]", "", text)


def _state_key(value: Any) -> str:
    key = _location_key(value)
    return _STATE_KEY_ALIASES.get(key, key)


def _canonical_state_name(value: Any) -> str:
    text = _safe_text(value)
    return _STATE_CANONICAL_NAMES.get(_location_key(text), text)


def _state_filter_terms(state_filter: str) -> list[str]:
    text = _safe_text(state_filter)
    if not text:
        return []
    terms = [text, *_STATE_ALIASES.get(_location_key(text), [])]
    return list(dict.fromkeys(terms))


def _state_filter_clause(columns: list[str], state_filter: str, parameters: dict[str, object]) -> str:
    terms = _state_filter_terms(state_filter)
    if not terms:
        return "1 = 1"

    clauses: list[str] = []
    for index, term in enumerate(terms):
        parameter_name = "state_filter" if index == 0 else f"state_filter_alias_{index}"
        parameters[parameter_name] = f"%{term}%"
        clauses.extend(
            f"coalesce(lower({column}), '') like lower(:{parameter_name})"
            for column in columns
        )
    return " or ".join(clauses)


def _source_urls(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]

    raw = str(value).strip()
    if not raw:
        return []

    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        if raw.startswith(("http://", "https://")):
            return [part.strip() for part in re.split(r",\s*(?=https?://)", raw) if part.strip()]
        return [part.strip() for part in raw.split(",") if part.strip()]

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def _unity_catalog_uri(table_name: str) -> str:
    return f"unity-catalog://{CATALOG}.{SCHEMA}.{table_name}"


def _primary_domain(value: Any) -> str:
    for url in _source_urls(value):
        domain = urlparse(url).netloc.lower()
        if domain:
            return domain
    return ""


def _canonical_domain(value: Any) -> str:
    domain = _safe_text(value).lower()
    if domain.startswith("www."):
        return domain[4:]
    return domain


def _entity_domain(value: Any) -> str:
    domain = _canonical_domain(value)
    if not domain:
        return ""
    if domain in _GENERIC_SOURCE_DOMAINS or any(domain.endswith(f".{item}") for item in _GENERIC_SOURCE_DOMAINS):
        return ""
    return domain


def _in_india_scope(country: Any) -> bool:
    country_text = _safe_text(country).lower()
    return "india" in country_text


def _parse_number(value: Any) -> float:
    if value is None or pd.isna(value):
        return 0.0
    return float(pd.to_numeric(pd.Series([value]), errors="coerce").fillna(0).iloc[0])


def _coordinate_distance(left: pd.Series, right: pd.Series) -> float | None:
    lat_left = _parse_number(left.get("latitude"))
    lon_left = _parse_number(left.get("longitude"))
    lat_right = _parse_number(right.get("latitude"))
    lon_right = _parse_number(right.get("longitude"))
    if not lat_left or not lon_left or not lat_right or not lon_right:
        return None
    return ((lat_left - lat_right) ** 2 + (lon_left - lon_right) ** 2) ** 0.5


def _freshness_signal(value: Any) -> float:
    raw = _safe_text(value)
    if not raw:
        return 0.0
    try:
        updated_at = (
            datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
            if "T" in raw
            else datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
        )
    except ValueError:
        return 0.0

    age_days = max((datetime.now(timezone.utc) - updated_at).days, 0)
    if age_days <= 180:
        return 12.0
    if age_days <= 365:
        return 8.0
    if age_days <= 730:
        return 4.0
    return 1.0


def _non_empty_count(values: list[Any]) -> int:
    return sum(1 for value in values if _non_empty_text(value))


def _fallback_districts(state_filter: str) -> pd.DataFrame:
    data = [
        {
            "district": "Nagpur",
            "state": state_filter or "Maharashtra",
            "need_score": 82.0,
            "coverage_gap": 64.0,
            "facility_count": 7,
            "evidence_score": 71.0,
            "priority_score": 79.0,
            "uncertainty_label": "Moderate Confidence",
            "risk_flags": "district join under review",
            "latitude": 21.1458,
            "longitude": 79.0882,
        },
        {
            "district": "Nashik",
            "state": state_filter or "Maharashtra",
            "need_score": 75.0,
            "coverage_gap": 58.0,
            "facility_count": 9,
            "evidence_score": 67.0,
            "priority_score": 72.0,
            "uncertainty_label": "Moderate Confidence",
            "risk_flags": "facility density may be understated",
            "latitude": 19.9975,
            "longitude": 73.7898,
        },
        {
            "district": "Aurangabad",
            "state": state_filter or "Maharashtra",
            "need_score": 68.0,
            "coverage_gap": 61.0,
            "facility_count": 5,
            "evidence_score": 59.0,
            "priority_score": 69.0,
            "uncertainty_label": "Weak Evidence",
            "risk_flags": "facility evidence sparse",
            "latitude": 19.8762,
            "longitude": 75.3433,
        },
    ]
    return _tag_source(pd.DataFrame(data), "fallback")


def _fallback_facilities(state_filter: str) -> pd.DataFrame:
    data = [
        {
            "unique_id": "demo-1",
            "name": "Sunrise Women and Surgical Centre",
            "address_city": "Nagpur",
            "address_stateOrRegion": state_filter or "Maharashtra",
            "address_zipOrPostcode": "440001",
            "specialties": "Maternal health, surgery, NICU",
            "procedure": "C-section, obstetric emergency, general surgery",
            "equipment": "NICU, blood bank, operating theatre",
            "capability": "24/7 emergency obstetrics and surgical backup",
            "description": "Facility advertises maternal emergency care, operating theatre access, and referral handling.",
            "source_urls": "https://example.org/demo-facility-1",
            "distinct_social_media_presence_count": 3,
            "affiliated_staff_presence": 1,
            "custom_logo_presence": 1,
            "numberDoctors": 18,
            "capacity": 120,
            "recency_of_page_update": "2025-11-01",
            "latitude": 21.1480,
            "longitude": 79.0850,
        },
        {
            "unique_id": "demo-2",
            "name": "CityCare Referral Hospital",
            "address_city": "Nashik",
            "address_stateOrRegion": state_filter or "Maharashtra",
            "address_zipOrPostcode": "422001",
            "specialties": "Emergency care, trauma, surgical support",
            "procedure": "Emergency stabilization, surgery, trauma intake",
            "equipment": "ICU, emergency bay, trauma equipment",
            "capability": "Emergency referral anchor with surgical escalation",
            "description": "Facility profile shows emergency intake capacity and regional referral support.",
            "source_urls": "https://example.org/demo-facility-2",
            "distinct_social_media_presence_count": 2,
            "affiliated_staff_presence": 1,
            "custom_logo_presence": 1,
            "numberDoctors": 14,
            "capacity": 90,
            "recency_of_page_update": "2024-08-14",
            "latitude": 19.9910,
            "longitude": 73.7820,
        },
        {
            "unique_id": "demo-3",
            "name": "Regional Access Clinic",
            "address_city": "Aurangabad",
            "address_stateOrRegion": state_filter or "Maharashtra",
            "address_zipOrPostcode": "431001",
            "specialties": "General access, outpatient, referral support",
            "procedure": "General consult, outpatient referral",
            "equipment": "Basic diagnostics",
            "capability": "Referral staging point with limited direct service evidence",
            "description": "Facility has limited specialty evidence and may require manual verification before use.",
            "source_urls": "",
            "distinct_social_media_presence_count": 0,
            "affiliated_staff_presence": 0,
            "custom_logo_presence": 0,
            "numberDoctors": 4,
            "capacity": 20,
            "recency_of_page_update": "",
            "latitude": 19.8790,
            "longitude": 75.3380,
        },
    ]
    return _tag_source(pd.DataFrame(data), "fallback")


def _keyword_sql(mission_type: str, table_alias: str = "") -> str:
    parts = []
    for keyword in MISSION_KEYWORDS.get(mission_type, []):
        safe = keyword.replace("'", "''")
        parts.append(
            "(coalesce(lower({a}specialties), '') like '%{k}%' or "
            "coalesce(lower({a}procedure), '') like '%{k}%' or "
            "coalesce(lower({a}equipment), '') like '%{k}%' or "
            "coalesce(lower({a}capability), '') like '%{k}%' or "
            "coalesce(lower({a}description), '') like '%{k}%')".format(a=table_alias, k=safe)
        )
    return " or ".join(parts) or "1 = 1"


def _candidate_seed_score_sql(table_alias: str = "") -> str:
    return """
      (
        case when coalesce({a}specialties, '') <> '' then 12 else 0 end +
        case when coalesce({a}procedure, '') <> '' then 12 else 0 end +
        case when coalesce({a}equipment, '') <> '' then 12 else 0 end +
        case when coalesce({a}capability, '') <> '' then 12 else 0 end +
        case when coalesce({a}description, '') <> '' then 12 else 0 end +
        case when coalesce({a}source_urls, '') <> '' then 12 else 0 end +
        coalesce(try_cast({a}numberDoctors as double), 0.0) * 0.7 +
        coalesce(try_cast({a}capacity as double), 0.0) * 0.08 +
        coalesce(try_cast({a}distinct_social_media_presence_count as double), 0.0) * 14 +
        coalesce(try_cast({a}affiliated_staff_presence as double), 0.0) * 18 +
        coalesce(try_cast({a}custom_logo_presence as double), 0.0) * 10
      )
    """.format(a=table_alias)


def _empty_density_frame() -> pd.DataFrame:
    return pd.DataFrame(
        columns=[
            "district",
            "state",
            "facility_count",
            "mission_facility_count",
            "latitude",
            "longitude",
            "district_key",
            "state_key",
        ]
    )


def _district_density_context(
    mission_type: str,
    state_filter: str,
    district_filter: str,
) -> pd.DataFrame:
    keyword_filter = _keyword_sql(mission_type, "f.")
    parameters: dict[str, object] = {}
    state_clause = "1 = 1"
    if state_filter:
        state_clause = _state_filter_clause(["pin.statename", "f.address_stateOrRegion"], state_filter, parameters)

    district_clause = "1 = 1"
    if district_filter:
        district_clause = (
            "coalesce(lower(pin.district), '') like lower(:district_filter) or "
            "coalesce(lower(f.address_city), '') like lower(:district_filter) or "
            "coalesce(lower(f.address_zipOrPostcode), '') like lower(:district_filter)"
        )
        parameters["district_filter"] = f"%{district_filter}%"

    sql = f"""
    select
      coalesce(nullif(pin.district, ''), f.address_city) as district,
      coalesce(nullif(pin.statename, ''), f.address_stateOrRegion) as state,
      count(distinct f.unique_id) as facility_count,
      count(distinct case when ({keyword_filter}) then f.unique_id end) as mission_facility_count,
      avg(cast(f.latitude as double)) as latitude,
      avg(cast(f.longitude as double)) as longitude
    from {CATALOG}.{SCHEMA}.facilities f
    left join {CATALOG}.{SCHEMA}.india_post_pincode_directory pin
      on regexp_replace(coalesce(f.address_zipOrPostcode, ''), '[^0-9]', '') = cast(pin.pincode as string)
    where coalesce(lower(f.address_country), '') like '%india%'
      and ({state_clause})
      and ({district_clause})
    group by
      coalesce(nullif(pin.district, ''), f.address_city),
      coalesce(nullif(pin.statename, ''), f.address_stateOrRegion)
    limit 500
    """
    raw = run_sql(sql, parameters=parameters)
    if raw.empty:
        return _empty_density_frame()

    density = raw.rename(columns=str).copy()
    for column in ["district", "state"]:
        if column not in density:
            density[column] = ""
        density[column] = density[column].apply(_safe_text)
    for column in ["facility_count", "mission_facility_count", "latitude", "longitude"]:
        if column not in density:
            density[column] = 0
        density[column] = pd.to_numeric(density[column], errors="coerce").fillna(0)

    density["district_key"] = density["district"].apply(_location_key)
    density["state_key"] = density["state"].apply(_state_key)
    return density[
        [
            "district",
            "state",
            "facility_count",
            "mission_facility_count",
            "latitude",
            "longitude",
            "district_key",
            "state_key",
        ]
    ]


def _density_confidence_label(row: pd.Series) -> str:
    if not bool(row.get("density_matched", False)):
        return "Data Ambiguous"
    mission_facility_count = _parse_number(row.get("mission_facility_count"))
    facility_count = _parse_number(row.get("facility_count"))
    if mission_facility_count >= 4:
        return "High Confidence"
    if mission_facility_count >= 1 or facility_count >= 3:
        return "Moderate Confidence"
    return "Weak Evidence"


def _density_gap(row: pd.Series) -> float:
    if not bool(row.get("density_matched", False)):
        return 68.0
    facility_count = _parse_number(row.get("facility_count"))
    mission_facility_count = _parse_number(row.get("mission_facility_count"))
    supply_score = min(100.0, mission_facility_count * 18 + max(facility_count - mission_facility_count, 0) * 3)
    return max(0.0, 100.0 - supply_score)


def _nfhs_need_summary(row: pd.Series) -> str:
    return (
        "NFHS: "
        f"child underweight {float(row['child_underweight_pct']):.1f}%, "
        f"insurance coverage {float(row['insurance_pct']):.1f}%, "
        f"institutional birth {float(row['institutional_birth_pct']):.1f}%, "
        f"high BP {float(row['high_bp_pct']):.1f}%."
    )


def _facility_density_summary(row: pd.Series) -> str:
    if not bool(row.get("density_matched", False)):
        return "No district-level facility density row matched; treat supply gap as ambiguous."
    return (
        f"{int(_parse_number(row.get('facility_count')))} facility row(s) matched this district/state; "
        f"{int(_parse_number(row.get('mission_facility_count')))} mission-matching anchor row(s) were found."
    )


def _district_risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if row.get("uncertainty_label") != "High Confidence":
        flags.append("district join under review")
    if row.get("density_confidence_label") == "Data Ambiguous":
        flags.append("facility density under review")
    elif row.get("density_confidence_label") == "Weak Evidence":
        flags.append("facility density is sparse")
    return "; ".join(flags)


def get_district_priorities(
    mission_type: str,
    state_filter: str,
    district_filter: str,
    confidence_threshold: float,
) -> pd.DataFrame:
    state_clause = ""
    parameters: dict[str, object] = {}
    if state_filter:
        state_clause = f"where {_state_filter_clause(['state_ut'], state_filter, parameters)}"

    sql = f"""
    select
      district_name as district,
      state_ut as state,
      coalesce(try_cast(trim(cast(child_u5_who_are_underweight_weight_for_age_18_pct as string)) as double), 0.0) as child_underweight_pct,
      coalesce(try_cast(trim(cast(hh_member_covered_health_insurance_pct as string)) as double), 0.0) as insurance_pct,
      coalesce(try_cast(trim(cast(institutional_birth_5y_pct as string)) as double), 0.0) as institutional_birth_pct,
      coalesce(try_cast(trim(cast(w15_plus_with_high_bp_sys_gte_140_mmhg_and_or_dia_gte_90_mm_pct as string)) as double), 0.0) as high_bp_pct
    from {CATALOG}.{SCHEMA}.nfhs_5_district_health_indicators
    {state_clause}
    limit 50
    """
    raw = run_sql(sql, parameters=parameters)
    if raw.empty:
        return _fallback_districts(state_filter)

    df = raw.rename(columns=str)
    df["state"] = df["state"].apply(_canonical_state_name)
    for column in ["child_underweight_pct", "insurance_pct", "institutional_birth_pct", "high_bp_pct"]:
        if column not in df:
            df[column] = 0
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)
    if district_filter:
        df = df[df["district"].str.contains(district_filter, case=False, na=False, regex=False)]
    if df.empty:
        return _fallback_districts(state_filter)

    density = _district_density_context(mission_type, state_filter, district_filter)

    df["district_key"] = df["district"].apply(_location_key)
    df["state_key"] = df["state"].apply(_state_key)
    df["need_score"] = (
        df["child_underweight_pct"].fillna(0) * 0.45
        + (100 - df["insurance_pct"].fillna(0)) * 0.2
        + (100 - df["institutional_birth_pct"].fillna(0)) * 0.2
        + df["high_bp_pct"].fillna(0) * 0.15
    )
    if mission_type == "maternal_health":
        df["need_score"] = df["need_score"] + (100 - df["institutional_birth_pct"].fillna(0)) * 0.25
    elif mission_type == "general_access":
        df["need_score"] = df["need_score"] + (100 - df["insurance_pct"].fillna(0)) * 0.2

    if not density.empty:
        df = df.merge(
            density.drop(columns=["district", "state"]),
            on=["district_key", "state_key"],
            how="left",
        )
    else:
        df["facility_count"] = 0
        df["mission_facility_count"] = 0
        df["latitude"] = 0
        df["longitude"] = 0
        df["density_matched"] = False

    if "density_matched" not in df:
        df["density_matched"] = df["facility_count"].notna()
    df["facility_count"] = pd.to_numeric(df["facility_count"], errors="coerce").fillna(0)
    df["mission_facility_count"] = pd.to_numeric(df["mission_facility_count"], errors="coerce").fillna(0)
    df["density_confidence_label"] = df.apply(_density_confidence_label, axis=1)
    df["density_gap"] = df.apply(_density_gap, axis=1)
    df["coverage_gap"] = (df["need_score"] * 0.45 + df["density_gap"] * 0.55).clip(0, 100)
    df["evidence_score"] = (
        45
        + df["density_matched"].astype(int) * 20
        + df["mission_facility_count"].clip(0, 5) * 4
        + (100 - df["coverage_gap"]).clip(0, 100) * 0.1
    ).clip(15, 95)
    df["priority_score"] = (df["need_score"] * 0.52 + df["coverage_gap"] * 0.48).clip(0, 100)
    df["uncertainty_label"] = df["evidence_score"].apply(_district_confidence_label)
    df["nfhs_need_summary"] = df.apply(_nfhs_need_summary, axis=1)
    df["facility_density_context"] = df.apply(_facility_density_summary, axis=1)
    df["risk_flags"] = df.apply(_district_risk_flags, axis=1)
    latitudes = pd.to_numeric(df["latitude"], errors="coerce")
    longitudes = pd.to_numeric(df["longitude"], errors="coerce")
    df["latitude"] = latitudes.mask(latitudes.eq(0))
    df["longitude"] = longitudes.mask(longitudes.eq(0))

    threshold_score = confidence_threshold * 100
    scored = df.copy()
    df = scored[scored["evidence_score"] >= threshold_score]
    if df.empty:
        df = scored
    return _tag_source(
        df.sort_values(["priority_score", "need_score"], ascending=False)
        .drop(columns=["district_key", "state_key"], errors="ignore")
        .head(10),
        "live",
    )


def _candidate_seed_score_from_row(row: pd.Series) -> float:
    score = (
        _parse_number(row.get("evidence_count")) * 12
        + _parse_number(row.get("numberDoctors")) * 0.7
        + _parse_number(row.get("capacity")) * 0.08
        + _parse_number(row.get("distinct_social_media_presence_count")) * 14
        + _parse_number(row.get("affiliated_staff_presence")) * 18
        + _parse_number(row.get("custom_logo_presence")) * 10
    )
    return round(float(score), 4)


def _apply_cached_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    cached_numeric_columns = {
        "cached_candidate_seed_score": "candidate_seed_score",
        "cached_evidence_count": "evidence_count",
        "cached_capability_fit": "capability_fit",
        "cached_dataset_trust_score": "dataset_trust_score",
        "cached_freshness_signal": "freshness_signal",
    }
    for cached_column, target_column in cached_numeric_columns.items():
        if cached_column not in df:
            continue
        cached_values = pd.to_numeric(df[cached_column], errors="coerce")
        df[target_column] = cached_values.where(cached_values.notna(), df[target_column])

    if "cached_confidence_label" in df:
        cached_labels = df["cached_confidence_label"].fillna("").astype(str).str.strip()
        df["confidence_label"] = cached_labels.where(cached_labels.ne(""), df["confidence_label"])
    if "cached_score_risk_flags" in df:
        cached_flags = df["cached_score_risk_flags"].fillna("").astype(str).str.strip()
        df["risk_flags"] = cached_flags.where(cached_flags.ne(""), df["risk_flags"])
    return df


def _scoring_cache_source(df: pd.DataFrame) -> str:
    if df.empty or "scoring_version" not in df:
        return "runtime"
    cached_versions = df["scoring_version"].fillna("").astype(str).str.strip()
    cached_count = int(cached_versions.ne("").sum())
    if cached_count == 0:
        return "runtime"
    if cached_count == len(df):
        return "cached"
    return "partial"


def _clean_facility_candidates(raw: pd.DataFrame) -> pd.DataFrame:
    df = raw.rename(columns=str).copy()
    for column in FACILITY_TEXT_COLUMNS + FACILITY_NUMERIC_COLUMNS:
        if column not in df.columns:
            df[column] = ""

    for column in FACILITY_TEXT_COLUMNS:
        df[column] = df[column].apply(_safe_text)
    for column in FACILITY_NUMERIC_COLUMNS:
        df[column] = pd.to_numeric(df[column], errors="coerce").fillna(0)

    df["source_url_list"] = df["source_urls"].apply(_source_urls)
    df["website_domain"] = df["source_urls"].apply(_primary_domain)
    df["normalized_name"] = df["name"].apply(_normalized_name)
    df["normalized_city"] = df["address_city"].apply(_location_key)
    df["normalized_state"] = df["address_stateOrRegion"].apply(_location_key)
    df["country_in_scope"] = df["address_country"].apply(_in_india_scope)
    df["search_query"] = df.apply(
        lambda row: " ".join(
            part
            for part in [row["name"], row["address_city"], row["address_stateOrRegion"], "India hospital"]
            if part
        ),
        axis=1,
    )
    df["freshness_signal"] = df["recency_of_page_update"].apply(_freshness_signal)
    df["evidence_count"] = df.apply(
        lambda row: _non_empty_count(
            [
                row["specialties"],
                row["procedure"],
                row["equipment"],
                row["capability"],
                row["description"],
                row["source_urls"],
            ]
        ),
        axis=1,
    )
    df["capability_fit"] = (
        df["evidence_count"] * 12
        + df["numberDoctors"] * 0.7
        + df["capacity"] * 0.08
    ).clip(0, 100)
    df["dataset_trust_score"] = (
        df["distinct_social_media_presence_count"] * 14
        + df["affiliated_staff_presence"] * 18
        + df["custom_logo_presence"] * 10
        + df["evidence_count"] * 7
        + df["freshness_signal"]
    ).clip(0, 100)
    df["trust_score"] = df["dataset_trust_score"]
    df["urgency_support"] = (df["capability_fit"] * 0.55 + df["dataset_trust_score"] * 0.45).clip(0, 100)
    df["confidence_label"] = df["dataset_trust_score"].apply(_facility_confidence_label)
    df["risk_flags"] = df.apply(_facility_risk_flags, axis=1)
    df["candidate_seed_score"] = df.apply(_candidate_seed_score_from_row, axis=1)
    return _apply_cached_score_columns(df)


def _entity_match(left: pd.Series, right: pd.Series) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    left_id = _safe_text(left.get("unique_id"))
    right_id = _safe_text(right.get("unique_id"))
    if left_id and right_id and left_id == right_id:
        return 1.0, ["shared unique id"]

    left_name = _safe_text(left.get("normalized_name"))
    right_name = _safe_text(right.get("normalized_name"))
    if not left_name or not right_name:
        return 0.0, []

    name_similarity = SequenceMatcher(None, left_name, right_name).ratio()
    if name_similarity < 0.8:
        return 0.0, []

    left_domain = _entity_domain(left.get("website_domain"))
    right_domain = _entity_domain(right.get("website_domain"))
    shared_domain = bool(left_domain and right_domain and left_domain == right_domain)
    shared_tokens = set(left_name.split()).intersection(right_name.split())
    if not shared_tokens and name_similarity < 0.95 and not shared_domain:
        return 0.0, []

    if shared_domain:
        score += 0.52
        reasons.append("shared website domain")

    if name_similarity >= 0.95:
        score += 0.34
        reasons.append("near-exact normalized name")
    elif name_similarity >= 0.88:
        score += 0.25
        reasons.append("strong normalized name match")
    elif name_similarity >= 0.8:
        score += 0.16

    same_city = bool(left.get("normalized_city")) and left.get("normalized_city") == right.get("normalized_city")
    same_state = bool(left.get("normalized_state")) and left.get("normalized_state") == right.get("normalized_state")
    if same_city:
        score += 0.16
        reasons.append("shared city")
    elif same_state:
        score += 0.08
        reasons.append("shared state")

    distance = _coordinate_distance(left, right)
    if distance is not None and distance <= 0.08:
        score += 0.14
        reasons.append("nearby coordinates")

    if left.get("address_zipOrPostcode") and left.get("address_zipOrPostcode") == right.get("address_zipOrPostcode"):
        score += 0.08
        reasons.append("shared postcode")
        if name_similarity >= 0.95 and same_city:
            score += 0.24
            reasons.append("same name and postcode")

    return min(score, 1.0), reasons


def _entity_block_keys(row: pd.Series) -> list[str]:
    keys: list[str] = []
    unique_id = _safe_text(row.get("unique_id"))
    if unique_id:
        keys.append(f"id:{unique_id}")

    domain = _entity_domain(row.get("website_domain"))
    if domain:
        keys.append(f"domain:{domain}")

    normalized_name = _safe_text(row.get("normalized_name"))
    normalized_city = _safe_text(row.get("normalized_city"))
    normalized_state = _safe_text(row.get("normalized_state"))
    postcode = _location_key(row.get("address_zipOrPostcode"))
    if normalized_name and normalized_city:
        keys.append(f"name_city:{normalized_name}|{normalized_city}")
    if normalized_name and normalized_state:
        keys.append(f"name_state:{normalized_name}|{normalized_state}")
    if normalized_name and postcode:
        keys.append(f"name_postcode:{normalized_name}|{postcode}")
    return list(dict.fromkeys(keys))


def _entity_candidate_pairs(resolved: pd.DataFrame, use_blocks: bool) -> list[tuple[int, int]]:
    if not use_blocks or len(resolved) <= ENTITY_RESOLUTION_PAIRWISE_LIMIT:
        return [
            (left_index, right_index)
            for left_index in range(len(resolved))
            for right_index in range(left_index + 1, len(resolved))
        ]

    blocks: dict[str, list[int]] = defaultdict(list)
    for index, row in resolved.iterrows():
        for key in _entity_block_keys(row):
            blocks[key].append(index)

    pairs: set[tuple[int, int]] = set()
    for members in blocks.values():
        if len(members) < 2 or len(members) > ENTITY_RESOLUTION_MAX_BLOCK_SIZE:
            continue
        sorted_members = sorted(set(members))
        for offset, left_index in enumerate(sorted_members):
            for right_index in sorted_members[offset + 1 :]:
                pairs.add((left_index, right_index))
    return sorted(pairs)


def _stable_resolved_entity_id(resolved: pd.DataFrame, canonical_index: int) -> str:
    seed_parts = [
        _safe_text(resolved.loc[canonical_index, "unique_id"]),
        _safe_text(resolved.loc[canonical_index, "normalized_name"]),
        _safe_text(resolved.loc[canonical_index, "normalized_city"]),
        _safe_text(resolved.loc[canonical_index, "normalized_state"]),
    ]
    seed = "|".join(part for part in seed_parts if part) or str(canonical_index)
    return f"entity-{sha1(seed.encode('utf-8')).hexdigest()[:12]}"


def resolve_facility_entities(
    df: pd.DataFrame,
    *,
    use_blocks: bool = False,
    stable_ids: bool = False,
) -> pd.DataFrame:
    if df.empty:
        empty = df.copy()
        empty["resolved_entity_id"] = []
        empty["canonical_name"] = []
        empty["entity_record_count"] = []
        empty["entity_match_confidence"] = []
        empty["entity_match_reasons"] = []
        empty["duplicate_review_required"] = []
        return empty

    resolved = df.copy().reset_index(drop=True)
    parent = list(range(len(resolved)))
    pair_scores: list[tuple[int, int, float, list[str]]] = []

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = parent[index]
        return index

    def union(left_index: int, right_index: int) -> None:
        left_root = find(left_index)
        right_root = find(right_index)
        if left_root != right_root:
            parent[right_root] = left_root

    for left_index, right_index in _entity_candidate_pairs(resolved, use_blocks):
        score, reasons = _entity_match(resolved.iloc[left_index], resolved.iloc[right_index])
        if score >= 0.84:
            union(left_index, right_index)
            pair_scores.append((left_index, right_index, score, reasons))

    clusters: dict[int, list[int]] = defaultdict(list)
    for index in range(len(resolved)):
        clusters[find(index)].append(index)

    cluster_details: dict[int, dict[str, Any]] = {}
    for cluster_number, member_indexes in enumerate(clusters.values(), start=1):
        member_frame = resolved.iloc[member_indexes].copy()
        canonical_index = member_frame.sort_values(
            ["evidence_count", "dataset_trust_score", "capability_fit"], ascending=False
        ).index[0]
        internal_scores = [
            (score, reasons)
            for left_index, right_index, score, reasons in pair_scores
            if left_index in member_indexes and right_index in member_indexes
        ]
        match_confidence = max((score for score, _ in internal_scores), default=1.0)
        reasons = []
        for _, match_reasons in internal_scores:
            reasons.extend(match_reasons)
        reason_text = ", ".join(dict.fromkeys(reasons)) if reasons else "single row candidate"
        cluster_details[canonical_index] = {
            "resolved_entity_id": (
                _stable_resolved_entity_id(resolved, canonical_index)
                if stable_ids
                else f"entity-{cluster_number:02d}"
            ),
            "canonical_name": _safe_text(resolved.loc[canonical_index, "name"]),
            "entity_record_count": len(member_indexes),
            "entity_match_confidence": round(match_confidence, 2),
            "entity_match_reasons": reason_text,
            "duplicate_review_required": len(member_indexes) > 1 and match_confidence < 0.93,
            "member_indexes": member_indexes,
        }

    for detail in cluster_details.values():
        for member_index in detail["member_indexes"]:
            resolved.loc[member_index, "resolved_entity_id"] = detail["resolved_entity_id"]
            resolved.loc[member_index, "canonical_name"] = detail["canonical_name"]
            resolved.loc[member_index, "entity_record_count"] = detail["entity_record_count"]
            resolved.loc[member_index, "entity_match_confidence"] = detail["entity_match_confidence"]
            resolved.loc[member_index, "entity_match_reasons"] = detail["entity_match_reasons"]
            resolved.loc[member_index, "duplicate_review_required"] = detail["duplicate_review_required"]

    return resolved


def _has_cached_entity_mapping(df: pd.DataFrame) -> bool:
    if df.empty or not set(_CACHED_ENTITY_COLUMNS).issubset(df.columns):
        return False
    return bool(_cached_entity_mask(df).all())


def _cached_entity_mask(df: pd.DataFrame) -> pd.Series:
    if df.empty or not set(_CACHED_ENTITY_COLUMNS).issubset(df.columns):
        return pd.Series(False, index=df.index)
    resolved_ids = df["resolved_entity_id"].fillna("").astype(str).str.strip()
    record_counts = pd.to_numeric(df["entity_record_count"], errors="coerce").fillna(0)
    match_confidence = pd.to_numeric(df["entity_match_confidence"], errors="coerce").fillna(0)
    return resolved_ids.ne("") & record_counts.gt(0) & match_confidence.gt(0)


def _apply_cached_entity_mapping(df: pd.DataFrame) -> pd.DataFrame:
    mapped = df.copy()
    mapped["resolved_entity_id"] = mapped["resolved_entity_id"].apply(_safe_text)
    mapped["canonical_name"] = mapped["canonical_name"].apply(_safe_text)
    mapped["entity_record_count"] = pd.to_numeric(mapped["entity_record_count"], errors="coerce").fillna(1)
    mapped["entity_match_confidence"] = pd.to_numeric(mapped["entity_match_confidence"], errors="coerce").fillna(1.0)
    mapped["entity_match_reasons"] = mapped["entity_match_reasons"].apply(_safe_text)
    mapped["duplicate_review_required"] = mapped["duplicate_review_required"].apply(_truthy_value)
    return mapped


def _resolve_entity_frame(df: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    if _has_cached_entity_mapping(df):
        return _apply_cached_entity_mapping(df), "cached"
    cached_mask = _cached_entity_mask(df)
    if bool(cached_mask.any()):
        cached = _apply_cached_entity_mapping(df[cached_mask])
        runtime = resolve_facility_entities(df[~cached_mask])
        return pd.concat([cached, runtime]).sort_index(), "partial"
    return resolve_facility_entities(df), "runtime"


def _primary_source_url(value: Any) -> str:
    urls = _source_urls(value)
    return urls[0] if urls else ""


def _entity_search_text(row: pd.Series) -> str:
    source_urls = " ".join(_source_urls(row.get("source_urls"))[:3])
    parts = [
        row.get("canonical_name"),
        row.get("name"),
        row.get("address_city"),
        row.get("address_stateOrRegion"),
        row.get("address_zipOrPostcode"),
        row.get("specialties"),
        row.get("procedure"),
        row.get("equipment"),
        row.get("capability"),
        row.get("description"),
        row.get("website_domain"),
        source_urls,
    ]
    return " ".join(dict.fromkeys(_safe_text(part) for part in parts if _non_empty_text(part)))[:4000]


def _source_fingerprint_value(row: pd.Series, column: str) -> str:
    if column == "source_urls":
        return _primary_source_url(row.get(column))
    if column == "description":
        return _safe_text(row.get(column))[:2000]
    return _safe_text(row.get(column))


def _source_row_fingerprint(row: pd.Series) -> str:
    fingerprint_text = "||".join(_source_fingerprint_value(row, column) for column in SOURCE_ROW_FINGERPRINT_COLUMNS)
    return sha1(fingerprint_text.encode("utf-8")).hexdigest()


def build_entity_index_frame(raw: pd.DataFrame) -> pd.DataFrame:
    cleaned = _clean_facility_candidates(raw)
    resolved = resolve_facility_entities(cleaned, use_blocks=True, stable_ids=True)
    built_at = datetime.now(timezone.utc).isoformat()
    index = pd.DataFrame(
        {
            "entity_index_version": ENTITY_INDEX_VERSION,
            "facility_id": resolved["unique_id"].apply(_safe_text),
            "facility_name": resolved["name"].apply(_safe_text),
            "resolved_entity_id": resolved["resolved_entity_id"].apply(_safe_text),
            "canonical_name": resolved["canonical_name"].apply(_safe_text),
            "entity_record_count": pd.to_numeric(resolved["entity_record_count"], errors="coerce").fillna(1).astype(int),
            "entity_match_confidence": pd.to_numeric(
                resolved["entity_match_confidence"], errors="coerce"
            ).fillna(1.0),
            "entity_match_reasons": resolved["entity_match_reasons"].apply(_safe_text),
            "duplicate_review_required": resolved["duplicate_review_required"].apply(_truthy_value),
            "entity_search_text": resolved.apply(_entity_search_text, axis=1),
            "address_city": resolved["address_city"].apply(_safe_text),
            "address_stateOrRegion": resolved["address_stateOrRegion"].apply(_safe_text),
            "address_zipOrPostcode": resolved["address_zipOrPostcode"].apply(_safe_text),
            "website_domain": resolved["website_domain"].apply(_safe_text),
            "primary_source_url": resolved["source_urls"].apply(_primary_source_url),
            "source_row_fingerprint": resolved.apply(_source_row_fingerprint, axis=1),
            "source_table": _unity_catalog_uri("facilities"),
            "built_at": built_at,
        }
    )
    index = (
        index.sort_values(
            ["entity_record_count", "entity_match_confidence", "facility_name"],
            ascending=[False, False, True],
        )
        .drop_duplicates(["facility_id", "source_row_fingerprint"])
        .sort_values(["facility_name", "facility_id"])
        .reset_index(drop=True)
    )
    return index[ENTITY_INDEX_COLUMNS]


def build_facility_scoring_frame(raw: pd.DataFrame) -> pd.DataFrame:
    cleaned = _clean_facility_candidates(raw)
    built_at = datetime.now(timezone.utc).isoformat()
    scoring = pd.DataFrame(
        {
            "scoring_version": SCORING_VERSION,
            "facility_id": cleaned["unique_id"].apply(_safe_text),
            "facility_name": cleaned["name"].apply(_safe_text),
            "candidate_seed_score": pd.to_numeric(cleaned["candidate_seed_score"], errors="coerce").fillna(0.0),
            "evidence_count": pd.to_numeric(cleaned["evidence_count"], errors="coerce").fillna(0).astype(int),
            "capability_fit": pd.to_numeric(cleaned["capability_fit"], errors="coerce").fillna(0.0),
            "dataset_trust_score": pd.to_numeric(cleaned["dataset_trust_score"], errors="coerce").fillna(0.0),
            "freshness_signal": pd.to_numeric(cleaned["freshness_signal"], errors="coerce").fillna(0.0),
            "confidence_label": cleaned["confidence_label"].apply(_safe_text),
            "risk_flags": cleaned["risk_flags"].apply(_safe_text),
            "source_row_fingerprint": cleaned.apply(_source_row_fingerprint, axis=1),
            "source_table": _unity_catalog_uri("facilities"),
            "built_at": built_at,
        }
    )
    scoring = (
        scoring.sort_values(["candidate_seed_score", "facility_name"], ascending=[False, True])
        .drop_duplicates(["facility_id", "source_row_fingerprint"])
        .sort_values(["facility_name", "facility_id"])
        .reset_index(drop=True)
    )
    return scoring[SCORING_COLUMNS]


def _mapping_feedback_key(row: pd.Series) -> tuple[str, str, str]:
    return (
        _safe_text(row.get("entity_index_version")),
        _safe_text(row.get("facility_id")),
        _safe_text(row.get("source_row_fingerprint")),
    )


def _mapping_feedback_text_similarity(candidate: pd.Series, existing: pd.Series) -> float:
    candidate_text = _safe_text(candidate.get("entity_search_text")).lower()
    existing_text = _safe_text(existing.get("entity_search_text")).lower()
    if not candidate_text or not existing_text:
        return 0.0
    return SequenceMatcher(None, candidate_text[:1200], existing_text[:1200]).ratio()


def _mapping_feedback_match(candidate: pd.Series, existing: pd.DataFrame) -> tuple[pd.Series | None, str]:
    if existing.empty:
        return None, ""

    candidate_id = _safe_text(candidate.get("facility_id"))
    if candidate_id and "facility_id" in existing:
        exact_id = existing[existing["facility_id"].fillna("").astype(str).str.strip().eq(candidate_id)]
        if not exact_id.empty:
            return exact_id.iloc[0], "existing facility id"

    candidate_name = _normalized_name(candidate.get("facility_name"))
    candidate_city = _location_key(candidate.get("address_city"))
    candidate_state = _location_key(candidate.get("address_stateOrRegion"))
    candidate_postcode = _location_key(candidate.get("address_zipOrPostcode"))
    candidate_domain = _entity_domain(candidate.get("website_domain"))

    for _, existing_row in existing.iterrows():
        existing_name = _normalized_name(existing_row.get("facility_name") or existing_row.get("canonical_name"))
        existing_city = _location_key(existing_row.get("address_city"))
        existing_state = _location_key(existing_row.get("address_stateOrRegion"))
        existing_postcode = _location_key(existing_row.get("address_zipOrPostcode"))
        existing_domain = _entity_domain(existing_row.get("website_domain"))
        same_name = bool(candidate_name and existing_name and candidate_name == existing_name)
        same_location = bool(
            (candidate_city and candidate_city == existing_city)
            or (candidate_postcode and candidate_postcode == existing_postcode)
            or (candidate_state and candidate_state == existing_state)
        )
        if same_name and same_location:
            return existing_row, "exact canonical name and location"
        if candidate_domain and candidate_domain == existing_domain and (same_name or same_location):
            return existing_row, "shared website domain"
        if _mapping_feedback_text_similarity(candidate, existing_row) >= 0.92:
            return existing_row, "search-text similarity"
    return None, ""


def _reuse_mapping(candidate: pd.Series, existing: pd.Series, reason: str) -> dict[str, Any]:
    reused = candidate.to_dict()
    reused["resolved_entity_id"] = _safe_text(existing.get("resolved_entity_id")) or _safe_text(candidate.get("resolved_entity_id"))
    reused["canonical_name"] = _safe_text(existing.get("canonical_name")) or _safe_text(candidate.get("canonical_name"))
    reused["entity_record_count"] = max(int(_parse_number(existing.get("entity_record_count"))), int(_parse_number(candidate.get("entity_record_count"))), 1)
    reused["entity_match_confidence"] = max(
        _parse_number(existing.get("entity_match_confidence")),
        _parse_number(candidate.get("entity_match_confidence")),
        0.92,
    )
    reused["entity_match_reasons"] = f"feedback loop reused cached mapping: {reason}"
    reused["duplicate_review_required"] = _truthy_value(existing.get("duplicate_review_required")) or _truthy_value(
        candidate.get("duplicate_review_required")
    )
    return reused


def build_entity_resolution_feedback_frame(candidate_index: pd.DataFrame, existing_index: pd.DataFrame) -> pd.DataFrame:
    if candidate_index.empty:
        return candidate_index.copy()
    if existing_index.empty:
        return candidate_index.drop_duplicates(["entity_index_version", "facility_id", "source_row_fingerprint"]).reset_index(drop=True)

    existing_keys = {_mapping_feedback_key(row) for _, row in existing_index.iterrows()}
    rows: list[dict[str, Any]] = []
    for _, candidate in candidate_index.iterrows():
        if _mapping_feedback_key(candidate) in existing_keys:
            continue
        existing, reason = _mapping_feedback_match(candidate, existing_index)
        if existing is not None:
            rows.append(_reuse_mapping(candidate, existing, reason))
        else:
            rows.append(candidate.to_dict())
    if not rows:
        return pd.DataFrame(columns=ENTITY_INDEX_COLUMNS)
    return pd.DataFrame(rows, columns=ENTITY_INDEX_COLUMNS).drop_duplicates(
        ["entity_index_version", "facility_id", "source_row_fingerprint"]
    )


def _search_result_match_score(entity: pd.Series, result: pd.Series) -> float:
    haystack = " ".join(
        [
            _safe_text(result.get("title")),
            _safe_text(result.get("snippet")),
            _safe_text(result.get("domain")),
        ]
    ).lower()
    name_similarity = SequenceMatcher(None, _safe_text(entity.get("normalized_name")), _normalized_name(haystack)).ratio()
    city_bonus = 0.1 if _safe_text(entity.get("address_city")).lower() in haystack else 0.0
    domain_bonus = 0.15 if _safe_text(entity.get("website_domain")) and _safe_text(entity.get("website_domain")) == _safe_text(result.get("domain")) else 0.0
    return min(name_similarity + city_bonus + domain_bonus, 1.0)


def search_facility_sources(df: pd.DataFrame, limit: int = 3, allow_search: bool = True) -> pd.DataFrame:
    if df.empty:
        return _empty_search_results()

    canonical = (
        df.sort_values(["urgency_support", "dataset_trust_score"], ascending=False)
        .drop_duplicates("resolved_entity_id")
        .head(4)
    )
    rows: list[dict[str, Any]] = []
    for row in canonical.itertuples(index=False):
        dataset_urls = list(getattr(row, "source_url_list", []))
        if dataset_urls:
            selected_url = dataset_urls[0]
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "facility_name": row.name,
                    "query": row.search_query,
                    "selection_source": "dataset_url",
                    "result_rank": 0,
                    "selected": True,
                    "result_title": row.name,
                    "result_url": selected_url,
                    "result_domain": urlparse(selected_url).netloc.lower(),
                    "match_confidence": 1.0,
                }
            )
            continue

        if not allow_search:
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "facility_name": row.name,
                    "query": row.search_query,
                    "selection_source": "unavailable",
                    "result_rank": -1,
                    "selected": False,
                    "result_title": "",
                    "result_url": "",
                    "result_domain": "",
                    "match_confidence": 0.0,
                }
            )
            continue

        try:
            results = search_public_web(row.search_query, limit=limit)
        except Exception:
            results = _empty_search_results()
        if results.empty:
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "facility_name": row.name,
                    "query": row.search_query,
                    "selection_source": "search_unavailable",
                    "result_rank": -1,
                    "selected": False,
                    "result_title": "",
                    "result_url": "",
                    "result_domain": "",
                    "match_confidence": 0.0,
                }
            )
            continue

        scored = results.copy()
        scored["match_confidence"] = scored.apply(
            lambda result_row: _search_result_match_score(pd.Series(row._asdict()), result_row), axis=1
        )
        best_rank = scored["match_confidence"].astype(float).idxmax()
        for _, result_row in scored.iterrows():
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "facility_name": row.name,
                    "query": row.search_query,
                    "selection_source": "search",
                    "result_rank": int(result_row["rank"]),
                    "selected": bool(result_row.name == best_rank),
                    "result_title": _safe_text(result_row["title"]),
                    "result_url": _safe_text(result_row["url"]),
                    "result_domain": _safe_text(result_row["domain"]),
                    "match_confidence": round(float(result_row["match_confidence"]), 2),
                }
            )

    if not rows:
        return _empty_search_results()
    return pd.DataFrame(rows, columns=SEARCH_RESULT_COLUMNS)


def _capability_terms(row: pd.Series) -> list[str]:
    text = " ".join(
        _safe_text(row.get(column))
        for column in ["specialties", "procedure", "equipment", "capability"]
    ).lower()
    tokens = re.findall(r"[a-z]{5,}", text)
    unique_tokens: list[str] = []
    for token in tokens:
        if token in _FACILITY_STOPWORDS or token in unique_tokens:
            continue
        unique_tokens.append(token)
        if len(unique_tokens) >= 10:
            break
    return unique_tokens


def _count_term_hits(text: str, terms: list[str]) -> int:
    lowered = text.lower()
    return sum(1 for term in terms if term in lowered)


def collect_website_signals(
    df: pd.DataFrame,
    search_results: pd.DataFrame,
    allow_web_enrichment: bool = True,
) -> pd.DataFrame:
    if df.empty:
        return _empty_website_signals()

    canonical = (
        df.sort_values(["urgency_support", "dataset_trust_score"], ascending=False)
        .drop_duplicates("resolved_entity_id")
        .head(4)
    )
    rows: list[dict[str, Any]] = []
    for row in canonical.itertuples(index=False):
        selected = search_results[
            (search_results["resolved_entity_id"] == row.resolved_entity_id) & (search_results["selected"])
        ]
        if selected.empty:
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "primary_url": "",
                    "primary_domain": "",
                    "verification_source": "unavailable",
                    "page_status": "unavailable",
                    "page_title": "",
                    "meta_description": "",
                    "website_excerpt": "",
                    "social_link_count": 0,
                    "contact_signal_count": 0,
                    "capability_mentions": 0,
                    "name_match_score": 0.0,
                    "domain_matches_dataset": False,
                }
            )
            continue

        selected_row = selected.iloc[0]
        primary_url = _safe_text(selected_row["result_url"])
        primary_domain = _safe_text(selected_row["result_domain"])
        verification_source = _safe_text(selected_row["selection_source"])

        if not allow_web_enrichment:
            rows.append(
                {
                    "resolved_entity_id": row.resolved_entity_id,
                    "facility_id": row.unique_id,
                    "primary_url": primary_url,
                    "primary_domain": primary_domain,
                    "verification_source": verification_source,
                    "page_status": "demo_safe",
                    "page_title": "",
                    "meta_description": "",
                    "website_excerpt": "",
                    "social_link_count": 0,
                    "contact_signal_count": 0,
                    "capability_mentions": 0,
                    "name_match_score": 0.0,
                    "domain_matches_dataset": bool(primary_domain and primary_domain == row.website_domain),
                }
            )
            continue

        try:
            page = scrape_public_page(primary_url)
        except Exception:
            page = {
                "url": primary_url,
                "domain": primary_domain,
                "status": "unavailable",
                "page_title": "",
                "meta_description": "",
                "text_excerpt": "",
                "social_links": 0,
                "contact_signals": 0,
            }
        page_text = " ".join(
            [
                _safe_text(page.get("page_title")),
                _safe_text(page.get("meta_description")),
                _safe_text(page.get("text_excerpt")),
            ]
        )
        capability_mentions = _count_term_hits(page_text, _capability_terms(pd.Series(row._asdict())))
        name_match_score = SequenceMatcher(None, _safe_text(row.normalized_name), _normalized_name(page_text)).ratio()
        rows.append(
            {
                "resolved_entity_id": row.resolved_entity_id,
                "facility_id": row.unique_id,
                "primary_url": primary_url,
                "primary_domain": primary_domain or _safe_text(page.get("domain")),
                "verification_source": verification_source,
                "page_status": _safe_text(page.get("status")) or "unavailable",
                "page_title": _safe_text(page.get("page_title")),
                "meta_description": _safe_text(page.get("meta_description")),
                "website_excerpt": _safe_text(page.get("text_excerpt")),
                "social_link_count": int(page.get("social_links", 0) or 0),
                "contact_signal_count": int(page.get("contact_signals", 0) or 0),
                "capability_mentions": capability_mentions,
                "name_match_score": round(name_match_score, 2),
                "domain_matches_dataset": bool(primary_domain and primary_domain == row.website_domain),
            }
        )

    if not rows:
        return _empty_website_signals()
    return pd.DataFrame(rows, columns=WEBSITE_SIGNAL_COLUMNS)


def build_trust_reviews(
    facilities: pd.DataFrame,
    search_results: pd.DataFrame,
    website_signals: pd.DataFrame,
    source: str,
) -> pd.DataFrame:
    if facilities.empty:
        return _empty_trust_reviews()

    canonical = (
        facilities.sort_values(["urgency_support", "dataset_trust_score"], ascending=False)
        .drop_duplicates("resolved_entity_id")
        .copy()
    )
    canonical = canonical.rename(columns={"unique_id": "facility_id", "name": "facility_name"})
    selected_search = search_results[search_results["selected"]].copy() if not search_results.empty else _empty_search_results()
    if selected_search.empty:
        selected_search = _empty_search_results()

    merged = canonical.merge(selected_search, on=["resolved_entity_id", "facility_id", "facility_name"], how="left")
    merged = merged.merge(website_signals, on=["resolved_entity_id", "facility_id"], how="left")

    rows: list[dict[str, Any]] = []
    for row in merged.to_dict(orient="records"):
        distinct_social_count = _parse_number(row.get("distinct_social_media_presence_count"))
        affiliated_staff_presence = _parse_number(row.get("affiliated_staff_presence"))
        custom_logo_presence = _parse_number(row.get("custom_logo_presence"))
        capability_mentions = int(_parse_number(row.get("capability_mentions")))
        contact_signal_count = int(_parse_number(row.get("contact_signal_count")))
        social_link_count = int(_parse_number(row.get("social_link_count")))
        name_match_score = _parse_number(row.get("name_match_score"))
        entity_match_confidence = _parse_number(row.get("entity_match_confidence"))
        entity_record_count = max(int(_parse_number(row.get("entity_record_count"))) or 0, 1)
        evidence_count = _parse_number(row.get("evidence_count"))
        freshness_signal = _parse_number(row.get("freshness_signal"))
        domain_matches_dataset = bool(row.get("domain_matches_dataset")) if pd.notna(row.get("domain_matches_dataset")) else False

        dataset_social_score = min(
            28.0,
            distinct_social_count * 6
            + affiliated_staff_presence * 8
            + custom_logo_presence * 5,
        )
        website_signal_score = min(
            38.0,
            capability_mentions * 5
            + contact_signal_count * 3
            + social_link_count * 2
            + name_match_score * 15
            + (8 if domain_matches_dataset else 0),
        )
        resolution_signal_score = max(
            0.0,
            min(
                18.0,
                entity_match_confidence * 12
                + min(entity_record_count, 3) * 2
                - (5 if row.get("duplicate_review_required") else 0),
            ),
        )
        freshness_signal_score = min(
            16.0,
            freshness_signal
            + (4 if row.get("page_status") == "ok" else 0)
            + (2 if row.get("selection_source") == "dataset_url" else 0),
        )
        trust_score_v2 = min(
            100.0,
            dataset_social_score
            + website_signal_score
            + resolution_signal_score
            + freshness_signal_score
            + evidence_count * 1.5,
        )

        if source == "fallback":
            website_verification_status = "demo-safe scaffold"
        elif row.get("page_status") == "ok" and row.get("name_match_score", 0) >= 0.55:
            website_verification_status = "verified" if row.get("selection_source") == "dataset_url" else "search-assisted"
        elif row.get("result_url"):
            website_verification_status = "review required"
        else:
            website_verification_status = "website unavailable"

        review_status = _facility_confidence_label(trust_score_v2)
        risk_flags: list[str] = []
        if row.get("duplicate_review_required"):
            risk_flags.append("entity match requires review")
        if website_verification_status in {"review required", "website unavailable"}:
            risk_flags.append(website_verification_status)
        if row.get("page_status") not in {"ok", "demo_safe", "", None}:
            risk_flags.append("website scrape incomplete")
        if social_link_count == 0 and distinct_social_count == 0:
            risk_flags.append("social proof is sparse")
        if evidence_count < 3:
            risk_flags.append("dataset evidence is sparse")

        rows.append(
            {
                "resolved_entity_id": row.get("resolved_entity_id", ""),
                "facility_id": row.get("facility_id", ""),
                "facility_name": row.get("facility_name", ""),
                "canonical_name": row.get("canonical_name", ""),
                "entity_record_count": entity_record_count,
                "entity_match_confidence": float(entity_match_confidence),
                "entity_match_reasons": _safe_text(row.get("entity_match_reasons")),
                "duplicate_review_required": bool(row.get("duplicate_review_required", False)),
                "search_query": _safe_text(row.get("search_query")),
                "selection_source": _safe_text(row.get("selection_source")) or "unavailable",
                "website_verification_status": website_verification_status,
                "primary_url": _safe_text(row.get("primary_url") or row.get("result_url")),
                "primary_domain": _safe_text(row.get("primary_domain") or row.get("result_domain")),
                "website_excerpt": _safe_text(row.get("website_excerpt"))[:280],
                "social_link_count": social_link_count,
                "contact_signal_count": contact_signal_count,
                "capability_mentions": capability_mentions,
                "name_match_score": float(name_match_score),
                "dataset_social_score": round(dataset_social_score, 1),
                "website_signal_score": round(website_signal_score, 1),
                "resolution_signal_score": round(resolution_signal_score, 1),
                "freshness_signal_score": round(freshness_signal_score, 1),
                "trust_score_v2": round(trust_score_v2, 1),
                "review_status": review_status,
                "risk_flags": "; ".join(dict.fromkeys(flag for flag in risk_flags if flag)),
            }
        )

    if not rows:
        return _empty_trust_reviews()
    return pd.DataFrame(rows, columns=TRUST_REVIEW_COLUMNS)


def _attach_artifacts(
    df: pd.DataFrame,
    source: str,
    trust_reviews: pd.DataFrame,
    search_results: pd.DataFrame,
    website_signals: pd.DataFrame,
    entity_index_source: str,
    scoring_source: str,
) -> pd.DataFrame:
    tagged = _tag_source(df, source)
    tagged.attrs["trust_reviews"] = trust_reviews
    tagged.attrs["search_results"] = search_results
    tagged.attrs["website_signals"] = website_signals
    tagged.attrs["entity_index_source"] = entity_index_source
    tagged.attrs["scoring_source"] = scoring_source
    return tagged


def _build_facility_review_frame(
    base: pd.DataFrame,
    source: str,
    confidence_threshold: float,
    allow_web_enrichment: bool,
) -> pd.DataFrame:
    cleaned = _clean_facility_candidates(base)
    scoring_source = _scoring_cache_source(cleaned)
    resolved, entity_index_source = _resolve_entity_frame(cleaned)
    search_results = search_facility_sources(resolved, allow_search=allow_web_enrichment)
    website_signals = collect_website_signals(resolved, search_results, allow_web_enrichment=allow_web_enrichment)
    trust_reviews = build_trust_reviews(resolved, search_results, website_signals, source=source)

    final = resolved.merge(
        trust_reviews[
            [
                "resolved_entity_id",
                "selection_source",
                "website_verification_status",
                "primary_url",
                "primary_domain",
                "website_excerpt",
                "social_link_count",
                "contact_signal_count",
                "capability_mentions",
                "name_match_score",
                "trust_score_v2",
                "review_status",
                "risk_flags",
            ]
        ].rename(columns={"risk_flags": "trust_risk_flags"}),
        on="resolved_entity_id",
        how="left",
    )
    final["trust_score"] = final["trust_score_v2"].fillna(final["dataset_trust_score"])
    final["confidence_label"] = final["review_status"].fillna(final["confidence_label"])
    final["urgency_support"] = (final["capability_fit"] * 0.4 + final["trust_score"] * 0.6).clip(0, 100)
    final["risk_flags"] = final.apply(
        lambda row: "; ".join(
            dict.fromkeys(
                part
                for part in [_safe_text(row.get("risk_flags")), _safe_text(row.get("trust_risk_flags"))]
                if part
            )
        ),
        axis=1,
    )
    final = final.drop(columns=["trust_risk_flags"])

    threshold_score = confidence_threshold * 100
    filtered = final[final["trust_score"] >= threshold_score].copy()
    if filtered.empty:
        filtered = final.copy()

    filtered = (
        filtered.sort_values(["urgency_support", "trust_score", "capability_fit"], ascending=False)
        .drop_duplicates("resolved_entity_id")
        .head(12)
    )
    entity_ids = filtered["resolved_entity_id"].dropna().unique().tolist()
    filtered_reviews = trust_reviews[trust_reviews["resolved_entity_id"].isin(entity_ids)].copy()
    filtered_search = search_results[search_results["resolved_entity_id"].isin(entity_ids)].copy()
    filtered_signals = website_signals[website_signals["resolved_entity_id"].isin(entity_ids)].copy()
    return _attach_artifacts(
        filtered,
        source,
        filtered_reviews,
        filtered_search,
        filtered_signals,
        entity_index_source,
        scoring_source,
    )


def _facility_select_list(table_alias: str = "") -> str:
    return f"""
      {table_alias}unique_id,
      {table_alias}name,
      {table_alias}address_city,
      {table_alias}address_stateOrRegion,
      {table_alias}address_zipOrPostcode,
      {table_alias}address_country,
      {table_alias}specialties,
      {table_alias}procedure,
      {table_alias}equipment,
      {table_alias}capability,
      {table_alias}description,
      {table_alias}source_urls,
      {table_alias}distinct_social_media_presence_count,
      {table_alias}affiliated_staff_presence,
      {table_alias}custom_logo_presence,
      {table_alias}numberDoctors,
      {table_alias}capacity,
      {table_alias}recency_of_page_update,
      {table_alias}latitude,
      {table_alias}longitude
    """


def _source_row_fingerprint_sql(table_alias: str = "") -> str:
    expressions: list[str] = []
    for column in SOURCE_ROW_FINGERPRINT_COLUMNS:
        if column == "source_urls":
            expression = f"""
            case
              when trim(cast({table_alias}source_urls as string)) like '[%'
                then coalesce(get_json_object(cast({table_alias}source_urls as string), '$[0]'), cast({table_alias}source_urls as string))
              else cast({table_alias}source_urls as string)
            end
            """
        elif column == "description":
            expression = f"left(cast({table_alias}description as string), 2000)"
        else:
            expression = f"cast({table_alias}{column} as string)"
        expressions.append(f"coalesce({expression}, '')")
    return f"sha1(concat_ws('||', {', '.join(expressions)}))"


def _facility_candidate_sql(
    mission_type: str,
    state_clause: str,
    district_clause: str,
    *,
    use_entity_index: bool,
    use_scoring_cache: bool,
) -> str:
    entity_table = entity_index_table_name()
    if use_entity_index and not entity_table:
        return ""

    score_table = scoring_table_name()
    if use_scoring_cache and not score_table:
        use_scoring_cache = False

    table_alias = "f." if use_entity_index or use_scoring_cache else ""
    keyword_filter = _keyword_sql(mission_type, table_alias)
    candidate_seed_score = _candidate_seed_score_sql(table_alias)
    select_list = _facility_select_list(table_alias)
    joins: list[str] = []
    if use_entity_index:
        select_list = (
            select_list
            + f""",
      ei.resolved_entity_id,
      ei.canonical_name,
      ei.entity_record_count,
      ei.entity_match_confidence,
      ei.entity_match_reasons,
      ei.duplicate_review_required,
      ei.entity_search_text,
      ei.source_row_fingerprint,
      ei.entity_index_version
    """
        )
        joins.append(
            f"""
    left join {entity_table} ei
      on cast(f.unique_id as string) = ei.facility_id
      and ei.entity_index_version = '{ENTITY_INDEX_VERSION}'
      and ei.source_row_fingerprint = {_source_row_fingerprint_sql("f.")}
    """
        )
    if use_scoring_cache:
        select_list = (
            select_list
            + f""",
      sc.scoring_version,
      sc.candidate_seed_score as cached_candidate_seed_score,
      sc.evidence_count as cached_evidence_count,
      sc.capability_fit as cached_capability_fit,
      sc.dataset_trust_score as cached_dataset_trust_score,
      sc.freshness_signal as cached_freshness_signal,
      sc.confidence_label as cached_confidence_label,
      sc.risk_flags as cached_score_risk_flags,
      sc.source_row_fingerprint as scoring_source_row_fingerprint
    """
        )
        joins.append(
            f"""
    left join {score_table} sc
      on cast(f.unique_id as string) = sc.facility_id
      and sc.scoring_version = '{SCORING_VERSION}'
      and sc.source_row_fingerprint = {_source_row_fingerprint_sql("f.")}
    """
        )

    if use_entity_index or use_scoring_cache:
        from_clause = f"""
    from {CATALOG}.{SCHEMA}.facilities f
    {''.join(joins)}
        """
        candidate_seed_select = f"coalesce(sc.candidate_seed_score, {candidate_seed_score})" if use_scoring_cache else candidate_seed_score
    else:
        from_clause = f"from {CATALOG}.{SCHEMA}.facilities"
        candidate_seed_select = candidate_seed_score

    return f"""
    select
      {select_list},
      {candidate_seed_select} as candidate_seed_score
    {from_clause}
    where ({state_clause})
      and ({district_clause})
      and coalesce(lower({table_alias}address_country), '') like '%india%'
      and ({keyword_filter})
    order by candidate_seed_score desc, coalesce({table_alias}name, '') asc, coalesce({table_alias}unique_id, '') asc
    limit {FACILITY_CANDIDATE_WINDOW}
    """


def get_facility_candidates(
    mission_type: str,
    state_filter: str,
    district_filter: str,
    confidence_threshold: float,
) -> pd.DataFrame:
    parameters: dict[str, object] = {}
    state_clause = "1 = 1"
    if state_filter:
        state_clause = _state_filter_clause(["address_stateOrRegion"], state_filter, parameters)

    district_clause = "1 = 1"
    if district_filter:
        district_clause = (
            "coalesce(lower(address_city), '') like lower(:district_filter) or "
            "coalesce(lower(address_zipOrPostcode), '') like lower(:district_filter)"
        )
        parameters["district_filter"] = f"%{district_filter}%"

    aliased_state_clause = state_clause.replace("address_stateOrRegion", "f.address_stateOrRegion")
    aliased_district_clause = district_clause.replace("address_city", "f.address_city").replace(
        "address_zipOrPostcode", "f.address_zipOrPostcode"
    )
    score_cache_enabled = bool(scoring_table_name())
    attempts = [
        (True, score_cache_enabled, aliased_state_clause, aliased_district_clause),
    ]
    if score_cache_enabled:
        attempts.append((True, False, aliased_state_clause, aliased_district_clause))
        attempts.append((False, True, aliased_state_clause, aliased_district_clause))
    attempts.append((False, False, state_clause, district_clause))
    raw = pd.DataFrame()
    for use_entity_index, use_scoring_cache, attempt_state_clause, attempt_district_clause in attempts:
        sql = _facility_candidate_sql(
            mission_type,
            attempt_state_clause,
            attempt_district_clause,
            use_entity_index=use_entity_index,
            use_scoring_cache=use_scoring_cache,
        )
        if not sql:
            continue
        raw = run_sql(sql, parameters=parameters)
        if not raw.empty:
            break
    if raw.empty:
        return _build_facility_review_frame(
            _fallback_facilities(state_filter),
            source="fallback",
            confidence_threshold=confidence_threshold,
            allow_web_enrichment=False,
        )

    live = _build_facility_review_frame(
        raw,
        source="live",
        confidence_threshold=confidence_threshold,
        allow_web_enrichment=True,
    )
    if not live.empty:
        return live
    return _build_facility_review_frame(
        _fallback_facilities(state_filter),
        source="fallback",
        confidence_threshold=confidence_threshold,
        allow_web_enrichment=False,
    )


def build_evidence_rows(df: pd.DataFrame, trust_reviews: pd.DataFrame | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for row in df.itertuples(index=False):
        sources = _source_urls(getattr(row, "source_urls", ""))
        source_url = sources[0] if sources else _safe_text(getattr(row, "primary_url", ""))
        claims = {
            "specialties": getattr(row, "specialties", ""),
            "procedure": getattr(row, "procedure", ""),
            "equipment": getattr(row, "equipment", ""),
            "capability": getattr(row, "capability", ""),
            "description": getattr(row, "description", ""),
        }
        for claim_type, evidence in claims.items():
            if _non_empty_text(evidence):
                rows.append(
                    {
                        "facility_id": str(getattr(row, "unique_id", "")),
                        "facility_name": getattr(row, "name", ""),
                        "claim_type": claim_type,
                        "evidence": str(evidence),
                        "source_url": source_url,
                    }
                )

    review_frame = trust_reviews if trust_reviews is not None else df.attrs.get("trust_reviews")
    if isinstance(review_frame, pd.DataFrame) and not review_frame.empty:
        for review in review_frame.itertuples(index=False):
            if _non_empty_text(review.website_excerpt):
                rows.append(
                    {
                        "facility_id": str(review.facility_id),
                        "facility_name": review.facility_name,
                        "claim_type": "website_excerpt",
                        "evidence": review.website_excerpt,
                        "source_url": review.primary_url,
                    }
                )
            if int(review.entity_record_count) > 1:
                rows.append(
                    {
                        "facility_id": str(review.facility_id),
                        "facility_name": review.facility_name,
                        "claim_type": "entity_resolution",
                        "evidence": (
                            f"Merged {int(review.entity_record_count)} similar rows with "
                            f"match confidence {float(review.entity_match_confidence):.2f}; "
                            f"{review.entity_match_reasons}"
                        ),
                        "source_url": review.primary_url,
                    }
                )

    if not rows:
        return pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"])
    return pd.DataFrame(rows)


def build_district_evidence_rows(top_district: dict[str, Any] | None) -> pd.DataFrame:
    if not top_district:
        return pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"])

    district = _safe_text(top_district.get("district")) or "unknown district"
    state = _safe_text(top_district.get("state")) or "unknown state"
    district_id = f"district:{_location_key(district)}:{_state_key(state)}"
    district_name = f"{district}, {state}".strip(", ")
    rows: list[dict[str, Any]] = []

    nfhs_summary = _safe_text(top_district.get("nfhs_need_summary"))
    if nfhs_summary and "unavailable" not in nfhs_summary.lower():
        rows.append(
            {
                "facility_id": district_id,
                "facility_name": district_name,
                "claim_type": "nfhs_need_summary",
                "evidence": nfhs_summary,
                "source_url": _unity_catalog_uri("nfhs_5_district_health_indicators"),
            }
        )

    density_context = _safe_text(top_district.get("facility_density_context"))
    if density_context and "unavailable" not in density_context.lower():
        rows.append(
            {
                "facility_id": district_id,
                "facility_name": district_name,
                "claim_type": "facility_density_context",
                "evidence": density_context,
                "source_url": (
                    f"{_unity_catalog_uri('facilities')} + "
                    f"{_unity_catalog_uri('india_post_pincode_directory')}"
                ),
            }
        )

    if not rows:
        return pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"])
    return pd.DataFrame(rows)


def save_user_decision(
    run_id: str,
    mission_type: str,
    district: str,
    facility_id: str,
    decision: str,
    note: str,
    metadata: dict[str, Any],
) -> bool:
    return save_user_decision_record(
        run_id=run_id,
        mission_type=mission_type,
        district=district,
        facility_id=facility_id,
        decision=decision,
        note=note,
        metadata_json=json.dumps(metadata),
    )


def _district_confidence_label(evidence_score: float) -> str:
    if evidence_score >= 75:
        return "High Confidence"
    if evidence_score >= 50:
        return "Moderate Confidence"
    return "Weak Evidence"


def _facility_confidence_label(score: float) -> str:
    if score >= 75:
        return "High Confidence"
    if score >= 50:
        return "Moderate Confidence"
    return "Weak Evidence"


def _facility_risk_flags(row: pd.Series) -> str:
    flags: list[str] = []
    if _non_empty_text(row.get("address_country")) and not bool(row.get("country_in_scope", True)):
        flags.append("country scope needs review")
    if not row.get("source_urls"):
        flags.append("missing source url")
    if row.get("evidence_count", 0) < 3:
        flags.append("sparse evidence")
    if row.get("dataset_trust_score", 0) < 50:
        flags.append("dataset trust proxy below preferred threshold")
    return "; ".join(flags)
