---
doc: REVIEW
id: REVIEW-ADR013-CANCEL-v0.1
reviewed_doc: [adr-013-inline-keyboard-callback-routing, overview]
reviewed_doc_version: 0.1
feature: smart-metric-picker / Cancel button delta (FR32)
project: checkpoint_recorder
review_type: delta
reviewer: architect-reviewer
reviewed_at: 2026-05-01T00:10Z
score: 9.0
gate_threshold: 7.0
verdict: PASS
stage_result: arch-done (delta approved)
refs:
  - {doc: brd, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: feat-smart-metric-picker, version: 0.1}
  - {doc: uc-16, version: 0.1}
tags: [project-docs, review]
---

# Architecture Delta Review: ADR-013 Cancel Button (FR32)

**Reviewed docs:** `adr-013-inline-keyboard-callback-routing.md` v0.1, `overview.md` v0.1  
**Feature delta:** Cancel button on every picker keyboard display (FR32 / R19)  
**Review type:** Targeted delta — only the two changed artefacts are scored  
**Date:** 2026-05-01  
**Reviewer:** architect-reviewer (claude-sonnet-4-6)

---

## 1. Universal Checks

**U1 — Boundary compliance**
Both documents reference only upstream artefacts (SRS v0.1, BRD v0.1 via the NFR and ADR index). No downstream code, implementation file, or runtime artefact is referenced as a normative source. PASS.

**U2 — Version / date consistency**
- ADR-013 frontmatter: `version: 0.1`, `updated: 2026-05-01`. Consistent with state.yaml `versions.arch: 0.1` and the current date.
- overview.md frontmatter: `version: 0.1`, `updated: 2026-05-01`. Consistent.
- Both docs reference `{doc: srs, version: 0.1}` in their `refs` field. SRS is indeed at v0.1. PASS.
- ADR-013 `refs` does not include a `brd` entry — only `{doc: srs, version: 0.1}`. The ADR deals with implementation routing, not business requirements directly, so omission of BRD ref is acceptable at ADR level. The overview.md correctly carries `{doc: brd, version: 0.1}`. Minor gap only (see F5).

**U3 — Reference integrity**
All Obsidian-style wiki-links in the changed sections resolve to known documents:
- `[[adr-001-monolith|ADR-001]]`, `[[adr-005-user-isolation|ADR-005]]`, `[[adr-013-inline-keyboard-callback-routing|ADR-013]]` — all present in ADR index.
- `[[srs|NFR18]]`, `[[srs|NFR6]]`, `[[srs|NFR4]]` — NFRs exist in SRS at those IDs.
- `[[brd#R19|R19]]`, `[[srs#FR32|FR32]]`, `[[us-8-metric-picker|US8]]` — traceable to feat doc and SRS.
PASS.

**U4 — Obsidian link syntax**
All wiki-links use `[[target|display]]` format consistently. No malformed links detected. PASS.

**U5 — Activity tags**
ADR-013 carries `activities: [logging, management]`. This matches FR32's `@logging @management` tags in SRS. overview.md carries `activities: []` (architecture overviews are not required to carry activity tags per role instructions). PASS.

**U6 — ID stability**
ADR-013 number has not changed; it was the correct next ADR in the existing sequence (ADR-012 is the tech stack ADR). No renumbering occurred. PASS.

---

## 2. Architecture-Specific Findings

### F1 — NFR alignment: NFR18 (picker ≤5s p95) — PRAISE

The Cancel path adds negligible latency: it bypasses the state gate without a DB read, calls `answer_callback_query` unconditionally, writes a single ConversationState row, and dispatches a short text reply. The existing NFR18 capacity note (≤20 users × ≤20 metrics; re-evaluate at ceiling) is unaffected. ADR-013 Consequences Negative explicitly confirms the ownership-validation DB round-trip applies only to `pick:` actions, not `cancel`. The overview NFR Mapping table retains the correct NFR18 entry. Strongly aligned. **Praise.**

### F2 — NFR alignment: NFR6 (per-user isolation) — PRAISE

The cancel bypass is the one path that explicitly does NOT need ownership validation — there is no metric_id payload. The ADR correctly documents that ownership-validation (Decision step 4) applies to `pick:<metric_id>` only. The overview Security section confirms: "handler validates metric_id belongs to the requesting user before proceeding (ADR-013); stale or replayed non-cancel callbacks are rejected… `callback_data = "cancel"` always routes to the FR31/FR32 Idle transition." Per-user isolation is structurally preserved because ConversationState is keyed by `internal_user_id` (DM6 PK = internal_user_id) and the state write uses the same key. **Praise.**

### F3 — Security: cancel bypass abuse surface — MINOR

