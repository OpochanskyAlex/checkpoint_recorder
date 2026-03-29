# CLAUDE.md — Business & System Requirements Pipeline

## Overview

This pipeline transforms a raw business idea into validated, versioned business and system requirements documents. It uses four specialized agents in sequence, with critic gates and stakeholder Q&A loops at each stage.

```
[Input: idea.md]
      │
      ▼
┌─────────────────────┐
│  Stage 1            │
│  Business Thinker   │  ──► Business Analysis Document v0.1
│  (business-thinker) │
└─────────────────────┘
      │
      ▼
┌─────────────────────┐
│  Stage 2            │
│  Business Critic    │  ──► Business Review Report
│  (business-thinker-critic)    │
└─────────────────────┘
      │
      ├── Score < 40? ──► Collect stakeholder Q&A ──► back to Stage 1
      │
      ▼ Score ≥ 40
┌─────────────────────┐
│  Stage 3            │
│  Context Architect  │  ──► System Context Document v0.1
│  (context-architect)│
└─────────────────────┘
      │
      ▼
┌───────────────────────────────┐
│  Stage 4                      │
│  System Critic                │  ──► System Review Report
│  (context-architect-critic)   │
└───────────────────────────────┘
      │
      ├── Score < 40? ──► Collect stakeholder Q&A ──► back to Stage 3
      │
      ▼ Score ≥ 40
[Output: versioned .md files]
```

---

## Input

Place your business idea file at: `initial_task_setup.md`

Minimum viable content:
- What problem is being solved
- Who is affected
- Any known constraints (budget, timeline, regulation)
- Any known stakeholders

---

## Commands

Run the full pipeline:
```bash
claude --allowedTools "Read,Write,mcp__filesystem" < CLAUDE.md
```

Or trigger specific stages:
```
/run-business-analysis   # Stage 1 + 2 only
/run-system-analysis     # Stage 3 + 4 only (requires approved business doc)
/run-full-pipeline       # All stages end-to-end
```

---

## Pipeline Execution Instructions

When this file is loaded, execute the following steps in order.

### STEP 0 — Load Input

1. Read `./input/idea.md`
2. If file does not exist → stop and ask the user to provide the business idea file
3. Print: `✅ Input loaded. Starting Business Analysis Pipeline.`

---

### STEP 1 — Business Thinker (v0.1)

**Agent:** `business-thinker`  
**Prompt template:**

```
You are acting as: business-thinker

INPUT DOCUMENT (version: raw-input):
---
{CONTENTS OF ./input/idea.md}
---

Produce a Business Analysis Document following your system prompt exactly.
Mark this as version v0.1.
Base it on: raw-input.
```

**Save output to:** `./output/business/business_v0.1.md`

---

### STEP 2 — Business Review Critic

**Agent:** `business-thinker-critic`  
**Prompt template:**

```
You are acting as: business-thinker-critic

DOCUMENT TO REVIEW:
---
{CONTENTS OF ./output/business/business_v0.1.md}
---

Produce a Business Review Report following your system prompt exactly.
Reference version: v0.1.
```

**Save output to:** `./output/business/business_review_v0.1.md`

**Gate logic:**

- Parse `Total Score: X / 50` from the review report
- If **Score ≥ 40** → proceed to Step 3
- If **Score < 40** → proceed to Step 2a (Stakeholder Q&A Loop)

---

### STEP 2a — Business Stakeholder Q&A Loop

**Trigger:** Business review score < 40, OR critic recommendation is `Reject` or `Iterate`

1. Extract all `Mandatory Revisions` from the review report
2. Extract all `Open Questions` that were flagged
3. Group them into clear stakeholder questions — remove duplicates and technical jargon
4. Present the questions to the user:

```
⚠️  The Business Review requires clarification before proceeding.
Score: {X}/50 — {Reject | Iterate | Accept with Adjustments}

Please answer the following questions to allow revision:

1. {Question extracted from mandatory revisions}
2. {Question extracted from open questions}
...
```

5. Wait for user answers
6. When answers are received, re-run **Step 1** with the following prompt:

```
You are acting as: business-thinker

PREVIOUS VERSION: v0.{N}
---
{CONTENTS OF previous business_vX.md}
---

STAKEHOLDER RESPONSES:
---
{USER ANSWERS}
---

CRITIC FEEDBACK:
---
{CONTENTS OF business_review_vX.md}
---

Produce an updated Business Analysis Document as version v0.{N+1}.
Address all mandatory revisions.
Incorporate stakeholder responses.
Do NOT regress on previously accepted decisions.
```

7. Save as `./output/business/business_v0.{N+1}.md`
8. Re-run **Step 2** on the new version
9. Repeat until score ≥ 40, max 3 iterations
10. After 3 iterations without passing → pause and notify user:

```
⛔  Pipeline paused after 3 revision cycles.
The business case requires deeper stakeholder input.
Latest score: {X}/50
Latest document: ./output/business/business_v0.{N}.md
Latest review:   ./output/business/business_review_v0.{N}.md

Please review both documents and restart the pipeline with a revised idea.md.
```

---

### STEP 3 — Context Architect (v0.1)

**Trigger:** Business review score ≥ 40

**Agent:** `context-architect`  
**Prompt template:**

