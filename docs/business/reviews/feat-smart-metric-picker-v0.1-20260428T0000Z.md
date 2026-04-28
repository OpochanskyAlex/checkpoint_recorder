---
doc: REVIEW
reviews: feat-smart-metric-picker
project: checkpoint_recorder
reviewer: business-analyst-reviewer
reviewed_version: 0.1
score: 8.2
verdict: approved
updated: 2026-04-28
tags: [project-docs, review]
---

# BA Review: Smart Metric Picker Feature — v0.1

**Reviewed documents:**
- `business/features/feat-smart-metric-picker.md` v0.1
- `business/stories/us-8-metric-picker.md` v0.1
- `business/brd.md` v0.1 (delta: R12–R17, US8 index entry, Q1–Q4 open questions, Q5–Q6 resolved, 3 glossary additions)
- `checkpoint_recorder.md` v0.1 (delta: US8 added to story index)

**Review scope:** Feature delta only — R12–R17, US8, feat spec, and US8 impact analysis. Existing R1–R11 and US1–US7 not re-reviewed except for conflict and ID-stability checks.

**Review date:** 2026-04-28

---

## Universal Checks

| Check | Result | Notes |
|---|---|---|
| U1 Boundary | PASS | All writes in `business/`, `checkpoint_recorder.md`, `_meta/`. No violations. |
| U2 Version discipline | PASS | All new files at `version: 0.1`. BRD remains `0.1` (additive edit to in-progress draft; no mid-revision bump). |
| U3 refs hygiene | PASS | `feat-smart-metric-picker.md` refs `{doc: brd, version: 0.1}`. `us-8-metric-picker.md` refs both brd v0.1 and feat-smart-metric-picker v0.1. Versions match actuals. |
| U4 Obsidian links | PASS | First mentions use `[[file\|display text]]` style throughout. BRD US8 entry, feat spec new-stories section, `checkpoint_recorder.md` story index — all correct. US8 traces section uses `[[brd#R12\|R12]]` anchor-style links, which is consistent with existing US files. No broken targets detected. |
| U5 Activity tags | PASS | R12–R16 carry `@logging @management`; R17 carries `@logging`. Both tags exist in taxonomy. feat spec frontmatter and US8 frontmatter declare `activities: [logging, management]`. |
| U6 ID stability | PASS | R1–R11 untouched. R12 continues from R11. US1–US7 untouched. US8 is new. No renumbering. |

All universal checks pass. No blockers triggered.

---

## Findings

### F1 — major | Criterion 1 (Completeness) | `us-8-metric-picker.md` AC8.6b; `brd.md` R12–R17

