#!/usr/bin/env python3
"""Simple Bob runner to map slash-commands to .bob/commands and perform basic workflows.

Usage examples:
  python tools/bob_runner.py ingest --source example.md
  python tools/bob_runner.py query --question "What is transformer"
  python tools/bob_runner.py create-page --type concept --title "My Concept" --filename my-concept.md

This runner is intentionally focused and safe: it scaffolds managed pages, maintains
source state, and deterministically rebuilds searchable Markdown indices.
"""
import argparse
import collections
import datetime
import hashlib
import importlib
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REGISTRY_REL = "index/source-registry.json"
REGISTRY_SCHEMA_VERSION = 1
EXTRACTION_SCHEMA_VERSION = 1
SUPPORTED_SOURCE_FORMATS = {"md", "txt", "pdf", "docx", "ipynb"}
MAX_CHUNK_CHARS = 4000
SOURCE_MAP_EXCERPT_CHARS = 180
INDEX_TARGET_TOKENS = 9000
INDEX_HARD_LIMIT = 10000
PAGE_WARNING_TOKENS = 5000
INDEX_MANIFEST_REL = "index/index.md"
INDEX_CATEGORIES = ("entities", "concepts", "sources", "analyses")
INDEX_HEADINGS = {
    "entities": "Entities",
    "concepts": "Concepts",
    "sources": "Sources",
    "analyses": "Analyses",
}
MAX_QUERY_CANDIDATES = 10

STOP_WORDS = {
    "about", "after", "also", "because", "been", "before", "being", "between",
    "could", "does", "each", "from", "have", "into", "more", "most", "other",
    "over", "such", "than", "that", "their", "there", "these", "they", "this",
    "through", "under", "using", "very", "were", "what", "when", "where", "which",
    "while", "with", "would", "your",
}

PAGE_TYPE_BY_DIRECTORY = {
    "entities": "entity",
    "concepts": "concept",
    "sources": "source",
    "analyses": "analysis",
}
COMMON_REQUIRED_SECTIONS = {"Summary", "Related Pages", "Sources"}
PAGE_REQUIRED_SECTIONS = {
    "entity": {"Key Information", "Mentions in Sources"},
    "concept": {"Definition", "Explanation", "Key Aspects", "Applications"},
    "source": {"Key Takeaways", "Entities Mentioned", "Concepts Discussed"},
    "analysis": {"Question", "Answer", "Sources Consulted", "Key Insights"},
}
SOURCE_REQUIRED_FIELDS = {
    "Type", "Author", "Original location", "Source ID", "Extraction status",
}
FRONTMATTER_REQUIRED_FIELDS = {
    "kind", "status", "aliases", "topics", "sources", "source_ids",
    "created", "updated", "last_reviewed",
}
FRONTMATTER_LIST_FIELDS = {"aliases", "topics", "sources", "source_ids"}
PAGE_STATUSES = {"draft", "verified", "needs-review", "archived"}
SOURCE_FRONTMATTER_FIELDS = {
    "ingest_status", "extraction_status", "source_type", "author", "year",
}
ENTITY_FRONTMATTER_FIELDS = {"entity_type", "related_concepts"}


def kebab(s: str) -> str:
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9\s-]", "", s)
    s = re.sub(r"[\s]+", "-", s)
    s = re.sub(r"-+", "-", s)
    return s


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def now_timestamp():
    """Return an ISO-8601 timestamp with the local UTC offset."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_file(path):
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def write_file(path, content):
    """Atomically replace a UTF-8 text file."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    content.encode("utf-8")
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", newline="", dir=parent, delete=False
        ) as temp_file:
            temp_path = temp_file.name
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())
        os.replace(temp_path, path)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def display_path(path):
    """Return stable, slash-separated paths for console and Markdown output."""
    return path.replace("\\", "/")


def canonical_key(value):
    """Normalize a title or alias for deterministic identity comparison."""
    return re.sub(r"[^a-z0-9]+", "", value.casefold())


