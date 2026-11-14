---
name: bob-rag
description: >-
  Retrieve paragraph-level passages from the Bob wiki with hybrid local search
  when the user invokes /rag, or when wiki pages and ingested raw sources must
  be searched semantically with page- and chunk-level citations.
---

# Bob RAG

Read [`../../../.bob/commands/rag.md`](../../../.bob/commands/rag.md) completely and follow it together with the repository `AGENTS.md`.

Retrieve paragraph-level passages (citations such as `wiki/concepts/qubit.md §Definition` or `index/extractions/....json p. 42 [src_...:p042:c03]`) through whichever surface this session exposes, preferring the lower-friction one:

- **MCP `wiki_search` when available — preferred for read-only retrieval.** One call, no shell round-trip or JSON parsing, and it is auto-approved. Use `wiki_search` for passages and `wiki_stats` for store health; `wiki_ask` only for optional local generation (not auto-approved).
- **CLI `python3 tools/rag.py search --query "<question>" --top-k 8 --json`** when no MCP client is connected, when you need the structured `--json` fields (`path`, `chunk_id`, `locator`, `score`, `bm25_rank`, `vector_rank`) for precise citation assembly, or for deterministic/scripted use.

Whichever surface you use, establish freshness first: `wiki_stats` (MCP) or `python3 tools/rag.py stats` reports drift, and `python3 tools/rag.py index --scope all` — **CLI only; MCP cannot refresh** — rebuilds the store after ingesting sources or editing pages. Refresh is incremental: unchanged files are skipped.

Retrieval output is evidence, not an answer. Read the cited pages and synthesize the response yourself with resolvable citations, and never invent page numbers or chunk IDs. `index/rag/` is derived state; `wiki/` Markdown, `index/source-registry.json`, and the numbered indices remain canonical. Never write to `raw/`.

The `ask` path generates locally with Ollama and is optional; verify its citations against the retrieved passages before quoting them. Defects in `tools/rag.py` or `tools/rag_mcp.py` are normal editing work — `AGENTS.md` section 12 applies only to `tools/bob_runner.py`.