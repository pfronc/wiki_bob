---
name: bob-lint
description: >-
  Audit Bob wiki health when the user invokes /lint or asks for a deterministic
  wiki integrity, provenance, link, index, or extraction-state review.
---

# Bob Lint

Read [`../../../.bob/commands/lint.md`](../../../.bob/commands/lint.md) completely and follow it together with the repository `AGENTS.md`.

Run `python tools/bob_runner.py lint` from the repository root. Treat lint as read-only: report deterministic findings and add a clearly separated semantic review of contradictions, staleness, missing concepts, and index-description quality.

Do not remediate findings during a lint request. Propose repairs and obtain explicit user direction before changing claims, merging pages, deleting duplicates, or reorganizing ambiguous relationships.

An `Oversized files` finding is advisory, not a defect to auto-fix. Report the count and what drives the size, but do not start compacting pages or proposing splits as automatic repairs: the threshold is a review prompt, pre-existing pages already exceed it, and remediation — including changing `PAGE_WARNING_TOKENS` — needs explicit user direction.

If the runner exhibits a genuine defect, stop and follow `AGENTS.md` section 12 before reading or changing the runner.
