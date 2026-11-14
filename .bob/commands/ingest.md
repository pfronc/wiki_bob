# Command: ingest

Usage: `/ingest [source-file]`

Purpose: Process a supported raw source file from `raw/` into structured wiki
pages, update the index, and append a log entry. Supported inputs are Markdown,
UTF-8 text, PDF (via `pypdf`), DOCX (via `python-docx`), and Jupyter notebooks
(`.ipynb`, stdlib JSON with per-cell units).

Inputs:
- `source-file` is a supported filename located in `raw/`.
- `--max-chunks N` optionally bounds extraction work. Repeating the ingest
  resumes at the first pending chunk. Progress state lives in
  `index/extractions/[source-id]/`, not on the source page.

Procedure:
1. Reject unsupported formats, then reconcile `index/source-registry.json` by
   SHA-256. Preserve stable IDs across unique renames, changed-source history,
   and exact-content duplicate relationships.
2. Extract Markdown/text by section or block, PDF by page, and DOCX by heading
   section. Persist stable chunks and source coordinates beneath
   `index/extractions/[source-id]/`. Failed extraction creates no wiki page.
3. Run the resumable extraction pass. If bounded work stops early, mark the
   ingest `partial` and clearly label the source page as incomplete.
4. Present chunk progress, the extraction artifact location, and key takeaways
   to the User and request confirmation before creating or updating canonical
   entity and concept pages. Consult chunk text in
   `index/extractions/[source-id]/` directly; source pages no longer carry a
   per-page Source Map ledger or keyword candidate lists.
5. After confirmation, read the index and up to five candidate pages at once.
6. Process selected chunks into source, entity, and concept pages. Maintain
   bidirectional contextual links. For PDF sources, cite page locations with
   Markdown-format links whose target is the raw file, pathed relative to the
   citing file (from `wiki/concepts/`, `wiki/entities/`, `wiki/sources/`, or
   `wiki/analyses/` that prefix is `../../raw/`):
   `[p. N](../../raw/OriginalFilename.pdf#page=N)` (single page) or
   `[pp. N–M](../../raw/OriginalFilename.pdf#page=N)` (range, linked to first
   page). The `#page=N` anchor jumps to the page in Obsidian (PDF++ installed);
   in VS Code the same link opens the PDF but its viewers start at page 1, so
   always keep the page number in the link text.
   For non-PDF sources, use section headings, timestamps, or chunk IDs.
7. For changed content, preserve the prior source page and registry version.
8. Ensure every generated source page has the shared Obsidian frontmatter plus
   `ingest_status`, `extraction_status`, `source_type`, `author`, and `year`.
   Keep `source_ids` synchronized with the registry-backed source ID. Bases are
   a review interface and never replace registry state.
9. Update the index with paths relative to `index/`; split oversized indices
   using the index-update rules.
10. Expand the runner log stub into a substantive ingest entry.
11. Report created/updated pages, chunk progress, and extraction status.

Quality checklist:
- New pages include a title, summary, Sources, Related Pages, and timestamp.
- Claims derived from PDF sources use Markdown-format PDF links (`[p. N](../../raw/File.pdf#page=N)`, target pathed relative to the citing file); non-PDF sources cite a section heading, timestamp, or chunk ID.
- Links are relative to the containing file and bidirectional where relevant.
- All mathematical expressions use LaTeX: inline `$…$` for in-text math, display `$$…$$` for standalone equations. Never use code spans or code blocks for math.
- Index and log are updated after enrichment.
- Templates are defined in `.bob/commands/create-page.md`.
