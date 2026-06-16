## Inspiration
<!-- Judging: Product judgment, Ambition -->

Virtue Foundation's India facility dataset made one thing clear: the hardest part is not finding *a* hospital. It is deciding whether a medical team can responsibly act on messy, uneven evidence. Care Convoy was inspired by the gap between a data table and a field decision: **where should the next specialty care mission go, and what should we verify before moving?**

## What It Does
<!-- Judging: Product judgment, Evidence and uncertainty -->

Care Convoy is a Track 3 **Referral Copilot** for India. It helps an operations lead choose a care mission, review the priority district, inspect a lead and backup referral anchor, and decide whether to **shortlist**, **verify first**, or **hold**.

The recommendation is not a black-box score. Care Convoy treats the referral action as:

$$\text{next action}=f(\text{need},\text{supply},\text{facility fit},\text{trust},\text{citations})$$

Then it shows the weakest check. The UI surfaces NFHS need, facility-density context, duplicate and website trust checks, cited facility evidence, confidence labels, and saved notes.

## How We Built It
<!-- Judging: Technical execution, Evidence and uncertainty -->

We built Care Convoy as a Streamlit Databricks App using the provided Virtue Foundation tables: `facilities`, `nfhs_5_district_health_indicators`, and `india_post_pincode_directory`.

Unity Catalog and a Databricks SQL Warehouse serve the planning data. Derived Delta tables cache deterministic facility scoring and entity mappings by source-row fingerprint, so changed records can fall back safely instead of reusing stale trust signals. Lakebase persists saved notes and follow-up status. MLflow evaluation checks evidence grounding and operator actionability.

## Challenges
<!-- Judging: Evidence and uncertainty, Product judgment -->

The dataset is valuable precisely because it is imperfect. Facility IDs may not represent unique real-world facilities, capability fields can be sparse, district names do not always align cleanly, and public source URLs vary in quality. We turned those risks into product behavior: visible uncertainty labels, citation checks, duplicate flags, and gates that slow the recommendation when evidence is weak.

## Accomplishments
<!-- Judging: Product judgment, Technical execution, Ambition -->

Care Convoy goes beyond a map or ranked list. It produces a saveable mission packet with a priority district, lead anchor, backup anchor, confidence, warnings, evidence rows, and a durable follow-up note. The app keeps the workflow readable for an operations lead while still giving judges a clear view of the Databricks architecture behind it.

## What We Learned
<!-- Judging: Evidence and uncertainty, Product judgment -->

We learned that data-for-good tools need humility built into the interface. A useful referral tool should not hide uncertainty; it should show which fact needs verification before action. Trust is not one feature; it is a chain across source quality, entity matching, capability evidence, and persistence.

## What's Next
<!-- Judging: Ambition -->

Next, we would add travel-time routing, stronger population denominators, Vector Search-backed facility evidence retrieval, and a review queue for analysts who validate weak or duplicate records over time.
