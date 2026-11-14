# Command: create-page

Usage: `/create-page [type]` (follow interactive prompts)

Purpose: Create a new wiki page of type `entity`, `concept`, `source`, or `analysis` using the project's templates and establish cross-references.

Procedure:
1. Confirm page type and collect Title, Filename (kebab-case), Key information, Related Pages from the User via interactive prompts.
2. Check existing `#` titles, `Canonical title` and `Aliases` metadata, index
   entries, and source-registry records for existing or similar pages. Refuse an
   exact canonical/alias duplicate. Mark uncertain source-registry matches as
   `Identity review: needs-review` instead of silently merging them.
3. Select the appropriate template and populate it:

Prepend this shared Obsidian Properties block to every managed page. Keep list
properties as lists even when empty. Use `needs-review` when identity or source
coverage is uncertain; otherwise new pages begin as `draft`.

```yaml
---
kind: entity # entity | concept | source | analysis | map
status: draft # draft | verified | needs-review | archived
aliases: []
topics: []
sources: []
source_ids: []
created: YYYY-MM-DD
updated: YYYY-MM-DD
last_reviewed:
---
```

Source pages also include `ingest_status`, `extraction_status`, `source_type`,
`author`, and `year`; entity pages include `entity_type` and
`related_concepts`. Concept and analysis pages may include `category` and
`analysis_type`. These properties power native Bases but do not replace prose
metadata or the source registry.

Entity Page Template:
```markdown
# Entity Name

**Canonical title**: Entity Name
**Aliases**: (none) or comma-separated alternatives
**Identity review**: clear | needs-review
**Type**: Person | Organization | Product | Location
**First mentioned**: [Source](link) or "User-created"
**Related concepts**: [Concept 1](link), [Concept 2](link)

## Summary
One paragraph overview.

## Key Information
- Attribute 1: Value
- Attribute 2: Value

## Mentions in Sources
- [Source 1](link) - Context of mention

## Related Pages
- [Related Entity](link) - Nature of relationship
- [Related Concept](link) - How they connect

## Sources
1. [Source Title](link) - Date

---
*Last updated: YYYY-MM-DD*
```

Concept Page Template:
```markdown
# Concept Name

**Canonical title**: Concept Name
**Aliases**: (none) or comma-separated alternatives
**Identity review**: clear | needs-review
**Category**: Theory | Method | Framework | Principle
**First introduced**: [Source](link) or "User-created"
**Related concepts**: [Concept 1](link), [Concept 2](link)

## Summary
One paragraph overview.

## Definition
Clear, concise definition in 1-2 sentences. Use LaTeX for all math: inline `$…$` and display `$$…$$`.

## Explanation
Detailed explanation with examples. Use LaTeX for all math: inline `$…$` and display `$$…$$`.

## Key Aspects
- Aspect 1: Description
- Aspect 2: Description

## Applications
Where and how this concept is used.

## Related Entities
- [Entity](link) - How they relate

## Related Pages
- [Related Concept](link) - Nature of relationship

## Sources
1. [Source Title](link) - Date - Key contribution

## External References
- [External Resource](URL) - Description

---
*Last updated: YYYY-MM-DD*
```

Source Page Template:
```markdown
# Source: Title

**Type**: Article | Book | Paper | Video | Podcast
**Date**: YYYY-MM-DD
**Author**: Name
**Original location**: `raw/filename.ext` or URL
**Source ID**: `src_...` from the registry or `manual:slug`
**Extraction status**: pending | partial | complete | failed | not-applicable
**Ingest status**: pending | partial | complete | draft
**Identity review**: clear | needs-review

## Summary
2-3 paragraph summary of main points.

## Key Takeaways
- Takeaway 1
- Takeaway 2
- Takeaway 3

## Entities Mentioned
- [Entity 1](link) - Context

## Concepts Discussed
- [Concept 1](link) - How discussed

## Notable Quotes
> Quote 1

## Related Pages
- [Related Page](link) - Nature of relationship

## Sources
- Original source: `raw/filename.ext` or URL

---
*Ingested: YYYY-MM-DD*
```

