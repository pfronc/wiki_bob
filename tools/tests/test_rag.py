import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


TOOLS_DIR = Path(__file__).resolve().parents[1]
RAG_PATH = TOOLS_DIR / "rag.py"
MCP_PATH = TOOLS_DIR / "rag_mcp.py"


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


rag = load_module("bob_rag", RAG_PATH)
rag_mcp = load_module("bob_rag_mcp", MCP_PATH)
convert = load_module("bob_convert", TOOLS_DIR / "convert.py")

CONCEPT_PAGE = """---
kind: concept
status: draft
aliases: ["quantum bit"]
topics: ["quantum computation"]
sources: ["../sources/test-book.md"]
source_ids: ["src_test"]
created: 2026-01-01
updated: 2026-01-01
last_reviewed:
category: Theory
---
# Qubit

Intro paragraph about the qubit.

## Definition

A qubit is the fundamental unit of quantum information, described by a
normalized superposition of two basis states.

## Measurement

Measurement collapses the qubit state onto a basis state with probabilities
given by the Born rule.

## Noise

Decoherence destroys superposition, which is why quantum error correction is
required.
"""

SOURCE_PAGE = """---
kind: source
status: verified
aliases: []
topics: []
sources: []
source_ids: ["src_test"]
created: 2026-01-01
updated: 2026-01-01
last_reviewed:
---
# Source: Test Book

## Key Takeaways

- Quantum mechanics constrains information processing.
"""

EXTRACTION = {
    "schema_version": 1,
    "source_id": "src_test",
    "raw_path": "raw/book.pdf",
    "sha256": "deadbeef",
    "format": "pdf",
    "status": "complete",
    "created": "2026-01-01T00:00:00+01:00",
    "updated": "2026-01-01T00:00:00+01:00",
    "unit_count": 2,
    "chunk_count": 2,
    "chunks": [
        {
            "chunk_id": "src_test:p001:c01",
            "ordinal": 1,
            "location": {"kind": "page", "page": 1},
            "text": "A short paragraph about Hilbert spaces and state vectors.",
            "status": "mapped",
        },
        {
            "chunk_id": "src_test:p042:c03",
            "ordinal": 2,
            "location": {"kind": "page", "page": 42},
            "text": (
                "The no-cloning theorem states that an unknown quantum state cannot be "
                "copied exactly, because copying is not a unitary operation on all states."
            ),
            "status": "mapped",
        },
    ],
    "error": None,
}


