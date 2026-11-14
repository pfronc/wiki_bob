---
name: rag
description: Paragraph-level retrieval over derived store (procedure pointer)
metadata:
  user-invocable: true
  disable-model-invocation: true
---

# Command: rag

Canonical procedure: .bob/commands/rag.md - follow it verbatim.
Contract: AGENTS.md sections 2, 5.4, 11.

Boundary: index/rag is deletable cache, never canonical. Refresh via CLI after edits; MCP is read-only retrieval only. Retrieval is evidence, not an answer.
