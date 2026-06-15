from __future__ import annotations

from pathlib import Path
import sys
import uuid
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.reasoning import run_agent
from src.db.lakebase import lakebase_available, lakebase_status, list_user_decisions
from src.ui.components import card, hero_header, inline_metrics, kpi_row, status_stack
from src.ui.theme import inject_theme
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

STAGE_VIEWS = ["Overview", "Anchors", "Trust Desk", "Shortlist"]


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _hero() -> None:
    hero_header(
        eyebrow="Track 3 Referral Copilot",
        title="Care Convoy",
        subtitle=(
            "A Databricks-native mission planner for India that combines district need, "
            "facility capability, and Trust Desk v2 verification so an operations lead "
            "can choose a credible deployment anchor without reading raw rows."
        ),
        chips=[
            ("User", "Virtue Foundation operations lead"),
            ("Trust layer", "Entity resolution + website corroboration"),
            ("Persistence", "Lakebase shortlist"),
            ("Evidence model", "Citations and uncertainty visible"),
        ],
    )


def _summary_metrics(result: dict[str, Any] | None) -> None:
    if result is None:
        items = [
            {"label": "App State", "value": "Ready", "value_class": "db-kpi-accent", "note": "Choose a mission to run the v2 flow."},
            {"label": "Track", "value": "3 + 2", "note": "Referral Copilot with Trust Desk v2."},
            {"label": "Data Path", "value": "Live SQL", "note": "Unity Catalog facilities and district indicators."},
            {"label": "Persistence", "value": "Lakebase", "note": "Saved shortlist decisions survive refresh."},
        ]
    else:
        trust_reviews = result.get("trust_reviews")
        items = [
            {"label": "Confidence", "value": result["confidence_label"], "value_class": "db-kpi-accent", "note": "Top anchor confidence after trust scoring."},
            {"label": "Priority Districts", "value": str(len(result["districts"])), "note": "Districts returned for the current mission."},
            {"label": "Anchor Entities", "value": str(len(result["facilities"])), "note": "Resolved facilities ranked for action."},
            {"label": "Trust Reviews", "value": str(len(trust_reviews) if trust_reviews is not None else 0), "note": "Entities with website verification status."},
        ]
    kpi_row(items)


def _show_empty_state() -> None:
    left, right = st.columns([1.4, 1], gap="large")
    with left:
        card(
            "How the v2 flow works",
            (
                "Run a mission, inspect the map and anchor shortlist, then switch to Trust Desk "
                "to see whether similar rows were merged and whether the selected website "
                "corroborates the facility claims."
            ),
            "The public app should tell the track, trust method, and persistence story before any code talk.",
        )
    with right:
        card(
            "Current deploy goal",
            (
                "This build is being aligned to the design-system skills so the UI becomes the live "
                "presentation surface rather than a plain scaffold."
            ),
            "Start from the sidebar to generate the first mission plan.",
        )


def _result_status_messages(result: dict[str, Any]) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = [("info", result["provenance"])]
    messages.extend(("warn", warning) for warning in result["warnings"])
    return messages


def _show_overview(result: dict[str, Any]) -> None:
    districts = result["districts"]
    facilities = result["facilities"]
    top_district = districts.iloc[0] if not districts.empty else None
    top_facility = facilities.iloc[0] if not facilities.empty else None

    left, right = st.columns([1.55, 1], gap="large")
    with left:
        st.subheader("Planning Map")
        render_map(districts, facilities)
        if top_district is not None:
            card(
                f"Priority district: {top_district['district']}, {top_district['state']}",
                (
                    f"Need score {top_district['need_score']:.1f}, coverage gap {top_district['coverage_gap']:.1f}, "
                    f"evidence score {top_district['evidence_score']:.1f}. "
                    f"Uncertainty label: {top_district['uncertainty_label']}."
                ),
                top_district["risk_flags"] or "No district risk flags.",
            )

    with right:
        card("Mission Brief", result["summary"], result["provenance"])
        inline_metrics(
            [
                ("Selected mission", result["mission_label"]),
                ("Top confidence", result["confidence_label"]),
                ("Shortlist mode", "Lakebase" if lakebase_available() else "Not configured"),
                (
                    "Top website status",
                    str(top_facility["website_verification_status"]) if top_facility is not None else "n/a",
                ),
            ]
        )
        if top_facility is not None:
            card(
                f"Top anchor: {top_facility['name']}",
                (
                    f"Capability fit {top_facility['capability_fit']:.0f}, trust score {top_facility['trust_score']:.0f}, "
                    f"resolved entity {top_facility['resolved_entity_id']} with {int(top_facility['entity_record_count'])} source row(s)."
                ),
                top_facility["risk_flags"] or "No facility review flags.",
            )
        status_stack(_result_status_messages(result))


def _show_district_snapshot(result: dict[str, Any]) -> None:
    districts = result["districts"]
    if districts.empty:
        st.info("No district priorities yet. Try broadening the state or district filter.")
        return

    st.subheader("District Priorities")
    chart = build_confidence_chart(districts, "district", "priority_score")
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True)

    for row in districts.head(4).itertuples(index=False):
        with st.container(border=True):
            top_left, top_right = st.columns([3, 1])
            with top_left:
                st.markdown(f"**{row.district}, {row.state}**")
                st.caption(row.uncertainty_label)
            with top_right:
                st.metric("Priority", f"{row.priority_score:.0f}")
            metric_cols = st.columns(4)
            metric_cols[0].metric("Need", _format_metric(row.need_score))
            metric_cols[1].metric("Gap", _format_metric(row.coverage_gap))
            metric_cols[2].metric("Facilities", _format_metric(row.facility_count))
            metric_cols[3].metric("Evidence", _format_metric(row.evidence_score))
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
            stats[3].metric("Entity Rows", int(row.entity_record_count))
            st.caption(
                f"Resolved entity: {row.resolved_entity_id} | website status: "
                f"{row.website_verification_status} | source: {row.selection_source}"
            )
            st.write(row.description or "No description available yet.")
            if row.primary_url:
                st.write(f"Website checked: {row.primary_url}")
            if row.website_excerpt:
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

    st.divider()
    _show_compare(result)


