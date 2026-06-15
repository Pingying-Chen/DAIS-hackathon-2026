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
from src.ui.components import action_panel, card, card_grid, hero_header, inline_metrics, kpi_row, status_stack
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

STAGE_VIEWS = ["Overview", "Anchor Review", "Trust Evidence", "Shortlist"]


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
            "A Databricks-native referral copilot for India that combines district need, facility capability, "
            "and a trust-scoring support layer so an operations lead can choose a credible deployment anchor "
            "without reading raw rows."
        ),
        chips=[
            ("User", "Virtue Foundation operations lead"),
            ("Decision", "Where to send the next referral team"),
            ("Trust layer", "Entity resolution + website corroboration"),
            ("Persistence", "Lakebase shortlist"),
            ("Evidence", "Citations and uncertainty visible"),
        ],
    )


def _summary_metrics(result: dict[str, Any] | None) -> None:
    if result is None:
        items = [
            {"label": "App State", "value": "Ready", "value_class": "db-kpi-accent", "note": "Choose a care need and build the referral plan."},
            {"label": "Track", "value": "3", "note": "Referral Copilot with a supporting trust layer."},
            {"label": "Data Path", "value": "India Facilities", "note": "Unity Catalog facilities plus district context."},
            {"label": "Persistence", "value": "Lakebase", "note": "Saved shortlist decisions survive refresh."},
        ]
    else:
        trust_reviews = result.get("trust_reviews")
        verified_count = 0
        if trust_reviews is not None and not trust_reviews.empty:
            verified_count = int(trust_reviews["website_verification_status"].eq("verified").sum())
        items = [
            {"label": "Referral Confidence", "value": result["confidence_label"], "value_class": "db-kpi-accent", "note": "Confidence in the lead referral anchor after trust scoring."},
            {"label": "Priority Districts", "value": str(len(result["districts"])), "note": "Districts returned for the current mission."},
            {"label": "Candidate Facilities", "value": str(len(result["facilities"])), "note": "Resolved facilities ranked for referral action."},
            {"label": "Verified Websites", "value": str(verified_count), "note": "Facility websites corroborated by the trust support layer."},
        ]
    kpi_row(items)


def _show_empty_state() -> None:
    card_grid(
        [
            {
                "title": "What this app helps you decide",
                "body": (
                    "Run the referral copilot, inspect the district map and facility shortlist, then use the trust layer "
                    "to verify whether the recommended anchor looks credible enough to act on."
                ),
                "caption": "The opening screen should make the review decision obvious before any technical detail appears.",
            },
            {
                "title": "What to click first",
                "body": (
                    "Choose a care need, keep or tighten the state and district filters, then click Build Referral Plan "
                    "to generate a shortlist with trust-backed evidence."
                ),
                "caption": "Results stay inside the main workspace views so the sidebar remains input-only.",
            },
        ]
    )


def _result_status_messages(result: dict[str, Any]) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = [("info", result["provenance"])]
    messages.extend(("warn", warning) for warning in result["warnings"])
    return messages


