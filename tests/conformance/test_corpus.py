"""The fixture manifest and the full-pipeline corpus sweep."""

import copy
import importlib
import inspect
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from tests.conformance.corpus import DEFAULT_MANIFEST, FixtureCase, load_manifest
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.multifile import MANIFEST_NAME, ReadLimits, evaluate_folder
from tests.conformance.number_limits import check_number_limits
from tests.conformance.semantic import CATALOG, check
from tests.conformance.strict_json import parse_input
from tests.conformance.types import InputInvalid, SetupFailed
from tests.conformance.validate import safe_pointer, schema_keyword

REPO = Path(__file__).resolve().parents[2]
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDS = FIXTURES / "records"
PACKAGES = FIXTURES / "packages"

# The multi-file package cases of the corpus. A case in the manifest that is not
# here, or a case here that is not in the manifest, fails a test.
PACKAGE_CASES = (
    "package-id-duplicate-across-members",
    "package-line-crlf",
    "package-line-no-final-lf",
    "package-member-checksum",
    "package-member-count",
    "package-member-missing",
    "package-member-size",
    "package-member-type",
    "package-member-unlisted",
    "package-ok-empty-list",
    "package-ok-gzip-member",
    "package-ok-two-asset-members",
    "package-position-duplicate-across-members",
    "package-records-with-arrays",
    "package-reference-across-members",
)

# Codes of the MFP rules that no packages/ case holds. Git cannot keep a link, a
# special file, or a case collision on every file system, so a test builds
# these in a temporary folder. Each entry names the test that does it:
# (test module, "Class.method"). The test must exist, and its code must name
# the diagnostic code.
MFP_NAMED_MODULES = ("test_multifile_folder", "test_multifile_reader", "test_multifile_validate")
MFP_NAMED_TESTS = {
    "MANIFEST_FILE_NAME": ("test_multifile_validate", "MemberRuleAndScanTests.test_manifest_file_name"),
    "MEMBER_PATH_DUPLICATE": (
        "test_multifile_folder",
        "CheckMemberListTest.test_duplicate_path_is_reported_at_each_later_entry",
    ),
    "MEMBER_PATH_CASE_COLLISION": (
        "test_multifile_folder",
        "CheckMemberListTest.test_paths_that_differ_only_in_case_collide",
    ),
    "MEMBER_PATH_NOT_EXACT": (
        "test_multifile_folder",
        "ExactSpellingTest.test_case_folding_file_system_reports_not_exact",
    ),
    "MEMBER_NOT_REGULAR": ("test_multifile_folder", "ScanFolderTest.test_member_that_is_a_link_is_not_regular"),
    "FILE_UNLISTED": (
        "test_multifile_folder",
        "ScanFolderTest.test_unlisted_file_outside_the_record_folders_is_a_warning",
    ),
    "MEMBER_COMPRESSION_MISMATCH": ("test_multifile_validate", "IntegrityTests.test_compression_mismatch"),
    "MEMBER_EMPTY_UNEXPECTED": (
        "test_multifile_folder",
        "CheckMemberListTest.test_empty_member_beside_a_full_member_is_unexpected",
    ),
}

