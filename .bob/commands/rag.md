# Command: rag

Usage: `/rag [index|search|ask|stats] [question]`

Purpose: Use the local retrieval store (derived state in `index/rag/`) to find paragraph-level passages in wiki pages and ingested raw-source chunks, and optionally to generate a grounded answer with a local Ollama model.

`/rag` complements `/query`: `bob query` ranks one-line index summaries, while `/rag` retrieves paragraph-level passages with stable citations such as `wiki/concepts/qubit.md §Definition` or `index/extractions/...json p. 42 [src_...:p042:c03]`.

Inputs:
- `index` — refresh the derived store after ingesting sources or editing pages
- `search` — retrieve ranked passages (the default action when a question is supplied)
- `ask` — generate an answer grounded in retrieved passages, using a local model
- `stats` — report store contents, drift against the current files, and local model availability

Procedure:
1. Confirm the store exists and is current:

   ```bash
   python3 tools/rag.py stats
   ```

   If it is missing, or if drift is reported, refresh it first:

   ```bash
   python3 tools/rag.py index --scope all
   ```

2. Retrieve passages:

   ```bash
   python3 tools/rag.py search --query "<question>" --top-k 8 --json
   ```

   The JSON payload contains `citation`, `path`, `corpus`, `locator`, `chunk_id`, `source_id`, `page`, `score`, `bm25_rank`, `vector_rank`, `snippet`, and `text`. Hybrid ranking merges BM25 and local embeddings; when Ollama is unreachable the tool degrades to BM25 and says so in `note`.
3. Read the highest-ranked passages and follow `path`/`chunk_id` back into `wiki/` or `index/extractions/` when more context is needed. Retrieval results are evidence, not an answer.
4. Synthesize the answer as in `/query` (direct answer, comparison, or structured sections) and cite every claim:
   - wiki page: `[Quantum Gates](../wiki/concepts/quantum-gates.md)` with the section locator from `citation`
   - raw chunk: `Claim. Citation: [Source Title](../wiki/sources/source-title.md), p. 42.` plus the stable chunk ID `src_...:p042:c03`
5. Optional fully local generation:

   ```bash
   python3 tools/rag.py ask --question "<question>" --top-k 6 --model gemma4:12b
   ```

   Verify every citation in the model's output against the retrieved passages before quoting it; a local model can still miscite or overreach.
6. Choose the lower-friction surface for the retrieval calls above:
   - **MCP (preferred for read-only retrieval when the client exposes it):** call `wiki_search`, `wiki_ask`, and `wiki_stats` directly instead of invoking the CLI. One call each, no shell round-trip or JSON parsing, and `wiki_search` and `wiki_stats` are auto-approved.
   - **CLI (always valid):** use the `python3 tools/rag.py …` commands above when no MCP client is connected, when you need the `--json` fields (`path`, `chunk_id`, `locator`, `score`, `bm25_rank`, `vector_rank`) for precise citations, or for deterministic/scripted use.
   - Refreshing the store is **CLI-only**: the MCP tools cannot run `index`, so `python3 tools/rag.py index --scope all` (step 1) remains mandatory after ingesting sources or editing pages.
7. Preserve the answer as an analysis page only when the `/query` preservation criteria apply; update the index and the log when you do.

Boundaries:
- `index/rag/rag.sqlite3` is a cache. It may be deleted and rebuilt at any time; the canonical layers stay `wiki/` Markdown, `index/source-registry.json`, and the numbered indices.
- The tool never writes to `raw/` or `wiki/`. `index` appends a `rag` log entry only when the store actually changes.
- `ask` sends retrieved passages only to the local Ollama server, never to a remote provider.

Quality checklist:
- `stats` reports no drift before retrieval is relied upon.
- Every claim in a synthesized or generated answer carries a resolvable citation.
- Raw-chunk citations include the page or section locator and the stable chunk ID.
- No citation is invented or paraphrased from memory.

Log template for store refreshes (written automatically by the tool):

```markdown
## [YYYY-MM-DD HH:MM] rag | Local retrieval index update (all)

Refreshed the derived local-RAG store that backs retrieval for the agent, the CLI, and the MCP server. Canonical layers are unchanged.

Pages affected:
- [index/rag/rag.sqlite3](index/rag/rag.sqlite3)

Key outcomes:
- Indexed N retrieval chunks from M file(s)
- Skipped N unchanged file(s); pruned N stale record(s)
- Stored N vectors using embeddinggemma (768 dims)
```