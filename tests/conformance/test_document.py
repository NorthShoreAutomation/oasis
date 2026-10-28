"""Tests for record type and spec_version routing."""

import subprocess
import sys
import unittest
from pathlib import Path

from tests.conformance.document import KINDS, SPEC_VERSION, route
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic, Routing

REPO = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent / "fixtures" / "records"

TYPE_BAD = ("TYPE_UNSUPPORTED", "")
TYPE_BAD_AT_TYPE = ("TYPE_UNSUPPORTED", "/type")
VERSION_BAD = ("VERSION_UNSUPPORTED", "/spec_version")

# name: (status, record type, spec_version, [(code, path), ...])
CASES = {
    "routing-no-type": ("unsupported", None, SPEC_VERSION, [TYPE_BAD]),
    "routing-type-unknown": ("unsupported", None, SPEC_VERSION, [TYPE_BAD_AT_TYPE]),
    "routing-type-number": ("unsupported", None, SPEC_VERSION, [TYPE_BAD_AT_TYPE]),
    "routing-spec-version-absent": ("unsupported", "asset", None, [VERSION_BAD]),
    "routing-spec-version-major-0": ("unsupported", "asset", None, [VERSION_BAD]),
    "routing-spec-version-3x": ("unsupported", "asset", None, [VERSION_BAD]),
    "routing-spec-version-number": ("unsupported", "asset", None, [VERSION_BAD]),
    "routing-spec-version-unknown-draft": ("unsupported", "asset", None, [VERSION_BAD]),
    "routing-root-array": ("unsupported", None, None, [TYPE_BAD, VERSION_BAD]),
    "routing-foreign-object": ("unsupported", None, None, [TYPE_BAD, VERSION_BAD]),
    "routing-ok-minimal-asset": ("selected", "asset", SPEC_VERSION, []),
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
        r = _route("routing-foreign-object")
        self.assertEqual(
            r.diagnostics,
            (
                Diagnostic(
                    "TYPE_UNSUPPORTED",
                    "UNS-1",
                    "error",
                    "",
                    "The document root has no supported record type.",
                ),
                Diagnostic(
                    "VERSION_UNSUPPORTED",
                    "REC-4, UNS-1",
                    "error",
                    "/spec_version",
                    "The declared spec_version is not supported by this checker.",
                ),
            ),
        )

    def test_constants(self):
        self.assertEqual(len(KINDS), 6)
        self.assertEqual(SPEC_VERSION, "2.0.0-draft.2")


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
