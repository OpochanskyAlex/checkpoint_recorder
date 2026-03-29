# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## What This Repository Is

A multi-agent pipeline that transforms a raw business idea into versioned, reviewed business analysis and system context documents. There is no application code — the pipeline IS the product.

The target project being documented here is a **Telegram bot for personal metric tracking** (`docs/requirements/initial_task_setup.md`).

---

## Pipeline Overview
Unless other specified, do following.

```
input: initial_task_setup.md
    │
    ▼
[Stage 1] business-thinker          → output/business/business_v0.1.md
[Stage 2] business-thinker-critic   → output/business/business_review_v0.1.md
    │  Score < 40 → Q&A loop → re-run Stage 1
    ▼  Score ≥ 40 or more than 3 cycles
[Stage 3] context-architect         → output/system/system_v0.1.md
[Stage 4] context-architect-critic  → output/system/system_review_v0.1.md
    │  Score < 40 → Q&A loop → re-run Stage 3
    ▼  Score ≥ 40 or more than 3 cycles
[Stage 5] architecture-designer     → output/system/architecture_v0.1.md
[Stage 6] architecturecritic        → output/system/architecture_review_v0.1.md
    │  Score < 40 → Q&A loop → re-run Stage 5
    ▼  Score ≥ 40 or more than 3 cycles
[Stage 7] architecture-designer         → output/system/architecture_v0.1.md
[Stage 8] architecture-designer-critic  → output/system/architecture_review_v0.1.md
    │  Score < 40 → Q&A loop → re-run Stage 7
    ▼  Score ≥ 40 or more than 3 cycles
Pipeline complete
```

**Gate threshold:** Score ≥ 40/50 to advance. Max 3 revision cycles per stage before pausing for deeper stakeholder input.

---

## Running the Pipeline

There are no build or test commands. The pipeline is driven by Claude Code agents directly.
iN case of uncertainty, ask questions. Preferable to combine questions in a batch.

**Input file:** `docs/requirements/initial_task_setup.md`

**To run a stage manually**, invoke the appropriate agent (see Agent Definitions below) with the prompt templates defined in this file.

**Versioning:** Documents start at `v0.1`, increment on each revision (`v0.2`, `v0.3`…), and are promoted to `v1.0` on critic approval. Never overwrite — all versions are preserved.

---

## Directory Structure

```
docs/requirements/
  initial_task_setup.md     ← Business idea input

output/
  business/
    business_v0.N.md        ← Business analysis (each iteration)
    business_review_v0.N.md ← Critic review of each version
  system/
    system_v0.N.md          ← System context doc (each iteration)
    system_review_v0.N.md   ← Critic review of each version

old/                        ← Archived earlier attempts (pre-pipeline)
```

---

## Agent Definitions

Each agent has a dedicated system prompt file. Load it verbatim before constructing the agent's prompt. Do not mix agent personas.

| Stage | Agent ID | System Prompt File |
|-------|----------|-------------------|
| 1 | `business-thinker` | `01_Business_Thinker.md` |
| 2 | `business-thinker-review-critic` | `02_Business_Review_Critic.md` |
| 3 | `context-architect` | `03_Context_Architect.md` |
| 4 | `context-architect-critic` | `04_System_Critic.md` |

---

## Critic Score Reference

| Score | Decision | Pipeline Action |
|-------|----------|----------------|
| < 30 | Reject | Mandatory rework + stakeholder Q&A |
| 30–39 | Iterate | Substantial revisions + stakeholder Q&A |
| 40–44 | Accept with adjustments | Advance to next stage |
| 45–50 | Accept | Advance confidently |

---

## Key Pipeline Rules

- **Never auto-answer stakeholder questions** — present them to the user and wait for responses.
- **Never skip the critic stage** — even if agent output looks strong.
- Every document must include a `Based on` reference and a `Changes Introduced` log.
- Each stage sees only its designated inputs — no cross-stage context bleed.
- If agent output is truncated, re-request with a continuation prompt before saving.