class RagTestCase(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_root = rag.ROOT
        self.original_mcp_root = rag_mcp.rag.ROOT
        rag.ROOT = str(self.root)
        rag_mcp.rag.ROOT = str(self.root)
        for relative in ("wiki/concepts", "wiki/sources", "index/extractions/src_test"):
            (self.root / relative).mkdir(parents=True, exist_ok=True)
        (self.root / "log.md").write_text("# Log\n\n", encoding="utf-8")
        (self.root / "index/source-registry.json").write_text(
            json.dumps({
                "schema_version": 1,
                "sources": [{
                    "source_id": "src_test",
                    "raw_path": "raw/book.pdf",
                    "source_page": "wiki/sources/test-book.md",
                }],
            }),
            encoding="utf-8",
        )
        self.write("wiki/concepts/qubit.md", CONCEPT_PAGE)
        self.write("wiki/sources/test-book.md", SOURCE_PAGE)
        self.write("index/extractions/src_test/deadbeef.json", json.dumps(EXTRACTION))

    def tearDown(self):
        rag.ROOT = self.original_root
        rag_mcp.rag.ROOT = self.original_mcp_root
        self.tempdir.cleanup()

    def write(self, relative, content):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def capture(self, function, *args, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = function(*args, **kwargs)
        return result, output.getvalue()

    def build(self, **kwargs):
        kwargs.setdefault("use_embeddings", False)
        return rag.build_index(rag.CORPORA, **kwargs)


    def test_wiki_chunks_follow_headings_and_drop_frontmatter(self):
        chunks = rag.wiki_page_chunks("wiki/concepts/qubit.md", CONCEPT_PAGE)
        self.assertEqual(["", "Definition", "Measurement", "Noise"],
                         [chunk["heading"] for chunk in chunks])
        self.assertEqual("wiki/concepts/qubit.md §Definition",
                         rag.citation_for(chunks[1]))
        body = " ".join(chunk["text"] for chunk in chunks)
        self.assertNotIn("kind: concept", body)
        self.assertIn("Born rule", body)
        self.assertEqual("Qubit", chunks[0]["title"])
        self.assertIn("quantum bit", chunks[0]["keywords"])

    def test_wiki_chunks_skip_source_map_and_candidate_concepts(self):
        page = (
            "---\nkind: source\n---\n# Source: Test Book\n\n"
            "## Summary\n\nReal summary text about quantum information.\n\n"
            "## Source Map\n\n"
            "- page 1: `src_test:p001:c01`; candidates: quantum, computation\n\n"
            "## Candidate Concepts\n\n- quantum (375 mapped chunks)\n\n"
            "## Key Takeaways\n\n- Real takeaway about qubits.\n"
        )
        chunks = rag.wiki_page_chunks("wiki/sources/test-book.md", page)
        self.assertEqual(["Summary", "Key Takeaways"],
                         [chunk["heading"] for chunk in chunks])
        body = " ".join(chunk["text"] for chunk in chunks)
        self.assertNotIn("src_test:p001:c01", body)
        self.assertNotIn("375 mapped chunks", body)

    def test_window_split_bounds_every_piece(self):
        paragraph = ("Measurement collapses the state onto a basis state. " * 90).strip()
        pieces = rag.window_split(paragraph)
        self.assertGreater(len(pieces), 1)
        for piece in pieces:
            self.assertLessEqual(len(piece), rag.CHUNK_TARGET_CHARS)
        page = f"---\nkind: concept\n---\n# Long\n\n## Body\n\n{paragraph}\n"
        chunks = rag.wiki_page_chunks("wiki/concepts/long.md", page)
        self.assertGreater(len(chunks), 1)
        self.assertEqual(f"§Body [1/{len(chunks)}]", chunks[0]["locator"])
        self.assertEqual(f"§Body [{len(chunks)}/{len(chunks)}]", chunks[-1]["locator"])
        self.assertIn("Measurement collapses", chunks[0]["text"])
        self.assertIn("Measurement collapses", chunks[-1]["text"][:200])

    def test_index_is_incremental_and_prunes_removed_files(self):
        stats = self.build(rebuild=True)
        self.assertEqual(3, stats["files"])
        self.assertGreaterEqual(stats["chunks"], 5)
        self.assertEqual("", stats["embed_model"])
        again = self.build()
        self.assertEqual(0, again["files"])
        self.assertEqual(3, again["skipped"])
        (self.root / "wiki/sources/test-book.md").unlink()
        pruned = self.build()
        self.assertEqual(1, pruned["pruned"])
        connection = rag.open_store()
        try:
            paths = {row["path"] for row in connection.execute("SELECT path FROM chunks")}
        finally:
            connection.close()
        self.assertNotIn("wiki/sources/test-book.md", paths)
        self.assertIn("wiki/concepts/qubit.md", paths)

    def test_stats_reports_drift(self):
        self.build(rebuild=True)
        info = rag.store_stats()
        self.assertEqual([], info["stale"])
        self.assertEqual([], info["unindexed"])
        self.assertEqual([], info["missing"])
        self.write("wiki/concepts/qubit.md", CONCEPT_PAGE + "\n## Extra\n\nNew material.\n")
        self.write("wiki/concepts/fresh.md", CONCEPT_PAGE.replace("# Qubit", "# Qudit"))
        (self.root / "wiki/sources/test-book.md").unlink()
        info = rag.store_stats()
        self.assertEqual(["wiki/concepts/qubit.md"], info["stale"])
        self.assertEqual(["wiki/concepts/fresh.md"], info["unindexed"])
        self.assertEqual(["wiki/sources/test-book.md"], info["missing"])
        rendered = rag.format_stats(info)
        self.assertIn("1 changed, 1 not indexed, 1 disappeared", rendered)

    def test_search_ranks_and_cites_both_corpora(self):
        self.build()
        wiki_results, _note = rag.search_chunks("Born rule collapse", corpora=("wiki",),
                                                top_k=3, use_embeddings=False)
        self.assertEqual("wiki/concepts/qubit.md §Measurement",
                         wiki_results[0]["citation"])
        chunk_results, _note = rag.search_chunks("no-cloning theorem", corpora=("chunks",),
                                                 top_k=3, use_embeddings=False)
        citation = chunk_results[0]["citation"]
        self.assertIn("p. 42", citation)
        self.assertIn("src_test:p042:c03", citation)
        self.assertEqual("src_test", chunk_results[0]["source_id"])
        self.assertEqual("Source: Test Book", chunk_results[0]["title"])
        self.assertIn("no-cloning theorem", chunk_results[0]["text"])

    def test_search_without_store_reports_error(self):
        results, note = rag.search_chunks("Born rule", use_embeddings=False)
        self.assertIsNone(results)
        self.assertIn("index", note)

    def test_cli_search_json_uses_env_root(self):
        self.build()
        environment = dict(os.environ, BOB_RAG_ROOT=str(self.root))
        completed = subprocess.run(
            [sys.executable, str(RAG_PATH), "search", "--query", "Born rule",
             "--json", "--no-embeddings"],
            capture_output=True, text=True, env=environment, check=False,
        )
        self.assertEqual(0, completed.returncode, completed.stderr)
        payload = json.loads(completed.stdout)
        self.assertEqual("Born rule", payload["query"])
        self.assertEqual(["wiki", "chunks"], payload["corpora"])
        self.assertIn("qubit.md", payload["results"][0]["citation"])

    def fake_embed(self, texts, model):
        """Deterministic stand-in for rag.embed_texts, so tests need no Ollama."""
        vectors = []
        for text in texts:
            lowered = text.casefold()
            vectors.append([
                1.0 if "no-cloning" in lowered else 0.0,
                1.0 if "qubit" in lowered else 0.0,
                1.0 if "born" in lowered else 0.0,
            ])
        return vectors

    def test_embeddings_are_stored_and_rank_results(self):
        with mock.patch.object(rag, "embed_texts", new=self.fake_embed):
            stats = self.build(rebuild=True, use_embeddings=True, model="test-embed")
            self.assertEqual("test-embed", stats["embed_model"])
            self.assertEqual(3, stats["embed_dim"])
            self.assertGreater(stats["embedded"], 0)
            results, note = rag.search_chunks("no-cloning", corpora=("chunks",), top_k=3)
        self.assertEqual("", note)
        self.assertEqual(
            "index/extractions/src_test/deadbeef.json p. 42 [src_test:p042:c03]",
            results[0]["citation"],
        )
        self.assertEqual(1, results[0]["vector_rank"])
        self.assertEqual(1, results[0]["bm25_rank"])

    def test_vector_search_degrades_when_ollama_is_unavailable(self):
        with mock.patch.object(rag, "embed_texts", new=self.fake_embed):
            self.build(rebuild=True, use_embeddings=True, model="test-embed")
        with mock.patch.object(rag, "embed_texts",
                               side_effect=rag.OllamaUnavailable("offline")):
            results, note = rag.search_chunks("no-cloning", corpora=("chunks",), top_k=2)
        self.assertTrue(results)
        self.assertIn("lexical only", note)
        self.assertIsNone(results[0]["vector_rank"])

    def test_index_action_logs_absence_of_embeddings(self):
        with mock.patch.object(rag, "embed_texts",
                               side_effect=rag.OllamaUnavailable("offline")):
            code, output = self.capture(rag.index_action, "all", False, None, "test-embed")
        self.assertEqual(0, code)
        self.assertIn("Embeddings: none (lexical BM25 retrieval only)", output)
        self.assertIn("embeddings unavailable", output)
        log = (self.root / "log.md").read_text(encoding="utf-8")
        self.assertIn("] rag | Local retrieval index update (all)", log)
        self.assertIn("index/rag/rag.sqlite3", log)
        self.assertIn("lexical (BM25) only", log)

    def test_index_action_is_silent_when_nothing_changed(self):
        self.capture(rag.index_action, "all", False, False, "test-embed")
        first_log = (self.root / "log.md").read_text(encoding="utf-8")
        code, output = self.capture(rag.index_action, "all", False, False, "test-embed")
        self.assertEqual(0, code)
        self.assertIn("unchanged skipped: 3", output)
        self.assertEqual(first_log, (self.root / "log.md").read_text(encoding="utf-8"))

    def test_mcp_tools_list_and_search_call(self):
        self.build()
        listing = rag_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        self.assertEqual(
            ["wiki_search", "wiki_ask", "wiki_stats"],
            [tool["name"] for tool in listing["result"]["tools"]],
        )
        initialized = rag_mcp.handle({
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-06-18"},
        })
        self.assertEqual("2025-06-18", initialized["result"]["protocolVersion"])
        self.assertEqual("bob-rag", initialized["result"]["serverInfo"]["name"])
        self.assertIsNone(
            rag_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"})
        )
        called = rag_mcp.handle({
            "jsonrpc": "2.0", "id": 2, "method": "tools/call",
            "params": {"name": "wiki_search", "arguments": {"query": "Born rule", "top_k": 2}},
        })
        self.assertFalse(called["result"]["isError"])
        self.assertIn("wiki/concepts/qubit.md §Measurement",
                      called["result"]["content"][0]["text"])
        unknown = rag_mcp.handle({
            "jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "nope"},
        })
        self.assertEqual(-32602, unknown["error"]["code"])
        missing = rag_mcp.handle({
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "wiki_search", "arguments": {}},
        })
        self.assertTrue(missing["result"]["isError"])

    def test_mcp_reports_missing_store(self):
        response = rag_mcp.handle({
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "wiki_search", "arguments": {"query": "Born rule"}},
        })
        self.assertTrue(response["result"]["isError"])
        self.assertIn("index", response["result"]["content"][0]["text"])

    def test_ask_degrades_to_passages_when_model_is_unavailable(self):
        self.build()
        with mock.patch.object(rag, "ollama_request",
                               side_effect=rag.OllamaUnavailable("offline")):
            answer, results, note = rag.ask_question("What is the Born rule?", top_k=2)
        self.assertIsNone(answer)
        self.assertTrue(results)
        self.assertIn("unavailable", note)
        with mock.patch.object(rag_mcp.rag, "ollama_request",
                               side_effect=rag_mcp.rag.OllamaUnavailable("offline")):
            response = rag_mcp.tool_ask({"question": "Born rule", "top_k": 2})
        self.assertFalse(response["isError"])
        self.assertIn("Retrieved passages", response["content"][0]["text"])

    def stored_text(self, page=None):
        """Return stored chunk text for a raw-page locator."""
        connection = rag.open_store()
        try:
            row = connection.execute(
                "SELECT text FROM chunks WHERE corpus = 'chunks' AND page = ?", (page,)
            ).fetchone()
        finally:
            connection.close()
        return row["text"] if row else None

    def test_split_glued_token_uses_vocabulary(self):
        vocab = {"no": 5, "cloning": 3, "theorem": 4, "information": 9, "quantum": 8}
        self.assertEqual("no cloning theorem",
                         rag.split_glued_token("nocloningtheorem", vocab))
        self.assertIsNone(rag.split_glued_token("cloning", vocab))
        self.assertIsNone(rag.split_glued_token("counterrevolutionaries", vocab))
        self.assertIsNone(rag.split_glued_token("Nielsen2010", vocab))

    def test_normalize_is_idempotent_and_leaves_short_runs(self):
        vocab = {"no": 5, "cloning": 3, "theorem": 4}
        text = "The nocloningtheorem holds. A nocloningwordx stays."
        once = rag.normalize_glued_text(text, vocab)
        self.assertIn("no cloning theorem", once)
        self.assertIn("nocloningwordx", once)
        self.assertEqual(once, rag.normalize_glued_text(once, vocab))
        self.assertEqual(text, rag.normalize_glued_text(text, {}))
        self.assertEqual("already spaced text",
                         rag.normalize_glued_text("already spaced text", vocab))

    def test_index_defaults_to_raw_text_and_repair_is_opt_in(self):
        words = ["information", "is", "physical", "and", "quantum", "computation",
                 "uses", "no", "cloning", "theorem", "for", "quantum", "information"]
        clean = " ".join(words) + ". " + " ".join(words) + "."
        glued = "".join(words)
        glued = glued[0].upper() + glued[1:]
        self.assertGreaterEqual(len(glued), rag.MIN_CHUNK_CHARS)
        record = dict(EXTRACTION)
        record["chunks"] = [
            {"chunk_id": "src_test:p001:c01", "ordinal": 1,
             "location": {"kind": "page", "page": 1}, "text": clean, "status": "mapped"},
            {"chunk_id": "src_test:p002:c01", "ordinal": 2,
             "location": {"kind": "page", "page": 2}, "text": glued, "status": "mapped"},
        ]
        self.write("index/extractions/src_test/deadbeef.json", json.dumps(record))

        default_stats = self.build(rebuild=True)
        self.assertEqual("none", default_stats["normalization"])
        self.assertEqual(glued, self.stored_text(2))

        repaired_stats = self.build(rebuild=True, normalize=True)
        self.assertEqual("glue-repair", repaired_stats["normalization"])
        repaired = self.stored_text(2)
        self.assertNotEqual(glued, repaired)
        self.assertIn("quantum computation", repaired)
        self.assertIn("no cloning theorem", repaired)

        switched = self.build()
        self.assertEqual("none", switched["normalization"])
        self.assertEqual(glued, self.stored_text(2))
        self.assertEqual(1, switched["files"])
        self.assertEqual(2, switched["skipped"])


