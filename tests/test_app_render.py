from __future__ import annotations

import os

from streamlit.testing.v1 import AppTest

from src.ui.decision_options import decision_options_for_packet

os.environ["DATABRICKS_WAREHOUSE_ID"] = ""


def test_app_initial_render_is_stable() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Build Referral Plan" for button in app.button)
    assert any(button.label == "Product Introduction" for button in app.button)
    assert any(button.label == "Clear Filters" for button in app.button)
    assert any(selectbox.label == "State" for selectbox in app.selectbox)
    assert any(selectbox.label == "District" for selectbox in app.selectbox)
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    first_page_text = " ".join([rendered_markdown, *[button.label for button in app.button]])
    assert "Care Convoy · Referral planning for India" in rendered_markdown
    assert "A referral planning tool that helps health teams find where specialty care is most needed" in rendered_markdown
    assert "Recommended next move" in rendered_markdown
    assert "Filters" in rendered_markdown
    assert rendered_markdown.index("Recommended next move") < rendered_markdown.index("Filters")
    assert rendered_markdown.index("Filters") < rendered_markdown.index("Facility points show")
    assert "Need score:" not in rendered_markdown
    assert "Coverage gap:" not in rendered_markdown
    assert "Evidence support:" not in rendered_markdown
    assert "No district health summary available." not in rendered_markdown
    assert "Source support:" in rendered_markdown
    assert "Some live data is unavailable" not in rendered_markdown
    assert "sample rows" not in rendered_markdown.casefold()
    assert "Sample website evidence" not in rendered_markdown
    assert "For Operations lead" not in rendered_markdown
    assert "Evidence rule" not in rendered_markdown
    assert "Pingying Chen, Zihang Liang" in rendered_markdown
    assert "Author: Pingying Chen" not in rendered_markdown
    assert "Co-author: Zihang Liang" not in rendered_markdown
    assert any(button.label == "Show why the recommendation is cautious" for button in app.button)
    assert "judge" not in first_page_text.casefold()
    assert "v8" not in first_page_text.casefold()


def test_caution_reveal_opens_the_detail_view() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)
    next(button for button in app.button if button.label == "Show why the recommendation is cautious").click()
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "The weakest check sets the recommended action." in rendered_markdown
    assert any(button.label == "Open Why This Place" for button in app.button)

    next(button for button in app.button if button.label == "Open Why This Place").click()
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "Why this recommendation" in rendered_markdown
    assert '<div class="db-card-title">Referral plan</div>' not in rendered_markdown


def test_view_selector_changes_rendered_module() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert '<div class="db-card-title">Referral plan</div>' in rendered_markdown

    view_selector = next(radio for radio in app.radio if radio.label == "Choose a view")
    view_selector.set_value("Why This Place")
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "Why this recommendation" in rendered_markdown
    assert '<div class="db-card-title">Referral plan</div>' not in rendered_markdown

    view_selector = next(radio for radio in app.radio if radio.label == "Choose a view")
    view_selector.set_value("Evidence Details")
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "Facility support details" in rendered_markdown
    assert "How to read the support details" in rendered_markdown


def test_save_review_note_view_uses_review_wording() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)
    view_selector = next(radio for radio in app.radio if radio.label == "Choose a view")
    view_selector.set_value("Save Review Note")
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    visible_text = " ".join(
        [
            rendered_markdown,
            *[button.label for button in app.button],
            *[text_area.label for text_area in app.text_area],
            *[selectbox.label for selectbox in app.selectbox],
        ]
    )
    assert "Review note draft" in rendered_markdown
    assert "No review notes saved yet" in rendered_markdown
    assert "Saved notes are unavailable in this session" not in visible_text
    assert "Saved in this browser session" in rendered_markdown
    assert "Example: Verify" in app.text_area[0].value
    assert any(text_area.label == "Review note" for text_area in app.text_area)
    assert any(selectbox.label == "Follow-up status" for selectbox in app.selectbox)
    assert any(button.label == "Save Review Note" for button in app.button)
    assert "Decision status" not in visible_text
    assert "Save shortlist item" not in visible_text
    assert "Save Decision" not in visible_text


def test_compare_view_uses_compact_score_wording() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)
    view_selector = next(radio for radio in app.radio if radio.label == "Choose a view")
    view_selector.set_value("Compare Anchors")
    app.run(timeout=20)

    assert not app.exception
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "/100" in rendered_markdown
    assert "Urgency support" not in rendered_markdown
    assert "Comparison signal" not in rendered_markdown
    assert "on a 0-100 scale" not in rendered_markdown
    assert "higher means better mission fit" not in rendered_markdown


def test_product_introduction_renders_from_planner_home() -> None:
    app = AppTest.from_file("src/app.py")

    app.run(timeout=20)
    next(button for button in app.button if button.label == "Product Introduction").click()
    app.run(timeout=20)

    assert not app.exception
    assert any(button.label == "Back To Referral Planner" for button in app.button)
    rendered_markdown = "\n".join(markdown.value for markdown in app.markdown)
    assert "Care Convoy helps an operations lead choose the next referral move." in rendered_markdown
    assert "What changed" in rendered_markdown
    assert "Product improvements" in rendered_markdown
    assert "Choose the situation" in rendered_markdown
    assert "Version 8" not in rendered_markdown
    assert "v8" not in rendered_markdown.casefold()
    assert "backend" not in rendered_markdown.casefold()


def test_decision_options_follow_mission_packet_action() -> None:
    assert decision_options_for_packet({"action_state": "hold"}) == ["hold", "needs verification"]
    assert decision_options_for_packet({"action_state": "verify first"}) == ["needs verification", "hold"]
    assert decision_options_for_packet({"action_state": "shortlist"}) == ["approved", "needs verification", "hold"]
