"""The record-stream engine of the semantic stage.

The fixtures give the single-document findings. The tests here add records
one at a time, as a multi-file package does, and check the deferred checks,
add order, the record order rule, and the on-disk store.
"""

import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from tests.conformance.corpus import load_manifest
from tests.conformance.package_check import PackageChecker, Where
from tests.conformance.semantic import check_package, diagnostic
from tests.conformance.strict_json import parse_input

FIXTURES = Path(__file__).resolve().parent / "fixtures"

REFERENCE_DEFINITION = {
    "id": "md-related",
    "label": "Related",
    "value_type": "asset_reference",
    "cardinality": "single",
}


def _root(**manifest_fields):
    root = {
        "type": "package",
        "spec_version": "2.0.0-draft.4",
        "id": "pkg-0001",
        "manifest": {
            "producer": {"name": "example-exporter", "version": "0.1.0"},
            "produced_at": "2026-10-05T09:00:00Z",
            "counts": {},
            "namespaces": [],
        },
    }
    root["manifest"].update(manifest_fields)
    return root


def _asset(asset_id, **fields):
    return dict({"id": asset_id, "title": "Example Clip"}, **fields)


def _collection(collection_id, **fields):
    return dict({"id": collection_id, "title": "Example Collection"}, **fields)


def _at(base):
    return Where(None, None, base)


def _run(records, root=None, store_path=":memory:"):
    checker = PackageChecker(_root() if root is None else root, store_path)
    try:
        for registry, record, where in records:
            checker.add(registry, record, where)
        return checker.finish()
    finally:
        checker.close()


def _pairs(diagnostics):
    return [(d.code, d.path) for d in diagnostics]


class SingleDocumentTests(unittest.TestCase):
    def test_single_document_findings_are_unchanged(self):
        cases = [c for c in load_manifest() if c.expected_structural == "valid" and not c.is_package]
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case.id):
                value = parse_input((FIXTURES / case.path).read_bytes()).value
                found = check_package(value)
                self.assertEqual(tuple((d.code, d.path) for d in found), case.expected_diagnostics)
                self.assertTrue(all(d.member is None and d.line is None for d in found))


