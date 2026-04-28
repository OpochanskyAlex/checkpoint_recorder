---
doc: ARCH-REVIEW
project: checkpoint_recorder
feature: smart-metric-picker
arch_version: 0.1
review_version: 0.1
status: needs-revision
reviewer: architect-reviewer
reviewed_by: architect-reviewer
score: 7.4
verdict: needs-revision
previous_review: null
suggest_major_bump: false
updated: 2026-04-28
tags: [project-docs, review, architecture]
refs:
  - {doc: arch-overview, version: 0.1}
  - {doc: adr-013, version: 0.1}
  - {doc: srs, version: 0.1}
  - {doc: uc-16, version: 0.1}
---

# Architecture Review: smart-metric-picker — v0.1 (2026-04-28T01:00Z)

## Scope

Feature-addition review covering the architectural changes introduced for the `smart-metric-picker` feature:
- `/docs/architecture/overview.md` (updated)
- `/docs/architecture/adrs/adr-013-inline-keyboard-callback-routing.md` (new)

Upstream documents read: SRS v0.1, BRD v0.1, UC16 v0.1.

---

## Universal Checks

### U1 — Boundary compliance
The architect's changes are confined to `docs/architecture/overview.md` and `docs/architecture/adrs/adr-013-inline-keyboard-callback-routing.md`. No edits to BRD, SRS, or UC files were made by the architect. The `refs` block in `overview.md` includes `{doc: feat-smart-metric-picker, version: 0.1}` which appears to reference a feature specification file not in the canonical upstream document set — however this is a `refs` hygiene issue (U3), not a boundary write violation. **PASS.**

### U2 — Version discipline
`overview.md` frontmatter: `version: 0.1`. `adr-013`: `version: 0.1`. Both are first-version documents on a feature-addition workflow. Version 0.1 is appropriate for the first authored revision prior to gate approval. **PASS.**

### U3 — refs list hygiene
`overview.md` refs list: `{doc: brd, version: 0.1}`, `{doc: srs, version: 0.1}`, `{doc: feat-smart-metric-picker, version: 0.1}`. The first two match the canonical versions in `state.yaml`. The third ref (`feat-smart-metric-picker`) references a feature spec file that is not part of the established upstream doc set and cannot be verified as a tracked document with an official version. This ref should either be removed or replaced with a reference to the UC16 use-case document that captures the same intent. **Minor finding — see F1.**

`adr-013` refs: `{doc: srs, version: 0.1}`. Correct and sufficient. **PASS.**

### U4 — Obsidian link correctness
All ADR wiki-links in the overview use the `[[filename|ID Title]]` pattern on first mention. ADR-013 is linked as `[[adr-013-inline-keyboard-callback-routing|ADR-013]]`. Within ADR-013, cross-references to ADR-001 and ADR-002 are consistent with the filenames of those files. SRS and BRD links follow the project convention. No broken link targets detected for the files read. **PASS.**

### U5 — Activity tags
ADR documents at the architecture layer are not required to carry `@<act>` activity tags per the rubric note ("usually not required on arch items"). However, `adr-013` frontmatter carries `activities: [logging, management]`, which is internally consistent with the FRs it covers. The overview does not carry per-section activity tags, which is the established pattern. **PASS.**

### U6 — ID stability
ADR-013 is a new ID, not a renumber of an existing one. The ADR index in `overview.md` shows ADR-001 through ADR-013 in sequence with no gaps or renumbering. All previously accepted ADRs remain listed with their original IDs. **PASS.**

---

## Findings

### F1 [minor] — U3 / Criterion 2 (ADR quality) — Unverifiable `feat-smart-metric-picker` ref in overview.md

**Location:** `/docs/architecture/overview.md`, frontmatter `refs` block, line 13.

**Description:** The `refs` block lists `{doc: feat-smart-metric-picker, version: 0.1}`. This document is not part of the canonical upstream pipeline (BRD → SRS → UC files → Architecture). It cannot be verified as a tracked, versioned document, and `state.yaml` does not list it in the `versions` map. Including an unverifiable ref undermines the refs hygiene guarantee. The architectural feature context is fully captured in SRS FR22–FR31, DM6, and UC16, which are already in the canonical chain.

**Fix required:** Remove `{doc: feat-smart-metric-picker, version: 0.1}` from the refs block in `overview.md` and replace with `{doc: uc-16, version: 0.1}` to anchor the feature specification reference to a tracked document.

---

### F2 [major] — Criterion 1 (NFR alignment) — NFR18 "met by design" claim lacks capacity analysis for DB catalog query on critical path