class ConvertTestCase(unittest.TestCase):
    """Hermetic tests for tools/convert.py (markitdown is stubbed, never imported)."""

    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_root = convert.ROOT
        convert.ROOT = str(self.root)

    def tearDown(self):
        convert.ROOT = self.original_root
        self.tempdir.cleanup()

    def write(self, relative, content=b"data"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        data = content.encode("utf-8") if isinstance(content, str) else content
        path.write_bytes(data)
        return str(path)

    def test_kebab_mirrors_runner_normalisation(self):
        self.assertEqual("my-talk-2024", convert.kebab("My Talk (2024)!"))
        self.assertEqual("converted", convert.kebab("!!!") or "converted")

    def test_native_formats_are_refused_before_conversion(self):
        for name in ("paper.pdf", "notes.docx", "plain.md", "raw.txt"):
            self.write(name)
        code = convert.convert_action(str(self.root / name), "index/converted",
                                       False, False)
        self.assertEqual(1, code)
        self.assertFalse((self.root / "index/converted").exists())

    def test_unsupported_format_is_skipped(self):
        self.write("archive.7z")
        self.assertEqual(1, convert.convert_action(
            str(self.root / "archive.7z"), "index/converted", False, False))

    def test_missing_source_reports_error(self):
        self.assertEqual(1, convert.convert_action(
            str(self.root / "nope.pptx"), "index/converted", False, False))

    def test_missing_markitdown_reports_install_hint(self):
        self.write("talk.pptx")
        with mock.patch.object(convert, "load_markitdown", return_value=None):
            code = convert.convert_action(str(self.root / "talk.pptx"),
                                          "index/converted", False, False)
        self.assertEqual(3, code)

    def test_binary_fallback_reports_format_extra(self):
        self.write("slides.pptx", b"\x00\x01binary")
        class FakeResult:
            text_content = "PK\x03\x04binary-blob"
        class FakeConverter:
            def convert(self, _path):
                return FakeResult()
        with mock.patch.object(convert, "load_markitdown",
                                return_value=FakeConverter):
            code = convert.convert_action(str(self.root / "slides.pptx"),
                                          "index/converted", False, False)
        self.assertEqual(1, code)
        self.assertFalse((self.root / "index/converted").exists())

    def test_successful_conversion_stages_markdown_with_provenance(self):
        self.write("My Talk (2024).pptx", b"\x00\x01fake")
        class FakeResult:
            text_content = "# Slides\n\nContent here."
        class FakeConverter:
            def convert(self, _path):
                return FakeResult()
        with mock.patch.object(convert, "load_markitdown",
                                return_value=FakeConverter):
            code = convert.convert_action(str(self.root / "My Talk (2024).pptx"),
                                          "index/converted", False, False)
        self.assertEqual(0, code)
        staged = self.root / "index/converted/my-talk-2024.md"
        self.assertTrue(staged.exists())
        body = staged.read_text(encoding="utf-8")
        self.assertIn("converted from", body.splitlines()[0])
        self.assertIn("# Slides", body)

    def test_stdout_mode_prints_without_writing(self):
        self.write("page.html", "<h1>Hi</h1>")
        class FakeResult:
            text_content = "# Hi"
        class FakeConverter:
            def convert(self, _path):
                return FakeResult()
        with mock.patch.object(convert, "load_markitdown",
                                return_value=FakeConverter):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = convert.convert_action(str(self.root / "page.html"),
                                              "index/converted", True, False)
        self.assertEqual(0, code)
        self.assertIn("# Hi", output.getvalue())
        self.assertFalse((self.root / "index/converted").exists())

    def test_formats_action_lists_supported_extensions(self):
        with mock.patch.object(convert, "load_markitdown", return_value=object):
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                code = convert.formats_action()
        self.assertEqual(0, code)
        self.assertIn(".pptx", output.getvalue())
        self.assertIn("PDF is intentionally excluded", output.getvalue())

