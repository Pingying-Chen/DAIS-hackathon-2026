from __future__ import annotations

APP_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Manrope:wght@400;500;600;700;800&display=swap');

html, body, [data-testid="stAppViewContainer"] {
  background: var(--db-bg);
  color: var(--db-text);
  font-family: var(--db-font);
  height: 100%;
}

[data-testid="stHeader"] {
  background: transparent;
}

#MainMenu, footer {
  visibility: hidden;
}

[data-testid="stAppViewContainer"] > .main {
  height: 100vh;
  height: 100dvh;
  overflow: hidden;
}

[data-testid="stMainBlockContainer"] {
  max-width: 100%;
  padding: 16px 16px 8px 16px;
  height: 100%;
}

[data-testid="stSidebar"] {
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-surface-hi) 92%, white), var(--db-surface-hi));
  border-right: 1px solid var(--db-outline);
}

[data-testid="stSidebar"] * {
  font-family: var(--db-font);
}

.db-shell {
  display: flex;
  flex-direction: column;
  gap: 12px;
  min-height: calc(100vh - 24px);
  min-height: calc(100dvh - 24px);
}

.db-hero {
  background:
    radial-gradient(circle at top right, color-mix(in srgb, var(--db-energy) 14%, transparent), transparent 42%),
    linear-gradient(135deg, color-mix(in srgb, var(--db-surface) 92%, white), color-mix(in srgb, var(--db-surface-hi) 86%, white));
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius-lg);
  box-shadow: 0 18px 40px rgba(15, 23, 42, 0.07);
  padding: 20px 22px;
}

.db-eyebrow {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  border-radius: 999px;
  background: color-mix(in srgb, var(--db-interactive) 10%, white);
  color: var(--db-interactive);
  font-size: 12px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.db-title {
  margin: 12px 0 8px 0;
  font-size: 34px;
  line-height: 1.05;
  font-weight: 800;
}

.db-subtitle {
  margin: 0;
  max-width: 78ch;
  color: var(--db-muted);
  font-size: 14px;
  line-height: 1.55;
}

.db-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 16px;
}

.db-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 7px 11px;
  border-radius: 999px;
  border: 1px solid var(--db-outline);
  background: rgba(255, 255, 255, 0.78);
  font-size: 12px;
  color: var(--db-muted);
}

.db-chip strong {
  color: var(--db-text);
  font-weight: 700;
}

.db-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
}

.db-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(var(--db-cols, 2), minmax(0, 1fr));
  align-items: stretch;
}

.db-kpi-card, .db-card {
  background: var(--db-surface);
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius-lg);
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.05);
  animation: db-fade-up var(--db-dur-medium) var(--db-ease-emphatic);
}

.db-kpi-card {
  padding: 14px 16px;
  min-height: 110px;
}

.db-kpi-label {
  color: var(--db-muted);
  font-size: 12px;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  font-weight: 700;
}

.db-kpi-value {
  margin-top: 10px;
  font-size: 30px;
  font-weight: 800;
  color: var(--db-text);
}

.db-kpi-accent {
  color: var(--db-interactive);
}

.db-kpi-note {
  margin-top: 8px;
  font-size: 12px;
  color: var(--db-muted);
  line-height: 1.4;
}

.db-stage {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.db-split {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(300px, 0.95fr);
  gap: 14px;
  align-items: stretch;
}

.db-view-note {
  margin: 0;
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
}

.db-card {
  padding: 16px 18px;
}

.db-card h3, .db-card h4 {
  margin: 0 0 8px 0;
}

.db-card-title {
  margin: 0 0 8px 0;
  font-size: 16px;
  font-weight: 800;
  color: var(--db-text);
}

.db-card-copy {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--db-muted);
}

.db-card-caption {
  margin-top: 10px;
  font-size: 12px;
  color: var(--db-muted);
}

.db-inline-metrics {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 10px;
  margin-top: 12px;
}

