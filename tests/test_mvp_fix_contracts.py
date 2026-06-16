from __future__ import annotations

import pandas as pd

from src.agent import reasoning
from src.agent import tools
from src.agent.tools import build_evidence_rows
from src.db import lakebase


def _frame(rows: list[dict[str, object]], source: str) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df.attrs["source"] = source
    return df


def _district_citation_rows() -> list[dict[str, object]]:
    return [
        {
            "facility_id": "district:nagpur:maharashtra",
            "facility_name": "Nagpur, Maharashtra",
            "claim_type": "nfhs_need_summary",
            "evidence": "NFHS: child underweight 34.0%, insurance coverage 24.0%.",
            "source_url": "unity-catalog://databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.nfhs_5_district_health_indicators",
        },
        {
            "facility_id": "district:nagpur:maharashtra",
            "facility_name": "Nagpur, Maharashtra",
            "claim_type": "facility_density_context",
            "evidence": "7 mission-matching facility row(s) mapped for this district.",
            "source_url": "unity-catalog://databricks_virtue_foundation_dataset_dais_2026.virtue_foundation_dataset.facilities",
        },
    ]


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


def test_run_agent_returns_mission_control_v5_3_contract(monkeypatch) -> None:
    monkeypatch.setenv("CARE_CONVOY_ENABLE_LLM_SUMMARY", "true")
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
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
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
    captured_prompts: list[str] = []

    monkeypatch.setattr(reasoning, "_llm_summary", lambda prompt: captured_prompts.append(prompt) or None)

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
        "Supply Mapper",
        "Facility Scout",
        "Trust Verifier",
        "Evidence Auditor",
        "Mission Strategist",
        "Supervisor",
    ]
    assert result["board_summary"].startswith("Mission Control v5.3")
    assert board[-1]["verdict"] == "shortlist with monitoring"
    assert board[-1]["confidence"] == "High Confidence"
    assert result["confidence_label"] == "High Confidence"
    assert result["summary_source"] == "deterministic fallback"
    assert [agent["gate"] for agent in result["mission_control_trace"]] == ["pass"] * 7
    assert result["mission_packet"]["version"] == "v5.3"
    assert result["mission_packet"]["action_state"] == "shortlist"
    assert result["mission_packet"]["lead_district"] == "Nagpur"
    assert result["mission_packet"]["lead_anchor"] == "Wockhardt Hospital Nagpur"
    assert result["mission_packet"]["population_context_status"].startswith("Population denominator planned")
    assert captured_prompts
    assert "'gate': 'pass'" in captured_prompts[0]
    assert "Mission packet action: shortlist" in captured_prompts[0]
    assert "Return 4 to 6 bullets" in captured_prompts[0]


