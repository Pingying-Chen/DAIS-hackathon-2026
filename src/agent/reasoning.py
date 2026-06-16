from __future__ import annotations

import os
from math import isnan
from typing import Any

import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

from src.agent.prompts import DEVHUB_LAKEBASE_SUBAGENT_PROMPT
from src.agent.tracing import trace_agent_run, tracing_status
from src.agent.tools import (
    build_district_evidence_rows,
    build_evidence_rows,
    get_district_priorities,
    get_facility_candidates,
)

MISSION_CONTROL_VERSION = "v5.3"
DISTRICT_CLAIM_TYPES = {"nfhs_need_summary", "facility_density_context"}


def _deterministic_summary(
    mission_label: str,
    state_filter: str,
    top_district: dict[str, Any] | None,
    top_facility: dict[str, Any] | None,
    top_trust_review: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    if top_district is None or top_facility is None:
        return "\n".join(
            [
                f"- Need: {mission_label}",
                "- Evidence: not strong enough",
                "- Action: use demo-safe fallback",
                "- Next: review before saving",
            ]
        )

    items = [
        f"- Need: {top_district['district']}, {top_district['state']}",
        f"- Anchor: {top_facility['name']}",
        f"- Fit: {top_facility['capability_fit']:.0f}",
        f"- Confidence: {top_facility['confidence_label']}",
    ]
    if top_trust_review is not None:
        items.append(f"- Website: {top_trust_review['website_verification_status']}")
    if warnings:
        items.append(f"- Caution: {warnings[0]}")
    return "\n".join(items[:6])


def _llm_summary(prompt: str) -> str | None:
    endpoint = os.environ.get("PRIMARY_LLM_ENDPOINT", "")
    if not endpoint:
        return None

    try:
        profile = os.environ.get("DATABRICKS_CONFIG_PROFILE") or os.environ.get("DATABRICKS_PROFILE")
        client = WorkspaceClient(profile=profile) if profile else WorkspaceClient()
        response = client.serving_endpoints.query(
            name=endpoint,
            messages=[
                ChatMessage(role=ChatMessageRole.SYSTEM, content=DEVHUB_LAKEBASE_SUBAGENT_PROMPT),
                ChatMessage(role=ChatMessageRole.USER, content=prompt),
            ],
            max_tokens=350,
            temperature=0.2,
        )
    except Exception:
        return None

    choices = getattr(response, "choices", None) or []
    if not choices:
        return None
    first = choices[0]
    message = getattr(first, "message", None)
    return getattr(message, "content", None)


def _result_source(df: Any) -> str:
    if getattr(df, "attrs", None) is None:
        return "unknown"
    return str(df.attrs.get("source", "unknown"))


def _provenance_label(district_source: str, facility_source: str) -> str:
    if district_source == "live" and facility_source == "live":
        return "Live Databricks SQL query with Trust Desk v2 public-web verification"
    if district_source == "fallback" and facility_source == "fallback":
        return "Demo-safe fallback scaffold with dataset-only trust review"
    return f"Mixed sources: {district_source} districts + {facility_source} facilities"


def _frame_attr(frame: Any, key: str) -> Any:
    attrs = getattr(frame, "attrs", None)
    if attrs is None:
        return None
    return attrs.get(key)


def _value(row: dict[str, Any] | None, key: str, fallback: Any = "") -> Any:
    if row is None:
        return fallback
    value = row.get(key, fallback)
    if value is None:
        return fallback
    return value


def _numeric_value(value: Any) -> float | None:
    if value is None:
        return None
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if isnan(score):
        return None
    return score


def _score(row: dict[str, Any] | None, key: str) -> float:
    score = _numeric_value(_value(row, key, 0))
    return score if score is not None else 0.0


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _series_has_truthy(values: Any) -> bool:
    return any(_truthy(value) for value in values)


def _density_needs_review(top_district: dict[str, Any] | None, density_context: str) -> bool:
    if top_district is None:
        return True

    density_matched = _value(top_district, "density_matched", None)
    if density_matched is not None and not _truthy(density_matched):
        return True

    density_confidence = str(_value(top_district, "density_confidence_label", "")).strip().lower()
    if density_confidence in {"data ambiguous", "weak evidence"}:
        return True

    risk_flags = str(_value(top_district, "risk_flags", "")).strip().lower()
    risk_markers = ("facility density under review", "density under review", "density ambiguous", "supply gap ambiguous")
    context_markers = ("ambiguous", "unavailable", "not matched")
    return any(marker in risk_flags for marker in risk_markers) or any(marker in density_context.lower() for marker in context_markers)


def _confidence_from_scores(*scores: float) -> str:
    if not scores:
        return "Weak Evidence"
    minimum_score = min(scores)
    if minimum_score >= 75:
        return "High Confidence"
    if minimum_score >= 50:
        return "Moderate Confidence"
    return "Weak Evidence"


def _board_item(agent: str, role: str, verdict: str, confidence: str, evidence: str, handoff: str) -> dict[str, str]:
    return {
        "agent": agent,
        "role": role,
        "verdict": verdict,
        "confidence": confidence,
        "evidence": evidence,
        "handoff": handoff,
    }


def _missing_source_count(citations: Any) -> int:
    citation_count = int(len(citations)) if citations is not None else 0
    if citation_count == 0:
        return 0
    if "source_url" not in citations:
        return citation_count
    source_urls = citations["source_url"].fillna("").astype(str).str.strip()
    return int(source_urls.eq("").sum())


def _empty_citation_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=["facility_id", "facility_name", "claim_type", "evidence", "source_url"])