**Description:** AC8.6b specifies behavior when fuzzy search yields zero matches for a management command (`/chart`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`, `/alert_set`): "the system responds with a 'no matching metrics found' message; no picker or Create button is shown." This is correct behavior, but it has no backing requirement in R12–R17. R17 explicitly covers only the logging/entry flow zero-match case. No requirement captures the management-command zero-match path. An AC without a backing R is an orphan acceptance criterion — untraceable and potentially dropped at SA stage.

**Suggested fix:** Add R18 [must] @management: "When the picker in a management command (`/chart`, `/alert_set`, `/metric_archive`, `/metric_reactivate`, `/metric_delete`) finds zero fuzzy matches for a supplied metric name argument, the system responds with a 'no matching metrics found' message; no Create button is shown and the command is not executed." Then link AC8.6b to R18.

---

### F2 — minor | Criterion 2 (Clarity) | `us-8-metric-picker.md` Notes section

**Description:** The Notes section contains the following statement: "R2 (auto-create) is not bypassed: if fuzzy matching yields zero results in the logging/entry flow, the system may proceed to auto-create as defined by R2, subject to Q-FEAT-6 resolution." Q-FEAT-6 is resolved and R17 has been added to the BRD explicitly stating "R2 auto-create does not fire silently." The note directly contradicts the resolved requirement and the stated behavior in AC8.6 and R17. A reader arriving at this note after reading R17 and AC8.6 will encounter a contradiction.

**Suggested fix:** Replace the stale note with: "R2 (auto-create) does not fire silently in the logging/entry flow. Per R17 (resolved Q-FEAT-6), when fuzzy matching yields zero results the system presents an explicit 'Create [typed_name]' inline button; the user must press it to initiate periodicity selection."

---

### F3 — minor | Criterion 2 (Clarity) | `brd.md` R15; `feat-smart-metric-picker.md` R15

**Description:** R15 includes the word "scrollable" in the requirement text: "...replaces the message with a scrollable inline keyboard listing all matching metrics." Q-FEAT-4 (open for SA) correctly flags that Telegram inline keyboards are only scrollable via native Telegram client UI and that no custom scroll is possible. However, the word "scrollable" remains in the normative R15 text. If SA reads this as a specific implementation requirement distinct from native scrolling, it introduces ambiguity. At minimum, the qualifier is not defined or testable at this stage.

**Suggested fix:** Remove "scrollable" from R15's normative text and relocate the intent to a parenthetical or note: "...replaces the message with an inline keyboard listing all matching metrics (displayed as a full-height list; native Telegram client scrolling applies — see Q-FEAT-4 for SA clarification on pagination)."

---

### F4 — nit | Criterion 1 (Completeness/Structure) | `brd.md` R14; `feat-smart-metric-picker.md` R14

**Description:** R14 restates the recency-ordering rule verbatim: "Inline keyboard buttons presenting metric choices are ordered by the timestamp of the most recent entry for each metric, descending; metrics with no entries appear last, ordered alphabetically." This ordering rule is already embedded in R12 ("ordered by most-recently-recorded entry (descending); metrics with no entries appear last, ordered alphabetically") and R13 ("presents matched metrics as inline keyboard buttons ordered by most-recently-recorded entry"). R14 adds no new information. While it causes no harm, it creates a maintenance surface: a future change to the ordering rule must be applied in three places.

**Suggested fix:** Remove R14 and instead link R12 and R13 to a shared ordering rule expressed as a constraint, or keep R14 as a standalone ordering rule and remove the duplicated detail from R12 and R13 (the latter approach is a larger rewrite; the former is simpler).

---

### F5 — praise | Criterion 3 (Testability) | `us-8-metric-picker.md` AC8.3, AC8.6b, AC8.10, AC8.11

**Description:** Edge cases are handled with notable precision. AC8.3 specifies the empty-catalog case (no metrics yet) with a specific message and no inline keyboard — a common UX edge case frequently missed at BA stage. AC8.10 and AC8.11 express the recency ordering rule as binary, independently verifiable test cases. AC8.6b separates the zero-match management-command behavior from the zero-match logging-flow behavior — a distinction that would otherwise surface as a defect at test stage.

---

## Per-Criterion Scores

### Criterion 1 — Completeness of requirements (weight 0.30)

**Score: 7.5 / 10.0**

R12–R17 cover the primary feature flows well: bare command, fuzzy match, overflow display, recency ordering, last-3-values context, and zero-match creation in logging. The feature spec includes a thorough impact-on-existing-requirements table. The US8 story index is correctly updated in both BRD and project overview.

Deduction: AC8.6b (zero-match management command → "no matching metrics found") has no backing requirement. This is a well-specified behavior without a normative home, making it invisible to downstream SA work unless noticed. R14's redundancy with R12/R13 is a nit. No goals are orphaned; all R trace to G.

---

### Criterion 2 — Clarity / absence of ambiguity (weight 0.25)

**Score: 8.0 / 10.0**

No banned words ("fast", "scalable", "user-friendly", etc.) without adjacent metrics were found. Requirements are specific: metric-name-required commands are enumerated explicitly in R12. The distinction between the picker (command-level trigger) and R3 ParseAttempt (NLP-level trigger) is clearly articulated in both the feat spec motivation section and the US8 Notes.

Deductions: The stale Q-FEAT-6 note in US8 contradicts R17 and the resolved requirement (F2). "scrollable" in R15's normative text is an undefined qualifier that will require SA interpretation (F3). Both are minor but addressable.

---

### Criterion 3 — Testability of acceptance criteria (weight 0.20)

**Score: 8.5 / 10.0**

AC quality is high overall. Response-time bounds are specified (5 seconds in AC8.1, AC8.4). Overflow threshold is precise (more than 4 → top 4 + overflow button). Ordering is specified as binary test cases (AC8.10, AC8.11). The "no entries yet" string is called out specifically. Empty-catalog and zero-match edge cases are covered.

Minor deduction: The stale note in US8 Notes (F2) creates test confusion — a tester reading it would not know whether R2 auto-create might still apply in some code path. AC8.7 says "bot acknowledges the selection" — "acknowledges" is slightly vague but the operative behavior (command proceeds) is observable. Timeout behavior in AC8.9 is deferred to SA (acceptable at BA stage). No AC is wholly untestable.

---

### Criterion 4 — Stakeholder coverage (weight 0.15)

**Score: 9.0 / 10.0**

All four project stakeholders (SH1–SH4) appear in the feat spec's "Affected Stakeholders" section with specific, differentiated concerns. SH5 (Telegram Platform) has no concern related to this feature and its absence is appropriate. Each stakeholder's concrete benefit or non-impact is stated explicitly. SH4 (Bot Operator) correctly notes no new external dependency is introduced.

---

### Criterion 5 — Traceability + activity taxonomy (weight 0.10)

**Score: 9.0 / 10.0**

All R12–R17 trace back to G1 (R16 additionally to G2). US8 traces to R12–R17, G1, G2. Activity tags are consistent across BRD, feat spec frontmatter, US8 frontmatter, and the `checkpoint_recorder.md` story index. The story index correctly lists US8 under both `@logging` and `@management`. All tags in use (`@logging`, `@management`) are defined in the taxonomy.

Minor gap: R17 only carries `@logging` while the overall feature also touches `@management` through R12–R16. This is technically correct (R17 is exclusively a logging-flow behavior), but it means the zero-match "Create" button path is invisible to `@management` scoped traceability queries. Not incorrect — just narrow. If F1's R18 is added, it would carry `@management` and close this.

---

## Weighted Total

| Criterion | Weight | Score | Contribution |
|---|---|---|---|
| 1. Completeness | 0.30 | 7.5 | 2.25 |
| 2. Clarity | 0.25 | 8.0 | 2.00 |
| 3. Testability | 0.20 | 8.5 | 1.70 |
| 4. Stakeholder coverage | 0.15 | 9.0 | 1.35 |
| 5. Traceability + taxonomy | 0.10 | 9.0 | 0.90 |
| **Total** | **1.00** | | **8.20** |

No blockers. Score 8.20 >= threshold 7.0.

---

## Verdict

**approved**

The feature addition is well-structured and ready to advance to SA. One major finding (F1: AC8.6b has no backing requirement) should be addressed either by the SA noting it as an implied requirement or by the BA adding R18 before SA produces the SRS. The two minor findings (F2: stale note, F3: "scrollable" qualifier) are low-risk and may be corrected as part of the SA handoff without a BRD revision cycle.

**suggest_major_bump: false**

This is an additive feature (R12–R17 added, no existing R renumbered or changed in scope). The BRD version does not require a major bump.

---

## Pre-SA Handoff Notes

The following SA open questions are in scope for the SRS stage (carried from feat spec):

- Q-FEAT-1: Shared vs. separate ConversationState for picker and ParseAttempt (R3)
- Q-FEAT-2: Whether "asking for new value" in logging flow is a new FSM state or re-uses existing entry submission state
- Q-FEAT-3: Exact rapidfuzz similarity threshold and scoring function for R13 — must be numeric in SRS to make R13 testable
- Q-FEAT-4: Whether "Show all fits" overflow list requires pagination buttons or relies on native Telegram client scrolling

These are correctly scoped as SA questions. The BA has done the appropriate work of identifying and documenting them; they are not BA deficiencies.