def test_run_agent_uses_trust_review_for_lead_facility_entity(monkeypatch) -> None:
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
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
                "nfhs_need_summary": "NFHS: child underweight 34.0%, insurance coverage 24.0%.",
                "risk_flags": "",
            }
        ],
        "live",
    )
    facilities = _frame(
        [
            {
                "unique_id": "lead-facility",
                "name": "Lead Hospital",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 88.0,
                "trust_score": 85.0,
                "confidence_label": "High Confidence",
                "specialties": "maternal health",
                "procedure": "c-section",
                "equipment": "nicu",
                "capability": "24/7 emergency obstetrics",
                "description": "Lead specialty care anchor",
                "source_urls": '["https://example.org/lead"]',
                "resolved_entity_id": "entity-lead",
                "entity_record_count": 1,
                "website_verification_status": "verified",
                "selection_source": "dataset_url",
                "primary_url": "https://example.org/lead",
                "website_excerpt": "Lead care website.",
                "risk_flags": "",
            },
            {
                "unique_id": "backup-facility",
                "name": "Backup Clinic",
                "address_city": "Nagpur",
                "address_stateOrRegion": "Maharashtra",
                "capability_fit": 70.0,
                "trust_score": 30.0,
                "confidence_label": "Weak Evidence",
                "specialties": "maternal health",
                "procedure": "",
                "equipment": "",
                "capability": "Referral support",
                "description": "Backup anchor",
                "source_urls": '["https://example.org/backup"]',
                "resolved_entity_id": "entity-backup",
                "entity_record_count": 1,
                "website_verification_status": "review required",
                "selection_source": "dataset_url",
                "primary_url": "https://example.org/backup",
                "website_excerpt": "Backup website.",
                "risk_flags": "",
            },
        ],
        "live",
    )
    facilities.attrs["trust_reviews"] = pd.DataFrame(
        [
            {
                "resolved_entity_id": "entity-backup",
                "facility_id": "backup-facility",
                "facility_name": "Backup Clinic",
                "website_verification_status": "review required",
                "trust_score_v2": 30.0,
                "review_status": "Weak Evidence",
                "duplicate_review_required": False,
                "primary_url": "https://example.org/backup",
                "website_excerpt": "Backup website.",
                "entity_record_count": 1,
            },
            {
                "resolved_entity_id": "entity-lead",
                "facility_id": "lead-facility",
                "facility_name": "Lead Hospital",
                "website_verification_status": "verified",
                "trust_score_v2": 85.0,
                "review_status": "High Confidence",
                "duplicate_review_required": False,
                "primary_url": "https://example.org/lead",
                "website_excerpt": "Lead care website.",
                "entity_record_count": 1,
            },
        ]
    )
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

    trust_gate = next(agent for agent in result["mission_control_trace"] if agent["agent"] == "Trust Verifier")
    assert trust_gate["gate"] == "pass"
    assert "trust review score is 85.0" in trust_gate["evidence"]


