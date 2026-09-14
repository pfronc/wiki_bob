# Command: query

Usage: `/query [question]`

Purpose: Search the wiki indices and pages, synthesize an answer with citations, and optionally preserve the result as an analysis page.

Inputs:
- `question` — user question or prompt.

Procedure:
1. Read `index/*.md` and identify 5–10 candidate pages by matching question keywords to titles/descriptions.
2. Read candidate pages in batch (up to 5 at once) and extract relevant facts, quotes and citations. Track cross-references that may point to additional relevant pages.
3. Synthesize the answer, formatted appropriately to the question type:
	- Simple fact: direct answer with citations.
	- Comparison: side-by-side or table with citations.
	- Complex topic: structured sections with headings.
	- Relationships: include a Mermaid diagram if helpful.

	Example answer format:
	```markdown
	## Answer: [Question]

	[Main answer paragraph with citations]

	### Key Points
	- Point 1 [citation](wiki/path.md)
	- Point 2 [citation](wiki/path.md)

	### Related Information
	[Additional context with citations]

	---
	**Sources consulted**: [Page 1](wiki/path.md), [Page 2](wiki/path.md)
	```

4. Assess preservation value:
	- Create an analysis Page if the answer synthesizes 3+ Pages, reveals non-obvious connections, compares multiple concepts/entities, or the User requests preservation.
	- Do not preserve for simple single-page lookups or trivial answers.

5. If preserving, create `wiki/analyses/[descriptive-title].md` using the Analysis Page Template and include the question, full answer, sources consulted, key insights, and related analyses.
6. Update index (Analyses section) and append a log entry when an analysis page is created.

Log template for preserved queries:

```markdown
## [YYYY-MM-DD HH:MM] query | [Question summary]

Created analysis Page from query.

Pages consulted:
- [Page 1](wiki/path.md)
- [Page 2](wiki/path.md)

Pages created:
- [wiki/analyses/analysis-title.md](wiki/analyses/analysis-title.md)

Key outcomes:
- Synthesized information from X Pages
- Revealed connection between [A] and [B]
```

Quality checklist:
- Answer directly addresses the question and is well-structured.
- All claims have citations using correct relative paths.
- If preserved: Analysis Page includes question, answer, sources, key insights, and timestamp; index and log updated.
