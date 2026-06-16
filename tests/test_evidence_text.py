from __future__ import annotations

from src.ui.evidence_text import evidence_sentence


def test_evidence_sentence_humanizes_json_like_lists() -> None:
    sentence = evidence_sentence(
        "specialties",
        '["internalMedicine","internalMedicine","reproductiveEndocrinology","gynaecology"]',
    )

    assert sentence == (
        "Listed specialties include Internal medicine, reproductive endocrinology, and gynaecology."
    )
    assert "[" not in sentence
    assert '"' not in sentence
    assert "internalMedicine" not in sentence
