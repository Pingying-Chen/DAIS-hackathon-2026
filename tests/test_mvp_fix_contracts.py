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
    assert list(rows.columns) == ["created_at", "mission_type", "district", "facility_id", "decision", "note"]
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
