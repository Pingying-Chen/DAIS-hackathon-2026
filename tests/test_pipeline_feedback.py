from __future__ import annotations

import pandas as pd

from src.agent import tools
from src.pipelines import entity_index
from src.pipelines import joined_dataset
from src.pipelines.feedback import append_only_frame


def _facility_rows() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "unique_id": "facility-1",
                "name": "Sunrise Surgical Hospital",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "440001",
                "address_country": "India",
                "specialties": "Maternal health",
                "procedure": "Surgery",
                "equipment": "NICU",
                "capability": "Emergency obstetrics",
                "description": "High-acuity women's hospital.",
                "source_urls": '["https://sunrise.example.org"]',
                "distinct_social_media_presence_count": 3,
                "affiliated_staff_presence": 1,
                "custom_logo_presence": 1,
                "numberDoctors": 20,
                "capacity": 120,
                "recency_of_page_update": "2026-05-01",
                "latitude": 21.145,
                "longitude": 79.088,
            },
            {
                "unique_id": "facility-2",
                "name": "Regional Access Clinic",
                "address_city": "Aurangabad",
                "address_stateOrRegion": "Maharashtra",
                "address_zipOrPostcode": "431001",
                "address_country": "India",
                "specialties": "General access",
                "procedure": "",
                "equipment": "Basic diagnostics",
                "capability": "Referral support",
                "description": "Small clinic.",
                "source_urls": "",
                "distinct_social_media_presence_count": 0,
                "affiliated_staff_presence": 0,
                "custom_logo_presence": 0,
                "numberDoctors": 3,
                "capacity": 15,
                "recency_of_page_update": "",
                "latitude": 19.879,
                "longitude": 75.338,
            },
        ]
    )


def test_append_only_frame_filters_existing_fingerprints() -> None:
    candidate = pd.DataFrame(
        [
            {"version": "v1", "facility_id": "facility-1", "source_row_fingerprint": "aaa", "score": 10},
            {"version": "v1", "facility_id": "facility-2", "source_row_fingerprint": "bbb", "score": 20},
        ]
    )
    existing = pd.DataFrame(
        [{"version": "v1", "facility_id": "facility-1", "source_row_fingerprint": "aaa"}]
    )

    append = append_only_frame(candidate, existing, ["version", "facility_id", "source_row_fingerprint"])

    assert append.to_dict(orient="records") == [
        {"version": "v1", "facility_id": "facility-2", "source_row_fingerprint": "bbb", "score": 20}
    ]


def test_build_facility_scoring_frame_has_append_keys_and_scores() -> None:
    scoring = tools.build_facility_scoring_frame(_facility_rows())

    assert list(scoring.columns) == tools.SCORING_COLUMNS
    assert scoring["scoring_version"].eq(tools.SCORING_VERSION).all()
    assert scoring["source_row_fingerprint"].str.len().eq(40).all()
    assert float(scoring.loc[scoring["facility_id"] == "facility-1", "candidate_seed_score"].iloc[0]) > 0


def test_clean_facility_candidates_prefers_cached_scoring_columns() -> None:
    raw = _facility_rows().head(1).copy()
    raw["scoring_version"] = tools.SCORING_VERSION
    raw["cached_candidate_seed_score"] = 999.0
    raw["cached_evidence_count"] = 42
    raw["cached_capability_fit"] = 88.0
    raw["cached_dataset_trust_score"] = 77.0
    raw["cached_freshness_signal"] = 9.0
    raw["cached_confidence_label"] = "High Confidence"
    raw["cached_score_risk_flags"] = "cached score row"

    cleaned = tools._clean_facility_candidates(raw)

    assert cleaned.iloc[0]["candidate_seed_score"] == 999.0
    assert int(cleaned.iloc[0]["evidence_count"]) == 42
    assert cleaned.iloc[0]["confidence_label"] == "High Confidence"
    assert cleaned.iloc[0]["risk_flags"] == "cached score row"
    assert tools._scoring_cache_source(cleaned) == "cached"


def test_facility_candidate_sql_can_join_scoring_cache(monkeypatch) -> None:
    monkeypatch.setenv("SCORING_TABLE", "workspace.default.care_convoy_facility_scoring")

    sql = tools._facility_candidate_sql(
        "surgery",
        "1 = 1",
        "1 = 1",
        use_entity_index=False,
        use_scoring_cache=True,
    )

    assert "workspace.default.care_convoy_facility_scoring" in sql
    assert "sc.scoring_version = 'care-convoy-scoring-v1'" in sql
    assert "coalesce(sc.candidate_seed_score" in sql


def test_joined_facility_table_name_defaults_to_app_ready_table(monkeypatch) -> None:
    monkeypatch.delenv("JOINED_FACILITY_TABLE", raising=False)
    monkeypatch.delenv("JOINED_DISTRICT_TABLE", raising=False)

    assert tools.joined_facility_table_name() == "workspace.default.care_convoy_joined_facility_readiness"
    assert tools.joined_district_table_name() == "workspace.default.care_convoy_joined_district_readiness"
    assert tools.joined_facility_table_name("unsafe.table") == ""
    assert tools.joined_district_table_name("unsafe.table") == ""


def test_joined_dataset_sql_deduplicates_pincode_and_adds_nfhs_context() -> None:
    sql = joined_dataset._create_joined_table_sql("workspace.default.care_convoy_joined_facility_readiness")

    assert "create or replace table workspace.default.care_convoy_joined_facility_readiness" in sql
    assert "pincode_geo as" in sql
    assert "group by regexp_replace(cast(pincode as string), '[^0-9]', '')" in sql
    assert "left join nfhs n" in sql
    assert "has_pincode_join" in sql
    assert "has_nfhs_join" in sql
    assert "source_row_fingerprint" in sql