def test_run_agent_requires_review_for_ambiguous_density(monkeypatch) -> None:
    districts = _frame(
        [
            {
                "district": "Nagpur",
                "state": "Maharashtra",
                "need_score": 82.0,
                "coverage_gap": 64.0,
                "facility_count": 0,
                "mission_facility_count": 0,
                "evidence_score": 71.0,
                "priority_score": 79.0,
                "uncertainty_label": "Moderate Confidence",
                "density_confidence_label": "Data Ambiguous",
                "density_matched": False,
                "facility_density_context": "No district-level facility density row matched; treat supply gap as ambiguous.",
                "risk_flags": "facility density under review",
            }
        ],
        "live",
    )
    trust_reviews = pd.DataFrame(
        [
            {
                "facility_id": "facility-1",
                "facility_name": "Wockhardt Hospital Nagpur",
                "website_verification_status": "verified",
                "trust_score_v2": 82.0,
                "review_status": "High Confidence",
                "duplicate_review_required": False,
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

    supply_gate = next(agent for agent in result["mission_control_trace"] if agent["agent"] == "Supply Mapper")
    assert supply_gate["gate"] == "review"
    assert result["review_board"][-1]["verdict"] == "shortlist after review"
    assert result["mission_packet"]["action_state"] == "verify first"
    assert "Facility-density context is ambiguous" in " ".join(result["warnings"])


def test_low_capability_fit_keeps_board_and_packet_in_review(monkeypatch) -> None:
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
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
                "risk_flags": "",
            }
        ],
        "live",
    )
    trust_reviews = pd.DataFrame(
        [
            {
                "facility_id": "facility-1",
                "facility_name": "Wockhardt Hospital Nagpur",
                "website_verification_status": "verified",
                "trust_score_v2": 90.0,
                "review_status": "High Confidence",
                "duplicate_review_required": False,
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
                "capability_fit": 40.0,
                "trust_score": 90.0,
                "confidence_label": "Weak Evidence",
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

    facility_gate = next(agent for agent in result["mission_control_trace"] if agent["agent"] == "Facility Scout")
    assert facility_gate["gate"] == "review"
    assert result["review_board"][-1]["verdict"] == "shortlist after review"
    assert result["mission_packet"]["action_state"] == "verify first"
    assert "shortlist with monitoring" not in result["board_summary"]


def test_weak_non_final_gate_stays_review_not_hold() -> None:
    board = [
        {
            "agent": "Need Scout",
            "role": "Ranks district demand.",
            "verdict": "district priority supported",
            "confidence": "Weak Evidence",
            "evidence": "Need evidence is sparse.",
            "handoff": "Review district context.",
        },
        {
            "agent": "Supervisor",
            "role": "Resolves final state.",
            "verdict": "shortlist with monitoring",
            "confidence": "High Confidence",
            "evidence": "Final board state supports shortlist.",
            "handoff": "Persist after operator review.",
        },
    ]

    trace = reasoning._build_mission_control_trace(board)

    assert trace[0]["gate"] == "review"
    assert trace[1]["gate"] == "pass"
    assert reasoning._mission_action_from_trace(trace) == "verify first"


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
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
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
    assert "Lead anchor has no citation rows" in " ".join(result["warnings"])
    assert result["mission_control_trace"][-1]["gate"] == "block"
    assert result["mission_packet"]["action_state"] == "hold"
    assert result["mission_packet"]["citation_status"] == "Lead anchor citations unavailable"


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
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
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
                "facility_count": 7,
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
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

    assert board[4]["verdict"] == "no citations available"
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
                "facility_count": 7,
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
            },
        top_facility={
            "unique_id": "facility-1",
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
            _district_citation_rows()
            + [
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

    assert board[3]["verdict"] == "trust check needs review"
    assert "0.0" in board[3]["evidence"]
    assert board[-1]["verdict"] == "shortlist after review"
    assert board[-1]["confidence"] == "Weak Evidence"


def test_review_board_blocks_when_lead_anchor_lacks_citations() -> None:
    board, board_summary = reasoning._build_review_board(
        mission_label="Maternal Health",
        top_district={
            "district": "Nagpur",
            "state": "Maharashtra",
            "need_score": 82.0,
            "evidence_score": 71.0,
            "uncertainty_label": "Moderate Confidence",
            "facility_count": 7,
            "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
            "density_confidence_label": "Moderate Confidence",
            "density_matched": True,
        },
        top_facility={
            "unique_id": "lead-facility",
            "name": "Lead Hospital",
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
        citations=pd.DataFrame(
            _district_citation_rows()
            + [
                {
                    "facility_id": "backup-facility",
                    "facility_name": "Backup Hospital",
                    "claim_type": "description",
                    "evidence": "Backup specialty care anchor",
                    "source_url": "https://example.org/backup",
                }
            ]
        ),
        warnings=[],
    )

    assert board[4]["verdict"] == "lead anchor citation gaps found"
    assert board[-1]["verdict"] == "hold for evidence"
    assert "hold for evidence" in board_summary


def test_review_board_falls_back_from_nan_trust_score_and_parses_string_false() -> None:
    board, _ = reasoning._build_review_board(
        mission_label="Maternal Health",
        top_district={
            "district": "Nagpur",
            "state": "Maharashtra",
                "need_score": 82.0,
                "evidence_score": 71.0,
                "uncertainty_label": "Moderate Confidence",
                "facility_count": 7,
                "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
                "density_confidence_label": "Moderate Confidence",
                "density_matched": True,
            },
        top_facility={
            "unique_id": "facility-1",
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
            _district_citation_rows()
            + [
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

    assert board[3]["verdict"] == "trust check passed"
    assert "82.0" in board[3]["evidence"]
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


def test_build_district_evidence_rows_cites_nfhs_and_density_sources() -> None:
    rows = tools.build_district_evidence_rows(
        {
            "district": "Nagpur",
            "state": "Maharashtra",
            "nfhs_need_summary": "NFHS: child underweight 34.0%, insurance coverage 24.0%.",
            "facility_density_context": "7 mission-matching facility row(s) mapped for this district.",
        }
    )

    assert set(rows["claim_type"]) == {"nfhs_need_summary", "facility_density_context"}
    assert rows["source_url"].str.startswith("unity-catalog://").all()
    assert rows["facility_id"].eq("district:nagpur:maharashtra").all()


def test_get_district_priorities_adds_nfhs_and_facility_density_context(monkeypatch) -> None:
    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        if "nfhs_5_district_health_indicators" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nagpur",
                        "state": "Maharashtra",
                        "child_underweight_pct": 34.0,
                        "insurance_pct": 24.0,
                        "institutional_birth_pct": 68.0,
                        "high_bp_pct": 18.0,
                    },
                    {
                        "district": "Nashik",
                        "state": "Maharashtra",
                        "child_underweight_pct": 22.0,
                        "insurance_pct": 60.0,
                        "institutional_birth_pct": 92.0,
                        "high_bp_pct": 11.0,
                    },
                ]
            )
        if "india_post_pincode_directory" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nagpur",
                        "state": "Maharashtra",
                        "facility_count": 2,
                        "mission_facility_count": 1,
                        "latitude": 21.14,
                        "longitude": 79.08,
                    },
                    {
                        "district": "Nashik",
                        "state": "Maharashtra",
                        "facility_count": 12,
                        "mission_facility_count": 6,
                        "latitude": 19.99,
                        "longitude": 73.78,
                    },
                ]
            )
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    districts = tools.get_district_priorities(
        mission_type="maternal_health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
    )

    nagpur = districts[districts["district"] == "Nagpur"].iloc[0]
    assert districts.attrs["source"] == "live"
    assert int(nagpur["facility_count"]) == 2
    assert int(nagpur["mission_facility_count"]) == 1
    assert "NFHS" in nagpur["nfhs_need_summary"]
    assert "mission-matching" in nagpur["facility_density_context"]
    assert nagpur["density_confidence_label"] == "Moderate Confidence"
    assert float(nagpur["coverage_gap"]) > 0


def test_get_district_priorities_normalizes_live_state_alias_for_density(monkeypatch) -> None:
    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        if "nfhs_5_district_health_indicators" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nandurbar",
                        "state": "Maharastra",
                        "child_underweight_pct": "38.2 ",
                        "insurance_pct": "18.4",
                        "institutional_birth_pct": "72.1",
                        "high_bp_pct": "16.0",
                    }
                ]
            )
        if "india_post_pincode_directory" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nandurbar",
                        "state": "Maharashtra",
                        "facility_count": 4,
                        "mission_facility_count": 1,
                        "latitude": 21.37,
                        "longitude": 74.24,
                    }
                ]
            )
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    districts = tools.get_district_priorities(
        mission_type="maternal_health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
    )

    district = districts.iloc[0]
    assert districts.attrs["source"] == "live"
    assert district["state"] == "Maharashtra"
    assert int(district["facility_count"]) == 4
    assert int(district["mission_facility_count"]) == 1
    assert district["density_confidence_label"] == "Moderate Confidence"