Analysis Page Template:
```markdown
# Analysis: Title

**Type**: Comparison | Synthesis | Deep Dive
**Date**: YYYY-MM-DD
**Origin**: Query | Lint | User request

## Summary
One paragraph overview.

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

## Related Pages
- [Related Page](link) - Nature of relationship

## Sources
- Citation: [Source Title](../sources/source-title.md), [p. N](../../raw/SourceFile.pdf#page=N).

---
*Created: YYYY-MM-DD*
```

4. Create the file `wiki/[type]/[filename].md` populated with the chosen template, ensure the timestamp is added, and save.
   Factual claims use `Claim. Citation: [Source Title](../sources/source-title.md),
   [p. 42](../../raw/OriginalFilename.pdf#page=42).` For PDF sources, link the
   page reference to the raw file with a standard Markdown link, pathed relative
   to the citing file (from `wiki/concepts/` etc. that is `../../raw/...`) — this
   keeps the citation clickable in both Obsidian (opens the PDF at the page) and
   VS Code (opens the PDF; its viewers ignore the `#page=` fragment and start at
   page 1, so the page number stays in the link text). Use a section, timestamp,
   or chunk ID only for non-PDF sources where page anchors do not apply.
5. Establish bidirectional cross-references:
	- Add links in the new Page to related Pages.
	- Update related Pages to link back to the new Page and include context for the relationship.
6. Update the relevant `index/*` file with a one-line description and metadata; check token counts.
7. Append a log entry to `log.md` using the template:

```markdown
## [YYYY-MM-DD HH:MM] create-page | [Page Title]

Created new [type] Page at User request.

Pages created:
- [wiki/[type]/[filename].md](wiki/[type]/[filename].md)

Pages updated (cross-references):
- [Related Page 1](link)
- [Related Page 2](link)

Key outcomes:
- Added new [type] to wiki
- Established X cross-references
```

8. Report back to the User with the page location, cross-references created, and suggested next steps.

Quality checklist:
- Shared frontmatter exists, uses valid status/kind values, and keeps collection properties as lists.
- Correct template used and all required sections present.
- Entity/concept canonical titles and aliases have been checked for duplicates.
- Title clear and descriptive; summary present.
- Every substantive claim resolves to a source page and source location.
- At least 1 cross-reference (if applicable) and bidirectional links established.
- All mathematical expressions use LaTeX: inline `$…$` for in-text math, display `$$…$$` for standalone equations. Never use code spans or code blocks for math.
- Tables with math avoid literal pipes inside `$...$`: use `\lvert`/`\rvert` for kets and absolute values (a bare `|` splits the row; `\|` renders as a double bar).
- Timestamp present; Markdown formatting correct.
- Index updated and log entry appended.

## Page size discipline

`PAGE_WARNING_TOKENS` (5,000) is a **review prompt, not a hard limit**. Do not
silently compact prose to fit it.

1. Measure the cause before editing anything. The estimator counts every
   punctuation mark, so PDF page anchors (`../../raw/…pdf#page=N`) required by the
   citation contract can account for ~30% of a well-cited page. Compare the total
   against the same file with link markup stripped to see whether prose or
   provenance dominates.
2. Judge scope, not size. A page that covers one coherent mechanism across two
   sources is correctly sized regardless of the number.
3. Present options to the user instead of choosing unilaterally:
   - **Accept the warning** — the default; pre-existing pages already exceed it,
     and lint findings do not fail the run.
   - **Relax the threshold** — requires explicit approval; it is a
     `tools/bob_runner.py` change, so follow `AGENTS.md` section 12 first.
   - **Split the page** — only when the topic is genuinely broader than one page,
     not merely when the count is high.
4. Never remove or coarsen citations, drop sections, or narrow scope to reduce the
   token count. Provenance outranks the advisory number.
