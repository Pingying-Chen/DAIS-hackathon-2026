from __future__ import annotations

import pandas as pd

from src.viz import maps


def test_render_map_returns_selected_facility_and_enables_selection(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_pydeck_chart(deck: object, **kwargs: object) -> dict[str, object]:
        captured["deck"] = deck
        captured["kwargs"] = kwargs
        return {
            "selection": {
                "objects": {
                    "facility-points": [
                        {
                            "kind": "Facility",
                            "label": "Nithya Hospital",
                            "district": "Nagpur",
                            "state": "Maharashtra",
                        }
                    ]
                }
            }
        }

    monkeypatch.setattr(maps.st, "pydeck_chart", fake_pydeck_chart)

    selected = maps.render_map(
        pd.DataFrame(
            [
                {
                    "latitude": 21.1458,
                    "longitude": 79.0882,
                    "district": "Nagpur",
                    "state": "Maharashtra",
                }
            ]
        ),
        pd.DataFrame(
            [
                {
                    "latitude": 21.1458,
                    "longitude": 79.0882,
                    "name": "Nithya Hospital",
                    "address_city": "Nagpur",
                    "address_stateOrRegion": "Maharashtra",
                }
            ]
        ),
        height=405,
    )

    kwargs = captured["kwargs"]
    deck = captured["deck"]

    assert selected == {"kind": "Facility", "label": "Nithya Hospital", "district": "Nagpur", "state": "Maharashtra"}
    assert kwargs["on_select"] == "rerun"
    assert kwargs["selection_mode"] == "single-object"
    assert kwargs["key"] == "planner_map"
    assert kwargs["height"] == 405
    assert [layer.id for layer in deck.layers] == ["facility-points"]


def test_render_map_ignores_district_points_when_facility_coordinates_are_missing(monkeypatch) -> None:
    messages: list[str] = []

    def fake_pydeck_chart(deck: object, **kwargs: object) -> dict[str, object]:
        raise AssertionError("district-only coordinates should not render a map")

    monkeypatch.setattr(maps.st, "pydeck_chart", fake_pydeck_chart)
    monkeypatch.setattr(maps.st, "info", lambda message: messages.append(str(message)))

    selected = maps.render_map(
        pd.DataFrame(
            [
                {
                    "latitude": 21.1458,
                    "longitude": 79.0882,
                    "district": "Nagpur",
                    "state": "Maharashtra",
                }
            ]
        ),
        pd.DataFrame(),
        height=405,
    )

    assert selected is None
    assert messages == ["Facility coordinates are not available yet for this result set."]
