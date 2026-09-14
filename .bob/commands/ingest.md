# Command: ingest

Usage: `/ingest [source-file]`

Purpose: Process a raw source file from `raw/` into structured wiki Pages (source, entities, concepts), update index, and append a log entry.

Inputs:
- `source-file` — filename located in `raw/` (e.g., `paper.pdf`, `article.md`).

Procedure:
1. Read `raw/[source-file]` fully and extract metadata (title, author, date, type).
2. Extract key information:
	- Main topics and concepts
	- Entities mentioned (people, organizations, products)
	- Novel insights or unique perspectives
	- Connections to existing wiki knowledge
3. Present Key Takeaways to the User and request confirmation before proceeding.

	Example presentation (send as markdown):
	```markdown
	## Key Takeaways from "[Source Title]"

	1. [First key point]
	2. [Second key point]
	3. [Third key point]
	4. [Fourth key point]
	5. [Fifth key point]

	**Entities identified**: [List]
	**Concepts identified**: [List]

	Questions:
	- Should I emphasize [aspect A] or [aspect B]?
	- Any specific connections to highlight?
	```

4. After confirmation: read relevant existing Pages (index/index_XXX.md and up to 5 candidate pages at once) to identify where to create or update content.
5. Create/update Pages:
	- Create source summary at `wiki/sources/[kebab-case-title].md` using the Source Page Template.
	- For each identified entity, create or update `wiki/entities/[entity-name].md` using the Entity Page Template; add the source to "Mentions in Sources" and update related concepts.
	- For each identified concept, create or update `wiki/concepts/[concept-name].md` using the Concept Page Template; add the source and update related entities/related pages.
	- Maintain bidirectional links: when linking Page A → Page B, also add Page B → Page A with context.
6. Update index:
	- Read current `index/index_XXX.md` and add entries under Entities, Concepts, Sources as needed (one-line descriptions and metadata).
	- Check token estimates; if an index exceeds limits, split following the index-update rules (create `index_XXX+1.md`, move newest ~2000 tokens, add navigation links).
7. Append a log entry to `log.md` using the ingest template:

	```markdown
	## [YYYY-MM-DD HH:MM] ingest | [Source Title]

	Processed raw/[filename] into wiki.

	Pages created:
	- [wiki/sources/source-name.md](wiki/sources/source-name.md)
	- [wiki/entities/entity-name.md](wiki/entities/entity-name.md)
	- [wiki/concepts/concept-name.md](wiki/concepts/concept-name.md)

	Pages updated:
	- [wiki/entities/existing-entity.md](wiki/entities/existing-entity.md)
	- [wiki/concepts/existing-concept.md](wiki/concepts/existing-concept.md)

	Key outcomes:
	- Identified X new entities, Y new concepts
	- Created Z cross-references
	- Updated index with N new entries
	```

8. Present a concise summary to the User with created/updated pages and statistics.

Quality checklist:
- All new pages include title, summary, sources, cross-references, timestamp.
- Links use relative paths and are bidirectional.
- Index updated and log entry appended.
- Templates used: Source, Entity, Concept (see .copilot/commands/create-page.md for templates).
