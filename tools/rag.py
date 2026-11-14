#!/usr/bin/env python3
"""Local retrieval-augmented access to the Bob wiki (derived, rebuildable state).

Usage examples:
  python tools/rag.py index --scope all
  python tools/rag.py search --query "why does measurement destroy superposition" --json
  python tools/rag.py ask --question "What is the no-cloning theorem?" --model gemma4:12b
  python tools/rag.py stats

Design notes:
  * Stdlib only. Embeddings are optional and come from a local Ollama server
    (`/api/embed`). When Ollama is unavailable the tool degrades to BM25 lexical
    retrieval instead of failing.
  * Everything this tool writes lives in `index/rag/` (agent-managed derived
    state). `raw/` and `wiki/` stay read-only. Markdown pages and
    `index/source-registry.json` remain the canonical layers.
  * The store is a cache: `index --rebuild` regenerates it deterministically.
  * Chunks from `index/extractions/` keep their runner-issued stable IDs and
    page/section locators, so answers can cite `...[p. 42]` as required by
    AGENTS.md section 3.4.
"""
import argparse
import array
import datetime
import hashlib
import json
import math
import os
import re
import sqlite3
import sys
import urllib.error
import urllib.request

ROOT = os.path.abspath(
    os.environ.get("BOB_RAG_ROOT")
    or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
RAG_DIR_REL = "index/rag"
STORE_REL = RAG_DIR_REL + "/rag.sqlite3"
WIKI_REL = "wiki"
EXTRACTIONS_REL = "index/extractions"
LOG_REL = "log.md"
STORE_SCHEMA_VERSION = 1
CORPORA = ("wiki", "chunks")
CHUNK_TARGET_CHARS = 1200
CHUNK_OVERLAP_CHARS = 150
MIN_CHUNK_CHARS = 80
GLUED_TOKEN_MIN = 16
VOCAB_MIN_COUNT = 2
MAX_WORD_LENGTH = 24
PIECE_PENALTY = 3.0
MIN_PIECE_LENGTH = 3
MAX_PIECE_COUNT = 16
SHORT_WORDS = frozenset({
    "is", "of", "in", "to", "be", "we", "it", "as", "at", "on", "or", "an",
    "by", "do", "if", "no", "so", "up", "us", "my", "me", "he", "go",
})
SNIPPET_CHARS = 480
EVIDENCE_CHARS = 1200
EMBED_BATCH = 32
DEFAULT_EMBED_MODEL = "embeddinggemma"
DEFAULT_CHAT_MODEL = "gemma4:12b"
RRF_K = 60
BM25_K1 = 1.2
BM25_B = 0.75


def ollama_base():
    """Return the Ollama base URL, accepting both bare host:port and full URLs."""
    configured = os.environ.get("OLLAMA_HOST") or "http://127.0.0.1:11434"
    if not configured.startswith(("http://", "https://")):
        configured = "http://" + configured
    return configured.rstrip("/")


def now_timestamp():
    """Return an ISO-8601 timestamp with the local UTC offset."""
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def now_iso():
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")


def display_path(path):
    """Return stable, slash-separated paths for console, JSON, and Markdown."""
    return path.replace("\\", "/")


def repo_path(relative):
    return os.path.join(ROOT, *display_path(relative).split("/"))


def read_text(path):
    with open(path, "r", encoding="utf-8") as handle:
        return handle.read()


def write_text(path, content):
    """Atomically replace a UTF-8 text file."""
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    content.encode("utf-8")
    temp_path = path + ".tmp-rag"
    with open(temp_path, "w", encoding="utf-8", newline="") as handle:
        handle.write(content)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp_path, path)


