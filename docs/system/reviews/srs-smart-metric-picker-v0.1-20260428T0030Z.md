---
doc: REVIEW
reviews: srs-smart-metric-picker-delta
project: checkpoint_recorder
reviewer: system-analyst-reviewer
reviewed_version: 0.1
score: 8.4
verdict: approved
updated: 2026-04-28
tags: [project-docs, review]
---

# SA Review: Smart Metric Picker Delta (SRS v0.1)

Review scope: FR22–FR30, updated FR6, NFR18, DM6 extension, Command Interface updates, BR13–BR14, SU-010, UC16, use-case-diagram additions, annotations on UC2/UC6/UC7/UC8/UC10.
Cross-check: FR22–FR30 vs FR1–FR21; FR6 vs R2/BRD; UC16 vs US8 ACs.

---

## Universal Checks

**U1 Boundary** — PASS. All SA writes are within `system/` (srs.md, cases/uc-16-*, cases/uc-2-*, uc-6-*, uc-7-*, uc-8-*, uc-10-*, use-case-diagram.puml). No writes detected outside the boundary.

**U2 Version discipline** — PASS. UC16 opens at `version: 0.1`. SRS remains `version: 0.1` (additive in-progress draft). Correct for feature-addition workflow.

**U3 Refs hygiene** — PASS with one minor gap. UC16 refs list `brd v0.1`, `srs v0.1`, and `feat-smart-metric-picker v0.1` — all correct. UC2/UC6/UC7/UC8/UC10 refs list `brd v0.1` and `srs v0.1` but do NOT list `feat-smart-metric-picker v0.1` despite receiving direct annotations from the feature. This is a minor hygiene gap; the feature spec is the authoritative source for the annotation notes those files received.

**U4 Obsidian links** — PASS. First-mention links in UC16 follow `[[srs#FR22|FR22 Picker bare-command trigger]]` pattern. Subsequent intra-file references are shorthand. No broken links detected. `[[us-8-metric-picker|US8 Select a metric via inline picker]]` correctly points to existing file. `[[uc-16-select-metric-picker|UC16]]` references in UC2/UC6/UC7/UC8/UC10 all point to the new file.

**U5 Activity tags** — PASS. FR22 `@logging @management`, FR23 `@logging @management`, FR24 `@logging @management`, FR25 `@logging @management`, FR26 `@logging @management`, FR27 `@logging`, FR28 `@management`, FR29 `@logging @management`, FR30 `@logging`. NFR18 `@logging @management`. BR13 `@logging @management`, BR14 `@logging`. All tags are from the declared activities taxonomy `[logging, management, analytics, alerting, account, discovery, General]`. No invalid tags.

**U6 ID stability** — PASS. FR22 continues from FR21; FR30 is the terminal new FR. BR13 continues from BR12; BR14 follows BR13. NFR18 follows NFR17. No existing IDs (FR1–FR21, NFR1–NFR17, BR1–BR12) were modified except FR6 trigger update, which is in scope and documented.

**US file existence check** — PASS. `us-8-metric-picker.md` exists and contains AC8.1–AC8.11 plus AC8.6b. All referenced `us-*.md` files for FR6 (us-1-log-metric) and FR22–FR30 (us-8-metric-picker) exist on disk.

**BRD version in refs** — PASS. SRS refs `{doc: brd, version: 0.1}`. UC16 refs `{doc: brd, version: 0.1}`. BRD is at version 0.1. Correct.

---

## Findings

### F1 — minor | Completeness | UC16 edge cases / FR29
**Location:** UC16 edge case "User sends free-text while PendingMetricPicker"; FR29 body.
**Description:** UC16 specifies that free-text received in PendingMetricPicker state triggers the reminder "Please select a metric from the keyboard above, or use /cancel to cancel action." However, `/cancel` does not appear anywhere in the SRS Command Interface table. There is no FR defining `/cancel` behavior, no ConversationState transition specified for `/cancel`, and no error path. The instruction to the user to "use /cancel" is a dead reference — a user pressing /cancel will receive either an unrecognized command response or nothing, neither of which matches the implied UX promise.
**Impact:** AC8.9 (timeout/cancellation) is addressed by timeout only. Explicit user-initiated cancellation is described in UC16 copy but not specced. Architect cannot implement the `/cancel` path from the current SRS.
**Suggested fix:** Either (a) add a `/cancel` command row to the Command Interface table with `auth: active`, parameters: none, behavior: clears any non-Idle ConversationState → Idle, dispatches "Action cancelled" message, and add a corresponding FR (FR31 or similar); or (b) remove the "/cancel" reference from UC16 and replace it with an instruction that only timeout cancels the session. Option (a) is strongly preferred for usability.

