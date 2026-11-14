# Command: lint

Usage: `/lint`

Purpose: Produce a deterministic, read-only health report for the managed wiki,
generated indices, source registry, and persisted extraction state.

## Procedure

1. Run `bob lint` from the repository root.
2. Review the summary counts and paths in all eleven report categories:
   - broken or malformed links in wiki Markdown and generated indices;
   - page schema, frontmatter, required sections, and timestamps;
   - literal pipes inside table-cell math (`$...$`) that break table rendering;
   - missing, duplicate, stale, or incorrectly ordered index entries;
   - managed pages with no inbound wiki link;
   - `Related Pages` links without reciprocal `Related Pages` context;
   - duplicate normalized titles, canonical titles, or aliases;
   - claims or citations without a resolvable source page and location;
   - raw files whose current SHA-256 differs from the registry;
   - managed pages over 5,000 estimated tokens, indices over 10,000, or
     persisted chunks over the configured chunk limit;
   - persisted extraction chunks that have not been mapped.
3. Review contradictions, staleness, missing concepts, and semantic index
   descriptions manually; deterministic lint does not infer these safely.
4. Return the report inline by default. Preserve a report in `wiki/analyses/`
   only when it has durable value or the user requests preservation.
5. Propose repairs and obtain user direction before changing claims, merging
   pages, deleting duplicates, or reorganizing ambiguous relationships.
6. Treat `Oversized files` as an advisory review prompt. Report which pages exceed
   the threshold and what drives each size, then offer the user the options —
   accept the warning (the default), raise `PAGE_WARNING_TOKENS` (a runner change;
   follow `AGENTS.md` section 12 first), or split an over-broad page. Do not begin
   compacting pages to satisfy the number, and never remove citations to reduce it.
7. If fixes are approved, apply them, rebuild the index once, rerun lint, and
   append a substantive `lint` or `fix` entry to `log.md`.

## Operational guarantees

- `bob lint` does not write the registry, pages, indices, extraction state, or
  log and returns success when a report was produced, even when issues exist.
- A missing `wiki/` directory is a command failure and returns a non-zero code.
- Paths and counts are deterministic so repeated reports can be compared.
- Index files use the 10,000-token hard limit; managed pages use a 5,000-token
  review threshold; extraction chunks use the runner's configured character
  limit.

## Quality checklist

- [ ] Every category appears with an actionable count.
- [ ] Every issue includes a repository-relative path and explanation.
- [ ] Semantic findings are clearly distinguished from deterministic checks.
- [ ] No remediation occurs without explicit user direction.