.db-inline-metric {
  padding: 10px 12px;
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface-hi) 70%, white);
  border: 1px solid color-mix(in srgb, var(--db-outline) 90%, white);
}

.db-inline-metric-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--db-muted);
  text-transform: uppercase;
  letter-spacing: 0.04em;
}

.db-inline-metric-value {
  margin-top: 6px;
  font-size: 18px;
  font-weight: 800;
  color: var(--db-text);
}

.db-status-stack {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.db-action-panel {
  background:
    linear-gradient(180deg, color-mix(in srgb, var(--db-surface) 88%, white), color-mix(in srgb, var(--db-surface-hi) 94%, white));
}

.db-action-steps {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.db-action-step {
  padding: 10px 12px;
  border-radius: var(--db-radius);
  border: 1px solid color-mix(in srgb, var(--db-outline) 90%, white);
  background: color-mix(in srgb, var(--db-surface-hi) 78%, white);
  color: var(--db-text);
  font-size: 12px;
  line-height: 1.45;
}

.db-grid-card {
  height: 100%;
}

.db-map-caption {
  margin-top: 8px;
  font-size: 12px;
  color: var(--db-muted);
}

.db-status {
  border-left: 4px solid var(--db-warn);
  border-radius: var(--db-radius);
  padding: 10px 12px;
  background: color-mix(in srgb, var(--db-warn) 10%, white);
  color: var(--db-text);
  font-size: 13px;
  line-height: 1.45;
}

.db-status.info {
  border-left-color: var(--db-interactive);
  background: color-mix(in srgb, var(--db-interactive) 10%, white);
}

.db-scroll-panel {
  max-height: 420px;
  overflow-y: auto;
  padding-right: 4px;
}

[data-testid="stDataFrame"] {
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius-lg);
  overflow: hidden;
}

[data-testid="stDeckGlJsonChart"] {
  min-height: 430px;
}

[data-testid="stDeckGlJsonChart"] iframe {
  min-height: 430px;
}

[data-testid="stButtonGroup"] button,
[data-testid="stSegmentedControl"] button {
  border-radius: 999px !important;
  border: 1px solid var(--db-outline) !important;
  background: rgba(255, 255, 255, 0.88) !important;
  color: var(--db-muted) !important;
  font-weight: 700 !important;
  min-height: 42px !important;
}

[data-testid="stButtonGroup"] button[aria-checked="true"],
[data-testid="stButtonGroup"] button[kind*="Active"],
[data-testid="stSegmentedControl"] button[aria-checked="true"] {
  background: var(--db-interactive) !important;
  border-color: var(--db-interactive) !important;
  color: white !important;
}

[data-testid="stButtonGroup"] button[kind*="Active"] p,
[data-testid="stSegmentedControl"] button[aria-checked="true"] p {
  color: white !important;
}

[data-testid="stBaseButton-primary"] {
  background: var(--db-accent) !important;
  border-color: var(--db-accent) !important;
  border-radius: var(--db-radius) !important;
}

[data-testid="stBaseButton-primary"]:hover {
  filter: brightness(1.05);
}

[data-testid="stMetric"] {
  background: transparent;
}

[data-testid="stDataFrame"] {
[data-testid="stExpander"] details,
[data-testid="stStatusWidget"] {
  border-radius: var(--db-radius);
  border: 1px solid var(--db-outline);
  background: rgba(255, 255, 255, 0.85);
}

@keyframes db-fade-up {
  from { opacity: 0; transform: translateY(8px); }
  to { opacity: 1; transform: none; }
}

@media (max-width: 1100px) {
  .db-kpis, .db-inline-metrics, .db-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .db-split {
    grid-template-columns: 1fr;
  }

  .db-title {
    font-size: 28px;
  }
}

@media (max-width: 720px) {
  [data-testid="stAppViewContainer"] > .main {
    overflow-y: auto;
  }

  [data-testid="stMainBlockContainer"] {
    padding: 14px;
  }

  .db-kpis, .db-grid {
    grid-template-columns: 1fr;
  }
}
"""