def _show_overview(result: dict[str, Any]) -> None:
    districts = result["districts"]
    facilities = result["facilities"]
    trust_reviews = result["trust_reviews"]
    top_district = districts.iloc[0] if not districts.empty else None
    top_facility = facilities.iloc[0] if not facilities.empty else None
    top_trust_review = trust_reviews.iloc[0] if trust_reviews is not None and not trust_reviews.empty else None

    left, right = st.columns([1.6, 1], gap="large")
    with left:
        render_map(districts, facilities, height=430)
        st.markdown(
            "<p class='db-map-caption'>Blue points show district demand context. Red points show the facilities being reviewed for credibility.</p>",
            unsafe_allow_html=True,
        )

    with right:
        card("What this run says", result["summary"], result["provenance"])
        inline_metrics(
            [
                ("Care need", result["mission_label"]),
                ("Referral confidence", result["confidence_label"]),
                ("Shortlist mode", "Lakebase" if lakebase_available() else "Not configured"),
                (
                    "Lead website status",
                    str(top_trust_review["website_verification_status"]) if top_trust_review is not None else "n/a",
                ),
            ]
        )
        if top_facility is not None:
            card(
                f"Lead referral anchor: {top_facility['name']}",
                (
                    f"Capability fit {top_facility['capability_fit']:.0f}, trust score {top_facility['trust_score']:.0f}, "
                    f"resolved entity {top_facility['resolved_entity_id']} built from {int(top_facility['entity_record_count'])} source row(s)."
                ),
                top_facility["risk_flags"] or "No facility review flags.",
            )
        if top_district is not None:
            card(
                f"Highest-need district context: {top_district['district']}, {top_district['state']}",
                (
                    f"Need score {top_district['need_score']:.1f}, coverage gap {top_district['coverage_gap']:.1f}, "
                    f"evidence score {top_district['evidence_score']:.1f}."
                ),
                top_district["uncertainty_label"],
            )
        action_panel(
            "What to do next",
            "Use the other views to decide whether this facility is the right anchor for the referral plan.",
            [
                "Open Anchor Review to inspect merged entities and compare the top facility candidates.",
                "Open Trust Evidence to see website corroboration, duplicate checks, and citations.",
                "Save the shortlist entry only after the trust signals support the referral recommendation.",
            ],
        )
        status_stack(_result_status_messages(result))


def _show_anchors(result: dict[str, Any]) -> None:
    districts = result["districts"]
    facilities = result["facilities"]
    if facilities.empty and districts.empty:
        st.info("No facility entities are available yet. Try broadening the state or district filter.")
        return

    left, right = st.columns([1.05, 1], gap="large")
    with left:
        if districts.empty:
            st.info("District demand context is not available for this run.")
        else:
            chart = build_confidence_chart(districts, "district", "priority_score")
            if chart is not None:
                chart.update_layout(height=350, margin=dict(l=8, r=8, t=8, b=8))
                st.plotly_chart(chart, use_container_width=True)

    with right:
        if facilities.empty:
            st.info("No facility candidates are available yet. The fallback dataset will appear once a district is selected.")
            return

        cards: list[dict[str, str]] = []
        for row in facilities.head(4).itertuples(index=False):
            cards.append(
                {
                    "title": row.name,
                    "body": (
                        f"{row.address_city}, {row.address_stateOrRegion}. Trust {row.trust_score:.0f}, fit {row.capability_fit:.0f}, "
                        f"website {row.website_verification_status}, entity rows {int(row.entity_record_count)}."
                    ),
                    "caption": row.risk_flags or row.confidence_label,
                }
            )
        card_grid(cards)

    if facilities.empty:
        st.info("No facility candidates are available yet. The fallback dataset will appear once a district is selected.")
        return

    for row in facilities.head(4).itertuples(index=False):
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

    _show_compare(result)


def _show_trust_desk(result: dict[str, Any]) -> None:
    trust_reviews = result["trust_reviews"]
    if trust_reviews is None or trust_reviews.empty:
        st.info("Trust Evidence appears once facility candidates are available.")
        return

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
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
            height=300,
        )

        cards: list[dict[str, str]] = []
        for review in trust_reviews.head(2).itertuples(index=False):
            cards.append(
                {
                    "title": review.facility_name,
                    "body": (
                    f"Status {review.review_status}, website {review.website_verification_status}, "
                    f"trust {review.trust_score_v2:.0f}, entity rows {review.entity_record_count}, "
                    f"match confidence {review.entity_match_confidence:.2f}."
                    ),
                    "caption": review.risk_flags or review.entity_match_reasons or "No extra review notes.",
                }
            )
        card_grid(cards)

    with right:
        card(
            "How the trust support layer works",
            (
                "Each facility row is cleaned and merged into a resolved entity, then the app checks a selected public website and "
                "combines those signals with the social-media features already present in the dataset."
            ),
            "The trust score supports the referral choice; it does not replace the referral decision itself.",
        )
        st.dataframe(result["citations"], use_container_width=True, hide_index=True, height=300)
        search_results = result.get("search_results")
        if search_results is not None and not search_results.empty:
            st.dataframe(
                search_results[
                    [
                        "facility_name",
                        "selection_source",
                        "result_domain",
                        "match_confidence",
                    ]
                ],
                use_container_width=True,
                hide_index=True,
                height=180,
            )


