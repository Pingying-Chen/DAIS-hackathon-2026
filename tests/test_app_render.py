from __future__ import annotations

from streamlit.testing.v1 import AppTest


def test_app_initial_render_is_stable() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Build Referral Plan" for button in app.button)
