from __future__ import annotations

import os
from typing import Any

from databricks.sdk import WorkspaceClient
from databricks.sdk.service.serving import ChatMessage, ChatMessageRole

from src.agent.prompts import DEVHUB_LAKEBASE_SUBAGENT_PROMPT
from src.agent.tools import (
    build_evidence_rows,
    get_district_priorities,
    get_facility_candidates,
)


def _deterministic_summary(
    mission_label: str,
    state_filter: str,
    top_district: dict[str, Any] | None,
    top_facility: dict[str, Any] | None,
    top_trust_review: dict[str, Any] | None,
    warnings: list[str],
) -> str:
    if top_district is None or top_facility is None:
        return (
            f"Care Convoy could not find strong live evidence for {mission_label} yet. "
            "The app is falling back to a demo-safe view so we can keep building the workflow."
        )

    warning_text = ""
    if warnings:
        warning_text = " Key cautions: " + "; ".join(warnings[:2]) + "."

    trust_text = ""
    if top_trust_review is not None:
        trust_text = (
            f" Trust Desk v2 labels the facility as {top_trust_review['review_status']} "
            f"with website status {top_trust_review['website_verification_status']}."
        )

    return (
        f"For {mission_label} in {state_filter or 'India'}, the current top district is "
        f"{top_district['district']}, {top_district['state']}. "
        f"The strongest current referral anchor is {top_facility['name']} in "
        f"{top_facility['address_city']}, with a capability-fit score of "
        f"{top_facility['capability_fit']:.0f} and confidence labeled "
        f"{top_facility['confidence_label']}.{trust_text}{warning_text}"
    )


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
    citations = build_evidence_rows(facilities, trust_reviews)
    district_source = _result_source(districts)
    facility_source = _result_source(facilities)

    warnings: list[str] = []
    if district_source != "live":
        warnings.append("District prioritization is using fallback data until a stronger live join is in place.")
    if facility_source != "live":
        warnings.append("Facility ranking is using demo-safe fallback data because no live anchor rows were returned.")
    if citations["source_url"].eq("").any():
        warnings.append("Some facility claims do not have source URLs yet and should stay in review.")
    if trust_reviews is not None and not trust_reviews.empty:
        if trust_reviews["website_verification_status"].isin(["website unavailable", "review required"]).any():
            warnings.append("Trust Desk v2 could not fully verify every facility website, so some trust scores remain review-required.")
        if trust_reviews["duplicate_review_required"].any():
            warnings.append("Some facility rows were clustered as possible duplicates and still need a human entity-resolution check.")

    top_district = districts.iloc[0].to_dict() if not districts.empty else None
    top_facility = facilities.iloc[0].to_dict() if not facilities.empty else None
    top_trust_review = trust_reviews.iloc[0].to_dict() if trust_reviews is not None and not trust_reviews.empty else None

    prompt = (
        f"You are writing a brief for a non-technical Virtue Foundation operations lead.\n"
        f"Mission type: {mission_label}\n"
        f"State filter: {state_filter or 'India'}\n"
        f"Top district: {top_district}\n"
        f"Top facility: {top_facility}\n"
        f"Top trust review: {top_trust_review}\n"
        f"Warnings: {warnings}\n"
        "Use only the supplied evidence, be explicit about uncertainty, and keep the answer to three sentences."
    )
    summary = _llm_summary(prompt) or _deterministic_summary(
        mission_label=mission_label,
        state_filter=state_filter,
        top_district=top_district,
        top_facility=top_facility,
        top_trust_review=top_trust_review,
        warnings=warnings,
    )

    confidence_label = "Weak Evidence"
    if not facilities.empty:
        confidence_label = str(facilities.iloc[0]["confidence_label"])

    provenance = _provenance_label(district_source, facility_source)
    return {
        "run_id": run_id,
        "mission_type": mission_type,
        "mission_label": mission_label,
        "summary": summary,
        "confidence_label": confidence_label,
        "districts": districts,
        "facilities": facilities,
        "trust_reviews": trust_reviews,
        "search_results": search_results,
        "citations": citations,
        "warnings": warnings,
        "provenance": provenance,
    }
