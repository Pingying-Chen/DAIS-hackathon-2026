# Care Convoy

Care Convoy is a referral planning tool for India that helps health teams find where specialty care is most needed, which facility to review first, and what evidence to verify before action.

Instead of presenting a single opaque score, Care Convoy produces a reviewable referral plan with cited evidence, uncertainty labels, duplicate and website trust checks, and a clear next action: shortlist, verify first, or hold.

The demo payoff is simple: Care Convoy does not just map need or list hospitals. It turns imperfect facility and district evidence into a cautious, cited referral recommendation with a saved review note for the next follow-up step.

The current app keeps the operator-first referral workflow and improves usability: dashboard numbers appear before filters, the planner has one authoritative navigation path, user-facing labels use plain language, scores carry their scale and meaning, and infrastructure details stay out of the product flow. A separate **Product Introduction** page explains the product, workflow, evidence model, and usability improvements without crowding the referral planner.

**Hackathon note:** Care Convoy was built for the Databricks Data for Good Hackathon using the provided Virtue Foundation facility dataset, NFHS district indicators, and India pincode directory.

- **Author:** Pingying Chen
- **Co-author:** Zihang Liang

## Fast Read

From here, the README is judge-facing: it maps the project to the hackathon track, demo path, evidence model, and Databricks resources.

**Track 3: Referral Copilot for the Virtue Foundation Data for Good Hackathon**

| Judging criterion | What Care Convoy proves | Where to look in the demo |
|---|---|---|
| Product judgment | A non-technical operations lead can choose a district, referral anchor, and verification action in minutes. | Plan, Why This Place, Save Review Note |
| Evidence and uncertainty | Rankings, facility fit, NFHS context, trust labels, and recommendations show citations or warnings instead of hiding weak evidence. | Evidence Details, Compare Anchors, Why This Place |
| Technical execution | Runs as a Databricks App using Unity Catalog, SQL Warehouse, append-only scoring and entity-mapping tables, Lakebase, Model Serving hooks, MLflow evaluation, Streamlit, pandas, Plotly, and PyDeck. | Product Introduction, Backend Pipeline, Databricks Resources |
| Ambition | The app does not stop at a map or a list. It uses seven decision gates to decide whether to shortlist, verify first, or hold. | Decision gates |

## Demo Media

<table>
  <tr>
    <td width="58%">
      <img src="docs/assets/care-convoy-demo.jpg" alt="Care Convoy demo showing the Maharashtra referral map and mission packet" width="100%">
    </td>
    <td width="42%">
      <h3>3-minute video placeholder</h3>
      <p><strong>Status:</strong> add the final Devpost, YouTube, or Loom link here before submission.</p>
      <ul>
        <li>0:00 - name Track 3 Referral Copilot.</li>
        <li>0:20 - show the recommended next move.</li>
        <li>1:10 - open Why This Place for the weakest gate.</li>
        <li>1:45 - open Evidence Details for plain-language source notes and uncertainty.</li>
        <li>2:20 - save a review note for the follow-up work.</li>
        <li>2:45 - open Product Introduction for the product story and usability summary.</li>
      </ul>
    </td>
  </tr>
</table>

## One Decision, End To End

1. Select a care mission such as maternal health, surgery, emergency care, or general access.
2. Review the dashboard numbers first, then filter by state, district, and minimum certainty when the operator wants a narrower run.
3. Click **Build Referral Plan**.
4. Review the priority district, map, referral anchor, backup anchor, confidence, warnings, and cited evidence. A map selection can focus the planner on the selected district or place.
5. Open **Why This Place** to see pass, review, or block gates for need, supply density, facility fit, trust, evidence, strategy, and supervisor action.
6. Open **Evidence Details** to inspect duplicate review, website verification, source URLs, and weak-evidence flags in plain language.
7. Save a review note so the recommended follow-up becomes durable operational state.
8. Open **Product Introduction** to review the product story, workflow, evidence surfaces, usability changes, and explicit non-claims.

## What Care Convoy Helps You Do

