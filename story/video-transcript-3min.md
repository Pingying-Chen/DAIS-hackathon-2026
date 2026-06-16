# Care Convoy 3-Minute Demo Transcript

Target length: 2:50 to 3:00 at a calm pace. Keep the browser on the Databricks App, zoom around 90-100%, and start with the Referral Planner loaded.

## Recording Setup

1. Open the deployed Care Convoy app and wait until the recommended next move is visible.
2. Do one warm-up run: click through the five views once so Streamlit and Databricks queries are warm.
3. Return to the Referral Planner with the Plan view selected.
4. Put this script on a second monitor, phone, or printed page outside the recorded area.
5. Record the browser window plus microphone with Loom, OBS, Zoom, or macOS screen recording.
6. Start recording, wait two seconds in silence, then begin speaking.
7. Keep the cursor still while speaking, and move only at the action markers.

If the live data differs from the values below, read the values shown on screen. The story still works as long as you name the action, district, lead anchor, confidence, citations, and saved note.

## Timed Script

### 0:00-0:15

(Show the title and top recommendation. Do not click yet.)

Care Convoy is our Track 3 Referral Copilot. It helps an operations lead in India choose where a specialty medical team should go next, which facility to review first, and what evidence to verify before action.

### 0:15-0:35

(Move the cursor over the Recommended next move panel.)

The app starts with the decision. In this run, it says verify first for maternal health in Nagpur, Maharashtra, with Sunrise Women and Surgical Centre as the lead anchor. The caution matters: verify before commitment.

### 0:35-0:55

(Point briefly at the filters, then click Build Referral Plan. Wait for the screen to settle before continuing.)

The setup is intentionally simple: care need, state, district, and minimum certainty. When I build the plan, the recommendation, map, facilities, evidence, and review note update together for a non-technical operations lead.

### 0:55-1:15

(Stay on Plan. Slowly move the cursor across the map, Referral plan card, and Lead referral anchor card.)

The Plan view combines district need, local supply, and facility fit. Nagpur is the priority district, and the lead anchor has strong mission fit, moderate trust support, and a website-status warning. Messy data becomes a practical next step.

### 1:15-1:45

(Click Why This Place. Pause one beat. Move down the gate list.)

Now I open Why This Place. This is the uncertainty model. Each gate is pass, review, or hold: need, supply, facility fit, trust, citations, strategy, and supervisor action. The weakest check drives the recommendation, so weak evidence slows the plan down.

### 1:45-2:05

(Click Compare Anchors. Hover over the two anchor cards or chart.)

Compare Anchors keeps us from trusting one opaque score. The lead and backup facilities are compared on urgency support, facility fit, trust, evidence certainty, and duplicate clues. A referral team sees the best candidate and a backup before making contact.

### 2:05-2:30

(Click Evidence Details. Move from the support cards to citation notes.)

Evidence Details makes high-stakes claims inspectable. The app shows duplicate clues, website status, trust support, source notes, citation rows, and thin-evidence warnings. Missing or weak citations downgrade the recommendation instead of being presented as certain.

### 2:30-2:50

(Click Save Review Note. In the note box, keep or paste: "Verify current services, referral contact, and source support before shortlisting." Choose the suggested follow-up status, then click Save Review Note.)

Finally, I save the operational follow-up. The note captures what the team must verify before shortlisting this anchor. Care Convoy persists the mission context, facility, confidence, recommendation, and note, so the next reviewer can continue from the same evidence-backed decision.

### 2:50-3:00

(Click Product Introduction, or stay on the saved note confirmation if time is tight.)

Care Convoy is built on the provided Virtue Foundation facility dataset, NFHS district indicators, and India pincode data in Databricks. The demo payoff is simple: not just a map, not just a hospital list, but a cautious, cited, saveable referral plan.

## Live Judge Version

Use the same click path, but make the spoken version conversational:

1. Title and track: "This is Care Convoy, Track 3 Referral Copilot."
2. Recommended next move: name the action, district, anchor, and caution.
3. Plan: show map plus lead anchor.
4. Why This Place: show pass, review, hold gates.
5. Compare Anchors: show lead and backup.
6. Evidence Details: show citations, website status, duplicate clues, and uncertainty.
7. Save Review Note: save one short note to prove persistence.
8. Close: "The product turns imperfect facility data into a cautious, cited referral plan."

## Timing Notes

- Do not read faster than normal conversation. The script is designed with click time included.
- If the app lags, stay quiet for one second, then say: "The same plan is recalculating across the map, evidence, and saved-note workflow."
- If you are at 2:40 before saving the note, skip Product Introduction and end on the saved-note confirmation.
- If you are at 2:30 before Evidence Details, skip Compare Anchors and go straight to Evidence Details, then Save Review Note.
- The three words judges should remember are: cautious, cited, saveable.
