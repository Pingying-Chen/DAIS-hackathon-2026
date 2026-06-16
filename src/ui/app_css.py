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

[data-testid="stToolbar"],
[data-testid="stAppDeployButton"] {
  display: none !important;
}

#MainMenu, footer {
  visibility: hidden;
}

[data-testid="stAppViewContainer"] > .main {
  min-height: 100vh;
  min-height: 100dvh;
  overflow-x: hidden;
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-surface-hi) 22%, var(--db-bg)), var(--db-bg));
}

[data-testid="stMainBlockContainer"] {
  max-width: 100%;
  padding: 42px 88px 52px 88px;
}

[data-testid="stSidebar"] {
  display: none;
}

[data-testid="collapsedControl"] {
  display: none;
}

.db-hero {
  padding: 12px 0 18px 0;
  border-bottom: 1px solid var(--db-outline);
  margin-bottom: 16px;
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
  overflow-wrap: anywhere;
  white-space: normal;
}

.db-chip strong {
  color: var(--db-text);
  font-weight: 700;
}

.db-control-copy {
  margin: 4px 0 8px 0;
  padding-top: 2px;
  border-top: 1px solid var(--db-outline);
}

.db-control-copy p {
  margin: 0;
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
}

.db-command-strip {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(240px, 0.45fr);
  gap: 14px;
  align-items: end;
  margin: 6px 0 8px 0;
  padding: 10px 0 8px 0;
  border-top: 1px solid var(--db-outline);
  border-bottom: 1px solid var(--db-outline);
}

.db-command-strip p {
  margin: 0;
  color: var(--db-text);
  font-size: 15px;
  line-height: 1.35;
  font-weight: 800;
}

.db-command-note {
  color: var(--db-muted);
  font-size: 11px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.db-alert-strip {
  display: grid;
  grid-template-columns: minmax(0, 1.25fr) minmax(280px, 0.75fr);
  gap: 18px;
  align-items: stretch;
  margin: 12px 0;
  padding: 16px 18px;
  border: 1px solid color-mix(in srgb, var(--db-interactive) 42%, var(--db-outline));
  border-radius: var(--db-radius);
  background:
    linear-gradient(135deg, color-mix(in srgb, var(--db-interactive) 14%, var(--db-surface)), color-mix(in srgb, var(--db-surface) 88%, transparent));
  box-shadow: 0 18px 48px rgba(0, 0, 0, 0.22);
}

.db-alert-kicker {
  color: var(--db-interactive);
  font-size: 11px;
  font-weight: 800;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}

.db-alert-main h2,
.db-intro-hero h2 {
  margin: 7px 0 9px 0;
  color: var(--db-text);
  font-size: 22px;
  line-height: 1.15;
  font-weight: 800;
  letter-spacing: 0;
  overflow-wrap: anywhere;
}

.db-alert-main ul {
  margin: 0;
  padding: 0;
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 7px;
}

.db-alert-main li {
  position: relative;
  padding-left: 14px;
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
}

.db-alert-main li::before {
  content: "";
  position: absolute;
  left: 0;
  top: 0.62em;
  width: 5px;
  height: 5px;
  border-radius: 999px;
  background: var(--db-interactive);
}

.db-alert-stats {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
}

.db-alert-stat {
  min-height: 62px;
  padding: 10px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-bg) 42%, transparent);
}

.db-alert-stat span {
  display: block;
  color: var(--db-muted);
  font-size: 10px;
  font-weight: 800;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.db-alert-stat strong {
  display: block;
  margin-top: 5px;
  color: var(--db-text);
  font-size: 13px;
  line-height: 1.25;
  overflow-wrap: anywhere;
  white-space: normal;
}

.db-intro-hero {
  margin: 12px 0 14px 0;
  padding: 16px 18px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface) 86%, transparent);
}

.db-intro-hero p {
  max-width: 86ch;
  margin: 0;
  color: var(--db-muted);
  font-size: 13px;
  line-height: 1.5;
}

.db-pipeline {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 10px;
  margin: 8px 0 12px 0;
}

.db-pipeline-step {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  padding: 12px;
  min-height: 150px;
  border-top: 1px solid var(--db-outline);
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-surface) 76%, transparent), transparent);
}

.db-pipeline-step span {
  width: 26px;
  height: 26px;
  display: grid;
  place-items: center;
  border-radius: 999px;
  background: var(--db-interactive);
  color: var(--db-bg);
  font-size: 12px;
  font-weight: 800;
}

.db-pipeline-step strong {
  display: block;
  color: var(--db-text);
  font-size: 13px;
  line-height: 1.25;
  overflow-wrap: anywhere;
}

.db-pipeline-step p {
  margin: 6px 0 0 0;
  color: var(--db-muted);
  font-size: 11px;
  line-height: 1.4;
  overflow-wrap: anywhere;
}

.db-kpis {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 16px;
  margin: 12px 0 16px 0;
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
  white-space: normal;
}

.db-kpi-accent {
  color: var(--db-interactive);
}

.db-kpi-note {
  margin-top: 7px;
  font-size: 11px;
  color: var(--db-muted);
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.db-grid {
  display: grid;
  gap: 16px;
  grid-template-columns: repeat(var(--db-cols, 2), minmax(0, 1fr));
  align-items: stretch;
  margin: 0 0 16px 0;
}

.db-card {
  padding: 14px 15px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface) 82%, transparent);
  box-shadow: 0 20px 50px rgba(0, 0, 0, 0.24);
  animation: db-fade-up var(--db-dur-medium) var(--db-ease-emphatic);
}

.db-card:not(.db-grid-card) {
  margin: 0 0 16px 0;
}

.db-grid-card {
  height: 100%;
  margin: 0;
  box-shadow: none;
}

