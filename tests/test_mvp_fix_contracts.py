from __future__ import annotations

import pandas as pd

from src.agent import reasoning
from src.agent.tools import build_evidence_rows
from src.db import lakebase


def _frame(rows: list[dict[str, object]], source: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.attrs["source"] = source
    return df


def test_run_agent_reports_mixed_sources_truthfully(monkeypatch) -> None:
    districts = _frame(
        [
            {
                "district": "Nagpur",
                "state": "Maharashtra",
                "need_score": 82.0,
                "coverage_gap": 64.0,
                "facility_count": 7,
                "evidence_score": 71.0,
                "priority_score": 79.0,
                "uncertainty_label": "Moderate Confidence",
                "risk_flags": "district join under review",
            }
        ],
        "fallback",
    )
    facilities = _frame(
        [
            {
                "unique_id": "facility-1",
                "name": "Wockhardt Hospital Nagpur",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 100.0,
                "confidence_label": "High Confidence",
                "specialties": "maternal health",
                "procedure": "c-section",
                "equipment": "nicu",
                "capability": "24/7 emergency obstetrics",
                "description": "Specialty care anchor",
                "source_urls": '["https://example.org/facility"]',
            }
        ],
        "live",
    )
    citations = pd.DataFrame(
        [
            {
                "facility_id": "facility-1",
                "facility_name": "Wockhardt Hospital Nagpur",
                "claim_type": "description",
                "evidence": "Specialty care anchor",
                "source_url": "https://example.org/facility",
            }
        ]
    )

    monkeypatch.setattr(reasoning, "get_district_priorities", lambda *args, **kwargs: districts)
    monkeypatch.setattr(reasoning, "get_facility_candidates", lambda *args, **kwargs: facilities)
    monkeypatch.setattr(reasoning, "build_evidence_rows", lambda df, trust_reviews=None: citations)
    monkeypatch.setattr(reasoning, "_llm_summary", lambda prompt: None)

    result = reasoning.run_agent(
        mission_type="maternal_health",
        mission_label="Maternal Health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
        run_id="test-run",
    )

    assert result["provenance"] == "Mixed sources: fallback districts + live facilities"
    assert "District prioritization is using fallback data until a stronger live join is in place." in result["warnings"]
    assert "Facility ranking is using demo-safe fallback data because no live anchor rows were returned." not in result["warnings"]


def test_run_agent_returns_review_board_v3_contract(monkeypatch) -> None:
    districts = _frame(
        [
            {
                "district": "Nagpur",
                "state": "Maharashtra",
                "need_score": 82.0,
                "coverage_gap": 64.0,
                "facility_count": 7,
                "evidence_score": 71.0,
                "priority_score": 79.0,
                "uncertainty_label": "Moderate Confidence",
                "risk_flags": "district join under review",
            }
        ],
        "live",
    )
    trust_reviews = pd.DataFrame(
        [
            {
                "resolved_entity_id": "entity-01",
                "facility_id": "facility-1",
                "facility_name": "Wockhardt Hospital Nagpur",
                "canonical_name": "Wockhardt Hospital Nagpur",
                "entity_record_count": 1,
                "entity_match_confidence": 1.0,
                "entity_match_reasons": "single row candidate",
                "duplicate_review_required": False,
                "search_query": "Wockhardt Hospital Nagpur India hospital",
                "selection_source": "dataset_url",
                "website_verification_status": "verified",
                "primary_url": "https://example.org/facility",
                "primary_domain": "example.org",
                "website_excerpt": "Emergency obstetrics and neonatal care.",
                "social_link_count": 2,
                "contact_signal_count": 1,
                "capability_mentions": 3,
                "name_match_score": 0.9,
                "dataset_social_score": 20.0,
                "website_signal_score": 30.0,
                "resolution_signal_score": 14.0,
                "freshness_signal_score": 8.0,
                "trust_score_v2": 82.0,
                "review_status": "High Confidence",
                "risk_flags": "",
            }
        ]
    )
    facilities = _frame(
        [
            {
                "unique_id": "facility-1",
                "name": "Wockhardt Hospital Nagpur",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 88.0,
                "trust_score": 82.0,
                "confidence_label": "High Confidence",
                "specialties": "maternal health",
                "procedure": "c-section",
                "equipment": "nicu",
                "capability": "24/7 emergency obstetrics",
                "description": "Specialty care anchor",
                "source_urls": '["https://example.org/facility"]',
                "resolved_entity_id": "entity-01",
                "entity_record_count": 1,
                "website_verification_status": "verified",
                "selection_source": "dataset_url",
                "primary_url": "https://example.org/facility",
                "website_excerpt": "Emergency obstetrics and neonatal care.",
                "risk_flags": "",
            }
        ],
        "live",
    )
    facilities.attrs["trust_reviews"] = trust_reviews
    facilities.attrs["search_results"] = pd.DataFrame()

    monkeypatch.setattr(reasoning, "get_district_priorities", lambda *args, **kwargs: districts)
    monkeypatch.setattr(reasoning, "get_facility_candidates", lambda *args, **kwargs: facilities)
    monkeypatch.setattr(reasoning, "_llm_summary", lambda prompt: None)

    result = reasoning.run_agent(
        mission_type="maternal_health",
        mission_label="Maternal Health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
        run_id="test-run",
    )

    board = result["review_board"]
    assert [agent["agent"] for agent in board] == [
        "Need Scout",
        "Facility Scout",
        "Trust Verifier",
        "Evidence Auditor",
        "Referral Strategist",
        "Supervisor",
    ]
    assert result["board_summary"].startswith("Convoy Review Board v3")
    assert board[-1]["verdict"] == "shortlist with monitoring"
    assert board[-1]["confidence"] == "High Confidence"
    assert result["confidence_label"] == "High Confidence"
    assert result["summary_source"] == "deterministic fallback"


def test_run_agent_uses_board_confidence_when_citations_are_missing(monkeypatch) -> None:
    districts = _frame(
        [
            {
                "district": "Nagpur",
                "state": "Maharashtra",
                "need_score": 82.0,
                "coverage_gap": 64.0,
                "facility_count": 7,
                "evidence_score": 71.0,
                "priority_score": 79.0,
                "uncertainty_label": "Moderate Confidence",
                "risk_flags": "",
            }
        ],
        "live",
    )
    facilities = _frame(
        [
            {
                "unique_id": "facility-1",
                "name": "Wockhardt Hospital Nagpur",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 88.0,
                "trust_score": 82.0,
                "confidence_label": "High Confidence",
                "specialties": "",
                "procedure": "",
                "equipment": "",
                "capability": "",
                "description": "",
                "source_urls": "",
                "resolved_entity_id": "entity-01",
                "entity_record_count": 1,
                "website_verification_status": "verified",
                "risk_flags": "",
            }
        ],
        "live",
    )
    facilities.attrs["trust_reviews"] = pd.DataFrame()

    monkeypatch.setattr(reasoning, "get_district_priorities", lambda *args, **kwargs: districts)
    monkeypatch.setattr(reasoning, "get_facility_candidates", lambda *args, **kwargs: facilities)
    monkeypatch.setattr(reasoning, "build_evidence_rows", lambda df, trust_reviews=None: pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"]))
    monkeypatch.setattr(reasoning, "_llm_summary", lambda prompt: None)

    result = reasoning.run_agent(
        mission_type="maternal_health",
        mission_label="Maternal Health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
        run_id="test-run",
    )

    assert result["review_board"][-1]["verdict"] == "hold for evidence"
    assert result["confidence_label"] == "Weak Evidence"
    assert "No facility citation rows were available" in " ".join(result["warnings"])


def test_run_agent_does_not_warn_for_string_false_duplicate_review(monkeypatch) -> None:
    districts = _frame(
        [
            {
                "district": "Nagpur",
                "state": "Maharashtra",
                "need_score": 82.0,
                "coverage_gap": 64.0,
                "facility_count": 7,
                "evidence_score": 71.0,
                "priority_score": 79.0,
                "uncertainty_label": "Moderate Confidence",
                "risk_flags": "",
            }
        ],
        "live",
    )
    trust_reviews = pd.DataFrame(
        [
            {
                "resolved_entity_id": "entity-01",
                "facility_id": "facility-1",
                "facility_name": "Wockhardt Hospital Nagpur",
                "website_verification_status": "verified",
                "trust_score_v2": 82.0,
                "review_status": "High Confidence",
                "duplicate_review_required": "False",
                "primary_url": "https://example.org/facility",
                "website_excerpt": "Emergency obstetrics and neonatal care.",
                "entity_record_count": 1,
            }
        ]
    )
    facilities = _frame(
        [
            {
                "unique_id": "facility-1",
                "name": "Wockhardt Hospital Nagpur",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 88.0,
                "trust_score": 82.0,
                "confidence_label": "High Confidence",
                "specialties": "maternal health",
                "procedure": "c-section",
                "equipment": "nicu",
                "capability": "24/7 emergency obstetrics",
                "description": "Specialty care anchor",
                "source_urls": '["https://example.org/facility"]',
                "resolved_entity_id": "entity-01",
                "entity_record_count": 1,
                "website_verification_status": "verified",
                "risk_flags": "",
            }
        ],
        "live",
    )
    facilities.attrs["trust_reviews"] = trust_reviews
    facilities.attrs["search_results"] = pd.DataFrame()

    monkeypatch.setattr(reasoning, "get_district_priorities", lambda *args, **kwargs: districts)
    monkeypatch.setattr(reasoning, "get_facility_candidates", lambda *args, **kwargs: facilities)
    monkeypatch.setattr(reasoning, "_llm_summary", lambda prompt: None)

    result = reasoning.run_agent(
        mission_type="maternal_health",
        mission_label="Maternal Health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
        run_id="test-run",
    )

    assert "Some facility rows were clustered as possible duplicates and still need a human entity-resolution check." not in result["warnings"]
    assert result["review_board"][-1]["verdict"] == "shortlist with monitoring"


def test_review_board_holds_when_no_citations() -> None:
    board, board_summary = reasoning._build_review_board(
        mission_label="Maternal Health",
        top_district={
            "district": "Nagpur",
            "state": "Maharashtra",
            "need_score": 82.0,
            "evidence_score": 71.0,
            "uncertainty_label": "Moderate Confidence",
        },
        top_facility={
            "name": "Wockhardt Hospital Nagpur",
            "address_city": "Nagpur",
            "capability_fit": 88.0,
            "trust_score": 82.0,
            "confidence_label": "High Confidence",
            "website_verification_status": "verified",
        },
        top_trust_review={
            "website_verification_status": "verified",
            "trust_score_v2": 82.0,
            "review_status": "High Confidence",
            "duplicate_review_required": False,
        },
        citations=pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"]),
        warnings=[],
    )

    assert board[3]["verdict"] == "no citations available"
    assert board[-1]["verdict"] == "hold for evidence"
    assert board[-1]["confidence"] == "Weak Evidence"
    assert "hold for evidence" in board_summary


def test_review_board_preserves_zero_trust_review_score() -> None:
    board, _ = reasoning._build_review_board(
        mission_label="Maternal Health",
        top_district={
            "district": "Nagpur",
            "state": "Maharashtra",
            "need_score": 82.0,
            "evidence_score": 71.0,
            "uncertainty_label": "Moderate Confidence",
        },
        top_facility={
            "name": "Wockhardt Hospital Nagpur",
            "address_city": "Nagpur",
            "capability_fit": 88.0,
            "trust_score": 82.0,
            "confidence_label": "High Confidence",
            "website_verification_status": "verified",
        },
        top_trust_review={
            "website_verification_status": "verified",
            "trust_score_v2": 0.0,
            "review_status": "Weak Evidence",
            "duplicate_review_required": False,
        },
        citations=pd.DataFrame(
            [
                {
                    "facility_id": "facility-1",
                    "facility_name": "Wockhardt Hospital Nagpur",
                    "claim_type": "description",
                    "evidence": "Specialty care anchor",
                    "source_url": "https://example.org/facility",
                }
            ]
        ),
        warnings=[],
    )

    assert board[2]["verdict"] == "trust check needs review"
    assert "0.0" in board[2]["evidence"]
    assert board[-1]["verdict"] == "shortlist after review"
    assert board[-1]["confidence"] == "Weak Evidence"


def test_review_board_falls_back_from_nan_trust_score_and_parses_string_false() -> None:
    board, _ = reasoning._build_review_board(
        mission_label="Maternal Health",
        top_district={
            "district": "Nagpur",
            "state": "Maharashtra",
            "need_score": 82.0,
            "evidence_score": 71.0,
            "uncertainty_label": "Moderate Confidence",
        },
        top_facility={
            "name": "Wockhardt Hospital Nagpur",
            "address_city": "Nagpur",
            "capability_fit": 88.0,
            "trust_score": 82.0,
            "confidence_label": "High Confidence",
            "website_verification_status": "verified",
        },
        top_trust_review={
            "website_verification_status": "verified",
            "trust_score_v2": float("nan"),
            "review_status": "High Confidence",
            "duplicate_review_required": "False",
        },
        citations=pd.DataFrame(
            [
                {
                    "facility_id": "facility-1",
                    "facility_name": "Wockhardt Hospital Nagpur",
                    "claim_type": "description",
                    "evidence": "Specialty care anchor",
                    "source_url": "https://example.org/facility",
                }
            ]
        ),
        warnings=[],
    )

    assert board[2]["verdict"] == "trust check passed"
    assert "82.0" in board[2]["evidence"]
    assert board[-1]["verdict"] == "shortlist with monitoring"
    assert board[-1]["confidence"] == "High Confidence"


def test_missing_source_count_handles_null_and_whitespace_urls() -> None:
    citations = pd.DataFrame(
        [
            {"source_url": None},
            {"source_url": "   "},
            {"source_url": "https://example.org/facility"},
        ]
    )

    assert reasoning._missing_source_count(citations) == 2


def test_build_evidence_rows_uses_clean_url_from_json_array() -> None:
    df = pd.DataFrame(
        [
            {
                "unique_id": "facility-1",
                "name": "Anchor Hospital",
                "specialties": "maternal health",
                "procedure": "c-section",
                "equipment": "nicu",
                "capability": "24/7 emergency obstetrics",
                "description": "Specialty care anchor",
                "source_urls": '["https://example.org/a","https://example.org/b"]',
            }
        ]
    )

    rows = build_evidence_rows(df)

    assert not rows.empty
    assert set(rows["source_url"]) == {"https://example.org/a"}


def test_list_user_decisions_returns_empty_frame_on_boundary_error(monkeypatch) -> None:
    def raise_bootstrap() -> None:
        raise RuntimeError("must be owner of table")

    monkeypatch.setattr(lakebase, "ensure_tables", raise_bootstrap)

    rows = lakebase.list_user_decisions(limit=5)

    assert rows.empty
    assert list(rows.columns) == ["created_at", "mission_type", "district", "facility_id", "decision", "note", "metadata_json"]
    assert "Lakebase shortlist is temporarily unavailable" in rows.attrs["error"]


def test_save_user_decision_record_returns_false_on_boundary_error(monkeypatch) -> None:
    def raise_bootstrap() -> None:
        raise RuntimeError("must be owner of table")

    monkeypatch.setattr(lakebase, "ensure_tables", raise_bootstrap)

    saved = lakebase.save_user_decision_record(
        run_id="run-1",
        mission_type="Maternal Health",
        district="Nagpur",
        facility_id="facility-1",
        decision="approved",
        note="ship it",
        metadata_json="{}",
    )

    assert saved is False
