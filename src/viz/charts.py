from __future__ import annotations

import colorsys
import re

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure

from src.ui.theme import tokens

_HSL_PATTERN = re.compile(r"hsla?\(([^)]+)\)")


def _css_hsl_to_hex(color: str) -> str:
    match = _HSL_PATTERN.match(color.strip())
    if not match:
        return "#2563eb"

    parts = [part.strip().replace("%", "") for part in match.group(1).split(",")]
    if len(parts) < 3:
        return "#2563eb"

    hue = (float(parts[0]) % 360) / 360
    saturation = max(0.0, min(float(parts[1]) / 100, 1.0))
    lightness = max(0.0, min(float(parts[2]) / 100, 1.0))
    red, green, blue = colorsys.hls_to_rgb(hue, lightness, saturation)
    return "#{:02x}{:02x}{:02x}".format(int(red * 255), int(green * 255), int(blue * 255))


def _apply_chart_theme(chart: Figure) -> Figure:
    theme = tokens()
    chart.update_layout(
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        coloraxis_showscale=False,
        font={"family": str(theme["font"]), "color": _css_hsl_to_hex(str(theme["text"]))},
        margin={"l": 8, "r": 8, "t": 8, "b": 8},
    )
    chart.update_xaxes(showgrid=False, zeroline=False)
    chart.update_yaxes(showgrid=False)
    return chart


def build_confidence_chart(df: pd.DataFrame, label_column: str, value_column: str) -> Figure | None:
    if df.empty or label_column not in df or value_column not in df:
        return None

    theme = tokens()
    chart_df = df[[label_column, value_column]].head(8).copy()
    chart = px.bar(
        chart_df,
        x=value_column,
        y=label_column,
        orientation="h",
        color=value_column,
        color_continuous_scale=[
            _css_hsl_to_hex(str(theme["surface_hi"])),
            _css_hsl_to_hex(str(theme["info"])),
            _css_hsl_to_hex(str(theme["interactive"])),
        ],
    )
    chart.update_traces(marker_line_width=0, hovertemplate="%{y}: %{x:.1f}<extra></extra>")
    return _apply_chart_theme(chart)


def build_tradeoff_chart(df: pd.DataFrame) -> Figure | None:
    needed = {"name", "urgency_support", "capability_fit", "trust_score"}
    if df.empty or not needed.issubset(df.columns):
        return None

    theme = tokens()
    chart_df = df[["name", "urgency_support", "capability_fit", "trust_score"]].copy()
    long_df = chart_df.melt(id_vars="name", var_name="metric", value_name="score")
    chart = px.bar(
        long_df,
        x="metric",
        y="score",
        color="name",
        barmode="group",
        color_discrete_sequence=[
            _css_hsl_to_hex(str(theme["interactive"])),
            _css_hsl_to_hex(str(theme["accent"])),
        ],
    )
    chart.update_traces(hovertemplate="%{fullData.name}: %{y:.1f}<extra></extra>")
    return _apply_chart_theme(chart)
