from __future__ import annotations

from html import escape

import streamlit as st


def hero_header(eyebrow: str, title: str, subtitle: str, chips: list[tuple[str, str]]) -> None:
    chip_html = "".join(
        f"<span class='db-chip'><strong>{escape(label)}</strong>{escape(value)}</span>"
        for label, value in chips
    )
    st.markdown(
        (
            f"<section class=\"db-hero\">"
            f"<span class=\"db-eyebrow\">{escape(eyebrow)}</span>"
            f"<h1 class=\"db-title\">{escape(title)}</h1>"
            f"<p class=\"db-subtitle\">{escape(subtitle)}</p>"
            f"<div class=\"db-chip-row\">{chip_html}</div>"
            f"</section>"
        ),
        unsafe_allow_html=True,
    )


def kpi_row(items: list[dict[str, str]]) -> None:
    cards = []
    for item in items:
        cards.append(
            (
                f"<div class=\"db-kpi-card\">"
                f"<div class=\"db-kpi-label\">{escape(item['label'])}</div>"
                f"<div class=\"db-kpi-value {escape(item.get('value_class', ''))}\">{escape(item['value'])}</div>"
                f"<div class=\"db-kpi-note\">{escape(item.get('note', ''))}</div>"
                f"</div>"
            )
        )
    st.markdown(f"<section class='db-kpis'>{''.join(cards)}</section>", unsafe_allow_html=True)


def card(title: str, body: str, caption: str = "") -> None:
    caption_html = f"<div class='db-card-caption'>{escape(caption)}</div>" if caption else ""
    st.markdown(
        (
            f"<section class=\"db-card\">"
            f"<div class=\"db-card-title\">{escape(title)}</div>"
            f"<p class=\"db-card-copy\">{escape(body)}</p>"
            f"{caption_html}"
            f"</section>"
        ),
        unsafe_allow_html=True,
    )


def inline_metrics(items: list[tuple[str, str]]) -> None:
    metrics_html = "".join(
        (
            f"<div class=\"db-inline-metric\">"
            f"<div class=\"db-inline-metric-label\">{escape(label)}</div>"
            f"<div class=\"db-inline-metric-value\">{escape(value)}</div>"
            f"</div>"
        )
        for label, value in items
    )
    st.markdown(f"<div class='db-inline-metrics'>{metrics_html}</div>", unsafe_allow_html=True)


def status_stack(messages: list[tuple[str, str]]) -> None:
    if not messages:
        return
    html = "".join(
        f"<div class='db-status {escape(tone)}'>{escape(message)}</div>" for tone, message in messages
    )
    st.markdown(f"<div class='db-status-stack'>{html}</div>", unsafe_allow_html=True)