**Location:** `/docs/architecture/overview.md`, NFR Mapping table, NFR18 row.

**Description:** The NFR18 mechanism states: "In-process rapidfuzz fuzzy lookup (no external round-trip); metric catalog query scoped by internal_user_id; inline keyboard assembled and dispatched synchronously within the webhook handler." The claim of "met by design" is asserted on the same basis as NFR1/NFR2, but the picker path has a materially different critical path: a full DB catalog query (all Active + Archived metrics per user, ordered by `MAX(entry_timestamp)`) plus rapidfuzz scoring over all metric names, plus inline keyboard serialization — all within the synchronous webhook handler within the 5s budget.

At the stated scale (~10 users, ~10 metrics each, ceiling 20 users), this is unlikely to violate the budget. However, the architecture doc provides no capacity analysis or even a rough estimate of the query cost under the stated load ceiling. The SRS NFR18 requires ≤5s p95, yet the architecture does not state any measured or estimated latency for the catalog query path, nor does it state an acceptable upper bound on catalog size before the p95 claim would require revision.

This is weaker than the NFR1/NFR2 "met by design" claims, which are plausible because those paths involve only NLP (in-process, no DB) before the first response. The picker requires a DB round-trip before any response is sent.

**Fix required:** Add a capacity note to the NFR18 row: state the expected catalog query cost at the stated scale (e.g., "≤20 users × ≤20 metrics = ≤400 rows; single indexed query by internal_user_id; expected p95 ≪ 1s at stated scale; re-evaluate at 20-user ceiling before architecture review"). This turns an unsubstantiated claim into a bounded, reviewable assertion. No design change required.

---

### F3 [major] — Criterion 3 (Scalability) — Scheduled Process FR attribution: FR29 and FR30 are misattributed to the Scheduled Process row

**Location:** `/docs/architecture/overview.md`, Component table, Scheduled Process row, column "FRs handled": `FR18, FR29, FR30`.

**Description:** FR29 defines `PendingMetricPicker` state routing behavior (Dispatcher routes CallbackQuery in this state; Scheduled Process handles *timeout cleanup* of stale sessions). FR30 defines `PendingPickerValue` state routing and timeout. Neither FR29 nor FR30 primarily describes a scheduled job — they are ConversationState routing specifications. The *scheduled* aspect is only the timeout cleanup side-effect, which is already subsumed by FR18 (which explicitly lists "stale PendingPeriodicity cleanup" as one of its four jobs — and the SRS text confirms FR18 was updated to include picker state cleanup).

Including FR29 and FR30 in the Scheduled Process row creates a misleading attribution: a reader would expect that the Scheduled Process implements the routing logic of FR29/FR30 directly, when in fact those FRs are primarily implemented by Message Dispatcher (CallbackQuery routing) and USG (state transitions). The only Scheduled Process involvement is timeout cleanup, which is correctly covered by FR18.

Contrast: Message Dispatcher row correctly lists FR29 and FR30 in its FRs column. Having the same FRs appear in two distinct component rows without qualification creates an ambiguous ownership picture.

**Fix required:** Remove FR29 and FR30 from the Scheduled Process row's "FRs handled" column. The Scheduled Process row's description already states "4 jobs + picker state timeout cleanup" which is sufficient and accurate. If traceability to the timeout aspect is needed, a parenthetical note "(timeout cleanup per FR18)" in the description column is clearer than listing FR29/FR30 as primary owners.

---

### F4 [minor] — Criterion 2 (ADR quality) — ADR-013 does not discuss NFR18 latency risk from the DB catalog query in the Consequences section

**Location:** `/docs/architecture/adrs/adr-013-inline-keyboard-callback-routing.md`, Consequences section (Negative subsection).

**Description:** The ADR's Negative consequences section correctly notes the 64-byte callback_data truncation risk and the stale keyboard UX issue. However, a relevant negative consequence is absent: routing CallbackQuery events through Message Dispatcher with a synchronous DB catalog query (metric ownership validation at step 4 of the Decision) adds a mandatory DB round-trip before any response. For management-command callbacks, this is in addition to the recency-ordering query already performed at keyboard construction time. The ADR's NFR section mentions this in passing ("dominant cost is DB metric catalog query") but does not list it as a formal negative consequence requiring mitigation.

This omission is not severe because the scale is bounded, but the "Negative consequences" section should be the exhaustive list of costs, not the NFR section.

**Fix required:** Add a bullet to the Negative consequences in ADR-013: "The ownership-validation DB read (step 4) adds a mandatory DB round-trip on every CallbackQuery event; at stated scale (≤20 users, ≤20 metrics each) this is within the NFR18 budget, but it must be re-evaluated at the 20-user ceiling."

