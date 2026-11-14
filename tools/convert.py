#!/usr/bin/env python3
"""Convert documents the Bob runner cannot read into Markdown for ingestion.

The runner natively ingests Markdown, UTF-8 text, PDF (pypdf), DOCX
(python-docx), and Jupyter notebooks (stdlib JSON). This helper covers the
formats it cannot: presentations, workbooks, HTML, EPUB, feeds, and plain data
files. Output is written to a staging
directory (`index/converted/` by default) because `raw/` is user-managed; move the
result into `raw/` yourself and then run `bob ingest --source <file>.md`.

Usage examples:
  python3 tools/convert.py formats
  python3 tools/convert.py convert --source slides.pptx
  python3 tools/convert.py convert --source page.html --stdout

Conversion is deliberately NOT used for PDF: the runner's page-level extraction
preserves the `p. N` locators that citations depend on, while Markdown conversion
produces one flat stream with no page boundaries.
"""
import argparse
import importlib
import os
import re
import sys

ROOT = os.path.abspath(
    os.environ.get("BOB_RAG_ROOT")
    or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
STAGING_REL = "index/converted"
MISSING_MARKITDOWN = "markitdown is not installed: pip install markitdown"

# Formats the runner already handles natively; convert refuses them.
RUNNER_NATIVE = {".md", ".markdown", ".txt", ".pdf", ".docx", ".ipynb"}

# Formats Markdown conversion is appropriate for, mapped to the extra they need.
FORMATS = {
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".xls": "xls",
    ".html": None,
    ".htm": None,
    ".epub": None,
    ".csv": None,
    ".json": None,
    ".xml": None,
    ".rss": None,
    ".msg": "outlook",
    ".zip": None,
}
EXTRA_MODULE = {"pptx": "pptx", "xlsx": "openpyxl", "xls": "xlrd", "outlook": "olefile"}
EXTRA_HINT = {
    "pptx": "pip install 'markitdown[pptx]'",
    "xlsx": "pip install 'markitdown[xlsx]'",
    "xls": "pip install 'markitdown[xls]'",
    "outlook": "pip install 'markitdown[outlook]'",
}


def display_path(path):
    return path.replace("\\", "/")


def configure_console():
    """Make console output robust for Unicode conversion output."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if stream is None or not reconfigure:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (LookupError, ValueError):
            reconfigure(errors="replace")


def kebab(text):
    """Mirror the runner's filename normalisation."""
    text = text.strip().lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s]+", "-", text)
    return re.sub(r"-+", "-", text).strip("-")


def load_markitdown():
    """Return the MarkItDown class, or None when the package is unavailable."""
    try:
        module = importlib.import_module("markitdown")
    except ImportError:
        return None
    return getattr(module, "MarkItDown", None)


def missing_dependency_hint(exc):
    """Extract the actionable install hint from a markitdown dependency error."""
    message = str(exc)
    match = re.search(r"pip install '?([^'\s]+)'?", message)
    return f"pip install {match.group(1)}" if match else MISSING_MARKITDOWN


def looks_like_raw_binary(text, extension):
    """Detect markitdown's plain-text fallback swallowing a binary document."""
    if extension in {".csv", ".json", ".xml", ".rss", ".txt"}:
        return False
    control = sum(1 for char in text[:4000] if ord(char) < 9 or 13 < ord(char) < 32)
    if control > 40:
        return True
    return bool(text[:4] == "PK\x03\x04" or text.lstrip().startswith("%PDF"))


def relative_display(path):
    """Show repo-relative paths inside the repo, absolute paths outside it."""
    absolute = os.path.abspath(path)
    if absolute.startswith(ROOT + os.sep):
        return display_path(os.path.relpath(absolute, ROOT))
    return display_path(absolute)


def convert_file(path, markitdown_class):
    """Return (markdown_text, error_message, used_fallback)."""
    extension = os.path.splitext(path)[1].lower()
    converter = markitdown_class()
    try:
        result = converter.convert(path)
    except Exception as exc:  # noqa: BLE001 - surfaced to the user verbatim
        if type(exc).__name__ == "MissingDependencyException":
            return None, missing_dependency_hint(exc), False
        first = str(exc).splitlines()[0] if str(exc) else type(exc).__name__
        return None, f"{type(exc).__name__}: {first}", False
    text = (getattr(result, "text_content", "") or "").strip()
    if not text:
        return None, "conversion produced no text", False
    if looks_like_raw_binary(text, extension):
        return text, None, True
    return text, None, False


def bodies_for(source):
    """List candidate input files for a source path (single file or directory)."""
    if os.path.isdir(source):
        found = []
        for dirpath, dirnames, filenames in os.walk(source):
            dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
            found.extend(os.path.join(dirpath, name) for name in sorted(filenames))
        return found
    return [source]


