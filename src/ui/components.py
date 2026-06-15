from __future__ import annotations

from html import escape

import streamlit as st


def hero_header(eyebrow: str, title: str, subtitle: str, chips: list[tuple[str, str]]) -> None:
    chip_html = "".join(
        f"<span class='db-chip'><strong>{escape(label)}</strong>{escape(value)}</span>"
        for label, value in chips
    )
    st.markdown(
        f"""
        <section class="db-hero">
          <span class="db-eyebrow">{escape(eyebrow)}</span>
          <h1 class="db-title">{escape(title)}</h1>
          <p class="db-subtitle">{escape(subtitle)}</p>
          <div class="db-chip-row">{chip_html}</div>
        </section>
        """,
        unsafe_allow_html=True,
    )


def kpi_row(items: list[dict[str, str]]) -> None:
    cards = []
    for item in items:
        cards.append(
            f"""
            <div class="db-kpi-card">
              <div class="db-kpi-label">{escape(item['label'])}</div>
              <div class="db-kpi-value {escape(item.get('value_class', ''))}">{escape(item['value'])}</div>
              <div class="db-kpi-note">{escape(item.get('note', ''))}</div>
            </div>
            """
        )
    st.markdown(f"<section class='db-kpis'>{''.join(cards)}</section>", unsafe_allow_html=True)


def card(title: str, body: str, caption: str = "") -> None:
    caption_html = f"<div class='db-card-caption'>{escape(caption)}</div>" if caption else ""
    st.markdown(
        f"""
        <section class="db-card">
          <div class="db-card-title">{escape(title)}</div>
          <p class="db-card-copy">{escape(body)}</p>
          {caption_html}
        </section>
        """,
        unsafe_allow_html=True,
    )


def inline_metrics(items: list[tuple[str, str]]) -> None:
    metrics_html = "".join(
        f"""
        <div class="db-inline-metric">
          <div class="db-inline-metric-label">{escape(label)}</div>
          <div class="db-inline-metric-value">{escape(value)}</div>
        </div>
        """
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
