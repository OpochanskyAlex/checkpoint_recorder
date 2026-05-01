---
doc: REVIEW
reviews: srs-cancel-button-delta
project: checkpoint_recorder
reviewer: system-analyst-reviewer
reviewed_version: 0.1
score: 9.1
verdict: approved
updated: 2026-05-01
tags: [project-docs, review]
---

# SA Review: Cancel Button Delta (FR32 + UC16 A6)

Review scope: FR32 (new), FR29 update (Cancel button termination path), Command Interface table new row (inline button — Cancel picker), UC16 update (A6 new alternative flow, T1/T2 step 8 and step 4/6 branch text updated, A1 step 4 added, A2 step 6 added, postconditions updated).

This is a delta-only review. Prior approved content (FR1–FR31, UC16 original flows, DM6 state machine, NFR1–NFR18, etc.) is not re-adjudicated except where the delta touches it.

Cross-check: FR32 vs BRD R19; UC16 A6 vs FR31 and FR32; DM6 state machine coverage; Command Interface table completeness.

---

## Universal Checks

**U1 Boundary** — PASS. Delta writes are confined to `system/srs.md` and `system/cases/uc-16-select-metric-picker.md`. No writes outside the `system/` directory detected.

**U2 Version discipline** — PASS. SRS remains `version: 0.1`; UC16 remains `version: 0.1`. Correct for an in-progress feature-addition delta. `updated` timestamps on both files show `2026-05-01`, matching the changelog entry.

**U3 Refs hygiene** — PASS. UC16 frontmatter refs list `{doc: brd, version: 0.1}`, `{doc: srs, version: 0.1}`, and `{doc: feat-smart-metric-picker, version: 0.1}` — all correct. SRS refs list `{doc: brd, version: 0.1}`. BRD is at version 0.1. FR32 `<-` trace includes `[[brd#R19|R19 Cancel button in picker keyboard]]` and `[[us-8-metric-picker|US8 Select a metric via inline picker]]` — both correct. No missing ref documents.

**U4 Obsidian links** — PASS. UC16 traces section includes `[[srs#FR32|FR32 Cancel button on picker keyboard]]`. FR32 in SRS links `[[brd#R19|R19 Cancel button in picker keyboard]]` and `[[us-8-metric-picker|US8 Select a metric via inline picker]]`. FR29 updated text references FR31 via prose; no broken Obsidian links detected.

**U5 Activity tags** — PASS. FR32 carries `@logging @management` — correct and consistent with R19 which spans both activity domains. The tags are from the declared taxonomy `[logging, management, analytics, alerting, account, discovery, General]`. No invalid tags.

**U6 ID stability** — PASS. FR32 follows FR31 sequentially. No existing FR IDs modified except FR29 (in-scope additive text). UC16 version unchanged at 0.1. No renumbering of existing IDs detected.

**US file existence check** — PASS. `us-8-metric-picker.md` exists and contains AC8.12 which is the acceptance criterion governing Cancel button behavior. The file's trace section includes `[[brd#R19|R19]]`. File is correctly referenced from FR32.

**BRD version in refs** — PASS. SRS refs `{doc: brd, version: 0.1}`. UC16 refs `{doc: brd, version: 0.1}`. BRD is confirmed at version 0.1 with R19 present.

---

## Findings

### F1 — minor | Data model & state | DM6 state machine not updated for FR32 Cancel arc

**Location:** SRS State Machines section, DM6 ConversationState lifecycle diagram.

**Description:** FR32 and UC16 A6 introduce a new user-initiated cancellation path triggered by pressing the Cancel inline button while in `PendingMetricPicker` state. FR29 is updated to state "pressing the inline Cancel button (`callback_data = "cancel"`) produces the same outcome as FR31." However, the DM6 ConversationState state machine diagram has NOT been updated to reflect this. The diagram currently shows:

```
PendingMetricPicker --> Idle : timeout / error / management done / FR31
```

The FR31 arc covers `/cancel` command-initiated cancellation. The FR32 Cancel button path (inline keyboard callback) produces the same state outcome but is a distinct trigger mechanism — a callback_query not a command message. Given that the previous review (F3 in srs-smart-metric-picker-v0.1) explicitly called out the need to add `/cancel` arcs once FR31 was specced, and FR31 was subsequently added, the DM6 diagram was updated to include `FR31` in the existing `PendingMetricPicker → Idle` arc. That arc now implicitly covers FR32 because FR32 is specified as producing an identical outcome to FR31. However, the arc label `timeout / error / management done / FR31` does not mention FR32, leaving a gap for readers who encounter FR32 independently.