**Finding:** The `cancel` bypass exits the state gate unconditionally from ANY non-Idle state, not only PendingMetricPicker. This is correct per FR31/FR32 semantics and is explicitly documented. However, no threat is listed for a crafted `callback_data = "cancel"` sent while the user is in a security-sensitive state such as `PendingMetricDeletionConfirmation` — pressing a stale Cancel button on a months-old picker keyboard would silently abort an in-progress deletion confirmation. The outcome (→ Idle, no action taken) is safe and benign, but the implicit threat model is absent from the threat list.

**Severity:** Minor. The outcome is safe (state → Idle, no data mutated, no deletion executed). However the threat list in the overview Security section does not acknowledge this as an explicitly considered and accepted risk.

**Recommendation:** Add a one-line note in the Callback data integrity bullet acknowledging that cancel-from-any-non-Idle-state is intentional and that the worst-case outcome is a harmless state reset (no data mutation, no command execution).

### F4 — ADR quality: context, decision, alternatives, consequences — PASS with praise

- **Context (5 points):** All five context points are present and coherent. Point 2 correctly introduces the three callback action types including `cancel`. Point 3 correctly states the state gate and its exception. PASS.
- **Decision:** Structured, numbered, unambiguous. Decision step 3 cleanly articulates the state-gate condition as `state ≠ PendingMetricPicker AND callback_data ≠ "cancel"`. The exception path is explicit. PASS.
- **Alternatives (≥2 required):** Three alternatives considered (A1, A2, A3). Each has Pros/Cons and a "Why not" rationale. The cancel bypass is not a separate architectural choice requiring its own alternative set — it is a consequence of choosing centralized routing (A1 rejected in favour of main decision). PASS.
- **Consequences Positive:** Four points, all accurate and specific. PASS.
- **Consequences Negative:** Four points. The stale-keyboard note has been correctly updated: the old framing ("stale keyboards remain active") is now framed as a feature ("reliable escape path even from stale UIs"). The DB round-trip note correctly scopes ownership-validation to `pick:` only. PASS. **Praise for honest trade-off documentation.**

### F5 — ADR refs field: BRD version absent — NIT

ADR-013 `refs` contains only `{doc: srs, version: 0.1}`. The feature traces to BRD R19 via SRS FR32. While ADRs are not required to carry full upstream ref chains, including `{doc: brd, version: 0.1}` would complete the traceability loop at the ADR level, consistent with overview.md practice.

**Severity:** Nit. No traceability gap at document level — overview.md and uc-16 both carry the BRD ref.

### F6 — Traceability: FR32 in overview Component table — PASS

The Message Dispatcher row in the Components table lists `FR3, FR22, FR23, FR24, FR25, FR26, FR27, FR28, FR29, FR30, FR31, FR32`. FR32 is present. The description column notes "callback_data encodes action type + metric_id per ADR-013." Traceability from R19 (feat doc) → FR32 (SRS) → ADR-013 (arch) → overview Component table is complete. PASS.

### F7 — Traceability: Interaction Flow J and cancel path — MINOR

**Finding:** Interaction Flow J in the overview (the "Metric Picker" flow row) describes the picker's happy path (keyboard display → callback → Entry Processor or Metric Manager). It does not mention the Cancel alternative path (A6 in UC16). The Failure Scenarios table covers picker-session-abandoned (timeout) but not the cancel-button interaction specifically. While the cancellation outcome is simple (state → Idle), an orchestrator reading Flow J in isolation cannot determine how the cancel path fits the dispatcher routing.

**Severity:** Minor. The gap is in a summary table, not in the normative ADR section. The ADR-013 Decision step 3 is the authoritative source for cancel routing; the Interaction Flows are summaries. However, a one-line parenthetical noting "(Cancel button → FR31/FR32 Idle path; no DB ownership check)" in Flow J would close the documentation gap.

**Recommendation:** Append a brief note to Flow J's "on selection" column or add a "Cancel" branch to the Pattern column.

### F8 — Scalability fit — PASS

The cancel path introduces zero additional DB reads (no ownership-validation required), one DB write (ConversationState → Idle), and one Telegram outbound API call. At ≤20 users this is negligibly cheap. The Consequences Negative note correctly defers the ownership-validation DB round-trip re-evaluation to the 20-user ceiling, and that note applies to `pick:` callbacks only. No new scalability concern is introduced by the cancel delta. PASS.

### F9 — Observability: cancel events — MINOR

**Finding:** The Observability section lists `conversation_state_event` in the key event types, which would fire on the ConversationState → Idle transition triggered by cancel. However, neither the ADR nor the overview explicitly states that cancel button presses are captured via `conversation_state_event` or any other event. The `picker_invocation_event` is confirmed as registered, but no analogous `picker_cancel_event` or annotation on `conversation_state_event` is provided for FR32 specifically.

