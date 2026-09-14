# WIKI System - Agent Operations Manual

## 1. System Overview

### 1.1 Role Definition
- **User**: Curator of source materials, query initiator, workflow supervisor
- **Agent**: AI librarian managing wiki content, maintaining consistency, answering queries. Agents should respond in English for all user-facing text unless the user explicitly requests another language.

### 1.2 Directory Structure

```
/
├── raw/          # Source documents (User-managed only)
├── wiki/         # Knowledge Pages (Agent-managed)
│   ├── entities/     # People, organizations, products
│   ├── concepts/     # Ideas, theories, methodologies
│   ├── sources/      # Source summaries with metadata
│   └── analyses/     # Query results worth preserving
├── index/        # Navigation indices (Agent-managed)
└── log.md        # Operation history (Agent-maintained)
```

#### Ownership Rules
- **raw/**: User exclusively (Agent: read-only — never write here)
- **wiki/**: Agent exclusively (User: read-only)
- **index/**: Agent exclusively (User: read-only)
- **log.md**: Agent maintains (User: read-only)

### 1.3 Automation Tool

Bob uses [`tools/bob_runner.py`](tools/bob_runner.py) for structural scaffolding. There is also a [`tools/bob`](tools/bob) shell wrapper that delegates directly to the runner — make it executable and add `tools/` to PATH for the shorter `bob ...` form:

```bash
chmod +x tools/bob
export PATH="$PWD/tools:$PATH"
```

**Available Commands**:
```bash
# Ingest - Scaffold a source page from a raw/ file
python3 tools/bob_runner.py ingest --source example.md

# Query - Search index for keyword matches (returns candidates only)
python3 tools/bob_runner.py query --question "What is transformer"

# Create-page - Generate a page skeleton from template
python3 tools/bob_runner.py create-page --type concept --title "My Concept" --filename my-concept.md
# Types: entity, concept, source, analysis

# Lint - Check wiki for missing headings/timestamps
python3 tools/bob_runner.py lint

# Index-update - Ensure index file exists
python3 tools/bob_runner.py index-update
```

**What bob_runner.py actually does (and does NOT do)**:

The runner is intentionally minimal — it creates scaffolding only. The agent is responsible for all content, cross-references, enrichment, and maintenance that the runner does not perform.

| Command | Runner does | Agent must add |
|---------|-------------|----------------|
| `ingest` | Creates `wiki/sources/[slug].md` with first 10 lines of raw file as Summary; adds one entry under `## Sources` in the index; appends a log stub | Replace stub Summary with real analysis; create entity/concept pages; add all cross-references |
| `query` | Keyword-searches index lines starting with `- ` (words >3 chars); prints up to 10 matches | Read actual wiki pages; synthesize answer; optionally preserve as analysis |
| `create-page` | Writes minimal skeleton file | Fill all sections; establish bidirectional links; update index and log |
| `lint` | Checks every `.md` in `wiki/` for a `# ` heading and one of the exact strings `Last updated` / `Ingested` / `Created:` | Check broken links, orphan pages, contradictions, missing concepts |
| `index-update` | Creates `index/index_001.md` if it doesn't exist; does nothing else | Scan wiki, populate/sync all index entries, split if over token limit |

**Critical runner behaviours to know**:

- **`ingest` summary** is the raw file's first 10 lines verbatim — always replace it with a proper analysis.
- **`ingest` on duplicate** adds a `YYYYMMDDHHMMSS` timestamp suffix to the filename rather than failing.
- **`create-page` on duplicate** exits with status 1 and does not create a file — check the index first.
- **`find_index_file()`** picks the **highest-numbered** index file (e.g. `index_002.md` over `index_001.md`). New entries are inserted immediately after the `## Sources` heading in that file. After a split, `ingest` correctly writes into the newest index.
- **`create-page` folder mapping**: type `analysis` → `wiki/analyses/`, `entity` → `wiki/entities/`, `concept` → `wiki/concepts/`, `source` → `wiki/sources/` (all plural).
- **`lint` timestamp check** matches any of these exact strings: `Last updated`, `Ingested`, `Created:` (note the colon on `Created:`). Any other wording is flagged as missing metadata.
- **log operation type** written by the runner for `create-page` actions is `create-page` (not in the original list of types — see §6.1).

**Bob's Usage Pattern**:
1. Execute automation for structure/boilerplate
2. Read created file
3. Enrich with analysis and cross-references
4. Update related pages with bidirectional links

---

## 2. Core Operations (High-Level)

### 2.1 INGEST
**Purpose**: Process new source from `raw/` into wiki Pages

**Command**: `/ingest [source-file]` → See [`.bob/commands/ingest.md`](.bob/commands/ingest.md) for detailed procedure

**Key principle**: Read source → Discuss takeaways with User → Create/update Pages → Update index → Log

### 2.2 QUERY
**Purpose**: Answer questions using wiki content, optionally preserve valuable answers

**Command**: `/query [question]` → See [`.bob/commands/query.md`](.bob/commands/query.md) for detailed procedure

**Preservation criteria**: Synthesizes 3+ Pages, reveals connections, comparison, or User requests

### 2.3 LINT
**Purpose**: Health-check wiki for contradictions, orphans, missing concepts, broken links

**Command**: `/lint` → See [`.bob/commands/lint.md`](.bob/commands/lint.md) for detailed procedure

**Frequency**: Monthly recommended

### 2.4 CREATE-PAGE
**Purpose**: Create new wiki page with proper template and cross-references

**Command**: `/create-page [type]` → See [`.bob/commands/create-page.md`](.bob/commands/create-page.md) for detailed procedure

**Types**: entity, concept, source, analysis

### 2.5 INDEX-UPDATE
**Purpose**: Maintain index files, ensure completeness, handle splitting

**Command**: `/index-update` → See [`.bob/commands/index-update.md`](.bob/commands/index-update.md) for detailed procedure

**When**: After bulk changes or monthly verification

### 2.6 RESEARCH
**Purpose**: Investigate a topic by combining wiki knowledge with external sources

**Command**: `/research [topic or question]` → See [`.bob/commands/research.md`](.bob/commands/research.md) for detailed procedure

**Key principle**: Check wiki first → supplement with external browsing if allowed → synthesize with citations → optionally preserve as analysis page

---

## 3. Page Standards

### 3.1 Naming Convention
- Use `kebab-case-descriptive-name.md`
- Be specific and descriptive
- Use lowercase only
- Avoid special characters (the `kebab()` function strips everything except `[a-z0-9\s-]`)

**Examples**:
- `openai.md`, `geoffrey-hinton.md` (entities)
- `machine-learning.md`, `gradient-descent.md` (concepts)
- `attention-is-all-you-need.md` (sources)
- `comparison-gpt-vs-claude.md` (analyses)

### 3.2 Required Elements (All Pages)
- [ ] Title (# heading)
- [ ] Summary paragraph
- [ ] Main content sections
- [ ] Cross-references section (## Related Pages)
- [ ] Sources section (## Sources)
- [ ] Last updated timestamp

### 3.3 Page Templates

Full templates are defined in [`.bob/commands/create-page.md`](.bob/commands/create-page.md). Key requirements:
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

Links within wiki pages use paths **relative to the file's own location**. Links inside index files use paths relative to the `index/` directory (e.g. `../wiki/concepts/foo.md`).

**Example in a wiki page**:
```markdown
## Related Pages
- [Machine Learning](../concepts/machine-learning.md) - Uses neural networks as core technique
```

**Example in an index entry**:
```markdown
- [Machine Learning](../wiki/concepts/machine-learning.md) - One-line description [sources: 2]
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
- [Entity Name](../wiki/entities/entity-name.md) - One-line description [sources: X]

## Concepts
- [Concept Name](../wiki/concepts/concept-name.md) - One-line description [sources: X]

## Sources
- [Source Title](../wiki/sources/source-title.md) - Date, type [entities: X, concepts: Y]

## Analyses
- [Analysis Title](../wiki/analyses/analysis-title.md) - Date, query summary
```

> **Note**: Index paths use `../wiki/` prefix (relative from `index/`). The runner's auto-inserted entries use bare `wiki/` paths — correct these when enriching.

### 5.2 Index Splitting Rules

**When**: Current index exceeds 10000 tokens

**How**:
1. Create `index_XXX+1.md`
2. Move newest ~2000 tokens to new index
3. Keep ~8000 tokens in old index
4. Add navigation links to both files:
   ```markdown
   Previous: [index_001.md](index_001.md)
   Next: [index_003.md](index_003.md)
   ```

> **Note**: After splitting, `bob_runner.py ingest` inserts into the highest-numbered index file, which is the most recently created one. No manual move is needed.

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

**Operation types**: `ingest`, `query`, `lint`, `fix`, `reorg`, `create-page`

> Note: `bob_runner.py` writes `create-page` as the operation type for that command. The runner's log entries contain `Brief: automated by bob_runner.py` and a minimal outcomes line — always expand these with real context when enriching.

### 6.2 Log Parsing Examples

```bash
# Last 5 operations
grep "^## \[" log.md | tail -5

# All ingests this month
grep "^## \[2026-05" log.md | grep "ingest"

# Pages modified today
grep "^## \[2026-05-24" log.md -A 10 | grep "wiki/"
```

---

## 7. Quality Checklists

### 7.1 Page Quality
Before finalizing any Page:
- [ ] Title is clear and descriptive
- [ ] Summary paragraph exists (not a raw-file excerpt)
- [ ] All sections have content
- [ ] At least 2 cross-references (unless isolated)
- [ ] At least 1 source citation
- [ ] Timestamp present using an exact accepted string: `Last updated`, `Ingested`, or `Created:`
- [ ] Markdown formatting correct
- [ ] Links use relative paths appropriate to file location
- [ ] No typos in key terms

### 7.2 Index Quality
Before updating index:
- [ ] All new Pages added
- [ ] One-line descriptions accurate
- [ ] Metadata included (source count, date)
- [ ] Alphabetical order within categories
- [ ] Token count noted
- [ ] Paths use `../wiki/` prefix (relative from `index/`)
- [ ] Navigation links present (if multiple indices)

### 7.3 Log Quality
Before appending to log:
- [ ] Date in ISO format [YYYY-MM-DD HH:MM]
- [ ] Operation type specified (valid types in §6.1)
- [ ] Title/description clear
- [ ] Affected Pages listed with links
- [ ] Key outcomes summarized (not just "automated operation")

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
3. Read candidates in single batch (up to 5 at once)
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

Bob executes operations using [`tools/bob_runner.py`](tools/bob_runner.py) for scaffolding. The [`tools/bob`](tools/bob) shell wrapper (already executable) provides a shorter CLI — use it by running `export PATH="$PWD/tools:$PATH"` first. Each command has a detailed procedure file in `.bob/commands/`.

### Command Reference Table

> **Prerequisite**: `export PATH="$PWD/tools:$PATH"` (or `python3 tools/bob_runner.py` as fallback)

| Slash Command | Automation Command | Procedure File |
|--------------|-------------------|----------------|
| `/ingest [file]` | `bob ingest --source [file]` | [`.bob/commands/ingest.md`](.bob/commands/ingest.md) |
| `/query [question]` | `bob query --question "[question]"` | [`.bob/commands/query.md`](.bob/commands/query.md) |
| `/create-page [type]` | `bob create-page --type [type] --title "[title]" --filename [name].md` | [`.bob/commands/create-page.md`](.bob/commands/create-page.md) |
| `/lint` | `bob lint` | [`.bob/commands/lint.md`](.bob/commands/lint.md) |
| `/index-update` | `bob index-update` | [`.bob/commands/index-update.md`](.bob/commands/index-update.md) |
| `/research [topic]` | `bob research` *(prints procedure path; no scaffolding)* | [`.bob/commands/research.md`](.bob/commands/research.md) |
| `/status` | `bob status` | skill only — no separate command file |
| `/raw-list [--pending-only]` | `bob raw-list [--pending-only]` | skill only — no separate command file |
| `/move --from [path] --to [path]` | `bob move --from [path] --to [path]` | skill only — no separate command file |

### Execution Pattern

1. **User invokes**: `/ingest paper.md`
2. **Bob runs scaffolding**: `bob ingest --source paper.md`
3. **Bob reads created file**: confirms what the runner produced
4. **Bob follows procedure**: reads `.bob/commands/ingest.md` for enrichment steps
5. **Bob adds intelligence**: real analysis, cross-references, relationships, expanded log entry

**Key principle**: Automation creates minimal structure → Bob adds all intelligence

---

## 12. Runner Error Handling

### 12.1 What to Do When `bob_runner.py` Produces an Error

If [`tools/bob_runner.py`](tools/bob_runner.py) exits with a non-zero status code, prints a Python traceback, or produces output that indicates incorrect behaviour (wrong paths, missing files, unexpected content), treat it as a bug and follow this procedure — **do not silently work around it**.

**Step 1 — Report clearly**

Tell the user immediately:
- What command was run (full invocation).
- What the runner printed (stdout + stderr, verbatim).
- What the expected outcome was vs what actually happened.

Example phrasing:
> "`bob ingest --source paper.md` failed with the following output:
> ```
> [paste output here]
> ```
> This looks like a bug in `tools/bob_runner.py`. Would you like me to analyse it and propose a fix?"

**Step 2 — Ask for permission before touching the runner**

Wait for explicit user approval before reading or editing [`tools/bob_runner.py`](tools/bob_runner.py). Do not attempt a silent fix.

**Step 3 — Analyse (only after approval)**

1. Read [`tools/bob_runner.py`](tools/bob_runner.py) and identify the defective function.
2. Reproduce the failure mentally by tracing the relevant code path.
3. Propose a minimal fix with a clear explanation of what is wrong and why the fix is correct.
4. Show the diff before applying it and ask for a final confirmation.

**Step 4 — Apply and verify**

1. Apply the approved fix using `apply_diff`.
2. Re-run the original failing command to confirm it now succeeds.
3. Log the fix under operation type `fix` in `log.md`.

### 12.2 Distinguishing Runner Bugs from Usage Errors

Not every failure is a bug. Check these first before escalating:

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| `Source file not found` | Wrong filename or not placed in `raw/` | Tell user to check the path |
| `File exists: will not overwrite` | Duplicate ingest / page already exists | Expected behaviour — proceed manually |
| `move requires --from and --to` | Missing CLI argument | Correct the invocation |
| `Unknown command: …` | Typo in command name | Correct the invocation |
| Python `Traceback` | Genuine bug | Follow §12.1 |
| Output is structurally wrong (bad paths, missing sections) | Genuine bug | Follow §12.1 |

### 12.3 Scope

- Only [`tools/bob_runner.py`](tools/bob_runner.py) is covered by this protocol. Bugs in wiki page content, index files, or skill files are handled through normal editing — no special permission is required.
- The runner is intentionally minimal. If a limitation is by design (see §1.3 "What bob_runner.py actually does"), note that to the user rather than filing it as a bug.

---

*This manual is a living document. Update it when workflows evolve.*
