# WIKI System - Agent Operations Manual

## 1. System Overview

### 1.1 Role Definition
- **User**: Curator of source materials, query initiator, workflow supervisor
- **Agent**: AI librarian managing wiki content, maintaining consistency, answering queries

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
- **raw/**: User exclusively (Agent: read-only)
- **wiki/**: Agent exclusively (User: read-only)
- **index/**: Agent exclusively (User: read-only)
- **log.md**: Agent maintains (User: read-only)

---

## 2. Core Operations (High-Level)

### 2.1 INGEST
**Purpose**: Process new source from `raw/` into wiki Pages

**Flow**: Read source → Discuss takeaways with User → Create/update Pages → Update index → Log

**Impact**: Typically touches 10-15 Pages per source

**Command**: `/ingest [source-file]` (see [slug: ingest](.bob/custom_mode.yaml) for detailed procedure)

### 2.2 QUERY
**Purpose**: Answer questions using wiki content, optionally preserve valuable answers

**Flow**: Search index → Read relevant Pages → Synthesize answer → Assess preservation value → Create analysis Page if valuable

**Preservation criteria**: Synthesizes 3+ Pages, reveals connections, comparison, or User requests

**Command**: `/query [question]` (see [slug: query](.bob/custom_mode.yaml) for detailed procedure)

### 2.3 LINT
**Purpose**: Health-check wiki for contradictions, orphans, missing concepts, broken links

**Flow**: Scan all Pages → Identify issues → Generate report → User prioritizes → Agent fixes

**Frequency**: Monthly recommended

**Command**: `/lint` (see [/lint](.bob/commands/lint.md) for detailed procedure)

---

## 3. Page Standards

### 3.1 Naming Convention
- Use `kebab-case-descriptive-name.md`
- Be specific and descriptive
- Use lowercase only
- Avoid special characters

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

### 3.3 Entity Page Template

```markdown
# Entity Name

**Type**: Person | Organization | Product | Location
**First mentioned**: [Source](link)
**Related concepts**: [Concept 1](link), [Concept 2](link)

## Summary
One paragraph overview.

## Key Information
- Attribute 1: Value
- Attribute 2: Value

## Mentions in Sources
- [Source 1](link) - Context of mention
- [Source 2](link) - Context of mention

## Related Pages
- [Related Entity](link) - Nature of relationship
- [Related Concept](link) - How they connect

## Sources
1. [Source Title](link) - Date

---
*Last updated: YYYY-MM-DD*
```

### 3.4 Concept Page Template

```markdown
# Concept Name

**Category**: Theory | Method | Framework | Principle
**First introduced**: [Source](link)
**Related concepts**: [Concept 1](link), [Concept 2](link)

## Definition
Clear, concise definition in 1-2 sentences.

## Explanation
Detailed explanation with examples.

## Key Aspects
- Aspect 1: Description
- Aspect 2: Description

## Applications
Where and how this concept is used.

## Related Entities
- [Entity](link) - How they relate

## Related Pages
- [Related Concept](link) - Nature of relationship
- [Analysis](link) - Where this concept was explored

## Sources
1. [Source Title](link) - Date - Key contribution

## External References
- [External Resource](URL) - Description

---
*Last updated: YYYY-MM-DD*
```

### 3.5 Source Page Template

```markdown
# Source: Title

**Type**: Article | Book | Paper | Video | Podcast
**Date**: YYYY-MM-DD
**Author**: Name
**Original location**: `raw/filename.ext`

## Summary
2-3 paragraph summary of main points.

## Key Takeaways
- Takeaway 1
- Takeaway 2
- Takeaway 3

## Entities Mentioned
- [Entity 1](link) - Context
- [Entity 2](link) - Context

## Concepts Discussed
- [Concept 1](link) - How discussed
- [Concept 2](link) - How discussed

## Notable Quotes
> Quote 1

> Quote 2

## Related Sources
- [Source](link) - Relationship (contradicts, supports, extends)

---
*Ingested: YYYY-MM-DD*
```

### 3.6 Analysis Page Template

```markdown
# Analysis: Title

**Type**: Comparison | Synthesis | Deep Dive
**Date**: YYYY-MM-DD
**Origin**: Query | Lint | User request

## Question
Original question or prompt.

## Answer
Comprehensive answer with sections as needed.

## Sources Consulted
- [Page 1](link)
- [Page 2](link)

## Key Insights
- Insight 1
- Insight 2

## Related Analyses
- [Analysis](link) - Relationship

---
*Created: YYYY-MM-DD*
```

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
- [Machine Learning](../concepts/machine-learning.md) - Uses neural networks as core technique
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
grep "^## \[2026-05" log.md | grep "ingest"

# Pages modified today
grep "^## \[2026-05-24" log.md -A 10 | grep "wiki/"
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

For detailed operational procedures, use these commands:

- `/ingest [source-file]` - Process new source into wiki
- `/query [question]` - Answer question with wiki content
- `/lint` - Run wiki health check (see [/lint](.bob/commands/lint.md))
- `/index-update` - Manually update index files (see [/index-update](.bob/commands/index-update.md))
- `/create-page [type]` - Create new page with template

See individual command definitions for step-by-step procedures.

---

*This manual is a living document. Update it when workflows evolve.*