# Rules of Appendix B whose check lives in semantic.py, document.py,
# number_limits.py, strict_json.py, timecode.py, formats.py, or multifile.py.
# Each one has at least one fixture.
CHECKED_RULES = (
    "DOC-1", "DOC-2", "DOC-3", "DOC-4",
    "REC-2", "UNS-1",
    "PKG-3", "PKG-6",
    "MFP-1", "MFP-2", "MFP-3", "MFP-4", "MFP-5", "MFP-6",
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


def _record_cases():
    return [c for c in load_manifest() if not c.is_package]


def _package_cases():
    return [c for c in load_manifest() if c.is_package]


def _is_mfp(rule_text):
    return any(rule.startswith("MFP-") for rule in rule_text.split(", "))


class ManifestTests(unittest.TestCase):
    def test_manifest_loads(self):
        cases = load_manifest()
        self.assertEqual(len(_record_cases()), len(list(RECORDS.glob("*.json"))))
        self.assertEqual(len(_package_cases()), len(list(PACKAGES.iterdir())))
        self.assertEqual(len(cases), len(_record_cases()) + len(_package_cases()))
        self.assertTrue(all(isinstance(c, FixtureCase) for c in cases))
        self.assertEqual(DEFAULT_MANIFEST, FIXTURES / "manifest.json")

    def test_every_record_has_one_case(self):
        ids = [c.id for c in _record_cases()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {p.stem for p in RECORDS.iterdir()})
        for case in _record_cases():
            with self.subTest(case.id):
                self.assertEqual(case.path, "records/%s.json" % case.id)
                self.assertTrue((FIXTURES / case.path).is_file())

    def test_every_package_folder_has_one_case(self):
        ids = [c.id for c in _package_cases()]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(set(ids), {p.name for p in PACKAGES.iterdir()})
        for case in _package_cases():
            with self.subTest(case.id):
                self.assertEqual(case.path, "packages/%s/" % case.id)
                self.assertTrue((FIXTURES / case.path / MANIFEST_NAME).is_file())

    def test_package_cases_are_the_planned_set(self):
        self.assertEqual(sorted(c.id for c in _package_cases()), list(PACKAGE_CASES))

    def test_rules_cover_appendix_b(self):
        covered = {rule for case in load_manifest() for rule in case.rules}
        for rule in CHECKED_RULES:
            with self.subTest(rule):
                self.assertIn(rule, covered)
        # DOC-1, DOC-3, and DOC-4 describe the single-document pipeline of this
        # module; a package case is judged by evaluate_folder and cites the MFP rules.
        self.assertEqual(
            {c.id for c in _record_cases() if "DOC-3" in c.rules},
            {c.id for c in _record_cases() if c.expected_structural == "valid"},
        )
        for case in _record_cases():
            with self.subTest(case.id):
                parse_refused = case.expected_diagnostics == INPUT_INVALID
                self.assertEqual("DOC-1" in case.rules, parse_refused)
                if case.expected_status == "input-invalid":
                    self.assertTrue("DOC-1" in case.rules or "DOC-4" in case.rules)
                    if not parse_refused:
                        self.assertIn("DOC-4", case.rules)
                        self.assertTrue(case.expected_diagnostics)
                        self.assertLessEqual({code for code, _p in case.expected_diagnostics}, NUMBER_CODES)
        for case in _package_cases():
            with self.subTest(case.id):
                self.assertTrue(any(_is_mfp(rule) for rule in case.rules))
                self.assertNotIn("DOC-3", case.rules)

    def test_checked_rules_cover_the_catalog(self):
        cited = {cited_rule for rules, _severity, _message in CATALOG.values() for cited_rule in rules.split(", ")}
        self.assertLessEqual(cited, set(CHECKED_RULES))

    def test_every_mfp_code_is_exercised(self):
        """A code of an MFP rule has a packages/ case or a named test. A new code must get one."""
        mfp_codes = {code for code, (rule, _severity, _message) in CATALOG.items() if _is_mfp(rule)}
        self.assertTrue(mfp_codes)
        in_fixtures = {item[0] for case in _package_cases() for item in case.expected_diagnostics}
        self.assertLessEqual(in_fixtures, set(CATALOG))
        self.assertLessEqual(set(MFP_NAMED_TESTS), mfp_codes)
        self.assertEqual(mfp_codes - in_fixtures - set(MFP_NAMED_TESTS), set())
        for code, (module_name, test_name) in MFP_NAMED_TESTS.items():
            with self.subTest(code):
                self.assertIn(module_name, MFP_NAMED_MODULES)
                module = importlib.import_module("tests.conformance." + module_name)
                class_name, method_name = test_name.split(".")
                method = getattr(getattr(module, class_name), method_name)
                self.assertTrue(method_name.startswith("test_"))
                self.assertIn('"%s"' % code, inspect.getsource(method))

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
        for case in _record_cases():
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
        inputs = [c for c in _record_cases() if c.id.startswith("input-")]
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


def _member_index(pointer):
    """The manifest index of a member pointer ``/manifest/members/<n>``, or None."""
    if pointer is None:
        return None
    prefix = "/manifest/members/"
    assert pointer.startswith(prefix), pointer
    return int(pointer[len(prefix):])


def _run_package(case):
    """Check one package folder: (result record, located diagnostics, structural errors)."""
    folder = FIXTURES / case.path
    record = evaluate_folder(folder / MANIFEST_NAME, REPO / "definitions", None, ReadLimits(), from_folder=True)
    found = tuple((d["code"], d["path"], _member_index(d.get("member")), d.get("line")) for d in record["diagnostics"])
    errors = tuple((e["keyword"], e["path"]) for e in record["structural_errors"])
    return record, found, errors


class PackageSweepTests(unittest.TestCase):
    def test_package_cases_match_expected_outcomes(self):
        cases = _package_cases()
        self.assertEqual(sorted(c.id for c in cases), list(PACKAGE_CASES))
        for case in cases:
            with self.subTest(case.id):
                record, found, errors = _run_package(case)
                self.assertEqual(record["form"], "multi-file")
                self.assertEqual(record["execution_status"], case.expected_status)
                self.assertEqual(record["structural"], case.expected_structural)
                self.assertEqual(found, case.located_diagnostics)
                if case.expected_structural == "invalid":
                    self.assertIn(case.expected_schema_error, errors)
                else:
                    self.assertEqual(errors, ())
                self.assertEqual(record["semantic"], "run" if case.expected_structural == "valid" else "not-run")

    def test_package_folders_hold_only_the_files_of_their_package(self):
        # Nothing but the manifest file and the member files it lists: no stray file from a tool.
        for case in _package_cases():
            with self.subTest(case.id):
                folder = FIXTURES / case.path
                files = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()}
                manifest = json.loads((folder / MANIFEST_NAME).read_text(encoding="utf-8"))
                listed = {m["path"] for m in manifest["manifest"]["members"]}
                # Two cases break this on purpose: one lists a file that is not there,
                # and one holds a file that it does not list.
                missing = len(listed - files)
                unlisted = len(files - listed - {MANIFEST_NAME})
                self.assertEqual(missing, 1 if case.id == "package-member-missing" else 0)
                self.assertEqual(unlisted, 1 if case.id == "package-member-unlisted" else 0)


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


