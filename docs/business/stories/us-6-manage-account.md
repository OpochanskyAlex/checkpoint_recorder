---
doc: US
id: US6
project: checkpoint_recorder
version: 0.1
status: draft
owner: business-analyst
reviewed_by: null
score: null
activities: [account]
refs:
  - {doc: brd, version: 0.1}
updated: 2026-04-26
tags: [project-docs, user-story]
---

# US6: Manage account

Traces to [[brd#R7|R7]], [[brd#R8|R8]], [[brd#R9|R9]], [[brd#R11|R11]], [[brd#G3|G3]].

Activity tags: `@account`

## Story

As a **user who cares about my data privacy**, I want to be automatically registered without providing personal information, understand my data policy upfront, and be able to delete my account with a safety window so that I trust the system with my ongoing tracking data.

## Acceptance Criteria

- AC6.1 Given a first-time user sends any message, exactly one account is created storing only an opaque internal ID (no Telegram name, username, or phone); an onboarding message is returned covering retention policy, no-export, verbatim message storage, and one-shot alerts.
- AC6.2 Given two simultaneous first messages from the same user, exactly one account record is created (idempotent registration).
- AC6.3 Given the user requests account deletion and confirms, the account enters a 72-hour pending period; no data is deleted immediately and the user is informed they can restore within that window.
- AC6.4 Given the user contacts the bot within the 72-hour window, they may restore their account; all data is preserved.
- AC6.5 Given 72 hours elapse without restoration, all user data is permanently and irreversibly deleted with no recovery path.

## Notes

Privacy by design (D-002, R7): no personal Telegram fields stored. The 72-hour grace period (D-010) is the sole protection against accidental deletion. After expiry, deletion is irreversible — consistent with the no-export policy (D-004).

## Open Questions

(None.)
