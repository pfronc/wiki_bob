# Command: index-update

Usage: `/index-update`

Purpose: Update or rebuild the `index/*` files to include new pages and keep token estimates within limits.

Procedure:
1. Scan `wiki/` and `raw/` for new or changed pages.
2. Add missing entries to the current `index_*.md` under appropriate categories.
3. If an index exceeds token limit, create a new `index_XXX.md` and move recent entries.
4. Add navigation links between index files.
5. Commit changes to index files and append a log entry.
---
description: WIKI Index Maintenance
---

## When User requests: `/index-update`

#### Step-by-Step Procedure:

##### 1. Scan Wiki Content
- List all files in wiki/ recursively
- Categorize by type: entities/, concepts/, sources/, analyses/
- Read each Page to extract:
  - Title
  - One-line description (from summary)
  - Metadata (date, source count, etc.)

##### 2. Read Current Indices
- List all files in index/
- Read all index_XXX.md files
- Note current structure and token counts

##### 3. Verify Completeness
- Check all wiki Pages are listed in indices
- Identify missing entries
- Identify outdated descriptions
- Identify incorrect metadata

##### 4. Update or Rebuild Indices

**If minor updates needed**:
- Add missing entries
- Update outdated descriptions
- Correct metadata
- Maintain alphabetical order within categories

**If major rebuild needed**:
- Create fresh index structure
- Organize by categories (Entities, Concepts, Sources, Analyses)
- Alphabetize within each category
- Include all metadata

**Index format**:
```markdown
# Wiki Index [001]

Last updated: YYYY-MM-DD
Total Pages: XXX
Token count: ~XXXX

## Entities
- [Entity Name](wiki/entities/entity-name.md) - One-line description [sources: X]
- ...

## Concepts
- [Concept Name](wiki/concepts/concept-name.md) - One-line description [sources: X]
- ...

## Sources
- [Source Title](wiki/sources/source-title.md) - Date, type [entities: X, concepts: Y]
- ...

## Analyses
- [Analysis Title](wiki/analyses/analysis-title.md) - Date, query summary
- ...
```

##### 5. Check Token Counts
- Estimate or calculate token count for each index
- If any index >10000 tokens, proceed to split

##### 6. Split Indices (if needed)

**When to split**: Current index >10000 tokens

**How to split**:
1. Create new index_XXX+1.md
2. Move newest ~2000 tokens to new index
3. Keep ~8000 tokens in old index
4. Add navigation links:
   ```markdown
   ---
   **Navigation**:
   - Previous: [index_001.md](index_001.md)
   - Next: [index_003.md](index_003.md)
   ```
5. Update both files with navigation

##### 7. Verify Index Quality
- [ ] All Pages listed
- [ ] Descriptions accurate
- [ ] Metadata complete
- [ ] Alphabetical order maintained
- [ ] Token counts noted
- [ ] Navigation links present (if multiple indices)
- [ ] No broken links

##### 8. Log Operation
Append to log.md:
```markdown
## [YYYY-MM-DD HH:MM] index-update | Manual index maintenance

Updated index files.

Changes:
- Added X missing entries
- Updated Y descriptions
- Split index_002.md (exceeded 10000 tokens)
- Created index_003.md

Current state:
- Total indices: N
- Total Pages indexed: X
- Average tokens per index: Y
```

##### 9. Report to User
```markdown
## Index Update Complete

### Changes Made:
- Added X missing entries
- Updated Y descriptions
- Corrected Z metadata entries
- Split N indices

### Current Index State:
- Total index files: N
- Total Pages indexed: X
- Largest index: Y tokens
- Smallest index: Z tokens

### Issues Found:
- [Any issues discovered]
```

#### Quality Checklist
- [ ] All wiki Pages represented in indices
- [ ] All descriptions accurate and concise
- [ ] All metadata complete
- [ ] Alphabetical order maintained
- [ ] Token counts within limits
- [ ] Navigation links correct
- [ ] Log entry appended