def _citation_frame(citations: Any) -> pd.DataFrame:
    if isinstance(citations, pd.DataFrame):
        return citations
    return _empty_citation_frame()


def _lead_citation_frame(citations: Any, top_facility: dict[str, Any] | None) -> pd.DataFrame:
    frame = _citation_frame(citations)
    if frame.empty or top_facility is None:
        return _empty_citation_frame()

    mask = pd.Series(False, index=frame.index)
    lead_id = str(_value(top_facility, "unique_id", "")).strip()
    lead_name = str(_value(top_facility, "name", "")).strip()
    if lead_id and "facility_id" in frame:
        mask = mask | frame["facility_id"].fillna("").astype(str).str.strip().eq(lead_id)
    if lead_name and "facility_name" in frame:
        mask = mask | frame["facility_name"].fillna("").astype(str).str.strip().eq(lead_name)
    return frame.loc[mask].copy()


def _district_citation_frame(citations: Any) -> pd.DataFrame:
    frame = _citation_frame(citations)
    if frame.empty or "claim_type" not in frame:
        return _empty_citation_frame()
    return frame[frame["claim_type"].isin(DISTRICT_CLAIM_TYPES)].copy()


def _district_citations_required(top_district: dict[str, Any] | None) -> bool:
    if top_district is None:
        return False
    district_claims = [
        str(_value(top_district, "nfhs_need_summary", "")).strip().lower(),
        str(_value(top_district, "facility_density_context", "")).strip().lower(),
    ]
    return any(claim and "unavailable" not in claim for claim in district_claims)


def _matching_trust_review(trust_reviews: Any, top_facility: dict[str, Any] | None) -> dict[str, Any] | None:
    if top_facility is None or trust_reviews is None or getattr(trust_reviews, "empty", True):
        return None

    frame = trust_reviews
    lead_entity = str(_value(top_facility, "resolved_entity_id", "")).strip()
    lead_id = str(_value(top_facility, "unique_id", "")).strip()
    lead_name = str(_value(top_facility, "name", "")).strip()

    for column, value in [
        ("resolved_entity_id", lead_entity),
        ("facility_id", lead_id),
        ("facility_name", lead_name),
    ]:
        if value and column in frame:
            matched = frame[frame[column].fillna("").astype(str).str.strip().eq(value)]
            if not matched.empty:
                return matched.iloc[0].to_dict()
    return frame.iloc[0].to_dict()


