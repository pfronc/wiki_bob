---
name: bob-create-page
description: >-
  Create an entity, concept, source, or analysis page in the Bob wiki when the
  user invokes /create-page or asks to add a canonical wiki page.
---

# Bob Create Page

Read [`../../../.bob/commands/create-page.md`](../../../.bob/commands/create-page.md) completely and follow it together with the repository `AGENTS.md`.

Resolve the page type, title, filename, content, and relationships from the request; ask only for information that cannot be inferred safely. Check titles, canonical titles, aliases, indices, and source registry before creation.

Use `python tools/bob_runner.py create-page --type <type> --title "<title>" --filename <kebab-name>.md` for the skeleton. Enrich it with the documented template, provenance, bidirectional links, index rebuild, and substantive log entry. Never write to `raw/`.

Do not silently compact prose to satisfy the 5,000-token page review threshold. When a sourced page exceeds it, first measure what actually drives the size — citation page anchors are counted as tokens and can be ~30% of a well-cited page — then report the finding and offer the user the options: accept the advisory warning, raise `PAGE_WARNING_TOKENS` (requires user approval, `AGENTS.md` section 12), or split the page into several items. Never trade away provenance or scope to fit the number.

If the runner exhibits a genuine defect, stop and follow `AGENTS.md` section 12 before reading or changing the runner.
