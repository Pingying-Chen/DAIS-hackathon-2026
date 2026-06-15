from __future__ import annotations

from pathlib import Path
import sys
import uuid
from typing import Any

import pandas as pd
import streamlit as st

# Databricks Apps launches Streamlit from the bundle root, so keep the repo root
# importable even when the script entrypoint lives under src/.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.reasoning import run_agent
from src.db.lakebase import lakebase_available, lakebase_status, list_user_decisions
from src.viz.charts import build_confidence_chart, build_tradeoff_chart
from src.viz.maps import render_map

MISSION_OPTIONS = {
    "maternal_health": "Maternal Health",
    "surgery": "Surgery",
    "emergency_care": "Emergency Care",
    "general_access": "General Access",
}

CONFIDENCE_OPTIONS = {
    "Weak Evidence": 0.25,
    "Moderate Confidence": 0.5,
    "High Confidence": 0.75,
}


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _show_summary(result: dict[str, Any]) -> None:
    left, right = st.columns([1.3, 1])
    with left:
        st.subheader("Mission Brief")
        st.markdown(result["summary"])
        st.caption(result["provenance"])
    with right:
        st.subheader("Decision Signal")
        st.metric("Confidence", result["confidence_label"])
        st.metric("Priority Districts", len(result["districts"]))
        st.metric("Anchor Candidates", len(result["facilities"]))
        st.metric("Resolved Entities", len(result["trust_reviews"]) if result["trust_reviews"] is not None else 0)
        if result["warnings"]:
            for warning in result["warnings"]:
                st.warning(warning)


def _show_districts(result: dict[str, Any]) -> None:
    districts = result["districts"]
    if districts.empty:
        st.info("No district priorities yet. Try broadening the state or district filter.")
        return

    st.subheader("District Priorities")
    chart = build_confidence_chart(districts, "district", "priority_score")
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True)

    for row in districts.head(5).itertuples(index=False):
        with st.container(border=True):
            header_left, header_right = st.columns([3, 1])
            with header_left:
                st.markdown(f"**{row.district}, {row.state}**")
                st.caption(row.uncertainty_label)
            with header_right:
                st.metric("Priority", f"{row.priority_score:.0f}")

            detail_cols = st.columns(4)
            detail_cols[0].metric("Need", _format_metric(row.need_score))
            detail_cols[1].metric("Coverage Gap", _format_metric(row.coverage_gap))
            detail_cols[2].metric("Facilities", _format_metric(row.facility_count))
            detail_cols[3].metric("Evidence", _format_metric(row.evidence_score))

            if row.risk_flags:
                st.caption(f"Risk flags: {row.risk_flags}")


def _show_facilities(result: dict[str, Any]) -> None:
    facilities = result["facilities"]
    if facilities.empty:
        st.info("No facility anchors yet. The fallback dataset will appear once a district is selected.")
        return

    st.subheader("Referral Anchors")
    for row in facilities.head(6).itertuples(index=False):
        with st.expander(f"{row.name} ({row.address_city}, {row.address_stateOrRegion})", expanded=False):
            stats = st.columns(4)
            stats[0].metric("Fit", f"{row.capability_fit:.0f}")
            stats[1].metric("Trust", f"{row.trust_score:.0f}")
            stats[2].metric("Confidence", row.confidence_label)
            stats[3].metric("Evidence", _format_metric(row.evidence_count))
            st.caption(
                f"Resolved entity: {getattr(row, 'resolved_entity_id', 'n/a')} "
                f"({getattr(row, 'entity_record_count', 1)} row(s)); "
                f"website status: {getattr(row, 'website_verification_status', 'unavailable')}"
            )
            st.write(row.description or "No description available yet.")
            if getattr(row, "primary_url", ""):
                st.write(f"Website checked: {row.primary_url}")
            if getattr(row, "website_excerpt", ""):
                st.caption(row.website_excerpt)
            if row.risk_flags:
                st.caption(f"Warnings: {row.risk_flags}")

            citations = result["citations"]
            facility_citations = citations[citations["facility_id"] == row.unique_id]
            if not facility_citations.empty:
                st.dataframe(
                    facility_citations[["claim_type", "evidence", "source_url"]],
                    use_container_width=True,
                    hide_index=True,
                )


