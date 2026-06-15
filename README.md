# Care Convoy

Care Convoy is a Databricks Apps MVP for the Virtue Foundation hackathon. The app helps an operations lead decide where to send the next specialty medical team in India using evidence-backed facility data, district need signals, visible uncertainty, and a persistent shortlist workflow.

## What belongs in this repo

- Project source code
- Databricks app configuration
- Tests for project behavior
- README and other user-facing project docs

## What stays local-only

The following are intentionally ignored so the repo stays focused on the actual submission build:

- Assistant overlay: `.agents/`, `.codex/`, `AGENTS.md`, `templates/`, and local helper scripts
- Planning inputs: `ref/`, `SPEC.md`, `PLAN.md`, `DEVELOPMENT-LOOP.md`, `DESIGN-CONFORMANCE.md`, and `TESTING.md`
- Local review artifacts after MVP work: `review/`, `recordings/`, `captures/`, `exports/`, `screenshots/`, and `tmp/`
- Secrets and local machine state: `.env`, `.databricks/`, IDE files, caches, and generated media

## Post-MVP Local Check List

After the MVP is built, review these local-only artifacts before deciding what should become product code or public documentation:

- `review/` for implementation notes and manual QA findings
- `screenshots/`, `captures/`, and `recordings/` for demo and UI checks
- `exports/` for any local data extracts or one-off analysis outputs
- `tmp/` for scratch outputs that should not enter version control
