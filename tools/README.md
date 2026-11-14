# Bob tools

Short instructions to use the `tools` helper scripts.

1. Make wrapper executable:

```bash
chmod +x tools/bob
```

2. Add `tools/` to your PATH for the current shell session:

```bash
export PATH="$PWD/tools:$PATH"
```

You can add that line to your shell rc (e.g., `~/.zshrc`) to persist it.

3. Examples:

```bash
# run ingest
bob ingest --source example.md

# bounded first pass; repeat without the limit to resume and finish
bob ingest --source textbook.pdf --max-chunks 25

# run query
bob query --question "What is transformer architecture?"

# research (agent-driven - prints procedure path, no scaffolding)
bob research
```

4. The command procedures are documented in `.bob/commands/`. The runner
   provides deterministic scaffolding, indexing, candidate retrieval, and
   structural checks; consult `AGENTS.md` for the authoritative responsibility
   and precedence rules.

5. Run the deterministic command tests from the repository root:

```bash
python -m unittest discover -s tools/tests -v
```

The suite uses temporary repositories and does not modify the working wiki.

6. Source lifecycle state is stored in `index/source-registry.json`. The
   `status`, `raw-list`, and `ingest` commands reconcile this manifest using
   SHA-256 hashes; filenames are not used to infer whether a source was
   ingested.

7. Install `requirements.txt` to enable dedicated PDF (`pypdf`) and DOCX
   (`python-docx`) extraction. Versioned chunk records are written beneath
   `index/extractions/`; `raw/` remains read-only.

8. `create-page` emits the complete Phase 4 schema for every page type.
   Entity/concept creation checks canonical titles and aliases; `lint` validates
   required sections, provenance links and source IDs, duplicate identities,
   and malformed links.

9. Managed pages also emit the Phase 5 Obsidian Properties contract. Native
   Bases are stored in `wiki/bases/` and curated maps in `wiki/maps/`; neither
   is required by the runner, and user workspace/theme/bookmark state is left
   untouched.

10. `index-update` deterministically regenerates all `index_XXX.md` parts and
    `index/index.md`, splitting near 9,000 estimated tokens. `query` searches
    every part, validates targets, deduplicates results, and ranks candidates;
    synthesis remains the agent's responsibility.

11. `lint` is a read-only Phase 7 health report. It emits counts and paths for
    links, schema/timestamps, index coverage/order, orphans, one-way
    relationships, duplicate identities, citation provenance, table-cell math
    pipes, raw hash drift, oversized files, and pending extraction chunks.
    Findings do not mutate data or fail the command; missing prerequisites do.

12. `rag.py` is separate, stdlib-only retrieval tooling (not part of the runner
    and not covered by the runner-bug protocol). It indexes managed wiki pages
    plus the stable chunks in `index/extractions/` into the derived store
    `index/rag/rag.sqlite3`, then serves hybrid BM25 + local-embedding search
    with citations, and optional local generation via Ollama.

    ```bash
    ollama pull embeddinggemma                 # one-time local embeddings
    bob-rag index --scope all                  # or: python3 tools/rag.py index
    bob-rag search --query "no-cloning" --json
    bob-rag ask --question "What is a qubit?" --model gemma4:12b
    bob-rag stats
    ```

    Embeddings are optional: without Ollama the tool degrades to BM25. `rag.py`
    writes only under `index/rag/` (plus a `rag` log entry when the store
    changes), and its tests live in `tools/tests/test_rag.py`. `rag_mcp.py`
    exposes `wiki_search`, `wiki_ask`, and `wiki_stats` over MCP stdio for
    agents that cannot shell out. The procedure is documented in
    `.bob/commands/rag.md`. How the hybrid BM25 + embeddinggemma + RRF
    ranking works is explained in `tools/hybrid-retrieval.md`.

13. `convert.py` stages formats the runner cannot read (pptx, xlsx, html,
    epub, ipynb, csv, json, xml, and more) into Markdown via markitdown.
    PDF stays with the runner so `p. N` page locators survive for citations;
    output goes to `index/converted/` because `raw/` is user-managed, then
    you move it and run `bob ingest --source <file>.md`. Its tests live in
    `tools/tests/test_rag.py` alongside the RAG suite (`ConvertTestCase`).