def _build_review_board(
    mission_label: str,
    top_district: dict[str, Any] | None,
    top_facility: dict[str, Any] | None,
    top_trust_review: dict[str, Any] | None,
    citations: Any,
    warnings: list[str],
) -> tuple[list[dict[str, str]], str]:
    citation_count = int(len(citations)) if citations is not None else 0
    missing_source_count = 0
    if citation_count:
        missing_source_count = _missing_source_count(citations)
    lead_citations = _lead_citation_frame(citations, top_facility)
    lead_citation_count = int(len(lead_citations))
    district_citations = _district_citation_frame(citations)
    district_citation_count = int(len(district_citations))
    district_citations_required = _district_citations_required(top_district)

    need_score = _score(top_district, "need_score")
    evidence_score = _score(top_district, "evidence_score")
    capability_fit = _score(top_facility, "capability_fit")
    trust_score = _score(top_facility, "trust_score")
    trust_review_score = trust_score
    if top_trust_review is not None:
        explicit_trust_score = _numeric_value(top_trust_review.get("trust_score_v2"))
        if explicit_trust_score is not None:
            trust_review_score = explicit_trust_score

    district_name = _value(top_district, "district", "No district")
    district_state = _value(top_district, "state", "")
    density_context = _value(top_district, "facility_density_context", "Facility density context unavailable")
    facility_count = _score(top_district, "facility_count")
    facility_name = _value(top_facility, "name", "No facility")
    facility_city = _value(top_facility, "address_city", "")
    website_status = _value(top_trust_review, "website_verification_status", _value(top_facility, "website_verification_status", "not checked"))
    duplicate_required = _truthy(_value(top_trust_review, "duplicate_review_required", False))

    need_confidence = _value(top_district, "uncertainty_label", _confidence_from_scores(evidence_score))
    supply_confidence = _value(top_district, "density_confidence_label", _value(top_district, "uncertainty_label", _confidence_from_scores(evidence_score)))
    facility_confidence = _value(top_facility, "confidence_label", _confidence_from_scores(capability_fit, trust_score))
    trust_confidence = _value(top_trust_review, "review_status", _confidence_from_scores(trust_review_score))
    evidence_confidence = "High Confidence"
    if (
        citation_count == 0
        or missing_source_count
        or lead_citation_count == 0
        or (district_citations_required and district_citation_count == 0)
    ):
        evidence_confidence = "Weak Evidence"
    elif citation_count < 3 or warnings:
        evidence_confidence = "Moderate Confidence"

    need_verdict = "district priority supported" if top_district is not None else "no district ready"
    supply_verdict = "supply context supported" if top_district is not None else "no supply context"
    if _density_needs_review(top_district, str(density_context)):
        supply_verdict = "supply context needs review"
    facility_verdict = "candidate anchor ready" if top_facility is not None else "no anchor ready"
    if top_facility is not None and capability_fit < 50:
        facility_verdict = "candidate needs capability review"

    trust_verdict = "trust check passed"
    if top_trust_review is None:
        trust_verdict = "trust check unavailable"
    elif website_status in {"review required", "website unavailable"} or duplicate_required or trust_review_score < 50:
        trust_verdict = "trust check needs review"

    evidence_verdict = "claim-safe"
    if citation_count == 0:
        evidence_verdict = "no citations available"
    elif lead_citation_count == 0:
        evidence_verdict = "lead anchor citation gaps found"
    elif district_citations_required and district_citation_count == 0:
        evidence_verdict = "district citation gaps found"
    elif missing_source_count:
        evidence_verdict = "citation gaps found"
    elif warnings:
        evidence_verdict = "claim-safe with cautions"

    final_confidence = _confidence_from_scores(capability_fit, trust_score, trust_review_score)
    if (
        citation_count == 0
        or lead_citation_count == 0
        or missing_source_count
        or (district_citations_required and district_citation_count == 0)
        or top_district is None
        or top_facility is None
    ):
        final_verdict = "hold for evidence"
        final_confidence = "Weak Evidence"
    elif (
        facility_verdict == "candidate needs capability review"
        or supply_verdict == "supply context needs review"
        or trust_verdict == "trust check needs review"
        or warnings
    ):
        final_verdict = "shortlist after review"
        final_confidence = "Moderate Confidence" if final_confidence == "High Confidence" else final_confidence
    else:
        final_verdict = "shortlist with monitoring"

    board = [
        _board_item(
            "Need Scout",
            "Ranks district demand and coverage gap for the selected mission.",
            need_verdict,
            str(need_confidence),
            f"{district_name}, {district_state} has need {need_score:.1f} and evidence {evidence_score:.1f}.",
            "Send the strongest district context to Facility Scout.",
        ),
        _board_item(
            "Supply Mapper",
            "Checks whether facility density makes the district need operationally meaningful.",
            supply_verdict,
            str(supply_confidence),
            f"{district_name} has {facility_count:.0f} mapped facility row(s). {density_context}",
            "Send supply pressure and density cautions to Facility Scout.",
        ),
        _board_item(
            "Facility Scout",
            "Finds operational referral anchors that match the care mission.",
            facility_verdict,
            str(facility_confidence),
            f"{facility_name} in {facility_city} has capability fit {capability_fit:.1f} and trust {trust_score:.1f}.",
            "Ask Trust Verifier whether this anchor is credible enough to act on.",
        ),
        _board_item(
            "Trust Verifier",
            "Runs entity resolution, website verification, and facility trust scoring.",
            trust_verdict,
            str(trust_confidence),
            f"Website status is {website_status}; trust review score is {trust_review_score:.1f}.",
            "Forward duplicate, website, and social-proof risks to Evidence Auditor.",
        ),
        _board_item(
            "Evidence Auditor",
            "Checks that recommendation claims have citations and visible cautions.",
            evidence_verdict,
            evidence_confidence,
            (
                f"{lead_citation_count} lead anchor citation row(s), "
                f"{district_citation_count} district provenance row(s), "
                f"{missing_source_count} citation row(s) lack a source URL."
            ),
            "Suppress or qualify claims that cannot be cited cleanly.",
        ),
        _board_item(
            "Mission Strategist",
            "Combines need, supply, capability, trust, and evidence into an action recommendation.",
            final_verdict,
            final_confidence,
            f"{mission_label} recommendation weighs district need {need_score:.1f}, capability {capability_fit:.1f}, and trust {trust_score:.1f}.",
            "Prepare the operator-facing decision packet.",
        ),
        _board_item(
            "Supervisor",
            "Routes the board sequence and resolves the final recommendation state.",
            final_verdict,
            final_confidence,
            f"Final board state: {final_verdict} for {facility_name} serving {district_name}.",
            "Persist the shortlist only after the operator accepts the board decision.",
        ),
    ]
    board_summary = (
        f"Mission Control {MISSION_CONTROL_VERSION} recommends {final_verdict} for {facility_name} "
        f"serving {district_name} with {final_confidence}."
    )
    return board, board_summary