**Impact:** Low functional risk since the behavior is specified as identical to FR31. Diagram readers and the implementing architect may overlook that a callback_query (not a command message) can also clear PendingMetricPicker state. The state machine is the authoritative transition diagram; omitting FR32 from it means the diagram is not self-contained.

**Suggested fix:** Update the DM6 `PendingMetricPicker --> Idle` arc label to read `timeout / error / management done / FR31 / FR32`. Also add `PendingPickerValue --> Idle : FR31 / FR32` if the Cancel button is reachable from PendingPickerValue (see F2).

---

### F2 — minor | Completeness | Cancel button reachability from PendingPickerValue not addressed

**Location:** UC16 A6; FR32 body; UC16 postconditions.

**Description:** UC16 A6 states it branches from "T1 step 8, T2 step 4 or 6, A1, or A2." It does NOT list A3 (PendingPickerValue — value received) as a branch source. This is correct for A3 itself (A3 is the success path after selection, where the picker keyboard has already been replaced). However, the question is what happens if the picker keyboard remains visible while the state has advanced to PendingPickerValue. In the current flow:

- User selects a metric → step 12 of T1/T2 routes `logging` path → state transitions to PendingPickerValue.
- The original picker message in Telegram is NOT explicitly replaced or deleted at this point; the user receives a new prompt "Enter value for [metric_name]:" but the previous inline keyboard message with its Cancel button is still visible in the Telegram chat.
- If the user now presses the Cancel button on the **stale picker keyboard** (from the PendingMetricPicker phase), the callback handler fires. At this point ConversationState = PendingPickerValue, not PendingMetricPicker.

This is not the same as E3 ("Inline callback received in unexpected state — ConversationState ≠ PendingMetricPicker") because FR29 explicitly routes `PendingMetricPicker` callbacks. But FR32 says the Cancel button produces the same outcome as FR31, and FR31 applies to all non-Idle states. The question is: does the Cancel button callback while in PendingPickerValue state trigger A6 (correct, FR32/FR31 intent) or E3 (unintended, session expired message)?

FR32 text says "every picker keyboard display includes a Cancel button as the last inline button; pressing it produces an outcome identical to FR31." FR31 covers "all non-Idle states." This implies FR32 Cancel should work from PendingPickerValue too. But neither FR32, FR29, nor UC16 A6 explicitly says so, and E3 in UC16 says callbacks in unexpected states are ignored or produce "Session expired."

**Impact:** Medium. If E3 fires instead of A6 when the user presses Cancel from PendingPickerValue, the user sees "Session expired. Please re-issue the command." rather than "Cancelled. You're back to the main menu." This contradicts the user's reasonable expectation (they pressed Cancel). It also leaves state as PendingPickerValue with no way to clear it except timeout (24h).

**Suggested fix:** (a) Add explicit routing: in FR29 or FR32, state that `callback_data = "cancel"` received in ANY non-Idle ConversationState (not only PendingMetricPicker) is routed to the FR31/FR32 cancel outcome. This aligns with FR31's "applies to all non-Idle states" intent. (b) Alternatively, in UC16, update A6 to add "Also branches from: PendingPickerValue state when Cancel button on stale picker keyboard is pressed" and update E3 to exclude `callback_data = "cancel"` from the "ignored" path.

---

### F3 — nit | API contract | Command Interface Cancel button row: callback_data format inconsistency

**Location:** SRS Command Interface table, new row "(inline button — Cancel picker)"; FR32 body.

**Description:** The Command Interface row for "(inline button — Cancel picker)" specifies `Callback data: cancel` (no quotes, no braces). FR32 body specifies `callback_data = "cancel"` (6 bytes). The existing "(inline button — metric selection)" row uses the format `Callback data: {picker_metric_id}` (braces, no quotes). The existing "(inline button — Create metric)" row uses `Callback data: {action: "create", typed_name: "<str>"}`. The Cancel row's format deviates from the pattern established by the other two rows.

**Impact:** Cosmetic but the Command Interface table is used as the authoritative contract reference by the architect. Format inconsistency requires the reader to manually interpret whether `cancel` is a literal string, a variable name, or a JSON key.

**Suggested fix:** Normalize to `Callback data: "cancel"` (quoted literal string) or `Callback data: {action: "cancel"}` if a JSON envelope is the actual wire format. Confirm which format is consistent with `callback_data = "cancel"` (6 bytes) in FR32 — this implies a plain string literal, so `Callback data: "cancel"` is the correct format.

---

### F4 — nit | Completeness | UC16 A6 does not explicitly dismiss the picker message

**Location:** UC16 A6, step 3–4.