---

### F2 — minor | Traceability | UC16 refs hygiene (U3 gap)
**Location:** `uc-2-log-metric.md`, `uc-6-archive-metric.md`, `uc-7-delete-metric.md`, `uc-8-configure-alert.md`, `uc-10-request-chart.md` — frontmatter `refs` section.
**Description:** Each of these five files received substantive annotations from the smart-metric-picker feature addition (edge case paragraphs linking to UC16, FR22/FR23/FR28 references). Their `refs` blocks still list only `brd v0.1` and `srs v0.1` but do not list `feat-smart-metric-picker v0.1`. Per U3, refs must reflect all documents that materially influenced the file's content in this edit.
**Suggested fix:** Add `{doc: feat-smart-metric-picker, version: 0.1}` to the refs block of each of the five annotated UC files. Alternatively, SA may argue the SRS is the single consolidation point and the feat doc is upstream of it — acceptable if documented as a convention in the SA's working notes.

---

### F3 — minor | Data model & state | DM6 `/cancel` transition gap
**Location:** SRS DM6 ConversationState state machine diagram.
**Description:** The state machine correctly covers all transitions referenced by FR22–FR30, including timeout paths (SU-009) to Idle. However, because UC16 references `/cancel` (see F1), there is an implied user-initiated cancellation transition from `PendingMetricPicker → Idle` and `PendingPickerValue → Idle` that is not shown in the diagram. Until F1 is resolved (either by adding a `/cancel` FR or removing the reference), the state machine is incomplete relative to UC16's own stated edge case.
**Suggested fix:** Contingent on F1 resolution: if `/cancel` FR is added, add `PendingMetricPicker --> Idle : /cancel command` and `PendingPickerValue --> Idle : /cancel command` transitions to the DM6 diagram.

---

### F4 — nit | API contract / Command Interface
**Location:** SRS Command Interface table, inline button row.
**Description:** The `(inline button — picker)` row lists `Callback data: {picker_metric_id}` as the parameter. This is a single field. For UC16 T2 step 5 zero-match logging path (A2), the user presses a "Create [typed_name]" button — a different callback type with different data (e.g., `{action: "create", typed_name: "<str>"}`). The Command Interface row does not differentiate picker-metric callbacks from Create-button callbacks. This is low-severity because the distinction is documented in UC16 A2 and FR27, but the Command Interface table is incomplete as a standalone reference.
**Suggested fix:** Split the inline button row into two: one for metric selection callbacks (`{picker_metric_id}`) and one for the Create button callback (`{action: "create", typed_name: "<str>"}`), or add a note in the Parameters column acknowledging the two callback types.

---

### F5 — nit | Completeness | UC16 A2 state transition ambiguity
**Location:** UC16 alternative flow A2 step 2 ("Create button pressed — logging zero-match").
**Description:** A2 step 2 states `ConversationState → PendingPeriodicity`. However, at this moment the state is `PendingMetricPicker` (per T2 step 5). The transition should be `PendingMetricPicker → PendingPeriodicity`, but the DM6 state machine only shows `Idle → PendingPeriodicity`. The Create button press from within `PendingMetricPicker` transitions to `PendingPeriodicity` without returning to `Idle` first — this is not shown as a valid arc in the DM6 diagram. This is a latent ambiguity for the architect (can PendingMetricPicker transition directly to PendingPeriodicity, or must it clear to Idle first?).
**Suggested fix:** Add the arc `PendingMetricPicker --> PendingPeriodicity : FR27 Create button pressed (logging zero-match)` to the DM6 state machine, or explicitly note in the diagram that the transition goes via Idle and document the atomic nature of the two-step in FR27.

---

### F6 — praise | Traceability completeness
**Location:** FR22–FR30, BRD R12–R18.
Every new FR (FR22–FR30) carries explicit `<-` traces to BRD R-requirements AND to US8. Every new BRD requirement (R12–R18) has at least one downstream FR. R17 → FR27 and R18 → FR28 are correctly paired for the split zero-match behavior. BR14 closes the loop on silent creation prevention end-to-end. No orphan FRs or orphan BRD requirements detected.