class DeferredCheckTests(unittest.TestCase):
    def test_asset_reference_to_a_later_asset_resolves(self):
        def records(value):
            return [
                ("metadata_definitions", REFERENCE_DEFINITION, _at("/metadata_definitions/0")),
                ("assets", _asset("a-1", metadata=[{"definition": "md-related", "value": value}]), _at("/assets/0")),
                ("assets", _asset("a-2"), _at("/assets/1")),
            ]

        self.assertEqual(_run(records("a-2")), [])
        self.assertEqual(
            _pairs(_run(records("a-3"))), [("REFERENCE_UNRESOLVED", "/assets/0/metadata/0/value")]
        )

    def test_relationship_target_checks_run_after_the_target_arrives(self):
        timing = {"time_base": {"rate": {"numerator": 25, "denominator": 1}}, "duration_frames": 750}

        def records(relationship):
            return [
                ("assets", _asset("a-1", relationships=[relationship]), _at("/assets/0")),
                ("assets", _asset("a-2", versions=[{"id": "v-1", "ordinal": 1, "timing": timing}]), _at("/assets/1")),
            ]

        unresolved_version = {"type": "subclip_of", "target": "a-2", "target_version": "v-9"}
        self.assertEqual(
            _pairs(_run(records(unresolved_version))),
            [("VERSION_REFERENCE_UNRESOLVED", "/assets/0/relationships/0/target_version")],
        )
        out_of_bounds = {
            "type": "subclip_of",
            "target": "a-2",
            "target_version": "v-1",
            "range": {"start_frame": 0, "end_frame": 800},
        }
        self.assertEqual(
            _pairs(_run(records(out_of_bounds))),
            [("POSITION_OUT_OF_BOUNDS", "/assets/0/relationships/0/range/end_frame")],
        )

    def test_first_occurrence_is_the_earliest_add(self):
        found = _run([("assets", _asset("a-1"), Where(3, 7, "")), ("assets", _asset("a-1"), Where(1, 2, ""))])
        self.assertEqual(found, [replace(diagnostic("ID_DUPLICATE", "/id"), member=1, line=2)])

        # A reference resolves to the first add of its id, not to the lowest member.
        relationship = {"type": "derived_from", "target": "a-1", "target_version": "v-2"}
        found = _run([
            ("assets", _asset("a-1", versions=[{"id": "v-1", "ordinal": 1}]), Where(3, 7, "")),
            ("assets", _asset("a-1", versions=[{"id": "v-2", "ordinal": 1}]), Where(1, 2, "")),
            ("assets", _asset("a-0", relationships=[relationship]), Where(0, 1, "")),
        ])
        self.assertEqual(
            [(d.code, d.member, d.line, d.path) for d in found],
            [
                ("VERSION_REFERENCE_UNRESOLVED", 0, 1, "/relationships/0/target_version"),
                ("ID_DUPLICATE", 1, 2, "/id"),
            ],
        )

    def test_collection_member_of_a_later_collection_resolves(self):
        def records(parent):
            return [
                ("collections", _collection("c-1", member_of=[{"collection": parent}]), _at("/collections/0")),
                ("collections", _collection("c-2"), _at("/collections/1")),
            ]

        self.assertEqual(_run(records("c-2")), [])
        self.assertEqual(
            _pairs(_run(records("c-3"))), [("REFERENCE_UNRESOLVED", "/collections/0/member_of/0/collection")]
        )

    def test_records_out_of_order_raise(self):
        checker = PackageChecker(_root())
        try:
            checker.add("assets", _asset("a-1"), _at("/assets/0"))
            with self.assertRaises(ValueError):
                checker.add("collections", _collection("c-1"), _at("/collections/0"))
        finally:
            checker.close()

    def test_counts_are_checked_only_without_a_member_list(self):
        self.assertEqual(
            _pairs(_run([], root=_root(counts={"assets": 1}))), [("COUNT_MISMATCH", "/manifest/counts/assets")]
        )
        self.assertEqual(_run([], root=_root(counts={"assets": 1}, members=[])), [])

    def test_findings_sort_by_member_then_line(self):
        root = _root(namespaces=[{"token": "vendor_a", "owner": "A"}, {"token": "vendor_a", "owner": "B"}])
        undeclared = {"vendor_b": {}}
        found = _run(
            [
                ("assets", _asset("a-1", extensions=undeclared), Where(2, 1, "")),
                ("assets", _asset("a-2", extensions=undeclared), Where(1, 5, "")),
                ("assets", _asset("a-3", extensions=undeclared), Where(1, 3, "")),
            ],
            root=root,
        )
        self.assertEqual(
            [(d.code, d.member, d.line, d.path) for d in found],
            [
                ("NAMESPACE_DECLARED_TWICE", None, None, "/manifest/namespaces/1/token"),
                ("NAMESPACE_UNDECLARED", 1, 3, "/extensions"),
                ("NAMESPACE_UNDECLARED", 1, 5, "/extensions"),
                ("NAMESPACE_UNDECLARED", 2, 1, "/extensions"),
            ],
        )


class StoreTests(unittest.TestCase):
    def test_on_disk_store_gives_the_same_findings(self):
        timing = {"time_base": {"rate": {"numerator": 25, "denominator": 1}}, "duration_frames": 750}
        records = [
            ("metadata_definitions", REFERENCE_DEFINITION, Where(0, 1, "")),
            ("collections", _collection("c-1"), Where(1, 1, "")),
            (
                "assets",
                _asset(
                    "a-1",
                    metadata=[{"definition": "md-related", "value": "a-9"}],
                    relationships=[{"type": "subclip_of", "target": "a-2", "range": {"start_frame": 0, "end_frame": 900}}],
                    member_of=[{"collection": "c-1", "position": 1}],
                ),
                Where(2, 1, ""),
            ),
            ("assets", _asset("a-2", timing=timing, member_of=[{"collection": "c-1", "position": 1}]), Where(2, 2, "")),
            ("assets", _asset("a-2"), Where(3, 1, "")),
        ]
        in_memory = _run(records)
        self.assertEqual(
            [(d.code, d.member, d.line, d.path) for d in in_memory],
            [
                ("POSITION_DUPLICATE", 2, 1, "/member_of/0"),
                ("REFERENCE_UNRESOLVED", 2, 1, "/metadata/0/value"),
                ("POSITION_OUT_OF_BOUNDS", 2, 1, "/relationships/0/range/end_frame"),
                ("POSITION_DUPLICATE", 2, 2, "/member_of/0"),
                ("ID_DUPLICATE", 3, 1, "/id"),
            ],
        )
        with tempfile.TemporaryDirectory() as directory:
            store = Path(directory) / "semantic.sqlite"
            on_disk = _run(records, store_path=str(store))
            self.assertTrue(store.is_file())
        self.assertEqual(on_disk, in_memory)


if __name__ == "__main__":
    unittest.main()
