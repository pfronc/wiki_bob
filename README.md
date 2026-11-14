# WIKI Knowledge Base System

A structured knowledge management system for ingesting, organizing, and querying information from various sources using AI-powered workflows.

## Overview

This WIKI system transforms raw source documents into an interconnected knowledge base of entities, concepts, and insights. It maintains bidirectional cross-references, tracks provenance, and enables powerful querying capabilities.

## Setup

### Prerequisites

| Requirement | Purpose | Required? |
|-------------|---------|-----------|
| Python ≥ 3.10 | Runner, RAG, convert tools | **Yes** |
| [Ollama](https://ollama.com) | Local embedding model (RAG) and optional local LLM | **Yes** (for RAG) |
| `embeddinggemma` Ollama model | Sentence embeddings for hybrid BM25+vector retrieval | **Yes** (for RAG) |
| A chat model (e.g. `gemma4:12b`) | Local answer generation (`bob-rag ask`, Obsidian wiki-agent) | Optional |

### 1. Clone or copy the repository

```bash
cp -r wiki_bob_v3/ my-wiki/
cd my-wiki/
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

For PDF and DOCX extraction support (strongly recommended):

```bash
pip install pypdf python-docx
```

For non-text format conversion (`.pptx`, `.xlsx`, `.epub`, `.ipynb`, etc.):

```bash
pip install markitdown
```

### 3. Make the CLI wrapper executable and add it to your PATH

```bash
chmod +x tools/bob tools/bob-rag
export PATH="$PWD/tools:$PATH"   # add to ~/.zshrc or ~/.bashrc to persist
```

Verify:

```bash
bob --help
```

### 4. Install Ollama and pull models

Install Ollama from [https://ollama.com](https://ollama.com), then pull the required embedding model and your preferred chat model:

```bash
# Required: embedding model used by the RAG store
ollama pull embeddinggemma

# Optional: local LLM for `bob-rag ask` and the Obsidian wiki-agent plugin
ollama pull gemma4:12b        # or any model Ollama supports
```

> **Without Ollama**: the RAG tool (`bob-rag`) degrades gracefully to BM25-only search. All other runner commands (`bob ingest`, `bob query`, `bob lint`, etc.) work without Ollama.

### 5. Build the RAG index (optional, requires Ollama)

After ingesting at least one source, build the local retrieval store:

```bash
bob-rag index --scope all
bob-rag stats        # verify contents and embedding coverage
```

### 6. Open in Obsidian (optional)

The `wiki/` folder is a self-contained Obsidian vault. Open it directly:

1. Open Obsidian → **Open folder as vault** → select `wiki/`
2. Enable community plugins when prompted (required for the wiki-agent plugin)
3. The **Wiki Agent** plugin (`.obsidian/plugins/wiki-agent/`) lets you query wiki content via a local Ollama model directly from Obsidian — configure the endpoint and model in its settings panel (default: `http://localhost:11434`, model `gemma4:12b`)

> The Obsidian vault is an **alternative reading and querying environment**. All canonical write operations (ingest, create-page, lint, index-update) must still go through the `bob` CLI or Bob AI agent — the Obsidian plugin is read-only.

---

## Directory Structure

```
/
├── raw/              # Source documents (User-managed, read-only for agent)
├── staging/          # Pre-ingest working area (User-managed)
├── work/             # Scratch notebooks and experiments (User-managed)
├── docs/             # Supplementary reference documents (User-managed)
├── wiki/             # Knowledge Pages (Agent-managed)
│   ├── entities/         # People, organizations, products
│   ├── concepts/         # Ideas, theories, methodologies
│   ├── sources/          # Source summaries with metadata
│   ├── analyses/         # Preserved query results
│   ├── notes/            # Informal or in-progress notes
│   ├── bases/            # Obsidian native bases
│   └── maps/             # Curated concept maps
├── index/            # Navigation indices and derived stores (Agent-managed)
│   ├── index.md          # Master index (auto-generated)
│   ├── index_001.md      # Paginated index parts (auto-split at ~9k tokens)
│   ├── source-registry.json  # Source lifecycle manifest (SHA-256 based)
│   ├── extractions/      # Versioned chunk records per source
│   ├── converted/        # Markdown conversions from non-text formats
│   └── rag/              # RAG SQLite store (derived, do not edit)
├── tools/            # Runner scripts and helpers
│   ├── bob              # Shell wrapper (add tools/ to PATH)
│   ├── bob-rag          # Shell wrapper for RAG tool
│   ├── bob_runner.py    # Core runner
│   ├── rag.py           # Hybrid BM25 + embedding retrieval
│   ├── rag_mcp.py       # MCP stdio interface for RAG
│   ├── convert.py       # Format converter (pptx, xlsx, epub, ipynb, …)
│   └── tests/           # Deterministic test suite
├── log.md            # Operation history (Agent-maintained)
├── AGENTS.md         # Agent operations manual
└── README.md         # This file
```

## Quick Start

### 1. Add a Source Document

Place your document in the `raw/` directory:

```bash
cp ~/Downloads/interesting-article.pdf raw/
```

### 2. Ingest the Source

Use the `/ingest` command in your AI assistant (or directly via the shell):

```bash
bob ingest --source interesting-article.pdf
```

The system will:
- Extract key information
- Discuss takeaways with you
- Create/update relevant Pages
- Update the index
- Log the operation

### 3. Query the Knowledge Base

Ask questions using the `/query` command:

```
/query What are the main themes across ingested sources?
```

The system will:
- Search the index
- Read relevant Pages
- Synthesize an answer with citations
- Optionally preserve valuable insights

## Core Operations

### INGEST
**Purpose**: Process new sources into structured wiki Pages

**Command**: `/ingest [source-file]`

**What it does**:
- Reads source from `raw/`
- Extracts entities, concepts, and insights
- Creates/updates wiki Pages
- Maintains cross-references
- Updates index and log

**Example**:
```
/ingest my-document.pdf
```

### QUERY
**Purpose**: Answer questions using wiki content

**Command**: `/query [question]`

**What it does**:
- Searches index for relevant Pages
- Synthesizes information from multiple sources
- Provides citations
- Preserves valuable analyses

**Example**:
```
/query How do concepts A and B relate to each other?
```

### LINT
**Purpose**: Health-check the wiki for issues

**Command**: `/lint`

**What it does**:
- Identifies broken links
- Finds orphaned Pages
- Detects missing concepts
- Reports contradictions

**Frequency**: Monthly recommended

## Page Types

### Entity Pages
**Location**: `wiki/entities/`

**Examples**: `some-person.md`, `some-organization.md`

**Contains**:
- Type (Person, Organization, Product, Location)
- Summary
- Key information
- Mentions in sources
- Related concepts and entities

### Concept Pages
**Location**: `wiki/concepts/`

**Examples**: `some-theory.md`, `some-method.md`

**Contains**:
- Definition
- Detailed explanation
- Key aspects
- Applications
- Related entities and concepts
- Sources

### Source Pages
**Location**: `wiki/sources/`

**Examples**: `author-year-title.md`

**Contains**:
- Metadata (type, date, author)
- Summary
- Key takeaways
- Entities and concepts mentioned
- Notable quotes

### Analysis Pages
**Location**: `wiki/analyses/`

**Examples**: `comparison-topic-a-vs-b.md`

**Contains**:
- Original question
- Comprehensive answer
- Sources consulted
- Key insights

## Key Features

### Bidirectional Cross-References
Every link is maintained in both directions. If Page A links to Page B, Page B also links back to Page A with context.

### Provenance Tracking
Every piece of information is traced back to its source document in `raw/`.

### Incremental Updates
New sources enhance existing Pages rather than duplicating information.

### Token-Aware Indexing
Indices automatically split when they exceed 10,000 tokens for optimal performance.

### Comprehensive Logging
All operations are logged with timestamps, affected Pages, and outcomes.

## Navigation

### Using the Index
Start with `index/index.md` (master) or `index/index_001.md` to browse:
- All entities alphabetically
- All concepts by category
- All sources chronologically
- All analyses by date

### Following Cross-References
Each Page includes a "Related Pages" section with contextual links to connected content.

### Searching the Log
Use `log.md` to track:
- When sources were ingested
- What Pages were created/updated
- Query history
- System maintenance

## Best Practices

### For Users

1. **Organize raw sources**: Use descriptive filenames in `raw/`
2. **Stage pre-processed files**: Place converted/work-in-progress materials in `staging/`
3. **Review takeaways**: Provide feedback during ingest to guide Page creation
4. **Ask specific queries**: More specific questions yield better answers
5. **Run monthly lints**: Keep the wiki healthy with regular checks

### For AI Agents

1. **Read efficiently**: Batch file reads
2. **Maintain bidirectionality**: Always update both sides of links
3. **Use relative paths**: All links must be relative to workspace root
4. **Log everything**: Append to log.md after every operation
5. **Check quality**: Use checklists before finalizing Pages

## File Ownership

| Directory | Owner | Access |
|-----------|-------|--------|
| `raw/` | User | User: write, Agent: read |
| `wiki/` | Agent | User: read, Agent: write |
| `index/` | Agent | User: read, Agent: write |
| `log.md` | Agent | User: read, Agent: write |

**Important**: Users should never manually edit `wiki/`, `index/`, or `log.md`. All modifications should go through AI operations.

## Maintenance

### Weekly
- Review log for patterns
- Check index token counts

### Monthly
- Run `/lint` for health check
- Review orphan Pages
- Check for missing concepts

### Quarterly
- Deep review of Page quality
- Archive obsolete content
- Update workflows if needed

## Technical Details

### Supported Source Formats
Natively by the runner:
- PDF documents
- Markdown files (`.md`)
- Text files (`.txt`)
- DOCX documents

Via `convert.py` (outputs to `index/converted/`):
- PowerPoint (`.pptx`), Excel (`.xlsx`)
- HTML, EPUB, CSV, JSON, XML
- Jupyter Notebooks (`.ipynb`)
- And more (via markitdown)

### Token Limits
- Index files: ~9,000 tokens (auto-split by `index-update`)
- Individual Pages: 5,000 tokens (warning threshold)

### Link Format
All internal links use relative paths:
```markdown
[Display Text](../concepts/concept-name.md)
```

### Naming Convention
All filenames use `kebab-case-descriptive-name.md`:
- Lowercase only
- Hyphens for spaces
- Descriptive and specific
- No special characters

## Troubleshooting

### "Page not found" errors
- Check if Page exists in correct directory
- Verify link uses relative path
- Run `/lint` to find broken links

### Duplicate content
- Search index before creating new Pages
- Update existing Pages instead of creating duplicates
- Use cross-references to avoid repetition

### Index too large
- System auto-splits near 9,000 tokens via `bob index-update`
- Navigate between parts using Previous/Next links in each index file

### Non-text source formats
- Run `python3 tools/convert.py` on the file first
- Move the resulting `.md` from `index/converted/` to `raw/`
- Then run `bob ingest --source <file>.md`

## Advanced Usage

### Creating Custom Analyses
Request specific comparisons or deep dives:
```
/query Compare the approaches used in source A vs source B
```

### Bulk Ingestion
Process multiple sources sequentially:
```
/ingest source1.pdf
/ingest source2.md
/ingest source3.txt
```

### Manual Page Creation
Create Pages outside normal workflow:
```
/create-page entity
```

### RAG Search
Index wiki content and run hybrid retrieval:
```bash
bob-rag index --scope all
bob-rag search --query "keyword" --json
bob-rag ask --question "What is X?"
```

## Contributing

This is a personal knowledge base system. To extend functionality:

1. Review `AGENTS.md` for operational procedures
2. Modify `.bob/custom_modes.yaml` for new workflows
3. Update this README when adding features

## Version History

- See `log.md` for the full operation history

---

*For detailed operational procedures, see [AGENTS.md](AGENTS.md)*