def _show_trust_desk(result: dict[str, Any]) -> None:
    trust_reviews = result["trust_reviews"]
    if trust_reviews is None or trust_reviews.empty:
        st.info("Trust Desk v2 appears once facility candidates are available.")
        return

    st.subheader("Trust Desk v2")
    st.dataframe(
        trust_reviews[
            [
                "facility_name",
                "review_status",
                "trust_score_v2",
                "website_verification_status",
                "entity_record_count",
                "entity_match_confidence",
                "selection_source",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    for review in trust_reviews.head(3).itertuples(index=False):
        with st.container(border=True):
            left, right = st.columns([2, 1])
            with left:
                st.markdown(f"**{review.facility_name}**")
                st.caption(
                    f"{review.website_verification_status} via {review.selection_source or 'unavailable'}"
                )
                if review.primary_url:
                    st.write(f"Matched website: {review.primary_url}")
                if review.website_excerpt:
                    st.write(review.website_excerpt)
            with right:
                st.metric("Trust v2", f"{review.trust_score_v2:.0f}")
                st.metric("Entity Rows", review.entity_record_count)
                st.metric("Match", f"{review.entity_match_confidence:.2f}")
            if review.entity_match_reasons:
                st.caption(f"Entity match logic: {review.entity_match_reasons}")
            if review.risk_flags:
                st.caption(f"Review flags: {review.risk_flags}")


def _show_compare(result: dict[str, Any]) -> None:
    facilities = result["facilities"].head(2)
    if len(facilities) < 2:
        st.info("Compare view unlocks when at least two candidate anchors are available.")
        return

    st.subheader("Trade-off Compare")
    chart = build_tradeoff_chart(facilities)
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True)

    left, right = st.columns(2)
    for column, row in zip((left, right), facilities.itertuples(index=False), strict=False):
        with column:
            st.markdown(f"**{row.name}**")
            st.caption(f"{row.address_city}, {row.address_stateOrRegion}")
            st.write(f"Urgency support: {row.urgency_support:.0f}")
            st.write(f"Capability fit: {row.capability_fit:.0f}")
            st.write(f"Confidence: {row.confidence_label}")
            st.write(f"Evidence completeness: {row.evidence_count}")


def _show_shortlist(result: dict[str, Any]) -> None:
    st.subheader("Mission Shortlist")
    saved = list_user_decisions(limit=8)
    saved_error = saved.attrs.get("error")
    if saved_error:
        st.warning(saved_error)
    elif not saved.empty:
        st.dataframe(saved, use_container_width=True, hide_index=True)
    else:
        st.caption("No persisted shortlist entries yet. Save one from the current recommendation run.")

    top_facility = result["facilities"].head(1)
    top_district = result["districts"].head(1)
    if top_facility.empty or top_district.empty:
        return

    candidate = top_facility.iloc[0]
    district = top_district.iloc[0]
    default_note = f"Review {candidate['name']} for {district['district']} as the first convoy anchor."

    with st.form("save_shortlist"):
        note = st.text_area("Verification note", value=default_note, height=100)
        decision = st.selectbox("Decision status", ["needs verification", "approved", "hold"])
        submitted = st.form_submit_button("Save shortlist item")

    if submitted:
        run_id = result["run_id"]
        payload = {
            "district": district["district"],
            "state": district["state"],
            "facility_name": candidate["name"],
            "confidence_label": candidate["confidence_label"],
        }
        from src.agent.tools import save_user_decision

        saved_ok = save_user_decision(
            run_id=run_id,
            mission_type=result["mission_label"],
            district=district["district"],
            facility_id=str(candidate["unique_id"]),
            decision=decision,
            note=note,
            metadata=payload,
        )
        if saved_ok:
            st.success("Shortlist item saved.")
        else:
            st.error("Could not save the shortlist item. Lakebase permissions or configuration need attention.")


st.set_page_config(page_title="Care Convoy", layout="wide")
st.title("Care Convoy")
st.caption("Referral copilot for planning specialty team deployment in India.")

with st.sidebar:
    st.subheader("Mission Setup")
    mission_key = st.selectbox("Mission type", list(MISSION_OPTIONS), format_func=MISSION_OPTIONS.get)
    state_filter = st.text_input("State filter", value="Maharashtra")
    district_filter = st.text_input("District filter", value="")
    confidence_label = st.select_slider("Minimum confidence", options=list(CONFIDENCE_OPTIONS))
    run_button = st.button("Build Mission Plan", type="primary", use_container_width=True)
    lakebase = lakebase_status()
    st.caption("Persistence mode: Lakebase" if lakebase_available() else "Persistence mode: Lakebase not configured yet")
    st.caption(lakebase["detail"])

if "latest_result" not in st.session_state:
    st.session_state.latest_result = None

if run_button:
    with st.spinner("Scoring district demand, anchor fit, and evidence quality..."):
        st.session_state.latest_result = run_agent(
            mission_type=mission_key,
            mission_label=MISSION_OPTIONS[mission_key],
            state_filter=state_filter.strip(),
            district_filter=district_filter.strip(),
            confidence_threshold=CONFIDENCE_OPTIONS[confidence_label],
            run_id=str(uuid.uuid4()),
        )

result = st.session_state.latest_result

if result is None:
    st.info("Start by selecting a mission type to generate a district shortlist and referral anchors.")
else:
    _show_summary(result)

    map_col, shortlist_col = st.columns([1.8, 1])
    with map_col:
        render_map(result["districts"], result["facilities"])
    with shortlist_col:
        _show_shortlist(result)

    tabs = st.tabs(["District Priorities", "Referral Anchors", "Trust Desk v2", "Evidence Ledger", "Trade-off Compare"])
    with tabs[0]:
        _show_districts(result)
    with tabs[1]:
        _show_facilities(result)
    with tabs[2]:
        _show_trust_desk(result)
    with tabs[3]:
        st.subheader("Evidence Ledger")
        st.dataframe(result["citations"], use_container_width=True, hide_index=True)
    with tabs[4]:
        _show_compare(result)
