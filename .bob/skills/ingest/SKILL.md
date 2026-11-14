---
name: ingest
description: 'Process a raw/ source into wiki pages (canonical procedure pointer)'
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Command: ingest

Canonical procedure: `.bob/commands/ingest.md` — follow it verbatim.
Contract: `AGENTS.md` §§1, 2, 3.4, 4, 6, 11, 12.

Boundary: runner extracts chunks + scaffolds source page + log stub; agent reviews takeaways, confirms with user, then enriches pages, links, index, log.
