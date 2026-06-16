from __future__ import annotations

import json
from html import escape
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
from src.ui.components import action_panel, bullet_card, card, card_grid, filter_pills, hero_header, inline_metrics, kpi_row, status_stack
from src.ui.decision_options import decision_options_for_packet
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

ALL_STATES_LABEL = "All India"
ALL_DISTRICTS_LABEL = "All districts"

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

STAGE_VIEWS = ["Map + Packet", "Mission Control", "Anchor Review", "Trust Evidence", "Shortlist"]
INTRO_TABS = ["How To Use", "Pipeline", "Evidence", "Demo"]

GATE_LABELS = {
    "pass": "Pass",
    "review": "Review",
    "block": "Block",
}

GATE_TONES = {
    "pass": "positive",
    "review": "warn",
    "block": "accent",
}

RUN_STEPS = [
    ("Need Scout", "Loaded NFHS district indicators and scored need."),
    ("Supply Mapper", "Joined facility density through pincode and district context."),
    ("Facility Scout", "Ranked lead and backup referral anchors from provided facilities."),
    ("Trust Verifier", "Checked entity resolution, website status, and trust signals."),
    ("Evidence Auditor", "Checked citation rows and uncertainty downgrades."),
    ("Mission Strategist", "Converted gate outcomes into an operator-ready mission action."),
    ("Supervisor", "Derived the mission packet action from the weakest gate."),
]


def _format_metric(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value)


def _shorten(value: Any, limit: int = 110) -> str:
    text = str(value or "").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 3].rstrip() + "..."


def _bullet_items(value: str, max_items: int = 6) -> list[str]:
    lines = [line.strip().lstrip("-*• ").strip() for line in value.splitlines()]
    items = [line.rstrip(".") for line in lines if line]
    if len(items) <= 1:
        chunks = value.replace(";", ".").split(".")
        items = [chunk.strip().rstrip(".") for chunk in chunks if chunk.strip()]
    return [_shorten(item, 120) for item in items[:max_items]]


def _short_status(message: str) -> str:
    if message.startswith("Live Databricks SQL"):
        return "Live data. Trust Desk included."
    if message.startswith("Demo-safe fallback"):
        return "Demo-safe fallback."
    if message.startswith("Mixed sources"):
        return message.replace(" + ", " + ")
    if message.startswith("District prioritization"):
        return "District source: fallback."
    if message.startswith("Facility ranking"):
        return "Facility source: fallback."
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
        eyebrow="Track 3 Referral Copilot · v5.3 Mission Control",
        title="Care Convoy Mission Control",
        subtitle="Plan the next referral move. Check need, supply, trust, and evidence. Save only after review.",
        chips=[
            ("Author", "Pingying Chen"),
            ("Co-author", "Zihang Liang"),
            ("User", "Virtue operations lead"),
            ("Decision", "Next referral move"),
            ("Mode", "Pass / review / block"),
            ("Save", "Lakebase shortlist"),
        ],
    )


def _summary_metrics(result: dict[str, Any] | None) -> None:
    if result is None:
        items = [
            {"label": "Mission Control", "value": "Ready", "value_class": "db-kpi-accent", "note": "Choose care need. Run plan."},
            {"label": "Track", "value": "3", "note": "Referral Copilot. Trust support."},
            {"label": "Data Path", "value": "Virtue", "note": "Facilities. NFHS. Pincodes."},
            {"label": "Persistence", "value": "Lakebase", "note": "Saved decisions reload."},
        ]
    else:
        trust_reviews = result.get("trust_reviews")
        verified_count = 0
        if trust_reviews is not None and not trust_reviews.empty:
            verified_count = int(trust_reviews["website_verification_status"].eq("verified").sum())
        packet = result.get("mission_packet", {})
        trace = result.get("mission_control_trace", [])
        gate_counts = _gate_counts(trace)
        items = [
            {"label": "Packet Action", "value": str(packet.get("action_state", "review")).title(), "value_class": "db-kpi-accent", "note": "Weakest gate decides."},
            {"label": "Gate Mix", "value": f"{gate_counts['pass']}/{gate_counts['review']}/{gate_counts['block']}", "note": "Pass / review / block."},
            {"label": "Priority Districts", "value": str(len(result["districts"])), "note": "Live district rows."},
            {"label": "Candidate Anchors", "value": str(len(result["facilities"])), "note": "Ranked facilities."},
            {"label": "Verified Websites", "value": str(verified_count), "note": "Trust support signal."},
        ]
    kpi_row(items)


