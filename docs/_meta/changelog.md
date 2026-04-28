# Changelog

## 2026-04-29T00:20Z | human | _meta/state.yaml
feature-addition | smart-metric-picker | Plan approved. Workflow complete. All stages: BA (8.2), SA (8.5), Arch (8.2), PM (human-approved). Implementation ready to begin — 12 tasks, ~191k tokens ±25%, critical path T1→T3→T4→T5→T6→T7→T8.

## 2026-04-29T00:10Z | orchestrator | project/plan-smart-metric-picker.md
feature-addition | smart-metric-picker | Post-Q&A plan revisions: T13 removed (tests in separate activity); T2 simplified to 1 env var (FUZZY_MATCH_THRESHOLD only, picker timeout reuses periodicity_prompt_expiry_hours per Q-PM-3 Option A); T7 reduced (USG middleware confirmed to cover CallbackQuery, no extension needed per Q-PM-2); T10 updated to reference existing setting; critical path updated T1→T3→T4→T5→T6→T7→T8; total token budget revised to ~191k ±25% (range 143k–239k); all 3 open questions resolved.

## 2026-04-29T00:00Z | project-manager | project/plan-smart-metric-picker.md
feature-addition | smart-metric-picker | Implementation plan created: 13 WBS tasks (T1–T13) across 4 milestones (M1 Core FSM+DB, M2 Picker UX, M3 Management+cancel, M4 Testing+observability); total token budget ~237k (±25%, range 178k–296k); critical path T1→T3→T4→T5→T6→T7→T8→T13; 8 implementation risks (RISK-F1–F8); 3 open questions (Q-PM-1–3).

## 2026-04-28T01:15Z | orchestrator | architecture/overview.md, architecture/adrs/adr-013-inline-keyboard-callback-routing.md
feature-addition | smart-metric-picker | Post-arch-review fixes (score 8.2): F1 feat-smart-metric-picker ref replaced with uc-16; F2 NFR18 capacity note added (≤400 rows, p95 ≪1s); F3 FR29/FR30 removed from Scheduled Process FRs; F4 ownership-validation DB round-trip added to ADR-013 Negative; F5 picker_invocation_event follow-up marked confirmed.

## 2026-04-28T01:00Z | architect | architecture/overview.md, architecture/adrs/adr-013-inline-keyboard-callback-routing.md
feature-addition | smart-metric-picker | Architecture delta: overview updated (FR22–FR31, NFR18, DM6 picker states, CallbackQuery routing, picker abandon failure scenario, Flow J, ADR-013 ref, AG-1 updated, Traceability Matrix updated); ADR-013 created (inline keyboard CallbackQuery routing — routed through Message Dispatcher, callback_data encoding pick:/create: action types, state gate, ownership validation). Component ownership: absorbed into existing components (Option 2 — no new component box). open_questions Q1–Q5 carried forward unchanged.

## 2026-04-28T00:35Z | orchestrator | system/srs.md, system/cases/uc-{2,6,7,8,10}-*.md
feature-addition | smart-metric-picker | Post-SA-review fixes: FR31 added (/cancel pre-existing undocumented command); /cancel + split inline-button rows added to Command Interface (F4); DM6 state machine updated with /cancel arcs on all non-Idle states + PendingMetricPicker→PendingPeriodicity arc (F3, F5); feat-smart-metric-picker ref added to UC2/UC6/UC7/UC8/UC10 (F2).

## 2026-04-28T00:30Z | system-analyst-reviewer | system/reviews/srs-smart-metric-picker-v0.1-20260428T0030Z.md
feature-addition | smart-metric-picker | SA review complete. Score: 8.5. Verdict: approved.

## 2026-04-28T00:20Z | system-analyst | system/srs.md, system/cases/uc-16-select-metric-picker.md, system/cases/uc-2-log-metric.md, system/cases/uc-6-archive-metric.md, system/cases/uc-7-delete-metric.md, system/cases/uc-8-configure-alert.md, system/cases/uc-10-request-chart.md, system/use-case-diagram.puml
feature-addition | smart-metric-picker | SRS delta: FR22–FR30 added, FR6 trigger updated (Create button via FR27, not auto-create), NFR18 added, DM6 enum+state_data extended (PendingMetricPicker+PendingPickerValue), Command Interface updated (metric_name optional on 5 commands + inline picker row), BR13+BR14 added, SU-010 added (rapidfuzz threshold), Q6–Q12 recorded (Q6–Q9 resolved, Q10–Q12 open); UC16 created (full picker interaction); UC2/UC6/UC7/UC8/UC10 annotated with picker intercept notes; use-case-diagram updated with UC16 node + 5 extend relationships.

