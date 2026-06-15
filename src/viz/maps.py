from __future__ import annotations

import colorsys
import re

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
    points["lat"] = points["latitude"]
    points["lon"] = points["longitude"]
    return points[["lat", "lon", "label", "kind", "region"]]


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


def render_map(districts: pd.DataFrame, facilities: pd.DataFrame, height: int = 430) -> None:
    district_points = pd.DataFrame()
    facility_points = pd.DataFrame()
    if not districts.empty and {"latitude", "longitude", "district"}.issubset(districts.columns):
        district_points = _point_frame(districts, label_column="district", type_label="District")
    if not facilities.empty and {"latitude", "longitude", "name"}.issubset(facilities.columns):
        facility_points = _point_frame(facilities, label_column="name", type_label="Facility")

    if district_points.empty and facility_points.empty:
        st.info("Map coordinates are not available yet for this result set.")
        return

    all_points = pd.concat([district_points, facility_points], ignore_index=True)
    center_lat = float(all_points["lat"].mean())
    center_lon = float(all_points["lon"].mean())
    theme = tokens()
    district_color = _css_hsl_to_rgb(str(theme["interactive"])) + [120]
    facility_color = _css_hsl_to_rgb(str(theme["accent"])) + [210]

    layers: list[pdk.Layer] = []
    if not district_points.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=district_points,
                get_position="[lon, lat]",
                get_radius=24000,
                radius_min_pixels=7,
                get_fill_color=district_color,
                stroked=True,
                get_line_color=[255, 255, 255, 180],
                line_width_min_pixels=1,
                pickable=True,
            )
        )
    if not facility_points.empty:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=facility_points,
                get_position="[lon, lat]",
                get_radius=17000,
                radius_min_pixels=5,
                get_fill_color=facility_color,
                stroked=True,
                get_line_color=[255, 255, 255, 220],
                line_width_min_pixels=1,
                pickable=True,
            )
        )

    deck = pdk.Deck(
        map_style="light",
        initial_view_state=pdk.ViewState(
            latitude=center_lat,
            longitude=center_lon,
            zoom=_zoom(all_points),
            pitch=0,
            bearing=0,
        ),
        layers=layers,
        tooltip={"html": "<b>{label}</b><br/>{kind}<br/>{region}", "style": {"fontFamily": "sans-serif"}},
    )
    st.pydeck_chart(deck, use_container_width=True)
