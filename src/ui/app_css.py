from __future__ import annotations

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
  background: var(--db-bg);
  color: var(--db-text);
  font-family: var(--db-font);
}

[data-testid="stHeader"] {
  background: transparent;
}

#MainMenu, footer {
  visibility: hidden;
}

[data-testid="stAppViewContainer"] > .main {
  min-height: 100vh;
  min-height: 100dvh;
  overflow-x: hidden;
  background:
    radial-gradient(circle at 72% 0%, color-mix(in srgb, var(--db-interactive) 16%, transparent), transparent 36%),
    linear-gradient(180deg, color-mix(in srgb, var(--db-surface-hi) 22%, var(--db-bg)), var(--db-bg));
}

[data-testid="stMainBlockContainer"] {
  max-width: 100%;
  padding: 14px 16px 22px 16px;
}

[data-testid="stSidebar"] {
  background: color-mix(in srgb, var(--db-surface) 88%, black);
  border-right: 1px solid var(--db-outline);
}

[data-testid="stSidebar"] * {
  font-family: var(--db-font);
}

.db-hero {
  padding: 8px 2px 12px 2px;
  border-bottom: 1px solid var(--db-outline);
  margin-bottom: 12px;
}

.db-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 5px 11px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--db-interactive) 14%, transparent);
  color: var(--db-interactive);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  border: 1px solid color-mix(in srgb, var(--db-interactive) 38%, transparent);
}

.db-title {
  margin: 10px 0 6px 0;
  font-size: 32px;
  line-height: 1.05;
  font-weight: 800;
  letter-spacing: 0;
}

.db-subtitle {
  margin: 0;
  max-width: 92ch;
  color: var(--db-muted);
  font-size: 13px;
  line-height: 1.5;
}

.db-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 7px;
  margin-top: 12px;
}

.db-chip {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  padding: 6px 10px;
  border-radius: 999px;
  border: 1px solid var(--db-outline);
  background: color-mix(in srgb, var(--db-surface) 62%, transparent);
  font-size: 11px;
  color: var(--db-muted);
}

.db-chip strong {
  color: var(--db-text);
  font-weight: 700;
}

.db-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 10px 0 12px 0;
}

.db-kpi-card {
  padding: 12px 13px;
  min-height: 94px;
  border-bottom: 1px solid var(--db-outline);
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-surface) 72%, transparent), transparent);
}

.db-kpi-label {
  color: var(--db-muted);
  font-size: 10px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 800;
}

.db-kpi-value {
  margin-top: 8px;
  font-size: 24px;
  font-weight: 800;
  color: var(--db-text);
  overflow-wrap: anywhere;
}

.db-kpi-accent {
  color: var(--db-interactive);
}

.db-kpi-note {
  margin-top: 7px;
  font-size: 11px;
  color: var(--db-muted);
  line-height: 1.35;
}

.db-grid {
  display: grid;
  gap: 10px;
  grid-template-columns: repeat(var(--db-cols, 2), minmax(0, 1fr));
  align-items: stretch;
}

.db-card {
  padding: 14px 15px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface) 82%, transparent);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.24);
  animation: db-fade-up var(--db-dur-medium) var(--db-ease-emphatic);
}

.db-grid-card {
  height: 100%;
  box-shadow: none;
}

.db-card-title {
  margin: 0 0 7px 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--db-text);
}

.db-card-copy {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--db-muted);
}

.db-bullet-list {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.db-bullet-list li {
  position: relative;
  padding-left: 14px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--db-muted);
}

.db-bullet-list li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.62em;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: var(--db-interactive);
}

.db-card-caption {
  margin-top: 9px;
  font-size: 11px;
  color: color-mix(in srgb, var(--db-muted) 84%, white);
  line-height: 1.35;
}

.db-section-label {
  margin: 0 0 8px 0;
  color: var(--db-muted);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.db-agent-row {
  display: grid;
  grid-template-columns: 76px minmax(0, 1fr);
  gap: 12px;
  padding: 11px 0;
  border-bottom: 1px solid var(--db-outline);
}

.db-agent-main {
  min-width: 0;
}

.db-agent-title {
  font-size: 14px;
  font-weight: 800;
  color: var(--db-text);
}

.db-agent-role,
.db-agent-evidence,
.db-agent-handoff {
  margin-top: 4px;
  font-size: 11px;
  line-height: 1.35;
  color: var(--db-muted);
}

.db-agent-evidence {
  color: color-mix(in srgb, var(--db-text) 80%, var(--db-muted));
}

.db-gate {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 68px;
  height: 28px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 800;
  text-transform: uppercase;
  border: 1px solid currentColor;
}

.db-gate-positive {
  color: var(--db-positive);
}

.db-gate-warn {
  color: var(--db-warn);
}

.db-gate-accent {
  color: var(--db-accent);
}

.db-step-stack {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 10px;
}

.db-step-card {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr);
  gap: 9px;
  align-items: start;
  padding: 8px 0;
  border-top: 1px solid var(--db-outline);
}