---

### F5 [minor] — Criterion 5 (Observability readiness) — `picker_invocation_event` not yet in the Observability section's key event types list but is referenced in ADR-013 Follow-ups

**Location:** `/docs/architecture/overview.md`, Observability section, "Key event types" list, and ADR-013 Follow-ups.

**Description:** ADR-013 Follow-ups explicitly state: "Add `picker_invocation_event` to the Observability event registry to track picker usage and NFR18 latency." However, the `picker_invocation_event` IS already present in the overview's Observability section key event types list (line 180). This means the ADR follow-up action has already been completed in the overview, but the ADR itself does not acknowledge this — the follow-up is written as if it is still outstanding. This creates a minor consistency gap: the ADR's follow-up section implies work not yet done, while the overview shows it as done.

**Fix required:** Update ADR-013 Follow-up item to mark it resolved: "~~Add `picker_invocation_event` to the Observability event registry~~ — completed in overview.md Observability section." Or, since ADRs should not be live task trackers, reframe as a confirmation: "Confirmed: `picker_invocation_event` added to overview.md Observability section."

---

### F6 [praise] — Criterion 2 (ADR quality) — ADR-013 alternatives are genuinely distinct and honestly assessed

**Description:** All three alternatives (A1: per-type handlers, A2: state-only routing, A3: self-contained callback_data) represent real architectural choices with meaningfully different trade-offs. Each "Why not" rationale is specific and tied to observable design properties. The 64-byte limit is identified in context (A3 "Why not") and then formally addressed in the Decision section and Negative consequences. The stale keyboard UX issue is named explicitly as an acknowledged limitation rather than hand-waved. This is a strong ADR.

---

### F7 [praise] — Criterion 4 (Security) — Callback ownership validation is structurally enforced at two layers

**Description:** The architecture explicitly states that metric_id ownership is validated at the routing layer (ADR-013 Decision step 4) in addition to the mandatory internal_user_id scoping at the Data Repository layer (ADR-005). This defense-in-depth for callback replay/forgery is beyond the minimum required and is clearly documented in both the Security section and the ADR. The stale-state rejection (UC16 E3 via ConversationState gate) provides a third check. This is well-designed.

---

### F8 [nit] — Criterion 7 (Diagram quality) — Container diagram caption could note CallbackQuery event type update

**Location:** `/docs/architecture/overview.md`, C4 Level 2 container diagram, caption.

**Description:** The C4 Level 2 caption now correctly states "Inbound events now include both Message events (text commands) and CallbackQuery events (inline keyboard button presses)." However, the Mermaid diagram label on the edge from TGA to BOT still reads `"inbound events\n(Message + CallbackQuery)"` in a compressed form that only readers of the caption will interpret correctly. This is a nit — the caption does the work — but the diagram label itself is slightly compressed compared to the clarity of the caption.

**Fix required:** No action required; advisory only.

---

## Per-Criterion Scores

### Criterion 1 — Alignment with NFRs (weight 0.20)

All 18 NFRs (NFR1–NFR18) are addressed in the NFR Mapping table with named mechanisms. NFR18 is the new addition for this feature. The mechanism is plausible at stated scale but the "met by design" claim is unsupported by any capacity analysis for the DB catalog query path (F2, major). All other NFRs retain well-established mechanisms from prior architecture. The NFR18 deficiency is bounded to the new feature and the scale ceiling limits the severity.

**Score: 7.5 / 10.0**

---

### Criterion 2 — Decision rationale / ADRs (weight 0.20)

ADR-013 has three genuinely distinct alternatives, honest positive and negative consequences, and a clear decision with specific implementation rules. Minor issue: the Follow-up section contains a resolved action written as if still pending (F5). Minor issue: the DB catalog query latency risk is mentioned in the NFR section but not formally in the Negative consequences (F4). Neither is a major gap. Refs hygiene issue on the unverifiable `feat-smart-metric-picker` ref (F1) touches this criterion. ADR quality is generally strong (F6, praise).

**Score: 8.0 / 10.0**

---

### Criterion 3 — Scalability and evolvability (weight 0.15)

The architecture correctly notes the 20-user hard ceiling and the single-process monolith scale model. No new bottlenecks are introduced: the picker runs in-process (no new external service). The DB catalog query is a bounded indexed scan. The FR attribution error in the Scheduled Process row (F3, major) does not introduce a bottleneck but creates a misleading ownership picture that could misdirect implementation. No new unbounded queues, global locks, or synchronous chains are introduced beyond the existing synchronous webhook handler pattern. The picker's synchronous path is structurally identical to the existing disambiguation flow.

