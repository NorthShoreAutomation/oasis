"""Package-level semantic checks: isolation, no mutation, helpers, and cross-record rules.

Every fixture runs through the full pipeline in ``test_corpus.py``. The
tests here check that the semantic stage touches no file or socket, never
changes the tree, never executes constraints, and test the package helpers
on small packages built in memory.
"""

import builtins
import copy
import io
import json
import os
import socket
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tests.conformance.document import route
from tests.conformance.package_check import Context
from tests.conformance.semantic import check, check_package, diagnostic, json_equal, resolve
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Routing

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
EXAMPLES = REPO / "definitions" / "examples"
EXAMPLE_NAMES = ("package-complete", "package-full", "package-minimal")


def _parsed(path):
    return parse_input(path.read_bytes())


def _valid_fixture_paths():
    manifest = json.loads((FIXTURES / "manifest.json").read_text(encoding="utf-8"))
    # A package case is a folder of member files, not one document.
    return [
        FIXTURES / c["path"]
        for c in manifest["cases"]
        if c["expected_structural"] == "valid" and c["path"].startswith("records/")
    ]


def _pairs(diagnostics):
    return [(d.code, d.path) for d in diagnostics]


def _package(**lists):
    """A minimal package; the counts match the given record lists."""
    package = {
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
    for key in ("storage_locations", "metadata_definitions", "collections", "assets"):
        package[key] = lists.get(key, [])
        package["manifest"]["counts"][key] = len(package[key])
    return package


def _asset(asset_id, **fields):
    return dict({"id": asset_id, "title": "Example Clip"}, **fields)


def _collection(collection_id, *parents):
    collection = {"id": collection_id, "title": "Example Collection"}
    if parents:
        collection["member_of"] = [{"collection": parent} for parent in parents]
    return collection


class PackageStageTests(unittest.TestCase):
    def test_examples_give_no_diagnostic(self):
        for name in EXAMPLE_NAMES:
            with self.subTest(name):
                value = _parsed(EXAMPLES / (name + ".json")).value
                self.assertEqual(check(value, route(value)), [])

    def test_output_is_sorted_catalog_diagnostics(self):
        for path in _valid_fixture_paths():
            with self.subTest(path.name):
                value = _parsed(path).value
                diagnostics = check(value, route(value))
                self.assertEqual(diagnostics, sorted(diagnostics, key=lambda d: (d.path, d.code)))
                for d in diagnostics:
                    self.assertEqual(d, diagnostic(d.code, d.path))

    def test_no_network_or_file_access(self):
        trees = []
        for path in _valid_fixture_paths() + [EXAMPLES / (n + ".json") for n in EXAMPLE_NAMES]:
            value = _parsed(path).value
            trees.append((path.name, value, route(value)))

        def refuse(*_args, **_kwargs):
            raise AssertionError("the semantic stage opened a file or a socket")

        with (
            mock.patch.object(socket, "socket", refuse),
            mock.patch.object(builtins, "open", refuse),
            mock.patch.object(io, "open", refuse),
            mock.patch.object(os, "open", refuse),
        ):
            for name, value, routing in trees:
                with self.subTest(name):
                    check(value, routing)

    def test_constraints_never_executed(self):
        package = _package(
            metadata_definitions=[
                {
                    "id": "md-code",
                    "label": "Code",
                    "value_type": "string",
                    "cardinality": "single",
                    "constraints": {"pattern": "^x$", "min_length": 10},
                }
            ],
            assets=[_asset("a-0001", metadata=[{"definition": "md-code", "value": "a"}])],
        )
        self.assertEqual(check_package(package), [])

    def test_tree_unchanged(self):
        paths = _valid_fixture_paths() + [EXAMPLES / (n + ".json") for n in EXAMPLE_NAMES]
        for path in paths:
            with self.subTest(path.name):
                value = _parsed(path).value
                before = copy.deepcopy(value)
                check(value, route(value))
                self.assertEqual(value, before)
                self.assertEqual(repr(value), repr(before))

    def test_unsupported_routing_runs_nothing(self):
        routing = Routing("unsupported", None, None, ())
        self.assertEqual(check({"type": "package"}, routing), [])


class CrossRecordTests(unittest.TestCase):
    def test_cycle_reports_only_entries_on_the_cycle(self):
        # c-3 hangs off the c-1, c-2 cycle; its entry is not on the cycle.
        package = _package(collections=[_collection("c-1", "c-2"), _collection("c-2", "c-1"), _collection("c-3", "c-1")])
        self.assertEqual(
            _pairs(check_package(package)),
            [("COLLECTION_CYCLE", "/collections/0/member_of/0"), ("COLLECTION_CYCLE", "/collections/1/member_of/0")],
        )

    def test_two_parents_without_a_cycle(self):
        package = _package(collections=[_collection("c-1"), _collection("c-2"), _collection("c-3", "c-1", "c-2")])
        self.assertEqual(check_package(package), [])

    def test_positions_share_one_scope_across_assets_and_collections(self):
        package = _package(
            collections=[_collection("c-1"), dict(_collection("c-2"), member_of=[{"collection": "c-1", "position": 2}])],
            assets=[_asset("a-0001", member_of=[{"collection": "c-1", "position": Decimal("2.0")}])],
        )
        self.assertEqual(
            _pairs(check_package(package)),
            [("POSITION_DUPLICATE", "/assets/0/member_of/0"), ("POSITION_DUPLICATE", "/collections/1/member_of/0")],
        )

    def test_one_collection_twice_needs_a_position_on_each_entry(self):
        package = _package(
            collections=[_collection("c-1")],
            assets=[
                _asset("a-0001", member_of=[{"collection": "c-1", "position": 1}, {"collection": "c-1"}]),
                _asset("a-0002", member_of=[{"collection": "c-1", "position": 3}, {"collection": "c-1", "position": 4}]),
            ],
        )
        self.assertEqual(_pairs(check_package(package)), [("MEMBERSHIP_DUPLICATE", "/assets/0/member_of/1")])

    def test_relationship_duplicate_ignores_description_and_extensions(self):
        package = _package(
            assets=[
                _asset("a-0001"),
                _asset(
                    "a-0002",
                    relationships=[
                        {"type": "derived_from", "target": "a-0001", "description": "First."},
                        {"type": "derived_from", "target": "a-0001", "description": "Second."},
                        {"type": "derived_from", "target": "a-0001", "label": "Other"},
                    ],
                ),
            ]
        )
        self.assertEqual(_pairs(check_package(package)), [("RELATIONSHIP_DUPLICATE", "/assets/1/relationships/1")])

    def test_extension_payload_is_never_walked(self):
        package = _package(assets=[_asset("a-0001", extensions={"vendor_a": {"extensions": {"vendor_b": {}}}})])
        package["manifest"]["namespaces"] = [{"token": "vendor_a", "owner": "Example Archive"}]
        self.assertEqual(check_package(package), [])

    def test_undeclared_namespace_reported_once_per_slot(self):
        package = _package(assets=[_asset("a-0001", extensions={"vendor_a": {}, "vendor_b": {}})])
        self.assertEqual(_pairs(check_package(package)), [("NAMESPACE_UNDECLARED", "/assets/0/extensions")])

    def test_definition_used_at_two_levels(self):
        definition = {"id": "md-note", "label": "Note", "value_type": "string", "cardinality": "single"}
        version = {"id": "v-1", "ordinal": 1, "metadata": [{"definition": "md-note", "value": "x"}]}
        package = _package(
            metadata_definitions=[definition],
            assets=[_asset("a-0001", metadata=[{"definition": "md-note", "value": "x"}], versions=[version])],
        )
        self.assertEqual(
            _pairs(check_package(package)),
            [("DEFINITION_SHARED_AND_VERSIONED", "/assets/0/versions/0/metadata/0/definition")],
        )

    def test_count_of_an_absent_array_is_zero(self):
        package = _package()
        del package["assets"]
        package["manifest"]["counts"]["assets"] = 1
        self.assertEqual(_pairs(check_package(package)), [("COUNT_MISMATCH", "/manifest/counts/assets")])


class JsonEqualTests(unittest.TestCase):
    def test_boolean_is_its_own_type(self):
        self.assertFalse(json_equal({"x": True}, {"x": 1}))
        self.assertFalse(json_equal({"x": False}, {"x": 0}))
        self.assertTrue(json_equal({"x": True}, {"x": True}))

    def test_numbers_equal_when_mathematically_equal(self):
        self.assertTrue(json_equal(25, Decimal("25.0")))
        self.assertTrue(json_equal(Decimal("2.50"), Decimal("2.5")))
        self.assertFalse(json_equal(25, Decimal("25.1")))

    def test_inside_an_extensions_payload(self):
        self.assertFalse(
            json_equal({"extensions": {"vendor_a": {"x": True}}}, {"extensions": {"vendor_a": {"x": 1}}})
        )
        self.assertTrue(
            json_equal({"extensions": {"vendor_a": {"n": 25}}}, {"extensions": {"vendor_a": {"n": Decimal("25.0")}}})
        )

    def test_structure(self):
        self.assertFalse(json_equal({"a": 1}, {"a": 1, "b": 2}))
        self.assertFalse(json_equal([1, 2], [2, 1]))
        self.assertFalse(json_equal([1], [1, 1]))
        self.assertFalse(json_equal(None, "null"))
        self.assertFalse(json_equal(None, 0))
        self.assertTrue(json_equal(None, None))
        self.assertFalse(json_equal("1", 1))
        self.assertFalse(json_equal([], {}))
        self.assertTrue(json_equal({"a": [1, {"b": "c"}]}, {"a": [Decimal("1.0"), {"b": "c"}]}))

    def test_strings_compare_by_code_points(self):
        self.assertFalse(json_equal("\u00e9", "e\u0301"))
        self.assertTrue(json_equal("\u00e9", "\u00e9"))

    def test_empty_object_is_not_an_absent_member(self):
        self.assertFalse(json_equal({"a": {}}, {}))


class ResolveTests(unittest.TestCase):
    def context(self):
        return Context(
            storage_locations={"sl-01": {"id": "sl-01"}},
            metadata_definitions={},
            collections={},
            namespaces=frozenset(),
        )

    def test_found(self):
        self.assertEqual(resolve(self.context(), "storage_locations", "sl-01", "/p"), ({"id": "sl-01"}, None))

    def test_unresolved(self):
        self.assertEqual(
            resolve(self.context(), "storage_locations", "sl-02", "/p"),
            (None, diagnostic("REFERENCE_UNRESOLVED", "/p")),
        )

    def test_ids_compare_exactly(self):
        for target in ("SL-01", "sl-01 ", 1, None):
            with self.subTest(target=target):
                self.assertEqual(resolve(self.context(), "storage_locations", target, "/p")[0], None)


if __name__ == "__main__":
    unittest.main()