.db-step-dot {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: grid;
  place-items: center;
  color: var(--db-bg);
  background: var(--db-interactive);
  font-size: 11px;
  font-weight: 800;
}

.db-step-title {
  color: var(--db-text);
  font-size: 12px;
  font-weight: 800;
}

.db-step-detail {
  margin-top: 3px;
  color: var(--db-muted);
  font-size: 11px;
  line-height: 1.35;
}

.db-inline-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 10px;
}

.db-inline-metric {
  padding: 9px 10px;
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface-hi) 72%, transparent);
  border: 1px solid var(--db-outline);
}

.db-inline-metric-label {
  font-size: 10px;
  font-weight: 800;
  color: var(--db-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.db-inline-metric-value {
  margin-top: 5px;
  font-size: 15px;
  font-weight: 800;
  color: var(--db-text);
  overflow-wrap: anywhere;
}

.db-filter-row {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin: 6px 0 10px 0;
}

.db-filter-pill {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  border-radius: 999px;
  border: 1px solid var(--db-outline);
  color: var(--db-muted);
  background: color-mix(in srgb, var(--db-surface-hi) 68%, transparent);
  font-size: 10px;
  line-height: 1.2;
}

.db-filter-pill strong {
  color: var(--db-text);
}

.db-status-stack {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 10px;
}

.db-status {
  border-left: 3px solid var(--db-warn);
  border-radius: var(--db-radius);
  padding: 9px 10px;
  background: color-mix(in srgb, var(--db-warn) 12%, transparent);
  color: var(--db-text);
  font-size: 12px;
  line-height: 1.4;
}

.db-status.info {
  border-left-color: var(--db-interactive);
  background: color-mix(in srgb, var(--db-interactive) 10%, transparent);
}

.db-action-panel {
  background: color-mix(in srgb, var(--db-surface) 88%, transparent);
}

.db-action-steps {
  display: flex;
  flex-direction: column;
  gap: 7px;
  margin-top: 10px;
}

.db-action-step {
  padding: 8px 0;
  border-top: 1px solid var(--db-outline);
  color: var(--db-text);
  font-size: 12px;
  line-height: 1.4;
}

.db-map-caption {
  margin-top: 7px;
  font-size: 11px;
  color: var(--db-muted);
}

[data-testid="stDataFrame"],
[data-testid="stExpander"] details,
[data-testid="stStatusWidget"] {
  border-radius: var(--db-radius);
  border: 1px solid var(--db-outline);
  background: color-mix(in srgb, var(--db-surface) 86%, transparent);
}

[data-testid="stDeckGlJsonChart"],
[data-testid="stDeckGlJsonChart"] iframe {
  min-height: 470px;
}

[data-testid="stButtonGroup"] button,
[data-testid="stSegmentedControl"] button {
  border-radius: 999px !important;
  border: 1px solid var(--db-outline) !important;
  background: color-mix(in srgb, var(--db-surface) 78%, transparent) !important;
  color: var(--db-muted) !important;
  font-weight: 800 !important;
  min-height: 38px !important;
}

[data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[kind*="Active"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  background: var(--db-interactive) !important;
  border-color: var(--db-interactive) !important;
  color: var(--db-bg) !important;
}

[data-testid="stButtonGroup"] button[kind*="Active"] p,
[data-testid="stSegmentedControl"] button[aria-checked="true"] p {
  color: var(--db-bg) !important;
}

[data-testid="stBaseButton-primary"] {
  background: var(--db-interactive) !important;
  border-color: var(--db-interactive) !important;
  color: var(--db-bg) !important;
  border-radius: var(--db-radius) !important;
}

[data-testid="stBaseButton-primary"]:hover {
  filter: brightness(1.07);
}

[data-testid="stMetric"] {
  background: transparent;
}

@keyframes db-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 1ms !important;
    transition-duration: 1ms !important;
  }
}

@media (max-width: 1100px) {
  .db-kpis {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .db-inline-metrics,
  .db-grid {
    grid-template-columns: 1fr;
  }

  .db-title {
    font-size: 27px;
  }
}

@media (max-width: 720px) {
  [data-testid="stMainBlockContainer"] {
    padding: 12px;
  }

  .db-kpis,
  .db-grid {
    grid-template-columns: 1fr;
  }

  .db-agent-row {
    grid-template-columns: 1fr;
  }
}
"""