---

### F7 — praise | FR6 update consistency
**Location:** FR6, DM2 state machine, UC2 A1, BRD R2.
The FR6 trigger update ("Create button via FR27, not auto-triggered on unrecognized name") is exactly consistent with BRD R2 (rewritten to require explicit "Create [typed_name]" button) and BR14 (no silent creation). The DM2 state machine note explicitly calls this out. UC2 A1 carries the dated annotation and correctly redirects to UC16/FR27. The FR6 traces include both `R2` and `R17` — dual-trace is appropriate because R2 defines the creation mechanic and R17 defines the new trigger. Strong execution here.

---

### F8 — praise | DM6 state machine coverage
**Location:** SRS State Machines section, DM6.
Both new states (PendingMetricPicker, PendingPickerValue) are fully specified with transitions, timeout arcs (SU-009), `state_data` contents, and routing logic. The `command_context` field in `state_data` cleanly differentiates logging from management paths without requiring additional state nodes (Q-FEAT-1 resolution is well-designed). The timeout paths are consistent between the diagram and FR29/FR30 text.

---

### F9 — praise | NFR18 measurability
**Location:** NFR18.
NFR18 is precisely formulated: metric, latency bound (≤5s p95), measurement point (Telegram Gateway send time), and dual trigger conditions (bare command receipt vs NLP parse completion). This is better than the vague "system should respond quickly" pattern; it gives the architect an unambiguous SLA and a defined measurement boundary.

---

### F10 — praise | UC16 AC coverage
**Location:** UC16 flows vs US8 ACs.
All 11 acceptance criteria (AC8.1–AC8.11 plus AC8.6b) are traceable to UC16 flows: AC8.1 → T1 main flow; AC8.2 → FR25/T1 step 5; AC8.3 → A5; AC8.4 → T2 main flow; AC8.5 → FR25/T2; AC8.6 → A2 (Create button); AC8.6b → T2 zero-match management → FR28; AC8.7 → T1 step 8–9; AC8.8 → T1 step 10–11; AC8.8b → A3; AC8.9 → A4; AC8.10/AC8.11 → FR24 / T1 step 4. No AC is unaddressed.

---

## Per-Criterion Scores

### Criterion 1 — Traceability to BRD (weight 0.25)

Score: **8.5 / 10**

All new FRs (FR22–FR30) trace to BRD R12–R18 and US8. FR6 update traces to R2 and R17. NFR18 traces to R12/R13 and FRs. BR13 traces to DM6/FR3; BR14 traces to FR27/FR6. R2 update in BRD is consistent with FR6 change. BRD G1 and G2 downstream coverage is complete. Minor deductions: (a) UC2/UC6/UC7/UC8/UC10 refs blocks do not cite feat-smart-metric-picker despite direct annotation from it (F2, minor); (b) the `/cancel` reference in UC16 edge case introduces an undocumented user-facing command without a BRD requirement or FR trace (F1 upstream gap).

---

### Criterion 2 — Completeness of functional spec (weight 0.25)

Score: **8.0 / 10**

FR22–FR30 cover all required paths: bare command, fuzzy match, recency sort, overflow, last-3-values, zero-match Create (logging), zero-match no-match (management), PendingMetricPicker state, PendingPickerValue state. UC16 maps to all US8 ACs. Error paths E1–E5 in UC16 are present and meaningful. Edge cases are comprehensive. Deductions: (a) `/cancel` command is referenced in UC16 edge case but not specified (F1 — this is a missing functional path, not just a style issue); (b) the A2 state transition from PendingMetricPicker → PendingPeriodicity is implied but not formally described as a valid arc (F5); (c) Command Interface table conflates two distinct callback types in a single row (F4, nit).

---

### Criterion 3 — Data model & state consistency (weight 0.15)

Score: **8.5 / 10**

DM6 enum extended correctly with PendingMetricPicker and PendingPickerValue. Both new states have `state_data` schemas documented inline. State machine covers all transitions mentioned in FRs and UCs including timeout arcs. All entities retain PKs; relationships explicit. One deduction: the DM6 state machine does not include a `PendingMetricPicker → PendingPeriodicity` arc for the A2 (Create button) path — currently only `Idle → PendingPeriodicity` exists (F5). This is a diagram gap that may mislead the architect about whether a direct state transition is intended.

---

### Criterion 4 — API contract precision (weight 0.15)

Score: **8.5 / 10**