def _gate_from_board_item(item: dict[str, str]) -> tuple[str, str]:
    verdict = item.get("verdict", "").lower()
    confidence = item.get("confidence", "").lower()
    if any(token in verdict for token in ["hold", "no ", "block"]):
        return "block", item.get("evidence", "Required evidence is not strong enough to act on.")
    if "weak evidence" in confidence or any(token in verdict for token in ["review", "caution", "gap", "unavailable", "needs"]):
        return "review", item.get("evidence", "This gate needs operator review before action.")
    return "pass", ""


def _mission_action_from_trace(trace: list[dict[str, str]]) -> str:
    gates = [item["gate"] for item in trace]
    if "block" in gates:
        return "hold"
    if "review" in gates:
        return "verify first"
    return "shortlist"


def _build_mission_control_trace(board: list[dict[str, str]]) -> list[dict[str, str]]:
    trace: list[dict[str, str]] = []
    for item in board:
        gate, blocking_reason = _gate_from_board_item(item)
        trace.append(
            {
                **item,
                "gate": gate,
                "blocking_reason": blocking_reason,
            }
        )
    return trace


def _citation_status(
    citations: Any,
    top_facility: dict[str, Any] | None = None,
    top_district: dict[str, Any] | None = None,
) -> str:
    citation_count = int(len(citations)) if citations is not None else 0
    if citation_count == 0:
        return "No citations available"
    lead_citation_count = int(len(_lead_citation_frame(citations, top_facility))) if top_facility is not None else 0
    if top_facility is not None and lead_citation_count == 0:
        return "Lead anchor citations unavailable"
    district_citation_count = int(len(_district_citation_frame(citations)))
    if _district_citations_required(top_district) and district_citation_count == 0:
        return "District provenance unavailable"
    missing_source_count = _missing_source_count(citations)
    if missing_source_count:
        return f"{citation_count} citation row(s), {missing_source_count} missing source URL(s)"
    if top_facility is not None:
        return f"{lead_citation_count} lead anchor citation row(s), {district_citation_count} district provenance row(s)"
    return f"{citation_count} cited evidence row(s)"


