# Command: research

Usage: `/research [topic or question]`

Purpose: Combine wiki knowledge with external sources (when allowed) to investigate a topic and synthesize findings.

Procedure:
1. Check the wiki indices (`index/*.md`) for existing material on the topic and identify 5–10 candidate pages.
2. Read candidate wiki pages (up to 5 at once) and extract relevant facts, claims, and citations.
3. If external research is allowed and needed, use browser tools to search for current authoritative information and verify findings across multiple reputable sources. External browsing must follow project policies and user consent.
4. Synthesize findings, combining wiki knowledge and external sources, with clear citations to both wiki pages (paths relative to citing file) and external URLs.
5. Assess preservation value (same criteria as `/query`): preserve when synthesizing 3+ pages, revealing non-obvious connections, comparing concepts/entities, or on user request. Otherwise answer inline only.
6. If preserving, create `wiki/analyses/[descriptive-title].md` with the Analysis Page Template from `.bob/commands/create-page.md` (question, answer, sources consulted, key insights, related analyses), update the index, and append a `query`-style log entry with origin `research`.
