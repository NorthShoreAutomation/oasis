"""Tests for the root checks of an exchange document (REC-2, UNS-1)."""

import subprocess
import sys
import unittest
from pathlib import Path

from tests.conformance.document import KINDS, SUPPORTED_VERSIONS, route
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic, Routing

REPO = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent / "fixtures" / "records"

DRAFT3 = "2.0.0-draft.3"
NOT_DOCUMENT = ("NOT_EXCHANGE_DOCUMENT", "")
NOT_DOCUMENT_AT_TYPE = ("NOT_EXCHANGE_DOCUMENT", "/type")
VERSION_BAD = ("VERSION_UNSUPPORTED", "/spec_version")

# name: (status, record type, spec_version, [(code, path), ...])
CASES = {
    "routing-foreign-object": ("unsupported", None, None, [NOT_DOCUMENT]),
    "routing-root-array": ("unsupported", None, None, [NOT_DOCUMENT]),
    "routing-spec-version-absent": ("unsupported", None, None, [NOT_DOCUMENT]),
    "routing-spec-version-major-0": ("unsupported", None, None, [VERSION_BAD]),
    "routing-spec-version-3x": ("unsupported", None, None, [VERSION_BAD]),
    "routing-spec-version-number": ("unsupported", None, None, [VERSION_BAD]),
    "routing-spec-version-unknown-draft": ("unsupported", None, None, [VERSION_BAD]),
    "routing-previous-draft": ("unsupported", None, None, [VERSION_BAD]),
    "routing-version-before-numbers": ("unsupported", None, None, [VERSION_BAD]),
    "routing-no-type": ("unsupported", None, DRAFT3, [NOT_DOCUMENT]),
    "routing-type-unknown": ("unsupported", None, DRAFT3, [NOT_DOCUMENT_AT_TYPE]),
    "routing-type-number": ("unsupported", None, DRAFT3, [NOT_DOCUMENT_AT_TYPE]),
    "routing-standalone-asset": ("unsupported", None, DRAFT3, [NOT_DOCUMENT_AT_TYPE]),
    "routing-ok-minimal-package": ("selected", "package", DRAFT3, []),
}


def _route(name):
    return route(parse_input((RECORDS / (name + ".json")).read_bytes()).value)


class RoutingFixtureTests(unittest.TestCase):
    def test_every_fixture_has_a_case(self):
        names = {p.stem for p in RECORDS.glob("routing-*.json")}
        self.assertEqual(names, set(CASES))

    def test_fixtures(self):
        for name, (status, kind, version, codes) in CASES.items():
            with self.subTest(name):
                r = _route(name)
                self.assertIsInstance(r, Routing)
                self.assertEqual(r.status, status)
                self.assertEqual(r.kind, kind)
                self.assertEqual(r.spec_version, version)
                self.assertEqual([(d.code, d.path) for d in r.diagnostics], codes)

    def test_diagnostic_fields(self):
        self.assertEqual(
            _route("routing-foreign-object").diagnostics,
            (
                Diagnostic(
                    "NOT_EXCHANGE_DOCUMENT",
                    "REC-2",
                    "error",
                    "",
                    "The document root is not a package exchange document.",
                ),
            ),
        )
        self.assertEqual(
            _route("routing-previous-draft").diagnostics,
            (
                Diagnostic(
                    "VERSION_UNSUPPORTED",
                    "UNS-1",
                    "error",
                    "/spec_version",
                    "The declared spec_version is not supported by this checker.",
                ),
            ),
        )

    def test_root_order(self):
        # The version check runs before the root type test.
        self.assertEqual(
            [(d.code, d.path) for d in route({"spec_version": "2.0.0-draft.2", "type": "clip"}).diagnostics],
            [VERSION_BAD],
        )
        # The exchange document test runs first.
        self.assertEqual([(d.code, d.path) for d in route({"type": "package"}).diagnostics], [NOT_DOCUMENT])
        self.assertEqual([(d.code, d.path) for d in route("package").diagnostics], [NOT_DOCUMENT])

    def test_version_compare_is_exact(self):
        for version in ("2.0.0-DRAFT.3", " 2.0.0-draft.3", "2.0.0-draft.3 ", "2.0.0-draft.03", "2.0.0"):
            with self.subTest(version=version):
                r = route({"spec_version": version, "type": "package"})
                self.assertEqual([(d.code, d.path) for d in r.diagnostics], [VERSION_BAD])
                self.assertIsNone(r.spec_version)

    def test_constants(self):
        self.assertEqual(KINDS, ("package",))
        self.assertEqual(SUPPORTED_VERSIONS, {DRAFT3: ("package",)})


class RoutingIsolationTests(unittest.TestCase):
    def test_document_does_not_import_loader(self):
        code = (
            "import sys, tests.conformance.document; "
            "sys.exit(1 if 'tests.conformance.loader' in sys.modules else 0)"
        )
        done = subprocess.run([sys.executable, "-c", code], cwd=REPO)
        self.assertEqual(done.returncode, 0)


if __name__ == "__main__":
    unittest.main()
