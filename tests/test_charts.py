from __future__ import annotations

import pandas as pd

from src.viz.charts import build_tradeoff_chart


def test_build_tradeoff_chart_ignores_dataframe_attrs_with_nested_frames() -> None:
    facilities = pd.DataFrame(
        [
            {
                "name": "Anchor Hospital",
                "urgency_support": 82.0,
                "capability_fit": 88.0,
                "trust_score": 79.0,
            },
            {
                "name": "Referral Clinic",
                "urgency_support": 66.0,
                "capability_fit": 71.0,
                "trust_score": 62.0,
            },
        ]
    )
    facilities.attrs["trust_reviews"] = pd.DataFrame([{"facility_name": "Anchor Hospital"}])

    chart = build_tradeoff_chart(facilities)

    assert chart is not None
