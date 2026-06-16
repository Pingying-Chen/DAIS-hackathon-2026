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


def _chart_frame(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    chart_df = df[columns].copy()
    chart_df.attrs = {}
    return chart_df


def build_confidence_chart(df: pd.DataFrame, label_column: str, value_column: str) -> Figure | None:
    if df.empty or label_column not in df or value_column not in df:
        return None

    theme = tokens()
    chart_df = _chart_frame(df, [label_column, value_column])
    chart_df = chart_df.sort_values(value_column, ascending=False).head(8)
    chart_df = chart_df.sort_values(value_column, ascending=True)
    max_score = float(chart_df[value_column].max())
    chart_df["Urgency"] = chart_df[value_column].apply(
        lambda value: "Most urgent" if float(value) == max_score else "Other districts"
    )
    chart_df["Score"] = chart_df.apply(
        lambda row: f"{float(row[value_column]):.0f}/100 · Most urgent"
        if row["Urgency"] == "Most urgent"
        else f"{float(row[value_column]):.0f}/100",
        axis=1,
    )
    label_title = label_column.replace("_", " ").title()
    chart = px.bar(
        chart_df,
        x=value_column,
        y=label_column,
        orientation="h",
        text="Score",
        labels={
            value_column: "Urgency score",
            label_column: label_title,
            "Urgency": "Urgency",
        },
        color="Urgency",
        color_discrete_map={
            "Most urgent": _css_hsl_to_hex(str(theme["interactive"])),
            "Other districts": _css_hsl_to_hex(str(theme["surface_hi"])),
        },
    )
    chart.update_traces(marker_line_width=0, textposition="auto", hovertemplate="%{y}: %{x:.0f}/100<extra></extra>")
    chart.update_layout(showlegend=False)
    chart.update_xaxes(range=[0, 100])
    chart.update_yaxes(categoryorder="array", categoryarray=chart_df[label_column].tolist())
    return _apply_chart_theme(chart)


def build_tradeoff_chart(df: pd.DataFrame) -> Figure | None:
    needed = {"name", "urgency_support", "capability_fit", "trust_score"}
    if df.empty or not needed.issubset(df.columns):
        return None

    theme = tokens()
    chart_df = _chart_frame(df, ["name", "urgency_support", "capability_fit", "trust_score"])
    long_df = chart_df.melt(id_vars="name", var_name="metric", value_name="score")
    metric_labels = {
        "urgency_support": "Urgency support (0-100)",
        "capability_fit": "Facility fit (0-100)",
        "trust_score": "Trust support (0-100)",
    }
    long_df["Metric"] = long_df["metric"].map(metric_labels)
    chart = px.bar(
        long_df,
        x="Metric",
        y="score",
        color="name",
        barmode="group",
        labels={
            "Metric": "Comparison signal",
            "score": "Score",
            "name": "Facility",
        },
        color_discrete_sequence=[
            _css_hsl_to_hex(str(theme["interactive"])),
            _css_hsl_to_hex(str(theme["accent"])),
        ],
    )
    chart.update_traces(hovertemplate="%{fullData.name}: %{y:.0f}/100<extra></extra>")
    chart.update_yaxes(range=[0, 100])
    return _apply_chart_theme(chart)