def formats_action():
    """Report which formats are convertible with the current dependencies."""
    markitdown_class = load_markitdown()
    print(f"markitdown: {'installed' if markitdown_class else 'MISSING'}")
    print(f"staging directory: {STAGING_REL}/")
    print()
    print(f"{'extension':<10} {'status':<10} note")
    for extension in sorted(FORMATS):
        extra = FORMATS[extension]
        if extension in RUNNER_NATIVE:
            status, note = "runner", "handled natively by 'bob ingest'"
        elif not markitdown_class:
            status, note = "blocked", MISSING_MARKITDOWN
        elif extra is None:
            status, note = "ready", ""
        else:
            try:
                importlib.import_module(EXTRA_MODULE[extra])
            except ImportError:
                status = "needs dep"
                note = EXTRA_HINT.get(extra, MISSING_MARKITDOWN)
            else:
                status, note = "ready", ""
        print(f"{extension:<10} {status:<10} {note}")
    print()
    print("PDF is intentionally excluded: citations need page locators (p. N).")
    return 0


def convert_action(source, out_dir, to_stdout, overwrite):
    """Convert a file (or directory of files) into staged Markdown."""
    if not os.path.exists(source):
        print(f"Error: source not found: {display_path(source)}")
        return 1
    markitdown_class = load_markitdown()
    if markitdown_class is None:
        print(f"Error: {MISSING_MARKITDOWN}")
        return 3

    targets = []
    for path in bodies_for(source):
        extension = os.path.splitext(path)[1].lower()
        if not extension:
            continue
        if extension in RUNNER_NATIVE:
            reason = {
                ".pdf": ("PDF stays with the runner so page locators (p. N) survive "
                         "for citations: bob ingest --source <file>.pdf"),
                ".docx": "DOCX is handled natively: bob ingest --source <file>.docx",
                ".ipynb": "IPYNB is handled natively: bob ingest --source <file>.ipynb",
            }.get(extension, f"{extension} is already ingestable: bob ingest --source <file>")
            print(f"skip {display_path(path)}: {reason}")
            continue
        if extension not in FORMATS:
            print(f"skip {display_path(path)}: unsupported format {extension}")
            continue
        targets.append(path)

    if not targets:
        print("Nothing to convert.")
        return 1

    staging = os.path.join(ROOT, *STAGING_REL.split("/"))
    failures = 0
    written = []
    for path in targets:
        relative = display_path(os.path.relpath(path, ROOT))
        extension = os.path.splitext(path)[1].lower()
        text, error, used_fallback = convert_file(path, markitdown_class)
        if error:
            print(f"FAIL {relative}: {error}")
            failures += 1
            continue
        if used_fallback:
            hint = EXTRA_HINT.get(FORMATS.get(extension), MISSING_MARKITDOWN)
            print(f"FAIL {relative}: no structural converter produced text; "
                  f"the file fell back to plain text. Install the format extra: {hint}")
            failures += 1
            continue
        if to_stdout:
            print(f"# source: {relative}\n")
            print(text)
            written.append(relative)
            continue
        name = kebab(os.path.splitext(os.path.basename(path))[0]) or "converted"
        destination = os.path.join(
            out_dir if os.path.isabs(out_dir) else os.path.join(ROOT, out_dir), f"{name}.md"
        )
        if os.path.exists(destination) and not overwrite:
            print(f"skip {destination}: exists (use --overwrite to replace)")
            continue
        os.makedirs(os.path.dirname(destination), exist_ok=True)
        header = (f"<!-- converted from {relative} by tools/convert.py; "
                  f"review before ingesting -->\n\n")
        with open(destination, "w", encoding="utf-8", newline="") as handle:
            handle.write(header + text + "\n")
        written.append(display_path(os.path.relpath(destination, ROOT)))
        print(f"OK   {relative} -> {display_path(os.path.relpath(destination, ROOT))} "
              f"({len(text)} chars)")

    if written and not to_stdout:
        print()
        print("Next steps (raw/ is user-managed, so move the file yourself):")
        for entry in written:
            name = os.path.basename(entry)
            print(f"  mv {entry} raw/{name} && python3 tools/bob_runner.py ingest --source {name}")
    return 1 if failures else 0


def main():
    configure_console()
    parser = argparse.ArgumentParser(
        description="Convert formats the Bob runner cannot read into staged Markdown."
    )
    parser.add_argument("command", nargs="?", default="convert",
                        help="convert (default) | formats")
    parser.add_argument("--source", help="convert: file or directory to convert")
    parser.add_argument("--out-dir", default=STAGING_REL,
                        help=f"convert: staging directory (default {STAGING_REL})")
    parser.add_argument("--stdout", action="store_true", help="convert: print instead of writing")
    parser.add_argument("--overwrite", action="store_true", help="convert: replace existing output")
    args = parser.parse_args()

    command = args.command.lstrip("/").lower()
    try:
        if command == "formats":
            return formats_action()
        if command == "convert":
            if not args.source:
                print("convert requires --source")
                return 1
            return convert_action(args.source, args.out_dir, args.stdout, args.overwrite)
        print("Unknown command:", command)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())