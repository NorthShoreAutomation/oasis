"""The fixture manifest and the full-pipeline corpus sweep."""

import copy
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.conformance.corpus import DEFAULT_MANIFEST, FixtureCase, load_manifest
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.semantic import check
from tests.conformance.strict_json import parse_input
from tests.conformance.types import InputInvalid, SetupFailed

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDS = FIXTURES / "records"

# Rules of the coverage table whose check lives in semantic.py, document.py,
# strict_json.py, timecode.py, or loader.py.
CHECKED_RULES = (
    "DOC-1", "DOC-2", "DOC-3",
    "REC-2", "REC-4", "UNS-1",
    "PKG-3", "PKG-6",
    "ID-1", "ID-2", "ID-4", "ID-5", "ID-6",
    "TIME-2", "TIME-4", "TIME-5", "TIME-7", "TIME-8", "TIME-9", "TIME-12",
    "GRP-3", "GRP-4", "GRP-6",
    "VER-2", "VER-3",
    "REL-3",
    "COL-3", "COL-4", "COL-5",
    "MD-2", "MD-4", "MD-5", "MD-6",
    "DT-1", "DT-2", "DT-3",
    "ANN-3",
    "EXT-2", "EXT-5",
)

# Rules that only the schema checks, each with a structural fixture.
STRUCTURAL_RULES = ("TIME-6", "EXT-3", "AST-1", "REC-7", "PKG-2", "MD-2", "DT-1", "MD-4")

# Structural case id: (failing keyword, RFC 6901 instance pointer).
STRUCTURAL_ERRORS = {
    "structural-asset-missing-title": ("required", ""),
    "structural-asset-unknown-key": ("unevaluatedProperties", ""),
    "structural-manifest-missing-counts": ("required", "/manifest"),
    "structural-pattern-invalid-regex": ("format", "/constraints/pattern"),
    "structural-date-time-space": ("format", "/manifest/produced_at"),
    "structural-namespace-oasis": ("not", "/extensions"),
    "structural-drop-frame-25": ("enum", "/timing/time_base/rate"),
    "structural-metadata-value-object": ("anyOf", "/metadata/0/value"),
    "package-snapshot-with-members": ("oneOf", "/assets/0/collections/0"),
}

INPUT_INVALID = (("INPUT_INVALID", ""),)


def _pointer(segments):
    return "".join("/" + str(s).replace("~", "~0").replace("/", "~1") for s in segments)


def _run(test, case, bundle):
    """Run the pipeline on one case: (status, structural, pairs, structural errors)."""
    try:
        parsed = parse_input((FIXTURES / case.path).read_bytes())
    except InputInvalid:
        return "input-invalid", "not-run", INPUT_INVALID, ()
    routing = route(parsed.value)
    if routing.status != "selected":
        return "unsupported", "not-run", tuple((d.code, d.path) for d in routing.diagnostics), ()
    errors = bundle.entry_point(routing.kind).validate(parsed)
    if errors:
        return "complete", "invalid", (), tuple((e.validator, _pointer(e.absolute_path)) for e in errors)
    before = copy.deepcopy(parsed.value)
    diagnostics = check(parsed.value, routing)
    # DOC-3: the semantic stage never changes the tree.
    test.assertEqual(parsed.value, before)
    test.assertEqual(repr(parsed.value), repr(before))
    return "complete", "valid", tuple((d.code, d.path) for d in diagnostics), ()


class ManifestTests(unittest.TestCase):
    def test_manifest_loads(self):
        cases = load_manifest()
        self.assertEqual(len(cases), len(list(RECORDS.glob("*.json"))))
        self.assertTrue(all(isinstance(c, FixtureCase) for c in cases))
        self.assertEqual(DEFAULT_MANIFEST, FIXTURES / "manifest.json")

    def test_every_record_has_one_case(self):
        ids = [c.id for c in load_manifest()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {p.stem for p in RECORDS.iterdir()})
        for case in load_manifest():
            with self.subTest(case.id):
                self.assertEqual(case.path, "records/%s.json" % case.id)
                self.assertTrue((FIXTURES / case.path).is_file())

    def test_rules_cover_appendix_b(self):
        covered = {rule for case in load_manifest() for rule in case.rules}
        for rule in CHECKED_RULES:
            with self.subTest(rule):
                self.assertIn(rule, covered)
        self.assertEqual(
            {c.id for c in load_manifest() if "DOC-3" in c.rules},
            {c.id for c in load_manifest() if c.expected_structural == "valid"},
        )
        self.assertEqual(
            {c.id for c in load_manifest() if "DOC-1" in c.rules},
            {c.id for c in load_manifest() if c.expected_status == "input-invalid"},
        )

    def test_structural_rules_have_structural_cases(self):
        covered = {r for c in load_manifest() if c.expected_structural == "invalid" for r in c.rules}
        for rule in STRUCTURAL_RULES:
            with self.subTest(rule):
                self.assertIn(rule, covered)


class SweepTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(REPO / "definitions")

    def test_sweep(self):
        for case in load_manifest():
            with self.subTest(case.id):
                status, structural, pairs, errors = _run(self, case, self.bundle)
                self.assertEqual(status, case.expected_status)
                self.assertEqual(structural, case.expected_structural)
                self.assertEqual(pairs, case.expected_diagnostics)
                if case.expected_structural == "invalid":
                    self.assertIn(STRUCTURAL_ERRORS[case.id], errors)

    def test_every_structural_case_has_an_expected_error(self):
        invalid = {c.id for c in load_manifest() if c.expected_structural == "invalid"}
        self.assertEqual(invalid, set(STRUCTURAL_ERRORS))

    def test_input_fixtures_report_input_invalid(self):
        inputs = [c for c in load_manifest() if c.id.startswith("input-")]
        self.assertEqual(len(inputs), 4)
        for case in inputs:
            with self.subTest(case.id):
                data = (FIXTURES / case.path).read_bytes()
                data.decode("utf-8")
                with self.assertRaises(InputInvalid):
                    parse_input(data)
                self.assertEqual(case.expected_status, "input-invalid")
                self.assertEqual(case.expected_structural, "not-run")
                self.assertEqual(case.expected_diagnostics, INPUT_INVALID)

    def test_not_utf8_reports_input_invalid(self):
        data = b'{"type": "asset\xff"}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-utf8.json"
            path.write_bytes(data)
            with self.assertRaises(InputInvalid):
                parse_input(path.read_bytes())


VALID_CASE = {
    "id": "routing-ok-minimal-asset",
    "path": "records/routing-ok-minimal-asset.json",
    "expected_status": "complete",
    "expected_structural": "valid",
    "expected_diagnostics": [],
    "rules": ["REC-2"],
    "note": "A minimal asset.",
}


def _manifest(*cases):
    return {
        "manifest_version": "2.0.0",
        "contract": "2.0.0-draft.2",
        "provenance": {
            "kind": "synthetic",
            "source": "Newly authored OASIS conformance examples",
            "reuse_terms": "Apache License 2.0",
        },
        "cases": list(cases),
    }


class ManifestShapeTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / "records").mkdir()
        shutil.copy(RECORDS / "routing-ok-minimal-asset.json", self.root / "records")

    def load(self, document):
        path = self.root / "manifest.json"
        if isinstance(document, bytes):
            path.write_bytes(document)
        else:
            path.write_text(json.dumps(document), encoding="utf-8")
        return load_manifest(path)

    def test_valid(self):
        (case,) = self.load(_manifest(VALID_CASE))
        self.assertEqual(case.expected_diagnostics, ())
        self.assertEqual(case.rules, ("REC-2",))

    def test_shape_problems_fail_setup(self):
        def changed(**fields):
            return dict(VALID_CASE, **fields)

        def without(key):
            return {k: v for k, v in VALID_CASE.items() if k != key}

        bad = {
            "not json": b"{",
            "duplicate member": b'{"cases": [], "cases": []}',
            "root array": [],
            "unknown top key": dict(_manifest(VALID_CASE), extra=1),
            "missing top key": {k: v for k, v in _manifest(VALID_CASE).items() if k != "contract"},
            "wrong manifest_version": dict(_manifest(VALID_CASE), manifest_version="9.9.9"),
            "wrong contract": dict(_manifest(VALID_CASE), contract="2.0.0"),
            "provenance not object": dict(_manifest(VALID_CASE), provenance="synthetic"),
            "cases not array": dict(_manifest(VALID_CASE), cases={}),
            "unknown case key": _manifest(changed(extra=1)),
            "missing case key": _manifest(without("note")),
            "id not string": _manifest(changed(id=1)),
            "unknown status": _manifest(changed(expected_status="selected")),
            "unknown structural": _manifest(changed(expected_structural="skipped")),
            "not-run on complete": _manifest(changed(expected_structural="not-run")),
            "pair not two strings": _manifest(changed(expected_diagnostics=[["X"]])),
            "unsorted diagnostics": _manifest(
                changed(expected_diagnostics=[["B", "/b"], ["A", "/a"]])
            ),
            "rules not strings": _manifest(changed(rules=[1])),
            "empty note": _manifest(changed(note="")),
            "path outside records": _manifest(changed(path="../routing-ok-minimal-asset.json")),
            "path not matching id": _manifest(changed(path="records/other.json")),
            "duplicate id": _manifest(VALID_CASE, VALID_CASE),
            "missing file": _manifest(
                VALID_CASE, changed(id="absent", path="records/absent.json")
            ),
            "file without case": _manifest(),
        }
        for name, document in bad.items():
            with self.subTest(name):
                with self.assertRaises(SetupFailed):
                    self.load(document)


if __name__ == "__main__":
    unittest.main()