def _show_empty_state() -> None:
    card_grid(
        [
            {
                "title": "Mission Control opens here",
                "body": "Build a plan. Review gates. Save a packet.",
                "caption": "v5.3 keeps humans in control.",
            },
            {
                "title": "Population context is planned",
                "body": "Not active yet. Rankings stay dataset-backed.",
                "caption": "Intentional demo scope.",
            },
        ]
    )


def _result_status_messages(result: dict[str, Any]) -> list[tuple[str, str]]:
    messages: list[tuple[str, str]] = [("info", _short_status(result["provenance"]))]
    if result.get("summary_source"):
        messages.append(("info", f"Brief: {result['summary_source']}"))
    messages.extend(("warn", _short_status(warning)) for warning in result["warnings"])
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


def _run_plan(
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
        run_id=str(uuid.uuid4()),
    )


def _ensure_national_result() -> None:
    if st.session_state.get("national_scan_done"):
        return

    try:
        with st.spinner("Loading the India-wide alert..."):
            st.session_state.national_result = _run_plan(
                mission_key="maternal_health",
                state_focus=ALL_STATES_LABEL,
                district_focus=ALL_DISTRICTS_LABEL,
                confidence_label="Weak Evidence",
            )
            if st.session_state.latest_result is None:
                st.session_state.latest_result = st.session_state.national_result
    except Exception as exc:
        st.session_state.national_error = str(exc)
    finally:
        st.session_state.national_scan_done = True


def _render_page_jump() -> None:
    active_page = str(st.session_state.get("app_page", "Live Demo"))
    _, right = st.columns([0.72, 0.28], gap="large")
    with right:
        label = "Back To Live Demo" if active_page == "Introduction" else "Open App Introduction"
        if st.button(label, use_container_width=True):
            st.session_state.app_page = "Live Demo" if active_page == "Introduction" else "Introduction"
            st.rerun()


