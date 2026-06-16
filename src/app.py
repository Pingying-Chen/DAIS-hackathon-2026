from __future__ import annotations

import json
from html import escape
from pathlib import Path
import re
import sys
import uuid
from typing import Any

import pandas as pd
import streamlit as st

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.reasoning import run_agent
from src.db.lakebase import lakebase_available, list_user_decisions
from src.ui.components import action_panel, bullet_card, card, card_grid, filter_pills, hero_header, inline_metrics, kpi_row, status_stack
from src.ui.decision_options import decision_options_for_packet
from src.ui.evidence_text import claim_label, evidence_sentence, source_note
from src.ui.theme import inject_theme
from src.viz.charts import build_confidence_chart
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

ALL_STATES_LABEL = "All India"
ALL_DISTRICTS_LABEL = "All districts"
DEFAULT_STATE_FOCUS = "Maharashtra"
DEFAULT_DISTRICT_FOCUS = "Nagpur"

INDIA_STATE_OPTIONS = [
    "Andaman and Nicobar Islands",
    "Andhra Pradesh",
    "Arunachal Pradesh",
    "Assam",
    "Bihar",
    "Chandigarh",
    "Chhattisgarh",
    "Dadra and Nagar Haveli and Daman and Diu",
    "Delhi",
    "Goa",
    "Gujarat",
    "Haryana",
    "Himachal Pradesh",
    "Jammu and Kashmir",
    "Jharkhand",
    "Karnataka",
    "Kerala",
    "Ladakh",
    "Lakshadweep",
    "Madhya Pradesh",
    "Maharashtra",
    "Manipur",
    "Meghalaya",
    "Mizoram",
    "Nagaland",
    "Odisha",
    "Puducherry",
    "Punjab",
    "Rajasthan",
    "Sikkim",
    "Tamil Nadu",
    "Telangana",
    "Tripura",
    "Uttar Pradesh",
    "Uttarakhand",
    "West Bengal",
]

APP_PAGE_LIVE = "Referral Planner"
APP_PAGE_INTRO = "Product Introduction"
STAGE_VIEWS = ["Plan", "Why This Place", "Compare Anchors", "Evidence Details", "Save Review Note"]
INTRO_TABS = ["Product", "Workflow", "Evidence", "Improvements"]
USER_DECISION_COLUMNS = ["created_at", "mission_type", "district", "facility_id", "decision", "note", "metadata_json"]

GATE_LABELS = {
    "pass": "Supported",
    "review": "Review",
    "block": "Hold",
}

GATE_TONES = {
    "pass": "positive",
    "review": "warn",
    "block": "accent",
}

RUN_STEPS = [
    ("Need Check", "Reads district health signals for the selected care need."),
    ("Local Supply", "Checks whether nearby facility coverage looks thin or uncertain."),
    ("Facility Fit", "Ranks lead and backup referral anchors for the mission."),
    ("Trust Signals", "Checks website status, duplicate clues, and claim strength."),
    ("Citation Review", "Looks for cited support before the recommendation is trusted."),
    ("Final Action", "Turns the weakest check into shortlist, verify first, or hold."),
]

AGENT_LABELS = {
    "Need Scout": "Need Check",
    "Supply Mapper": "Local Supply Check",
    "Score Cache": "Readiness Check",
    "Facility Scout": "Facility Fit Check",
    "Trust Verifier": "Trust Signal Check",
    "Evidence Auditor": "Citation Review",
    "Mission Strategist": "Action Check",
    "Supervisor": "Final Recommendation",
}

SOURCE_LABELS = {
    "cached": "Ready",
    "partial": "Partly ready",
    "runtime": "Checked live",
    "dataset_url": "Website listed in the facility record",
    "search": "Website found through public search",
    "search_unavailable": "Public search unavailable",
    "unavailable": "No website evidence found",
}

DECISION_LABELS = {
    "approved": "Ready To Shortlist",
    "needs verification": "Needs Verification",
    "hold": "Hold For Now",
    "shortlist": "Ready To Shortlist",
    "verify first": "Verify First",
    "review": "Needs Review",
    "block": "Hold For Now",
}

CONFIDENCE_MEANINGS = {
    "Weak Evidence": "weak evidence; verify before action",
    "Moderate Confidence": "usable evidence with some caution",
    "High Confidence": "stronger evidence, still review before action",
}


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "Not available"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _shorten(value: Any, limit: int = 110) -> str:
    return _display_text(value)


def _display_text(value: Any, fallback: str = "Not available") -> str:
    if value is None:
        return fallback
    if isinstance(value, float) and pd.isna(value):
        return fallback
    text = str(value).strip()
    if not text or text.casefold() in {"nan", "none", "null", "n/a", "na", "unknown"}:
        return fallback
    return text


def _plain_label(value: Any, fallback: str = "Not available") -> str:
    text = _display_text(value, fallback)
    if text == fallback:
        return text
    return text.replace("_", " ").replace("-", " ").title()


def _decision_label(value: Any) -> str:
    text = _display_text(value, "Review First")
    return DECISION_LABELS.get(text.casefold(), text.replace("_", " ").title())


def _confidence_label(value: Any) -> str:
    text = _display_text(value, "Weak Evidence")
    return CONFIDENCE_MEANINGS.get(text, text)


def _source_label(value: Any) -> str:
    text = _display_text(value)
    return SOURCE_LABELS.get(text, _plain_label(text))


def _score_text(value: Any, *, scale: str = "0-100", meaning: str = "higher means stronger") -> str:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return "Not available"
    if scale == "0-100":
        return f"{number:.0f}/100"
    return f"{number:.0f}"


