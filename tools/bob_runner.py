#!/usr/bin/env python3
"""Simple Bob runner to map slash-commands to .bob/commands and perform basic workflows.

Usage examples:
  python tools/bob_runner.py ingest --source example.md
  python tools/bob_runner.py query --question "What is transformer"
  python tools/bob_runner.py create-page --type concept --title "My Concept" --filename my-concept.md

This runner is intentionally minimal and safe: it creates source/entity/concept pages
using templates and updates `index_001.md` and `log.md` in a best-effort way.
"""
import argparse
import datetime
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def kebab(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_file(path, content):
    with open(path, "a", encoding="utf-8") as f:
        f.write(content)


def find_index_file():
    """Return the path to the highest-numbered index file (e.g. index_002.md
    rather than index_001.md) so that ingest inserts into the most-recently
    created index after a split, not the oldest one."""
    idx_dir = os.path.join(ROOT, "index")
    if not os.path.isdir(idx_dir):
        return None
    entries = sorted([p for p in os.listdir(idx_dir) if p.startswith("index_") and p.endswith(".md")])
    if not entries:
        return None
    return os.path.join(idx_dir, entries[-1])


def update_index_with_source(title, relpath):
    idx = find_index_file()
    if not idx:
        print("No index file found; skipping index update.")
        return
    text = read_file(idx)
    marker = "## Sources"
    insert = f"- [{title}]({relpath}) - {datetime.date.today().isoformat()}, auto-ingest\n"
    if marker in text:
        parts = text.split(marker)
        before = parts[0] + marker + "\n"
        after = parts[1]
        # insert after marker
        new = before + insert + after
        write_file(idx, new)
        print(f"Updated index: {idx}")
    else:
        # append at end
        append_file(idx, "\n## Sources\n" + insert)
        print(f"Appended Sources section to index: {idx}")


def append_log(operation, title, pages_created=None, pages_updated=None):
    logp = os.path.join(ROOT, "log.md")
    ts = now_iso()
    entry = f"## [{ts}] {operation} | {title}\n\n"
    entry += "Brief: automated by bob_runner.py\n\n"
    if pages_created:
        entry += "Pages created:\n"
        for p in pages_created:
            entry += f"- [{p}]({p})\n"
        entry += "\n"
    if pages_updated:
        entry += "Pages updated:\n"
        for p in pages_updated:
            entry += f"- [{p}]({p})\n"
        entry += "\n"
    entry += "Key outcomes:\n- automated operation\n\n"
    append_file(logp, entry)
    print(f"Appended log entry to {logp}")


def ingest_action(source):
    rawp = os.path.join(ROOT, "raw", source)
    if not os.path.isfile(rawp):
        print(f"Source file not found: {rawp}")
        return 1
    content = read_file(rawp)
    # try to get title from first markdown heading
    m = re.search(r"^#\s+(.*)$", content, re.MULTILINE)
    if m:
        title = m.group(1).strip()
    else:
        title = os.path.splitext(os.path.basename(source))[0]
    slug = kebab(title)
    target_rel = f"wiki/sources/{slug}.md"
    target = os.path.join(ROOT, target_rel)
    if os.path.exists(target):
        print(f"Target exists: {target}; will not overwrite. Creating with timestamp suffix.")
        ts = datetime.datetime.now().strftime("%Y%m%d%H%M%S")
        target = os.path.join(ROOT, f"wiki/sources/{slug}-{ts}.md")
        target_rel = os.path.relpath(target, ROOT)
    summary = (content.strip().splitlines()[:10])
    summary_text = "\n".join(summary)
    md = []
    md.append(f"# Source: {title}\n")
    md.append(f"**Type**: Article\n")
    md.append(f"**Date**: {datetime.date.today().isoformat()}\n")
    md.append(f"**Author**: (unknown)\n")
    md.append(f"**Original location**: raw/{source}\n\n")
    md.append("## Summary\n")
    md.append(summary_text + "\n\n")
    md.append("## Key Takeaways\n- (add takeaways)\n\n")
    md.append("## Entities Mentioned\n- (add entities)\n\n")
    md.append("## Concepts Discussed\n- (add concepts)\n\n")
    md.append(f"---\n*Ingested: {datetime.date.today().isoformat()}*\n")
    write_file(target, "\n".join(md))
    print(f"Created source page: {target_rel}")
    index_rel = "../" + target_rel
    update_index_with_source(title, index_rel)
    append_log("ingest", title, pages_created=[target_rel])
    return 0


def query_action(question):
    # Very simple: search index for matching titles and print candidate pages
    idx = find_index_file()
    if not idx:
        print("No index file found.")
        return 1
    text = read_file(idx)
    # naive search: find lines containing question keywords
    keywords = [w.lower() for w in re.findall(r"\w+", question) if len(w) > 1]
    matches = []
    for line in text.splitlines():
        ll = line.lower()
        if any(k in ll for k in keywords) and line.startswith("- "):
            matches.append(line)
    if not matches:
        print("No obvious matches in index. Try a broader query.")
        return 0
    print("Candidates from index:")
    for m in matches[:10]:
        print(m)
    return 0


def create_page_action(ptype, title, filename):
    if ptype not in ("entity", "concept", "source", "analysis"):
        print("Unknown page type. Use entity|concept|source|analysis")
        return 1
    if not filename:
        filename = kebab(title) + ".md"
    rel = os.path.join("wiki", ptype + "s", filename)
    path = os.path.join(ROOT, rel)
    if os.path.exists(path):
        print(f"File exists: {rel}; will not overwrite.")
        return 1
    md = [f"# {title}\n"]
    if ptype == "entity":
        md += ["**Type**: Person | Organization | Product | Location\n", "**First mentioned**: User-created\n\n", "## Summary\nOne paragraph overview.\n\n", "## Key Information\n- Attribute: Value\n\n", "## Mentions in Sources\n- (add)\n\n", "---\n*Last updated: " + datetime.date.today().isoformat() + "*\n"]
    elif ptype == "concept":
        md += ["**Category**: Theory | Method | Framework | Principle\n", "**First introduced**: User-created\n\n", "## Definition\n1-2 sentence definition.\n\n", "## Explanation\nDetails...\n\n", "---\n*Last updated: " + datetime.date.today().isoformat() + "*\n"]
    elif ptype == "source":
        md += ["**Type**: Article\n", "**Date**: " + datetime.date.today().isoformat() + "\n", "**Author**: (unknown)\n", "**Original location**: raw/\n\n", "## Summary\n\n", "---\n*Ingested: " + datetime.date.today().isoformat() + "*\n"]
    else:
        md += ["**Type**: Analysis\n", "**Date**: " + datetime.date.today().isoformat() + "\n\n", "## Question\n\n", "## Answer\n\n", "## Sources Consulted\n\n", "---\n*Created: " + datetime.date.today().isoformat() + "*\n"]
    write_file(path, "\n".join(md))
    append_log("create-page", title, pages_created=[rel])
    print(f"Created page: {rel}")
    return 0


def lint_action():
    problems = []
    wiki_dir = os.path.join(ROOT, "wiki")
    link_re = re.compile(r'\[[^\]]*\]\(([^)]+)\)')
    for root, dirs, files in os.walk(wiki_dir):
        for f in files:
            if not f.endswith('.md'):
                continue
            p = os.path.join(root, f)
            txt = read_file(p)
            if not re.search(r"^# ", txt, re.MULTILINE):
                problems.append((p, "Missing title heading"))
            if "Last updated" not in txt and "Ingested" not in txt and "Created:" not in txt:
                problems.append((p, "Missing timestamp/metadata"))
            for target in link_re.findall(txt):
                # Skip external URLs and fragment-only anchors
                if target.startswith("http") or target.startswith("#"):
                    continue
                # Strip any in-page fragment before resolving
                path_part = target.split("#")[0]
                if not path_part:
                    continue
                resolved = os.path.normpath(os.path.join(os.path.dirname(p), path_part))
                if not os.path.exists(resolved):
                    problems.append((p, f"Broken link: {target}"))
    if not problems:
        print("Lint: no obvious issues found.")
    else:
        print("Lint issues:")
        for p, msg in problems:
            print(f"- {os.path.relpath(p, ROOT)}: {msg}")
    return 0


def research_action():
    print(
        "research is an agent-only operation — no scaffolding is generated by the runner.\n"
        "Follow the procedure at .bob/commands/research.md to conduct a research session."
    )
    return 0


def status_action():
    """Print an orientation snapshot: page counts, uningested raw files,
    recent log entries, and index health."""

    # (a) Count .md files per wiki subdirectory, skipping .obsidian
    wiki_dir = os.path.join(ROOT, "wiki")
    counts = {}
    for subdir in ("entities", "concepts", "sources", "analyses"):
        d = os.path.join(wiki_dir, subdir)
        if os.path.isdir(d):
            counts[subdir] = len([f for f in os.listdir(d) if f.endswith(".md")])
        else:
            counts[subdir] = 0
    total = sum(counts.values())

    print("=== Wiki Pages ===")
    for cat in ("entities", "concepts", "sources", "analyses"):
        print(f"  {cat:<12} {counts[cat]}")
    print(f"  {'total':<12} {total}")
    print()

    # (b) Uningested raw/ files
    raw_dir = os.path.join(ROOT, "raw")
    sources_dir = os.path.join(wiki_dir, "sources")
    uningested = []
    if os.path.isdir(raw_dir):
        for fname in sorted(os.listdir(raw_dir)):
            fpath = os.path.join(raw_dir, fname)
            if not os.path.isfile(fpath):
                continue
            slug = kebab(os.path.splitext(fname)[0])
            if not os.path.exists(os.path.join(sources_dir, slug + ".md")):
                uningested.append(fname)

    print("=== Uningested raw/ files ===")
    if uningested:
        for f in uningested:
            print(f"  {f}")
    else:
        print("  (none — all raw files have a matching source page)")
    print()

    # (c) Last 3 log entries
    logp = os.path.join(ROOT, "log.md")
    recent = []
    if os.path.isfile(logp):
        for line in open(logp, encoding="utf-8"):
            if line.startswith("## ["):
                recent.append(line.strip())
    recent = recent[-3:]

    print("=== Recent Log Entries ===")
    if recent:
        for entry in recent:
            print(f"  {entry}")
    else:
        print("  (no log entries yet)")
    print()

    # (d) Index health
    idx = find_index_file()
    print("=== Index Health ===")
    if not idx:
        print("  No index file found.")
    else:
        idx_text = open(idx, encoding="utf-8").read()
        word_count = len(idx_text.split())
        token_est = int(word_count / 0.75)
        rel = os.path.relpath(idx, ROOT)
        warning = "  ⚠  NEAR LIMIT — consider splitting" if token_est > 8000 else ""
        print(f"  File    : {rel}")
        print(f"  Tokens  : ~{token_est}{warning}")
        print(f"  Limit   : 10 000 tokens")
    print()

    return 0


def raw_list_action(pending_only=False):
    """List files in raw/ with size and mtime, showing ingest status."""
    raw_dir = os.path.join(ROOT, "raw")
    sources_dir = os.path.join(ROOT, "wiki", "sources")

    if not os.path.isdir(raw_dir):
        print("raw/ directory not found.")
        return 1

    files = sorted(
        f for f in os.listdir(raw_dir)
        if os.path.isfile(os.path.join(raw_dir, f))
    )

    if not files:
        print("raw/ is empty.")
        return 0

    pending = []
    ingested = []
    for fname in files:
        fpath = os.path.join(raw_dir, fname)
        slug = kebab(os.path.splitext(fname)[0])
        is_ingested = os.path.exists(os.path.join(sources_dir, slug + ".md"))
        stat = os.stat(fpath)
        size_kb = stat.st_size / 1024
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        entry = (fname, size_kb, mtime, is_ingested)
        if is_ingested:
            ingested.append(entry)
        else:
            pending.append(entry)

    def print_entry(fname, size_kb, mtime, is_ingested):
        size_str = f"[{size_kb:>6.1f} KB]"
        status = "[ingested]" if is_ingested else ""
        print(f"  {fname:<40} {size_str}  {mtime}  {status}".rstrip())

    if pending:
        print("=== Pending (not yet ingested) ===")
        for entry in pending:
            print_entry(*entry)
        print()

    if not pending_only and ingested:
        print("=== Ingested ===")
        for entry in ingested:
            print_entry(*entry)
        print()

    if not pending and not pending_only:
        print("All raw/ files have been ingested.")

    if pending_only and not pending:
        print("No pending files in raw/.")

    return 0


def extract_page_meta(path):
    """Read a wiki .md file and return (title, first_sentence, page_type).

    - title: text of the first '# ' heading.
    - first_sentence: first non-empty line of content after the ## Summary
      heading (if present), otherwise the first non-empty line that is not a
      heading, badge, or front-matter separator.
    - page_type: inferred from the immediate parent directory name
      (entities | concepts | sources | analyses).
    """
    try:
        txt = read_file(path)
    except OSError:
        return None, None, None

    # page_type from parent dir
    page_type = os.path.basename(os.path.dirname(path))

    # title from first '# ' heading
    title = None
    for line in txt.splitlines():
        m = re.match(r"^#\s+(.+)$", line)
        if m:
            title = m.group(1).strip()
            break
    if not title:
        title = os.path.splitext(os.path.basename(path))[0]

    # first_sentence: prefer content after ## Summary, else first plain line
    lines = txt.splitlines()
    first_sentence = ""

    # try to find ## Summary block first
    in_summary = False
    for line in lines:
        if re.match(r"^##\s+Summary", line, re.IGNORECASE):
            in_summary = True
            continue
        if in_summary:
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and stripped != "---":
                # strip markdown bold/italic markers and link syntax
                clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
                clean = re.sub(r"[*_`]", "", clean)
                first_sentence = clean[:120]
                break
            if stripped.startswith("##"):
                break  # moved past the Summary section

    if not first_sentence:
        # fall back: first non-empty, non-heading, non-badge line
        for line in lines:
            stripped = line.strip()
            if (
                stripped
                and not stripped.startswith("#")
                and not stripped.startswith("**")
                and not stripped.startswith("---")
                and not stripped.startswith("*Ingested")
                and not stripped.startswith("*Last")
                and not stripped.startswith("*Created")
            ):
                clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
                clean = re.sub(r"[*_`]", "", clean)
                first_sentence = clean[:120]
                break

    return title, first_sentence, page_type


def index_update_action():
    """Rebuild the four index sections from disk, updating header metadata."""
    idx = find_index_file()
    if not idx:
        print("No index file found; creating index/index_001.md")
        idx = os.path.join(ROOT, "index", "index_001.md")
        write_file(
            idx,
            f"# Wiki Index [001]\n\nLast updated: {datetime.date.today().isoformat()}\n"
            "Total Pages: 0\nToken count: ~0\n\n"
            "## Entities\n\n## Concepts\n\n## Sources\n\n## Analyses\n",
        )

    # Walk wiki/, skip .obsidian subtree, collect pages by type
    wiki_dir = os.path.join(ROOT, "wiki")
    buckets = {"entities": [], "concepts": [], "sources": [], "analyses": []}

    for dirpath, dirnames, filenames in os.walk(wiki_dir):
        # prune hidden / obsidian dirs in-place so os.walk skips them
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in sorted(filenames):
            if not fname.endswith(".md"):
                continue
            full = os.path.join(dirpath, fname)
            title, first_sentence, page_type = extract_page_meta(full)
            if page_type not in buckets:
                continue
            # path relative to index/ dir  → ../wiki/{type}/{file}
            rel_from_index = "../" + os.path.relpath(full, ROOT).replace("\\", "/")
            desc = first_sentence if first_sentence else "(no description)"
            entry = f"- [{title}]({rel_from_index}) - {desc}"
            buckets[page_type].append(entry)

    total_pages = sum(len(v) for v in buckets.values())

    # Read existing index to preserve header and footer
    existing = read_file(idx)
    ex_lines = existing.splitlines(keepends=True)

    # Identify the line index of the first section heading and the last line of
    # the ## Analyses section so we can keep everything before and after.
    section_headings = {"## Entities", "## Concepts", "## Sources", "## Analyses"}
    first_section_lineno = None
    for i, line in enumerate(ex_lines):
        if line.strip() in section_headings:
            first_section_lineno = i
            break

    # Everything after ## Analyses section (navigation links, trailing notes)
    footer_lines = []
    in_analyses = False
    analyses_ended_at = None
    for i, line in enumerate(ex_lines):
        if line.strip() == "## Analyses":
            in_analyses = True
            continue
        if in_analyses and line.strip().startswith("## "):
            # another section after Analyses — treat rest as footer
            analyses_ended_at = i
            break
        if in_analyses and line.strip().startswith("---"):
            analyses_ended_at = i
            break
    if analyses_ended_at is not None:
        footer_lines = ex_lines[analyses_ended_at:]

    # Build header block: preserve original lines up to (not including) first section
    if first_section_lineno is not None:
        header_lines = ex_lines[:first_section_lineno]
    else:
        # No sections found — preserve entire existing content as header
        header_lines = ex_lines

    # Update header fields in-place
    today = datetime.date.today().isoformat()
    # Estimate token count from word count of all wiki pages
    all_words = 0
    for dirpath, dirnames, filenames in os.walk(wiki_dir):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fname in filenames:
            if fname.endswith(".md"):
                try:
                    content = read_file(os.path.join(dirpath, fname))
                    all_words += len(content.split())
                except OSError:
                    pass
    token_estimate = int(all_words / 0.75)

    new_header = []
    for line in header_lines:
        if re.match(r"^Last updated:", line):
            new_header.append(f"Last updated: {today}\n")
        elif re.match(r"^Total Pages:", line):
            new_header.append(f"Total Pages: {total_pages}\n")
        elif re.match(r"^Token count:", line):
            new_header.append(f"Token count: ~{token_estimate}\n")
        else:
            new_header.append(line)
    # If header fields were absent, append them before the sections
    field_lines = "".join(new_header)
    if "Last updated:" not in field_lines:
        new_header.append(f"Last updated: {today}\n")
    if "Total Pages:" not in field_lines:
        new_header.append(f"Total Pages: {total_pages}\n")
    if "Token count:" not in field_lines:
        new_header.append(f"Token count: ~{token_estimate}\n")

    # Build the four sections
    def build_section(heading, entries):
        lines = [f"{heading}\n"]
        if entries:
            for e in entries:
                lines.append(e + "\n")
        else:
            lines.append(f"*No {heading[3:].lower()} yet.*\n")
        lines.append("\n")
        return lines

    body = []
    body += build_section("## Entities", buckets["entities"])
    body += build_section("## Concepts", buckets["concepts"])
    body += build_section("## Sources", buckets["sources"])
    body += build_section("## Analyses", buckets["analyses"])

    new_content = "".join(new_header) + "".join(body) + "".join(footer_lines)
    write_file(idx, new_content)

    print(f"Index updated: {idx}")
    print(f"  Entities : {len(buckets['entities'])}")
    print(f"  Concepts : {len(buckets['concepts'])}")
    print(f"  Sources  : {len(buckets['sources'])}")
    print(f"  Analyses : {len(buckets['analyses'])}")
    print(f"  Total    : {total_pages} pages | ~{token_estimate} tokens")
    return 0


def move_action(from_rel, to_rel):
    """Rename a wiki page and rewrite all inbound links across wiki/ and index/."""
    from_abs = os.path.join(ROOT, from_rel)
    to_abs   = os.path.join(ROOT, to_rel)

    # --- validation ---
    if not os.path.isfile(from_abs):
        print(f"Error: source file does not exist: {from_rel}")
        return 1
    if os.path.exists(to_abs):
        print(f"Error: destination already exists: {to_rel}")
        return 1

    # Ensure the destination directory exists
    os.makedirs(os.path.dirname(to_abs), exist_ok=True)

    # --- rename ---
    os.rename(from_abs, to_abs)
    print(f"Renamed: {from_rel} → {to_rel}")

    # --- rewrite inbound links in wiki/ and index/ ---
    updated_files = []
    search_dirs = [
        os.path.join(ROOT, "wiki"),
        os.path.join(ROOT, "index"),
    ]
    for search_dir in search_dirs:
        if not os.path.isdir(search_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(search_dir):
            # skip .obsidian inside wiki/
            dirnames[:] = [d for d in dirnames if d != ".obsidian"]
            for fname in filenames:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(dirpath, fname)
                # skip the file we just renamed (it's at to_abs)
                if os.path.abspath(fpath) == os.path.abspath(to_abs):
                    continue
                file_dir = os.path.dirname(fpath)
                # compute what the old path looks like relative to this file
                old_rel_from_file = os.path.relpath(from_abs, file_dir)
                new_rel_from_file = os.path.relpath(to_abs,   file_dir)
                content = read_file(fpath)
                if old_rel_from_file in content:
                    new_content = content.replace(old_rel_from_file, new_rel_from_file)
                    write_file(fpath, new_content)
                    updated_files.append(os.path.relpath(fpath, ROOT))
                    print(f"  Updated links in: {os.path.relpath(fpath, ROOT)}")

    # --- log ---
    append_log("fix", f"move {from_rel} → {to_rel}", pages_updated=[to_rel] + updated_files)
    print(f"\nDone. {len(updated_files)} file(s) had links updated.")
    return 0


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', help='slash command (ingest|query|create-page|lint|index-update|research|status|raw-list|move)')
    p.add_argument('--source', help='source filename for ingest (relative to raw/)')
    p.add_argument('--question', help='question for query')
    p.add_argument('--type', help='page type for create-page')
    p.add_argument('--title', help='title for create-page')
    p.add_argument('--filename', help='filename for create-page')
    p.add_argument('--pending-only', action='store_true', help='raw-list: show only uningested files')
    p.add_argument('--from', dest='from_rel', help='move: source path (relative to repo root)')
    p.add_argument('--to',   dest='to_rel',   help='move: destination path (relative to repo root)')
    args = p.parse_args()

    cmd = args.command.lstrip('/').lower()
    if cmd == 'ingest':
        if not args.source:
            print('ingest requires --source')
            sys.exit(1)
        sys.exit(ingest_action(args.source))
    elif cmd == 'query':
        if not args.question:
            print('query requires --question')
            sys.exit(1)
        sys.exit(query_action(args.question))
    elif cmd == 'create-page':
        if not args.type or not args.title:
            print('create-page requires --type and --title')
            sys.exit(1)
        sys.exit(create_page_action(args.type, args.title, args.filename))
    elif cmd == 'lint':
        sys.exit(lint_action())
    elif cmd == 'index-update':
        sys.exit(index_update_action())
    elif cmd == 'research':
        sys.exit(research_action())
    elif cmd == 'status':
        sys.exit(status_action())
    elif cmd == 'raw-list':
        sys.exit(raw_list_action(pending_only=args.pending_only))
    elif cmd == 'move':
        if not args.from_rel or not args.to_rel:
            print('move requires --from and --to')
            sys.exit(1)
        sys.exit(move_action(args.from_rel, args.to_rel))
    else:
        print('Unknown command:', cmd)
        sys.exit(2)


if __name__ == '__main__':
    main()