PACKAGE_CASE = {
    "id": "package-ok-example",
    "path": "packages/package-ok-example/",
    "expected_status": "complete",
    "expected_structural": "valid",
    "expected_diagnostics": [["MEMBERS_SMALL", "/manifest/members", None, None], ["ID_DUPLICATE", "/id", 1, 2]],
    "rules": ["MFP-3"],
    "note": "A package.",
}


def _manifest(*cases):
    return {
        "manifest_version": "2.0.0",
        "contract": "2.0.0-draft.4",
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

    def add_package(self, name="package-ok-example", files=(MANIFEST_NAME,)):
        folder = self.root / "packages" / name
        for relative in files:
            (folder / relative).parent.mkdir(parents=True, exist_ok=True)
            (folder / relative).write_bytes(b"{}")

    def test_valid_package_case(self):
        self.add_package()
        records, package = self.load(_manifest(VALID_CASE, PACKAGE_CASE))
        self.assertTrue(package.is_package)
        self.assertFalse(records.is_package)
        self.assertEqual(package.path, "packages/package-ok-example/")
        self.assertEqual(
            package.expected_diagnostics,
            (("MEMBERS_SMALL", "/manifest/members", None, None), ("ID_DUPLICATE", "/id", 1, 2)),
        )
        self.assertEqual(package.located_diagnostics, package.expected_diagnostics)
        self.assertEqual(records.expected_diagnostics, ())

    def test_package_case_may_write_a_finding_as_a_pair(self):
        self.add_package()
        case = dict(PACKAGE_CASE, expected_diagnostics=[["COUNT_MISMATCH", "/manifest/counts/assets"]])
        _records, package = self.load(_manifest(VALID_CASE, case))
        self.assertEqual(package.expected_diagnostics, (("COUNT_MISMATCH", "/manifest/counts/assets"),))
        self.assertEqual(package.located_diagnostics, (("COUNT_MISMATCH", "/manifest/counts/assets", None, None),))

    def test_package_diagnostics_are_sorted_by_member_line_path_code(self):
        self.add_package()
        sorted_case = dict(
            PACKAGE_CASE,
            expected_diagnostics=[
                ["MEMBERS_SMALL", "/manifest/members", None, None],
                ["B", "/z", 0, None],
                ["B", "/a", 0, 1],
                ["A", "/z", 0, 1],
                ["A", "/a", 1, 1],
            ],
        )
        (_records, package) = self.load(_manifest(VALID_CASE, sorted_case))
        self.assertEqual(len(package.expected_diagnostics), 5)

    def test_package_shape_problems_fail_setup(self):
        def changed(**fields):
            return dict(PACKAGE_CASE, **fields)

        bad = {
            "path without the folder form": changed(path="packages/package-ok-example"),
            "path not matching id": changed(path="packages/other/"),
            "path in records": changed(path="records/package-ok-example.json"),
            "path with a parent part": changed(path="packages/../package-ok-example/"),
            "id with a slash": changed(id="a/b", path="packages/a/b/"),
            "id starting with a dot": changed(id=".x", path="packages/.x/"),
            "three items": changed(expected_diagnostics=[["A", "/a", 1]]),
            "five items": changed(expected_diagnostics=[["A", "/a", 1, 1, 1]]),
            "member not an integer": changed(expected_diagnostics=[["A", "/a", "1", 1]]),
            "member a boolean": changed(expected_diagnostics=[["A", "/a", True, 1]]),
            "member negative": changed(expected_diagnostics=[["A", "/a", -1, 1]]),
            "line zero": changed(expected_diagnostics=[["A", "/a", 0, 0]]),
            "line not an integer": changed(expected_diagnostics=[["A", "/a", 0, "1"]]),
            "line a boolean": changed(expected_diagnostics=[["A", "/a", 0, True]]),
            "empty code": changed(expected_diagnostics=[["", "/a", 0, 1]]),
            "member before no member": changed(
                expected_diagnostics=[["A", "/a", 0, 1], ["B", "/a", None, None]]
            ),
            "line after a later line": changed(expected_diagnostics=[["A", "/a", 0, 2], ["A", "/a", 0, 1]]),
            "path after a later path": changed(expected_diagnostics=[["A", "/b", 0, 1], ["A", "/a", 0, 1]]),
            "code after a later code": changed(expected_diagnostics=[["B", "/a", 0, 1], ["A", "/a", 0, 1]]),
        }
        self.add_package()
        for name, case in bad.items():
            with self.subTest(name):
                with self.assertRaises(SetupFailed):
                    self.load(_manifest(VALID_CASE, case))

    def test_record_case_cannot_have_a_location(self):
        for item in (["A", "/a", 0, 1], ["A", "/a", None, None]):
            with self.subTest(item):
                with self.assertRaises(SetupFailed):
                    self.load(_manifest(dict(VALID_CASE, expected_diagnostics=[item])))

    def test_package_folder_problems_fail_setup(self):
        with self.subTest("package folder without a case"):
            self.add_package()
            with self.assertRaises(SetupFailed):
                self.load(_manifest(VALID_CASE))
        with self.subTest("case without a folder"):
            shutil.rmtree(self.root / "packages")
            with self.assertRaises(SetupFailed):
                self.load(_manifest(VALID_CASE, PACKAGE_CASE))
        with self.subTest("folder without a manifest file"):
            self.add_package(files=("assets/part-00001.jsonl",))
            with self.assertRaises(SetupFailed):
                self.load(_manifest(VALID_CASE, PACKAGE_CASE))
        with self.subTest("a stray file in packages"):
            shutil.rmtree(self.root / "packages")
            self.add_package()
            (self.root / "packages" / "stray.json").write_bytes(b"{}")
            with self.assertRaises(SetupFailed):
                self.load(_manifest(VALID_CASE, PACKAGE_CASE))

    def test_package_case_id_is_unique_across_forms(self):
        self.add_package()
        with self.assertRaises(SetupFailed):
            self.load(_manifest(VALID_CASE, PACKAGE_CASE, PACKAGE_CASE))

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
