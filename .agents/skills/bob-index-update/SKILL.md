---
name: bob-index-update
description: >-
  Rebuild and verify Bob wiki indices when the user invokes /index-update or
  asks to refresh generated wiki navigation and index coverage.
---

# Bob Index Update

Read [`../../../.bob/commands/index-update.md`](../../../.bob/commands/index-update.md) completely and follow it together with the repository `AGENTS.md`.

Run `python tools/bob_runner.py index-update` from the repository root. Do not hand-edit generated numbered indices or the manifest. Review the result for semantic descriptions, exact coverage, alphabetical ordering, valid relative links, navigation, source counts, and token limits.

Enrich the runner's log entry only when substantive manual review or reorganization occurred. Obtain user confirmation before ambiguous reorganization.

If the runner exhibits a genuine defect, stop and follow `AGENTS.md` section 12 before reading or changing the runner.