## 2026-04-28T00:15Z | orchestrator | business/brd.md, business/features/feat-smart-metric-picker.md, business/stories/us-8-metric-picker.md, business/stories/us-1-log-metric.md
feature-addition | smart-metric-picker | Post-review amendments: R2 rewritten (auto-create replaced by explicit Create-button flow per R17); R18 added (@management zero-match path); R15 "scrollable" qualifier clarified (F3); US1 AC1.2 and Notes updated; stale R2 note in US8 replaced (F2); all R18 traces added.

## 2026-04-28T00:10Z | business-analyst-reviewer | business/reviews/feat-smart-metric-picker-v0.1-20260428T0000Z.md
feature-addition | smart-metric-picker | BA review complete. Score: 8.2. Verdict: approved.

## 2026-04-28T00:00Z | business-analyst | business/features/feat-smart-metric-picker.md, business/stories/us-8-metric-picker.md, business/brd.md, checkpoint_recorder.md
feature-addition | smart-metric-picker | Added R12–R16 (inline metric picker for bare/fuzzy commands), US8 (metric picker story), feature spec with 6 open questions, and glossary additions; no existing IDs altered.

## 2026-04-26T00:00Z | orchestrator | _meta/state.yaml, _meta/changelog.md
Init. Workflow rewrite-docs started. Directory structure created. Source file inventory: 9 files in docsOLD/. Stages: ba, sa, arch, pm. Activities taxonomy established.

## 2026-04-26T00:04Z | project-manager | project/plan.md, project/risks.md, checkpoint_recorder.md
rewrite-docs | docsOLD/requirements/project_plan.md v1.1 → project/plan.md + project/risks.md | human-pending-review.
v0.1 draft. 4 milestones (M1–M4) aligned to source delivery stages; 13 WBS tasks (T1–T13) with T-shirt + token sizing; critical path T1→T3→T5→T8→T11→T12→T13; RACI (solo project); 3 open questions (OI-2/OI-3/OI-1 status); 11 risks (RISK1–RISK8 from BRD + RISK9–RISK11 from architecture). Orphan included: Planning Assumptions (§6). Sizing added (required by template, not present in source).

## 2026-04-26T00:03Z | architect | architecture/overview.md, architecture/adrs/adr-001..adr-012 (12 files), checkpoint_recorder.md
rewrite-docs | docsOLD/requirements/architecture.md v0.9 + docsOLD/requirements/technology.md + docsOLD/requirements/implementation_spec.md §7,§8 → architecture/overview.md + 12 ADR files | human-pending-review.
v0.1 draft. C4 L1–L3 diagrams; 13 components documented; full tech stack (ADR-012); integrations table; all 17 NFRs mapped; cross-cutting concerns (security, observability, data, deployment); 12 ADRs (ADR-001–ADR-012). Orphans included: Architectural Goals (AG-1–AG-7), Interaction Flows Summary (A–I), Failure Scenarios (12 scenarios), Traceability Matrix. Source open items AU-001/002/003 resolved. D2 discrepancy (aiogram FSM vs direct DB) noted in ADR-012 — do not edit code.

## 2026-04-26T00:02Z | system-analyst | system/srs.md, system/use-case-diagram.puml, system/cases/uc-*.md (15 files), checkpoint_recorder.md
rewrite-docs | docsOLD/requirements/system_analysis.md + docsOLD/requirements/implementation_spec.md → system/srs.md + 15 UC files | human-pending-review.
v0.1 draft. FR1–FR21; NFR1–NFR17; DM1–DM8; Command Interface; 15 use cases (UC1–UC15); 5 state machines; BR1–BR12; 5 open questions. Absorbed from impl_spec: all FRs → UCs, NFRs, validation rules (→ DM constraints), lifecycle models (→ state machines), business rules. Deferred to arch: integration requirements (§7), error handling (§8). Dropped: readiness assessment (point-in-time). Orphans included: periodicity vocab, dimension naming convention, SD decision log, SU uncertainty register. Discrepancy noted: D2 (aiogram FSM vs direct DB ConversationState management) in DM6. Source open issues Q1-Q5 carried forward; OI-2 and OI-3 marked resolved.

## 2026-04-26T00:01Z | business-analyst | business/brd.md, business/stories/us-*.md (7 files), checkpoint_recorder.md
rewrite-docs | docsOLD/requirements/business_analysis.md + docsOLD/requirements/initial_task_setup.md → business/brd.md | human-pending-review.
v0.1 draft. G1–G4 goals; SH1–SH5 stakeholders; R1–R11 requirements; US1–US7 user stories (separate files). Activity taxonomy: logging, management, analytics, alerting, account, discovery, General. Orphan sections included as custom: Risks (RISK1–RISK8), Decision Log (D-001–D-013), Hypothesis Statement, Traceability. Source discrepancies: none at BRD layer.
