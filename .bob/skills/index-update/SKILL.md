---
name: index-update
description: Rebuild numbered indices and manifest (canonical procedure pointer)
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Command: index-update

Canonical procedure: .bob/commands/index-update.md - follow it verbatim.
Contract: AGENTS.md sections 5, 11.

Boundary: runner rebuilds and splits near 9k tokens (hard 10k) and regenerates manifest; agent verifies semantics, never hand-edits generated parts.
