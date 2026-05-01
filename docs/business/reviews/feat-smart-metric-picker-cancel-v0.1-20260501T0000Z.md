---
doc: REVIEW
reviews: feat-smart-metric-picker (Cancel-button delta)
project: checkpoint_recorder
reviewer: business-analyst-reviewer
reviewed_version: 0.1 (delta: R19 + AC8.12)
score: 8.70
verdict: approved
updated: 2026-05-01
tags: [project-docs, review]
---

# BA Review: Smart Metric Picker — Cancel Button Delta (R19 + AC8.12)

**Reviewed documents:**
- `business/brd.md` v0.1 (delta: R19 added; US8 index updated to include R19)
- `business/features/feat-smart-metric-picker.md` v0.1 (delta: R19 added to New Business Requirements)
- `business/stories/us-8-metric-picker.md` v0.1 (delta: AC8.12 added; Traces to line updated with R19)

**Review scope:** Delta only — R19 and AC8.12. All prior findings from `feat-smart-metric-picker-v0.1-20260428T0000Z.md` are acknowledged; this review does not re-adjudicate them. The three prior amendments from that review (R18 added, stale note fixed, "scrollable" clarified) are confirmed present.

**Pre-answered stakeholder question:** Q-A1 resolved before authoring — Cancel button behavior is identical to `/cancel`; no new Q raised.

**Review date:** 2026-05-01

---

## Universal Checks

| Check | Result | Notes |
|---|---|---|
| U1 Boundary | PASS | Writes confined to `business/brd.md`, `business/features/feat-smart-metric-picker.md`, `business/stories/us-8-metric-picker.md`, and `_meta/changelog.md`. All within the BA's allowed boundary. |
| U2 Version discipline | PASS (with nit) | All files remain at `version: 0.1`. No illegal mid-revision bump. However, the `updated` field in all three modified files was not refreshed: `brd.md` still shows `2026-04-26`; `feat-smart-metric-picker.md` and `us-8-metric-picker.md` still show `2026-04-28`. Stale date is a nit (see F2). |
| U3 refs hygiene | PASS | No new refs introduced by the delta. Existing refs (`brd v0.1`, `feat-smart-metric-picker v0.1`) remain correct and non-stale. |
| U4 Obsidian links | PASS | `[[brd#R19\|R19]]` added to US8 Traces section, consistent with the style used for R12–R18. AC8.12 references `/cancel` as plain text (appropriate — commands are not linked entities). No broken targets. |
| U5 Activity tags | PASS | R19 carries `@logging @management`. Both tags exist in the project taxonomy (`state.yaml` activities list). Consistent with R12–R16 which also carry both tags. |
| U6 ID stability | PASS | R19 continues sequentially from R18. AC8.12 continues sequentially from AC8.11. No existing IDs renumbered. No deletions without marking. |

All universal checks pass. No blockers triggered.

---

## Findings

### F1 — minor | Criteria 1 + 3 (Completeness, Testability) | `brd.md` R19; `feat-smart-metric-picker.md` R19; `us-8-metric-picker.md` AC8.12

**Description:** R19 reads: "Every picker keyboard display (bare command, fuzzy match, and overflow expansion) includes a Cancel button as the last button." AC8.12 mirrors this enumeration: "Given the user presses the Cancel button on any picker keyboard (bare command, fuzzy match, or overflow)..."

Both R19 and AC8.12 enumerate exactly three display contexts. However, R17 introduces a fourth picker keyboard display: when the logging/entry flow finds **zero fuzzy matches**, the system presents an explicit "Create [typed_name]" inline button. This Create-button screen is rendered as an inline keyboard (it is a picker keyboard display in the same UX surface), but it is omitted from the enumeration in both R19 and AC8.12.

The stated intent — "every picker keyboard display" — implies the Cancel button should also appear on the zero-match Create screen in the logging flow. If it does not, a user who types a metric name that yields no matches has no way to cancel without typing `/cancel` manually, which is inconsistent with the feature's stated outcome. If it intentionally does not apply to the Create screen, that exclusion should be explicit.

This is a testability gap: a tester reading AC8.12 will not test Cancel on the R17 zero-match display. It is also a completeness gap: R19's normative text does not capture a known picker keyboard variant.

**Suggested fix:** Extend the parenthetical in R19 to "(bare command, fuzzy match, overflow expansion, and zero-match Create-button display)". Update AC8.12 to match, adding: "...or zero-match Create-button display (R17 path)". Alternatively, if the design intent is to exclude the Create screen from Cancel coverage, add an explicit exclusion sentence to R19 and a note to AC8.12.

---

### F2 — nit | Criterion 2 (Clarity / version discipline) | All three file frontmatters

**Description:** The `updated` field was not refreshed in any of the three modified files. `brd.md` shows `2026-04-26`; `feat-smart-metric-picker.md` and `us-8-metric-picker.md` show `2026-04-28`. The actual edit date is 2026-05-01 per the changelog. Stale `updated` dates make it harder to identify which files changed in a given session and may confuse tooling or reviewers who rely on the field for freshness detection.

**Suggested fix:** Set `updated: 2026-05-01` in the frontmatter of all three files that received edits in this delta.

---

### F3 — praise | Criterion 3 (Testability) | `us-8-metric-picker.md` AC8.12

