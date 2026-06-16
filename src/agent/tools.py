from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from difflib import SequenceMatcher
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
_FACILITY_STOPWORDS = {
    "and",
    "care",
    "centre",
    "center",
    "clinic",
    "foundation",
    "health",
    "healthcare",
    "hospital",
    "india",
    "institute",
    "medical",
    "trust",
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
        return [part.strip() for part in raw.split(",") if part.strip()]

    if isinstance(parsed, list):
        return [str(item).strip() for item in parsed if str(item).strip()]
    if isinstance(parsed, str) and parsed.strip():
        return [parsed.strip()]
    return []


def _primary_domain(value: Any) -> str:
    for url in _source_urls(value):
        domain = urlparse(url).netloc.lower()
        if domain:
            return domain
    return ""


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
    return df


def _entity_match(left: pd.Series, right: pd.Series) -> tuple[float, list[str]]:
    reasons: list[str] = []
    score = 0.0

    left_domain = _safe_text(left.get("website_domain"))
    right_domain = _safe_text(right.get("website_domain"))
    if left_domain and right_domain and left_domain == right_domain:
        score += 0.52
        reasons.append("shared website domain")

    name_similarity = SequenceMatcher(None, _safe_text(left.get("normalized_name")), _safe_text(right.get("normalized_name"))).ratio()
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

    return min(score, 1.0), reasons


def resolve_facility_entities(df: pd.DataFrame) -> pd.DataFrame:
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

    for left_index in range(len(resolved)):
        for right_index in range(left_index + 1, len(resolved)):
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
            "resolved_entity_id": f"entity-{cluster_number:02d}",
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
) -> pd.DataFrame:
    tagged = _tag_source(df, source)
    tagged.attrs["trust_reviews"] = trust_reviews
    tagged.attrs["search_results"] = search_results
    tagged.attrs["website_signals"] = website_signals
    return tagged


def _build_facility_review_frame(
    base: pd.DataFrame,
    source: str,
    confidence_threshold: float,
    allow_web_enrichment: bool,
) -> pd.DataFrame:
    cleaned = _clean_facility_candidates(base)
    resolved = resolve_facility_entities(cleaned)
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
    return _attach_artifacts(filtered, source, filtered_reviews, filtered_search, filtered_signals)


def get_facility_candidates(
    mission_type: str,
    state_filter: str,
    district_filter: str,
    confidence_threshold: float,
) -> pd.DataFrame:
    keyword_filter = _keyword_sql(mission_type)
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

    sql = f"""
    select
      unique_id,
      name,
      address_city,
      address_stateOrRegion,
      address_zipOrPostcode,
      address_country,
      specialties,
      procedure,
      equipment,
      capability,
      description,
      source_urls,
      distinct_social_media_presence_count,
      affiliated_staff_presence,
      custom_logo_presence,
      numberDoctors,
      capacity,
      recency_of_page_update,
      latitude,
      longitude
    from {CATALOG}.{SCHEMA}.facilities
    where {state_clause}
      and ({district_clause})
      and coalesce(lower(address_country), '') like '%india%'
      and ({keyword_filter})
    limit 40
    """
    raw = run_sql(sql, parameters=parameters)
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
