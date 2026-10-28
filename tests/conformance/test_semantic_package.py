"""Package-context semantic checks: every fixture, the examples, isolation, no mutation."""

import builtins
import copy
import io
import os
import socket
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.semantic import PackageContext, check, check_package, diagnostic, json_equal, resolve
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Routing

REPO = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent / "fixtures" / "records"
EXAMPLES = REPO / "definitions" / "examples"

# name: complete sorted [(code, path), ...]
CASES = {
    "package-count-mismatch": [("COUNT_MISMATCH", "/manifest/counts/assets")],
    "package-count-absent-array-ok": [],
    "package-reference-unresolved-complete": [("REFERENCE_UNRESOLVED", "/assets/0/files/0/storage_location")],
    "package-reference-unresolved-partial": [
        ("REFERENCE_UNRESOLVED_PARTIAL", "/assets/0/files/0/storage_location"),
    ],
    "package-id-duplicate-assets": [("ID_DUPLICATE", "/assets/1/id")],
    "package-id-shared-across-kinds-ok": [],
    "package-snapshot-mismatch-field": [("SNAPSHOT_MISMATCH", "/assets/0/collections/0")],
    "package-snapshot-extra-field": [("SNAPSHOT_MISMATCH", "/assets/0/collections/0")],
    "package-collection-cycle": [
        ("COLLECTION_CYCLE", "/collections/0/parent"),
        ("COLLECTION_CYCLE", "/collections/1/parent"),
    ],
    "package-collection-self-parent": [("COLLECTION_CYCLE", "/collections/0/parent")],
    "package-membership-disagrees": [("MEMBERSHIP_DISAGREES", "/assets/0/collections/0")],
    "package-membership-partial-ok": [],
    "package-namespace-undeclared": [("NAMESPACE_UNDECLARED", "/assets/0/extensions")],
    "package-namespace-payload-nested-ok": [],
    "package-namespace-declared-twice": [("NAMESPACE_DECLARED_TWICE", "/manifest/namespaces/1/token")],
    "package-namespace-unused-ok": [],
    "package-snapshot-namespace-undeclared-partial": [
        ("REFERENCE_UNRESOLVED_PARTIAL", "/assets/0/collections/0"),
        ("NAMESPACE_UNDECLARED", "/assets/0/collections/0/extensions"),
    ],
    "package-relationship-target-no-timing": [("TIMELINE_UNDECLARED", "/assets/1/relationships/0/range")],
    "package-relationship-range-out-of-bounds": [
        ("FRAME_OUT_OF_BOUNDS", "/assets/1/relationships/0/range/end_frame"),
    ],
    "package-value-shape-mismatch": [("VALUE_SHAPE_MISMATCH", "/assets/0/metadata/0/value")],
    "package-value-date-invalid": [("VALUE_DATE_INVALID", "/assets/0/metadata/2/value")],
    "package-value-option-unknown": [("VALUE_OPTION_UNKNOWN", "/assets/0/metadata/0/value")],
    "package-value-option-repeated": [("VALUE_OPTION_REPEATED", "/assets/0/metadata/0/value/1")],
    "package-value-reference-partial": [("REFERENCE_UNRESOLVED_PARTIAL", "/assets/0/metadata/3/value")],
    "package-value-empty-multiple-ok": [],
    "standalone-namespace-undeclared-ok": [],
    "package-snapshot-missing-field": [("SNAPSHOT_MISMATCH", "/assets/0/collections/0")],
    "package-value-definition-unresolved-complete": [
        ("REFERENCE_UNRESOLVED", "/assets/0/metadata/0/definition"),
    ],
    "package-collection-cycle-tail": [
        ("COLLECTION_CYCLE", "/collections/0/parent"),
        ("COLLECTION_CYCLE", "/collections/1/parent"),
    ],
}

# Structurally invalid: a snapshot that carries members (ID-6, COL-5).
STRUCTURAL_INVALID = ("package-snapshot-with-members",)

PACKAGE_EXAMPLES = {
    "package-complete": [],
    "package-full": [],
    "package-minimal": [],
}


def _parsed(path):
    return parse_input(path.read_bytes())


def _pairs(diagnostics):
    return [(d.code, d.path) for d in diagnostics]


class PackageFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(REPO / "definitions")

    def _check(self, path):
        parsed = _parsed(path)
        routing = route(parsed.value)
        self.assertEqual(routing.status, "selected")
        errors = self.bundle.entry_point(routing.kind).validate(parsed)
        self.assertEqual([(list(e.absolute_path), e.validator) for e in errors], [])
        diagnostics = check(parsed.value, routing)
        self.assertEqual(diagnostics, sorted(diagnostics, key=lambda d: (d.path, d.code)))
        for d in diagnostics:
            self.assertEqual(d, diagnostic(d.code, d.path))
        return _pairs(diagnostics)

    def test_every_case_has_a_fixture(self):
        for name in list(CASES) + list(STRUCTURAL_INVALID):
            with self.subTest(name):
                self.assertTrue((RECORDS / (name + ".json")).is_file())

    def test_fixtures(self):
        for name, expected in CASES.items():
            with self.subTest(name):
                self.assertEqual(self._check(RECORDS / (name + ".json")), expected)

    def test_snapshot_with_members_is_structurally_invalid(self):
        for name in STRUCTURAL_INVALID:
            with self.subTest(name):
                parsed = _parsed(RECORDS / (name + ".json"))
                routing = route(parsed.value)
                self.assertEqual(routing.status, "selected")
                self.assertGreaterEqual(len(self.bundle.entry_point(routing.kind).validate(parsed)), 1)

    def test_examples_complete_with_declared_warnings(self):
        for name, expected in PACKAGE_EXAMPLES.items():
            with self.subTest(name):
                self.assertEqual(self._check(EXAMPLES / (name + ".json")), expected)

    def test_no_network_or_file_access(self):
        trees = []
        for name in CASES:
            value = _parsed(RECORDS / (name + ".json")).value
            trees.append((name, value, route(value)))
        for name in PACKAGE_EXAMPLES:
            value = _parsed(EXAMPLES / (name + ".json")).value
            trees.append((name, value, route(value)))

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
        package = copy.deepcopy(_parsed(EXAMPLES / "package-minimal.json").value)
        package["manifest"]["counts"].update({"metadata_definitions": 1, "assets": 1})
        package["metadata_definitions"] = [
            {
                "type": "metadata_definition",
                "spec_version": "2.0.0-draft.2",
                "id": "md-code",
                "value_type": "string",
                "cardinality": "single",
                "constraints": {"pattern": "^x$", "min_length": 10},
            }
        ]
        package["assets"] = [
            {
                "type": "asset",
                "spec_version": "2.0.0-draft.2",
                "id": "a-0001",
                "title": "Example Clip",
                "access": {"status": "none"},
                "metadata": [{"definition": "md-code", "value": "a"}],
            }
        ]
        self.assertEqual(check_package(package), [])

    def test_tree_unchanged(self):
        paths = [RECORDS / (n + ".json") for n in CASES] + [EXAMPLES / (n + ".json") for n in PACKAGE_EXAMPLES]
        for path in paths:
            with self.subTest(path.name):
                value = _parsed(path).value
                before = copy.deepcopy(value)
                check(value, route(value))
                self.assertEqual(value, before)
                self.assertEqual(repr(value), repr(before))

    def test_unsupported_routing_runs_nothing(self):
        routing = Routing("unsupported", "package", None, ())
        self.assertEqual(check({"type": "package"}, routing), [])


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


class ResolveTests(unittest.TestCase):
    def context(self, completeness):
        return PackageContext(
            spec_version="2.0.0-draft.2",
            completeness={"storage_locations": completeness, "metadata_definitions": completeness,
                          "collections": completeness, "assets": completeness},
            storage_locations={"sl-01": {"id": "sl-01"}},
            metadata_definitions={},
            collections={},
            assets={},
            namespaces=frozenset(),
        )

    def test_found(self):
        self.assertEqual(resolve(self.context("complete"), "storage_locations", "sl-01", "/p"), ({"id": "sl-01"}, None))

    def test_unresolved_complete(self):
        self.assertEqual(
            resolve(self.context("complete"), "storage_locations", "sl-02", "/p"),
            (None, diagnostic("REFERENCE_UNRESOLVED", "/p")),
        )

    def test_unresolved_partial(self):
        self.assertEqual(
            resolve(self.context("partial"), "storage_locations", "sl-02", "/p"),
            (None, diagnostic("REFERENCE_UNRESOLVED_PARTIAL", "/p")),
        )


if __name__ == "__main__":
    unittest.main()