**Description:** AC8.12 specifies five independently verifiable outcomes in a single AC: (1) picker is dismissed, (2) conversation state returns to Idle, (3) reply is identical to `/cancel` response, (4) no metric is selected, (5) no command is executed. This level of multi-outcome specificity is excellent and goes beyond the minimum of one observable binary outcome. The three-context enumeration (bare / fuzzy / overflow) also ensures the AC is not inadvertently tested in only the "happy path" bare-command scenario.

---

## Per-Criterion Scores

### Criterion 1 — Completeness of requirements (weight 0.30)

**Score: 8.5 / 10.0**

R19 is present in all three files. The US8 traces-to line is updated to include R19. The BRD US8 index entry correctly lists R19. The feature spec "New Business Requirements" section includes R19 with correct tag and goal trace.

Deduction for F1: The Create-button display (R17 zero-match logging path) is a known, explicitly-specified picker keyboard surface that is not enumerated in R19's scope. The omission may be intentional (design choice to exclude it) or an oversight; neither interpretation is made explicit. A confirmed picker keyboard variant that is neither included nor excluded from a requirement claiming "every picker keyboard display" leaves a completeness gap.

---

### Criterion 2 — Clarity / absence of ambiguity (weight 0.25)

**Score: 9.0 / 10.0**

No banned words without adjacent metrics. R19's normative text is precise: "dismisses the picker", "returns the user to Idle state", "produces the same reply text as the /cancel command" — all unambiguous outcomes. The phrase "same reply text as the /cancel command" is a functional cross-reference to FR31 (defined in SRS), appropriate at BA level given Q-A1 is resolved. The parenthetical enumeration in R19 resolves potential ambiguity in "every picker keyboard display" for the three cases listed.

Deduction for F2 (nit): Stale `updated` dates reduce document hygiene. Not an ambiguity in requirements text, but a version-discipline nit.

---

### Criterion 3 — Testability of acceptance criteria (weight 0.20)

**Score: 8.0 / 10.0**

AC8.12 is binary and multi-outcome (see F3 praise). The placement of AC8.12 under "Recency ordering" is mildly odd structurally — Cancel behavior is not about recency — but does not impair testability.

Deduction for F1: The Create-button display is not covered in AC8.12. A test suite derived directly from AC8.12 will have a coverage gap on the R17 picker surface. The word "any" in "any picker keyboard" in AC8.12's Given clause could be read to cover all screens, but the explicit enumeration that follows limits its scope to the three named contexts, leaving the fourth uncovered.

---

### Criterion 4 — Stakeholder coverage (weight 0.15)

**Score: 9.0 / 10.0**

No new stakeholder concerns are introduced by the Cancel button. The feat spec "Affected Stakeholders" section was not updated for this delta, which is acceptable — the Cancel button is a standard escape mechanism that benefits all end users (SH1–SH3) uniformly and has no operational impact on SH4. The existing stakeholder analysis remains valid and complete.

No deduction; this is appropriate for a single-button delta.

---

### Criterion 5 — Traceability + activity taxonomy (weight 0.10)

**Score: 9.5 / 10.0**

R19 traces back to G1 (reduce friction — Cancel removes the only escape being `/cancel` manual typing, consistent with G1's low-friction promise). US8 traces-to line updated. BRD US8 index entry updated. Activity tags `@logging @management` on R19 match R12–R16 (the picker covers both activities). The Q-A1 resolution is recorded in the changelog, which is the appropriate location for a pre-answered question that did not require a formal open-question entry in the doc.

Minor gap: The feat spec "Open Questions" section was not updated to record Q-A1 as a resolved question (in the style of ~~Q-FEAT-5~~ and ~~Q-FEAT-6~~). This is a nit; the changelog is authoritative.

---

## Weighted Total

| Criterion | Weight | Score | Contribution |
|---|---|---|---|
| 1. Completeness | 0.30 | 8.5 | 2.55 |
| 2. Clarity | 0.25 | 9.0 | 2.25 |
| 3. Testability | 0.20 | 8.0 | 1.60 |
| 4. Stakeholder coverage | 0.15 | 9.0 | 1.35 |
| 5. Traceability + taxonomy | 0.10 | 9.5 | 0.95 |
| **Total** | **1.00** | | **8.70** |

No blockers. Score 8.70 >= threshold 7.0.

---

## Verdict

**approved**

The R19 delta is well-executed: the requirement is present in all three required locations, the AC is binary and multi-outcome, traceability is fully maintained, and the resolution of Q-A1 is correctly recorded. One minor finding (F1) identifies an under-specification: the Create-button display (R17 zero-match path) is a picker keyboard surface that is neither included nor explicitly excluded from R19's "every picker keyboard display" scope and is absent from AC8.12's enumeration. This should be resolved before the SRS author writes FR coverage for the Cancel button.

**suggest_major_bump: false**

This is an additive single-requirement delta. No existing R renumbered. No existing AC renumbered or changed in scope. BRD version does not require a major bump.

---

## Carry-Forward Notes to SA

- F1 requires a decision before FR coverage is written: does the Cancel button appear on the R17 zero-match Create-button display? The BA should clarify in R19 and AC8.12 before SA proceeds with the picker Cancel FSM arc.
- The `/cancel` reply text that R19 and AC8.12 reference is already defined in FR31 of the SRS. The SA should confirm the FR coverage of the Cancel button for the picker keyboard explicitly references FR31 and the PendingMetricPicker → Idle arc in DM6 state machine.
