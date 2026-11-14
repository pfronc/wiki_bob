# WIKI System - Agent Operations Manual

## 1. System Overview

### 1.1 Role Definition
- **User**: Curator of source materials, query initiator, workflow supervisor
- **Agent**: AI librarian managing wiki content, maintaining consistency, answering queries. Agents should respond in English for all user-facing text unless the user explicitly requests another language.

### 1.2 Directory Structure

```
/
├── raw/              # Source documents (User-managed only)
├── staging/          # Pre-ingest working area (User-managed)
├── work/             # Scratch notebooks and experiments (User-managed)
├── docs/             # Supplementary reference documents (User-managed)
├── wiki/             # Knowledge Pages (Agent-managed)
│   ├── entities/         # People, organizations, products
│   ├── concepts/         # Ideas, theories, methodologies
│   ├── sources/          # Source summaries with metadata
│   ├── analyses/         # Query results worth preserving
│   ├── notes/            # Informal or in-progress notes
│   ├── bases/            # Obsidian native bases
│   └── maps/             # Curated concept maps
├── index/            # Navigation indices and derived stores (Agent-managed)
│   ├── index.md          # Master index (auto-generated)
│   ├── index_001.md      # Paginated index parts
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
└── README.md         # Project overview
```

#### Ownership Rules
- **raw/**: User exclusively (Agent: read-only)
- **staging/**: User exclusively (Agent: read-only)
- **work/**: User exclusively (Agent: read-only)
- **docs/**: User exclusively (Agent: read-only)
- **wiki/**: Agent exclusively (User: read-only)
- **index/**: Agent exclusively (User: read-only)
- **log.md**: Agent maintains (User: read-only)

### 1.3 Automation Tools

Bob uses [`tools/bob_runner.py`](tools/bob_runner.py) via the [`tools/bob`](tools/bob) shell wrapper for standardized operations to ensure consistency and reduce token usage. Add `tools/` to your PATH (see [`tools/README.md`](tools/README.md)) to call commands as `bob <command>`.

**Available Commands**:
```bash
# Ingest - Create source page from raw/ file
bob ingest --source example.md

# Query - Search index for keywords
bob query --question "What is X?"

# Create-page - Generate page from template
bob create-page --type concept --title "My Concept" --filename my-concept.md
# Types: entity, concept, source, analysis

# Lint - Check wiki health
bob lint

# Index-update - Regenerate all index parts
bob index-update

# RAG - Index and search wiki content
bob-rag index --scope all
bob-rag search --query "keyword"
```

**What bob_runner.py Does**:
- Creates pages using standard templates
- Applies kebab-case naming automatically
- Regenerates `index/index.md` and `index/index_XXX.md` parts
- Appends standardized entries to `log.md`
- Handles duplicate filenames (adds timestamp suffix)
- Tracks source lifecycle state via `index/source-registry.json` (SHA-256 hashes)
- Writes chunk records under `index/extractions/`

**Bob's Usage Pattern**:
1. Execute automation for structure/boilerplate
2. Read created file
3. Enrich with analysis and cross-references
4. Update related pages with bidirectional links

**Benefits**:
- **Consistency**: Uniform formatting, naming, timestamps
- **Efficiency**: Saves tokens for intelligence, not boilerplate
- **Reliability**: Tested code handles edge cases
- **Speed**: File operations execute instantly


---

## 2. Core Operations (High-Level)

### 2.1 INGEST
**Purpose**: Process new source from `raw/` into wiki Pages

**Command**: `/ingest [source-file]` → See `.bob/commands/ingest.md` for detailed procedure

**Key principle**: Read source → Discuss takeaways with User → Create/update Pages → Update index → Log

### 2.2 QUERY
**Purpose**: Answer questions using wiki content, optionally preserve valuable answers

**Command**: `/query [question]` → See `.bob/commands/query.md` for detailed procedure

**Preservation criteria**: Synthesizes 3+ Pages, reveals connections, comparison, or User requests

### 2.3 LINT
**Purpose**: Health-check wiki for contradictions, orphans, missing concepts, broken links

**Command**: `/lint` → See `.bob/commands/lint.md` for detailed procedure

**Frequency**: Monthly recommended

### 2.4 CREATE-PAGE
**Purpose**: Create new wiki page with proper template and cross-references

**Command**: `/create-page [type]` → See `.bob/commands/create-page.md` for detailed procedure

**Types**: entity, concept, source, analysis

### 2.5 INDEX-UPDATE
**Purpose**: Maintain index files, ensure completeness, handle splitting

**Command**: `/index-update` → See `.bob/commands/index-update.md` for detailed procedure

**When**: After bulk changes or monthly verification

---

## 3. Page Standards

### 3.1 Naming Convention
- Use `kebab-case-descriptive-name.md`
- Be specific and descriptive
- Use lowercase only
- Avoid special characters

**Examples**:
- `some-person.md`, `some-organization.md` (entities)
- `some-theory.md`, `some-method.md` (concepts)
- `author-year-title.md` (sources)
- `comparison-topic-a-vs-b.md` (analyses)

### 3.2 Required Elements (All Pages)
- [ ] Title (# heading)
- [ ] Summary paragraph
- [ ] Main content sections
- [ ] Cross-references section (## Related Pages)
- [ ] Sources section (## Sources)
- [ ] Last updated timestamp

### 3.3 Page Templates

**Note**: Full templates are defined in `.bob/commands/create-page.md`. Key requirements:
- Entity pages: Type, first mention, key information, mentions in sources
- Concept pages: Category, definition, explanation, applications, external references
- Source pages: Type, date, author, summary, takeaways, entities/concepts mentioned
- Analysis pages: Type, date, origin, question, answer, sources consulted, insights

---

## 4. Cross-Reference Guidelines

### 4.1 When to Link (Always Bidirectional)
- Entity mentioned in concept → link both ways
- Source discusses entity/concept → link both ways
- Concepts that build on each other → link both ways
- Contradicting or complementary sources → link both ways

### 4.2 Link Format
`[Display Text](relative/path/to/page.md)`

**Example**:
```markdown
## Related Pages
- [Some Concept](../concepts/some-concept.md) - Relationship context here
```

### 4.3 Link Maintenance
During updates:
- Verify all links still valid
- Add new relevant links discovered
- Remove links to deleted Pages
- Update link context if relationship changed

---

## 5. Index Management

### 5.1 Index File Structure

**Filename**: `index_001.md`, `index_002.md`, etc.

**Token limit**: 10000 tokens per file

**Format**:
```markdown
# Wiki Index [001]

Last updated: YYYY-MM-DD
Total Pages: XXX
Token count: ~XXXX

## Entities
- [Entity Name](wiki/entities/entity-name.md) - One-line description [sources: X]

## Concepts
- [Concept Name](wiki/concepts/concept-name.md) - One-line description [sources: X]

## Sources
- [Source Title](wiki/sources/source-title.md) - Date, type [entities: X, concepts: Y]

## Analyses
- [Analysis Title](wiki/analyses/analysis-title.md) - Date, query summary
```

### 5.2 Index Splitting Rules

**When**: Current index exceeds 10000 tokens

**How**:
1. Create `index_XXX+1.md`
2. Move newest ~2000 tokens to new index
3. Keep ~8000 tokens in old index
4. Add navigation links:
   ```markdown
   Previous: [index_001.md](index_001.md)
   Next: [index_003.md](index_003.md)
   ```

### 5.3 Update Frequency
- After every ingest
- After query preservation
- After lint fixes
- Monthly verification

---

## 6. Log Management

### 6.1 Log Format

**File**: `log.md` (append-only, chronological)

**Entry template**:
```markdown
## [YYYY-MM-DD HH:MM] operation_type | Title

Brief description of what happened.

Pages affected:
- [Page 1](link)
- [Page 2](link)

Key outcomes:
- Outcome 1
- Outcome 2
```

**Operation types**: `ingest`, `query`, `lint`, `fix`, `reorg`

### 6.2 Log Parsing Examples

```bash
# Last 5 operations
grep "^## \[" log.md | tail -5

# All ingests this month
grep "^## \[$(date +%Y-%m)" log.md | grep "ingest"

# Pages modified today
grep "^## \[$(date +%Y-%m-%d)" log.md -A 10 | grep "wiki/"
```

---

## 7. Quality Checklists

### 7.1 Page Quality
Before finalizing any Page:
- [ ] Title is clear and descriptive
- [ ] Summary paragraph exists
- [ ] All sections have content
- [ ] At least 2 cross-references (unless isolated)
- [ ] At least 1 source citation
- [ ] Last updated timestamp present
- [ ] Markdown formatting correct
- [ ] Links use relative paths
- [ ] No typos in key terms

### 7.2 Index Quality
Before updating index:
- [ ] All new Pages added
- [ ] One-line descriptions accurate
- [ ] Metadata included (source count, date)
- [ ] Alphabetical order within categories
- [ ] Token count noted
- [ ] Navigation links present (if multiple indices)

### 7.3 Log Quality
Before appending to log:
- [ ] Date in ISO format [YYYY-MM-DD]
- [ ] Operation type specified
- [ ] Title/description clear
- [ ] Affected Pages listed with links
- [ ] Key outcomes summarized

---

## 8. Decision Trees

### 8.1 Should I Create a New Page?

```
Is this a distinct entity/concept?
├─ Yes → Does a Page already exist?
│  ├─ Yes → Update existing Page
│  └─ No → Create new Page
└─ No → Add to existing related Page
```

### 8.2 Should I Preserve This Query Answer?

```
Did I synthesize info from 3+ Pages?
├─ Yes → Create analysis Page
└─ No → Is this a comparison/novel insight?
   ├─ Yes → Create analysis Page
   └─ No → Did User request preservation?
      ├─ Yes → Create analysis Page
      └─ No → Answer only, don't preserve
```

### 8.3 Should I Split the Index?

```
Current index token count > 10000?
├─ Yes → Create new index file
│  └─ Move newest ~2000 tokens to new file
└─ No → Continue using current index
```

---

## 9. Performance Guidelines

### 9.1 Reading Strategy

**For queries**:
1. Read index first (lightweight)
2. Identify 5-10 candidate Pages
3. Read candidates in single batch
4. Follow cross-references only if needed

**For ingests**:
1. Read source once completely
2. Identify all affected Pages
3. Read affected Pages in single batch
4. Update all Pages
5. Update index once at end

### 9.2 Token Management

**Monitor**:
- Index file sizes (split at 10000)
- Individual Page sizes (warn if >5000)
- Total wiki size (report monthly)

**Optimize**:
- Use concise summaries
- Link instead of repeating
- Archive old analyses if rarely accessed

---

## 10. Maintenance Schedule

### 10.1 After Every Ingest
- [ ] Update affected Pages
- [ ] Update index
- [ ] Append to log
- [ ] Verify cross-references

### 10.2 Weekly
- [ ] Review log for patterns
- [ ] Check index token counts

### 10.3 Monthly
- [ ] Run full lint
- [ ] Review orphan Pages
- [ ] Check for missing concepts
- [ ] Report wiki statistics

### 10.4 Quarterly
- [ ] Deep review of Page quality
- [ ] Reorganize if needed
- [ ] Archive obsolete content
- [ ] Update this manual if workflows changed

---

## 11. Slash Commands Reference

Bob executes operations using the [`tools/bob`](tools/bob) wrapper (backed by [`tools/bob_runner.py`](tools/bob_runner.py)) for standardization. Each command has a corresponding procedure file in `.bob/commands/`.

### Command Reference Table

| Slash Command | Automation Command | Procedure File |
|--------------|-------------------|----------------|
| `/ingest [file]` | `bob ingest --source [file]` | `.bob/commands/ingest.md` |
| `/query [question]` | `bob query --question "[question]"` | `.bob/commands/query.md` |
| `/create-page [type]` | `bob create-page --type [type] --title "[title]" --filename [name].md` | `.bob/commands/create-page.md` |
| `/lint` | `bob lint` | `.bob/commands/lint.md` |
| `/index-update` | `bob index-update` | `.bob/commands/index-update.md` |
| `/rag` | `bob-rag index --scope all` then `bob-rag search --query "…"` | `.bob/commands/rag.md` |
| `/research` | *(agent-driven, no scaffolding)* | `.bob/commands/research.md` |

### Execution Pattern

1. **User invokes**: `/ingest document.md`
2. **Bob executes automation**: `bob ingest --source document.md`
3. **Bob follows procedure**: Reads `.bob/commands/ingest.md` for enrichment steps
4. **Bob adds intelligence**: Analysis, cross-references, relationships

**Key principle**: Automation creates structure → Bob adds intelligence

---

*This manual is a living document. Update it when workflows evolve.*