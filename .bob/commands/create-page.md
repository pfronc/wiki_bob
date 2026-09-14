# Command: create-page

Usage: `/create-page [type]` (follow interactive prompts)

Purpose: Create a new wiki page of type `entity`, `concept`, `source`, or `analysis` using the project's templates and establish cross-references.

Procedure:
1. Confirm page type and collect Title, Filename (kebab-case), Key information, Related Pages from the User via interactive prompts.
2. Check index files for existing or similar pages; if a page exists, offer an update flow instead of creating a duplicate.
3. Select the appropriate template and populate it:

Entity Page Template:
```markdown
# Entity Name

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

**Category**: Theory | Method | Framework | Principle
**First introduced**: [Source](link) or "User-created"
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

---
*Ingested: YYYY-MM-DD*
```

Analysis Page Template:
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

4. Create the file `wiki/[type]/[filename].md` populated with the chosen template, ensure the timestamp is added, and save.
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
- Correct template used and all required sections present.
- Title clear and descriptive; summary present.
- At least 1 cross-reference (if applicable) and bidirectional links established.
- Timestamp present; Markdown formatting correct.
- Index updated and log entry appended.
