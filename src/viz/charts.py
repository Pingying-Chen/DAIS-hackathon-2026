from __future__ import annotations

import pandas as pd
import plotly.express as px
from plotly.graph_objects import Figure


def build_confidence_chart(df: pd.DataFrame, label_column: str, value_column: str) -> Figure | None:
    if df.empty or label_column not in df or value_column not in df:
        return None
    chart_df = df[[label_column, value_column]].head(8).copy()
    return px.bar(
        chart_df,
        x=value_column,
        y=label_column,
        orientation="h",
        color=value_column,
        color_continuous_scale=["#d5e8d4", "#82b366", "#4c7a34"],
    )


def build_tradeoff_chart(df: pd.DataFrame) -> Figure | None:
    needed = {"name", "urgency_support", "capability_fit", "trust_score"}
    if df.empty or not needed.issubset(df.columns):
        return None
    chart_df = df[["name", "urgency_support", "capability_fit", "trust_score"]].copy()
    long_df = chart_df.melt(id_vars="name", var_name="metric", value_name="score")
    return px.bar(
        long_df,
        x="metric",
        y="score",
        color="name",
        barmode="group",
        color_discrete_sequence=["#295c45", "#c56a3d"],
    )