def metadata_value(text, field):
    match = re.search(rf"^\*\*{re.escape(field)}\*\*:\s*(.*?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def frontmatter_metadata(text):
    """Parse the deliberately small YAML subset used by managed wiki pages."""
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end < 0:
        return None
    metadata = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([a-z][a-z0-9_]*)\s*:\s*(.*)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        raw_value = raw_value.strip()
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = None
        elif raw_value == "":
            value = ""
        elif len(raw_value) >= 2 and raw_value[0] == raw_value[-1] == '"':
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = None
        else:
            value = raw_value
        metadata[key] = value
    return metadata


def frontmatter_list(properties, field):
    """Return a frontmatter list while giving static analyzers a stable type."""
    value = properties.get(field)
    return value if isinstance(value, list) else []


def frontmatter(kind, status="draft", aliases=None, topics=None, sources=None,
                source_ids=None, created=None, updated=None, last_reviewed="", **extra):
    """Render stable Obsidian-compatible Properties without a YAML dependency."""
    today = datetime.date.today().isoformat()
    values = {
        "kind": kind,
        "status": status,
        "aliases": aliases or [],
        "topics": topics or [],
        "sources": sources or [],
        "source_ids": source_ids or [],
        "created": created or today,
        "updated": updated or today,
        "last_reviewed": last_reviewed,
    }
    values.update(extra)
    lines = ["---"]
    for key, value in values.items():
        if isinstance(value, list):
            rendered = json.dumps(value, ensure_ascii=False)
        elif value is None or value == "":
            rendered = ""
        else:
            rendered = str(value)
        lines.append(f"{key}: {rendered}")
    lines.extend(["---", ""])
    return "\n".join(lines)


def page_title(text):
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def page_aliases(text):
    properties = frontmatter_metadata(text)
    if properties and isinstance(properties.get("aliases"), list):
        return [str(item).strip() for item in properties["aliases"] if str(item).strip()]
    value = metadata_value(text, "Aliases")
    if not value or value.casefold() in {"(none)", "none", "[]"}:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def identity_matches(title, page_type):
    """Return exact page identities and registry candidates for a proposed page."""
    proposed = canonical_key(title)
    exact = []
    review = []
    wiki_dir = os.path.join(ROOT, "wiki")
    for directory in ("entities", "concepts"):
        candidate_dir = os.path.join(wiki_dir, directory)
        if not os.path.isdir(candidate_dir):
            continue
        for filename in sorted(os.listdir(candidate_dir)):
            if not filename.endswith(".md"):
                continue
            path = os.path.join(candidate_dir, filename)
            text = read_file(path)
            identities = [page_title(text) or "", metadata_value(text, "Canonical title") or ""]
            identities.extend(page_aliases(text))
            if proposed and proposed in {canonical_key(item) for item in identities if item}:
                exact.append(display_path(os.path.relpath(path, ROOT)))
    if page_type in {"entity", "concept", "source"}:
        registry = load_source_registry()
        for record in registry["sources"]:
            candidates = [os.path.splitext(os.path.basename(record["raw_path"]))[0]]
            if record.get("source_page"):
                candidates.append(os.path.splitext(os.path.basename(record["source_page"]))[0])
            if proposed and proposed in {canonical_key(item) for item in candidates}:
                review.append(f"{record['source_id']} ({record['raw_path']})")
    return sorted(set(exact)), sorted(set(review))


def registry_path():
    return os.path.join(ROOT, *REGISTRY_REL.split("/"))


def empty_registry():
    return {"schema_version": REGISTRY_SCHEMA_VERSION, "sources": []}


def load_source_registry():
    """Load and minimally validate the agent-managed source registry."""
    path = registry_path()
    if not os.path.exists(path):
        return empty_registry()
    data = json.loads(read_file(path))
    if not isinstance(data, dict) or data.get("schema_version") != REGISTRY_SCHEMA_VERSION:
        raise ValueError("source registry has an unsupported or missing schema_version")
    if not isinstance(data.get("sources"), list):
        raise ValueError("source registry field 'sources' must be a list")
    required = {"source_id", "raw_path", "sha256", "format", "source_page",
                "extraction_status", "ingest_status", "last_processed"}
    for record in data["sources"]:
        if not isinstance(record, dict) or not required.issubset(record):
            raise ValueError("source registry contains an invalid source record")
    return data


def serialize_registry(registry):
    registry["sources"].sort(key=lambda item: item["source_id"])
    return json.dumps(registry, indent=2, ensure_ascii=True) + "\n"


def hash_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source_file:
        for block in iter(lambda: source_file.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def raw_files():
    """Return (registry path, absolute path) pairs for every file under raw/."""
    raw_dir = os.path.join(ROOT, "raw")
    if not os.path.isdir(raw_dir):
        return []
    files = []
    for dirpath, dirnames, filenames in os.walk(raw_dir):
        dirnames.sort()
        for filename in sorted(filenames):
            absolute = os.path.join(dirpath, filename)
            relative = "raw/" + display_path(os.path.relpath(absolute, raw_dir))
            files.append((relative, absolute))
    return files


def new_source_id(registry, raw_path):
    stem = kebab(os.path.splitext(os.path.basename(raw_path))[0]) or "source"
    base = f"src_{datetime.date.today().strftime('%Y%m%d')}_{stem}"
    used = {record["source_id"] for record in registry["sources"]}
    candidate = base
    suffix = 2
    while candidate in used:
        candidate = f"{base}_{suffix}"
        suffix += 1
    return candidate


def reconcile_source_registry(registry=None):
    """Reconcile raw files by path and hash, detecting changes and renames."""
    if registry is None:
        registry = load_source_registry()
    records = registry["sources"]
    by_path = {record["raw_path"]: record for record in records}
    scanned = [(raw_path, absolute, hash_file(absolute)) for raw_path, absolute in raw_files()]
    present_paths = {item[0] for item in scanned}
    claimed_ids = set()
    changed = False

    for raw_path, _absolute, digest in scanned:
        record = by_path.get(raw_path)
        if record is None:
            rename_candidates = [
                item for item in records
                if item["source_id"] not in claimed_ids
                and item["raw_path"] not in present_paths
                and item["sha256"] == digest
            ]
            if len(rename_candidates) == 1:
                record = rename_candidates[0]
                record["raw_path"] = raw_path
                record["availability"] = "present"
                changed = True
            else:
                extension = os.path.splitext(raw_path)[1].lower().lstrip(".") or "unknown"
                record = {
                    "source_id": new_source_id(registry, raw_path),
                    "raw_path": raw_path,
                    "sha256": digest,
                    "format": extension,
                    "source_page": None,
                    "extraction_status": "pending",
                    "ingest_status": "pending",
                    "last_processed": None,
                    "availability": "present",
                    "duplicate_of": None,
                    "versions": [],
                }
                records.append(record)
                changed = True
        elif record["sha256"] != digest:
            history = record.setdefault("versions", [])
            history.append({
                "version": len(history) + 1,
                "raw_path": record["raw_path"],
                "sha256": record["sha256"],
                "source_page": record.get("source_page"),
                "extraction_status": record["extraction_status"],
                "ingest_status": record["ingest_status"],
                "last_processed": record["last_processed"],
            })
            record.update({
                "sha256": digest,
                "format": os.path.splitext(raw_path)[1].lower().lstrip(".") or "unknown",
                "source_page": None,
                "extraction_status": "pending",
                "ingest_status": "changed",
                "last_processed": None,
                "availability": "present",
                "duplicate_of": None,
            })
            changed = True
        elif record.get("availability") != "present":
            record["availability"] = "present"
            changed = True
        claimed_ids.add(record["source_id"])

    for record in records:
        if record["source_id"] not in claimed_ids and record.get("availability") != "missing":
            record["availability"] = "missing"
            changed = True

    groups = {}
    for record in records:
        if record.get("availability") == "present":
            groups.setdefault(record["sha256"], []).append(record)
    for group in groups.values():
        group.sort(key=lambda item: (
            item["ingest_status"] != "complete",
            bool(item.get("duplicate_of")),
            item["source_id"],
        ))
        canonical = group[0]
        if canonical.get("duplicate_of") is not None:
            canonical["duplicate_of"] = None
            if canonical["ingest_status"] == "duplicate":
                page = canonical.get("source_page")
                page_exists = page and os.path.isfile(os.path.join(ROOT, *page.split("/")))
                canonical["ingest_status"] = "complete" if page_exists else "pending"
            changed = True
        for duplicate in group[1:]:
            if duplicate.get("duplicate_of") != canonical["source_id"]:
                duplicate["duplicate_of"] = canonical["source_id"]
                changed = True
            desired_page = canonical.get("source_page")
            desired_ingest = "duplicate" if canonical["ingest_status"] == "complete" else "pending"
            if duplicate.get("source_page") != desired_page or duplicate["ingest_status"] != desired_ingest:
                duplicate["source_page"] = desired_page
                duplicate["ingest_status"] = desired_ingest
                duplicate["extraction_status"] = canonical["extraction_status"]
                changed = True
    return registry, changed


def registry_record_for_path(registry, raw_path):
    return next((record for record in registry["sources"] if record["raw_path"] == raw_path
                 and record.get("availability") == "present"), None)


def normalize_relative_path(value, label):
    """Normalize Windows or POSIX separators and reject paths outside ROOT."""
    if not value or "\x00" in value:
        raise ValueError(f"{label} must be a non-empty relative path")
    normalized = os.path.normpath(value.replace("\\", os.sep).replace("/", os.sep))
    drive, _ = os.path.splitdrive(normalized)
    if drive or os.path.isabs(normalized) or normalized == os.pardir or normalized.startswith(os.pardir + os.sep):
        raise ValueError(f"{label} must stay within the repository: {value}")
    return normalized


def extraction_relative_path(record):
    """Return the version-specific persisted extraction-state path."""
    digest = record["sha256"][:16]
    return f"index/extractions/{record['source_id']}/{digest}.json"


def extraction_path(record):
    return os.path.join(ROOT, *extraction_relative_path(record).split("/"))


def clean_extracted_text(value):
    """Normalize extractor output without erasing semantic paragraph breaks."""
    value = value.replace("\r\n", "\n").replace("\r", "\n").replace("\x00", "")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
    return "\n".join(lines).strip()


def extract_text_units(path, source_format):
    text = read_file(path)
    if source_format == "md":
        units = []
        heading = "Document"
        body = []
        for line in text.splitlines():
            match = re.match(r"^(#{1,6})\s+(.+?)\s*$", line)
            if match:
                if body or units:
                    units.append({"heading": heading, "text": clean_extracted_text("\n".join(body))})
                heading = match.group(2).strip()
                body = []
            else:
                body.append(line)
        if body or not units:
            units.append({"heading": heading, "text": clean_extracted_text("\n".join(body))})
        return [
            {
                "unit": index,
                "location": {"kind": "section", "section": index, "heading": item["heading"]},
                "text": item["text"],
            }
            for index, item in enumerate(units, 1) if item["text"] or len(units) == 1
        ]
    blocks = [clean_extracted_text(block) for block in re.split(r"\n\s*\n", text)]
    blocks = [block for block in blocks if block]
    return [
        {"unit": index, "location": {"kind": "block", "block": index}, "text": block}
        for index, block in enumerate(blocks, 1)
    ] or [{"unit": 1, "location": {"kind": "block", "block": 1}, "text": ""}]


def extract_pdf_units(path):
    try:
        pdf_reader = importlib.import_module("pypdf").PdfReader
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("PDF extraction requires the 'pypdf' package") from exc
    reader = pdf_reader(path)
    units = []
    for page_number, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception as exc:
            raise RuntimeError(f"PDF extraction failed on page {page_number}: {exc}") from exc
        units.append({
            "unit": page_number,
            "location": {"kind": "page", "page": page_number},
            "text": clean_extracted_text(text),
        })
    return units


def extract_docx_units(path):
    try:
        document_factory = importlib.import_module("docx").Document
    except (ImportError, AttributeError) as exc:
        raise RuntimeError("DOCX extraction requires the 'python-docx' package") from exc
    try:
        document = document_factory(path)
    except Exception as exc:
        raise RuntimeError(f"DOCX extraction failed: {exc}") from exc
    sections = []
    heading = "Document"
    paragraphs = []
    start = 1
    for paragraph_number, paragraph in enumerate(document.paragraphs, 1):
        text = clean_extracted_text(paragraph.text)
        style = getattr(getattr(paragraph, "style", None), "name", "") or ""
        if text and style.lower().startswith("heading"):
            if paragraphs:
                sections.append((heading, start, paragraph_number - 1, "\n\n".join(paragraphs)))
            heading = text
            paragraphs = []
            start = paragraph_number + 1
        elif text:
            if not paragraphs:
                start = paragraph_number
            paragraphs.append(text)
    if paragraphs or not sections:
        end = len(document.paragraphs)
        sections.append((heading, start, end, "\n\n".join(paragraphs)))
    return [
        {
            "unit": index,
            "location": {
                "kind": "section",
                "section": index,
                "heading": heading,
                "paragraph_start": start,
                "paragraph_end": end,
            },
            "text": text,
        }
        for index, (heading, start, end, text) in enumerate(sections, 1)
    ]


def extract_ipynb_units(path):
    """Extract notebook cells as text units using only the standard library.

    Markdown cells are kept verbatim; code cells are fenced and plain-text
    outputs appended. Rich outputs (images, HTML, plots) are skipped.
    """
    try:
        with open(path, "r", encoding="utf-8") as handle:
            notebook = json.load(handle)
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError(f"IPYNB extraction failed: invalid notebook JSON: {exc}") from exc
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        raise RuntimeError("IPYNB extraction failed: invalid notebook JSON: missing 'cells' list")
    units = []
    for cell_number, cell in enumerate(notebook["cells"], 1):
        if not isinstance(cell, dict):
            continue
        cell_type = cell.get("cell_type", "")
        source = cell.get("source", [])
        if isinstance(source, list):
            source_text = "".join(str(part) for part in source)
        else:
            source_text = str(source)
        parts = []
        if cell_type == "markdown":
            text = clean_extracted_text(source_text)
            if text:
                parts.append(text)
        elif cell_type == "code":
            code = clean_extracted_text(source_text)
            if code:
                parts.append("```python\n" + code + "\n```")
            for output in cell.get("outputs", []) or []:
                if not isinstance(output, dict):
                    continue
                output_type = output.get("output_type", "")
                if output_type == "stream" and output.get("text"):
                    text = output["text"]
                    stream = "".join(text) if isinstance(text, list) else str(text)
                    stream = clean_extracted_text(stream)
                    if stream:
                        parts.append("```\n" + stream + "\n```")
                elif output_type in ("execute_result", "display_data"):
                    data = output.get("data", {})
                    if isinstance(data, dict) and data.get("text/plain"):
                        plain = data["text/plain"]
                        plain_text = "".join(plain) if isinstance(plain, list) else str(plain)
                        plain_text = clean_extracted_text(plain_text)
                        if plain_text:
                            parts.append("```\n" + plain_text + "\n```")
        else:
            continue
        if parts:
            units.append({
                "unit": cell_number,
                "location": {"kind": "cell", "cell": cell_number, "cell_type": cell_type},
                "text": "\n\n".join(parts),
            })
    if not units:
        raise RuntimeError("IPYNB extraction failed: no markdown or code cells found")
    return units


def extract_units(path, source_format):
    if source_format in ("md", "txt"):
        return extract_text_units(path, source_format)
    if source_format == "pdf":
        return extract_pdf_units(path)
    if source_format == "docx":
        return extract_docx_units(path)
    if source_format == "ipynb":
        return extract_ipynb_units(path)
    raise ValueError(f"unsupported source format: .{source_format}")


def split_oversized_text(text, maximum):
    """Split one paragraph at sentence/word boundaries, then hard-wrap if needed."""
    if len(text) <= maximum:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces = []
    current = ""
    for sentence in sentences:
        if len(sentence) > maximum:
            words = sentence.split()
            for word in words:
                if len(word) > maximum:
                    if current:
                        pieces.append(current)
                        current = ""
                    pieces.extend(word[i:i + maximum] for i in range(0, len(word), maximum))
                elif not current:
                    current = word
                elif len(current) + len(word) + 1 <= maximum:
                    current += " " + word
                else:
                    pieces.append(current)
                    current = word
        elif not current:
            current = sentence
        elif len(current) + len(sentence) + 1 <= maximum:
            current += " " + sentence
        else:
            pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return pieces


def chunk_units(source_id, units, maximum=MAX_CHUNK_CHARS):
    chunks = []
    for unit in units:
        paragraphs = [part.strip() for part in re.split(r"\n\s*\n|\n", unit["text"]) if part.strip()]
        pieces = []
        for paragraph in paragraphs:
            pieces.extend(split_oversized_text(paragraph, maximum))
        grouped = []
        current = ""
        for piece in pieces:
            if not current:
                current = piece
            elif len(current) + len(piece) + 2 <= maximum:
                current += "\n\n" + piece
            else:
                grouped.append(current)
                current = piece
        if current or not grouped:
            grouped.append(current)
        kind = unit["location"]["kind"]
        coordinate = {"page": "p", "section": "s", "block": "b", "cell": "n"}[kind]
        unit_number = unit["location"][kind]
        for chunk_number, text in enumerate(grouped, 1):
            chunks.append({
                "chunk_id": f"{source_id}:{coordinate}{unit_number:03d}:c{chunk_number:02d}",
                "ordinal": len(chunks) + 1,
                "location": unit["location"],
                "text": text,
                "status": "pending",
                "candidate_terms": [],
            })
    return chunks


def candidate_terms(text, limit=5):
    words = [word.lower() for word in re.findall(r"[A-Za-z][A-Za-z0-9-]{3,}", text)]
    counts = collections.Counter(word for word in words if word not in STOP_WORDS)
    return [word for word, _count in counts.most_common(limit)]


def location_label(location):
    if location["kind"] == "page":
        return f"page {location['page']}"
    if location["kind"] == "section":
        label = f"section {location['section']}"
        if location.get("heading"):
            label += f" ({location['heading']})"
        if location.get("paragraph_start"):
            label += f", paragraphs {location['paragraph_start']}-{location['paragraph_end']}"
        return label
    if location["kind"] == "cell":
        label = f"cell {location['cell']}"
        if location.get("cell_type"):
            label += f" ({location['cell_type']})"
        return label
    return f"block {location['block']}"


def new_extraction_state(record, units):
    chunks = chunk_units(record["source_id"], units)
    return {
        "schema_version": EXTRACTION_SCHEMA_VERSION,
        "source_id": record["source_id"],
        "raw_path": record["raw_path"],
        "sha256": record["sha256"],
        "format": record["format"],
        "status": "extracted",
        "created": now_timestamp(),
        "updated": now_timestamp(),
        "unit_count": len(units),
        "chunk_count": len(chunks),
        "chunks": chunks,
        "error": None,
    }


def load_extraction_state(record):
    path = extraction_path(record)
    if not os.path.isfile(path):
        return None
    state = json.loads(read_file(path))
    if (state.get("schema_version") != EXTRACTION_SCHEMA_VERSION
            or state.get("source_id") != record["source_id"]
            or state.get("sha256") != record["sha256"]
            or not isinstance(state.get("chunks"), list)):
        raise ValueError(f"invalid extraction state: {extraction_relative_path(record)}")
    return state


def process_source_map_chunks(state, maximum=None):
    pending = [chunk for chunk in state["chunks"] if chunk.get("status") != "mapped"]
    selected = pending if maximum is None else pending[:maximum]
    for chunk in selected:
        chunk["candidate_terms"] = candidate_terms(chunk["text"])
        chunk["status"] = "mapped"
    remaining = sum(chunk.get("status") != "mapped" for chunk in state["chunks"])
    state["status"] = "complete" if not remaining else "partial"
    state["updated"] = now_timestamp()
    return len(selected), remaining


def configure_console():
    """Make all runner output safe on legacy Windows console encodings."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            reconfigure(encoding="ascii", errors="backslashreplace")


def log_entry(operation, title, pages_created=None, pages_updated=None):
    entry = f"## [{now_iso()}] {operation} | {title}\n\n"
    entry += "Brief: automated by bob_runner.py\n\n"
    if pages_created:
        entry += "Pages created:\n"
        for page in pages_created:
            page = display_path(page)
            entry += f"- [{page}]({page})\n"
        entry += "\n"
    if pages_updated:
        entry += "Pages updated:\n"
        for page in pages_updated:
            page = display_path(page)
            entry += f"- [{page}]({page})\n"
        entry += "\n"
    return entry + "Key outcomes:\n- automated operation\n\n"


def commit_text_updates(updates):
    """Apply a set of text replacements and roll back completed writes on error."""
    originals = {}
    for path, content in updates:
        content.encode("utf-8")
        originals[path] = read_file(path) if os.path.exists(path) else None
    written = []
    try:
        for path, content in updates:
            write_file(path, content)
            written.append(path)
    except OSError:
        for path in reversed(written):
            original = originals[path]
            if original is None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            else:
                write_file(path, original)
        raise


def commit_file_changes(updates, deletes=None):
    """Atomically apply generated-file replacements and exact-file removals."""
    deletes = deletes or []
    update_paths = {path for path, _content in updates}
    paths = update_paths | set(deletes)
    originals = {path: read_file(path) if os.path.exists(path) else None for path in paths}
    for _path, content in updates:
        content.encode("utf-8")
    completed = []
    try:
        for path, content in updates:
            write_file(path, content)
            completed.append(path)
        for path in deletes:
            if os.path.exists(path):
                os.unlink(path)
                completed.append(path)
    except OSError:
        for path in reversed(completed):
            original = originals[path]
            if original is None:
                try:
                    os.unlink(path)
                except FileNotFoundError:
                    pass
            else:
                write_file(path, original)
        raise


def find_index_file():
    """Return the path to the highest-numbered generated index part."""
    idx_dir = os.path.join(ROOT, "index")
    if not os.path.isdir(idx_dir):
        return None
    entries = []
    for name in os.listdir(idx_dir):
        match = re.fullmatch(r"index_(\d+)\.md", name)
        if match:
            entries.append((int(match.group(1)), name))
    if not entries:
        return None
    _, newest = max(entries, key=lambda item: (item[0], item[1]))
    return os.path.join(idx_dir, newest)


def index_files():
    """Return every numbered Markdown index in numeric order."""
    idx_dir = os.path.join(ROOT, "index")
    if not os.path.isdir(idx_dir):
        return []
    entries = []
    for name in os.listdir(idx_dir):
        match = re.fullmatch(r"index_(\d+)\.md", name)
        if match:
            entries.append((int(match.group(1)), os.path.join(idx_dir, name)))
    return [path for _number, path in sorted(entries)]


def source_title(source, state):
    for chunk in state["chunks"]:
        heading = chunk["location"].get("heading")
        if heading and heading != "Document":
            return heading
    return os.path.splitext(os.path.basename(source))[0]


def source_page_markdown(source, title, record, state, target, ingest_status):
    mapped = [chunk for chunk in state["chunks"] if chunk.get("status") == "mapped"]
    first_text = next((chunk["text"] for chunk in mapped if chunk["text"].strip()), "")
    summary = re.sub(r"\s+", " ", first_text).strip()[:600]
    if len(first_text) > 600:
        summary += "..."
    if not summary:
        summary = "No extractable text was found in this source."
    artifact_rel = extraction_relative_path(record)
    artifact_link = display_path(os.path.relpath(
        os.path.join(ROOT, *artifact_rel.split("/")), os.path.dirname(target)
    ))
    md = [frontmatter(
        "source",
        aliases=[],
        source_ids=[record["source_id"]],
        ingest_status=ingest_status,
        extraction_status=record["extraction_status"],
        source_type=record["format"],
        author="",
        year=datetime.date.today().year,
    )]
    md += [
        f"# Source: {title}\n",
        f"**Type**: {record['format'].upper()}\n",
        f"**Date**: {datetime.date.today().isoformat()}\n",
        "**Author**: (unknown)\n",
        f"**Original location**: {record['raw_path']}\n",
        f"**Source ID**: {record['source_id']}\n",
        f"**SHA-256**: `{record['sha256']}`\n",
        f"**Extraction status**: {record['extraction_status']}\n",
        f"**Ingest status**: {ingest_status}\n",
        f"**Chunk state**: [{state['chunk_count']} chunks]({artifact_link})\n\n",
    ]
    prior_pages = [item.get("source_page") for item in record.get("versions", []) if item.get("source_page")]
    if prior_pages:
        prior = prior_pages[-1]
        prior_link = os.path.relpath(os.path.join(ROOT, *prior.split("/")), os.path.dirname(target))
        md.append(f"**Supersedes**: [{os.path.basename(prior)}]({display_path(prior_link)})\n\n")
    md.extend(["## Summary\n", summary + "\n\n"])
    if ingest_status == "partial":
        remaining = sum(chunk.get("status") != "mapped" for chunk in state["chunks"])
        md.append(
            f"> Partial ingest: {remaining} of {state['chunk_count']} chunks remain. "
            "Chunk progress state lives in the extraction artifact linked under "
            "**Chunk state** above. Do not treat this page as complete knowledge.\n\n"
        )
    md.extend([
        "\n## Key Takeaways\n- (agent adds takeaways after user confirmation)\n\n",
        "## Entities Mentioned\n- (agent adds entities)\n\n",
        "## Concepts Discussed\n- (agent adds concepts)\n\n",
        "## Related Pages\n- (agent adds related pages)\n\n",
        "## Sources\n",
        f"- Original file: `{record['raw_path']}`; extraction artifact: [{artifact_rel}]({artifact_link})\n\n",
        f"---\n*Ingested: {datetime.date.today().isoformat()}*\n",
    ])
    return "".join(md)


def ingest_action(source, max_chunks=None):
    try:
        source = normalize_relative_path(source, "source")
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    rawp = os.path.join(ROOT, "raw", source)
    if not os.path.isfile(rawp):
        print(f"Source file not found: {rawp}")
        return 1
    source_format = os.path.splitext(source)[1].lower().lstrip(".") or "unknown"
    registry, registry_changed = reconcile_source_registry()
    raw_rel = "raw/" + display_path(source)
    record = registry_record_for_path(registry, raw_rel)
    if record is None:
        print(f"Error: source registry did not discover: {raw_rel}")
        return 1
    if record.get("duplicate_of"):
        canonical = next(
            (item for item in registry["sources"] if item["source_id"] == record["duplicate_of"]),
            None,
        )
        if canonical and canonical["ingest_status"] == "complete":
            record["source_page"] = canonical["source_page"]
            record["extraction_status"] = canonical["extraction_status"]
            record["ingest_status"] = "duplicate"
            record["last_processed"] = now_timestamp()
            write_file(registry_path(), serialize_registry(registry))
            print(f"Duplicate source: {raw_rel}")
            print(f"  Matches: {canonical['raw_path']} ({canonical['source_id']})")
            print(f"  Source page: {canonical['source_page']}")
            return 0
    if record["ingest_status"] == "complete" and record.get("source_page"):
        source_page = os.path.join(ROOT, *record["source_page"].split("/"))
        if os.path.isfile(source_page):
            if registry_changed:
                write_file(registry_path(), serialize_registry(registry))
            print(f"Source unchanged: {raw_rel}")
            print(f"  Source ID: {record['source_id']}")
            print(f"  Source page: {record['source_page']}")
            return 0
    if source_format not in SUPPORTED_SOURCE_FORMATS:
        record.update({
            "extraction_status": "unsupported",
            "ingest_status": "failed",
            "last_processed": now_timestamp(),
            "extraction_error": f"unsupported source format: .{source_format}",
        })
        write_file(registry_path(), serialize_registry(registry))
        print(f"Error: unsupported source format: .{source_format}")
        print("Supported formats: .docx, .ipynb, .md, .pdf, .txt")
        return 1
    try:
        state = load_extraction_state(record)
        if state is None:
            units = extract_units(rawp, source_format)
            state = new_extraction_state(record, units)
            write_file(extraction_path(record), json.dumps(state, indent=2, ensure_ascii=True) + "\n")
    except (ImportError, UnicodeError, ValueError, RuntimeError, OSError) as exc:
        record.update({
            "extraction_status": "failed",
            "ingest_status": "failed",
            "last_processed": now_timestamp(),
            "extraction_error": str(exc),
        })
        write_file(registry_path(), serialize_registry(registry))
        print(f"Error: extraction failed for {raw_rel}: {exc}")
        return 1
    processed, remaining = process_source_map_chunks(state, max_chunks)
    write_file(extraction_path(record), json.dumps(state, indent=2, ensure_ascii=True) + "\n")
    record.update({
        "extraction_file": extraction_relative_path(record),
        "extraction_status": "complete",
        "chunk_count": state["chunk_count"],
        "processed_chunks": state["chunk_count"] - remaining,
        "ingest_status": "partial" if remaining else "complete",
        "last_processed": now_timestamp(),
        "extraction_error": None,
    })
    title = source_title(source, state)
    slug = kebab(title)
    if not slug:
        print("Error: source title does not produce a valid page filename.")
        return 1
    target_rel = record.get("source_page") or f"wiki/sources/{slug}.md"
    target = os.path.join(ROOT, *target_rel.split("/"))
    page_existed = os.path.exists(target)
    if page_existed and not record.get("source_page"):
        suffix = record["source_id"]
        version = len(record.get("versions", [])) + 1
        if record.get("versions"):
            suffix += f"-v{version}"
        target = os.path.join(ROOT, f"wiki/sources/{slug}-{suffix}.md")
        target_rel = display_path(os.path.relpath(target, ROOT))
    record["source_page"] = target_rel
    md = source_page_markdown(source, title, record, state, target, record["ingest_status"])
    updates = [(target, md)]
    _records, index_groups, index_updates, obsolete_indices = build_index_changes(
        overrides={target_rel: md}
    )
    updates.extend(index_updates)
    index_message = f"Rebuilt {len(index_groups)} index part(s) and {INDEX_MANIFEST_REL}"
    log_path = os.path.join(ROOT, "log.md")
    existing_log = read_file(log_path) if os.path.exists(log_path) else ""
    log_pages = [target_rel]
    updates.append((log_path, existing_log + log_entry(
        "ingest", title,
        pages_updated=log_pages if page_existed else None,
        pages_created=None if page_existed else log_pages,
    )))
    for other in registry["sources"]:
        if other.get("duplicate_of") == record["source_id"] and other["sha256"] == record["sha256"]:
            other.update({
                "source_page": target_rel,
                "extraction_status": "complete",
                "ingest_status": "duplicate" if not remaining else "pending",
            })
    updates.append((registry_path(), serialize_registry(registry)))
    commit_file_changes(updates, obsolete_indices)
    action = "Updated" if page_existed else "Created"
    print(f"{action} source page: {target_rel}")
    print(f"Source ID: {record['source_id']}")
    print(f"Extraction state: {extraction_relative_path(record)}")
    print(f"Mapped chunks: {processed}; remaining: {remaining}")
    print(index_message)
    print(f"Appended log entry to {log_path}")
    return 0


def search_terms(value):
    return [
        term.casefold() for term in re.findall(r"[\w-]+", value, re.UNICODE)
        if len(term) > 1 and term.casefold() not in STOP_WORDS
    ]


def index_link_target(index_path, href):
    """Resolve an index link and accept only existing managed Markdown pages."""
    href = href.split("#", 1)[0].strip().replace("/", os.sep)
    if not href or re.match(r"^[a-z][a-z0-9+.-]*:", href, re.IGNORECASE):
        return None
    target = os.path.abspath(os.path.normpath(os.path.join(os.path.dirname(index_path), href)))
    wiki_root = os.path.abspath(os.path.join(ROOT, "wiki"))
    try:
        if os.path.commonpath([target, wiki_root]) != wiki_root:
            return None
    except ValueError:
        return None
    if not target.lower().endswith(".md") or not os.path.isfile(target):
        return None
    return target


def page_graph_links(path, text):
    """Return normalized absolute managed-page targets linked by one page."""
    result = set()
    wiki_root = os.path.abspath(os.path.join(ROOT, "wiki"))
    for href in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
        href = href.split("#", 1)[0].strip().replace("/", os.sep)
        if not href or re.match(r"^[a-z][a-z0-9+.-]*:", href, re.IGNORECASE):
            continue
        target = os.path.abspath(os.path.normpath(os.path.join(os.path.dirname(path), href)))
        try:
            inside = os.path.commonpath([target, wiki_root]) == wiki_root
        except ValueError:
            inside = False
        if inside and target.lower().endswith(".md"):
            result.add(os.path.normcase(target))
    return result


def query_action(question):
    """Rank valid, deduplicated candidates found across every index part."""
    parts = index_files()
    if not parts:
        print("No index file found.")
        return 1
    terms = search_terms(question)
    if not terms:
        print("No searchable terms in question. Try a more specific query.")
        return 0

    candidates = {}
    entry_pattern = re.compile(r"^- \[([^\]]+)\]\(([^)]+)\)(?:\s+-\s+(.*))?$")
    for part in parts:
        for line in read_file(part).splitlines():
            match = entry_pattern.match(line.strip())
            if not match:
                continue
            indexed_title, href, indexed_description = match.groups()
            target = index_link_target(part, href)
            if target is None:
                continue
            target_key = os.path.normcase(target)
            if target_key in candidates:
                continue
            page_text = read_file(target)
            properties = frontmatter_metadata(page_text) or {}
            title = page_title(page_text) or indexed_title
            aliases = page_aliases(page_text)
            topics = frontmatter_list(properties, "topics")
            summary = index_summary(page_text) or indexed_description or ""
            sources = frontmatter_list(properties, "sources")
            source_ids = frontmatter_list(properties, "source_ids")
            updated = str(properties.get("updated") or "")[:10]
            candidates[target_key] = {
                "title": title,
                "href": href,
                "description": summary,
                "aliases": aliases,
                "topics": [str(item) for item in topics],
                "updated": updated,
                "source_count": max(len(set(map(str, sources))), len(set(map(str, source_ids)))),
                "part": os.path.basename(part),
                "links": page_graph_links(target, page_text),
            }

    question_phrase = " ".join(terms)
    for candidate in candidates.values():
        title_terms = set(search_terms(candidate["title"]))
        alias_terms = set(search_terms(" ".join(candidate["aliases"])))
        topic_terms = set(search_terms(" ".join(candidate["topics"])))
        keyword_terms = set(search_terms(candidate["description"]))
        score = 0.0
        matched = set()
        normalized_title = " ".join(search_terms(candidate["title"]))
        if question_phrase and question_phrase in normalized_title:
            score += 30.0
        for term in terms:
            if term in title_terms:
                score += 12.0
                matched.add(term)
            if term in alias_terms:
                score += 10.0
                matched.add(term)
            if term in topic_terms:
                score += 7.0
                matched.add(term)
            if term in keyword_terms:
                score += 3.0
                matched.add(term)
        if matched:
            score += 8.0 * len(matched) / len(set(terms))
        candidate["text_score"] = score

    direct_matches = {
        path for path, candidate in candidates.items() if candidate["text_score"] > 0
    }
    ranked = []
    today = datetime.date.today()
    for path, candidate in candidates.items():
        outgoing = len(candidate["links"] & direct_matches)
        incoming = sum(
            path in other["links"]
            for other_path, other in candidates.items()
            if other_path in direct_matches and other is not candidate
        )
        graph_score = min(9.0, 3.0 * (outgoing + incoming)) if direct_matches else 0.0
        if candidate["text_score"] <= 0 and graph_score <= 0:
            continue
        recency_score = 0.0
        try:
            age = max(0, (today - datetime.date.fromisoformat(candidate["updated"])).days)
            recency_score = max(0.0, 2.0 - min(age, 730) / 365.0)
        except ValueError:
            pass
        source_score = min(4.0, float(candidate["source_count"]))
        candidate["score"] = candidate["text_score"] + graph_score + recency_score + source_score
        ranked.append(candidate)

    ranked.sort(key=lambda item: (-item["score"], item["title"].casefold(), item["href"]))
    if not ranked:
        print("No obvious matches in index. Try a broader query.")
        return 0
    print(f"Candidates from {len(parts)} index part(s):")
    for number, candidate in enumerate(ranked[:MAX_QUERY_CANDIDATES], 1):
        description = candidate["description"] or "(no description)"
        print(
            f"{number}. [{candidate['title']}]({candidate['href']}) - {description} "
            f"[score: {candidate['score']:.1f}; sources: {candidate['source_count']}; "
            f"index: {candidate['part']}]"
        )
    return 0


def create_page_action(ptype, title, filename):
    if ptype not in ("entity", "concept", "source", "analysis"):
        print("Unknown page type. Use entity|concept|source|analysis")
        return 1
    if not filename:
        slug = kebab(title)
        if not slug:
            print("Error: title does not produce a valid page filename.")
            return 1
        filename = slug + ".md"
    try:
        filename = normalize_relative_path(filename, "filename")
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    if os.path.basename(filename) != filename or not filename.lower().endswith(".md"):
        print("Error: filename must be a Markdown filename, not a path.")
        return 1
    page_directories = {
        "entity": "entities",
        "concept": "concepts",
        "source": "sources",
        "analysis": "analyses",
    }
    rel = os.path.join("wiki", page_directories[ptype], filename)
    path = os.path.join(ROOT, rel)
    if os.path.exists(path):
        print(f"File exists: {rel}; will not overwrite.")
        return 1
    exact_matches, review_candidates = identity_matches(title, ptype)
    if exact_matches and ptype in {"entity", "concept"}:
        print(f"Duplicate canonical title or alias: {title}")
        for match in exact_matches:
            print(f"  Matches: {match}")
        return 1
    today = datetime.date.today().isoformat()
    review_status = "needs-review" if review_candidates else "clear"
    page_status = "needs-review" if review_candidates else "draft"
    extras = {}
    if ptype == "entity":
        extras = {"entity_type": "", "related_concepts": []}
    elif ptype == "concept":
        extras = {"category": ""}
    elif ptype == "source":
        extras = {
            "ingest_status": "draft", "extraction_status": "not-applicable",
            "source_type": "", "author": "", "year": today[:4],
        }
    elif ptype == "analysis":
        extras = {"analysis_type": ""}
    manual_source_ids = [f"manual:{os.path.splitext(filename)[0]}"] if ptype == "source" else []
    md = [frontmatter(
        ptype,
        status=page_status,
        aliases=[],
        source_ids=manual_source_ids,
        **extras,
    ), f"# {title}\n"]
    if ptype == "entity":
        md += [f"**Canonical title**: {title}\n", "**Aliases**: (none)\n",
               f"**Identity review**: {review_status}\n",
               "**Type**: Person | Organization | Product | Location\n",
               "**First mentioned**: User-created\n\n",
               "## Summary\n(add concise overview)\n\n",
               "## Key Information\n- (add sourced attributes using the citation convention)\n\n",
               "## Mentions in Sources\n- (add source links and context)\n\n",
               "## Related Pages\n- (add contextual, reciprocal links)\n\n",
               "## Sources\n- (add source-page links; use `Citation: Title, location`)\n\n",
               f"---\n*Last updated: {today}*\n"]
    elif ptype == "concept":
        md += [f"**Canonical title**: {title}\n", "**Aliases**: (none)\n",
               f"**Identity review**: {review_status}\n",
               "**Category**: Theory | Method | Framework | Principle\n",
               "**First introduced**: User-created\n\n",
               "## Summary\n(add concise overview)\n\n",
               "## Definition\n(add a sourced 1-2 sentence definition)\n\n",
               "## Explanation\n(add sourced explanation and examples)\n\n",
               "## Key Aspects\n- (add sourced aspects)\n\n",
               "## Applications\n(add sourced applications)\n\n",
               "## Related Entities\n- (add contextual links)\n\n",
               "## Related Pages\n- (add contextual, reciprocal links)\n\n",
               "## Sources\n- (add source-page links; use `Citation: Title, location`)\n\n",
               "## External References\n- (optional external references)\n\n",
               f"---\n*Last updated: {today}*\n"]
    elif ptype == "source":
        manual_id = f"manual:{os.path.splitext(filename)[0]}"
        md += ["**Type**: Article | Book | Paper | Video | Podcast\n",
               f"**Date**: {today}\n", "**Author**: (unknown)\n",
               "**Original location**: (add raw path or URL)\n",
               f"**Source ID**: {manual_id}\n", "**Extraction status**: not-applicable\n",
               "**Ingest status**: draft\n", f"**Identity review**: {review_status}\n\n",
               "## Summary\n(add 2-3 paragraph summary)\n\n",
               "## Key Takeaways\n- (add takeaway with source location)\n\n",
               "## Entities Mentioned\n- (add contextual links)\n\n",
               "## Concepts Discussed\n- (add contextual links)\n\n",
               "## Notable Quotes\n> (add quote with page, section, timestamp, or chunk ID)\n\n",
               "## Related Pages\n- (add contextual, reciprocal links)\n\n",
               "## Sources\n- Original source: (add raw path or URL)\n\n",
               f"---\n*Ingested: {today}*\n"]
    else:
        md += ["**Type**: Comparison | Synthesis | Deep Dive\n", f"**Date**: {today}\n",
               "**Origin**: Query | Lint | User request\n\n",
               "## Summary\n(add concise overview)\n\n", "## Question\n(add original prompt)\n\n",
               "## Answer\n(add cited synthesis)\n\n",
               "## Sources Consulted\n- (add wiki-page links)\n\n",
               "## Key Insights\n- (add cited insights)\n\n",
               "## Related Analyses\n- (add contextual links)\n\n",
               "## Related Pages\n- (add contextual, reciprocal links)\n\n",
               "## Sources\n- (add source-page links; use `Citation: Title, location`)\n\n",
               f"---\n*Created: {today}*\n"]
    log_path = os.path.join(ROOT, "log.md")
    existing_log = read_file(log_path) if os.path.exists(log_path) else ""
    commit_text_updates([
        (path, "\n".join(md)),
        (log_path, existing_log + log_entry("create-page", title, pages_created=[rel])),
    ])
    print(f"Appended log entry to {log_path}")
    print(f"Created page: {rel}")
    for candidate in review_candidates:
        print(f"Identity review candidate: {candidate}")
    return 0


def markdown_sections(text):
    sections = {}
    current = None
    for line in text.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            current = match.group(1)
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(line)
    return sections


def is_placeholder_content(line):
    stripped = line.strip().lower()
    return (
        not stripped
        or stripped == "---"
        or stripped.startswith("(add")
        or stripped.startswith("- (add")
        or stripped.startswith("> (add")
        or stripped.startswith("- no ")
    )


def source_id_index():
    """Map registered source pages, including historical versions, to IDs."""
    result = {}
    registry = load_source_registry()
    for record in registry["sources"]:
        pages = [record.get("source_page")]
        pages.extend(version.get("source_page") for version in record.get("versions", []))
        for page in pages:
            if page:
                result[display_path(page)] = record["source_id"]
    return result


LINT_CATEGORIES = (
    "Broken links",
    "Page schema and timestamps",
    "Table math pipes",
    "Index coverage and ordering",
    "Orphan pages",
    "One-way relationships",
    "Duplicate titles and aliases",
    "Citation provenance",
    "Changed raw sources",
    "Oversized files",
    "Unprocessed source chunks",
)


def lint_add(issues, category, path, message):
    issues[category].append((display_path(path), message))


def markdown_link_matches(text):
    """Return ordinary Markdown links, excluding images."""
    return list(re.finditer(r'(?<!!)\[([^\]]*)\]\(([^)]*)\)', text))


def resolve_local_link(source_path, target):
    """Resolve a local Markdown target, returning None for external/anchor links."""
    if re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", target) or target.startswith("#"):
        return None
    path_part = target.split("#", 1)[0]
    if not path_part:
        return None
    return os.path.normpath(os.path.join(os.path.dirname(source_path), path_part))


TABLE_ROW_PREFIX_RE = re.compile(r"^\s*\|")
INLINE_MATH_RE = re.compile(r"\$([^$\n]+?)\$")


def table_math_pipe_lines(text):
    """Return 1-based line numbers of table rows whose inline math contains a pipe.

    Markdown splits table cells on `|` before math is rendered, so a literal pipe
    inside `$...$` in a table row breaks the row, while escaping it as `\\|` keeps the
    row intact but LaTeX renders `\\|` as a double vertical bar.
    """
    findings = []
    for number, line in enumerate(text.splitlines(), 1):
        if not TABLE_ROW_PREFIX_RE.match(line):
            continue
        for match in INLINE_MATH_RE.finditer(line):
            if "|" in match.group(1):
                findings.append(number)
                break
    return findings


def lint_action():
    """Print a deterministic, read-only Phase 7 repository health report."""
    issues = {category: [] for category in LINT_CATEGORIES}
    wiki_dir = os.path.join(ROOT, "wiki")
    if not os.path.isdir(wiki_dir):
        print("Error: wiki/ directory not found.")
        return 1
    identities = collections.defaultdict(list)
    registered_sources = source_id_index()
    managed_pages = {}
    inbound = collections.Counter()
    relationships = set()
    pages_scanned = 0

    for root, dirs, files in os.walk(wiki_dir):
        dirs[:] = sorted(name for name in dirs if not name.startswith("."))
        for f in sorted(files):
            if not f.endswith('.md'):
                continue
            p = os.path.join(root, f)
            txt = read_file(p)
            relative = display_path(os.path.relpath(p, ROOT))
            page_type = PAGE_TYPE_BY_DIRECTORY.get(os.path.basename(root))
            if page_type:
                managed_pages[relative] = (p, txt)
                pages_scanned += 1
            title = page_title(txt)
            properties = frontmatter_metadata(txt)
            if properties is None:
                lint_add(issues, "Page schema and timestamps", relative, "Missing or malformed YAML frontmatter")
            else:
                for field in sorted(FRONTMATTER_REQUIRED_FIELDS - set(properties)):
                    lint_add(issues, "Page schema and timestamps", relative, f"Missing frontmatter property: {field}")
                if page_type and properties.get("kind") != page_type:
                    lint_add(issues, "Page schema and timestamps", relative, f"Frontmatter kind must be: {page_type}")
                if properties.get("status") not in PAGE_STATUSES:
                    lint_add(issues, "Page schema and timestamps", relative, "Invalid frontmatter status")
                for field in sorted(FRONTMATTER_LIST_FIELDS):
                    if field in properties and not isinstance(properties[field], list):
                        lint_add(issues, "Page schema and timestamps", relative, f"Frontmatter property must be a list: {field}")
                for field in ("created", "updated"):
                    value = properties.get(field)
                    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
                        lint_add(issues, "Page schema and timestamps", relative, f"Invalid frontmatter date: {field}")
                if page_type == "source":
                    for field in sorted(SOURCE_FRONTMATTER_FIELDS - set(properties)):
                        lint_add(issues, "Page schema and timestamps", relative, f"Missing source frontmatter property: {field}")
                if page_type == "entity":
                    for field in sorted(ENTITY_FRONTMATTER_FIELDS - set(properties)):
                        lint_add(issues, "Page schema and timestamps", relative, f"Missing entity frontmatter property: {field}")
                    if "related_concepts" in properties and not isinstance(properties["related_concepts"], list):
                        lint_add(issues, "Page schema and timestamps", relative, "Frontmatter property must be a list: related_concepts")
            if not title:
                lint_add(issues, "Page schema and timestamps", relative, "Missing title heading")
            if not re.search(
                r"^\*(?:Last updated:|Ingested:|Created:) \d{4}-\d{2}-\d{2}\*$",
                txt,
                re.MULTILINE,
            ):
                lint_add(issues, "Page schema and timestamps", relative, "Missing timestamp/metadata")

            for line_number in table_math_pipe_lines(txt):
                lint_add(
                    issues,
                    "Table math pipes",
                    relative,
                    f"Pipe inside table-cell math on line {line_number}; "
                    "use \\lvert/\\rvert (a bare pipe splits the row and \\| renders as a double bar)",
                )

            sections = markdown_sections(txt)
            if page_type:
                required = COMMON_REQUIRED_SECTIONS | PAGE_REQUIRED_SECTIONS[page_type]
                for heading in sorted(required - set(sections)):
                    lint_add(issues, "Page schema and timestamps", relative, f"Missing required section: ## {heading}")
            if page_type:
                for identity in [title or ""] + page_aliases(txt):
                    if canonical_key(identity):
                        identities[canonical_key(identity)].append(relative)
            if page_type in {"entity", "concept"}:
                canonical = metadata_value(txt, "Canonical title")
                if not canonical:
                    lint_add(issues, "Page schema and timestamps", relative, "Missing metadata field: Canonical title")
                if metadata_value(txt, "Aliases") is None:
                    lint_add(issues, "Page schema and timestamps", relative, "Missing metadata field: Aliases")
                for identity in [canonical or ""]:
                    if canonical_key(identity):
                        identities[canonical_key(identity)].append(relative)
            if page_type == "source":
                for field in sorted(SOURCE_REQUIRED_FIELDS):
                    if metadata_value(txt, field) is None:
                        lint_add(issues, "Page schema and timestamps", relative, f"Missing metadata field: {field}")
                source_id = metadata_value(txt, "Source ID")
                if properties and source_id and source_id not in properties.get("source_ids", []):
                    lint_add(issues, "Citation provenance", relative, f"Frontmatter source_ids missing: {source_id}")
                for prose_field, property_field in (
                    ("Ingest status", "ingest_status"),
                    ("Extraction status", "extraction_status"),
                ):
                    prose_value = metadata_value(txt, prose_field)
                    if properties and prose_value and properties.get(property_field) != prose_value:
                        lint_add(issues, "Page schema and timestamps", relative, f"Frontmatter/prose mismatch: {property_field}")
                if source_id and not source_id.startswith("manual:"):
                    if registered_sources.get(relative) != source_id:
                        lint_add(issues, "Citation provenance", relative, f"Untraceable source ID: {source_id}")

            matches = markdown_link_matches(txt)
            non_image_text = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', txt)
            if non_image_text.count("](") > len(matches):
                lint_add(issues, "Broken links", relative, "Malformed Markdown link syntax")
            valid_provenance_link = False
            for match in matches:
                label, target = match.groups()
                if not label.strip() or not target.strip() or "\\" in target:
                    lint_add(issues, "Broken links", relative, f"Malformed link: [{label}]({target})")
                    continue
                if re.match(r"^[a-zA-Z]:[/\\]", target) or target.startswith("/"):
                    lint_add(issues, "Broken links", relative, f"Malformed internal link: {target}")
                    continue
                resolved = resolve_local_link(p, target)
                if resolved is None:
                    continue
                if not os.path.exists(resolved):
                    lint_add(issues, "Broken links", relative, f"Broken link: {target}")
                else:
                    resolved_rel = display_path(os.path.relpath(resolved, ROOT))
                    if resolved_rel in managed_pages or resolved_rel.startswith("wiki/"):
                        inbound[resolved_rel] += 1
                    related_text = "\n".join(sections.get("Related Pages", []))
                    if match.group(0) in related_text and resolved_rel.startswith("wiki/"):
                        relationships.add((relative, resolved_rel))
                    if resolved_rel.startswith("wiki/sources/"):
                        line_start = txt.rfind("\n", 0, match.start()) + 1
                        line_end = txt.find("\n", match.end())
                        citation_line = txt[line_start:line_end if line_end >= 0 else len(txt)]
                        locator = re.search(
                            r"\b(?:p{1,2}\.\s*\d+|pages?\s+\d+|section\s+\S+|"
                            r"timestamp\s+\S+|chunk(?:\s+id)?\s+[`A-Za-z0-9_:.-]+|"
                            r"src_[A-Za-z0-9_-]+:[A-Za-z0-9_:.-]+)",
                            citation_line,
                            re.IGNORECASE,
                        )
                        if "Citation:" in citation_line and locator:
                            valid_provenance_link = True

            for line_number, line in enumerate(txt.splitlines(), 1):
                if "Citation:" not in line:
                    continue
                citation_links = markdown_link_matches(line)
                source_links = []
                for citation_match in citation_links:
                    resolved = resolve_local_link(p, citation_match.group(2))
                    if resolved is not None and display_path(os.path.relpath(resolved, ROOT)).startswith("wiki/sources/"):
                        source_links.append(resolved)
                if not source_links or not any(os.path.isfile(path) for path in source_links):
                    lint_add(issues, "Citation provenance", relative, f"Citation on line {line_number} has no resolvable source page")
                if not re.search(
                    r"\b(?:p{1,2}\.\s*\d+|pages?\s+\d+|section\s+\S+|timestamp\s+\S+|"
                    r"chunk(?:\s+id)?\s+[`A-Za-z0-9_:.-]+|src_[A-Za-z0-9_-]+:[A-Za-z0-9_:.-]+)",
                    line,
                    re.IGNORECASE,
                ):
                    lint_add(issues, "Citation provenance", relative, f"Citation on line {line_number} has no source location")

            if page_type in {"entity", "concept", "analysis"}:
                claim_sections = {
                    "entity": {"Summary", "Key Information"},
                    "concept": {"Summary", "Definition", "Explanation", "Key Aspects", "Applications"},
                    "analysis": {"Summary", "Answer", "Key Insights"},
                }[page_type]
                has_claim = any(
                    not is_placeholder_content(line)
                    for heading in claim_sections
                    for line in sections.get(heading, [])
                )
                if has_claim and not valid_provenance_link:
                    lint_add(issues, "Citation provenance", relative, "Untraceable claims: no resolvable source-page citation with location")

            token_count = estimate_tokens(txt)
            if page_type and token_count > PAGE_WARNING_TOKENS:
                lint_add(issues, "Oversized files", relative, f"Page is ~{token_count} tokens (warning threshold: {PAGE_WARNING_TOKENS})")

    for identity, identity_pages in sorted(identities.items()):
        unique_pages = sorted(set(identity_pages))
        if len(unique_pages) > 1:
            message = f"Duplicate canonical title or alias: {identity} ({', '.join(unique_pages)})"
            for relative in unique_pages:
                lint_add(issues, "Duplicate titles and aliases", relative, message)

    managed_paths = set(managed_pages)
    for relative in sorted(managed_paths):
        if inbound[relative] == 0:
            lint_add(issues, "Orphan pages", relative, "No inbound link from another wiki page")
    for source, target in sorted(relationships):
        if target in managed_paths and (target, source) not in relationships:
            lint_add(issues, "One-way relationships", source, f"Related Pages link to {target} has no reciprocal Related Pages link")

    index_paths = index_files()
    index_documents = list(index_paths)
    manifest_path = os.path.join(ROOT, *INDEX_MANIFEST_REL.split("/"))
    if os.path.isfile(manifest_path):
        index_documents.append(manifest_path)
    else:
        lint_add(issues, "Index coverage and ordering", INDEX_MANIFEST_REL, "Index manifest is missing")
    if not index_paths:
        lint_add(issues, "Index coverage and ordering", "index/", "No numbered index parts exist")
    actual_entries = []
    for index_path in index_documents:
        index_relative = display_path(os.path.relpath(index_path, ROOT))
        text = read_file(index_path)
        token_count = estimate_tokens(text)
        if token_count > INDEX_HARD_LIMIT:
            lint_add(issues, "Oversized files", index_relative, f"Index is ~{token_count} tokens (hard limit: {INDEX_HARD_LIMIT})")
        for match in markdown_link_matches(text):
            label, target = match.groups()
            if not label.strip() or not target.strip() or "\\" in target:
                lint_add(issues, "Broken links", index_relative, f"Malformed link: [{label}]({target})")
                continue
            resolved = resolve_local_link(index_path, target)
            if resolved is not None and not os.path.exists(resolved):
                lint_add(issues, "Broken links", index_relative, f"Broken link: {target}")
            if index_path in index_paths and target.split("#", 1)[0].startswith("../wiki/"):
                actual_entries.append(display_path(os.path.normpath(os.path.join("index", target))))

    expected_records = collect_index_records()
    expected_entries = [record["path"][3:] for record in expected_records]
    actual_counts = collections.Counter(actual_entries)
    expected_set = set(expected_entries)
    for relative in expected_entries:
        if actual_counts[relative] == 0:
            lint_add(issues, "Index coverage and ordering", relative, "Managed page is missing from numbered indices")
        elif actual_counts[relative] > 1:
            lint_add(issues, "Index coverage and ordering", relative, f"Managed page appears {actual_counts[relative]} times in numbered indices")
    for relative in sorted(set(actual_entries) - expected_set):
        lint_add(issues, "Index coverage and ordering", relative, "Index entry does not correspond to a managed page")
    if actual_entries != expected_entries:
        common_actual = [path for path in actual_entries if path in expected_set]
        common_expected = [path for path in expected_entries if path in set(actual_entries)]
        if common_actual != common_expected:
            lint_add(issues, "Index coverage and ordering", "index/", "Entries are not in deterministic category/title order")

    registry = load_source_registry()
    for record in registry["sources"]:
        raw_path = record["raw_path"]
        absolute = os.path.join(ROOT, *raw_path.split("/"))
        if record.get("availability") != "missing" and os.path.isfile(absolute):
            digest = hash_file(absolute)
            if digest != record["sha256"]:
                lint_add(issues, "Changed raw sources", raw_path, f"Current SHA-256 differs from registry for {record['source_id']}")
        state_path = extraction_path(record)
        if os.path.isfile(state_path):
            state = load_extraction_state(record)
            if state is None:
                lint_add(
                    issues,
                    "Unprocessed source chunks",
                    extraction_relative_path(record),
                    f"Extraction state disappeared while checking {record['source_id']}",
                )
                continue
            pending = [chunk for chunk in state["chunks"] if chunk.get("status") != "mapped"]
            if pending:
                artifact = display_path(os.path.relpath(state_path, ROOT))
                lint_add(issues, "Unprocessed source chunks", artifact, f"{len(pending)} of {len(state['chunks'])} chunks are not mapped")
            for chunk in state["chunks"]:
                if len(chunk.get("text", "")) > MAX_CHUNK_CHARS:
                    artifact = display_path(os.path.relpath(state_path, ROOT))
                    lint_add(issues, "Oversized files", artifact, f"Chunk {chunk.get('chunk_id', '(unknown)')} exceeds {MAX_CHUNK_CHARS} characters")
        elif record.get("availability") != "missing" and (
            record.get("extraction_status") in {"pending", "partial", "extracted"}
            or record.get("ingest_status") in {"pending", "partial", "changed"}
        ):
            lint_add(
                issues,
                "Unprocessed source chunks",
                extraction_relative_path(record),
                f"Extraction state is missing for {record['source_id']} ({record.get('ingest_status')})",
            )

    total = sum(len(items) for items in issues.values())
    print("Lint health report (read-only)")
    print(f"Managed pages scanned: {pages_scanned}")
    print(f"Total issues: {total}")
    for category in LINT_CATEGORIES:
        print(f"- {category}: {len(issues[category])}")
    for category in LINT_CATEGORIES:
        if not issues[category]:
            continue
        print(f"\n## {category}")
        for path, message in sorted(set(issues[category])):
            print(f"- {path}: {message}")
    return 0


def research_action():
    procedure = os.path.join(ROOT, ".bob", "commands", "research.md")
    if not os.path.isfile(procedure):
        print("Error: research procedure not found: .bob/commands/research.md")
        return 1
    print(
        "research is an agent-only operation - no scaffolding is generated by the runner.\n"
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

    # (b) Registry-backed raw source lifecycle
    registry, changed = reconcile_source_registry()
    if changed or not os.path.exists(registry_path()):
        write_file(registry_path(), serialize_registry(registry))
    pending = [record for record in registry["sources"]
               if record.get("availability") == "present"
               and record["ingest_status"] not in ("complete", "duplicate")]

    print("=== Uningested raw/ files ===")
    if pending:
        for record in sorted(pending, key=lambda item: item["raw_path"]):
            print(f"  {record['raw_path'][4:]} [{record['ingest_status']}]")
    else:
        print("  (none - all registered raw files are complete or duplicates)")
    present = [record for record in registry["sources"] if record.get("availability") == "present"]
    duplicates = sum(record["ingest_status"] == "duplicate" for record in present)
    print(f"  Registry: {len(present)} present, {len(pending)} pending/changed, {duplicates} duplicate")
    print()

    # (c) Last 3 log entries
    logp = os.path.join(ROOT, "log.md")
    recent = []
    if os.path.isfile(logp):
        for line in read_file(logp).splitlines():
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
        idx_text = read_file(idx)
        word_count = len(idx_text.split())
        token_est = int(word_count / 0.75)
        rel = os.path.relpath(idx, ROOT)
        warning = "  WARNING: NEAR LIMIT - consider splitting" if token_est > 8000 else ""
        print(f"  File    : {rel}")
        print(f"  Tokens  : ~{token_est}{warning}")
        print(f"  Limit   : 10 000 tokens")
    print()

    return 0


def raw_list_action(pending_only=False):
    """List files in raw/ with size and mtime, showing ingest status."""
    raw_dir = os.path.join(ROOT, "raw")

    if not os.path.isdir(raw_dir):
        print("raw/ directory not found.")
        return 1

    registry, changed = reconcile_source_registry()
    if changed or not os.path.exists(registry_path()):
        write_file(registry_path(), serialize_registry(registry))
    records = sorted(
        (record for record in registry["sources"] if record.get("availability") == "present"),
        key=lambda item: item["raw_path"],
    )

    if not records:
        print("raw/ is empty.")
        return 0

    pending = []
    ingested = []
    for record in records:
        fname = record["raw_path"][4:]
        fpath = os.path.join(ROOT, *record["raw_path"].split("/"))
        is_ingested = record["ingest_status"] in ("complete", "duplicate")
        stat = os.stat(fpath)
        size_kb = stat.st_size / 1024
        mtime = datetime.datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d")
        entry = (fname, size_kb, mtime, record["ingest_status"])
        if is_ingested:
            ingested.append(entry)
        else:
            pending.append(entry)

    def print_entry(fname, size_kb, mtime, status):
        size_str = f"[{size_kb:>6.1f} KB]"
        print(f"  {fname:<40} {size_str}  {mtime}  [{status}]")

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


def index_summary(text):
    """Extract a compact plain-text summary for an index or search result."""
    lines = text.splitlines()
    in_summary = False
    for line in lines:
        if re.match(r"^##\s+Summary\s*$", line, re.IGNORECASE):
            in_summary = True
            continue
        stripped = line.strip()
        if in_summary and stripped.startswith("##"):
            break
        if in_summary and stripped and stripped != "---":
            clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
            return re.sub(r"[*_`]", "", clean)[:120]
    for line in lines:
        stripped = line.strip()
        if (
            stripped and not stripped.startswith(("#", "**", "---", "*Ingested", "*Last", "*Created"))
        ):
            clean = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", stripped)
            return re.sub(r"[*_`]", "", clean)[:120]
    return ""


def extract_page_meta(path):
    """Return the title, compact summary, and managed page directory."""
    try:
        text = read_file(path)
    except OSError:
        return None, None, None
    title = page_title(text) or os.path.splitext(os.path.basename(path))[0]
    relative = display_path(os.path.relpath(path, os.path.join(ROOT, "wiki")))
    page_type = relative.split("/", 1)[0]
    return title, index_summary(text), page_type


def estimate_tokens(text):
    """Return a deterministic, conservative token estimate for Markdown."""
    units = len(re.findall(r"\w+|[^\w\s]", text, re.UNICODE))
    return max(1, (units * 4 + 2) // 3)


def index_record(path, text):
    relative = display_path(os.path.relpath(path, ROOT))
    parts = relative.split("/")
    if len(parts) < 3 or parts[0] != "wiki" or parts[1] not in INDEX_CATEGORIES:
        return None
    properties = frontmatter_metadata(text) or {}
    aliases = frontmatter_list(properties, "aliases") or page_aliases(text)
    topics = frontmatter_list(properties, "topics")
    sources = frontmatter_list(properties, "sources")
    source_ids = frontmatter_list(properties, "source_ids")
    updated = str(properties.get("updated") or "")[:10]
    if not updated:
        timestamp = re.search(r"\*(?:Last updated:|Ingested:|Created:)\s*(\d{4}-\d{2}-\d{2})", text)
        updated = timestamp.group(1) if timestamp else "unknown"
    return {
        "category": parts[1],
        "title": page_title(text) or os.path.splitext(os.path.basename(path))[0],
        "path": "../" + relative,
        "summary": index_summary(text) or "(no description)",
        "aliases": [str(item) for item in aliases if str(item).strip()],
        "topics": [str(item) for item in topics if str(item).strip()],
        "updated": updated,
        "source_count": max(len(set(map(str, sources))), len(set(map(str, source_ids)))),
    }


def collect_index_records(overrides=None):
    """Read managed pages once and return canonical records for index generation."""
    overrides = overrides or {}
    wiki_dir = os.path.join(ROOT, "wiki")
    records = []
    seen = set()
    for category in INDEX_CATEGORIES:
        category_dir = os.path.join(wiki_dir, category)
        if not os.path.isdir(category_dir):
            continue
        for dirpath, dirnames, filenames in os.walk(category_dir):
            dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
            for filename in sorted(filenames):
                if not filename.lower().endswith(".md"):
                    continue
                path = os.path.join(dirpath, filename)
                relative = display_path(os.path.relpath(path, ROOT))
                text = overrides[relative] if relative in overrides else read_file(path)
                record = index_record(path, text)
                if record:
                    records.append(record)
                    seen.add(relative)
    for relative, text in sorted(overrides.items()):
        if relative in seen:
            continue
        path = os.path.join(ROOT, *relative.split("/"))
        record = index_record(path, text)
        if record:
            records.append(record)
    category_order = {category: number for number, category in enumerate(INDEX_CATEGORIES)}
    records.sort(key=lambda item: (
        category_order[item["category"]], item["title"].casefold(), item["path"].casefold()
    ))
    return records


def render_index_entry(record):
    metadata = []
    if record["aliases"]:
        metadata.append("aliases: " + ", ".join(record["aliases"]))
    if record["topics"]:
        metadata.append("topics: " + ", ".join(record["topics"]))
    metadata.extend([f"updated: {record['updated']}", f"sources: {record['source_count']}"])
    return f"- [{record['title']}]({record['path']}) - {record['summary']} [{'; '.join(metadata)}]"


def render_index_part(records, part_number, part_count, total_pages):
    today = datetime.date.today().isoformat()
    lines = [
        f"# Wiki Index [{part_number:03d}]", "", f"Last updated: {today}",
        f"Total Pages: {total_pages}", f"Pages in part: {len(records)}", "Token count: ~0", "",
    ]
    for category in INDEX_CATEGORIES:
        heading = INDEX_HEADINGS[category]
        lines.append(f"## {heading}")
        entries = [record for record in records if record["category"] == category]
        if entries:
            lines.extend(render_index_entry(record) for record in entries)
        else:
            lines.append(f"*No {heading.lower()} in this part.*")
        lines.append("")
    lines.extend(["---", "**Navigation**:", "- Manifest: [index.md](index.md)"])
    if part_number > 1:
        lines.append(f"- Previous: [index_{part_number - 1:03d}.md](index_{part_number - 1:03d}.md)")
    if part_number < part_count:
        lines.append(f"- Next: [index_{part_number + 1:03d}.md](index_{part_number + 1:03d}.md)")
    content = "\n".join(lines) + "\n"
    for _attempt in range(3):
        count = estimate_tokens(content)
        updated = re.sub(r"^Token count: ~\d+$", f"Token count: ~{count}", content, flags=re.MULTILINE)
        if updated == content:
            break
        content = updated
    return content


def partition_index_records(records):
    groups = []
    current = []
    total_pages = len(records)
    for record in records:
        proposed = current + [record]
        trial = render_index_part(proposed, 999, 999, total_pages)
        if current and estimate_tokens(trial) > INDEX_TARGET_TOKENS:
            groups.append(current)
            current = [record]
        else:
            current = proposed
    groups.append(current)
    return groups


def render_index_manifest(parts, total_pages):
    today = datetime.date.today().isoformat()
    lines = [
        "# Wiki Index Manifest", "", f"Last updated: {today}",
        f"Total Pages: {total_pages}", f"Index Parts: {len(parts)}", "",
        "The numbered indices are generated from managed wiki pages. Run `bob index-update` to rebuild them.",
        "", "## Parts",
    ]
    for number, (records, content) in enumerate(parts, 1):
        if records:
            span = f"{records[0]['title']} through {records[-1]['title']}"
        else:
            span = "empty wiki"
        lines.append(
            f"- [Index {number:03d}](index_{number:03d}.md) - {len(records)} pages, "
            f"~{estimate_tokens(content)} tokens; {span}"
        )
    return "\n".join(lines) + "\n"


def build_index_changes(overrides=None):
    """Build every index part and identify obsolete generated parts."""
    for path in index_files():
        read_file(path)  # Validate existing generated inputs before any mutation.
    records = collect_index_records(overrides)
    groups = partition_index_records(records)
    rendered = [
        render_index_part(group, number, len(groups), len(records))
        for number, group in enumerate(groups, 1)
    ]
    for content in rendered:
        if estimate_tokens(content) > INDEX_HARD_LIMIT:
            raise ValueError("a generated index part exceeds the hard token limit")
    idx_dir = os.path.join(ROOT, "index")
    updates = [
        (os.path.join(idx_dir, f"index_{number:03d}.md"), content)
        for number, content in enumerate(rendered, 1)
    ]
    part_pairs = list(zip(groups, rendered))
    updates.append((os.path.join(ROOT, *INDEX_MANIFEST_REL.split("/")), render_index_manifest(part_pairs, len(records))))
    desired = {path for path, _content in updates if re.search(r"index_\d+\.md$", path)}
    obsolete = [path for path in index_files() if path not in desired]
    return records, groups, updates, obsolete


def index_update_action():
    """Deterministically rebuild, split, and link every generated index part."""
    wiki_dir = os.path.join(ROOT, "wiki")
    if not os.path.isdir(wiki_dir):
        print("Error: wiki/ directory not found.")
        return 1
    records, groups, updates, obsolete = build_index_changes()
    counts = collections.Counter(record["category"] for record in records)
    log_path = os.path.join(ROOT, "log.md")
    existing_log = read_file(log_path) if os.path.exists(log_path) else ""
    affected = [display_path(os.path.relpath(path, ROOT)) for path, _content in updates]
    entry = (
        f"## [{now_iso()}] index-update | Deterministic index rebuild\n\n"
        "Rebuilt all index parts from managed wiki pages and refreshed the manifest.\n\n"
        "Pages affected:\n" + "".join(f"- [{path}]({path})\n" for path in affected) + "\n"
        "Key outcomes:\n"
        f"- Indexed {len(records)} pages across {len(groups)} part(s)\n"
        f"- Removed {len(obsolete)} obsolete index part(s)\n\n"
    )
    updates.append((log_path, existing_log + entry))
    commit_file_changes(updates, obsolete)
    token_counts = [estimate_tokens(content) for _path, content in updates if re.search(r"index_\d+\.md$", _path)]
    print(f"Index rebuilt: {len(groups)} part(s); manifest: {INDEX_MANIFEST_REL}")
    for category in INDEX_CATEGORIES:
        print(f"  {INDEX_HEADINGS[category]:<9}: {counts[category]}")
    print(f"  Total    : {len(records)} pages")
    print(f"  Largest  : ~{max(token_counts)} tokens")
    return 0


def move_action(from_rel, to_rel):
    """Rename a wiki page and rewrite all inbound links across wiki/ and index/."""
    try:
        from_rel = normalize_relative_path(from_rel, "source path")
        to_rel = normalize_relative_path(to_rel, "destination path")
    except ValueError as exc:
        print(f"Error: {exc}")
        return 1
    if not from_rel.lower().endswith(".md") or not to_rel.lower().endswith(".md"):
        print("Error: move supports Markdown pages only.")
        return 1
    wiki_prefix = "wiki" + os.sep
    if not from_rel.startswith(wiki_prefix) or not to_rel.startswith(wiki_prefix):
        print("Error: source and destination must both be inside wiki/.")
        return 1

    from_abs = os.path.join(ROOT, from_rel)
    to_abs   = os.path.join(ROOT, to_rel)

    # --- validation ---
    if not os.path.isfile(from_abs):
        print(f"Error: source file does not exist: {from_rel}")
        return 1
    if os.path.exists(to_abs):
        print(f"Error: destination already exists: {to_rel}")
        return 1

    # Preflight every file before changing anything. This catches invalid UTF-8
    # and permission/read errors without leaving a half-completed move.
    rewrites = []
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
                # The moved page itself is renamed separately and must not be
                # treated as an inbound-link file.
                if os.path.abspath(fpath) in (os.path.abspath(from_abs), os.path.abspath(to_abs)):
                    continue
                file_dir = os.path.dirname(fpath)
                old_rel_from_file = os.path.relpath(from_abs, file_dir)
                new_rel_from_file = os.path.relpath(to_abs,   file_dir)
                content = read_file(fpath)
                new_content = content
                variants = (
                    (old_rel_from_file, new_rel_from_file),
                    (display_path(old_rel_from_file), display_path(new_rel_from_file)),
                )
                for old_link, new_link in variants:
                    new_content = new_content.replace(old_link, new_link)
                if new_content != content:
                    rewrites.append((fpath, content, new_content))

    log_path = os.path.join(ROOT, "log.md")
    original_log = read_file(log_path) if os.path.exists(log_path) else ""
    registry_update = None
    if os.path.exists(registry_path()):
        original_registry = read_file(registry_path())
        registry = load_source_registry()
        source_page_from = display_path(from_rel)
        source_page_to = display_path(to_rel)
        registry_changed = False
        for record in registry["sources"]:
            if record.get("source_page") == source_page_from:
                record["source_page"] = source_page_to
                registry_changed = True
            for version in record.get("versions", []):
                if version.get("source_page") == source_page_from:
                    version["source_page"] = source_page_to
                    registry_changed = True
        if registry_changed:
            registry_update = (registry_path(), original_registry, serialize_registry(registry))
    updated_files = [display_path(os.path.relpath(path, ROOT)) for path, _, _ in rewrites]
    ts = now_iso()
    log_entry = f"## [{ts}] fix | move {display_path(from_rel)} -> {display_path(to_rel)}\n\n"
    log_entry += "Brief: automated by bob_runner.py\n\nPages updated:\n"
    for page in [display_path(to_rel)] + updated_files:
        log_entry += f"- [{page}]({page})\n"
    log_entry += "\nKey outcomes:\n- automated operation\n\n"

    destination_dir = os.path.dirname(to_abs)
    destination_dir_existed = os.path.isdir(destination_dir)
    renamed = False
    written = []
    try:
        os.makedirs(destination_dir, exist_ok=True)
        os.rename(from_abs, to_abs)
        renamed = True
        for fpath, original, replacement in rewrites:
            write_file(fpath, replacement)
            written.append((fpath, original))
        if registry_update:
            fpath, original, replacement = registry_update
            write_file(fpath, replacement)
            written.append((fpath, original))
        write_file(log_path, original_log + log_entry)
    except OSError as exc:
        for fpath, original in reversed(written):
            write_file(fpath, original)
        if renamed and os.path.exists(to_abs) and not os.path.exists(from_abs):
            os.rename(to_abs, from_abs)
        if not destination_dir_existed:
            try:
                os.rmdir(destination_dir)
            except OSError:
                pass
        print(f"Error: move failed without completing: {exc}")
        return 1

    print(f"Renamed: {display_path(from_rel)} -> {display_path(to_rel)}")
    for page in updated_files:
        print(f"  Updated links in: {page}")
    print(f"\nDone. {len(updated_files)} file(s) had links updated.")
    return 0


def main():
    configure_console()
    p = argparse.ArgumentParser()
    p.add_argument('command', help='slash command (ingest|query|create-page|lint|index-update|research|status|raw-list|move)')
    p.add_argument('--source', help='source filename for ingest (relative to raw/)')
    p.add_argument('--max-chunks', type=int, help='ingest: map at most this many pending chunks (resume/testing)')
    p.add_argument('--question', help='question for query')
    p.add_argument('--type', help='page type for create-page')
    p.add_argument('--title', help='title for create-page')
    p.add_argument('--filename', help='filename for create-page')
    p.add_argument('--pending-only', action='store_true', help='raw-list: show only uningested files')
    p.add_argument('--from', dest='from_rel', help='move: source path (relative to repo root)')
    p.add_argument('--to',   dest='to_rel',   help='move: destination path (relative to repo root)')
    args = p.parse_args()

    cmd = args.command.lstrip('/').lower()
    try:
        if cmd == 'ingest':
            if not args.source:
                print('ingest requires --source')
                return 1
            if args.max_chunks is not None and args.max_chunks < 1:
                print('ingest --max-chunks must be a positive integer')
                return 1
            return ingest_action(args.source, max_chunks=args.max_chunks)
        if cmd == 'query':
            if not args.question:
                print('query requires --question')
                return 1
            return query_action(args.question)
        if cmd == 'create-page':
            if not args.type or not args.title:
                print('create-page requires --type and --title')
                return 1
            return create_page_action(args.type, args.title, args.filename)
        if cmd == 'lint':
            return lint_action()
        if cmd == 'index-update':
            return index_update_action()
        if cmd == 'research':
            return research_action()
        if cmd == 'status':
            return status_action()
        if cmd == 'raw-list':
            return raw_list_action(pending_only=args.pending_only)
        if cmd == 'move':
            if not args.from_rel or not args.to_rel:
                print('move requires --from and --to')
                return 1
            return move_action(args.from_rel, args.to_rel)
        print('Unknown command:', cmd)
        return 2
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == '__main__':
    sys.exit(main())