.db-card-title {
  margin: 0 0 7px 0;
  font-size: 14px;
  font-weight: 800;
  color: var(--db-text);
  overflow-wrap: anywhere;
}

.db-card-copy {
  margin: 0;
  font-size: 12px;
  line-height: 1.5;
  color: var(--db-muted);
  overflow-wrap: anywhere;
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
  overflow-wrap: anywhere;
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
  overflow-wrap: anywhere;
}

.db-evidence-stack {
  display: flex;
  flex-direction: column;
  gap: 16px;
  margin: 0 0 16px 0;
}

.db-evidence-card {
  padding: 14px 15px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface) 82%, transparent);
}

.db-evidence-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.db-evidence-list li {
  display: grid;
  grid-template-columns: minmax(96px, 0.32fr) minmax(0, 1fr);
  gap: 8px 12px;
  padding-top: 10px;
  border-top: 1px solid var(--db-outline);
}

.db-evidence-list strong {
  color: var(--db-text);
  font-size: 12px;
  line-height: 1.35;
  overflow-wrap: anywhere;
}

.db-evidence-list span {
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
  overflow-wrap: anywhere;
}

.db-evidence-list em {
  grid-column: 2;
  color: color-mix(in srgb, var(--db-muted) 84%, white);
  font-size: 10px;
  font-style: normal;
  line-height: 1.3;
  overflow-wrap: anywhere;
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
  overflow-wrap: anywhere;
}

.db-agent-evidence {
  color: color-mix(in srgb, var(--db-text) 80%, var(--db-muted));
}

.db-gate {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 84px;
  width: auto;
  height: 28px;
  padding: 0 10px;
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
  gap: 16px;
  margin: 0 0 16px 0;
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
  white-space: normal;
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
  overflow-wrap: anywhere;
  white-space: normal;
}

.db-filter-pill strong {
  color: var(--db-text);
}

.db-story-path {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin: 8px 0 12px 0;
}

.db-story-step {
  min-height: 58px;
  padding: 9px 10px;
  border-top: 1px solid var(--db-outline);
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-surface) 62%, transparent), transparent);
}

.db-story-step.active {
  border-top-color: var(--db-interactive);
  background: linear-gradient(180deg, color-mix(in srgb, var(--db-interactive) 15%, var(--db-surface)), transparent);
}

.db-story-step strong {
  display: block;
  color: var(--db-text);
  font-size: 12px;
  line-height: 1.2;
}

.db-story-step span {
  display: block;
  margin-top: 4px;
  color: var(--db-muted);
  font-size: 10px;
  line-height: 1.25;
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

.db-caution-summary p {
  margin: 0 0 10px 0;
  color: var(--db-muted);
  font-size: 13px;
  line-height: 1.5;
  overflow-wrap: anywhere;
}

.db-caution-summary ul {
  margin: 0 0 12px 0;
  padding-left: 18px;
  color: var(--db-muted);
  font-size: 12px;
  line-height: 1.45;
}

.db-caution-summary li {
  margin: 5px 0;
  overflow-wrap: anywhere;
}

.db-caution-panel {
  margin: 0 0 16px 0;
  padding: 12px 13px;
  border: 1px solid var(--db-outline);
  border-radius: var(--db-radius);
  background: color-mix(in srgb, var(--db-surface-hi) 64%, transparent);
}

.db-label-legend {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin: 2px 0 10px 0;
}

.db-label-legend span {
  display: inline-flex;
  gap: 5px;
  align-items: baseline;
  padding: 6px 8px;
  border: 1px solid var(--db-outline);
  border-radius: 999px;
  color: var(--db-muted);
  background: color-mix(in srgb, var(--db-surface-hi) 62%, transparent);
  font-size: 11px;
  line-height: 1.2;
  overflow-wrap: anywhere;
  white-space: normal;
}

.db-label-legend strong {
  color: var(--db-text);
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
  overflow-wrap: anywhere;
}

[data-testid="stButton"] button,
[data-testid="stFormSubmitButton"] button,
[data-testid="stBaseButton-secondary"],
[data-testid="stBaseButton-primary"] {
  min-height: 40px !important;
  white-space: normal !important;
}

[data-testid="stButton"] button p,
[data-testid="stFormSubmitButton"] button p,
[data-testid="stRadio"] label p {
  white-space: normal !important;
  overflow-wrap: anywhere !important;
}

.db-map-caption {
  margin: 7px 0 16px 0;
  font-size: 11px;
  color: var(--db-muted);
}

[data-testid="stDataFrame"],
[data-testid="stExpander"] details {
  border-radius: var(--db-radius);
  border: 1px solid var(--db-outline);
  background: color-mix(in srgb, var(--db-surface) 86%, transparent);
}

[data-testid="stStatusWidget"] {
  display: none !important;
}

.db-app-footer {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 18px;
  margin-top: 24px;
  padding-top: 14px;
  border-top: 1px solid var(--db-outline);
  color: var(--db-muted);
  font-size: 11px;
  line-height: 1.4;
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
  [data-testid="stMainBlockContainer"] {
    padding: 34px 48px 44px 48px;
  }

  .db-alert-strip {
    grid-template-columns: 1fr;
  }

  .db-command-strip,
  .db-story-path {
    grid-template-columns: 1fr;
  }

  .db-pipeline {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

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
    padding: 24px;
  }

  .db-kpis,
  .db-grid,
  .db-pipeline,
  .db-alert-stats {
    grid-template-columns: 1fr;
  }

  .db-agent-row {
    grid-template-columns: 1fr;
  }

  .db-evidence-list li {
    grid-template-columns: 1fr;
  }

  .db-evidence-list em {
    grid-column: 1;
  }
}
"""
