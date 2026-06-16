from __future__ import annotations

import colorsys
import re
from typing import Any

import pandas as pd
import pydeck as pdk
import streamlit as st

from src.ui.theme import tokens

_HSL_PATTERN = re.compile(r"hsla?\(([^)]+)\)")


def _css_hsl_to_rgb(color: str) -> list[int]:
    match = _HSL_PATTERN.match(color.strip())
    if not match:
        return [37, 99, 235]

    parts = [part.strip().replace("%", "") for part in match.group(1).split(",")]
    if len(parts) < 3:
        return [37, 99, 235]

    hue = (float(parts[0]) % 360) / 360
    saturation = max(0.0, min(float(parts[1]) / 100, 1.0))
    lightness = max(0.0, min(float(parts[2]) / 100, 1.0))
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return [int(red * 255), int(green * 255), int(blue * 255)]


def _point_frame(
    frame: pd.DataFrame,
    *,
    label_column: str,
    type_label: str,
) -> pd.DataFrame:
    points = frame[["latitude", "longitude"]].copy()
    points["latitude"] = pd.to_numeric(points["latitude"], errors="coerce")
    points["longitude"] = pd.to_numeric(points["longitude"], errors="coerce")
    points = points.dropna()
    if points.empty:
        return points

    points["label"] = frame.loc[points.index, label_column].fillna(type_label)
    points["kind"] = type_label
    if "address_stateOrRegion" in frame.columns:
        points["region"] = frame.loc[points.index, "address_stateOrRegion"].fillna("")
    elif "state" in frame.columns:
        points["region"] = frame.loc[points.index, "state"].fillna("")
    else:
        points["region"] = ""
    if "district" in frame.columns:
        points["district"] = frame.loc[points.index, "district"].fillna("")
    elif "address_city" in frame.columns:
        points["district"] = frame.loc[points.index, "address_city"].fillna("")
    else:
        points["district"] = ""
    points["state"] = points["region"]
    points["lat"] = points["latitude"]
    points["lon"] = points["longitude"]
    return points[["lat", "lon", "label", "kind", "region", "district", "state"]]


def _selected_object(event: Any) -> dict[str, Any] | None:
    selection = getattr(event, "selection", None)
    if selection is None and isinstance(event, dict):
        selection = event.get("selection")
    if not selection:
        return None

    objects = getattr(selection, "objects", None)
    if objects is None and isinstance(selection, dict):
        objects = selection.get("objects")
    if not isinstance(objects, dict):
        return None

    layer_objects = objects.get("facility-points")
    if layer_objects:
        selected = layer_objects[0]
        return dict(selected) if isinstance(selected, dict) else None
    return None


def _zoom(points: pd.DataFrame) -> float:
    if points.empty:
        return 4.2

    lat_span = float(points["lat"].max() - points["lat"].min())
    lon_span = float(points["lon"].max() - points["lon"].min())
    span = max(lat_span, lon_span)
    if span < 0.12:
        return 10.6
    if span < 0.4:
        return 9.4
    if span < 0.9:
        return 8.2
    if span < 1.8:
        return 7.2
    if span < 4:
        return 6.2
    if span < 8:
        return 5.4
    return 4.6


def render_map(districts: pd.DataFrame, facilities: pd.DataFrame, height: int = 430) -> dict[str, Any] | None:
    facility_points = pd.DataFrame()
    if not facilities.empty and {"latitude", "longitude", "name"}.issubset(facilities.columns):
        facility_points = _point_frame(facilities, label_column="name", type_label="Facility")

    if facility_points.empty:
        st.info("Facility coordinates are not available yet for this result set.")
        return None

    all_points = facility_points.reset_index(drop=True)
    center_lat = float(all_points["lat"].mean())
    center_lon = float(all_points["lon"].mean())
    theme = tokens()
    facility_color = _css_hsl_to_rgb(str(theme["accent"])) + [210]

    layers: list[pdk.Layer] = []
    if not facility_points.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=facility_points,
                id="facility-points",
                get_position="[lon, lat]",
                get_radius=17000,
                radius_min_pixels=5,
                get_fill_color=facility_color,
                stroked=True,
                get_line_color=[255, 255, 255, 220],
                line_width_min_pixels=1,
                pickable=True,
                auto_highlight=True,
            )
        )

    deck = pdk.Deck(
        map_style="dark",
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=_zoom(all_points),
            pitch=0,
            bearing=0,
        ),
        layers=layers,
        tooltip={"html": "<b>{label}</b><br/>{kind}<br/>{region}<br/>Click to focus this facility", "style": {"fontFamily": "sans-serif"}},
    )
    event = st.pydeck_chart(
        deck,
        width="stretch",
        height=height,
        on_select="rerun",
        selection_mode="single-object",
        key="planner_map",
    )
    return _selected_object(event)