- **Find a practical starting point:** rank districts and candidate referral anchors for the selected care need.
- **Balance need with supply:** combine NFHS district health indicators with facility-density context instead of looking only at hospital counts.
- **Zoom in without losing context:** start with dashboard-wide signals, then narrow the view through filters or map selection.
- **Check whether an anchor is believable:** compare facility claims, website evidence, duplicate risk, and trust signals before acting.
- **See the evidence behind the recommendation:** inspect readable source-note cards, facility text, source URLs, and Unity Catalog provenance rows for important claims.
- **Know when to slow down:** use decision gates to turn weak evidence into a visible shortlist, verify-first, or hold action.
- **Reuse cached scoring and identities:** rely on append-only scoring and entity-mapping tables keyed by source-row fingerprints, while falling back to runtime scoring/resolution when data changes.
- **Keep the review trail durable:** save the mission packet, gate trace, facility anchor, confidence, follow-up status, and review note to Lakebase.
- **Validate the workflow:** use MLflow evaluation checks for evidence grounding and operator actionability.

## Backend Pipeline

In the live app, internal infrastructure details stay out of the operator home so the referral decision remains the main product surface. The backend is organized into four product modules:

```mermaid
flowchart LR
    data["1. Data Readiness<br/>Profile, score, and resolve facility evidence"]
    planning["2. Need And Supply<br/>Rank district need against local care capacity"]
    trust["3. Trust And Evidence<br/>Review anchors, claims, citations, and weak signals"]
    control["4. Mission Control And Persistence<br/>Convert gates into a saved operator action"]
    data --> planning --> trust --> control
```

<details>
<summary><strong>Module 1 - Data Readiness</strong></summary>

This module turns the provided datasets into candidate-ready evidence while keeping source uncertainty visible.

```mermaid
flowchart LR
    provided["Provided facility, NFHS, and pincode tables"] --> profile["Profile coverage, names, and source quality"]
    profile --> score["Build deterministic facility score features"]
    profile --> identity["Build facility identity mapping"]
    score --> score_cache["Append scoring row when the source fingerprint is new"]
    identity --> exact["Reuse exact id and fingerprint matches"]
    exact --> similar["Reuse similar mappings when exact matches are absent"]
    similar --> entity_cache["Append new or reused entity mapping"]
    score_cache --> ready["Candidate-ready data layer"]
    entity_cache --> ready
```

- Reads the three provided Virtue Foundation Unity Catalog tables.
- Treats sparse capability fields, duplicate-looking facilities, weak source URLs, and district-name mismatch as product risks.
- Keeps scoring and entity-resolution caches as optimization paths, with source-row fingerprints to avoid stale mappings after dataset updates.
- Appends only new scoring rows and new or reused entity-mapping rows; exact cache hits are skipped.
- Stores search-ready entity text so the similarity lookup can move to Databricks Vector Search without changing the app contract.

</details>

<details>
<summary><strong>Module 2 - Need And Supply</strong></summary>

This module chooses the district context for the mission before any facility is treated as the answer.

```mermaid
flowchart LR
    mission["Selected care need"] --> indicators["Relevant NFHS indicators"]
    facilities["Facility locations and capabilities"] --> density["Facility-density context"]
    pincode["Pincode district reconciliation"] --> density
    indicators --> district["Priority district"]
    density --> district
    district --> scope["Candidate search scope with uncertainty labels"]
```

- Combines NFHS district health indicators with facility-density context.
- Uses mission type to choose the relevant need and capability signals.
- Outputs the priority district and uncertainty labels before selecting an anchor.

</details>

<details>
<summary><strong>Module 3 - Trust And Evidence</strong></summary>

This module selects referral anchors and checks whether their claims are strong enough to act on.

```mermaid
flowchart LR
    scope["Priority district and care need"] --> candidates["Candidate facility window"]
    candidates --> ranking["Cached score or runtime score"]
    ranking --> anchors["Lead and backup anchors"]
    anchors --> trust["Duplicate, website, and claim review"]
    anchors --> facility_evidence["Facility claim citations"]
    trust --> evidence["Evidence ledger"]
    facility_evidence --> evidence
    evidence --> warnings["Visible warnings for weak evidence"]
```

- Ranks lead and backup facility anchors from the provided facilities table, preferring cached deterministic scores when their fingerprints match.
- Aligns the Trust Desk review to the selected lead facility, not an unrelated duplicate.
- Emits citation rows for facility claims and provenance rows for NFHS and density claims.

</details>

<details>
<summary><strong>Module 4 - Mission Control And Persistence</strong></summary>

