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
from tests.conformance.number_limits import check_number_limits
from tests.conformance.semantic import CATALOG, check
from tests.conformance.strict_json import parse_input
from tests.conformance.types import InputInvalid, SetupFailed
from tests.conformance.validate import safe_pointer, schema_keyword

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDS = FIXTURES / "records"

# Rules of Appendix B whose check lives in semantic.py, document.py,
# number_limits.py, strict_json.py, timecode.py, or formats.py. Each one has
# at least one fixture.
CHECKED_RULES = (
    "DOC-1", "DOC-2", "DOC-3", "DOC-4",
    "REC-2", "UNS-1",
    "PKG-3", "PKG-6",
    "ID-1", "ID-2", "ID-4", "ID-5",
    "TIME-2", "TIME-4", "TIME-5", "TIME-7", "TIME-8", "TIME-9", "TIME-12", "TIME-13",
    "FILE-6", "FILE-8",
    "GRP-4", "GRP-6", "GRP-7", "GRP-10", "GRP-11", "GRP-12",
    "VER-2", "VER-6", "VER-7",
    "REL-3", "REL-4", "REL-5", "REL-6",
    "COL-3", "COL-4", "COL-7",
    "MD-4", "MD-5", "MD-6", "MD-7", "MD-8",
    "DT-1", "DT-3",
    "EXT-2",
)

# Rules that only the schema checks, each with a structurally invalid fixture.
STRUCTURAL_RULES = (
    "ACC-1", "ACC-2", "ANN-4", "AST-1", "DT-2", "EXT-3", "FILE-9", "MD-2", "PKG-2", "REC-7",
    "STO-1", "TIME-6", "TIME-10", "TIME-14", "VER-4", "VER-5",
)

INPUT_INVALID = (("INPUT_INVALID", ""),)
NUMBER_CODES = frozenset({"NUMBER_OUT_OF_RANGE", "NUMBER_TOO_PRECISE"})


def _run(test, case, bundle):
    """Run the pipeline on one case: (status, structural, pairs, structural errors).

    The stages run in the order of the validate command: strict parse
    (DOC-1), root checks (REC-2, UNS-1), number limits (DOC-4), schema, then
    semantic checks. Structural errors are (keyword, pointer) pairs as the
    command reports them.
    """
    try:
        parsed = parse_input((FIXTURES / case.path).read_bytes())
    except InputInvalid:
        return "input-invalid", "not-run", INPUT_INVALID, ()
    routing = route(parsed.value)
    if routing.status != "selected":
        return "unsupported", "not-run", tuple((d.code, d.path) for d in routing.diagnostics), ()
    limits = check_number_limits(parsed.value, bundle.property_names)
    if limits:
        return "input-invalid", "not-run", tuple((d.code, d.path) for d in limits), ()
    errors = bundle.entry_point(routing.kind).validate(parsed)
    if errors:
        return "complete", "invalid", (), tuple((schema_keyword(e), safe_pointer(e)) for e in errors)
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
        for case in load_manifest():
            with self.subTest(case.id):
                parse_refused = case.expected_diagnostics == INPUT_INVALID
                self.assertEqual("DOC-1" in case.rules, parse_refused)
                if case.expected_status == "input-invalid":
                    self.assertTrue("DOC-1" in case.rules or "DOC-4" in case.rules)
                    if not parse_refused:
                        self.assertIn("DOC-4", case.rules)
                        self.assertTrue(case.expected_diagnostics)
                        self.assertLessEqual({code for code, _p in case.expected_diagnostics}, NUMBER_CODES)

    def test_checked_rules_cover_the_catalog(self):
        cited = {rule for rule, _severity, _message in CATALOG.values() for rule in rule.split(", ")}
        self.assertLessEqual(cited, set(CHECKED_RULES))

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
                    self.assertIn(case.expected_schema_error, errors)

    def test_every_structural_case_has_an_expected_error(self):
        for case in load_manifest():
            with self.subTest(case.id):
                invalid = case.expected_structural == "invalid"
                self.assertEqual(case.expected_schema_error is not None, invalid)

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
        data = b'{"type": "package\xff"}'
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "not-utf8.json"
            path.write_bytes(data)
            with self.assertRaises(InputInvalid):
                parse_input(path.read_bytes())


VALID_CASE = {
    "id": "routing-ok-minimal-package",
    "path": "records/routing-ok-minimal-package.json",
    "expected_status": "complete",
    "expected_structural": "valid",
    "expected_diagnostics": [],
    "rules": ["REC-2"],
    "note": "A minimal package.",
}

INVALID_CASE = dict(
    VALID_CASE,
    expected_structural="invalid",
    expected_schema_error={"keyword": "required", "path": "/manifest"},
)


def _manifest(*cases):
    return {
        "manifest_version": "2.0.0",
        "contract": "2.0.0-draft.3",
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
        shutil.copy(RECORDS / "routing-ok-minimal-package.json", self.root / "records")

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
        self.assertIsNone(case.expected_schema_error)

    def test_valid_schema_error(self):
        (case,) = self.load(_manifest(INVALID_CASE))
        self.assertEqual(case.expected_schema_error, ("required", "/manifest"))

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
            "path outside records": _manifest(changed(path="../routing-ok-minimal-package.json")),
            "path not matching id": _manifest(changed(path="records/other.json")),
            "duplicate id": _manifest(VALID_CASE, VALID_CASE),
            "missing file": _manifest(
                VALID_CASE, changed(id="absent", path="records/absent.json")
            ),
            "file without case": _manifest(),
            "schema error on a valid case": _manifest(
                changed(expected_schema_error={"keyword": "required", "path": ""})
            ),
            "invalid case without schema error": _manifest(changed(expected_structural="invalid")),
            "schema error not object": _manifest(dict(INVALID_CASE, expected_schema_error="required")),
            "schema error unknown key": _manifest(
                dict(INVALID_CASE, expected_schema_error={"keyword": "required", "path": "", "x": 1})
            ),
            "schema error empty keyword": _manifest(
                dict(INVALID_CASE, expected_schema_error={"keyword": "", "path": ""})
            ),
            "schema error path not pointer": _manifest(
                dict(INVALID_CASE, expected_schema_error={"keyword": "required", "path": "manifest"})
            ),
            "schema error path bad escape": _manifest(
                dict(INVALID_CASE, expected_schema_error={"keyword": "required", "path": "/a~2"})
            ),
        }
        for name, document in bad.items():
            with self.subTest(name):
                with self.assertRaises(SetupFailed):
                    self.load(document)


if __name__ == "__main__":
    unittest.main()
