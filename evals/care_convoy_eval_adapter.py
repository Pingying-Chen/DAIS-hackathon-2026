from __future__ import annotations

from typing import Any

import pandas as pd

from src.agent.reasoning import run_agent


def _records(frame: Any, columns: list[str], limit: int) -> list[dict[str, Any]]:
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return []
    available_columns = [column for column in columns if column in frame.columns]
    return frame[available_columns].head(limit).fillna("").to_dict(orient="records")


def _board_items(items: Any) -> list[dict[str, str]]:
    if not isinstance(items, list):
        return []
    return [
        {
            "agent": str(item.get("agent", "")),
            "verdict": str(item.get("verdict", "")),
            "confidence": str(item.get("confidence", "")),
            "gate": str(item.get("gate", "")),
            "evidence": str(item.get("evidence", "")),
        }
        for item in items
        if isinstance(item, dict)
    ]


def evaluate_agent(
    mission_type: str,
    mission_label: str,
    state_filter: str,
    district_filter: str,
    confidence_threshold: float,
    run_id: str,
) -> dict[str, Any]:
    result = run_agent(
        mission_type=mission_type,
        mission_label=mission_label,
        state_filter=state_filter,
        district_filter=district_filter,
        confidence_threshold=confidence_threshold,
        run_id=run_id,
    )
    packet = result.get("mission_packet", {})
    return {
        "version": packet.get("version", ""),
        "summary": result.get("summary", ""),
        "summary_source": result.get("summary_source", ""),
        "board_summary": result.get("board_summary", ""),
        "mission_packet": packet,
        "confidence_label": result.get("confidence_label", ""),
        "provenance": result.get("provenance", ""),
        "warning_count": len(result.get("warnings", [])),
        "warnings": result.get("warnings", []),
        "review_board": _board_items(result.get("mission_control_trace", [])),
        "districts": _records(
            result.get("districts"),
            ["district", "state", "priority_score", "uncertainty_label", "risk_flags"],
            3,
        ),
        "facilities": _records(
            result.get("facilities"),
            ["unique_id", "name", "address_city", "confidence_label", "trust_score", "risk_flags"],
            3,
        ),
        "citations": _records(
            result.get("citations"),
            ["facility_id", "facility_name", "claim_type", "evidence", "source_url"],
            8,
        ),
        "observability": result.get("observability", {}),
    }