def _score_number(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _need_read(value: Any) -> str:
    score = _score_number(value)
    if score is None:
        return "Need level: not enough district data to rate urgency."
    if score >= 75:
        return "Need level: high priority for the selected care need."
    if score >= 50:
        return "Need level: meaningful need; compare it with nearby districts."
    return "Need level: lower priority than the leading districts."


def _coverage_read(value: Any) -> str:
    score = _score_number(value)
    if score is None:
        return "Local coverage: not enough mapped supply data to judge the gap."
    if score >= 75:
        return "Local coverage: large gap; local options look thin."
    if score >= 50:
        return "Local coverage: noticeable gap; review local supply before action."
    return "Local coverage: some mapped supply is present."


def _support_read(value: Any, confidence: Any) -> str:
    label = _display_text(confidence, "").casefold()
    score = _score_number(value)
    if "weak" in label:
        return "Source support: weak; use this only as a lead until sources improve."
    if "moderate" in label:
        return "Source support: moderate; good enough to review next, not enough to act alone."
    if "high" in label:
        return "Source support: strong; still confirm before action."
    if score is None:
        return "Source support: limited; verify before action."
    if score >= 75:
        return "Source support: strong; still confirm before action."
    if score >= 50:
        return "Source support: moderate; good enough to review next, not enough to act alone."
    return "Source support: weak; use this only as a lead until sources improve."


def _district_summary_text(value: Any) -> str:
    text = _display_text(value, "District health summary is not available for this place yet.")
    if text == "No district health summary available.":
        return "District health summary is not available for this place yet."
    return text


def _count_text(value: Any, unit: str) -> str:
    try:
        count = int(value)
    except (TypeError, ValueError):
        return f"No {unit}"
    if count == 1:
        return f"1 {unit}"
    return f"{count} {unit}s"


def _website_status(value: Any) -> str:
    text = _display_text(value, "Not checked")
    if text.casefold() in {"demo-safe scaffold", "demo safe scaffold"}:
        return "Needs website review"
    if text.casefold() == "search-assisted":
        return "Search assisted"
    return text.replace("_", " ").replace("-", " ").capitalize()


def _citation_status(value: Any) -> str:
    text = _display_text(value, "Needs citation review")
    if text.casefold() in {"complete", "cited", "supported"}:
        return "Cited"
    if text.casefold() in {"missing", "none", "needs citation review"}:
        return "Needs citation review"
    cleaned = (
        text.replace("_", " ")
        .replace("-", " ")
        .replace("row(s)", "rows")
        .replace("lead anchor citation", "facility citation")
        .replace("district provenance", "district source")
    )
    return cleaned[0].upper() + cleaned[1:] if cleaned else "Needs citation review"


def _summary_source_label(value: Any) -> str:
    return ""


def _plain_review_summary(value: Any) -> str:
    text = _display_text(value, "The recommendation needs review before action.")
    return (
        text.replace("Mission Control v5.3", "The review checks")
        .replace("Mission Control", "The review checks")
        .replace("shortlist after review", "verify before shortlisting")
        .replace("checks recommends verify", "checks recommend verifying")
        .replace("checks recommends", "checks recommend")
    )


def _plain_trace_text(value: Any, fallback: str = "No evidence text available.") -> str:
    text = _display_text(value, fallback)
    replacements = {
        "Website status is demo-safe scaffold": "Website status needs review",
        "Website status is demo safe scaffold": "Website status needs review",
        "demo-safe scaffold": "website evidence needs review",
        "demo safe scaffold": "website evidence needs review",
        "Facility Scout": "Facility Fit Check",
        "Trust Verifier": "Trust Signal Check",
        "Evidence Auditor": "Citation Review",
        "Ask Trust Signal Check whether": "Use the trust review to decide whether",
        "entity resolution": "duplicate review",
        "facility trust scoring": "facility credibility checks",
        "Trust Desk v2": "Trust review",
        "board sequence": "review sequence",
        "Final board state": "Final review state",
        "shortlist after review": "verify before shortlisting",
        "social-proof": "supporting evidence",
        "lead anchor citation row(s)": "facility citation rows",
        "district provenance row(s)": "district source rows",
        "citation row(s)": "citation rows",
        "facility row(s)": "facility rows",
    }
    for source, target in replacements.items():
        text = text.replace(source, target)

    score_patterns = {
        r"\bneed\s+(\d+(?:\.\d+)?)": "need score",
        r"\bevidence\s+(\d+(?:\.\d+)?)": "evidence support",
        r"\bcapability\s+(\d+(?:\.\d+)?)": "facility fit",
        r"\bcapability fit\s+(\d+(?:\.\d+)?)": "facility fit",
        r"\btrust\s+(\d+(?:\.\d+)?)": "trust support",
        r"\bscore is\s+(\d+(?:\.\d+)?)": "score",
    }
    for pattern, label in score_patterns.items():
        text = re.sub(
            pattern,
            lambda match, metric=label: f"{metric} {float(match.group(1)):.0f} on a 0-100 scale",
            text,
            flags=re.IGNORECASE,
        )
    return text


def _saved_decision_warning(message: Any) -> str:
    text = _display_text(message, "Saved-decision storage is not available in this runtime.")
    if "Lakebase" in text:
        return "Review notes can still be saved in this app session."
    return text


def _gate_summary_text(trace: list[dict[str, str]]) -> str:
    gate_counts = _gate_counts(trace)
    return f"{gate_counts['pass']} supported, {gate_counts['review']} need review, {gate_counts['block']} hold"


def _data_coverage_text(result: dict[str, Any]) -> str:
    coverage = result.get("data_coverage", {})
    facility_source = _display_text(coverage.get("facility_source"), "unknown").casefold()
    rows_considered = _score_number(coverage.get("facility_rows_considered")) or 0
    displayed = _score_number(coverage.get("facility_rows_displayed")) or len(result.get("facilities", []))
    if facility_source == "live":
        return f"Live scan: {int(rows_considered):,} facility rows"
    if facility_source == "fallback":
        return f"Fallback sample: {int(rows_considered or displayed)} rows"
    return f"{_plain_label(facility_source, 'Unknown source')}: {int(rows_considered or displayed)} rows"


def _saved_decisions_status() -> str:
    return "Ready"


def _bullet_items(value: str, max_items: int = 6) -> list[str]:
    lines = [line.strip().lstrip("-*• ").strip() for line in value.splitlines()]
    items = [line.rstrip(".") for line in lines if line]
    if len(items) <= 1:
        chunks = value.replace(";", ".").split(".")
        items = [chunk.strip().rstrip(".") for chunk in chunks if chunk.strip()]
    return [_shorten(item, 120) for item in items[:max_items]]


def _short_status(message: str) -> str:
    if message.startswith("Live Databricks SQL"):
        return ""
    if message.startswith("Demo-safe fallback"):
        return ""
    if message.startswith("Mixed sources"):
        return ""
    if message.startswith("District prioritization"):
        return "Review the district recommendation before action."
    if message.startswith("Facility ranking"):
        return "Review the facility recommendation before action."
    if message.startswith("Facility-density"):
        return "Supply density needs review."
    if message.startswith("No facility citation"):
        return "No citations. Hold claims."
    if message.startswith("Some facility claims"):
        return "Some claims lack URLs."
    if message.startswith("Trust Desk"):
        return "Website checks need review."
    if message.startswith("Some facility rows"):
        return "Possible duplicates need review."
    return _shorten(message)


def _hero() -> None:
    hero_header(
        eyebrow="Care Convoy · Referral planning for India",
        title="Care Convoy",
        subtitle="A referral planning tool that helps health teams find where specialty care is most needed, which facility to review first, and what evidence to verify before action.",
        chips=[],
    )


def _render_footer() -> None:
    st.markdown(
        (
            "<div class='db-app-footer'>"
            "<span>Pingying Chen, Zihang Liang</span>"
            "</div>"
        ),
        unsafe_allow_html=True,
    )


def _summary_metrics(result: dict[str, Any] | None) -> None:
    if result is None:
        items = [
            {"label": "Operator View", "value": "Ready", "value_class": "db-kpi-accent", "note": "Start with the default district recommendation."},
            {"label": "Product Type", "value": "Referral Copilot", "note": "Supports referral planning."},
            {"label": "Evidence", "value": "Required", "note": "Weak claims are downgraded."},
            {"label": "Saved Review Notes", "value": _saved_decisions_status(), "note": "Follow-up notes can be revisited."},
        ]
    else:
        trust_reviews = result.get("trust_reviews")
        verified_count = 0
        if trust_reviews is not None and not trust_reviews.empty:
            verified_count = int(trust_reviews["website_verification_status"].eq("verified").sum())
        packet = result.get("mission_packet", {})
        trace = result.get("mission_control_trace", [])
        items = [
            {"label": "Recommended Action", "value": _decision_label(packet.get("action_state", "review")), "value_class": "db-kpi-accent", "note": "Set by the weakest evidence check."},
            {"label": "Recommendation Support", "value": _gate_summary_text(trace), "note": "Supported, needs review, hold."},
            {"label": "Places Checked", "value": str(len(result["districts"])), "note": "Priority districts."},
            {"label": "Facility Options", "value": str(len(result["facilities"])), "note": "Ranked anchors."},
            {"label": "Websites Verified", "value": str(verified_count), "note": "Facility credibility support."},
        ]
    kpi_row(items)


def _show_empty_state() -> None:
    card_grid(
        [
            {
                "title": "The referral story opens here",
                "body": "Read the recommendation, inspect evidence, then save a note.",
                "caption": "The operator path stays first.",
            },
            {
                "title": "Population context is planned",
                "body": "Not active yet. Rankings stay dataset-backed.",
                "caption": "Intentional demo scope.",
            },
        ]
    )


def _result_status_messages(result: dict[str, Any]) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = []
    provenance = _short_status(result["provenance"])
    if provenance:
        messages.append(("info", provenance))
    for warning in result["warnings"]:
        warning_text = _short_status(warning)
        if warning_text:
            messages.append(("warn", warning_text))
    return messages


def _clean_option_values(values: Any) -> list[str]:
    cleaned = [str(value).strip() for value in values if str(value or "").strip()]
    return sorted(dict.fromkeys(cleaned))


def _scope_rows_from_results(*results: dict[str, Any] | None) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for result in results:
        if not result:
            continue
        districts = result.get("districts")
        if not isinstance(districts, pd.DataFrame) or districts.empty:
            continue
        if not {"state", "district"}.issubset(districts.columns):
            continue
        frames.append(districts[["state", "district"]].copy())

    if not frames:
        return pd.DataFrame(columns=["state", "district"])
    rows = pd.concat(frames, ignore_index=True).dropna(how="all")
    rows["state"] = rows["state"].astype(str).str.strip()
    rows["district"] = rows["district"].astype(str).str.strip()
    return rows[(rows["state"] != "") | (rows["district"] != "")]


def _state_options(*results: dict[str, Any] | None) -> list[str]:
    scope_rows = _scope_rows_from_results(*results)
    data_states = _clean_option_values(scope_rows["state"]) if not scope_rows.empty else []
    states = sorted(dict.fromkeys([*INDIA_STATE_OPTIONS, *data_states]))
    return [ALL_STATES_LABEL, *states]


def _district_options(state_focus: str, *results: dict[str, Any] | None) -> list[str]:
    scope_rows = _scope_rows_from_results(*results)
    if scope_rows.empty:
        return [ALL_DISTRICTS_LABEL]

    if state_focus and state_focus != ALL_STATES_LABEL:
        scope_rows = scope_rows[scope_rows["state"].str.casefold() == state_focus.casefold()]

    districts = _clean_option_values(scope_rows["district"])
    return [ALL_DISTRICTS_LABEL, *districts]


def _state_filter_value(state_focus: str) -> str:
    return "" if state_focus == ALL_STATES_LABEL else state_focus.strip()


def _district_filter_value(district_focus: str) -> str:
    return "" if district_focus == ALL_DISTRICTS_LABEL else district_focus.strip()


@st.cache_data(show_spinner=False, ttl=900)
def _run_plan_cached(
    mission_key: str,
    state_focus: str,
    district_focus: str,
    confidence_label: str,
) -> dict[str, Any]:
    return run_agent(
        mission_type=mission_key,
        mission_label=MISSION_OPTIONS[mission_key],
        state_filter=_state_filter_value(state_focus),
        district_filter=_district_filter_value(district_focus),
        confidence_threshold=CONFIDENCE_OPTIONS[confidence_label],
        run_id=f"{mission_key}:{state_focus}:{district_focus}:{confidence_label}",
    )


def _run_plan(
    mission_key: str,
    state_focus: str,
    district_focus: str,
    confidence_label: str,
) -> dict[str, Any]:
    result = _run_plan_cached(mission_key, state_focus, district_focus, confidence_label)
    result["run_id"] = str(uuid.uuid4())
    return result


def _ensure_starter_result() -> None:
    if st.session_state.get("starter_scan_done"):
        return

    try:
        with st.spinner(f"Loading {DEFAULT_DISTRICT_FOCUS}, {DEFAULT_STATE_FOCUS}..."):
            st.session_state.starter_result = _run_plan(
                mission_key="maternal_health",
                state_focus=DEFAULT_STATE_FOCUS,
                district_focus=DEFAULT_DISTRICT_FOCUS,
                confidence_label="Weak Evidence",
            )
            if st.session_state.latest_result is None:
                st.session_state.latest_result = st.session_state.starter_result
    except Exception as exc:
        st.session_state.starter_error = str(exc)
    finally:
        st.session_state.starter_scan_done = True


def _map_jump_target(point: dict[str, Any]) -> tuple[str, str, str] | None:
    district = str(point.get("district") or point.get("label") or "").strip()
    state = str(point.get("state") or point.get("region") or "").strip()
    kind = str(point.get("kind") or "Map point").strip()
    if not district:
        return None
    return state or ALL_STATES_LABEL, district, kind


def _queue_map_jump(point: dict[str, Any] | None) -> None:
    if not point:
        return

    target = _map_jump_target(point)
    if target is None:
        return

    state, district, kind = target
    selection_key = f"{kind}|{state}|{district}".casefold()
    already_focused = (
        st.session_state.get("map_jump_selection_key") == selection_key
        and st.session_state.get("state_focus") == state
        and st.session_state.get("district_focus") == district
    )
    if already_focused:
        return

    st.session_state.pending_map_jump = {"state": state, "district": district, "kind": kind}
    st.session_state.map_jump_selection_key = selection_key
    st.rerun()


def _apply_pending_map_jump() -> None:
    pending_jump = st.session_state.pop("pending_map_jump", None)
    if not isinstance(pending_jump, dict):
        return

    state = str(pending_jump.get("state") or ALL_STATES_LABEL).strip() or ALL_STATES_LABEL
    district = str(pending_jump.get("district") or ALL_DISTRICTS_LABEL).strip() or ALL_DISTRICTS_LABEL
    kind = str(pending_jump.get("kind") or "map point").strip().lower()
    st.session_state.state_focus = state
    st.session_state.district_focus = district

    try:
        with st.spinner(f"Focusing {district} from the map..."):
            st.session_state.latest_result = _run_plan(
                mission_key=st.session_state.mission_key,
                state_focus=state,
                district_focus=district,
                confidence_label=st.session_state.confidence_label,
            )
        st.session_state.map_jump_message = f"Showing {district}, {state} from the selected {kind}."
    except Exception:
        st.session_state.map_jump_message = "Could not rebuild the plan from that map point. Try the State and District filters."


def _build_filtered_plan() -> None:
    st.session_state.latest_result = _run_plan(
        mission_key=st.session_state.mission_key,
        state_focus=st.session_state.state_focus,
        district_focus=st.session_state.district_focus,
        confidence_label=st.session_state.confidence_label,
    )


def _render_page_jump() -> None:
    active_page = str(st.session_state.get("app_page", APP_PAGE_LIVE))
    if active_page == "Introduction":
        active_page = APP_PAGE_INTRO
        st.session_state.app_page = APP_PAGE_INTRO
    _, right = st.columns([0.72, 0.28], gap="large")
    with right:
        label = "Back To Referral Planner" if active_page == APP_PAGE_INTRO else "Product Introduction"
        if st.button(label, width="stretch"):
            st.session_state.app_page = APP_PAGE_LIVE if active_page == APP_PAGE_INTRO else APP_PAGE_INTRO
            st.rerun()


def _render_top_controls() -> tuple[str, str, str, str, bool]:
    starter_result = st.session_state.get("starter_result")
    latest_result = st.session_state.get("latest_result")
    state_options = _state_options(starter_result, latest_result)
    if st.session_state.state_focus not in state_options:
        st.session_state.state_focus = DEFAULT_STATE_FOCUS

    district_options = _district_options(st.session_state.state_focus, starter_result, latest_result)
    if st.session_state.district_focus not in district_options:
        st.session_state.district_focus = DEFAULT_DISTRICT_FOCUS if DEFAULT_DISTRICT_FOCUS in district_options else ALL_DISTRICTS_LABEL

    st.markdown(
        (
            "<section class='db-command-strip'>"
            "<div>"
            "<div class='db-section-label'>Filters</div>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    cols = st.columns([1.04, 0.98, 0.98, 0.92, 0.84, 0.66], gap="medium")
    with cols[0]:
        mission_key = st.selectbox("Care need", list(MISSION_OPTIONS), format_func=MISSION_OPTIONS.get, key="mission_key")
    with cols[1]:
        state_focus = st.selectbox("State", state_options, key="state_focus")
    with cols[2]:
        district_options = _district_options(state_focus, starter_result, latest_result)
        if st.session_state.district_focus not in district_options:
            st.session_state.district_focus = DEFAULT_DISTRICT_FOCUS if DEFAULT_DISTRICT_FOCUS in district_options else ALL_DISTRICTS_LABEL
        district_focus = st.selectbox("District", district_options, key="district_focus")
    with cols[3]:
        confidence_label = st.selectbox("Minimum certainty", list(CONFIDENCE_OPTIONS), key="confidence_label")
    with cols[4]:
        st.markdown("<div class='db-control-spacer'></div>", unsafe_allow_html=True)
        run_button = st.button(
            "Build Referral Plan",
            type="primary",
            on_click=_build_filtered_plan,
            width="stretch",
        )
    with cols[5]:
        st.markdown("<div class='db-control-spacer'></div>", unsafe_allow_html=True)
        clear_button = st.button("Clear Filters", width="stretch")

    if clear_button:
        st.session_state.mission_key = "maternal_health"
        st.session_state.state_focus = DEFAULT_STATE_FOCUS
        st.session_state.district_focus = DEFAULT_DISTRICT_FOCUS
        st.session_state.confidence_label = "Weak Evidence"
        st.session_state.latest_result = st.session_state.get("starter_result")
        st.rerun()

    filter_pills(
        [
            ("Need", MISSION_OPTIONS[str(mission_key)]),
            ("State", state_focus),
            ("District", district_focus),
            ("Minimum certainty", _confidence_label(confidence_label)),
        ]
    )
    map_jump_message = st.session_state.pop("map_jump_message", "")
    if map_jump_message:
        st.success(map_jump_message)

    return mission_key, state_focus, district_focus, confidence_label, run_button


def _show_recommendation_alert(result: dict[str, Any] | None) -> None:
    if result is None:
        message = escape(st.session_state.get("starter_error", "The starter district scan is still loading."))
        st.markdown(
            (
                "<section class='db-alert-strip'>"
                "<div><div class='db-alert-kicker'>Recommended next move</div>"
                "<h2>Starter district scan unavailable</h2>"
                f"<p>{message}</p></div>"
                "</section>"
            ),
            unsafe_allow_html=True,
        )
        return

    packet = result.get("mission_packet", {})
    trace = result.get("mission_control_trace", [])
    lead_district = _display_text(packet.get("lead_district"), "No district selected")
    lead_state = _display_text(packet.get("lead_state"), "")
    action = _decision_label(packet.get("action_state", "verify first"))
    next_action = _display_text(packet.get("next_verification_action"), "Review the packet before saving.")
    lead_anchor = _display_text(packet.get("lead_anchor"), "No lead anchor selected")
    confidence = _confidence_label(packet.get("confidence", result.get("confidence_label", "Weak Evidence")))
    citation_status = _citation_status(packet.get("citation_status"))
    location = f"{lead_district}, {lead_state}".strip().strip(",")

    alert_items = [
        next_action,
    ]
    list_html = "".join(f"<li>{escape(item)}</li>" for item in alert_items if item)
    stat_html = "".join(
        (
            "<div class='db-alert-stat'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            "</div>"
        )
        for label, value in [
            ("Data used", _data_coverage_text(result)),
            ("Lead anchor", lead_anchor),
            ("Confidence", confidence),
            ("Citations", citation_status),
        ]
    )

    st.markdown(
        (
            "<section class='db-alert-strip'>"
            "<div class='db-alert-main'>"
            "<div class='db-alert-kicker'>Recommended next move</div>"
            f"<h2>{escape(action)}: {escape(location)}</h2>"
            f"<ul>{list_html}</ul>"
            "</div>"
            f"<div class='db-alert-stats'>{stat_html}</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _open_caution_reason() -> None:
    st.session_state.caution_reason_open = True


def _set_stage_view(view: str) -> None:
    if view in STAGE_VIEWS:
        st.session_state.stage_view_radio = view


def _show_caution_expander(summary: str) -> None:
    if not st.session_state.get("caution_reason_open", False):
        st.button(
            "Show why the recommendation is cautious",
            key="show_caution_reason_button",
            on_click=_open_caution_reason,
            width="stretch",
        )
        return

    st.markdown(
        (
            "<section class='db-caution-panel'>"
            "<div class='db-card-title'>Why the recommendation is cautious</div>"
            "<div class='db-caution-summary'>"
            f"<p>{escape(_plain_review_summary(summary))}</p>"
            "<ul>"
            "<li>Review the visible support details before shortlisting.</li>"
            "<li>The weakest check sets the recommended action.</li>"
            "</ul>"
            "</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )
    st.button(
        "Open Why This Place",
        key="open_why_this_place",
        on_click=_set_stage_view,
        args=("Why This Place",),
        width="stretch",
    )


def _review_label_legend() -> None:
    st.markdown(
        (
            "<section class='db-label-legend'>"
            "<span><strong>Pass</strong> enough support for the plan</span>"
            "<span><strong>Review</strong> verify before action</span>"
            "<span><strong>Hold</strong> wait for stronger evidence</span>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _show_product_intro_page(starter_result: dict[str, Any] | None) -> None:
    st.markdown(
        (
            "<section class='db-intro-hero'>"
            "<div class='db-alert-kicker'>Product introduction</div>"
            "<h2>Care Convoy helps an operations lead choose the next referral move.</h2>"
            "<p>It turns imperfect facility and district evidence into a cautious recommendation: where to start, which facility to review first, and what must be verified before action.</p>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    tabs = st.tabs(INTRO_TABS)

    with tabs[0]:
        card_grid(
            [
                {
                    "title": "Who it serves",
                    "body": "A non-technical operations lead planning specialty medical referrals in India.",
                    "caption": "The app is written for action, not analysis jargon.",
                },
                {
                    "title": "Decision it improves",
                    "body": "Choose a priority district and a lead referral anchor, then decide whether to shortlist, verify first, or hold.",
                    "caption": "The answer is useful only when the uncertainty is visible.",
                },
                {
                    "title": "What it returns",
                    "body": "A referral plan with a map, facility comparison, source support, and a saved verification note.",
                    "caption": "Every high-stakes claim is cited or downgraded.",
                },
                {
                    "title": "What changed",
                    "body": "Clear filters, one navigation path, plain-language labels, score scales, and no internal system readouts in the product flow.",
                    "caption": "The interface now optimizes for first-glance understanding.",
                },
            ],
            columns=4,
        )
        action_panel(
            "Fast read",
            "Use this page when you need the product story in under a minute.",
            [
                "Start in Plan to see the recommended next move.",
                "Open Why This Place to see which evidence check needs attention.",
                "Open Compare Anchors when choosing between facilities.",
                "Open Evidence Details before trusting a facility claim.",
                "Open Save Review Note to keep a follow-up note.",
            ],
        )

    with tabs[1]:
        steps = [
            ("1", "Choose the situation", "Pick the care need, state, district, and minimum certainty."),
            ("2", "Read the recommendation", "See the priority place, lead facility, confidence, and next action."),
            ("3", "Check the reason", "Review the pass, review, or hold checks behind the recommendation."),
            ("4", "Compare anchors", "Compare facilities on urgency support, facility fit, and trust support."),
            ("5", "Inspect evidence", "Read citation rows, website status, duplicate clues, and weak-evidence warnings."),
            ("6", "Save the review note", "Record what to verify before the facility moves forward."),
        ]
        step_html = "".join(
            (
                "<section class='db-pipeline-step'>"
                f"<span>{escape(number)}</span>"
                f"<div><strong>{escape(title)}</strong><p>{escape(body)}</p></div>"
                "</section>"
            )
            for number, title, body in steps
        )
        st.markdown(f"<div class='db-pipeline'>{step_html}</div>", unsafe_allow_html=True)
        action_panel(
            "What the product does not claim",
            "The app stays cautious where the evidence is thin.",
            [
                "No travel-time routing denominator is active.",
                "Population context is planned, not used for the current ranking.",
                "Weak source evidence is downgraded instead of hidden.",
                "The provided facility dataset remains the source of truth.",
                "A saved review note is not an automatic deployment order.",
            ],
        )

    with tabs[2]:
        if starter_result:
            packet = starter_result.get("mission_packet", {})
            card_grid(
                [
                    {
                        "title": "Current starter action",
                        "body": _decision_label(packet.get("action_state", "review")),
                        "caption": _display_text(packet.get("next_verification_action"), "Review before saving."),
                    },
                    {
                        "title": "Citation status",
                        "body": _citation_status(packet.get("citation_status")),
                        "caption": "Recommendation claims are qualified when citation rows are missing.",
                    },
                    {
                        "title": "Uncertainty label",
                        "body": _confidence_label(packet.get("confidence", starter_result.get("confidence_label", "Weak Evidence"))),
                        "caption": "Weak evidence appears as a product signal, not a hidden caveat.",
                    },
                ],
                columns=3,
            )
        bullet_card(
            "Where support appears",
            [
                "District context cites NFHS and facility-density provenance.",
                "Facility claims show source URL rows when available.",
                "Evidence Details shows website status and duplicate-review flags.",
                "Why This Place explains which check caused a review or hold.",
            ],
            "Evidence is readable without opening project files.",
        )

    with tabs[3]:
        card_grid(
            [
                {
                    "title": "Visible filters",
                    "body": "Care need, state, district, and certainty controls are visible on the first screen.",
                    "caption": "No hidden setup popover.",
                },
                {
                    "title": "One navigation path",
                    "body": "The planner uses a single view selector instead of two parallel controls.",
                    "caption": "The selected view is always authoritative.",
                },
                {
                    "title": "Plain language",
                    "body": "Tables and labels avoid raw field names, JSON-style values, and missing-value tokens.",
                    "caption": "Scores include scale and meaning.",
                },
                {
                    "title": "Separated modules",
                    "body": "Plan, reason, comparison, evidence, and review-note capture each have their own view.",
                    "caption": "No module has to compete with another one.",
                },
            ],
            columns=4,
        )
        bullet_card(
            "Product improvements",
            [
                "Removes first-page review-room language.",
                "Makes filters visible at first glance.",
                "Removes internal system readouts from the product flow.",
                "Makes repeated facts use the same wording wherever they appear.",
            ],
            "The product still relies on the provided facility dataset and cautious evidence rules.",
        )


def _gate_counts(trace: list[dict[str, str]]) -> dict[str, int]:
    counts = {"pass": 0, "review": 0, "block": 0}
    for item in trace:
        gate = item.get("gate", "review")
        if gate in counts:
            counts[gate] += 1
    return counts


def _gate_badge(gate: str) -> str:
    tone = GATE_TONES.get(gate, "warn")
    label = GATE_LABELS.get(gate, "Review")
    return f"<span class='db-gate db-gate-{escape(tone)}'>{escape(label)}</span>"


def _agent_label(value: Any) -> str:
    text = _display_text(value, "Citation Review")
    return AGENT_LABELS.get(text, text.replace("_", " ").title())


def _mission_packet_items(packet: dict[str, Any]) -> list[dict[str, str]]:
    return [
        {
            "title": "Lead district",
            "body": f"{packet.get('lead_district', 'No district')}, {packet.get('lead_state', '')}",
            "caption": _shorten(packet.get("nfhs_signals", "NFHS context unavailable")),
        },
        {
            "title": "Lead anchor",
            "body": str(packet.get("lead_anchor", "No lead anchor")),
            "caption": f"Backup: {packet.get('backup_anchor', 'No backup anchor')}",
        },
        {
            "title": "Coverage context",
            "body": _shorten(packet.get("facility_density_context", "Facility density unavailable")),
            "caption": str(packet.get("population_context_status", "Population context unavailable")),
        },
        {
            "title": "Next action",
            "body": str(packet.get("next_verification_action", "Review this packet before saving.")),
            "caption": f"Citations: {_citation_status(packet.get('citation_status'))}",
        },
    ]


def _render_tool_steps() -> None:
    html = "".join(
        (
            "<div class='db-step-card'>"
            f"<span class='db-step-dot'>{index}</span>"
            f"<div><div class='db-step-title'>{escape(label)}</div>"
            f"<div class='db-step-detail'>{escape(detail)}</div></div>"
            "</div>"
        )
        for index, (label, detail) in enumerate(RUN_STEPS, start=1)
    )
    st.markdown(f"<section class='db-step-stack'>{html}</section>", unsafe_allow_html=True)


def _show_mission_control(result: dict[str, Any]) -> None:
    trace = result.get("mission_control_trace") or result.get("review_board", [])
    packet = result.get("mission_packet", {})
    left, right = st.columns([1.15, 0.85], gap="large")

    with left:
        st.markdown("<div class='db-section-label'>Why this recommendation</div>", unsafe_allow_html=True)
        _review_label_legend()
        for item in trace:
            gate = item.get("gate", "review")
            reason = item.get("blocking_reason") or item.get("handoff", "")
            st.markdown(
                (
                    "<section class='db-agent-row'>"
                    f"{_gate_badge(gate)}"
                    "<div class='db-agent-main'>"
                    f"<div class='db-agent-title'>{escape(_agent_label(item.get('agent')))}</div>"
                    f"<div class='db-agent-role'>{escape(_plain_trace_text(item.get('role'), 'Review step'))}</div>"
                    f"<div class='db-agent-evidence'>{escape(_plain_trace_text(item.get('evidence'), 'No evidence text available.'))}</div>"
                    f"<div class='db-agent-handoff'>{escape(_plain_trace_text(reason, 'No additional action needed.'))}</div>"
                    "</div>"
                    "</section>"
                ),
                unsafe_allow_html=True,
            )

    with right:
        action = _decision_label(packet.get("action_state", "review"))
        bullet_card(
            f"Recommended action: {action}",
            [
                f"Next: {_display_text(packet.get('next_verification_action'), result.get('board_summary', 'Review first.'))}",
                f"Certainty: {_confidence_label(packet.get('confidence', result.get('confidence_label', 'Weak Evidence')))}",
                f"Citations: {_citation_status(packet.get('citation_status'))}",
                f"Support: {_gate_summary_text(trace)}",
            ],
            "Review before saving.",
        )
        _render_tool_steps()
        status_stack(_result_status_messages(result))


def _shortlist_display(saved: pd.DataFrame) -> pd.DataFrame:
    if saved.empty or "metadata_json" not in saved.columns:
        return saved
    display = saved.copy()
    metadata = display["metadata_json"].apply(_parse_metadata)
    display["board_verdict"] = metadata.apply(lambda value: value.get("board_verdict", ""))
    display["board_confidence"] = metadata.apply(lambda value: value.get("board_confidence", ""))
    display["facility_name"] = metadata.apply(lambda value: value.get("facility_name", ""))
    display["packet_action"] = metadata.apply(
        lambda value: value.get("mission_packet", {}).get("action_state", value.get("board_verdict", ""))
    )
    pretty = pd.DataFrame(
        {
            "Saved": display["created_at"].apply(lambda value: _display_text(value)),
            "Care Need": display["mission_type"].apply(lambda value: _display_text(value)),
            "District": display["district"].apply(lambda value: _display_text(value)),
            "Facility": display["facility_name"].apply(lambda value: _display_text(value, "Facility not recorded")),
            "Follow-up Status": display["decision"].apply(_decision_label),
            "Planner Suggestion": display["packet_action"].apply(_decision_label),
            "Confidence": display["board_confidence"].apply(lambda value: _confidence_label(value)),
            "Note": display["note"].apply(lambda value: _display_text(value, "No note recorded")),
        }
    )
    return pretty


def _saved_review_cards(saved: pd.DataFrame) -> list[dict[str, str]]:
    display = _shortlist_display(saved)
    cards: list[dict[str, str]] = []
    for row in display.head(6).to_dict("records"):
        facility = _display_text(row.get("Facility"), "Facility not recorded")
        district = _display_text(row.get("District"), "District not recorded")
        status = _display_text(row.get("Follow-up Status"), "Needs Verification")
        suggestion = _display_text(row.get("Planner Suggestion"), "Review before action")
        cards.append(
            {
                "title": facility,
                "body": _display_text(row.get("Note"), "No note recorded."),
                "caption": f"{district}. Follow-up: {status}. Planner suggestion: {suggestion}.",
            }
        )
    return cards


def _local_saved_decisions(limit: int = 8) -> pd.DataFrame:
    rows = st.session_state.setdefault("local_user_decisions", [])
    if not rows:
        return pd.DataFrame(columns=USER_DECISION_COLUMNS)
    return pd.DataFrame(rows, columns=USER_DECISION_COLUMNS).head(limit)


def _saved_decisions(limit: int = 8) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    if lakebase_available():
        saved = list_user_decisions(limit=limit)
        if not saved.empty:
            frames.append(saved)
    local_saved = _local_saved_decisions(limit=limit)
    if not local_saved.empty:
        frames.append(local_saved)
    if not frames:
        return pd.DataFrame(columns=USER_DECISION_COLUMNS)
    combined = pd.concat(frames, ignore_index=True)
    return combined.head(limit)


def _save_local_decision(
    *,
    run_id: str,
    mission_type: str,
    district: str,
    facility_id: str,
    decision: str,
    note: str,
    metadata: dict[str, Any],
) -> None:
    rows = st.session_state.setdefault("local_user_decisions", [])
    row = {
        "created_at": pd.Timestamp.now(tz="UTC").isoformat(),
        "mission_type": mission_type,
        "district": district,
        "facility_id": facility_id,
        "decision": decision,
        "note": note,
        "metadata_json": json.dumps(metadata),
        "run_id": run_id,
    }
    rows[:] = [
        existing
        for existing in rows
        if not (existing.get("run_id") == run_id and existing.get("facility_id") == facility_id)
    ]
    rows.insert(0, row)


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _citation_display(citations: pd.DataFrame) -> pd.DataFrame:
    if citations.empty:
        return pd.DataFrame(columns=["Claim", "Evidence", "Source"])
    display = citations.copy()
    claim_values = display.get("claim_type", pd.Series([""] * len(display), dtype=str))
    evidence_values = display.get("evidence", pd.Series([""] * len(display), dtype=str))
    return pd.DataFrame(
        {
            "Claim": claim_values.apply(_plain_label),
            "Evidence": [
                evidence_sentence(claim_type, evidence)
                for claim_type, evidence in zip(claim_values, evidence_values, strict=False)
            ],
            "Source": display.get("source_url", pd.Series(dtype=str)).apply(lambda value: _display_text(value, "Source link not available")),
        }
    )


def _render_citation_notes(citations: pd.DataFrame) -> None:
    if citations.empty:
        card(
            "Source notes",
            "No source notes are available for this selection yet.",
            "Review facility details before action.",
        )
        return

    grouped_cards: list[str] = []
    for facility_name, rows in citations.groupby("facility_name", sort=False):
        items = []
        for row in rows.itertuples(index=False):
            items.append(
                (
                    "<li>"
                    f"<strong>{escape(claim_label(getattr(row, 'claim_type', 'Source note')))}</strong>"
                    f"<span>{escape(evidence_sentence(getattr(row, 'claim_type', ''), getattr(row, 'evidence', '')))}</span>"
                    f"<em>{escape(source_note(getattr(row, 'source_url', '')))}</em>"
                    "</li>"
                )
            )
        grouped_cards.append(
            (
                "<section class='db-evidence-card'>"
                f"<div class='db-card-title'>{escape(_display_text(facility_name, 'Source notes'))}</div>"
                f"<ul class='db-evidence-list'>{''.join(items)}</ul>"
                "</section>"
            )
        )

    st.markdown(f"<section class='db-evidence-stack'>{''.join(grouped_cards)}</section>", unsafe_allow_html=True)


def _trust_review_cards(trust_reviews: pd.DataFrame, limit: int = 4) -> list[dict[str, str]]:
    cards: list[dict[str, str]] = []
    for review in trust_reviews.head(limit).itertuples(index=False):
        cards.append(
            {
                "title": _display_text(getattr(review, "facility_name", ""), "Facility not named"),
                "body": (
                    f"Review status: {_plain_label(getattr(review, 'review_status', 'review'))}. "
                    f"Website: {_website_status(getattr(review, 'website_verification_status', 'Not checked'))}. "
                    f"Trust support: {_score_text(getattr(review, 'trust_score_v2', None), meaning='higher means stronger facility evidence')}."
                ),
                "caption": _display_text(
                    getattr(review, "risk_flags", "")
                    or getattr(review, "entity_match_reasons", "")
                    or "No extra review notes."
                ),
            }
        )
    return cards


def _web_evidence_display(search_results: pd.DataFrame) -> pd.DataFrame:
    if search_results.empty:
        return pd.DataFrame(columns=["Facility", "Website Evidence", "Domain", "Match Certainty"])
    return pd.DataFrame(
        {
            "Facility": search_results["facility_name"].apply(lambda value: _display_text(value, "Facility not named")),
            "Website Evidence": search_results["selection_source"].apply(_source_label),
            "Domain": search_results["result_domain"].apply(lambda value: _display_text(value, "Domain not available")),
            "Match Certainty": search_results["match_confidence"].apply(
                lambda value: _score_text(float(value) * 100, meaning='higher means a stronger website match')
            ),
        }
    )


def _show_overview(result: dict[str, Any]) -> None:
    _render_top_controls()

    districts = result["districts"]
    facilities = result["facilities"]
    trust_reviews = result["trust_reviews"]
    top_district = districts.iloc[0] if not districts.empty else None
    top_facility = facilities.iloc[0] if not facilities.empty else None
    packet = result.get("mission_packet", {})

    left, right = st.columns(2, gap="large")
    with left:
        selected_map_point = render_map(districts, facilities, height=405)
        _queue_map_jump(selected_map_point)
        st.markdown(
            "<p class='db-map-caption'>Facility points show anchors being reviewed for credibility.</p>",
            unsafe_allow_html=True,
        )
        if top_district is not None:
            nfhs_summary = str(top_district.get("nfhs_need_summary", "") or "")
            bullet_card(
                f"Highest-need district: {top_district['district']}, {top_district['state']}",
                [
                    _need_read(top_district["need_score"]),
                    _coverage_read(top_district["coverage_gap"]),
                    _support_read(top_district["evidence_score"], top_district.get("uncertainty_label")),
                    _district_summary_text(nfhs_summary),
                ],
                "Use this as a starting point before contacting facilities.",
            )

    with right:
        plan_items: list[str] = []
        if top_district is not None:
            plan_items.append(f"Priority place: {top_district['district']}, {top_district['state']}")
        if top_facility is not None:
            plan_items.extend(
                [
                    f"Lead referral anchor: {top_facility['name']}",
                    f"Facility fit: {_score_text(top_facility['capability_fit'], meaning='higher means better mission fit')}",
                    f"Evidence certainty: {_confidence_label(top_facility['confidence_label'])}",
                    f"Website status: {_website_status(top_facility['website_verification_status'])}",
                ]
            )
        if result.get("warnings"):
            warning = _short_status(result["warnings"][0])
            if warning:
                plan_items.append(f"Caution: {warning}")
        bullet_card("Referral plan", plan_items)
        inline_metrics(
            [
                ("Care need", result["mission_label"]),
                ("Recommended action", _decision_label(packet.get("action_state", "review"))),
                (
                    "Lead website status",
                    _website_status(top_facility["website_verification_status"]) if top_facility is not None else "Not checked",
                ),
            ]
        )
        if top_facility is not None:
            bullet_card(
                f"Lead referral anchor: {top_facility['name']}",
                [
                    f"Facility fit: {_score_text(top_facility['capability_fit'], meaning='higher means better mission fit')}",
                    f"Trust support: {_score_text(top_facility['trust_score'], meaning='higher means stronger facility evidence')}",
                    f"Duplicate clues: {_count_text(top_facility['entity_record_count'], 'matching record')}",
                    f"Website status: {_website_status(top_facility['website_verification_status'])}",
                ],
                top_facility["risk_flags"] or "No facility review flags.",
            )
        if result.get("board_summary"):
            _show_caution_expander(result["board_summary"])


def _show_review_board(result: dict[str, Any]) -> None:
    board = result.get("review_board", [])
    if not board:
        st.info("The decision audit appears once a referral plan has been built.")
        return

    board_frame = pd.DataFrame(board)
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.dataframe(
            board_frame[["agent", "verdict", "confidence", "evidence"]],
            width="stretch",
            hide_index=True,
            height=300,
        )
        cards = [
            {
                "title": row["agent"],
                "body": f"{row['role']} Verdict: {row['verdict']}.",
                "caption": row["handoff"],
            }
            for row in board[:4]
        ]
        card_grid(cards)

    with right:
        supervisor = board[-1]
        card(
            "Supervisor packet",
            result.get("board_summary", "The board has not produced a final packet yet."),
            f"Final confidence: {supervisor['confidence']}",
        )
        action_panel(
            "How the decision audit works",
            "One gate per risk.",
            [
                "Need Scout: district demand.",
                "Supply Mapper: facility density.",
                "Facility Scout: anchor fit.",
                "Trust Verifier: website and entity checks.",
                "Evidence Auditor: citation safety.",
                "Supervisor: final action.",
            ],
        )


def _show_anchors(result: dict[str, Any]) -> None:
    districts = result["districts"]
    facilities = result["facilities"]
    if facilities.empty and districts.empty:
        st.info("No facility options are available yet. Try broadening the state or district filter.")
        return

    left, right = st.columns([1.05, 1], gap="large")
    with left:
        if districts.empty:
            st.info("District demand context is not available for this run.")
        else:
            chart = build_confidence_chart(districts, "district", "priority_score")
            if chart is not None:
                chart.update_layout(height=350, margin=dict(l=8, r=8, t=8, b=8))
                st.plotly_chart(chart, width="stretch")

    with right:
        if facilities.empty:
            st.info("No facility options are available yet. Try a broader place filter.")
            return

        cards: list[dict[str, str]] = []
        for row in facilities.head(4).itertuples(index=False):
            cards.append(
                {
                    "title": row.name,
                    "body": (
                        f"{row.address_city}, {row.address_stateOrRegion}. "
                        f"Trust support {_score_text(row.trust_score, meaning='higher means stronger facility evidence')}. "
                        f"Facility fit {_score_text(row.capability_fit, meaning='higher means better mission fit')}."
                    ),
                    "caption": _display_text(row.risk_flags or _confidence_label(row.confidence_label)),
                }
            )
        card_grid(cards)

    if facilities.empty:
        st.info("No facility options are available yet. Try a broader place filter.")
        return

    for row in facilities.head(4).itertuples(index=False):
        with st.expander(f"{row.name} ({row.address_city}, {row.address_stateOrRegion})", expanded=False):
            stats = st.columns(4)
            stats[0].metric("Facility Fit (0-100)", f"{row.capability_fit:.0f}", help="Higher means a better match for the selected care need.")
            stats[1].metric("Trust Support (0-100)", f"{row.trust_score:.0f}", help="Higher means stronger facility evidence.")
            stats[2].metric("Evidence Certainty", _confidence_label(row.confidence_label))
            stats[3].metric("Duplicate Clues", int(row.entity_record_count), help="More matching records can mean a stronger match or a duplicate-review need.")
            st.caption(f"Website status: {_website_status(row.website_verification_status)}")
            st.write(_display_text(row.description, "No facility description is available yet."))
            if row.primary_url:
                st.write(f"Website checked: {row.primary_url}")
            if row.website_excerpt:
                st.caption(row.website_excerpt)
            if row.risk_flags:
                st.caption(f"Warnings: {row.risk_flags}")

            citations = result["citations"]
            facility_citations = citations[citations["facility_id"] == row.unique_id]
            if not facility_citations.empty:
                _render_citation_notes(facility_citations)

def _show_trust_desk(result: dict[str, Any]) -> None:
    trust_reviews = result["trust_reviews"]
    if trust_reviews is None or trust_reviews.empty:
        st.info("Evidence Details appears once facility candidates are available.")
        return

    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.markdown("<div class='db-section-label'>Facility support details</div>", unsafe_allow_html=True)
        card_grid(_trust_review_cards(trust_reviews), columns=2)

    with right:
        bullet_card(
            "How to read the support details",
            [
                "Duplicate clues show whether similar facility rows need review.",
                "Website status shows whether a public site supports the facility claim.",
                "Trust support is a 0-100 score; higher means stronger facility evidence.",
                "The recommendation stays cautious when citations are missing.",
            ],
            "Trust supports. It does not replace judgment.",
        )
        _render_citation_notes(result["citations"])
        search_results = result.get("search_results")
        if search_results is not None and not search_results.empty:
            st.dataframe(
                _web_evidence_display(search_results),
                width="stretch",
                hide_index=True,
                height=180,
            )

def _show_shortlist(result: dict[str, Any]) -> None:
    saved = _saved_decisions(limit=8)
    top_facility = result["facilities"].head(1)
    top_district = result["districts"].head(1)
    left, right = st.columns([1.1, 0.9], gap="large")
    with left:
        feedback = st.session_state.pop("save_feedback", "")
        if feedback:
            st.success(feedback)
        if not saved.empty:
            st.markdown("<div class='db-section-label'>Saved review notes</div>", unsafe_allow_html=True)
            card_grid(_saved_review_cards(saved), columns=1)
        else:
            card(
                "No review notes saved yet",
                "Save what the team should verify before shortlisting this facility.",
                "Saved in this browser session when Lakebase is not configured.",
            )

    with right:
        if top_facility.empty or top_district.empty:
            return

        candidate = top_facility.iloc[0]
        district = top_district.iloc[0]
        board_agents = result.get("review_board", [])
        supervisor = board_agents[-1] if board_agents else {}
        mission_packet = result.get("mission_packet", {})
        default_note = (
            f"Example: Verify {candidate['name']} in {district['district']} before shortlisting. "
            "Confirm the current services, referral contact, and whether the website or source text supports the care need."
        )
        bullet_card(
            "Review note draft",
            [
                f"Facility to review: {candidate['name']}",
                f"Place: {district['district']}, {district['state']}",
                f"Source support: {_confidence_label(candidate['confidence_label'])}",
                "Use this note to capture what must be checked next.",
            ],
            f"Current review flag: {_plain_label(candidate['risk_flags'], 'No extra review flag')}.",
        )

        with st.form("save_review_note"):
            note = st.text_area("Review note", value=default_note, height=130)
            decision_options = decision_options_for_packet(mission_packet)
            decision = st.selectbox("Follow-up status", decision_options, format_func=_decision_label)
            submitted = st.form_submit_button("Save Review Note")

        if submitted:
            run_id = result["run_id"]
            payload = {
                "district": district["district"],
                "state": district["state"],
                "facility_name": candidate["name"],
                "confidence_label": candidate["confidence_label"],
                "resolved_entity_id": candidate["resolved_entity_id"],
                "website_verification_status": candidate["website_verification_status"],
                "board_summary": result.get("board_summary", ""),
                "board_verdict": supervisor.get("verdict", ""),
                "board_confidence": supervisor.get("confidence", ""),
                "board_agents": [agent["agent"] for agent in board_agents],
                "mission_packet": result.get("mission_packet", {}),
                "mission_control_trace": result.get("mission_control_trace", []),
                "cache_sources": result.get("cache_sources", {}),
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
            if not saved_ok:
                _save_local_decision(
                    run_id=run_id,
                    mission_type=result["mission_label"],
                    district=district["district"],
                    facility_id=str(candidate["unique_id"]),
                    decision=decision,
                    note=note,
                    metadata=payload,
                )
            st.session_state.save_feedback = (
                "Review note saved."
                if saved_ok
                else "Review note saved in this browser session."
            )
            st.rerun()


def _stage_selector() -> str:
    pending_view = st.session_state.pop("pending_stage_view", "")
    if pending_view in STAGE_VIEWS:
        st.session_state.stage_view_radio = pending_view
    default_view = st.session_state.get("stage_view_radio", "Plan")
    if default_view not in STAGE_VIEWS:
        default_view = "Plan"
        st.session_state.stage_view_radio = default_view
    selected_view = st.radio(
        "Choose a view",
        STAGE_VIEWS,
        index=STAGE_VIEWS.index(default_view),
        horizontal=True,
        key="stage_view_radio",
    )
    if selected_view not in STAGE_VIEWS:
        selected_view = "Plan"
        st.session_state.stage_view_radio = selected_view
    return selected_view


def _render_stage(view: str, result: dict[str, Any]) -> None:
    if view == "Why This Place":
        _show_mission_control(result)
    elif view == "Plan":
        _show_overview(result)
    elif view == "Compare Anchors":
        _show_anchors(result)
    elif view == "Evidence Details":
        _show_trust_desk(result)
    else:
        _show_shortlist(result)


def _render_story_path(active_view: str) -> None:
    steps = [
        ("Plan", "Recommendation"),
        ("Why This Place", "Gate trace"),
        ("Compare Anchors", "Facility fit"),
        ("Evidence Details", "Sources"),
        ("Save Review Note", "Review note"),
    ]
    html = "".join(
        (
            f"<div class='db-story-step{' active' if label == active_view else ''}'>"
            f"<strong>{escape(label)}</strong>"
            f"<span>{escape(caption)}</span>"
            "</div>"
        )
        for label, caption in steps
    )
    st.markdown(f"<section class='db-story-path'>{html}</section>", unsafe_allow_html=True)


st.set_page_config(page_title="Care Convoy", layout="wide", initial_sidebar_state="collapsed")
inject_theme()

st.session_state.setdefault("latest_result", None)
st.session_state.setdefault("starter_result", None)
st.session_state.setdefault("starter_error", "")
st.session_state.setdefault("starter_scan_done", False)
st.session_state.setdefault("app_page", APP_PAGE_LIVE)
st.session_state.setdefault("mission_key", "maternal_health")
st.session_state.setdefault("state_focus", DEFAULT_STATE_FOCUS)
st.session_state.setdefault("district_focus", DEFAULT_DISTRICT_FOCUS)
st.session_state.setdefault("confidence_label", "Weak Evidence")

if st.session_state.get("control_surface_version") != "district-startup":
    st.session_state.control_surface_version = "district-startup"
    st.session_state.state_focus = DEFAULT_STATE_FOCUS
    st.session_state.district_focus = DEFAULT_DISTRICT_FOCUS
    st.session_state.confidence_label = "Weak Evidence"
    st.session_state.stage_view = "Plan"
    st.session_state.stage_view_radio = "Plan"

_hero()
_ensure_starter_result()

if st.session_state.app_page == APP_PAGE_INTRO:
    _render_page_jump()
    _show_product_intro_page(st.session_state.get("starter_result"))
    _render_footer()
    st.stop()

_apply_pending_map_jump()

result = st.session_state.latest_result or st.session_state.get("starter_result")
_show_recommendation_alert(result)

if result is None:
    _show_empty_state()
else:
    selected_view = _stage_selector()
    _render_stage(selected_view, result)

_render_page_jump()
_render_footer()