**Score: 7.5 / 10.0** (deducted ~1.5 for F3 major)

---

### Criterion 4 — Security posture (weight 0.15)

The security section is comprehensive and now includes the picker-specific additions: metric catalog query scoped by internal_user_id (cross-user picker visibility structurally prevented), callback_data ownership validation at routing layer (ADR-013), stale callback rejection via ConversationState gate. The pre-existing security model (bot token, per-user isolation, raw_input exclusion, no personal data) is preserved and explicitly confirmed as unaffected by this feature. Defense-in-depth on callback replay is commendable (F7, praise).

**Score: 9.0 / 10.0**

---

### Criterion 5 — Observability readiness (weight 0.15)

The new `picker_invocation_event` is added to the key event types list. The SLO `picker_keyboard_latency_ms ≤ 5,000` is tied to NFR18. The failure scenario for picker session abandonment (stale keyboard) is covered in the Failure Scenarios table with detection, mitigation, and residual risk all stated. The ADR Follow-up section inconsistently implies `picker_invocation_event` is still pending when it is already present in the overview (F5, minor). Observability coverage is otherwise solid.

**Score: 8.5 / 10.0** (deducted 0.5 for F5 minor)

---

### Criterion 6 — Cost and operational fit (weight 0.10)

No new infrastructure components are introduced. The feature runs entirely in-process. The only operational change is the Alembic migration for DM6 enum extension (PendingMetricPicker, PendingPickerValue), which is explicitly noted in the Deployment section. Cost impact is zero (same Railway/Supabase footprint). Operational burden is unchanged. The deployment note is clear and actionable.

**Score: 9.0 / 10.0**

---

### Criterion 7 — Diagram quality (weight 0.05)

All three C4 diagrams (context, container, component) are present, captioned, and referenced from prose. The component diagram caption explicitly explains the no-new-box decision and directs readers to ADR-013 — this is good traceability. The container diagram edge label correctly reflects the new CallbackQuery event type. The component diagram correctly shows Message Dispatcher with the updated label "(Message + CallbackQuery)". No orphan boxes introduced. One nit on diagram label compression (F8).

**Score: 8.5 / 10.0**

---

## Score Calculation

| # | Criterion | Weight | Score | Weighted |
|---|---|---|---|---|
| 1 | Alignment with NFRs | 0.20 | 7.5 | 1.50 |
| 2 | Decision rationale (ADRs) | 0.20 | 8.0 | 1.60 |
| 3 | Scalability & evolvability | 0.15 | 7.5 | 1.13 |
| 4 | Security posture | 0.15 | 9.0 | 1.35 |
| 5 | Observability readiness | 0.15 | 8.5 | 1.28 |
| 6 | Cost & operational fit | 0.10 | 9.0 | 0.90 |
| 7 | Diagram quality | 0.05 | 8.5 | 0.43 |
| **Total** | | **1.00** | | **8.2** |

No blockers present. Score not capped.

**Score: 8.2 — needs-revision**

---

## Verdict

**Score: 8.2 / 10.0 — needs-revision**

The architecture is structurally sound. ADR-013 is well-argued, security posture is strong, and observability coverage is adequate. Two issues require fixes before approval:

1. **F3 (major)** — FR29/FR30 misattributed to Scheduled Process row. This creates an implementation ambiguity that could mislead developers into placing routing logic in the wrong component. Fix is a one-line table edit.

2. **F2 (major)** — NFR18 "met by design" lacks a bounded capacity statement for the DB catalog query path. At ≤20 users this is safe, but the claim is not reviewable without a stated scope boundary. Fix is an addendum to the NFR18 row.

Fixes F1, F4, F5 are minor and can be bundled with the above. No design change is required — all fixes are documentation corrections.

**Action:** `stage: arch-revise`. Resolve F2 and F3 at minimum. Re-review not required for minor/nit items if architect acknowledges them in the revision changelog.

---

## Changelog Entry

- 2026-04-28T01:00Z: Initial architecture review for smart-metric-picker feature. Reviewed arch-overview v0.1 and ADR-013 v0.1. Score: 8.2. Verdict: needs-revision. Major findings: F2 (NFR18 capacity claim unsupported), F3 (FR29/FR30 misattributed to Scheduled Process). Minor findings: F1 (unverifiable ref), F4 (ADR Negative consequences incomplete), F5 (ADR follow-up inconsistency). Reviewer: architect-reviewer.
