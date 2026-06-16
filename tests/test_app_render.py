from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.ui.decision_options import decision_options_for_packet


def test_app_initial_render_is_stable() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Build Referral Plan" for button in app.button)
    assert any(button.label == "For Judges" for button in app.button)
    assert any(selectbox.label == "State" for selectbox in app.selectbox)
    assert any(selectbox.label == "District" for selectbox in app.selectbox)
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "v7 feedback-cache view" in rendered_markdown
    assert "Recommended next move" in rendered_markdown
    assert "Current question" in rendered_markdown


def test_judge_proof_room_renders_from_operator_home() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)
    next(button for button in app.button if button.label == "For Judges").click()
    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Back To Operator Demo" for button in app.button)
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "Interactive proof room for the backend story" in rendered_markdown
    assert "Three-minute app-led pitch" in rendered_markdown
    assert "Append-Only Score Cache" in rendered_markdown


def test_decision_options_follow_mission_packet_action() -> None:
    assert decision_options_for_packet({"action_state": "hold"}) == ["hold", "needs verification"]
    assert decision_options_for_packet({"action_state": "verify first"}) == ["needs verification", "hold"]
    assert decision_options_for_packet({"action_state": "shortlist"}) == ["approved", "needs verification", "hold"]