def test_joined_district_dataset_sql_preserves_all_nfhs_districts() -> None:
    sql = joined_dataset._create_joined_district_table_sql(
        "workspace.default.care_convoy_joined_district_readiness",
        "workspace.default.care_convoy_joined_facility_readiness",
    )

    assert "create or replace table workspace.default.care_convoy_joined_district_readiness" in sql
    assert "from databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators" in sql
    assert "left join facility_density fd" in sql
    assert "maternal_health_facility_count" in sql
    assert "districts with facility density" not in sql


def test_district_priorities_prefer_joined_district_table(monkeypatch) -> None:
    monkeypatch.setenv("JOINED_DISTRICT_TABLE", "workspace.default.care_convoy_joined_district_readiness")
    calls: list[str] = []

    def fake_run_sql(statement: str, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(statement)
        if "care_convoy_joined_district_readiness" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nagpur",
                        "state": "Maharashtra",
                        "child_underweight_pct": 34.0,
                        "insurance_pct": 24.0,
                        "institutional_birth_pct": 68.0,
                        "high_bp_pct": 18.0,
                        "facility_count": 142,
                        "mission_facility_count": 0,
                        "latitude": 21.14,
                        "longitude": 79.08,
                        "density_matched": True,
                    }
                ]
            )
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    districts = tools.get_district_priorities("maternal_health", "Maharashtra", "Nagpur", 0.25)

    assert districts.attrs["source"] == "live"
    assert districts.attrs["district_source_table"] == "workspace.default.care_convoy_joined_district_readiness"
    assert int(districts.iloc[0]["facility_count"]) == 142
    assert all("nfhs_5_district_health_indicators" not in statement for statement in calls)


def test_facility_candidates_broaden_live_query_before_demo_fallback(monkeypatch) -> None:
    monkeypatch.setenv("JOINED_FACILITY_TABLE", "workspace.default.care_convoy_joined_facility_readiness")
    monkeypatch.setenv("ENTITY_INDEX_TABLE", "")
    monkeypatch.setenv("SCORING_TABLE", "")
    calls: list[str] = []

    def fake_run_sql(statement: str, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(statement)
        if "maternal" not in statement and "care_convoy_joined_facility_readiness" in statement:
            frame = _facility_rows().head(1).copy()
            frame["source_row_count"] = 10088
            return frame
        return pd.DataFrame()

    def fake_build(
        frame: pd.DataFrame,
        source: str,
        confidence_threshold: float,
        allow_web_enrichment: bool,
    ) -> pd.DataFrame:
        result = frame.copy()
        result.attrs["source"] = source
        result.attrs["source_row_count"] = int(frame.get("source_row_count", pd.Series([len(frame)])).iloc[0])
        return result

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)
    monkeypatch.setattr(tools, "_build_facility_review_frame", fake_build)

    result = tools.get_facility_candidates("maternal_health", "Maharashtra", "Nagpur", 0.25)

    assert result.attrs["source"] == "live"
    assert result.attrs["facility_source_label"] == "joined"
    assert result.attrs["keyword_requirement"] == "location"
    assert result.attrs["source_row_count"] == 10088
    assert any("maternal" in statement for statement in calls)
    assert any("maternal" not in statement for statement in calls)


def test_facility_candidates_keep_entity_only_fallback_when_scoring_cache_misses(monkeypatch) -> None:
    monkeypatch.setenv("SCORING_TABLE", "workspace.default.care_convoy_facility_scoring")
    monkeypatch.setenv("ENTITY_INDEX_TABLE", "workspace.default.care_convoy_facility_entity_index")
    calls: list[str] = []

    def fake_run_sql(statement: str, *args: object, **kwargs: object) -> pd.DataFrame:
        calls.append(statement)
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    tools.get_facility_candidates("surgery", "Maharashtra", "", 0.25)

    assert any("care_convoy_facility_scoring" in statement for statement in calls)
    assert any(
        "care_convoy_facility_entity_index" in statement and "care_convoy_facility_scoring" not in statement
        for statement in calls
    )


def test_entity_existing_rows_query_uses_slim_lookup_projection() -> None:
    sql = entity_index._existing_rows_sql("workspace.default.care_convoy_facility_entity_index")

    assert "cast('' as string) as entity_search_text" in sql
    assert "where entity_index_version = 'care-convoy-entity-index-v1'" in sql


def test_entity_resolution_feedback_skips_exact_and_reuses_similar_mapping() -> None:
    existing = tools.build_entity_index_frame(_facility_rows().head(1))
    changed = _facility_rows().head(1).copy()
    changed.loc[changed.index[0], "description"] = "Updated source description."
    candidate = tools.build_entity_index_frame(pd.concat([_facility_rows().head(1), changed, _facility_rows().tail(1)]))

    append = tools.build_entity_resolution_feedback_frame(candidate, existing)
    reused = append[append["facility_id"] == "facility-1"].iloc[0]

    assert len(append) == 2
    assert reused["resolved_entity_id"] == existing.iloc[0]["resolved_entity_id"]
    assert "feedback loop reused cached mapping" in reused["entity_match_reasons"]
    assert set(append["facility_id"]) == {"facility-1", "facility-2"}