def _build_mission_packet(
    *,
    mission_label: str,
    top_district: dict[str, Any] | None,
    facilities: Any,
    trace: list[dict[str, str]],
    citations: Any,
    warnings: list[str],
) -> dict[str, Any]:
    lead_facility = facilities.iloc[0].to_dict() if facilities is not None and not facilities.empty else None
    backup_facility = facilities.iloc[1].to_dict() if facilities is not None and len(facilities) > 1 else None
    supervisor = trace[-1] if trace else {}
    action_state = _mission_action_from_trace(trace)

    if action_state == "shortlist":
        next_action = "Save packet. Monitor evidence."
    elif action_state == "verify first":
        next_action = "Verify anchor before commitment."
    else:
        next_action = "Hold until evidence gaps close."

    if warnings and action_state == "shortlist":
        action_state = "verify first"
        next_action = "Review warnings before saving."

    return {
        "version": MISSION_CONTROL_VERSION,
        "mission_label": mission_label,
        "lead_district": _value(top_district, "district", "No district"),
        "lead_state": _value(top_district, "state", ""),
        "lead_anchor": _value(lead_facility, "name", "No lead anchor"),
        "backup_anchor": _value(backup_facility, "name", "No backup anchor"),
        "action_state": action_state,
        "confidence": supervisor.get("confidence", "Weak Evidence"),
        "board_gate_state": supervisor.get("gate", "block"),
        "citation_status": _citation_status(citations, lead_facility, top_district),
        "nfhs_signals": _value(top_district, "nfhs_need_summary", "NFHS context unavailable"),
        "facility_density_context": _value(top_district, "facility_density_context", "Facility density unavailable"),
        "population_context_status": "Population denominator planned. Not active.",
        "population_total": None,
        "mission_anchors_per_100k": None,
        "next_verification_action": next_action,
        "warning_count": len(warnings),
    }


