from __future__ import annotations

import pandas as pd
import streamlit as st


def render_map(districts: pd.DataFrame, facilities: pd.DataFrame) -> None:
    st.subheader("Planning Map")
    points = []
    if not districts.empty and {"latitude", "longitude"}.issubset(districts.columns):
        district_points = districts[["latitude", "longitude"]].copy()
        district_points["latitude"] = pd.to_numeric(district_points["latitude"], errors="coerce")
        district_points["longitude"] = pd.to_numeric(district_points["longitude"], errors="coerce")
        district_points = district_points.dropna()
        district_points.columns = ["lat", "lon"]
        points.append(district_points)
    if not facilities.empty and {"latitude", "longitude"}.issubset(facilities.columns):
        facility_points = facilities[["latitude", "longitude"]].copy()
        facility_points["latitude"] = pd.to_numeric(facility_points["latitude"], errors="coerce")
        facility_points["longitude"] = pd.to_numeric(facility_points["longitude"], errors="coerce")
        facility_points = facility_points.dropna()
        facility_points.columns = ["lat", "lon"]
        points.append(facility_points)

    if not points:
        st.info("Map coordinates are not available yet for this result set.")
        return

    st.map(pd.concat(points, ignore_index=True), use_container_width=True)