This module turns evidence strength into an operator action and persists the review trail.

```mermaid
flowchart LR
    evidence["Need, supply, trust, and citation evidence"] --> gates["Seven pass-review-block gates"]
    gates --> packet["Mission packet"]
    packet --> recommendation["Operator-facing recommendation"]
    recommendation --> decision["Shortlist, verify first, or hold"]
    decision --> saved["Saved follow-up status and review note"]
    packet --> eval["Evidence-grounding and actionability evaluation"]
```

- Runs Need Scout, Supply Mapper, Facility Scout, Trust Verifier, Evidence Auditor, Mission Strategist, and Supervisor.
- Converts the weakest required gate into the operator-facing action: shortlist, verify first, or hold.
- Saves the follow-up status, review note, and gate trace to Lakebase so the app demonstrates persistent action.

</details>

## Input Datasets

Care Convoy uses the provided Virtue Foundation data as the primary product source. Derived rows support speed, evidence review, and validation without replacing the provided data.

| Dataset | Type | Role in the flow | User-facing evidence |
|---|---|---|---|
| `facilities` | Provided | Facility names, capabilities, locations, source URLs, doctors, capacity, descriptions, anchor ranking, and trust review. | Facility citations, source URL warnings, trust labels, anchor cards. |
| `nfhs_5_district_health_indicators` | Provided | District-level health need signals such as child underweight rate, insurance coverage, institutional births, and high blood pressure prevalence. | NFHS need summary and district provenance rows. |
| `india_post_pincode_directory` | Provided | District and state reconciliation for facility-density context. | Density provenance rows and district supply warnings. |
| `care_convoy_facility_scoring` | Derived | Append-only deterministic score features, candidate seed score, evidence counts, trust proxies, and source-row fingerprints. | Faster candidate ordering and scaled facility-fit scores. |
| `care_convoy_facility_entity_index` | Derived | Append-only facility identity mapping, duplicate flags, source-row fingerprints, and search-ready text. | Faster duplicate review, stale-cache fallback, and facility trust alignment. |
| `care_convoy_eval_v5_3` | Derived | Validation-only evaluation rows for evidence grounding and operator actionability. | MLflow evaluation report; not used for recommendations. |

## Backend Decision Design

The backend is designed as a staged evidence pipeline rather than a single ranking formula. Each stage adds a specific check, then the final stage converts the weakest required signal into the user-facing action.

| Backend stage | What it checks | Output |
|---|---|---|
| Need signal | NFHS district indicators and demand uncertainty. | A priority district with health-need context. |
| Supply context | Facility-density pressure and pincode/district reconciliation. | A warning when local supply evidence is thin or ambiguous. |
| Scoring cache | Deterministic facility score features keyed by source-row fingerprint. | Fast candidate ordering with runtime fallback for uncached rows. |
| Anchor selection | Lead and backup facility fit from the provided facilities table. | Candidate referral anchors for the chosen care need. |
| Trust review | Duplicate resolution, website status, and facility trust signals. | Confidence labels and review-required flags. |
| Evidence audit | Lead-anchor citations and unsupported-claim downgrades. | Source-backed evidence rows and visible gaps. |
| Action strategy | Need, supply, capability, trust, and evidence trade-offs. | Shortlist, verify-first, or hold guidance. |
| Persistence | Saved mission packet, gate trace, facility anchor, confidence, follow-up status, and review note. | A durable Lakebase review-note record. |

## Databricks Resources

- **Databricks Apps:** Hosts the Streamlit product experience.
- **Databricks Lakebase:** Persists saved review notes, follow-up statuses, and review context.
- **Databricks Asset Bundles:** Packages the app, resources, and deployment configuration for repeatable deploys.
- **MLflow:** Records tracing hooks and GenAI evaluation for evidence grounding and operator actionability.
- **Unity Catalog:** Governs the provided Virtue Foundation datasets and derived support tables.
- **Databricks SQL Warehouse:** Serves facility, district, and evidence queries for the app.
- **Databricks Model Serving:** Provides an optional summary hook when `CARE_CONVOY_ENABLE_LLM_SUMMARY=true`; deterministic summaries remain the default.

## Acknowledgements

Care Convoy was built during the hackathon period with original application code and submission-focused assets.

## License

Care Convoy is released under the MIT License. See [LICENSE](LICENSE) for details.