**Description:** A6 step 2 calls `answer_callback_query` (correctly, per ADR-013 which requires answering all callback queries). Step 3 transitions state. Step 4 dispatches the reply. However, A6 does not state whether the picker keyboard message is edited/deleted (e.g., via `edit_message_text` or `delete_message`) when the Cancel button is pressed. For comparison, A1 step 2 explicitly says "current message replaced with full inline keyboard." The `/cancel` command path (FR31) operates on a command message, not an inline keyboard, so it also does not address this. The architect must infer whether to leave a stale keyboard visible or remove/replace it.

**Impact:** Low — does not affect functional correctness of state or reply. Affects UX cleanliness: a stale picker keyboard with a Cancel button remaining visible after cancellation is poor UX.

**Suggested fix:** Add to A6 step 2 or between steps 2 and 3: "Edit the picker keyboard message to remove the inline keyboard (replace with plain confirmation text or delete the message)." This removes the stale keyboard from view.

---

### F5 — praise | Traceability completeness

**Location:** FR32, BRD R19, US8 AC8.12, UC16 traces.

FR32 carries a clean `<-` trace to `[[brd#R19|R19 Cancel button in picker keyboard]]` and `[[us-8-metric-picker|US8]]`. R19 in the BRD is present and links downstream to FR32 via US8 AC8.12. The UC16 traces section was updated to include `[[srs#FR32|FR32 Cancel button on picker keyboard]]`. The traceability chain is complete: R19 → AC8.12 → FR32 → A6, with no orphan requirements on either end.

---

### F6 — praise | FR32 and FR29 co-specification

**Location:** FR29 updated text; FR32 new text.

The decision to specify FR32 as "identical outcome to FR31" rather than re-specifying the outcome in full is the correct approach — it creates a single source of truth for cancellation behavior and avoids contradictions. FR29 correctly cross-references FR31 in its updated Cancel button note. FR32 reinforces this with `callback_data = "cancel"` (6 bytes) which is a precise wire-level spec that the architect can implement without ambiguity on the happy path.

---

### F7 — praise | UC16 A6 branching coverage

**Location:** UC16 A6 branch declaration.

A6 correctly enumerates every point in the UC16 flows from which the Cancel button is reachable while in PendingMetricPicker state: T1 step 8 (main picker displayed), T2 step 4 or 6 (fuzzy picker or zero-match displayed), A1 (overflow expanded), A2 (Create button display). This covers all picker keyboard presentations for PendingMetricPicker. The A1 step 4 addition ("Cancel button remains present on the expanded keyboard; pressing it → A6") is a correct and necessary addition that prevents the "Show all fits" expansion from hiding the cancellation path.

---

## Per-Criterion Scores

### Criterion 1 — Traceability to BRD (weight 0.25)

Score: **9.5 / 10**

FR32 traces cleanly to R19 and US8. R19 in BRD is present and covers the full scope of Cancel button placement (bare command, fuzzy match, overflow, zero-match Create-button display) — FR32 mirrors this language exactly. US8 AC8.12 is the downstream acceptance criterion and is correctly cited. UC16 traces section updated. No orphan FRs or BRD requirements introduced. FR29 update is additive and consistent with existing traces. Minor deduction only: FR31 (which FR32 defers to for outcome specification) traces to `[[brd#G1|G1]]` only, not to a specific R-requirement — this is a carry-forward from the previous approved delta and is not re-adjudicated here, but it means the Cancel-outcome spec sits one level removed from a named BRD requirement for the management activity domain.

---

### Criterion 2 — Completeness of functional spec (weight 0.25)

Score: **8.5 / 10**

FR32 specifies the trigger (Cancel button on any picker keyboard), the trigger conditions (all four display contexts), the callback data (`"cancel"`, 6 bytes), and the outcome (identical to FR31). UC16 A6 covers the happy path correctly. A1 and A2 are updated to include the Cancel reachability note. Postconditions updated with explicit Cancel button outcome text. Deductions: (a) F2 — PendingPickerValue state is not addressed as a Cancel button reachability case; the interaction between a stale picker keyboard and PendingPickerValue state is unspecified, creating an implementation ambiguity of medium impact; (b) F4 — picker message dismissal behavior on Cancel not specified, leaving UX detail to architectural discretion.

---

### Criterion 3 — Data model & state consistency (weight 0.15)

Score: **8.5 / 10**

The DM6 state machine already contains the `PendingMetricPicker → Idle` arc with `FR31` as a label (added in the post-review fix pass). FR32 produces an identical state outcome. No new states are introduced. The state model is internally consistent. Deduction: F1 — DM6 diagram arc label does not include FR32, making the diagram an incomplete reference for the Cancel button callback path. This is a documentation gap, not a logical inconsistency, but the state machine is the authoritative transition diagram per the rubric.

