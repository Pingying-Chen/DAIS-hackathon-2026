# Care Convoy

Care Convoy is a Databricks Apps submission for the Virtue Foundation Data for Good hackathon. It helps a Virtue Foundation operations lead decide where to send the next specialty medical team in India by combining district health need, facility capability, cited evidence, uncertainty labels, and a review board before a plan is saved.

## Judge Summary

- **Track:** Track 3, Referral Copilot with a trust-scoring support layer.
- **Primary user:** Virtue Foundation operations lead.
- **Decision improved:** Choose a credible district and facility anchor for the next referral or outreach team.
- **Core idea:** Do not just rank facilities; decide whether the evidence is strong enough to act on.
- **Platform:** Databricks Apps, Unity Catalog, SQL Warehouse, Lakebase, Model Serving, Streamlit, pandas, Plotly, and PyDeck.

## How To Use It

1. Choose a care need such as maternal health, surgery, emergency care, or general access.
2. Optionally focus the run by state, district, and minimum certainty.
3. Click **Build Referral Plan**.
4. Review the top district, map, referral anchor, confidence, warnings, and cited evidence.
5. Open **Review Board** to see the decision gate across need, facility fit, trust, evidence, strategy, and supervisor review.
6. Open **Trust Evidence** to inspect duplicate resolution, website verification, source URLs, and weak-evidence flags.
7. Save a shortlist decision with a verification note so the recommendation becomes persistent operational state.

## What Judges Should Look For

- **Clear user workflow:** The app starts with a concrete operational question: where should the next specialty team go?
- **Provided data in the decision:** Facility records drive anchor selection, NFHS district indicators support need context, and pincode data supports district-density reconciliation.
- **Evidence-first outputs:** Facility claims, rankings, trust labels, and recommendations are paired with citation rows or visible warning states.
- **Uncertainty as product behavior:** Missing source URLs, duplicate ambiguity, weak website verification, and weak density joins reduce confidence instead of being hidden.
- **Persistent action:** Shortlist decisions are saved to Lakebase with the board verdict, confidence, facility name, and review metadata.
- **Databricks-native execution:** The live app uses managed Databricks resources rather than a local-only prototype.

## Key Features

- **Referral planning:** Ranks districts and candidate facility anchors for the selected care need.
- **NFHS-backed district context:** Uses district health indicators alongside facility-density context to explain why a place should be reviewed.
- **Trust Desk:** Resolves duplicate-looking facility rows, checks public website evidence, and calculates trust-supported recommendation signals.
- **Convoy Review Board:** Separates the decision into need, facility fit, trust verification, citation safety, referral strategy, and supervisor approval.
- **Evidence ledger:** Shows source-backed facility text behind important claims and keeps missing citations visible.
- **Shortlist persistence:** Saves operational decisions and reloads them from Lakebase.

## Data And Evidence

Care Convoy uses the provided Virtue Foundation dataset:

- `facilities` for facility names, capabilities, locations, source URLs, social proof proxies, doctors, capacity, and descriptive evidence.
- `nfhs_5_district_health_indicators` for district-level need signals such as child underweight rate, insurance coverage, institutional births, and high blood pressure prevalence.
- `india_post_pincode_directory` for district and state reconciliation when estimating facility-density context.

The app treats this data as valuable but imperfect. Weak joins, sparse capability text, missing URLs, stale pages, and duplicate-looking facility records are surfaced as review risks.

## Review Board

The Convoy Review Board helps keep the recommendation from becoming a single opaque score:

- **Need Scout** checks district need and uncertainty.
- **Facility Scout** checks whether the lead facility appears operationally relevant.
- **Trust Verifier** reviews duplicate resolution, website status, and trust score.
- **Evidence Auditor** downgrades unsupported or uncited claims.
- **Referral Strategist** combines need, capability, trust, and evidence into an action recommendation.
- **Supervisor** produces the final board verdict and confidence used in the saved shortlist.

## Architecture At A Glance

```mermaid
flowchart LR
    user["Operations lead"] --> app["Care Convoy Streamlit app"]
    app --> setup["Mission setup"]
    setup --> planner["Referral planner"]

    planner --> uc["Unity Catalog dataset"]
    uc --> nfhs["NFHS district indicators"]
    uc --> facilities["Facility records"]
    uc --> pincodes["Pincode directory"]

    planner --> trust["Trust Desk"]
    trust --> evidence["Evidence ledger"]
    evidence --> board["Convoy Review Board"]
    board --> packet["Referral recommendation"]
    packet --> lakebase["Lakebase shortlist"]
    lakebase --> saved["Saved decisions"]
```

## Validation Status

- Local deterministic tests pass: `29 passed`.
- Python syntax compilation passes.
- Dependency audit returned no known vulnerabilities.
- Browser availability check confirmed the deployed Databricks App renders the Care Convoy UI instead of a platform error page.
- Lakebase read-after-write smoke confirmed shortlist metadata can persist and reload.
- Live Databricks data checks confirmed the NFHS table is populated and Maharashtra facility-density context can be reconciled from the provided facility and pincode tables.

## Demo Payoff

Care Convoy does not just map need or list hospitals. It turns messy facility and district evidence into a cautious, cited, saveable referral decision for an operations lead.