def _show_trust_desk(result: dict[str, Any]) -> None:
    trust_reviews = result["trust_reviews"]
    if trust_reviews is None or trust_reviews.empty:
        st.info("Trust Desk v2 appears once facility candidates are available.")
        return

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
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
                detail_left, detail_right = st.columns([2, 1])
                with detail_left:
                    st.markdown(f"**{review.facility_name}**")
                    st.caption(f"{review.website_verification_status} via {review.selection_source or 'unavailable'}")
                    if review.primary_url:
                        st.write(f"Matched website: {review.primary_url}")
                    if review.website_excerpt:
                        st.write(review.website_excerpt)
                with detail_right:
                    st.metric("Trust v2", f"{review.trust_score_v2:.0f}")
                    st.metric("Entity Rows", review.entity_record_count)
                    st.metric("Match", f"{review.entity_match_confidence:.2f}")
                if review.entity_match_reasons:
                    st.caption(f"Entity match logic: {review.entity_match_reasons}")
                if review.risk_flags:
                    st.caption(f"Review flags: {review.risk_flags}")

    with right:
        st.subheader("Evidence Ledger")
        st.dataframe(result["citations"], use_container_width=True, hide_index=True)


def _show_compare(result: dict[str, Any]) -> None:
    facilities = result["facilities"].head(2)
    if len(facilities) < 2:
        st.info("Compare view unlocks when at least two candidate anchors are available.")
        return

    st.subheader("Trade-off Compare")
    chart = build_tradeoff_chart(facilities)
    if chart is not None:
        st.plotly_chart(chart, use_container_width=True)

    left, right = st.columns(2, gap="large")
    for column, row in zip((left, right), facilities.itertuples(index=False), strict=False):
        with column:
            card(
                row.name,
                (
                    f"{row.address_city}, {row.address_stateOrRegion}. "
                    f"Urgency support {row.urgency_support:.0f}, capability fit {row.capability_fit:.0f}, "
                    f"confidence {row.confidence_label}."
                ),
                row.risk_flags or "No additional review flags.",
            )


def _show_shortlist(result: dict[str, Any]) -> None:
    st.subheader("Mission Shortlist")
    saved = list_user_decisions(limit=8)
    saved_error = saved.attrs.get("error")
    if saved_error:
        st.warning(saved_error)
    elif not saved.empty:
        st.dataframe(saved, use_container_width=True, hide_index=True)
    else:
        card(
            "No shortlist entries yet",
            "Save the current top anchor after reviewing its trust status to create a persistent decision artifact.",
            "The shortlist is the impact beat: it proves the run produced a durable action.",
        )

    top_facility = result["facilities"].head(1)
    top_district = result["districts"].head(1)
    if top_facility.empty or top_district.empty:
        return

    candidate = top_facility.iloc[0]
    district = top_district.iloc[0]
    default_note = f"Review {candidate['name']} for {district['district']} as the first convoy anchor."

    with st.form("save_shortlist"):
        note = st.text_area("Verification note", value=default_note, height=110)
        decision = st.selectbox("Decision status", ["needs verification", "approved", "hold"])
        submitted = st.form_submit_button("Save shortlist item")

    if submitted:
        run_id = result["run_id"]
        payload = {
            "district": district["district"],
            "state": district["state"],
            "facility_name": candidate["name"],
            "confidence_label": candidate["confidence_label"],
            "resolved_entity_id": candidate["resolved_entity_id"],
            "website_verification_status": candidate["website_verification_status"],
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


@st.fragment
def _render_stage(view: str, result: dict[str, Any]) -> None:
    if view == "Overview":
        _show_overview(result)
        st.divider()
        _show_district_snapshot(result)
    elif view == "Anchors":
        _show_facilities(result)
    elif view == "Trust Desk":
        _show_trust_desk(result)
    else:
        _show_shortlist(result)


st.set_page_config(page_title="Care Convoy", layout="wide")
inject_theme()

st.markdown("<div class='db-shell'>", unsafe_allow_html=True)
_hero()

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
    with st.spinner("Scoring district demand, anchor fit, and trust review..."):
        st.session_state.latest_result = run_agent(
            mission_type=mission_key,
            mission_label=MISSION_OPTIONS[mission_key],
            state_filter=state_filter.strip(),
            district_filter=district_filter.strip(),
            confidence_threshold=CONFIDENCE_OPTIONS[confidence_label],
            run_id=str(uuid.uuid4()),
        )

result = st.session_state.latest_result
_summary_metrics(result)

if result is None:
    _show_empty_state()
else:
    stage_view = st.segmented_control(
        "Workspace View",
        STAGE_VIEWS,
        default="Overview",
        selection_mode="single",
        label_visibility="collapsed",
        key="stage_view",
    )
    _render_stage(stage_view or "Overview", result)

st.markdown("</div>", unsafe_allow_html=True)