---

### Criterion 4 — API contract precision (weight 0.15)

Score: **9.0 / 10**

The new "(inline button — Cancel picker)" row in the Command Interface table is present with auth, callback data, success response, and error response fields populated. The success response "Cancelled. You're back to the main menu." matches FR31 and FR32. The error response is listed as "—" (none) which is acceptable given that E3 (unexpected state) already covers the error path. Deduction: F3 — `callback_data` format notation (`cancel` without quotes) is inconsistent with the JSON-envelope pattern used by the other two inline button rows; requires reader interpretation.

---

### Criterion 5 — NFR measurability (weight 0.10)

Score: **10.0 / 10**

No new NFRs introduced by this delta. Existing NFR18 (picker keyboard ≤5s p95) applies to the Cancel button display as part of the picker keyboard presentation, which is unchanged. FR32 does not introduce any performance-sensitive path that would require a new NFR. All existing NFRs (NFR1–NFR18) are unmodified and remain measurable.

---

### Criterion 6 — Use case diagram currency (weight 0.10)

Score: **9.5 / 10**

`use-case-diagram.puml` exists. UC16 node is present. The Cancel button (FR32) is an enhancement to an existing use case (UC16), not a new use case node. No new UC file was added; no diagram node changes are required. The diagram correctly reflects the current UC count (UC1–UC16) with all nodes present and all `uc-*.md` files having corresponding nodes. The diagram's `updated` date (changelog `2026-05-01T00:02Z`) is the same run as the delta. Minor: the diagram was not re-timestamp-updated in this delta because no structural change was made to it — this is correct behavior and not a deduction. Hairline deduction only for the carry-forward UC16 placement in Logging-only package (noted in prior review, not re-adjudicated).

---

## Weighted Score Calculation

| # | Criterion | Weight | Score | Contribution |
|---|---|---|---|---|
| 1 | Traceability to BRD | 0.25 | 9.5 | 2.375 |
| 2 | Completeness of functional spec | 0.25 | 8.5 | 2.125 |
| 3 | Data model & state consistency | 0.15 | 8.5 | 1.275 |
| 4 | API contract precision | 0.15 | 9.0 | 1.350 |
| 5 | NFR measurability | 0.10 | 10.0 | 1.000 |
| 6 | Use case diagram currency | 0.10 | 9.5 | 0.950 |
| **Total** | | **1.00** | | **9.075** |

**Rounded score: 9.1**

No blockers detected. No score cap applies.

---

## Verdict: `approved`

Score 9.1 ≥ 7.0 threshold. No blockers. Two minor findings (F1, F2) and two nits (F3, F4). The delta is well-formed and traceable. F2 is the highest-priority item — the PendingPickerValue / stale picker keyboard Cancel interaction is unspecified and could produce a confusing "Session expired" message when the user intends to cancel. This should be resolved before implementation of the callback router.

`suggest_major_bump: false` — additive delta; SRS remains at v0.1 per workflow convention.

---

## Summary

**Top 3 findings:**

1. **F2 (minor)** — Cancel button reachability from PendingPickerValue state is unspecified. After a user selects a metric (state → PendingPickerValue), the original picker keyboard with its Cancel button remains visible in the Telegram chat. If the user presses it, the callback handler fires with ConversationState = PendingPickerValue. FR32 says Cancel produces the same outcome as FR31, and FR31 applies to all non-Idle states — but neither FR29 nor UC16 A6 explicitly routes this case. E3 may fire instead of A6, producing "Session expired" and leaving the user stuck in PendingPickerValue until the 24h timeout.

2. **F1 (minor)** — DM6 ConversationState state machine diagram does not include FR32 in the `PendingMetricPicker → Idle` arc label. The arc currently reads `timeout / error / management done / FR31`. Adding `/ FR32` would make the diagram self-contained and distinguish the command-initiated cancel (FR31) from the inline-button-initiated cancel (FR32) for the architect.

3. **F3 (nit)** — Command Interface table Cancel picker row uses unquoted `cancel` as the callback data value, inconsistent with the JSON-envelope notation used by the metric selection and Create button rows. Should be normalized to `"cancel"` (quoted literal) to match FR32's prose specification of `callback_data = "cancel"` (6 bytes).

**Next step:** Resolve F2 (routing spec for Cancel button in PendingPickerValue state) before or during architecture implementation of the callback router. F1 is a quick diagram label update. F3 and F4 are cosmetic fixes that can be bundled into the next SA pass.