For a personal portfolio bot at ≤20 users this is an acceptable gap — the `conversation_state_event` existing coverage is sufficient to detect cancel-triggered Idle transitions. However the oncall visibility description does not call out "unexpected cancel from non-picker state" as a detectable scenario.

**Severity:** Minor. The observability section already covers the general state-transition event. The absence of an FR32-specific event annotation is a documentation gap, not a design gap. At portfolio scale this does not materially affect incident response.

**Recommendation:** Add a parenthetical to the `conversation_state_event` entry: "(includes FR31/FR32 cancel transitions)" or a note in the ADR Follow-ups.

### F10 — Diagram quality — PASS (delta scope)

No new diagram was added in this delta. The existing C4 Level 2 Container diagram correctly labels the inbound arrow as "(Message + CallbackQuery)" — this label was already present and is not changed by the FR32 delta. The C4 Level 3 Component diagram caption explicitly notes "No new component box is added for the smart-metric-picker feature." The cancel path uses existing components (Message Dispatcher → USG → Data Repository) with no new boxes required. Diagram quality is appropriate for the scope of change. PASS.

---

## 3. Weighted Score Breakdown

| # | Criterion | Weight | Raw (0–10) | Weighted |
|---|---|---|---|---|
| 1 | Alignment with NFRs (NFR18, NFR6, NFR4) | 0.20 | 10.0 | 2.00 |
| 2 | Decision rationale (ADR quality: context, decision, alternatives, consequences) | 0.20 | 9.5 | 1.90 |
| 3 | Scalability & evolvability | 0.15 | 10.0 | 1.50 |
| 4 | Security posture | 0.15 | 8.0 | 1.20 |
| 5 | Observability readiness | 0.15 | 8.0 | 1.20 |
| 6 | Cost & operational fit | 0.10 | 10.0 | 1.00 |
| 7 | Diagram quality | 0.05 | 9.0 | 0.45 |
| | **Total** | **1.00** | | **9.25** |

**Adjusted score:** 9.0 / 10.0

> Adjustment rationale: F3 (security threat model gap) and F7 (interaction flow cancel path undocumented in summary table) are both minor findings that marginally reduce scores on criteria 4 and 2 respectively; F9 (observability annotation gap) is minor and reduces criterion 5 slightly. No blockers present. Score rounded to 9.0.

---

## 4. Findings Summary

| ID | Severity | Criterion | Short description |
|---|---|---|---|
| F1 | praise | NFR alignment | Cancel path adds zero latency overhead; NFR18 fully preserved |
| F2 | praise | Security / NFR6 | Ownership-validation correctly scoped to pick: only; cancel bypass is structurally safe |
| F3 | minor | Security posture | Cancel-from-any-state threat not explicitly enumerated in threat model; outcome is safe but absence is undocumented |
| F4 | praise | ADR quality | Honest negative-consequences documentation; state-gate condition precisely specified |
| F5 | nit | ADR refs | BRD ref absent from ADR-013 refs field; traceability exists at higher levels |
| F6 | pass | Traceability | FR32 present in overview Component table; R19 → FR32 → ADR-013 → overview chain complete |
| F7 | minor | Diagram / flow quality | Interaction Flow J summary does not reference the cancel (A6) path |
| F8 | pass | Scalability | Cancel adds no DB read; zero new scalability concern at ≤20 users |
| F9 | minor | Observability | No explicit FR32 annotation on conversation_state_event; minor documentation gap |
| F10 | pass | Diagrams | No new diagrams required; existing C4 labels correct |

---

## 5. Final Score and Verdict

**Final score: 9.0 / 10.0**

**Gate threshold: 7.0**

**Verdict: PASS**

**Stage result:** Delta approved. No blockers. Three minor findings (F3, F7, F9) are documentation gaps that do not compromise correctness or safety — all are recommended to address before implementation, but do not block advancement.

---

## 6. Summary

The Cancel button delta (FR32 / R19) is a well-executed, minimal architectural change. ADR-013 was correctly extended: the cancel action type is unambiguously defined, the state-gate bypass is precisely specified, the ownership-validation exclusion is correctly scoped, and the stale-keyboard negative consequence is honestly reframed as a deliberate escape-path feature. The overview's Security and Component sections are consistently updated. NFR alignment is strong — the cancel path adds zero DB reads, trivial latency, and no cross-user isolation risk. Three minor findings remain: the threat model does not explicitly acknowledge cancel-from-non-picker-state as a considered and accepted risk (F3), the Interaction Flow J summary table omits the cancel branch (F7), and the observability section lacks an explicit annotation linking FR31/FR32 to `conversation_state_event` (F9). None of these minor gaps affect correctness or safety at the current portfolio scale, and all are straightforward to close before or during implementation.

---

## Changelog

- 2026-05-01T00:10Z — Initial delta review by architect-reviewer. Score: 9.0/10.0. Verdict: PASS.
