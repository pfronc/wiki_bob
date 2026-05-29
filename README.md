# WIKI Knowledge Base System

A structured knowledge management system for ingesting, organizing, and querying information from various sources using AI-powered workflows.

## Overview

This WIKI system transforms raw source documents into an interconnected knowledge base of entities, concepts, and insights. It maintains bidirectional cross-references, tracks provenance, and enables powerful querying capabilities.

## Directory Structure

```
/
├── raw/              # Source documents (User-managed)
│   └── [your-sources.pdf, .md, .txt, etc.]
├── wiki/             # Knowledge Pages (AI-managed)
│   ├── entities/     # People, organizations, products
│   ├── concepts/     # Ideas, theories, methodologies
│   ├── sources/      # Source summaries with metadata
│   └── analyses/     # Preserved query results
├── index/            # Navigation indices (AI-managed)
│   └── index_001.md
├── log.md            # Operation history
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

Use the `/ingest` command in your AI assistant:

```
/ingest interesting-article.pdf
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
/query What are the main differences between GPT and Claude?
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
/ingest attention-is-all-you-need.pdf
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
/query How does gradient descent work in neural networks?
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

**Examples**: `openai.md`, `geoffrey-hinton.md`, `gpt-4.md`

**Contains**:
- Type (Person, Organization, Product, Location)
- Summary
- Key information
- Mentions in sources
- Related concepts and entities

### Concept Pages
**Location**: `wiki/concepts/`

**Examples**: `machine-learning.md`, `gradient-descent.md`

**Contains**:
- Definition
- Detailed explanation
- Key aspects
- Applications
- Related entities and concepts
- Sources

### Source Pages
**Location**: `wiki/sources/`

**Examples**: `attention-is-all-you-need.md`

**Contains**:
- Metadata (type, date, author)
- Summary
- Key takeaways
- Entities and concepts mentioned
- Notable quotes

### Analysis Pages
**Location**: `wiki/analyses/`

**Examples**: `comparison-gpt-vs-claude.md`

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
Start with `index/index_001.md` to browse:
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
2. **Review takeaways**: Provide feedback during ingest to guide Page creation
3. **Ask specific queries**: More specific questions yield better answers
4. **Run monthly lints**: Keep the wiki healthy with regular checks

### For AI Agents

1. **Read efficiently**: Batch file reads (up to 5 at once)
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
- PDF documents
- Markdown files (.md)
- Text files (.txt)
- DOCX documents

### Token Limits
- Index files: 10,000 tokens (auto-split)
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
- System auto-splits at 10,000 tokens
- Navigate between indices using Previous/Next links

## Advanced Usage

### Creating Custom Analyses
Request specific comparisons or deep dives:
```
/query Compare the approaches to attention mechanisms in Transformer vs LSTM architectures
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

## Contributing

This is a personal knowledge base system. To extend functionality:

1. Review `AGENTS.md` for operational procedures
2. Modify `.bob/custom_modes.yaml` for new workflows
3. Update this README when adding features

## Version History

- **2026-05-24**: Initial system setup with ingest and query modes
- See `log.md` for detailed operation history

## License

Personal knowledge management system. Not for redistribution.

---

*For detailed operational procedures, see [AGENTS.md](AGENTS.md)*