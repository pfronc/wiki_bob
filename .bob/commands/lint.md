---
description: WIKI Health Check
---
## When User requests: `/lint`

#### Step-by-Step Procedure:

##### 1. Scan All Pages

**Read systematically**:
- List all files in wiki/ recursively
- Read Pages in batches (up to 5 at once)
- Track all entities, concepts, sources, analyses

**Build mental map**:
- All Page titles and paths
- All cross-references (who links to whom)
- All concepts mentioned
- All entities mentioned
- All sources cited

##### 2. Check for Issues

**A. Contradictions (Priority: HIGH)**
- Same concept described differently in multiple Pages
- Conflicting claims about same entity
- Inconsistent terminology

Example:
```
- [Page A](wiki/concepts/ai-safety.md) defines alignment as "X"
- [Page B](wiki/concepts/alignment.md) defines alignment as "Y"
- Contradiction: Different definitions of same concept
```

**B. Staleness (Priority: HIGH)**
- Claims superseded by newer sources
- Outdated information
- Missing recent developments

Example:
```
- [Page](wiki/entities/openai.md) states "GPT-4 is latest model"
- [Source](wiki/sources/new-article.md) mentions GPT-5
- Staleness: Entity Page needs update
```

**C. Orphan Pages (Priority: MEDIUM)**
- Pages with no inbound links
- Isolated content not connected to wiki graph

Example:
```
- [Page](wiki/concepts/obscure-theory.md) has no inbound references
- Orphan: Should be linked from related concepts or archived
```

**D. Missing Concepts (Priority: MEDIUM)**
- Concepts mentioned but not defined
- Terms used without dedicated Page

Example:
```
- "Constitutional AI" mentioned in [Page X](link), [Page Y](link)
- No dedicated Page: wiki/concepts/constitutional-ai.md
- Missing concept: Should create Page
```

**E. Broken Links (Priority: HIGH)**
- References to non-existent Pages
- Incorrect paths

Example:
```
- [Page A](wiki/concepts/ml.md) links to [Page B](wiki/concepts/neural-nets.md)
- Page B doesn't exist
- Broken link: Fix path or create Page
```

**F. Missing Cross-References (Priority: LOW)**
- Related Pages not linked
- One-way links (not bidirectional)

Example:
```
- [Page A](wiki/concepts/transformers.md) links to [Page B](wiki/concepts/attention.md)
- Page B doesn't link back to Page A
- Missing cross-ref: Add bidirectional link
```

##### 3. Generate Report

**Format**:
```markdown
## Lint Report [YYYY-MM-DD]

**Total Pages scanned**: X
**Issues found**: Y

---

### Contradictions (Priority: HIGH) - Count: X

#### Issue 1: [Brief description]
- **Pages involved**: [Page A](link), [Page B](link)
- **Conflict**: [Description of contradiction]
- **Recommendation**: [How to resolve]

---

### Staleness (Priority: HIGH) - Count: X

#### Issue 1: [Brief description]
- **Page**: [Page](link)
- **Problem**: [What's outdated]
- **Source**: [Newer source](link)
- **Recommendation**: [What to update]

---

### Orphan Pages (Priority: MEDIUM) - Count: X

#### Issue 1: [Page title]
- **Page**: [Page](link)
- **Problem**: No inbound references
- **Recommendation**: Link from [suggested Pages] or archive

---

### Missing Concepts (Priority: MEDIUM) - Count: X

#### Issue 1: "[Concept name]"
- **Mentioned in**: [Page X](link), [Page Y](link)
- **Problem**: No dedicated Page
- **Recommendation**: Create wiki/concepts/[concept-name].md

---

### Broken Links (Priority: HIGH) - Count: X

#### Issue 1: [Brief description]
- **Source Page**: [Page](link)
- **Broken link**: [Target path]
- **Recommendation**: Fix path or create missing Page

---

### Missing Cross-References (Priority: LOW) - Count: X

#### Issue 1: [Brief description]
- **Pages**: [Page A](link) → [Page B](link)
- **Problem**: One-way link only
- **Recommendation**: Add reciprocal link in Page B

---

### Suggestions for Improvement

**New sources to seek**:
- Topic A: [Why it would be valuable]
- Topic B: [Why it would be valuable]

**New questions to explore**:
- Question 1: [Why it's interesting]
- Question 2: [Why it's interesting]

**Potential reorganization**:
- [Suggestion for better structure]

---

### Statistics
- Total entities: X
- Total concepts: Y
- Total sources: Z
- Total analyses: W
- Average cross-references per Page: N
- Pages with <2 cross-refs: M
```

##### 4. Present Report to User
- Show complete report
- Highlight high-priority issues
- Ask User to prioritize fixes

##### 5. Execute Fixes (User-directed)
- User reviews report
- User specifies which issues to fix
- Agent fixes issues one by one
- Agent confirms each fix with User

##### 6. Log Operation
Append to log.md:
```markdown
## [YYYY-MM-DD HH:MM] lint | Health check complete

Scanned X Pages across wiki.

Issues found:
- Contradictions: X (high priority)
- Staleness: Y (high priority)
- Orphans: Z (medium priority)
- Missing concepts: W (medium priority)
- Broken links: V (high priority)
- Missing cross-refs: U (low priority)

Key outcomes:
- Generated comprehensive report
- Identified [specific important issue]
- Suggested [number] new sources to seek
```

#### Quality Checklist
- [ ] All wiki/ subdirectories scanned
- [ ] All issue types checked
- [ ] Report is comprehensive and clear
- [ ] Issues prioritized correctly
- [ ] Recommendations are actionable
- [ ] Statistics included
- [ ] Log entry appended