```
You are acting as: context-architect

APPROVED BUSINESS DOCUMENT (version: v{N}):
---
{CONTENTS OF latest approved ./output/business/business_v{N}.md}
---

Produce a System Context Document following your system prompt exactly.
Mark this as system version v0.1.
Based on: Business v{N}.
```

**Save output to:** `./output/system/system_v0.1.md`

---

### STEP 4 — System Critic

**Agent:** `context-architect-critic`  
**Prompt template:**

```
You are acting as: context-architect-critic

SYSTEM DOCUMENT TO REVIEW:
---
{CONTENTS OF ./output/system/system_v0.1.md}
---

Produce a System Review Report following your system prompt exactly.
Reference version: v0.1.
```

**Save output to:** `./output/system/system_review_v0.1.md`

**Gate logic:**

- Parse `Total Score: X / 50` from the review report
- If **Score ≥ 40** → proceed to Step 5 (Final Output)
- If **Score < 40** → proceed to Step 4a (System Q&A Loop)

---

### STEP 4a — System Stakeholder Q&A Loop

**Trigger:** System review score < 40, OR recommendation is `Reject` or `Iterate`

1. Extract `Mandatory Revisions` from the system review
2. Group into clear stakeholder questions — avoid technical jargon
3. Present to user:

```
⚠️  The System Review requires clarification before proceeding.
Score: {X}/50 — {Reject | Iterate | Accept with Adjustments}

Please answer the following questions:

1. {Question from mandatory revisions}
2. {Question from structural weaknesses}
...
```

4. Wait for user answers
5. When answers are received, re-run **Step 3** with:

```
You are acting as: context-architect

PREVIOUS SYSTEM VERSION: v0.{N}
---
{CONTENTS OF system_v0.{N}.md}
---

STAKEHOLDER RESPONSES:
---
{USER ANSWERS}
---

SYSTEM CRITIC FEEDBACK:
---
{CONTENTS OF system_review_v0.{N}.md}
---

APPROVED BUSINESS DOCUMENT: v{B}
---
{CONTENTS OF approved business doc}
---

Produce an updated System Context Document as version v0.{N+1}.
Address all mandatory revisions.
Incorporate stakeholder responses.
Do NOT contradict approved business decisions.
```

6. Save as `./output/system/system_v0.{N+1}.md`
7. Re-run **Step 4** on the new version
8. Repeat until score ≥ 40, max 3 iterations
9. After 3 iterations without passing → pause and notify user

---

### STEP 5 — Final Output Summary

When both stages are approved (scores ≥ 40), produce a summary:

```
✅ Pipeline Complete

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
APPROVED BUSINESS DOCUMENT
  File:    ./output/business/business_v{N}.md
  Version: v{N}
  Score:   {X}/50

APPROVED SYSTEM DOCUMENT
  File:    ./output/system/system_v{M}.md
  Version: v{M}
  Score:   {Y}/50
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

REVISION HISTORY
  Business: {list of versions produced}
  System:   {list of versions produced}

OPEN ITEMS (not blocking, but noted by critics)
  {Any non-mandatory items flagged across all reviews}

Next step: Use approved system document as input for architecture design.
```

---

## Output Directory Structure

```
./input/
  idea.md                         ← Your input

./output/
  business/
    business_v0.1.md              ← First business analysis
    business_review_v0.1.md       ← First business review
    business_v0.2.md              ← Revised (if needed)
    business_review_v0.2.md       ← Review of revision
    ...
  system/
    system_v0.1.md                ← First system context doc
    system_review_v0.1.md         ← First system review
    system_v0.2.md                ← Revised (if needed)
    system_review_v0.2.md         ← Review of revision
    ...
```

---

## Agent System Prompts

The four agents used in this pipeline are defined in:

| File | Agent |
|------|-------|
| `01_Business_Thinker.md` | `business-thinker` |
| `02_Business_Review_Critic.md` | `business-thinker-review-critic` |
| `03_Context_Architect.md` | `context-architect` |
| `04_System_Critic.md` | `context-architect-critic` |

When running in Claude Code, load each agent's system prompt verbatim before sending their prompt template. Do not mix agent personas — each agent operates independently and sees only its designated inputs.

---

## Critic Score Interpretation

| Score | Meaning | Action |
|-------|---------|--------|
| < 30 | Major flaws | Reject — mandatory rework, collect stakeholder input |
| 30–39 | Weak clarity | Iterate — substantial revisions needed |
| 40–44 | Acceptable | Accept with minor adjustments — proceed |
| 45–50 | Strong | Accept as baseline — proceed confidently |

**Pipeline gate threshold: 40**

---

## Versioning Rules

- All documents start at `v0.1`
- Each revision increments the minor version: `v0.2`, `v0.3`, etc.
- A critic-approved document is promoted to a clean integer version for handoff: `v1.0`
- No document is overwritten — all versions are preserved
- Every version must include a `Based on` reference and a `Changes Introduced` log

---

## Notes for Claude Code Execution

- Read agent system prompts from the `.md` files before constructing each prompt
- Use `Write` tool to save all output files
- Do not skip the critic stages even if you believe the output is good
- Stakeholder questions must be presented to the user — do not auto-answer them
- Do not merge or abbreviate agent outputs — preserve full structured Markdown
- If any agent output is truncated, re-request with a continuation prompt before saving