@trace_agent_run("care_convoy_mission_control_v5_3")
def run_agent(
    mission_type: str,
    mission_label: str,
    state_filter: str,
    district_filter: str,
    confidence_threshold: float,
    run_id: str,
) -> dict[str, Any]:
    districts = get_district_priorities(mission_type, state_filter, district_filter, confidence_threshold)
    facilities = get_facility_candidates(mission_type, state_filter, district_filter, confidence_threshold)
    trust_reviews = _frame_attr(facilities, "trust_reviews")
    search_results = _frame_attr(facilities, "search_results")
    district_source = _result_source(districts)
    facility_source = _result_source(facilities)
    top_district = districts.iloc[0].to_dict() if not districts.empty else None
    top_facility = facilities.iloc[0].to_dict() if not facilities.empty else None
    top_trust_review = _matching_trust_review(trust_reviews, top_facility)
    facility_citations = build_evidence_rows(facilities, trust_reviews)
    district_citations = build_district_evidence_rows(top_district)
    citation_frames = [frame for frame in [facility_citations, district_citations] if not frame.empty]
    citations = pd.concat(citation_frames, ignore_index=True) if citation_frames else _empty_citation_frame()

    warnings: list[str] = []
    if district_source != "live":
        warnings.append("District prioritization is using fallback data until a stronger live join is in place.")
    if facility_source != "live":
        warnings.append("Facility ranking is using demo-safe fallback data because no live anchor rows were returned.")
    if _density_needs_review(top_district, str(_value(top_district, "facility_density_context", ""))):
        warnings.append("Facility-density context is ambiguous for the lead district and needs operator review before saving.")
    if citations.empty:
        warnings.append("No facility citation rows were available, so the board should hold or qualify the recommendation.")
    elif top_facility is not None and _lead_citation_frame(citations, top_facility).empty:
        warnings.append("Lead anchor has no citation rows, so the board should hold the recommendation.")
    if _district_citations_required(top_district) and _district_citation_frame(citations).empty:
        warnings.append("District need or facility-density claims are missing provenance rows.")
    if _missing_source_count(citations):
        warnings.append("Some facility claims do not have source URLs yet and should stay in review.")
    if trust_reviews is not None and not trust_reviews.empty:
        if trust_reviews["website_verification_status"].isin(["website unavailable", "review required"]).any():
            warnings.append("Trust Desk v2 could not fully verify every facility website, so some trust scores remain review-required.")
        if _series_has_truthy(trust_reviews["duplicate_review_required"]):
            warnings.append("Some facility rows were clustered as possible duplicates and still need a human entity-resolution check.")

    review_board, board_summary = _build_review_board(
        mission_label=mission_label,
        top_district=top_district,
        top_facility=top_facility,
        top_trust_review=top_trust_review,
        citations=citations,
        warnings=warnings,
    )
    mission_control_trace = _build_mission_control_trace(review_board)
    mission_packet = _build_mission_packet(
        mission_label=mission_label,
        top_district=top_district,
        facilities=facilities,
        trace=mission_control_trace,
        citations=citations,
        warnings=warnings,
    )

    prompt = (
        f"You are writing a brief for a non-technical Virtue Foundation operations lead.\n"
        f"Mission type: {mission_label}\n"
        f"State filter: {state_filter or 'India'}\n"
        f"Top district: {top_district}\n"
        f"Top facility: {top_facility}\n"
        f"Top trust review: {top_trust_review}\n"
        f"Mission Control {MISSION_CONTROL_VERSION} trace: {mission_control_trace}\n"
        f"Mission packet action: {mission_packet['action_state']}\n"
        f"Warnings: {warnings}\n"
        "Use only supplied evidence. Return 4 to 6 bullets. Keep each bullet under 10 words."
    )
    summary_source = "Databricks model serving"
    summary = _llm_summary(prompt)
    if not summary:
        summary_source = "deterministic fallback"
        summary = _deterministic_summary(
            mission_label=mission_label,
            state_filter=state_filter,
            top_district=top_district,
            top_facility=top_facility,
            top_trust_review=top_trust_review,
            warnings=warnings,
        )

    confidence_label = "Weak Evidence"
    if review_board:
        confidence_label = review_board[-1]["confidence"]
    elif not facilities.empty:
        confidence_label = str(facilities.iloc[0]["confidence_label"])

    provenance = _provenance_label(district_source, facility_source)
    return {
        "run_id": run_id,
        "mission_type": mission_type,
        "mission_label": mission_label,
        "summary": summary,
        "summary_source": summary_source,
        "confidence_label": confidence_label,
        "districts": districts,
        "facilities": facilities,
        "trust_reviews": trust_reviews,
        "search_results": search_results,
        "citations": citations,
        "review_board": review_board,
        "mission_control_trace": mission_control_trace,
        "mission_packet": mission_packet,
        "board_summary": board_summary,
        "warnings": warnings,
        "provenance": provenance,
        "observability": {
            "mlflow": tracing_status(),
        },
    }
