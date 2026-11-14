# Command: index-update

Usage: `/index-update`

Purpose: deterministically rebuild all numbered indices and the index manifest
from managed wiki pages.

## Procedure

1. Run `bob index-update`.
2. The runner reads every Markdown page in the managed entity, concept, source,
   and analysis trees. It derives titles, summaries, aliases, topics, update
   dates, and source coverage from page content and frontmatter.
3. The runner sorts entries by category and title, writes index-relative links,
   and partitions entries at approximately 9,000 estimated tokens per part.
   The hard limit is 10,000 estimated tokens.
4. The runner rewrites `index_001.md` through `index_NNN.md`, removes obsolete
   numbered parts, adds Previous/Next/Manifest navigation, and regenerates
   `index/index.md` with every part, count, token estimate, and title span.
5. Review descriptions and metadata for semantic quality. Generated numbered
   indices and the manifest should not be hand-edited.
6. Verify that all managed pages appear once, entries are alphabetical within
   each category, every link resolves, and no part exceeds the hard limit.
7. The runner appends an `index-update` entry to `log.md`; enrich it only when
   substantive manual review or reorganization occurred.

## Generated index format

```markdown
# Wiki Index [001]

Last updated: YYYY-MM-DD
Total Pages: XXX
Pages in part: XXX
Token count: ~XXXX

## Entities
- [Entity Name](../wiki/entities/entity-name.md) - Summary [updated: YYYY-MM-DD; sources: X]

## Concepts
...

---
**Navigation**:
- Manifest: [index.md](index.md)
- Next: [index_002.md](index_002.md)
```

## Quality checklist

- [ ] Every managed page is represented exactly once
- [ ] Entries are alphabetized within categories
- [ ] Paths are relative to `index/` and resolve
- [ ] All numbered parts are listed in `index/index.md`
- [ ] Navigation is correct
- [ ] Each part is below 10,000 estimated tokens
- [ ] Descriptions and source counts are accurate
