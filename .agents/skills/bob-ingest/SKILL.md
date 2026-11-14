---
name: bob-ingest
description: >-
  Ingest a supported file from raw/ into the Bob wiki when the user invokes
  /ingest or asks to process a local source into canonical wiki pages.
---

# Bob Ingest

Read [`../../../.bob/commands/ingest.md`](../../../.bob/commands/ingest.md) completely and follow it together with the repository `AGENTS.md`.

Use `python tools/bob_runner.py ingest --source <file>` from the repository root for scaffolding. Add `--max-chunks N` only when requested or needed to bound a large extraction pass.

Treat the runner output as scaffolding: read chunk text in `index/extractions/[source-id]/`, replace excerpt-based summaries with analysis, and keep source pages free of per-page Source Map ledgers and keyword candidate lists. Present key takeaways and obtain user confirmation before creating or updating canonical entity and concept pages. Never write to `raw/`.

After confirmation, maintain provenance, bidirectional links, generated indices, and the substantive ingest log entry. If the runner exhibits a genuine defect, stop and follow `AGENTS.md` section 12 before reading or changing the runner.