def _show_compare(result: dict[str, Any]) -> None:
    facilities = result["facilities"].head(2)
    if len(facilities) < 2:
        st.info("Compare view unlocks when at least two facility candidates are available.")
        return

    chart = build_tradeoff_chart(facilities)
    if chart is not None:
        chart.update_layout(height=300, margin=dict(l=8, r=8, t=8, b=8))
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
    saved = list_user_decisions(limit=8)
    saved_error = saved.attrs.get("error")
    top_facility = result["facilities"].head(1)
    top_district = result["districts"].head(1)
    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        if saved_error:
            st.warning(saved_error)
        elif not saved.empty:
            st.dataframe(saved, use_container_width=True, hide_index=True, height=310)
        else:
            card(
                "No shortlist entries yet",
                "Save the current lead facility after reviewing its trust status to create a durable decision record.",
                "The shortlist is the impact beat: it proves the run produced a persistent action.",
            )

    with right:
        if top_facility.empty or top_district.empty:
            return

        candidate = top_facility.iloc[0]
        district = top_district.iloc[0]
        default_note = f"Review {candidate['name']} for {district['district']} as the first referral anchor."
        card(
            "Ready to save",
            (
                f"{candidate['name']} is the current lead candidate for {district['district']}, {district['state']}. "
                f"Save only after the trust evidence and duplicate-review flags look acceptable."
            ),
            candidate["risk_flags"] or "No extra risk flags on the lead candidate.",
        )

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


def _stage_selector() -> str:
    segmented = getattr(st, "segmented_control", None)
    if callable(segmented):
        selected = segmented(
            "Review View",
            STAGE_VIEWS,
            default="Overview",
            selection_mode="single",
            label_visibility="collapsed",
            key="stage_view",
        )
        return selected or "Overview"

    return st.radio(
        "Review View",
        STAGE_VIEWS,
        index=0,
        horizontal=True,
        label_visibility="collapsed",
        key="stage_view_radio",
    )


@st.fragment
def _render_stage(view: str, result: dict[str, Any]) -> None:
    if view == "Overview":
        _show_overview(result)
    elif view == "Anchor Review":
        _show_anchors(result)
    elif view == "Trust Evidence":
        _show_trust_desk(result)
    else:
        _show_shortlist(result)


st.set_page_config(page_title="Care Convoy", layout="wide")
inject_theme()

_hero()

with st.sidebar:
    st.subheader("Mission Setup")
    mission_key = st.selectbox("Care need", list(MISSION_OPTIONS), format_func=MISSION_OPTIONS.get)
    state_filter = st.text_input("State focus", value="Maharashtra")
    district_filter = st.text_input("District focus", value="")
    confidence_label = st.select_slider("Minimum certainty", options=list(CONFIDENCE_OPTIONS))
    run_button = st.button("Build Referral Plan", type="primary", use_container_width=True)
    lakebase = lakebase_status()
    st.caption("Shortlist mode: Lakebase" if lakebase_available() else "Shortlist mode: Lakebase not configured yet")
    st.caption(lakebase["detail"])

if "latest_result" not in st.session_state:
    st.session_state.latest_result = None

if run_button:
    with st.spinner("Resolving entities, checking websites, and scoring trust..."):
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
    _render_stage(_stage_selector(), result)