def file_digest(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def text_digest(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def collapse(text):
    return re.sub(r"\s+", " ", text).strip()


def plain_text(text):
    """Strip the small Markdown subset used by managed pages for snippet output."""
    text = re.sub(r"```.*?```", " ", text, flags=re.DOTALL)
    text = re.sub(r"\[\[([^\]|]+)\|([^\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", text)
    text = re.sub(r"`([^`]*)`", r"\1", text)
    return collapse(re.sub(r"[*_>#]", " ", text))


def tokenize(text):
    """Return normalized term tokens; Unicode-aware so Polish queries work."""
    return re.findall(r"\w+", text.casefold(), re.UNICODE)


def snippet(text, query_terms, width=SNIPPET_CHARS):
    """Return a plain-text excerpt centered on the first matching query term."""
    body = plain_text(text)
    start = 0
    lowered = body.casefold()
    for term in query_terms:
        position = lowered.find(term)
        if position >= 0:
            start = max(0, position - width // 3)
            break
    excerpt = body[start:start + width]
    if start > 0:
        excerpt = "…" + excerpt
    if start + width < len(body):
        excerpt = excerpt + "…"
    return excerpt


def frontmatter_fields(text):
    """Parse the deliberately small YAML subset used by managed wiki pages."""
    if not text.startswith("---\n"):
        return {}, ""
    end = text.find("\n---\n", 4)
    if end < 0:
        return {}, ""
    fields = {}
    for line in text[4:end].splitlines():
        match = re.match(r"^([a-z][a-z0-9_]*)\s*:\s*(.*)$", line)
        if not match:
            continue
        key, raw_value = match.groups()
        raw_value = raw_value.strip()
        if raw_value.startswith("[") and raw_value.endswith("]"):
            try:
                fields[key] = json.loads(raw_value)
            except json.JSONDecodeError:
                fields[key] = raw_value
        elif len(raw_value) >= 2 and raw_value[0] == raw_value[-1] == '"':
            try:
                fields[key] = json.loads(raw_value)
            except json.JSONDecodeError:
                fields[key] = raw_value
        else:
            fields[key] = raw_value
    return fields, text[end + 5:]


def field_list(fields, name):
    value = fields.get(name)
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip() and value.strip() != "[]":
        return [part.strip() for part in value.split(",") if part.strip()]
    return []


def page_title(text, fallback):
    match = re.search(r"^#\s+(.+?)\s*$", text, re.MULTILINE)
    return match.group(1).strip() if match else fallback


def humanize_filename(path):
    stem = os.path.splitext(os.path.basename(path))[0]
    return stem.replace("-", " ").replace("_", " ").strip() or stem


def split_at_boundary(text, budget):
    """Split text at the last paragraph, sentence, or word boundary within budget."""
    window = text[:budget]
    for separator in ("\n\n", ". ", " "):
        cut = window.rfind(separator)
        if cut >= budget // 2:
            return text[:cut + len(separator)].strip(), text[cut + len(separator):].strip()
    return text[:budget].strip(), text[budget:].strip()


def window_split(text, target=CHUNK_TARGET_CHARS, overlap=CHUNK_OVERLAP_CHARS):
    """Split text into overlapping pieces that never exceed `target` characters."""
    pieces = []
    remaining = text.strip()
    first = True
    step_budget = max(MIN_CHUNK_CHARS, target - overlap)
    while remaining:
        budget = target if first else step_budget
        if len(remaining) <= budget:
            head, remaining = remaining, ""
        else:
            head, remaining = split_at_boundary(remaining, budget)
        if not head:
            break
        prefix = "" if first else (pieces[-1][-overlap:] if overlap else "")
        piece = (prefix + head).strip()
        if piece:
            pieces.append(piece)
        first = False
    return pieces


def wiki_page_chunks(relative, text):
    """Return retrievable chunks for one managed Markdown page.

    Scaffolding sections emitted by the runner (source-map ledger and keyword
    candidate lists) are excluded: their chunk-ID lines and bare keyword lists
    add no retrievable facts and dilute lexical ranking.
    """
    fields, body = frontmatter_fields(text)
    title = page_title(text, humanize_filename(relative))
    keywords = " ".join(
        field_list(fields, "aliases") + field_list(fields, "topics")
        + [str(fields.get("kind") or ""), str(fields.get("category") or "")]
    ).strip()
    sections = []
    heading = None
    buffer = []
    for line in body.splitlines():
        match = re.match(r"^##\s+(.+?)\s*$", line)
        if match:
            sections.append((heading, "\n".join(buffer)))
            heading = match.group(1).strip()
            buffer = []
            continue
        if heading is None and re.match(r"^#\s+.+$", line):
            continue
        buffer.append(line)
    sections.append((heading, "\n".join(buffer)))

    chunks = []
    for heading, section_text in sections:
        section_text = section_text.strip()
        if not section_text:
            continue
        if heading in ("Source Map", "Candidate Concepts"):
            continue
        locator = f"§{heading}" if heading else "§(intro)"
        pieces = window_split(section_text)
        for index, piece in enumerate(pieces):
            if len(piece) < MIN_CHUNK_CHARS and len(pieces) > 1:
                continue
            locator_text = f"{locator} [{index + 1}/{len(pieces)}]" if len(pieces) > 1 else locator
            chunks.append({
                "path": relative,
                "corpus": "wiki",
                "ordinal": len(chunks) + 1,
                "chunk_id": None,
                "source_id": None,
                "title": title,
                "heading": heading or "",
                "locator": locator_text,
                "page": None,
                "keywords": keywords,
                "text": piece,
            })
    return chunks


def extraction_chunks(relative, document, titles, normalizer=None):
    """Return retrievable chunks from one versioned extraction record."""
    source_id = document.get("source_id") or ""
    raw_path = display_path(document.get("raw_path") or "")
    title = titles.get(source_id) or humanize_filename(raw_path or relative)
    chunks = []
    for chunk in document.get("chunks") or []:
        text = (chunk.get("text") or "").strip()
        if normalizer is not None and text:
            text = normalizer(text)
        if len(text) < MIN_CHUNK_CHARS:
            continue
        location = chunk.get("location") or {}
        kind = str(location.get("kind") or "unit")
        page = location.get("page")
        if kind == "page" and isinstance(page, int):
            locator = f"p. {page}"
        elif location.get("section"):
            locator = f"§{location['section']}"
        elif location.get("block_start"):
            locator = f"blocks {location.get('block_start')}-{location.get('block_end')}"
        else:
            locator = f"{kind} {chunk.get('ordinal')}"
        chunks.append({
            "path": relative,
            "corpus": "chunks",
            "ordinal": int(chunk.get("ordinal") or len(chunks) + 1),
            "chunk_id": chunk.get("chunk_id"),
            "source_id": source_id or None,
            "title": title,
            "heading": "",
            "locator": locator,
            "page": page if isinstance(page, int) else None,
            "keywords": raw_path,
            "text": text,
        })
    return chunks


def source_page_titles():
    """Map stable source IDs to their canonical source-page titles."""
    titles = {}
    registry_path = repo_path("index/source-registry.json")
    if not os.path.exists(registry_path):
        return titles
    try:
        registry = json.loads(read_text(registry_path))
    except (OSError, ValueError):
        return titles
    for record in registry.get("sources") or []:
        source_id = record.get("source_id")
        page_rel = record.get("source_page")
        if not source_id or not page_rel:
            continue
        page_path = repo_path(page_rel)
        if os.path.exists(page_path):
            try:
                titles[source_id] = page_title(read_text(page_path), humanize_filename(page_rel))
            except OSError:
                continue
    return titles


def iter_matching_files(base_rel, suffix):
    base = repo_path(base_rel)
    if not os.path.isdir(base):
        return []
    found = []
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = sorted(name for name in dirnames if not name.startswith("."))
        for name in sorted(filenames):
            if name.endswith(suffix):
                found.append(os.path.join(dirpath, name))
    return found


def collect_source_chunks(corpora, normalize=False):
    """Return {relative_path: (corpus, chunks, digest)} for the requested corpora.

    Extraction chunks are repaired with a vocabulary built from the corpus itself,
    which recovers words glued together by the PDF text layer (for example
    ``no-cloningtheorem``). Wiki pages are already well formed and are untouched.
    """
    collected = {}
    if "wiki" in corpora:
        for path in iter_matching_files(WIKI_REL, ".md"):
            relative = display_path(os.path.relpath(path, ROOT))
            try:
                text = read_text(path)
                chunks = wiki_page_chunks(relative, text)
            except (OSError, UnicodeError) as exc:
                print(f"Warning: skipping {relative}: {exc}", file=sys.stderr)
                continue
            if chunks:
                collected[relative] = ("wiki", chunks, file_digest(path))
    if "chunks" in corpora:
        titles = source_page_titles()
        documents = []
        for path in iter_matching_files(EXTRACTIONS_REL, ".json"):
            relative = display_path(os.path.relpath(path, ROOT))
            try:
                document = json.loads(read_text(path))
            except (OSError, ValueError) as exc:
                print(f"Warning: skipping {relative}: {exc}", file=sys.stderr)
                continue
            documents.append((path, relative, document))
        vocabulary = {}
        if normalize:
            bodies = [
                (chunk.get("text") or "")
                for _path, _relative, document in documents
                for chunk in document.get("chunks") or []
            ]
            vocabulary = build_vocabulary(bodies)
        normalizer = (
            (lambda value: normalize_glued_text(value, vocabulary)) if vocabulary else None
        )
        for path, relative, document in documents:
            chunks = extraction_chunks(relative, document, titles, normalizer=normalizer)
            if chunks:
                collected[relative] = ("chunks", chunks, file_digest(path))
    return collected


def build_vocabulary(texts, min_count=VOCAB_MIN_COUNT):
    """Collect words the extractor already spaced correctly, with their counts.

    Only stand-alone tokens are counted, so words hidden inside glued runs cannot
    pollute the vocabulary that is later used to repair those runs.
    """
    counts = {}
    for text in texts:
        for token in re.findall(r"(?<![A-Za-z])[A-Za-z]{2,}(?![A-Za-z])", text):
            lowered = token.lower()
            counts[lowered] = counts.get(lowered, 0) + 1
    return {word: count for word, count in counts.items() if count >= min_count}


def split_glued_token(token, vocab):
    """Repair one glued run by splitting it into vocabulary words, or None.

    Conservative by design: a run is only split when every piece is a known word
    and the whole run segments cleanly, so rare long real words stay intact.
    """
    lowered = token.lower()
    if lowered in vocab:
        return None
    if token[1:] != token[1:].lower():
        return None
    length = len(lowered)
    best = {0: (0.0, [])}
    for end in range(1, length + 1):
        for start in range(max(0, end - MAX_WORD_LENGTH), end):
            if start not in best:
                continue
            piece = lowered[start:end]
            frequency = vocab.get(piece)
            if frequency is None:
                continue
            if len(piece) < MIN_PIECE_LENGTH and piece not in SHORT_WORDS:
                continue
            score, pieces = best[start]
            if len(pieces) >= MAX_PIECE_COUNT:
                continue
            total = score + math.log1p(frequency) - (PIECE_PENALTY if pieces else 0.0)
            if end not in best or total > best[end][0]:
                best[end] = (total, pieces + [piece])
    if length not in best:
        return None
    pieces = best[length][1]
    if len(pieces) < 2:
        return None
    if token[0].isupper():
        pieces[0] = pieces[0].capitalize()
    return " ".join(pieces)


def normalize_glued_text(text, vocab):
    """Insert missing spaces inside long glued runs produced by PDF extraction."""
    if not vocab:
        return text
    pattern = re.compile(rf"[A-Za-z]{{{GLUED_TOKEN_MIN},}}")
    return pattern.sub(lambda match: split_glued_token(match.group(0), vocab) or match.group(0), text)


def normalization_gloss():
    """Describe the active text-normalization mode for stats output."""
    return "glue-repair" if GLUED_TOKEN_MIN else "none"


class OllamaUnavailable(RuntimeError):
    """Raised when the local Ollama server or a required model is unusable."""


def ollama_request(route, payload, timeout=900):
    """POST JSON to the local Ollama server and decode the JSON reply."""
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        ollama_base() + route, data=body, headers={"Content-Type": "application/json"}
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8", "replace")[:200]
        except OSError:
            detail = ""
        raise OllamaUnavailable(f"HTTP {exc.code} from {route} {detail}".strip()) from exc
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
        raise OllamaUnavailable(f"{type(exc).__name__}: {exc}") from exc
    except ValueError as exc:
        raise OllamaUnavailable(f"invalid JSON from {route}: {exc}") from exc


def embed_texts(texts, model):
    """Return one embedding per text, preferring the batch /api/embed route."""
    if not texts:
        return []
    try:
        vectors = []
        for start in range(0, len(texts), EMBED_BATCH):
            batch = texts[start:start + EMBED_BATCH]
            response = ollama_request("/api/embed", {"model": model, "input": batch})
            embeddings = response.get("embeddings") or []
            if len(embeddings) != len(batch):
                raise OllamaUnavailable(f"model '{model}' returned {len(embeddings)} vectors")
            vectors.extend([[float(value) for value in vector] for vector in embeddings])
        return vectors
    except OllamaUnavailable as batch_error:
        vectors = []
        try:
            for text in texts:
                response = ollama_request("/api/embeddings", {"model": model, "prompt": text})
                embedding = response.get("embedding")
                if not embedding:
                    raise OllamaUnavailable("no embedding field")
                vectors.append([float(value) for value in embedding])
            return vectors
        except OllamaUnavailable as legacy_error:
            raise OllamaUnavailable(f"{batch_error}; legacy route failed: {legacy_error}")


def encode_vector(values):
    return array.array("f", values).tobytes()


def decode_vector(blob):
    values = array.array("f")
    values.frombytes(blob)
    return values


def cosine_scores(query_vector, matrix):
    """Cosine similarity of one query vector against a list of stored vectors."""
    if not matrix:
        return []
    if numpy_module():
        import numpy  # local import keeps the module importable without numpy
        query = numpy.asarray(query_vector, dtype="float32")
        stacked = numpy.asarray(matrix, dtype="float32")
        numerator = stacked @ query
        denominators = numpy.linalg.norm(stacked, axis=1) * float(numpy.linalg.norm(query))
        denominators[denominators == 0] = 1.0
        return (numerator / denominators).tolist()
    query_norm = math.sqrt(sum(value * value for value in query_vector)) or 1.0
    scores = []
    for vector in matrix:
        numerator = 0.0
        denominator = 0.0
        for left, right in zip(vector, query_vector):
            numerator += left * right
            denominator += left * left
        scores.append(numerator / ((math.sqrt(denominator) or 1.0) * query_norm))
    return scores


def numpy_module():
    """Return the numpy module when it is installed, otherwise None."""
    try:
        import numpy as module  # noqa: F401
    except ImportError:
        return None
    return module


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS files (
    path TEXT PRIMARY KEY,
    corpus TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    chunk_count INTEGER NOT NULL,
    indexed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    path TEXT NOT NULL,
    corpus TEXT NOT NULL,
    ordinal INTEGER NOT NULL,
    chunk_id TEXT,
    source_id TEXT,
    title TEXT,
    heading TEXT,
    locator TEXT,
    page INTEGER,
    keywords TEXT,
    text TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    model TEXT,
    dim INTEGER,
    vector BLOB
);
CREATE UNIQUE INDEX IF NOT EXISTS chunks_key ON chunks(path, ordinal);
CREATE INDEX IF NOT EXISTS chunks_corpus ON chunks(corpus);
"""


def store_path():
    return repo_path(STORE_REL)


def open_store(create=False):
    """Open the derived store; return None when it does not exist yet."""
    path = store_path()
    if not create and not os.path.exists(path):
        return None
    os.makedirs(os.path.dirname(path), exist_ok=True)
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.executescript(SCHEMA)
    return connection


def get_meta(connection, key, default=None):
    row = connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else default


def set_meta(connection, key, value):
    connection.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
        (key, "" if value is None else str(value)),
    )


def embed_text(chunk):
    """Compose the text used for embedding so short chunks keep their context."""
    header = " — ".join(part for part in (chunk["title"], chunk["heading"]) if part)
    keywords = chunk.get("keywords") or ""
    pieces = [piece for piece in (header, keywords, chunk["text"]) if piece]
    return "\n".join(pieces)[:6000]


def build_index(corpora=CORPORA, rebuild=False, use_embeddings=None,
                model=DEFAULT_EMBED_MODEL, normalize=False):
    """Populate the derived store and return a statistics dictionary.

    ``normalize`` is opt-in: the glue-repair pass is measured to be a marginal
    retrieval win that can also corrupt legitimate long words, so the default keeps
    the extractor's original text.
    """
    collected = collect_source_chunks(corpora, normalize=normalize)
    connection = open_store(create=True)
    try:
        if rebuild:
            connection.execute("DELETE FROM chunks")
            connection.execute("DELETE FROM files")
        stored_model = get_meta(connection, "embed_model", "") or ""
        stored_normalization = get_meta(connection, "text_normalization", "") or ""
        requested_normalization = "glue-repair" if normalize else "none"
        embed_requested = use_embeddings is not False
        vectors_valid = embed_requested and stored_model == model
        existing = {row["path"]: dict(row) for row in connection.execute("SELECT * FROM files")}

        stats = {
            "files": 0, "chunks": 0, "embedded": 0, "skipped": 0, "pruned": 0,
            "embed_model": stored_model, "embed_dim": int(get_meta(connection, "embed_dim", 0) or 0),
            "normalization": "glue-repair" if normalize else "none",
            "note": "",
        }
        pending = []
        for relative, (corpus, chunks, digest) in sorted(collected.items()):
            record = existing.get(relative)
            # Only extraction chunks are affected by text normalization, so a mode
            # switch must not invalidate the (already clean) wiki pages.
            normalization_ok = (
                corpus != "chunks" or stored_normalization == requested_normalization
            )
            unchanged = (
                not rebuild
                and normalization_ok
                and record is not None
                and record["sha256"] == digest
            )
            if unchanged and (vectors_valid or not embed_requested):
                stats["skipped"] += 1
                continue
            pending.append((relative, corpus, chunks, digest))

        texts = []
        spans = []
        for _relative, _corpus, chunks, _digest in pending:
            spans.append((len(texts), len(texts) + len(chunks)))
            texts.extend(embed_text(chunk) for chunk in chunks)

        vectors = []
        embedding_note = ""
        if embed_requested and texts:
            try:
                vectors = embed_texts(texts, model)
            except OllamaUnavailable as exc:
                embedding_note = f"embeddings unavailable ({exc}); stored lexical text only"
                vectors = []

        stamp = now_timestamp()
        for position, (relative, corpus, chunks, digest) in enumerate(pending):
            connection.execute("DELETE FROM chunks WHERE path = ?", (relative,))
            start, end = spans[position]
            file_vectors = vectors[start:end] if vectors else []
            for offset, chunk in enumerate(chunks):
                vector = file_vectors[offset] if offset < len(file_vectors) else None
                connection.execute(
                    "INSERT INTO chunks (path, corpus, ordinal, chunk_id, source_id, title, "
                    "heading, locator, page, keywords, text, sha256, model, dim, vector) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        relative, corpus, chunk["ordinal"], chunk["chunk_id"],
                        chunk["source_id"], chunk["title"], chunk["heading"],
                        chunk["locator"], chunk["page"], chunk["keywords"], chunk["text"],
                        text_digest(chunk["text"]), model if vector else None,
                        len(vector) if vector else None,
                        encode_vector(vector) if vector else None,
                    ),
                )
                stats["chunks"] += 1
            connection.execute(
                "INSERT INTO files (path, corpus, sha256, chunk_count, indexed_at) "
                "VALUES (?, ?, ?, ?, ?) ON CONFLICT(path) DO UPDATE SET "
                "corpus = excluded.corpus, sha256 = excluded.sha256, "
                "chunk_count = excluded.chunk_count, indexed_at = excluded.indexed_at",
                (relative, corpus, digest, len(chunks), stamp),
            )
            stats["files"] += 1
            stats["embedded"] += len(file_vectors)

        scope = set(collected)
        for relative, record in existing.items():
            if record["corpus"] in corpora and relative not in scope:
                connection.execute("DELETE FROM chunks WHERE path = ?", (relative,))
                connection.execute("DELETE FROM files WHERE path = ?", (relative,))
                stats["pruned"] += 1

        dimension = len(vectors[0]) if vectors else 0
        if vectors:
            set_meta(connection, "embed_model", model)
            set_meta(connection, "embed_dim", dimension)
        elif stats["chunks"] > 0:
            set_meta(connection, "embed_model", "")
            set_meta(connection, "embed_dim", 0)
        set_meta(connection, "schema_version", STORE_SCHEMA_VERSION)
        set_meta(connection, "built_at", stamp)
        set_meta(connection, "scopes", ",".join(corpora))
        set_meta(connection, "text_normalization", stats["normalization"])
        connection.commit()
        stats["embed_model"] = get_meta(connection, "embed_model", "") or ""
        stats["embed_dim"] = int(get_meta(connection, "embed_dim", 0) or 0)
        stats["note"] = embedding_note
        return stats
    finally:
        connection.close()


def bm25_rank(rows, query_terms):
    """Return (row_index, score) pairs ranked by BM25 over stored text."""
    counts_list = []
    lengths = []
    document_frequency = {}
    for row in rows:
        text = f"{row['title']} {row['heading']} {row['keywords'] or ''} {row['text']}"
        terms = tokenize(text)
        counts = {}
        for term in terms:
            counts[term] = counts.get(term, 0) + 1
        for term in counts:
            document_frequency[term] = document_frequency.get(term, 0) + 1
        counts_list.append(counts)
        lengths.append(len(terms))
    total = len(counts_list)
    if not total:
        return []
    average = (sum(lengths) / total) or 1.0
    ranked = []
    for index, counts in enumerate(counts_list):
        score = 0.0
        for term in dict.fromkeys(query_terms):
            frequency = counts.get(term, 0)
            if not frequency:
                continue
            matches = document_frequency.get(term, 0)
            idf = math.log(1 + (total - matches + 0.5) / (matches + 0.5))
            denominator = frequency + BM25_K1 * (1 - BM25_B + BM25_B * lengths[index] / average)
            score += idf * frequency * (BM25_K1 + 1) / denominator
        if score > 0:
            ranked.append((index, score))
    ranked.sort(key=lambda item: (-item[1], item[0]))
    return ranked


def reciprocal_rank_fusion(rankings):
    """Fuse several ranked index lists into one deterministic ranking."""
    fused = {}
    for ranking in rankings:
        for rank, (index, _score) in enumerate(ranking, start=1):
            entry = fused.setdefault(index, {"score": 0.0, "ranks": []})
            entry["score"] += 1.0 / (RRF_K + rank)
            entry["ranks"].append(rank)
    ordered = sorted(fused.items(), key=lambda item: (-item[1]["score"], item[0]))
    return [(index, entry["score"]) for index, entry in ordered]


def load_rows(connection, corpora):
    """Return every stored chunk for the requested corpora in deterministic order."""
    placeholders = ",".join("?" for _ in corpora)
    statement = (
        f"SELECT * FROM chunks WHERE corpus IN ({placeholders}) ORDER BY path, ordinal"
    )
    return [dict(row) for row in connection.execute(statement, tuple(corpora))]


def citation_for(row):
    """Return a provenance string for a chunk, matching AGENTS.md citation style."""
    if row["corpus"] == "chunks":
        identifier = f" [{row['chunk_id']}]" if row["chunk_id"] else ""
        return f"{row['path']} {row['locator']}{identifier}"
    return f"{row['path']} {row['locator']}"


def search_chunks(query, corpora=CORPORA, top_k=8, use_embeddings=None,
                  model=DEFAULT_EMBED_MODEL):
    """Return (results, note). Results carry citations, scores, and snippets."""
    connection = open_store()
    if connection is None:
        return None, "store not found; run 'python tools/rag.py index' first"
    try:
        rows = load_rows(connection, corpora)
        stored_model = get_meta(connection, "embed_model", "") or ""
        stored_dim = int(get_meta(connection, "embed_dim", 0) or 0)
    finally:
        connection.close()
    if not rows:
        return [], None

    query_terms = tokenize(query)
    lexical = bm25_rank(rows, query_terms)
    rankings = [lexical]
    rank_maps = [{index: rank for rank, (index, _score) in enumerate(lexical, start=1)}]
    note = ""

    vector_positions = [index for index, row in enumerate(rows) if row["vector"]]
    if use_embeddings is not False:
        if not vector_positions or not stored_model or not stored_dim:
            note = ("store holds no vectors; run 'index' with embeddings enabled "
                    "for semantic search")
        else:
            try:
                query_vector = embed_texts([query], stored_model)[0]
                matrix = [decode_vector(rows[index]["vector"]) for index in vector_positions]
                scores = cosine_scores(query_vector, matrix)
                ranked = sorted(
                    zip(vector_positions, scores), key=lambda item: (-item[1], item[0])
                )
                semantic = [(index, score) for index, score in ranked if score > 0]
                if semantic:
                    rankings.append(semantic)
                    rank_maps.append(
                        {index: rank for rank, (index, _score) in enumerate(semantic, start=1)}
                    )
            except OllamaUnavailable as exc:
                note = f"vector search unavailable ({exc}); results are lexical only"

    fused = reciprocal_rank_fusion(rankings)
    results = []
    for index, score in fused[:max(1, top_k)]:
        row = rows[index]
        results.append({
            "citation": citation_for(row),
            "path": row["path"],
            "corpus": row["corpus"],
            "title": row["title"],
            "heading": row["heading"],
            "locator": row["locator"],
            "chunk_id": row["chunk_id"],
            "source_id": row["source_id"],
            "page": row["page"],
            "score": round(score, 6),
            "bm25_rank": rank_maps[0].get(index),
            "vector_rank": rank_maps[1].get(index) if len(rank_maps) > 1 else None,
            "snippet": snippet(row["text"], query_terms),
            "text": row["text"][:EVIDENCE_CHARS],
        })
    return results, note


def format_results(results, note=None):
    """Render retrieval results for console output."""
    lines = []
    if note:
        lines.append(f"[rag] {note}")
        lines.append("")
    if not results:
        lines.append("No matching passages.")
        return "\n".join(lines)
    for position, result in enumerate(results, start=1):
        ranks = []
        if result["bm25_rank"]:
            ranks.append(f"bm25 #{result['bm25_rank']}")
        if result["vector_rank"]:
            ranks.append(f"vector #{result['vector_rank']}")
        suffix = f"  ({', '.join(ranks)})" if ranks else ""
        lines.append(f"{position}. [{result['score']:.4f}] {result['citation']}{suffix}")
        lines.append(f"   {result['snippet']}")
        lines.append("")
    return "\n".join(lines).rstrip()


CHAT_SYSTEM_PROMPT = (
    "You answer questions about a personal, agent-curated quantum-computing wiki "
    "using ONLY the CONTEXT passages provided. Cite every factual claim with the "
    "passage citation in square brackets, for example "
    "[wiki/concepts/qubit.md §Definition] or "
    "[index/extractions/...json p. 42 [src_...:p042:c03]]. Never invent citations, "
    "page numbers, or chunk IDs. If the CONTEXT does not answer the question, say so "
    "explicitly and name what is missing. Answer in well-structured Markdown and keep "
    "it concise."
)


def build_context(results):
    """Render retrieved passages as a citable context block."""
    blocks = []
    for position, result in enumerate(results, start=1):
        blocks.append(f"[{position}] {result['citation']}\n{result['text']}")
    return "\n\n".join(blocks)


def ollama_models():
    """Return the locally available Ollama model names, or None when unreachable."""
    request = urllib.request.Request(ollama_base() + "/api/tags")
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, OSError, ValueError):
        return None
    return [str(model.get("name") or "") for model in data.get("models") or []]


def ask_question(question, corpora=CORPORA, top_k=6, model=DEFAULT_CHAT_MODEL,
                 use_embeddings=None):
    """Return (answer, results, note) grounded in retrieved passages."""
    results, note = search_chunks(
        question, corpora=corpora, top_k=top_k, use_embeddings=use_embeddings
    )
    if results is None:
        return None, None, note
    if not results:
        return None, [], f"no matching passages in: {', '.join(corpora)}"
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT},
        {"role": "user", "content": f"QUESTION: {question}\n\nCONTEXT:\n{build_context(results)}"},
    ]
    try:
        response = ollama_request(
            "/api/chat", {"model": model, "messages": messages, "stream": False}
        )
    except OllamaUnavailable as exc:
        return None, results, f"local chat model unavailable ({exc}); showing passages instead"
    answer = ((response.get("message") or {}).get("content") or "").strip()
    if not answer:
        return None, results, "local chat model returned an empty answer"
    return answer, results, note


def current_digests(corpora):
    """Return {relative_path: sha256} for every indexable file in the corpora."""
    digests = {}
    if "wiki" in corpora:
        for path in iter_matching_files(WIKI_REL, ".md"):
            digests[display_path(os.path.relpath(path, ROOT))] = file_digest(path)
    if "chunks" in corpora:
        for path in iter_matching_files(EXTRACTIONS_REL, ".json"):
            digests[display_path(os.path.relpath(path, ROOT))] = file_digest(path)
    return digests


def store_stats(corpora=CORPORA):
    """Return a dictionary describing the derived store and any drift."""
    path = store_path()
    info = {
        "store": display_path(os.path.relpath(path, ROOT)),
        "exists": os.path.exists(path),
        "size_bytes": 0,
        "built_at": None,
        "scopes": None,
        "embed_model": "",
        "embed_dim": 0,
        "text_normalization": "",
        "indexed_files": 0,
        "indexed_chunks": 0,
        "files_by_corpus": {},
        "chunks_by_corpus": {},
        "stale": [],
        "unindexed": [],
        "missing": [],
        "ollama_models": ollama_models(),
    }
    if not info["exists"]:
        return info
    info["size_bytes"] = os.path.getsize(path)
    connection = open_store()
    try:
        info["built_at"] = get_meta(connection, "built_at")
        info["scopes"] = get_meta(connection, "scopes")
        info["embed_model"] = get_meta(connection, "embed_model", "") or ""
        info["embed_dim"] = int(get_meta(connection, "embed_dim", 0) or 0)
        info["text_normalization"] = get_meta(connection, "text_normalization", "") or ""
        for row in connection.execute(
            "SELECT corpus, COUNT(*) AS total FROM chunks GROUP BY corpus"
        ):
            info["chunks_by_corpus"][row["corpus"]] = row["total"]
            info["indexed_chunks"] += row["total"]
        stored = {}
        for row in connection.execute("SELECT path, corpus, sha256 FROM files"):
            stored[row["path"]] = (row["sha256"], row["corpus"])
            info["files_by_corpus"][row["corpus"]] = (
                info["files_by_corpus"].get(row["corpus"], 0) + 1
            )
            info["indexed_files"] += 1
    finally:
        connection.close()

    digests = current_digests(corpora)
    for relative, digest in sorted(digests.items()):
        if relative not in stored:
            info["unindexed"].append(relative)
        elif stored[relative][0] != digest:
            info["stale"].append(relative)
    info["missing"] = sorted(
        relative for relative, (_digest, corpus) in stored.items()
        if corpus in corpora and relative not in digests
    )
    return info


def format_stats(info):
    """Render store statistics for console output."""
    status = "present" if info["exists"] else "missing"
    lines = [f"Store: {info['store']} [{status}]"]
    if not info["exists"]:
        lines.append("Run 'python tools/rag.py index --scope all' to build it.")
        lines.extend(model_lines(info))
        return "\n".join(lines)
    lines.append(
        f"Size: {info['size_bytes'] / 1024:.1f} KiB | built: {info['built_at']} "
        f"| scopes: {info['scopes']}"
    )
    files = ", ".join(f"{name}={count}" for name, count in sorted(info["files_by_corpus"].items()))
    chunks = ", ".join(f"{name}={count}" for name, count in sorted(info["chunks_by_corpus"].items()))
    lines.append(f"Files indexed: {info['indexed_files']} ({files or 'none'})")
    lines.append(f"Chunks indexed: {info['indexed_chunks']} ({chunks or 'none'})")
    if info["embed_model"]:
        lines.append(f"Embeddings: {info['embed_model']} ({info['embed_dim']} dims)")
    else:
        lines.append("Embeddings: none stored (lexical BM25 retrieval only)")
    lines.append(f"Text normalization: {info['text_normalization'] or 'unknown'}")
    lines.append(
        f"Drift: {len(info['stale'])} changed, {len(info['unindexed'])} not indexed, "
        f"{len(info['missing'])} disappeared"
    )
    for label, key in (("changed", "stale"), ("not indexed", "unindexed"), ("disappeared", "missing")):
        for relative in info[key][:10]:
            lines.append(f"  - {label}: {relative}")
        if len(info[key]) > 10:
            lines.append(f"  - {label}: … {len(info[key]) - 10} more")
    lines.extend(model_lines(info))
    return "\n".join(lines)


def model_lines(info):
    """Describe local Ollama model availability relevant to RAG."""
    if info["ollama_models"] is None:
        return ["Ollama: unreachable at 127.0.0.1:11434 (lexical retrieval only)"]
    names = ", ".join(sorted(info["ollama_models"])) or "none"
    lines = [f"Ollama models: {names}"]
    if DEFAULT_EMBED_MODEL not in names:
        lines.append(
            f"  pull '{DEFAULT_EMBED_MODEL}' for semantic search: "
            f"ollama pull {DEFAULT_EMBED_MODEL}"
        )
    if DEFAULT_CHAT_MODEL not in names:
        lines.append(f"  '{DEFAULT_CHAT_MODEL}' is needed for 'ask'; otherwise use 'search'")
    return lines


def write_log(operation, title, description, affected, outcomes):
    """Append a fully resolved entry to log.md (append-only, AGENTS.md section 6)."""
    entry = [f"## [{now_iso()}] {operation} | {title}", "", description.strip(), ""]
    if affected:
        entry.append("Pages affected:")
        entry.extend(f"- [{item}]({item})" for item in affected)
        entry.append("")
    entry.append("Key outcomes:")
    entry.extend(f"- {item}" for item in outcomes)
    entry.append("")
    with open(repo_path(LOG_REL), "a", encoding="utf-8") as handle:
        handle.write("\n".join(entry) + "\n")


def corpora_for_scope(scope):
    """Map a CLI scope to the corpora to index or search."""
    if scope == "wiki":
        return ("wiki",)
    if scope == "chunks":
        return ("chunks",)
    return CORPORA


def index_action(scope, rebuild, use_embeddings, model, normalize=False):
    """Rebuild or refresh the derived retrieval store."""
    corpora = corpora_for_scope(scope)
    stats = build_index(
        corpora, rebuild=rebuild, use_embeddings=use_embeddings, model=model,
        normalize=normalize,
    )
    print(f"Store: {display_path(os.path.relpath(store_path(), ROOT))}")
    print(f"Scopes: {', '.join(corpora)}{' (rebuilt)' if rebuild else ''}")
    label = stats["normalization"]
    if label == "none":
        label += " (opt in to glue repair with --normalize)"
    print(f"Text normalization: {label}")
    print(
        f"Files written: {stats['files']}  chunks written: {stats['chunks']}  "
        f"unchanged skipped: {stats['skipped']}  pruned: {stats['pruned']}"
    )
    if stats["embed_model"]:
        print(
            f"Embeddings: {stats['embed_model']} ({stats['embed_dim']} dims), "
            f"{stats['embedded']} vectors written"
        )
    else:
        print("Embeddings: none (lexical BM25 retrieval only)")
    if stats["note"]:
        print(f"Note: {stats['note']}")
    if stats["files"] or stats["pruned"] or rebuild:
        outcomes = [
            f"Indexed {stats['chunks']} retrieval chunks from {stats['files']} file(s)",
            f"Skipped {stats['skipped']} unchanged file(s); pruned {stats['pruned']} stale record(s)",
            f"Text normalization: {stats['normalization']}",
        ]
        if stats["embed_model"]:
            outcomes.append(
                f"Stored {stats['embedded']} vectors using {stats['embed_model']} "
                f"({stats['embed_dim']} dims)"
            )
        else:
            outcomes.append("No vectors stored; retrieval is lexical (BM25) only")
        if stats["note"]:
            outcomes.append(stats["note"])
        write_log(
            "rag",
            f"Local retrieval index update ({scope})",
            "Refreshed the derived local-RAG store that backs retrieval for the agent, "
            "the CLI, and the MCP server. Canonical layers are unchanged.",
            [STORE_REL],
            outcomes,
        )
    return 0


def search_action(query, scope, top_k, as_json, use_embeddings):
    """Print ranked passages for a query."""
    corpora = corpora_for_scope(scope)
    results, note = search_chunks(
        query, corpora=corpora, top_k=top_k, use_embeddings=use_embeddings
    )
    if results is None:
        print(f"Error: {note}")
        return 1
    if as_json:
        payload = {
            "query": query,
            "corpora": list(corpora),
            "note": note or None,
            "results": results,
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0
    print(format_results(results, note))
    return 0


def ask_action(question, scope, top_k, model, use_embeddings):
    """Answer a question locally, grounded in retrieved passages."""
    corpora = corpora_for_scope(scope)
    answer, results, note = ask_question(
        question, corpora=corpora, top_k=top_k, model=model,
        use_embeddings=use_embeddings,
    )
    if results is None:
        print(f"Error: {note}")
        return 1
    if answer is None:
        print(format_results(results, note))
        return 3
    print(answer)
    print("\nSources:")
    for result in results:
        print(f"- {result['citation']}")
    if note:
        print(f"\n[rag] {note}", file=sys.stderr)
    return 0


def stats_action(as_json):
    """Report store contents, drift, and local model availability."""
    info = store_stats()
    if as_json:
        print(json.dumps(info, indent=2, ensure_ascii=False))
        return 0
    print(format_stats(info))
    return 0


def configure_console():
    """Make console output robust for Unicode citations on narrow terminals."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if stream is None or not reconfigure:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except (LookupError, ValueError):
            reconfigure(errors="replace")


def main():
    configure_console()
    parser = argparse.ArgumentParser(
        description="Local RAG over the Bob wiki (derived state in index/rag/)."
    )
    parser.add_argument("command", help="index | search | ask | stats | mcp")
    parser.add_argument("--scope", choices=("all", "wiki", "chunks"), default="all",
                        help="corpus selection (default all)")
    parser.add_argument("--query", help="search: query text")
    parser.add_argument("--question", help="ask: question text")
    parser.add_argument("--top-k", type=int, default=8,
                        help="search/ask: number of passages to return (default 8)")
    parser.add_argument("--json", action="store_true", dest="as_json",
                        help="emit machine-readable JSON")
    parser.add_argument("--rebuild", action="store_true",
                        help="index: discard and rebuild the store")
    parser.add_argument("--no-embeddings", action="store_true",
                        help="index/search: stay lexical (BM25) and never call Ollama")
    parser.add_argument("--normalize", action="store_true",
                        help="index: repair words glued by PDF extraction (opt-in; "
                             "measured marginal, can corrupt long words)")
    parser.add_argument("--embed-model", default=DEFAULT_EMBED_MODEL,
                        help=f"index: Ollama embedding model (default {DEFAULT_EMBED_MODEL})")
    parser.add_argument("--model", default=DEFAULT_CHAT_MODEL,
                        help=f"ask: Ollama chat model (default {DEFAULT_CHAT_MODEL})")
    args = parser.parse_args()

    command = args.command.lstrip("/").lower()
    use_embeddings = False if args.no_embeddings else None
    normalize = bool(args.normalize)
    if args.top_k is not None and args.top_k < 1:
        print("--top-k must be a positive integer")
        return 1
    try:
        if command == "index":
            return index_action(args.scope, args.rebuild, use_embeddings, args.embed_model,
                                normalize=normalize)
        if command == "search":
            if not args.query:
                print("search requires --query")
                return 1
            return search_action(args.query, args.scope, args.top_k, args.as_json, use_embeddings)
        if command == "ask":
            if not args.question:
                print("ask requires --question")
                return 1
            return ask_action(args.question, args.scope, args.top_k, args.model, use_embeddings)
        if command == "stats":
            return stats_action(args.as_json)
        if command == "mcp":
            print("The MCP server is a separate entry point: python tools/rag_mcp.py")
            return 0
        print("Unknown command:", command)
        return 2
    except (OSError, UnicodeError, ValueError, sqlite3.Error) as exc:
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