def _render_top_controls() -> tuple[str, str, str, str, bool]:
    national_result = st.session_state.get("national_result")
    latest_result = st.session_state.get("latest_result")
    state_options = _state_options(national_result, latest_result)
    if st.session_state.state_focus not in state_options:
        st.session_state.state_focus = ALL_STATES_LABEL

    district_options = _district_options(st.session_state.state_focus, national_result, latest_result)
    if st.session_state.district_focus not in district_options:
        st.session_state.district_focus = ALL_DISTRICTS_LABEL

    st.markdown(
        (
            "<section class='db-control-copy'>"
            "<div class='db-section-label'>Mission setup</div>"
            "<p>Start with the India-wide alert, then narrow the referral plan only when a judge asks about a place.</p>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    cols = st.columns([1.1, 1, 1, 1, 0.92, 0.72], gap="medium")
    with cols[0]:
        mission_key = st.selectbox("Care need", list(MISSION_OPTIONS), format_func=MISSION_OPTIONS.get, key="mission_key")
    with cols[1]:
        state_focus = st.selectbox("State", state_options, key="state_focus")
    with cols[2]:
        district_options = _district_options(state_focus, national_result, latest_result)
        if st.session_state.district_focus not in district_options:
            st.session_state.district_focus = ALL_DISTRICTS_LABEL
        district_focus = st.selectbox("District", district_options, key="district_focus")
    with cols[3]:
        confidence_label = st.select_slider("Minimum certainty", options=list(CONFIDENCE_OPTIONS), key="confidence_label")
    with cols[4]:
        st.write("")
        run_button = st.button("Build Referral Plan", type="primary", use_container_width=True)
    with cols[5]:
        st.write("")
        clear_button = st.button("Clear", use_container_width=True)

    if clear_button:
        st.session_state.mission_key = "maternal_health"
        st.session_state.state_focus = ALL_STATES_LABEL
        st.session_state.district_focus = ALL_DISTRICTS_LABEL
        st.session_state.confidence_label = "Weak Evidence"
        st.session_state.latest_result = st.session_state.get("national_result")
        st.rerun()

    lakebase = lakebase_status()
    filter_pills(
        [
            ("Active need", MISSION_OPTIONS[str(mission_key)]),
            ("Active state", state_focus),
            ("Active district", district_focus),
            ("Shortlist", "Lakebase" if lakebase_available() else "Not configured"),
        ]
    )
    with st.popover("How To Use"):
        st.markdown(
            "- Read the India-wide alert first.\n"
            "- Use State and District only when narrowing the story.\n"
            "- Click **Build Referral Plan** to re-rank the map and packet.\n"
            "- Open **Mission Control** to see why the app says save, verify, or hold.\n"
            "- Save from **Shortlist** only after reviewing trust evidence."
        )
        st.caption(lakebase["detail"])

    return mission_key, state_focus, district_focus, confidence_label, run_button


def _show_national_alert(result: dict[str, Any] | None) -> None:
    if result is None:
        message = escape(st.session_state.get("national_error", "The India-wide scan is still loading."))
        st.markdown(
            (
                "<section class='db-alert-strip'>"
                "<div><div class='db-alert-kicker'>Most important India alert</div>"
                "<h2>National scan unavailable</h2>"
                f"<p>{message}</p></div>"
                "</section>"
            ),
            unsafe_allow_html=True,
        )
        return

    packet = result.get("mission_packet", {})
    trace = result.get("mission_control_trace", [])
    gate_counts = _gate_counts(trace)
    lead_district = str(packet.get("lead_district", "No district"))
    lead_state = str(packet.get("lead_state", ""))
    action = str(packet.get("action_state", "verify first")).title()
    warning = _short_status(result["warnings"][0]) if result.get("warnings") else "No blocking warning in the national scan."
    next_action = str(packet.get("next_verification_action", "Review the packet before saving."))
    lead_anchor = str(packet.get("lead_anchor", "No lead anchor"))
    confidence = str(packet.get("confidence", result.get("confidence_label", "Weak Evidence")))
    citation_status = str(packet.get("citation_status", "unknown"))
    location = f"{lead_district}, {lead_state}".strip().strip(",")

    alert_items = [
        f"Start with {location} for {result['mission_label']}.",
        warning,
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
            ("Action", action),
            ("Lead anchor", lead_anchor),
            ("Confidence", confidence),
            ("Gates", f"{gate_counts['pass']} pass · {gate_counts['review']} review · {gate_counts['block']} block"),
            ("Citations", citation_status),
        ]
    )

    st.markdown(
        (
            "<section class='db-alert-strip'>"
            "<div class='db-alert-main'>"
            "<div class='db-alert-kicker'>Most important India alert</div>"
            f"<h2>{escape(action)}: {escape(location)}</h2>"
            f"<ul>{list_html}</ul>"
            "</div>"
            f"<div class='db-alert-stats'>{stat_html}</div>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )


def _show_intro_page(national_result: dict[str, Any] | None) -> None:
    st.markdown(
        (
            "<section class='db-intro-hero'>"
            "<div class='db-alert-kicker'>In-app introduction</div>"
            "<h2>Care Convoy helps an operations lead choose the next referral move.</h2>"
            "<p>The demo starts with an India-wide alert, then shows how evidence, uncertainty, trust checks, and persistence turn messy facility data into a cautious action.</p>"
            "</section>"
        ),
        unsafe_allow_html=True,
    )

    tabs = st.tabs(INTRO_TABS)

    with tabs[0]:
        action_panel(
            "How a non-technical user should use the app",
            "Follow this order during the judge conversation.",
            [
                "Read the India-wide alert first.",
                "Use State and District only if the judge asks to narrow the map.",
                "Click Build Referral Plan to re-rank districts and facility anchors.",
                "Open Mission Control to see pass, review, and block gates.",
                "Open Trust Evidence before saving any shortlist item.",
            ],
        )
        card_grid(
            [
                {
                    "title": "Map + Packet",
                    "body": "Shows the priority district, lead anchor, backup anchor, next action, and cited cautions.",
                    "caption": "Use it as the first live demo screen.",
                },
                {
                    "title": "Mission Control",
                    "body": "Shows seven agent gates so judges can see why the plan says shortlist, verify first, or hold.",
                    "caption": "This is the trust moment.",
                },
                {
                    "title": "Anchor Review",
                    "body": "Compares facility candidates by fit, trust, confidence, and evidence rows.",
                    "caption": "Use it when judges ask why this facility.",
                },
                {
                    "title": "Shortlist",
                    "body": "Saves a decision and verification note through Lakebase so action persists after interaction.",
                    "caption": "This proves the app is operational.",
                },
            ],
            columns=4,
        )

    with tabs[1]:
        steps = [
            ("1", "Provided data", "Facilities, NFHS district health indicators, and India pincode geography are read from the Virtue Foundation catalog."),
            ("2", "Need and supply", "NFHS signals and facility density identify where need is high and supply evidence is thin."),
            ("3", "Trust and evidence", "Facility anchors are checked for fit, duplicate risk, website status, source URLs, and claim citations."),
            ("4", "Mission Control", "Seven gates convert evidence into shortlist, verify-first, or hold guidance."),
            ("5", "Persistence", "The chosen packet, gate trace, facility, district, and note are saved to Lakebase."),
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
            "What the pipeline is not claiming",
            "The demo is intentionally honest about scope.",
            [
                "No travel-time routing denominator is active.",
                "Population context is planned, not used for ranking.",
                "Weak source evidence is downgraded instead of hidden.",
                "The provided facility dataset remains the source of truth.",
            ],
        )

    with tabs[2]:
        if national_result:
            packet = national_result.get("mission_packet", {})
            card_grid(
                [
                    {
                        "title": "Current national action",
                        "body": str(packet.get("action_state", "review")).title(),
                        "caption": str(packet.get("next_verification_action", "Review before saving.")),
                    },
                    {
                        "title": "Citation status",
                        "body": str(packet.get("citation_status", "unknown")),
                        "caption": "Recommendation claims are qualified when citation rows are missing.",
                    },
                    {
                        "title": "Uncertainty label",
                        "body": str(packet.get("confidence", national_result.get("confidence_label", "Weak Evidence"))),
                        "caption": "Weak evidence appears as a product signal, not a hidden caveat.",
                    },
                ],
                columns=3,
            )
        bullet_card(
            "Evidence surfaces in the app",
            [
                "District context cites NFHS and facility-density provenance.",
                "Facility claims show source URL rows when available.",
                "Trust Evidence shows website status and duplicate-review flags.",
                "Mission Control explains which gate caused a review or hold.",
            ],
            "Judges can inspect evidence without reading code.",
        )

    with tabs[3]:
        action_panel(
            "Three-minute judge path",
            "Lead with the workflow, then prove the build.",
            [
                "0:00 - Name Track 3 Referral Copilot and show the India alert.",
                "0:25 - Build or refresh one referral plan.",
                "1:05 - Open Mission Control and explain the weakest gate.",
                "1:45 - Open Trust Evidence for citations and uncertainty.",
                "2:20 - Save a shortlist decision with a note.",
                "2:45 - Close on Databricks Apps, Unity Catalog, Lakebase, and MLflow evaluation.",
            ],
        )
        card_grid(
            [
                {
                    "title": "Author",
                    "body": "Pingying Chen",
                    "caption": "Care Convoy submission.",
                },
                {
                    "title": "Co-author",
                    "body": "Zihang Liang",
                    "caption": "Care Convoy submission.",
                },
            ],
            columns=2,
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
            "caption": f"Citations: {packet.get('citation_status', 'unknown')}",
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
        st.markdown("<div class='db-section-label'>Agent gate trace</div>", unsafe_allow_html=True)
        with st.popover("Terms"):
            st.markdown(
                "- **Gate:** pass, review, or block.\n"
                "- **Density:** mapped facility supply.\n"
                "- **Citation safety:** claim has source evidence.\n"
                "- **Strategist:** turns gates into action."
            )
        for item in trace:
            gate = item.get("gate", "review")
            reason = item.get("blocking_reason") or item.get("handoff", "")
            st.markdown(
                (
                    "<section class='db-agent-row'>"
                    f"{_gate_badge(gate)}"
                    "<div class='db-agent-main'>"
                    f"<div class='db-agent-title'>{escape(item.get('agent', 'Agent'))}</div>"
                    f"<div class='db-agent-role'>{escape(item.get('role', ''))}</div>"
                    f"<div class='db-agent-evidence'>{escape(item.get('evidence', ''))}</div>"
                    f"<div class='db-agent-handoff'>{escape(reason)}</div>"
                    "</div>"
                    "</section>"
                ),
                unsafe_allow_html=True,
            )

    with right:
        action = str(packet.get("action_state", "review")).title()
        bullet_card(
            f"Supervisor action: {action}",
            [
                f"Next: {packet.get('next_verification_action', result.get('board_summary', 'Review first.'))}",
                f"Confidence: {packet.get('confidence', result.get('confidence_label', 'Weak Evidence'))}",
                f"Citations: {packet.get('citation_status', 'unknown')}",
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
    return display[
        [
            "created_at",
            "mission_type",
            "district",
            "facility_name",
            "decision",
            "packet_action",
            "board_confidence",
            "note",
        ]
    ]


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if not raw:
        return {}
    try:
        parsed = json.loads(str(raw))
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _show_overview(result: dict[str, Any]) -> None:
    districts = result["districts"]
    facilities = result["facilities"]
    trust_reviews = result["trust_reviews"]
    top_district = districts.iloc[0] if not districts.empty else None
    top_facility = facilities.iloc[0] if not facilities.empty else None
    top_trust_review = trust_reviews.iloc[0] if trust_reviews is not None and not trust_reviews.empty else None
    packet = result.get("mission_packet", {})

    left, right = st.columns(2, gap="large")
    with left:
        render_map(districts, facilities, height=405)
        st.markdown(
            "<p class='db-map-caption'>District points show demand context; facility points show anchors being reviewed for credibility.</p>",
            unsafe_allow_html=True,
        )
        if top_district is not None:
            district_caption = top_district["uncertainty_label"]
            density_context = str(top_district.get("facility_density_context", "") or "")
            nfhs_summary = str(top_district.get("nfhs_need_summary", "") or "")
            if density_context:
                district_caption = f"{district_caption}. {_shorten(density_context, 90)}"
            bullet_card(
                f"Highest-need district: {top_district['district']}, {top_district['state']}",
                [
                    f"Need score: {top_district['need_score']:.1f}",
                    f"Coverage gap: {top_district['coverage_gap']:.1f}",
                    f"Evidence score: {top_district['evidence_score']:.1f}",
                    _shorten(nfhs_summary, 92),
                ],
                district_caption,
            )

    with right:
        bullet_card("Mission packet", _bullet_items(result["summary"]), _short_status(result["provenance"]))
        inline_metrics(
            [
                ("Care need", result["mission_label"]),
                ("Packet action", str(packet.get("action_state", "review")).title()),
                ("Shortlist mode", "Lakebase" if lakebase_available() else "Not configured"),
                (
                    "Lead website status",
                    str(top_trust_review["website_verification_status"]) if top_trust_review is not None else "n/a",
                ),
            ]
        )
        if top_facility is not None:
            bullet_card(
                f"Lead referral anchor: {top_facility['name']}",
                [
                    f"Fit: {top_facility['capability_fit']:.0f}",
                    f"Trust: {top_facility['trust_score']:.0f}",
                    f"Entity rows: {int(top_facility['entity_record_count'])}",
                    f"Website: {top_facility['website_verification_status']}",
                ],
                top_facility["risk_flags"] or "No facility review flags.",
            )
        if result.get("board_summary"):
            bullet_card(
                "Mission Control v5.3",
                [
                    _shorten(result["board_summary"], 90),
                    "Seven visible gates.",
                    "Weakest gate sets action.",
                ],
                "Review before saving.",
            )
        status_stack(_result_status_messages(result)[:2])

    if packet:
        card_grid(_mission_packet_items(packet), columns=4)

    bottom_left, bottom_right = st.columns(2, gap="large")
    with bottom_left:
        action_panel(
            "What to do next",
            "Review in this order.",
            [
                "Check Mission Control gates.",
                "Compare anchor candidates.",
                "Review trust evidence.",
                "Save only after verification.",
            ],
        )
    with bottom_right:
        status_stack(_result_status_messages(result)[2:5])


def _show_review_board(result: dict[str, Any]) -> None:
    board = result.get("review_board", [])
    if not board:
        st.info("Mission Control appears once a referral plan has been built.")
        return

    board_frame = pd.DataFrame(board)
    left, right = st.columns([1.15, 0.85], gap="large")
    with left:
        st.dataframe(
            board_frame[["agent", "verdict", "confidence", "evidence"]],
            use_container_width=True,
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
            "How Mission Control decides",
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
                        f"{row.address_city}, {row.address_stateOrRegion}. Trust {row.trust_score:.0f}. Fit {row.capability_fit:.0f}."
                    ),
                    "caption": _shorten(row.risk_flags or row.confidence_label),
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
                    "body": f"Status {review.review_status}. Website {review.website_verification_status}. Trust {review.trust_score_v2:.0f}.",
                    "caption": _shorten(review.risk_flags or review.entity_match_reasons or "No extra review notes."),
                }
            )
        card_grid(cards)

    with right:
        bullet_card(
            "How the trust support layer works",
            [
                "Merge likely duplicate rows.",
                "Check selected public website.",
                "Use dataset social signals.",
                "Support the referral choice.",
            ],
            "Trust supports. It does not replace judgment.",
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
            st.dataframe(_shortlist_display(saved), use_container_width=True, hide_index=True, height=310)
        else:
            card(
                "No shortlist entries yet",
                "Save after trust review.",
                "Persistence proves action.",
            )

    with right:
        if top_facility.empty or top_district.empty:
            return

        candidate = top_facility.iloc[0]
        district = top_district.iloc[0]
        board_agents = result.get("review_board", [])
        supervisor = board_agents[-1] if board_agents else {}
        mission_packet = result.get("mission_packet", {})
        default_note = f"Review {candidate['name']} for {district['district']} as the first referral anchor."
        bullet_card(
            "Ready to save",
            [
                f"Anchor: {candidate['name']}",
                f"District: {district['district']}, {district['state']}",
                f"Confidence: {candidate['confidence_label']}",
                "Save only after trust review.",
            ],
            _shorten(candidate["risk_flags"] or "No extra risk flags."),
        )

        with st.form("save_shortlist"):
            note = st.text_area("Verification note", value=default_note, height=110)
            decision_options = decision_options_for_packet(mission_packet)
            decision = st.selectbox("Decision status", decision_options)
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
                "board_summary": result.get("board_summary", ""),
                "board_verdict": supervisor.get("verdict", ""),
                "board_confidence": supervisor.get("confidence", ""),
                "board_agents": [agent["agent"] for agent in board_agents],
                "mission_packet": result.get("mission_packet", {}),
                "mission_control_trace": result.get("mission_control_trace", []),
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
            default="Map + Packet",
            selection_mode="single",
            label_visibility="collapsed",
            key="stage_view",
        )
        return selected or "Map + Packet"

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
    if view == "Mission Control":
        _show_mission_control(result)
    elif view == "Map + Packet":
        _show_overview(result)
    elif view == "Anchor Review":
        _show_anchors(result)
    elif view == "Trust Evidence":
        _show_trust_desk(result)
    else:
        _show_shortlist(result)


st.set_page_config(page_title="Care Convoy", layout="wide", initial_sidebar_state="collapsed")
inject_theme()

st.session_state.setdefault("latest_result", None)
st.session_state.setdefault("national_result", None)
st.session_state.setdefault("national_error", "")
st.session_state.setdefault("national_scan_done", False)
st.session_state.setdefault("app_page", "Live Demo")
st.session_state.setdefault("mission_key", "maternal_health")
st.session_state.setdefault("state_focus", ALL_STATES_LABEL)
st.session_state.setdefault("district_focus", ALL_DISTRICTS_LABEL)
st.session_state.setdefault("confidence_label", "Weak Evidence")

if st.session_state.get("control_surface_version") != "top-controls-v1":
    st.session_state.control_surface_version = "top-controls-v1"
    st.session_state.state_focus = ALL_STATES_LABEL
    st.session_state.district_focus = ALL_DISTRICTS_LABEL
    st.session_state.confidence_label = "Weak Evidence"

_hero()
_render_page_jump()
_ensure_national_result()

if st.session_state.app_page == "Introduction":
    _show_intro_page(st.session_state.get("national_result"))
    st.stop()

mission_key, state_focus, district_focus, confidence_label, run_button = _render_top_controls()

if run_button:
    with st.spinner("Running agent gates..."):
        st.session_state.latest_result = _run_plan(mission_key, state_focus, district_focus, confidence_label)

_show_national_alert(st.session_state.get("national_result"))

result = st.session_state.latest_result or st.session_state.get("national_result")
_summary_metrics(result)

if result is None:
    _show_empty_state()
else:
    _render_stage(_stage_selector(), result)
