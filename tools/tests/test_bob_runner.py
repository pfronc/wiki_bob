import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from typing import Any
import unittest
from unittest import mock


RUNNER_PATH = Path(__file__).resolve().parents[1] / "bob_runner.py"
SPEC = importlib.util.spec_from_file_location("bob_runner", RUNNER_PATH)
assert SPEC is not None
assert SPEC.loader is not None
bob: Any = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bob)


class BobRunnerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_root = bob.ROOT
        bob.ROOT = str(self.root)
        for path in (
            "raw",
            "wiki/entities",
            "wiki/concepts",
            "wiki/sources",
            "wiki/analyses",
            "index",
            ".bob/commands",
        ):
            (self.root / path).mkdir(parents=True, exist_ok=True)
        (self.root / "log.md").write_text("# Log\n\n", encoding="utf-8")
        (self.root / ".bob/commands/research.md").write_text("# Research\n", encoding="utf-8")

    def tearDown(self):
        bob.ROOT = self.original_root
        self.tempdir.cleanup()

    def capture(self, function, *args, **kwargs):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            result = function(*args, **kwargs)
        return result, output.getvalue()

    def write_index(self, number, content=None):
        path = self.root / "index" / f"index_{number:03d}.md"
        if content is None:
            content = (
                f"# Wiki Index [{number:03d}]\n\nLast updated: 2026-01-01\n"
                "Total Pages: 0\nToken count: ~0\n\n## Entities\n\n"
                "## Concepts\n\n## Sources\n\n## Analyses\n"
            )
        path.write_text(content, encoding="utf-8")
        return path

    def test_create_page_supports_all_types_and_duplicate_failure(self):
        expected = {
            "entity": "entities",
            "concept": "concepts",
            "source": "sources",
            "analysis": "analyses",
        }
        for page_type, directory in expected.items():
            with self.subTest(page_type=page_type):
                filename = f"page {page_type}.md"
                self.assertEqual(0, bob.create_page_action(page_type, page_type.title(), filename))
                page = self.root / "wiki" / directory / filename
                self.assertTrue(page.is_file())
                text = page.read_text(encoding="utf-8")
                properties = bob.frontmatter_metadata(text)
                self.assertIsNotNone(properties)
                self.assertEqual(page_type, properties["kind"])
                self.assertEqual("draft", properties["status"])
                for field in ("aliases", "topics", "sources", "source_ids"):
                    self.assertIsInstance(properties[field], list)
                for heading in ("## Summary", "## Related Pages", "## Sources"):
                    self.assertIn(heading, text)
                self.assertRegex(text, r"\*(?:Last updated:|Ingested:|Created:) \d{4}-\d{2}-\d{2}\*")
                if page_type == "source":
                    for field in ("ingest_status", "extraction_status", "source_type", "author", "year"):
                        self.assertIn(field, properties)
                    for field in ("Type", "Author", "Original location", "Source ID", "Extraction status"):
                        self.assertIn(f"**{field}**:", text)
                if page_type == "entity":
                    self.assertIn("entity_type", properties)
                    self.assertIsInstance(properties["related_concepts"], list)
                if page_type == "analysis":
                    self.assertFalse((self.root / "wiki/analysiss" / filename).exists())
                self.assertEqual(1, bob.create_page_action(page_type, page_type.title(), filename))
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertIn("Lint health report (read-only)", output)
        self.assertIn("Managed pages scanned: 4", output)

    def test_create_page_rejects_existing_canonical_title_or_alias(self):
        existing = self.root / "wiki/concepts/quantum-computing.md"
        existing.write_text(
            "# Quantum Computing\n\n**Canonical title**: Quantum Computing\n"
            "**Aliases**: QC, Quantum Computation\n\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        result, output = self.capture(
            bob.create_page_action, "concept", "Quantum Computation", "duplicate.md"
        )
        self.assertEqual(1, result)
        self.assertIn("Duplicate canonical title or alias", output)
        self.assertFalse((self.root / "wiki/concepts/duplicate.md").exists())

    def test_create_source_marks_registry_title_match_for_review(self):
        registry = {
            "schema_version": 1,
            "sources": [{
                "source_id": "src_20260101_paper",
                "raw_path": "raw/paper.md",
                "sha256": "0" * 64,
                "format": "md",
                "source_page": None,
                "extraction_status": "pending",
                "ingest_status": "pending",
                "last_processed": "2026-01-01T00:00:00+00:00",
            }],
        }
        (self.root / "index/source-registry.json").write_text(
            json.dumps(registry), encoding="utf-8"
        )
        result, output = self.capture(bob.create_page_action, "source", "Paper", "paper-page.md")
        self.assertEqual(0, result)
        self.assertIn("Identity review candidate", output)
        text = (self.root / "wiki/sources/paper-page.md").read_text(encoding="utf-8")
        self.assertIn("**Identity review**: needs-review", text)

    def test_create_page_rejects_invalid_type_and_path_without_writes(self):
        original_log = (self.root / "log.md").read_text(encoding="utf-8")
        self.assertEqual(1, bob.create_page_action("note", "Bad", "bad.md"))
        self.assertEqual(1, bob.create_page_action("concept", "Bad", "..\\bad.md"))
        self.assertEqual(1, bob.create_page_action("concept", "!!!", None))
        self.assertEqual(original_log, (self.root / "log.md").read_text(encoding="utf-8"))

    def test_create_page_invalid_log_is_atomic(self):
        (self.root / "log.md").write_bytes(b"\xff")
        result, output = self.run_main([
            "create-page", "--type", "concept", "--title", "Atomic Page"
        ])
        self.assertEqual(1, result)
        self.assertIn("Error:", output)
        self.assertFalse((self.root / "wiki/concepts/atomic-page.md").exists())

    def test_find_index_file_uses_numeric_order_for_one_two_and_many(self):
        self.write_index(2)
        self.assertEqual("index_002.md", Path(bob.find_index_file()).name)
        self.write_index(9)
        self.assertEqual("index_009.md", Path(bob.find_index_file()).name)
        for number in list(range(1, 9)) + [10, 11, 12]:
            self.write_index(number)
        (self.root / "index/index_latest.md").write_text("ignored", encoding="utf-8")
        self.assertEqual("index_012.md", Path(bob.find_index_file()).name)

    def test_ingest_success_with_spaces_and_windows_separator(self):
        self.write_index(1)
        source = self.root / "raw" / "folder with spaces" / "source file.md"
        source.parent.mkdir()
        source.write_text("# Useful Source\n\nBody text.\n", encoding="utf-8")
        result, _ = self.capture(bob.ingest_action, "folder with spaces\\source file.md")
        self.assertEqual(0, result)
        self.assertTrue((self.root / "wiki/sources/useful-source.md").is_file())
        self.assertIn("../wiki/sources/useful-source.md", (self.root / "index/index_001.md").read_text(encoding="utf-8"))

    def test_ingest_invalid_utf8_is_atomic(self):
        self.write_index(1)
        (self.root / "raw/binary.txt").write_bytes(b"\xff\xfe")
        original_log = (self.root / "log.md").read_text(encoding="utf-8")
        self.assertEqual(1, bob.ingest_action("binary.txt"))
        self.assertEqual([], list((self.root / "wiki/sources").iterdir()))
        self.assertEqual(original_log, (self.root / "log.md").read_text(encoding="utf-8"))

    def test_ingest_invalid_index_is_atomic(self):
        (self.root / "raw/source.md").write_text("# Source\n", encoding="utf-8")
        index = self.write_index(1)
        index.write_bytes(b"\xff")
        result, output = self.run_main(["ingest", "--source", "source.md"])
        self.assertEqual(1, result)
        self.assertIn("Error:", output)
        self.assertFalse((self.root / "wiki/sources/source.md").exists())

    def test_ingest_rejects_unsupported_format_before_page_creation(self):
        self.write_index(1)
        (self.root / "raw/archive.zip").write_bytes(b"not a supported document")
        result, output = self.capture(bob.ingest_action, "archive.zip")
        self.assertEqual(1, result)
        self.assertIn("unsupported source format", output)
        self.assertEqual([], list((self.root / "wiki/sources").iterdir()))
        registry = json.loads((self.root / "index/source-registry.json").read_text(encoding="utf-8"))
        self.assertEqual("unsupported", registry["sources"][0]["extraction_status"])
        self.assertEqual("failed", registry["sources"][0]["ingest_status"])

    def test_chunked_ingest_is_bounded_stable_and_resumable(self):
        self.write_index(1)
        source = self.root / "raw/large.md"
        source.write_text(
            "# Large Source\n\n" + ("alpha quantum system. " * 240) +
            "\n\n## Second Section\n\n" + ("beta entanglement state. " * 240),
            encoding="utf-8",
        )
        result, output = self.capture(bob.ingest_action, "large.md", max_chunks=1)
        self.assertEqual(0, result)
        self.assertIn("remaining:", output)
        registry_path = self.root / "index/source-registry.json"
        first_record = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual("partial", first_record["ingest_status"])
        page = self.root / first_record["source_page"]
        partial_text = page.read_text(encoding="utf-8")
        self.assertIn("Partial ingest", partial_text)
        self.assertNotIn("## Source Map", partial_text)
        self.assertNotIn("## Candidate Concepts", partial_text)
        partial_properties = bob.frontmatter_metadata(partial_text)
        self.assertEqual("source", partial_properties["kind"])
        self.assertEqual("partial", partial_properties["ingest_status"])
        self.assertEqual([first_record["source_id"]], partial_properties["source_ids"])
        state_path = self.root / first_record["extraction_file"]
        first_state = json.loads(state_path.read_text(encoding="utf-8"))
        first_ids = [chunk["chunk_id"] for chunk in first_state["chunks"]]
        self.assertTrue(all(len(chunk["text"]) <= bob.MAX_CHUNK_CHARS for chunk in first_state["chunks"]))
        self.assertEqual(1, sum(chunk["status"] == "mapped" for chunk in first_state["chunks"]))

        self.assertEqual(0, bob.ingest_action("large.md"))
        final_record = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        final_state = json.loads(state_path.read_text(encoding="utf-8"))
        self.assertEqual("complete", final_record["ingest_status"])
        self.assertEqual(first_ids, [chunk["chunk_id"] for chunk in final_state["chunks"]])
        self.assertTrue(all(chunk["status"] == "mapped" for chunk in final_state["chunks"]))
        complete_text = page.read_text(encoding="utf-8")
        self.assertNotIn("Partial ingest", complete_text)
        self.assertNotIn("## Source Map", complete_text)
        self.assertNotIn("## Candidate Concepts", complete_text)
        self.assertEqual("complete", bob.frontmatter_metadata(complete_text)["ingest_status"])
        index_text = (self.root / "index/index_001.md").read_text(encoding="utf-8")
        self.assertEqual(1, index_text.count("../wiki/sources/large-source.md"))

    def test_pdf_and_docx_ingest_preserve_extractor_coordinates(self):
        self.write_index(1)
        cases = {
            "paper.pdf": {"kind": "page", "page": 42},
            "report.docx": {
                "kind": "section", "section": 3, "heading": "Results",
                "paragraph_start": 8, "paragraph_end": 11,
            },
        }
        for filename, location in cases.items():
            with self.subTest(filename=filename):
                (self.root / "raw" / filename).write_bytes(filename.encode("ascii"))
                function = "extract_pdf_units" if filename.endswith("pdf") else "extract_docx_units"
                units = [{"unit": 1, "location": location, "text": "Quantum measurement result."}]
                with mock.patch.object(bob, function, return_value=units):
                    self.assertEqual(0, bob.ingest_action(filename))
                registry = json.loads((self.root / "index/source-registry.json").read_text(encoding="utf-8"))
                record = next(item for item in registry["sources"] if item["raw_path"].endswith(filename))
                state = json.loads((self.root / record["extraction_file"]).read_text(encoding="utf-8"))
                self.assertEqual(location, state["chunks"][0]["location"])
                expected = ":p042:c01" if filename.endswith("pdf") else ":s003:c01"
                self.assertTrue(state["chunks"][0]["chunk_id"].endswith(expected))

    def test_ipynb_ingest_extracts_cells_with_stdlib_only(self):
        self.write_index(1)
        notebook = {
            "cells": [
                {
                    "cell_type": "markdown",
                    "source": ["# Entanglement\n", "\n", "Bell pairs correlate."],
                },
                {
                    "cell_type": "code",
                    "source": ["from qiskit import QuantumCircuit\n", "qc = QuantumCircuit(2)"],
                    "outputs": [
                        {"output_type": "stream", "text": ["hello\n"]},
                        {
                            "output_type": "execute_result",
                            "data": {"text/plain": ["<Result>"], "image/png": "iVBOR="},
                        },
                    ],
                },
                {"cell_type": "code", "source": []},
            ],
        }
        (self.root / "raw/lab.ipynb").write_text(json.dumps(notebook), encoding="utf-8")
        self.assertEqual(0, bob.ingest_action("lab.ipynb"))
        registry = json.loads((self.root / "index/source-registry.json").read_text(encoding="utf-8"))
        record = registry["sources"][0]
        self.assertEqual("ipynb", record["format"])
        self.assertEqual("complete", record["ingest_status"])
        state = json.loads((self.root / record["extraction_file"]).read_text(encoding="utf-8"))
        self.assertEqual(2, len(state["chunks"]))
        self.assertEqual({"kind": "cell", "cell": 1, "cell_type": "markdown"},
                         state["chunks"][0]["location"])
        self.assertTrue(state["chunks"][0]["chunk_id"].endswith(":n001:c01"))
        self.assertEqual({"kind": "cell", "cell": 2, "cell_type": "code"},
                         state["chunks"][1]["location"])
        code_text = state["chunks"][1]["text"]
        self.assertIn("QuantumCircuit(2)", code_text)
        self.assertIn("hello", code_text)
        self.assertNotIn("iVBOR", code_text)

    def test_ipynb_ingest_rejects_invalid_notebook(self):
        self.write_index(1)
        (self.root / "raw/broken.ipynb").write_text('{"cells": "not-a-list"}', encoding="utf-8")
        result, output = self.capture(bob.ingest_action, "broken.ipynb")
        self.assertEqual(1, result)
        self.assertIn("IPYNB extraction failed", output)
        self.assertEqual([], list((self.root / "wiki/sources").iterdir()))

    def test_extraction_failure_records_error_without_source_page(self):
        self.write_index(1)
        (self.root / "raw/broken.pdf").write_bytes(b"broken")
        with mock.patch.object(bob, "extract_pdf_units", side_effect=RuntimeError("page 2 corrupt")):
            result, output = self.capture(bob.ingest_action, "broken.pdf")
        self.assertEqual(1, result)
        self.assertIn("page 2 corrupt", output)
        self.assertEqual([], list((self.root / "wiki/sources").iterdir()))
        record = json.loads(
            (self.root / "index/source-registry.json").read_text(encoding="utf-8")
        )["sources"][0]
        self.assertEqual("failed", record["extraction_status"])
        self.assertEqual("page 2 corrupt", record["extraction_error"])

    def test_registry_detects_unchanged_changed_and_renamed_source(self):
        self.write_index(1)
        source = self.root / "raw/source.md"
        source.write_text("# Stable Title\n\nFirst version.\n", encoding="utf-8")
        self.assertEqual(0, bob.ingest_action("source.md"))
        registry_path = self.root / "index/source-registry.json"
        first = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        source_id = first["source_id"]
        first_page = first["source_page"]

        result, output = self.capture(bob.ingest_action, "source.md")
        self.assertEqual(0, result)
        self.assertIn("Source unchanged", output)
        self.assertEqual(1, len(list((self.root / "wiki/sources").glob("*.md"))))

        source.write_text("# Stable Title\n\nSecond version.\n", encoding="utf-8")
        result, status_output = self.capture(bob.status_action)
        self.assertEqual(0, result)
        self.assertIn("source.md [changed]", status_output)
        changed = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual(source_id, changed["source_id"])
        self.assertEqual(first_page, changed["versions"][0]["source_page"])
        self.assertIsNone(changed["source_page"])

        self.assertEqual(0, bob.ingest_action("source.md"))
        current = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual("complete", current["ingest_status"])
        self.assertNotEqual(first_page, current["source_page"])
        self.assertTrue((self.root / first_page).is_file())
        self.assertTrue((self.root / current["source_page"]).is_file())

        renamed = self.root / "raw/renamed.md"
        source.rename(renamed)
        result, raw_output = self.capture(bob.raw_list_action)
        self.assertEqual(0, result)
        self.assertIn("renamed.md", raw_output)
        renamed_record = json.loads(registry_path.read_text(encoding="utf-8"))["sources"][0]
        self.assertEqual(source_id, renamed_record["source_id"])
        self.assertEqual("raw/renamed.md", renamed_record["raw_path"])
        self.assertEqual("complete", renamed_record["ingest_status"])

    def test_registry_detects_content_duplicates_and_duplicate_titles(self):
        self.write_index(1)
        (self.root / "raw/one.md").write_text("# Same Title\n\nAlpha.\n", encoding="utf-8")
        self.assertEqual(0, bob.ingest_action("one.md"))
        (self.root / "raw/copy.md").write_text("# Same Title\n\nAlpha.\n", encoding="utf-8")

        result, status_output = self.capture(bob.status_action)
        self.assertEqual(0, result)
        result, raw_output = self.capture(bob.raw_list_action)
        self.assertEqual(0, result)
        self.assertIn("1 duplicate", status_output)
        self.assertIn("copy.md", raw_output)
        self.assertIn("[duplicate]", raw_output)
        registry = json.loads((self.root / "index/source-registry.json").read_text(encoding="utf-8"))
        self.assertEqual(2, len(registry["sources"]))
        self.assertEqual(1, sum(bool(item.get("duplicate_of")) for item in registry["sources"]))

        (self.root / "raw/one.md").unlink()
        result, raw_output = self.capture(bob.raw_list_action)
        self.assertEqual(0, result)
        self.assertIn("copy.md", raw_output)
        self.assertIn("[complete]", raw_output)

        (self.root / "raw/different.md").write_text("# Same Title\n\nBeta.\n", encoding="utf-8")
        self.assertEqual(0, bob.ingest_action("different.md"))
        pages = list((self.root / "wiki/sources").glob("*.md"))
        self.assertEqual(2, len(pages))
        self.assertEqual(2, len({path.name for path in pages}))

    def test_move_updates_source_registry_page_mapping(self):
        self.write_index(1)
        (self.root / "raw/source.md").write_text("# Source\n", encoding="utf-8")
        self.assertEqual(0, bob.ingest_action("source.md"))
        self.assertEqual(0, bob.move_action("wiki/sources/source.md", "wiki/sources/moved.md"))
        self.assertFalse((self.root / "wiki/sources/source.md").exists())
        self.assertTrue((self.root / "wiki/sources/moved.md").exists())
        registry = json.loads((self.root / "index/source-registry.json").read_text(encoding="utf-8"))
        self.assertEqual("wiki/sources/moved.md", registry["sources"][0]["source_page"])

    def test_query_success_and_missing_index_failure(self):
        (self.root / "wiki/concepts/gate.md").write_text(
            "# Quantum Gate\n\n## Summary\nA unitary operation.\n\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        self.write_index(1, "# Index\n\n## Concepts\n- [Quantum Gate](../wiki/concepts/gate.md) - unitary\n")
        result, output = self.capture(bob.query_action, "quantum")
        self.assertEqual(0, result)
        self.assertIn("Quantum Gate", output)
        shutil.rmtree(self.root / "index")
        self.assertEqual(1, bob.query_action("quantum"))

    def test_query_searches_all_parts_ranks_deduplicates_and_skips_stale_links(self):
        alias_page = self.root / "wiki/concepts/quantum-bit.md"
        alias_page.write_text(
            bob.frontmatter(
                "concept", aliases=["Qubit"], topics=["quantum information"],
                sources=["wiki/sources/one.md"], source_ids=["manual:one"],
                updated="2026-09-16",
            ) + "# Quantum Bit\n\n## Summary\nThe basic unit of quantum information.\n\n"
            "## Related Pages\n- [Measurement](measurement.md)\n\n*Last updated: 2026-09-16*\n",
            encoding="utf-8",
        )
        operation_page = self.root / "wiki/concepts/qubit-operations.md"
        operation_page.write_text(
            bob.frontmatter("concept", updated="2024-01-01") +
            "# Qubit Operations\n\n## Summary\nOperations on quantum states.\n\n"
            "*Last updated: 2024-01-01*\n",
            encoding="utf-8",
        )
        measurement_page = self.root / "wiki/concepts/measurement.md"
        measurement_page.write_text(
            bob.frontmatter("concept", updated="2025-01-01") +
            "# Measurement\n\n## Summary\nObservation of a state.\n\n"
            "*Last updated: 2025-01-01*\n",
            encoding="utf-8",
        )
        self.write_index(
            1,
            "# Index\n\n## Concepts\n"
            "- [Quantum Bit](../wiki/concepts/quantum-bit.md) - quantum information\n"
            "- [Ghost Qubit](../wiki/concepts/missing.md) - stale target\n",
        )
        self.write_index(
            2,
            "# Index\n\n## Concepts\n"
            "- [Qubit Operations](../wiki/concepts/qubit-operations.md) - operations\n"
            "- [Quantum Bit](../wiki/concepts/quantum-bit.md) - duplicate\n"
            "- [Measurement](../wiki/concepts/measurement.md) - observation\n",
        )
        result, output = self.capture(bob.query_action, "qubit")
        self.assertEqual(0, result)
        self.assertIn("Candidates from 2 index part(s)", output)
        self.assertIn("Qubit Operations", output)
        self.assertIn("Quantum Bit", output)
        self.assertIn("Measurement", output)  # Included through graph proximity.
        self.assertNotIn("Ghost Qubit", output)
        self.assertEqual(1, output.count("[Quantum Bit]("))
        self.assertLess(output.index("Qubit Operations"), output.index("Quantum Bit"))

    def test_lint_success_and_failure_paths(self):
        page = self.root / "wiki/concepts/test.md"
        page.write_text("# Test\n\n[Missing](missing.md)\n\n*Last updated: 2026-01-01*\n", encoding="utf-8")
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertIn("Broken link", output)
        shutil.rmtree(self.root / "wiki")
        self.assertEqual(1, bob.lint_action())

    def test_lint_reports_schema_provenance_duplicates_and_malformed_links(self):
        source = self.root / "wiki/sources/source.md"
        source.write_text(
            "# Source\n\n**Type**: Paper\n**Author**: A\n"
            "**Original location**: raw/source.md\n**Source ID**: manual:source\n"
            "**Extraction status**: not-applicable\n\n## Summary\nSummary.\n\n"
            "## Key Takeaways\n- One.\n\n## Entities Mentioned\n- None.\n\n"
            "## Concepts Discussed\n- None.\n\n## Related Pages\n- None.\n\n"
            "## Sources\n- Original source.\n\n---\n*Ingested: 2026-01-01*\n",
            encoding="utf-8",
        )
        first = self.root / "wiki/concepts/first.md"
        first.write_text(
            "# First\n\n**Canonical title**: Shared\n**Aliases**: (none)\n\n"
            "## Summary\nA factual claim.\n\n## Definition\nDefinition.\n\n"
            "## Explanation\nExplanation.\n\n## Key Aspects\n- Aspect.\n\n"
            "## Applications\nApplication.\n\n## Related Pages\n- [Bad](..\\bad.md)\n\n"
            "## Sources\n- None.\n\n---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        second = self.root / "wiki/entities/second.md"
        second.write_text(
            "# Second\n\n**Canonical title**: Other\n**Aliases**: Shared\n\n"
            "## Summary\n(add concise overview)\n\n## Key Information\n- (add facts)\n\n"
            "## Mentions in Sources\n- (add sources)\n\n## Related Pages\n- (add)\n\n"
            "## Sources\n- (add)\n\n---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertIn("Untraceable claims", output)
        self.assertIn("Duplicate canonical title or alias", output)
        self.assertIn("Malformed link", output)

    def test_lint_accepts_complete_cited_concept(self):
        source = self.root / "wiki/sources/source.md"
        source.write_text(
            bob.frontmatter(
                "source", source_ids=["manual:source"], ingest_status="complete",
                extraction_status="not-applicable", source_type="paper", author="A", year=2026,
            ) + "# Source\n\n**Type**: Paper\n**Author**: A\n"
            "**Original location**: https://example.test/source\n**Source ID**: manual:source\n"
            "**Extraction status**: not-applicable\n\n## Summary\nSummary.\n\n"
            "## Key Takeaways\n- One.\n\n## Entities Mentioned\n- None.\n\n"
            "## Concepts Discussed\n- None.\n\n## Related Pages\n- None.\n\n"
            "## Sources\n- Original source.\n\n---\n*Ingested: 2026-01-01*\n",
            encoding="utf-8",
        )
        concept = self.root / "wiki/concepts/cited.md"
        concept.write_text(
            bob.frontmatter("concept", sources=["wiki/sources/source.md"], source_ids=["manual:source"]) +
            "# Cited\n\n**Canonical title**: Cited\n**Aliases**: (none)\n\n"
            "## Summary\nA factual claim.\n\n## Definition\nDefinition.\n\n"
            "## Explanation\nExplanation.\n\n## Key Aspects\n- Aspect.\n\n"
            "## Applications\nApplication.\n\n## Related Pages\n- None.\n\n"
            "## Sources\n- Citation: [Source](../sources/source.md), section 1.\n\n"
            "---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertNotIn("Untraceable claims", output)
        self.assertNotIn("Citation on line", output)

    def test_lint_phase7_graph_index_drift_size_and_chunk_controls(self):
        first = self.root / "wiki/concepts/first.md"
        second = self.root / "wiki/concepts/second.md"
        source = self.root / "wiki/sources/source.md"
        first.write_text(
            bob.frontmatter("concept") +
            "# First\n\n**Canonical title**: First\n**Aliases**: Shared\n\n"
            "## Summary\nClaim.\n\n## Definition\nDefinition.\n\n## Explanation\nExplain.\n\n"
            "## Key Aspects\n- One.\n\n## Applications\nUse.\n\n"
            "## Related Pages\n- [Second](second.md)\n\n"
            "## Sources\n- Citation: [Source](../sources/source.md).\n\n"
            "---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        second.write_text(
            bob.frontmatter("concept", aliases=["Shared"]) +
            "# Second\n\n**Canonical title**: Second\n**Aliases**: Shared\n\n"
            "## Summary\nClaim.\n\n## Definition\nDefinition.\n\n## Explanation\nExplain.\n\n"
            "## Key Aspects\n- One.\n\n## Applications\nUse.\n\n"
            "## Related Pages\n- None.\n\n## Sources\n- None.\n\n"
            "---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        source.write_text(
            bob.frontmatter(
                "source", source_ids=["src_test"], ingest_status="partial",
                extraction_status="partial", source_type="txt", author="A", year=2026,
            ) +
            "# Source\n\n**Type**: Text\n**Author**: A\n**Original location**: raw/source.txt\n"
            "**Source ID**: src_test\n**Extraction status**: partial\n**Ingest status**: partial\n\n"
            "## Summary\nSummary.\n\n## Key Takeaways\n- One.\n\n## Entities Mentioned\n- None.\n\n"
            "## Concepts Discussed\n- None.\n\n## Related Pages\n- None.\n\n## Sources\n- Original.\n\n"
            "---\n*Ingested: 2026-01-01*\n",
            encoding="utf-8",
        )
        raw = self.root / "raw/source.txt"
        raw.write_text("changed", encoding="utf-8")
        registry = {
            "schema_version": 1,
            "sources": [{
                "source_id": "src_test", "raw_path": "raw/source.txt", "sha256": "0" * 64,
                "format": "txt", "source_page": "wiki/sources/source.md",
                "extraction_status": "partial", "ingest_status": "partial",
                "last_processed": "2026-01-01T00:00:00+00:00", "availability": "present",
                "duplicate_of": None, "versions": [],
            }],
        }
        (self.root / "index/source-registry.json").write_text(json.dumps(registry), encoding="utf-8")
        extraction = self.root / bob.extraction_relative_path(registry["sources"][0])
        extraction.parent.mkdir(parents=True)
        extraction.write_text(json.dumps({
            "schema_version": 1, "source_id": "src_test", "raw_path": "raw/source.txt",
            "sha256": "0" * 64, "format": "txt", "status": "partial",
            "chunks": [{
                "chunk_id": "src_test:b001:c01", "status": "pending",
                "text": "x" * (bob.MAX_CHUNK_CHARS + 1),
            }],
        }), encoding="utf-8")
        self.write_index(
            1,
            "# Index\n\n## Concepts\n"
            "- [Second](../wiki/concepts/second.md) - out of order\n"
            "- [First](../wiki/concepts/first.md) - out of order\n",
        )
        before = {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

        result, output = self.capture(bob.lint_action)
        after = {
            str(path.relative_to(self.root)): path.read_bytes()
            for path in self.root.rglob("*") if path.is_file()
        }

        self.assertEqual(0, result)
        self.assertEqual(before, after)
        for category in bob.LINT_CATEGORIES:
            self.assertRegex(output, rf"- {re.escape(category)}: \d+")
        self.assertIn("One-way relationships", output)
        self.assertIn("Duplicate titles and aliases", output)
        self.assertIn("Citation on line", output)
        self.assertIn("Changed raw sources", output)
        self.assertIn("Unprocessed source chunks", output)
        self.assertIn("Managed page is missing from numbered indices", output)
        self.assertIn("Entries are not in deterministic category/title order", output)
        self.assertIn("exceeds 4000 characters", output)

    def test_lint_reports_invalid_obsidian_frontmatter(self):
        concept = self.root / "wiki/concepts/bad-properties.md"
        concept.write_text(
            "---\nkind: entity\nstatus: unknown\naliases: not-a-list\n---\n"
            "# Bad Properties\n\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertIn("Missing frontmatter property", output)
        self.assertIn("Frontmatter kind must be: concept", output)
        self.assertIn("Invalid frontmatter status", output)
        self.assertIn("Frontmatter property must be a list: aliases", output)

    def test_lint_reports_pipes_inside_table_cell_math(self):
        page = self.root / "wiki/concepts/tables.md"
        page.write_text(
            "# Tables\n\n"
            "Prose math $|0\\rangle$ outside a table is fine.\n\n"
            "| State | Form |\n"
            "|---|---|\n"
            "| zero | $|0\\rangle$ |\n"
            "| one | $\\|1\\rangle$ |\n"
            "| two | $\\lvert 2\\rangle$ |\n\n"
            "---\n*Last updated: 2026-01-01*\n",
            encoding="utf-8",
        )
        result, output = self.capture(bob.lint_action)
        self.assertEqual(0, result)
        self.assertIn("Table math pipes", output)
        self.assertIn("Pipe inside table-cell math on line 7", output)
        self.assertIn("Pipe inside table-cell math on line 8", output)
        self.assertNotIn("Pipe inside table-cell math on line 3", output)
        self.assertNotIn("Pipe inside table-cell math on line 9", output)

    def test_phase5_native_bases_map_and_root_vault_exist(self):
        repository = RUNNER_PATH.parents[1]
        self.assertTrue((repository / ".obsidian").is_dir())
        self.assertFalse((repository / "wiki/.obsidian").exists())
        bases = {
            "ingestion-queue.base", "source-library.base", "concept-glossary.base",
            "entity-directory.base", "review-queue.base",
        }
        for name in bases:
            text = (repository / "wiki/bases" / name).read_text(encoding="utf-8")
            self.assertIn("filters:", text)
            self.assertIn("views:", text)
            self.assertIn('file.inFolder("wiki', text)
        map_text = (repository / "wiki/maps/quantum-computing.md").read_text(encoding="utf-8")
        self.assertEqual("map", bob.frontmatter_metadata(map_text)["kind"])
        for name in bases:
            self.assertIn(name, map_text)

    def test_index_update_success_and_invalid_utf8_failure(self):
        pages = {
            "entities/alpha.md": "Alpha",
            "concepts/beta.md": "Beta",
            "sources/gamma.md": "Gamma",
            "analyses/delta.md": "Delta",
        }
        for relative, title in pages.items():
            page = self.root / "wiki" / relative
            page.write_text(
                f"# {title}\n\n## Summary\n{title} summary.\n\n*Last updated: 2026-01-01*\n",
                encoding="utf-8",
            )
        self.assertEqual(0, bob.index_update_action())
        index_text = (self.root / "index/index_001.md").read_text(encoding="utf-8")
        for relative, title in pages.items():
            self.assertIn(f"[{title}](../wiki/{relative})", index_text)
        (self.root / "wiki/concepts/beta.md").write_bytes(b"\xff")
        result, output = self.run_main(["index-update"])
        self.assertEqual(1, result)
        self.assertIn("Error:", output)

    def test_index_update_splits_deterministically_writes_manifest_and_removes_obsolete_parts(self):
        for number in range(18):
            page = self.root / "wiki/concepts" / f"topic-{number:02d}.md"
            page.write_text(
                bob.frontmatter(
                    "concept", aliases=[f"Alias {number:02d}"], topics=["scaling"],
                    source_ids=[f"manual:{number:02d}"], updated="2026-09-16",
                ) + f"# Topic {number:02d}\n\n## Summary\n"
                + (f"Deterministic searchable description {number:02d}. " * 5)
                + "\n\n*Last updated: 2026-09-16*\n",
                encoding="utf-8",
            )
        obsolete = self.write_index(99)
        with mock.patch.object(bob, "INDEX_TARGET_TOKENS", 420):
            self.assertEqual(0, bob.index_update_action())
            parts = bob.index_files()
            self.assertGreater(len(parts), 1)
            first_build = {Path(path).name: Path(path).read_text(encoding="utf-8") for path in parts}
            self.assertFalse(obsolete.exists())
            manifest = (self.root / "index/index.md").read_text(encoding="utf-8")
            for path in parts:
                self.assertIn(Path(path).name, manifest)
                content = Path(path).read_text(encoding="utf-8")
                self.assertIn("Manifest: [index.md](index.md)", content)
                self.assertLessEqual(bob.estimate_tokens(content), bob.INDEX_HARD_LIMIT)
            indexed = "\n".join(first_build.values())
            for number in range(18):
                self.assertEqual(1, indexed.count(f"../wiki/concepts/topic-{number:02d}.md"))
            indexed_titles = []
            for content in first_build.values():
                indexed_titles.extend(re.findall(r"^- \[(Topic \d+)\]", content, re.MULTILINE))
                self.assertLessEqual(bob.estimate_tokens(content), bob.INDEX_TARGET_TOKENS)
            self.assertEqual(sorted(indexed_titles, key=str.casefold), indexed_titles)
            self.assertIn("aliases: Alias 00", indexed)
            self.assertIn("topics: scaling", indexed)
            _records, _groups, generated, no_obsolete = bob.build_index_changes()
            second_build = {
                Path(path).name: content
                for path, content in generated
                if Path(path).name.startswith("index_")
            }
            self.assertEqual([], no_obsolete)
            self.assertEqual(first_build, second_build)

    def test_move_rewrites_links_for_spaces_and_windows_input(self):
        source = self.root / "wiki/concepts/old page.md"
        source.write_text("# Old\n", encoding="utf-8")
        inbound = self.root / "wiki/entities/linker.md"
        inbound.write_text("[Old](../concepts/old page.md)\n", encoding="utf-8")
        index = self.write_index(1, "[Old](../wiki/concepts/old page.md)\n")
        result = bob.move_action(
            "wiki\\concepts\\old page.md",
            "wiki\\concepts\\new folder\\new page.md",
        )
        self.assertEqual(0, result)
        self.assertFalse(source.exists())
        self.assertTrue((self.root / "wiki/concepts/new folder/new page.md").is_file())
        self.assertIn("../concepts/new folder/new page.md", inbound.read_text(encoding="utf-8"))
        self.assertIn("../wiki/concepts/new folder/new page.md", index.read_text(encoding="utf-8"))

    def test_move_existing_destination_failure_does_not_change_source(self):
        source = self.root / "wiki/concepts/source.md"
        destination = self.root / "wiki/concepts/destination.md"
        source.write_text("source", encoding="utf-8")
        destination.write_text("destination", encoding="utf-8")
        self.assertEqual(1, bob.move_action("wiki/concepts/source.md", "wiki/concepts/destination.md"))
        self.assertEqual("source", source.read_text(encoding="utf-8"))
        self.assertEqual("destination", destination.read_text(encoding="utf-8"))

    def test_move_supports_all_page_directories(self):
        for directory in ("entities", "concepts", "sources", "analyses"):
            with self.subTest(directory=directory):
                source = self.root / "wiki" / directory / "before.md"
                destination = self.root / "wiki" / directory / "after.md"
                source.write_text(f"# {directory}\n", encoding="utf-8")
                self.assertEqual(
                    0,
                    bob.move_action(
                        f"wiki\\{directory}\\before.md",
                        f"wiki\\{directory}\\after.md",
                    ),
                )
                self.assertTrue(destination.is_file())

    def test_status_success_and_invalid_index_failure(self):
        self.write_index(1)
        for directory in ("entities", "concepts", "sources", "analyses"):
            (self.root / "wiki" / directory / "page.md").write_text("# Page\n", encoding="utf-8")
        result, output = self.capture(bob.status_action)
        self.assertEqual(0, result)
        self.assertIn("Wiki Pages", output)
        self.assertEqual(4, output.count("1\n"))
        (self.root / "index/index_001.md").write_bytes(b"\xff")
        result, output = self.run_main(["status"])
        self.assertEqual(1, result)
        self.assertIn("Error:", output)

    def test_raw_list_success_and_missing_directory_failure(self):
        (self.root / "raw/note.txt").write_text("note", encoding="utf-8")
        result, output = self.capture(bob.raw_list_action)
        self.assertEqual(0, result)
        self.assertIn("note.txt", output)
        shutil.rmtree(self.root / "raw")
        self.assertEqual(1, bob.raw_list_action())

    def test_research_success_and_missing_procedure_failure(self):
        self.assertEqual(0, bob.research_action())
        (self.root / ".bob/commands/research.md").unlink()
        self.assertEqual(1, bob.research_action())

    def test_cli_argument_and_unknown_command_failures(self):
        result, output = self.run_main(["create-page", "--type", "concept"])
        self.assertEqual(1, result)
        self.assertIn("requires --type and --title", output)
        result, output = self.run_main(["unknown"])
        self.assertEqual(2, result)
        self.assertIn("Unknown command", output)

    def test_runner_source_is_ascii_only(self):
        self.assertTrue(RUNNER_PATH.read_bytes().isascii())

    def run_main(self, arguments):
        output = io.StringIO()
        old_argv = sys.argv
        try:
            sys.argv = [str(RUNNER_PATH)] + arguments
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
                result = bob.main()
        finally:
            sys.argv = old_argv
        return result, output.getvalue()


if __name__ == "__main__":
    unittest.main()
