from __future__ import annotations

from streamlit.testing.v1 import AppTest

from src.ui.decision_options import decision_options_for_packet


def test_app_initial_render_is_stable() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Build Referral Plan" for button in app.button)
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "v5.2 Mission Control" in rendered_markdown
    assert "Mission Control opens here" in rendered_markdown


def test_decision_options_follow_mission_packet_action() -> None:
    assert decision_options_for_packet({"action_state": "hold"}) == ["hold", "needs verification"]
    assert decision_options_for_packet({"action_state": "verify first"}) == ["needs verification", "hold"]
    assert decision_options_for_packet({"action_state": "shortlist"}) == ["approved", "needs verification", "hold"]