Command Interface table updated correctly: five commands now carry `[metric_name]` as optional parameter with bare-command picker trigger noted. FR column updated for all affected commands. The new inline button callback row is present and includes auth, callback data schema, success response, and error response. Minor deduction: the single inline button row conflates picker-metric callbacks and Create-button callbacks which have different data shapes (F4). Not a full point deduction because FR27 and UC16 cover the distinction in their respective sections.

---

### Criterion 5 — NFR measurability (weight 0.10)

Score: **9.5 / 10**

NFR18 is precisely specified with metric (picker keyboard presented), bound (≤5s p95), trigger conditions (command receipt for bare; NLP parse completion for fuzzy), and measurement point (Telegram Gateway send time). SU-010 provides a numeric threshold (70, 0–100 scale) with scoring function (`token_set_ratio`) and environment variable name (`FUZZY_MATCH_THRESHOLD`). Existing NFRs NFR1–NFR17 unmodified. Minor nit only: NFR18 references Q-FEAT-4 as "resolved" in the same sentence but that cross-reference is slightly verbose; no score impact.

---

### Criterion 6 — Use case diagram currency (weight 0.10)

Score: **9.0 / 10**

`use-case-diagram.puml` exists. UC16 node is present in the Logging package. User → UC16 connection present. Five `UC16 ..> UCx <<extend>>` relationships added for UC2, UC6, UC7, UC8, UC10 — correctly captures the extend relationships. Every `uc-*.md` (UC1–UC16) has a node in the diagram; every diagram node has a corresponding file. Diagram timestamp (per changelog) is `2026-04-28T00:20Z`, same run as UC16 creation. Minor deduction: UC16 is placed in the "Logging" package only; since the feature spans both Logging and Management activities, this is a mild misrepresentation of scope. Functionally not a blocker — PlantUML does not support multi-package membership and the extend links to UC6/UC7/UC8/UC10 in Management are present. No actor or connection gaps.

---

## Weighted Score Calculation

| # | Criterion | Weight | Score | Contribution |
|---|---|---|---|---|
| 1 | Traceability to BRD | 0.25 | 8.5 | 2.125 |
| 2 | Completeness of functional spec | 0.25 | 8.0 | 2.000 |
| 3 | Data model & state consistency | 0.15 | 8.5 | 1.275 |
| 4 | API contract precision | 0.15 | 8.5 | 1.275 |
| 5 | NFR measurability | 0.10 | 9.5 | 0.950 |
| 6 | Use case diagram currency | 0.10 | 9.0 | 0.900 |
| **Total** | | **1.00** | | **8.525** |

**Rounded score: 8.5**

No blockers detected. No score cap applies.

---

## Verdict: `approved`

Score 8.5 ≥ 7.0 threshold. No blockers. Three minor findings (F1, F2, F3) and two nits (F4, F5) that do not prevent advancement to the architecture stage. F1 (missing `/cancel` command spec) is the highest-priority item to resolve before or during architecture design — the architect must either implement `/cancel` or remove the UC16 reference; leaving it as-is creates a user-visible dead reference. F5 (PendingMetricPicker → PendingPeriodicity arc) should be resolved in the DM6 diagram to prevent architect ambiguity.

`suggest_major_bump: false` — additive feature delta; SRS remains at v0.1 per workflow convention.

---

## Summary

**Top 3 findings:**

1. **F1 (minor)** — `/cancel` command referenced in UC16 edge case but not specified anywhere in the SRS Command Interface or FR list. User is instructed to use `/cancel` to exit a PendingMetricPicker session, but the command has no defined behavior, transition, or FR. Must be resolved before or during architecture.

2. **F5 (nit)** — DM6 state machine lacks the `PendingMetricPicker → PendingPeriodicity` arc for the A2 Create-button flow. Only `Idle → PendingPeriodicity` is shown. Architect may assume PendingMetricPicker must clear to Idle before transitioning to PendingPeriodicity, which is not the intent.

3. **F2 (minor)** — UC2/UC6/UC7/UC8/UC10 refs blocks omit `feat-smart-metric-picker v0.1` despite direct annotations from that feature. Minor hygiene gap; no traceability break since the SRS is the consolidation point.

**Next step:** Advance to `arch` stage. Architect should treat F1 as a design input — either spec `/cancel` as a new command in the architecture or document the decision to rely on timeout-only cancellation and remove the `/cancel` reference from UC16.