def test_get_district_priorities_labels_missing_density_as_ambiguous(monkeypatch) -> None:
    def fake_run_sql(statement: str, timeout_seconds: int = 20, parameters: dict[str, object] | None = None) -> pd.DataFrame:
        if "nfhs_5_district_health_indicators" in statement:
            return pd.DataFrame(
                [
                    {
                        "district": "Nagpur",
                        "state": "Maharashtra",
                        "child_underweight_pct": 34.0,
                        "insurance_pct": 24.0,
                        "institutional_birth_pct": 68.0,
                        "high_bp_pct": 18.0,
                    }
                ]
            )
        return pd.DataFrame()

    monkeypatch.setattr(tools, "run_sql", fake_run_sql)

    districts = tools.get_district_priorities(
        mission_type="maternal_health",
        state_filter="Maharashtra",
        district_filter="",
        confidence_threshold=0.25,
    )

    district = districts.iloc[0]
    assert districts.attrs["source"] == "live"
    assert int(district["facility_count"]) == 0
    assert district["density_confidence_label"] == "Data Ambiguous"
    assert "facility density under review" in district["risk_flags"]


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


def test_save_agent_feedback_record_returns_false_on_boundary_error(monkeypatch) -> None:
    def raise_bootstrap() -> None:
        raise RuntimeError("must be owner of table")

    monkeypatch.setattr(lakebase, "ensure_tables", raise_bootstrap)

    saved = lakebase.save_agent_feedback_record(
        run_id="run-1",
        mission_type="Maternal Health",
        district="Nagpur",
        facility_id="facility-1",
        recommended_action="needs verification",
        confidence_label="Moderate Confidence",
        provenance="Live sources",
        feedback_json="{}",
    )

    assert saved is False
