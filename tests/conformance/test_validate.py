"""The validate command and the result record."""

import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path

from jsonschema import Draft202012Validator

from tests.conformance import validate
from tests.conformance.corpus import load_manifest
from tests.conformance.loader import load_bundle
from tests.conformance.semantic import CATALOG
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"
FIXTURES = Path(__file__).resolve().parent / "fixtures"
RECORDS = FIXTURES / "records"
RESULT_SCHEMA = Path(__file__).resolve().parent / "result.schema.json"

SENTINELS = ("ZZSENTINELZZ", "zzsentinelzz")


def run(*argv):
    """Run main with captured stdout and stderr: (exit code, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        try:
            code = validate.main([str(arg) for arg in argv])
        except SystemExit as stop:
            code = stop.code
    return code, out.getvalue(), err.getvalue()


def run_strict(*argv):
    """Run main with stdout encoded as strict UTF-8, as a real terminal or pipe does."""
    raw = io.BytesIO()
    out = io.TextIOWrapper(raw, encoding="utf-8", errors="strict", newline="")
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
        code = validate.main(list(argv))
    out.flush()
    return code, raw.getvalue().decode("utf-8")


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


class TempFiles:
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def write(self, name, data):
        path = Path(self.directory.name) / name
        if isinstance(data, bytes):
            path.write_bytes(data)
        else:
            path.write_text(json.dumps(data), encoding="utf-8")
        return path


class CommandTests(TempFiles, unittest.TestCase):
    def test_every_example_passes(self):
        examples = sorted(EXAMPLES.glob("*.json"))
        self.assertTrue(examples)
        for path in examples:
            with self.subTest(path.name):
                code, out, _ = run(path)
                self.assertEqual(code, 0, out)
                self.assertTrue(out.startswith("PASS status=complete "), out)

    def test_examples_are_the_three_packages(self):
        self.assertEqual(
            [p.stem for p in sorted(EXAMPLES.glob("*.json"))],
            ["package-complete", "package-full", "package-minimal"],
        )

    def test_warning_alone_still_passes(self):
        # Only the two multi-file listing and size codes are warnings; they never fail a package alone.
        self.assertEqual({c for c, (_r, severity, _m) in CATALOG.items() if severity == "warning"}, {"FILE_UNLISTED", "MEMBERS_SMALL"})
        record = validate.evaluate((EXAMPLES / "package-minimal.json").read_bytes(), DEFINITIONS)
        record["diagnostics"] = [
            {"code": "COUNT_MISMATCH", "rule": "PKG-3", "severity": "warning", "path": "", "message": "m"}
        ]
        self.assertEqual(validate.exit_code(record), 0)
        record["diagnostics"][0]["severity"] = "error"
        self.assertEqual(validate.exit_code(record), 1)

    def test_seconds_disagree_fails(self):
        code, out, _ = run(RECORDS / "time-seconds-disagree.json")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("FAIL status=complete type=package structural=valid semantic=run\n"), out)
        self.assertIn("\nerror SECONDS_DISAGREE /assets/0/annotations/0/start_seconds: ", out)

    def test_number_limit_is_input_invalid_with_routing_fields(self):
        code, out, _ = run(RECORDS / "number-range-core.json")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("FAIL status=input-invalid type=package structural=not-run semantic=not-run\n"), out)
        self.assertIn("\nerror NUMBER_OUT_OF_RANGE ", out)
        record = json.loads(run(RECORDS / "number-range-core.json", "--json")[1])
        self.assertEqual((record["type"], record["spec_version"]), ("package", "2.0.0-draft.4"))

    def test_spec_version_outside_major_2_is_unsupported(self):
        code, out, _ = run(RECORDS / "routing-spec-version-major-0.json")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("FAIL status=unsupported "), out)
        self.assertIn("structural=not-run semantic=not-run", out)

    def test_bom_is_input_invalid(self):
        code, out, _ = run(RECORDS / "input-bom.json")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("FAIL status=input-invalid type=none structural=not-run semantic=not-run\n"), out)
        self.assertIn("error INPUT_INVALID (root): ", out)

    def test_structural_invalid_fails(self):
        code, out, _ = run(RECORDS / "structural-asset-unknown-key.json")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.startswith("FAIL status=complete type=package structural=invalid semantic=not-run\n"), out)
        self.assertIn("schema errors: 1\n  /assets/0 keyword unevaluatedProperties\n", out)

    def test_missing_file_is_setup_failure(self):
        code, out, _ = run(Path(self.directory.name) / "absent.json")
        self.assertEqual(code, 2)
        self.assertTrue(out.startswith("ERROR status=setup-failed type=none structural=not-run semantic=not-run\n"), out)
        self.assertIn("note: Setup failed: input file cannot be read.\n", out)

    def test_non_utf8_file_name(self):
        name = os.fsdecode(b"bad\xff.json")
        path = Path(self.directory.name) / name
        try:
            shutil.copyfile(EXAMPLES / "package-minimal.json", path)
        except (OSError, UnicodeError):
            self.skipTest("the file system refuses a non-UTF-8 file name")
        code, out = run_strict(str(path))
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("PASS "), out)
        code, out = run_strict(str(path), "--json")
        self.assertEqual(code, 0, out)
        record = json.loads(out)
        self.assertEqual(record["execution_status"], "complete")
        self.assertTrue(record["file"].endswith("bad\\xff.json"), record["file"])
        record["file"].encode("utf-8")

    def test_bad_option_is_usage_error(self):
        code, out, err = run(EXAMPLES / "package-minimal.json", "--no-such-option")
        self.assertEqual(code, 2)
        self.assertEqual(out, "")
        self.assertIn("usage:", err)

    def test_huge_number_is_setup_failure(self):
        document = load(EXAMPLES / "package-minimal.json")
        text = json.dumps(document)[:-1] + ', "size": ' + "9" * 5000 + "}"
        path = self.write("huge.json", text.encode("utf-8"))
        code, out, _ = run(path)
        self.assertEqual(code, 2, out)
        self.assertTrue(out.startswith("ERROR status=setup-failed "), out)
        self.assertIn("note: Setup failed: numeric token length exceeds 1024 bytes.\n", out)
        self.assertNotIn("input-invalid", out)
        record = json.loads(run(path, "--json")[1])
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertEqual(record["diagnostics"], [])
        self.assertIsNotNone(record["input_sha256"])

    def test_deep_constraint_pattern_is_setup_failure(self):
        package = load(EXAMPLES / "package-full.json")
        (definition,) = [d for d in package["metadata_definitions"] if "pattern" in d.get("constraints", {})]
        definition["constraints"]["pattern"] = "(" * 1500 + "a" + ")" * 1500
        path = self.write("deep-pattern.json", package)
        code, out, _ = run(path)
        self.assertEqual(code, 2, out[:400])
        self.assertTrue(out.startswith("ERROR status=setup-failed "), out[:400])
        self.assertIn("note: Setup failed: pattern nesting exceeds the checker's resource limit.\n", out)
        self.assertNotIn("structural=invalid", out)
        record = json.loads(run(path, "--json")[1])
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertEqual(record["structural"], "not-run")
        self.assertEqual(record["limitations"], ["Setup failed: pattern nesting exceeds the checker's resource limit."])

    def test_uppercase_ipvfuture_namespace_schema_passes(self):
        package = load(EXAMPLES / "package-full.json")
        package["manifest"]["namespaces"][0]["schema"] = "https://[V1.a]/schema"
        path = self.write("ipvfuture.json", package)
        code, out, _ = run(path)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.startswith("PASS status=complete type=package structural=valid "), out)

    def test_json_output_validates_for_each_status(self):
        schema = load(RESULT_SCHEMA)
        Draft202012Validator.check_schema(schema)
        checker = Draft202012Validator(schema)
        cases = {
            "complete": EXAMPLES / "package-full.json",
            "complete-invalid": RECORDS / "structural-asset-unknown-key.json",
            "input-invalid": RECORDS / "input-bom.json",
            "input-invalid-number": RECORDS / "number-range-core.json",
            "unsupported": RECORDS / "routing-spec-version-major-0.json",
            "setup-failed": Path(self.directory.name) / "absent.json",
        }
        for name, path in cases.items():
            with self.subTest(name):
                code, out, _ = run(path, "--json")
                record = json.loads(out)
                self.assertEqual(sorted(checker.iter_errors(record), key=str), [])
                status = {"complete-invalid": "complete", "input-invalid-number": "input-invalid"}.get(name, name)
                self.assertEqual(record["execution_status"], status)
                self.assertEqual(record["file"], str(path))
                self.assertEqual(record["form"], "single-document")
                self.assertEqual(code, {"complete": 0, "setup-failed": 2}.get(name, 1))

    def test_record_fields(self):
        data = (EXAMPLES / "package-minimal.json").read_bytes()
        record = validate.evaluate(data, DEFINITIONS)
        bundle = load_bundle(DEFINITIONS)
        self.assertEqual(
            record["harness"],
            {
                "id": "oasis-python-reference-harness",
                "version": "2.0.0-draft.4",
                "dependencies": ["jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4"],
            },
        )
        self.assertEqual(record["input_sha256"], parse_input(data).sha256)
        self.assertEqual(record["bundle_manifest_sha256"], bundle.manifest_sha256)
        self.assertEqual(record["type"], "package")
        self.assertEqual(record["spec_version"], "2.0.0-draft.4")
        self.assertEqual(
            (record["execution_status"], record["structural"], record["semantic"]),
            ("complete", "valid", "run"),
        )
        self.assertEqual(record["limitations"], [])

    def test_dependencies_match_requirements(self):
        lines = (Path(__file__).resolve().parent / "requirements.txt").read_text(encoding="utf-8").split()
        self.assertEqual(list(validate.DEPENDENCIES), lines)

    def test_bundle_failure_is_setup_failure(self):
        data = (EXAMPLES / "package-minimal.json").read_bytes()
        record = validate.evaluate(data, Path(self.directory.name))
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertIsNone(record["bundle_manifest_sha256"])
        self.assertEqual(len(record["limitations"]), 1)

    def test_result_schema_codes_are_the_catalog(self):
        schema = load(RESULT_SCHEMA)
        codes = schema["$defs"]["diagnostic"]["properties"]["code"]["enum"]
        self.assertEqual(codes, sorted(CATALOG))
        self.assertEqual(len(codes), 69)
        self.assertEqual(schema["$defs"]["diagnostic"]["properties"]["severity"]["enum"], ["error", "warning"])
        self.assertEqual(schema["properties"]["harness"]["properties"]["version"]["const"], validate.HARNESS_VERSION)
        self.assertEqual(schema["properties"]["spec_version"]["enum"], ["2.0.0-draft.4", None])
        self.assertEqual(schema["properties"]["type"]["enum"], ["package", None])
        self.assertEqual(schema["$id"], "https://www.northshoreautomation.com/schemas/oasis/2/conformance/result.schema.json")


class OutputSafetyTests(TempFiles, unittest.TestCase):
    def sentinel_inputs(self):
        sentinel = load(RECORDS / "sentinel-strings.json")
        unknown_key = dict(sentinel, ZZSENTINELZZ="value ZZSENTINELZZ")
        nested = load(RECORDS / "sentinel-strings.json")
        nested["assets"][0]["files"][0]["checksum"]["ZZSENTINELZZ"] = "value ZZSENTINELZZ"
        # Draft.3 has no connection object, so the credential
        # sentinel lives in an extension value of a storage location.
        credential = load(EXAMPLES / "package-complete.json")
        credential["storage_locations"][0]["extensions"] = {"archive_b": {"credential_reference": "ZZSENTINELZZ"}}
        namespace = load(RECORDS / "package-namespace-undeclared.json")
        namespace["assets"][0]["extensions"] = {"zzsentinelzz": {"rating": 4}}
        return {
            "sentinel-strings": RECORDS / "sentinel-strings.json",
            "unknown-key": self.write("unknown-key.json", unknown_key),
            "nested-unknown-key": self.write("nested-unknown-key.json", nested),
            "credential": self.write("credential.json", credential),
            "namespace": self.write("namespace.json", namespace),
        }

    def test_output_never_contains_input_values(self):
        expected = {
            "sentinel-strings": ("complete", "valid", ["REFERENCE_UNRESOLVED"]),
            "unknown-key": ("complete", "invalid", []),
            "nested-unknown-key": ("complete", "invalid", []),
            "credential": ("complete", "valid", []),
            "namespace": ("complete", "valid", ["NAMESPACE_UNDECLARED"]),
        }
        for name, path in self.sentinel_inputs().items():
            with self.subTest(name):
                self.assertIn("ZZSENTINELZZ", path.read_text(encoding="utf-8").upper())
                _, text, _ = run(path)
                _, raw, _ = run(path, "--json")
                record = json.loads(raw)
                status, structural, codes = expected[name]
                self.assertEqual((record["execution_status"], record["structural"]), (status, structural))
                self.assertEqual([d["code"] for d in record["diagnostics"]], codes)
                if name == "nested-unknown-key":
                    self.assertEqual(
                        record["structural_errors"],
                        [{"path": "/assets/0/files/0/checksum", "keyword": "additionalProperties"}],
                    )
                for output in (text, raw):
                    for sentinel in SENTINELS:
                        self.assertNotIn(sentinel, output)

    def test_printable_escapes_control_characters(self):
        self.assertEqual(validate._printable("a\x01b\nc\x7f"), "a\\u0001b\\u000ac\\u007f")
        self.assertEqual(validate._printable("plain /a~1b"), "plain /a~1b")

    def test_human_escapes_control_characters(self):
        record = validate.evaluate((EXAMPLES / "package-minimal.json").read_bytes(), DEFINITIONS)
        record["limitations"] = ["Setup failed: bad\x01text."]
        record["diagnostics"] = [
            {"code": "INPUT_INVALID", "rule": "DOC-1", "severity": "error", "path": "/a\x02", "message": "m"}
        ]
        text = validate._human(record, 1)
        self.assertIn("note: Setup failed: bad\\u0001text.\n", text)
        self.assertIn("error INPUT_INVALID /a\\u0002: m\n", text)
        self.assertNotIn("\x01", text)
        self.assertNotIn("\x02", text)
        self.assertEqual(text.count("\n"), 3)


MULTI_FILE_CODES = {
    "MANIFEST_FILE_NAME": ("MFP-1", "error"),
    "MEMBER_PATH_DUPLICATE": ("MFP-2", "error"),
    "MEMBER_PATH_CASE_COLLISION": ("MFP-2", "error"),
    "MEMBER_TYPE_MISMATCH": ("MFP-2", "error"),
    "MEMBER_MISSING": ("MFP-3", "error"),
    "MEMBER_NOT_REGULAR": ("MFP-3", "error"),
    "MEMBER_SIZE_MISMATCH": ("MFP-3", "error"),
    "MEMBER_CHECKSUM_MISMATCH": ("MFP-3", "error"),
    "MEMBER_UNLISTED": ("MFP-3", "error"),
    "FILE_UNLISTED": ("MFP-3", "warning"),
    "MEMBER_COMPRESSION_MISMATCH": ("MFP-4", "error"),
    "MEMBER_LINE_INVALID": ("MFP-4", "error"),
    "MEMBER_COUNT_MISMATCH": ("MFP-5", "error"),
    "MEMBER_EMPTY_UNEXPECTED": ("MFP-6", "error"),
    "MEMBERS_SMALL": ("MFP-3", "warning"),
}


def record_with(diagnostics, structural_errors=(), form="single-document"):
    """A complete result record that holds the given findings, as the command builds it."""
    record = validate._blank_record(b"{}")
    record["form"] = form
    record["execution_status"] = "complete"
    record["structural"] = "valid" if not structural_errors else "invalid"
    record["semantic"] = "run" if not structural_errors else "not-run"
    record["diagnostics"] = validate._diagnostics(diagnostics)
    record["structural_errors"] = list(structural_errors)
    return record


class FindingLocationTests(unittest.TestCase):
    def schema_errors(self, record):
        return sorted(Draft202012Validator(load(RESULT_SCHEMA)).iter_errors(record), key=str)

    def test_single_document_record_gains_only_form(self):
        record = validate.evaluate((EXAMPLES / "package-minimal.json").read_bytes(), DEFINITIONS)
        self.assertEqual(record["form"], "single-document")
        self.assertNotIn("member", json.dumps(record))
        self.assertEqual(
            sorted(record),
            sorted([
                "harness", "file", "form", "input_sha256", "bundle_manifest_sha256", "type", "spec_version",
                "execution_status", "structural", "semantic", "diagnostics", "structural_errors", "limitations",
            ]),
        )

    def test_single_document_findings_carry_no_location_keys(self):
        data = (RECORDS / "sentinel-strings.json").read_bytes()
        record = validate.evaluate(data, DEFINITIONS)
        self.assertTrue(record["diagnostics"])
        for d in record["diagnostics"]:
            self.assertEqual(sorted(d), ["code", "message", "path", "rule", "severity"])
        data = (RECORDS / "structural-asset-unknown-key.json").read_bytes()
        record = validate.evaluate(data, DEFINITIONS)
        self.assertTrue(record["structural_errors"])
        for error in record["structural_errors"]:
            self.assertEqual(sorted(error), ["keyword", "path"])

    def test_form_is_single_document_when_setup_fails(self):
        record = validate._blank_record(None)
        self.assertEqual(record["form"], "single-document")
        self.assertEqual(self.schema_errors(validate._setup_failed(record, "Setup failed: input file cannot be read.")), [])

    def test_member_location_renders_as_manifest_pointer(self):
        d = Diagnostic("ID_DUPLICATE", "ID-1", "error", "/id", "m", member=17, line=4)
        rendered = validate._diagnostics([d])[0]
        self.assertEqual(rendered["member"], "/manifest/members/17")
        self.assertEqual(rendered["line"], 4)
        self.assertNotIn("unlisted_path", rendered)

    def test_member_zero_and_member_without_line(self):
        d = Diagnostic("MEMBER_MISSING", "MFP-3", "error", "", "m", member=0)
        rendered = validate._diagnostics([d])[0]
        self.assertEqual(rendered["member"], "/manifest/members/0")
        self.assertNotIn("line", rendered)

    def test_unlisted_path_is_kept_in_the_record(self):
        d = Diagnostic("FILE_UNLISTED", "MFP-3", "warning", "", "m", unlisted_path="notes/readme.txt")
        rendered = validate._diagnostics([d])[0]
        self.assertEqual(rendered["unlisted_path"], "notes/readme.txt")
        self.assertNotIn("member", rendered)

    def test_diagnostics_sort_by_member_then_line_then_path_then_code(self):
        def make(code, path, member=None, line=None):
            return Diagnostic(code, "ID-1", "error", path, "m", member=member, line=line)

        shuffled = [
            make("ID_DUPLICATE", "/id", member=2, line=1),
            make("ID_DUPLICATE", "/b"),
            make("REFERENCE_UNRESOLVED", "/a", member=1, line=9),
            make("ID_DUPLICATE", "/id", member=1, line=9),
            make("ID_DUPLICATE", "/a", member=1, line=3),
            make("ID_DUPLICATE", "/a"),
        ]
        order = [(d.get("member"), d.get("line"), d["path"], d["code"]) for d in validate._diagnostics(shuffled)]
        self.assertEqual(
            order,
            [
                (None, None, "/a", "ID_DUPLICATE"),
                (None, None, "/b", "ID_DUPLICATE"),
                ("/manifest/members/1", 3, "/a", "ID_DUPLICATE"),
                ("/manifest/members/1", 9, "/a", "REFERENCE_UNRESOLVED"),
                ("/manifest/members/1", 9, "/id", "ID_DUPLICATE"),
                ("/manifest/members/2", 1, "/id", "ID_DUPLICATE"),
            ],
        )

    def test_member_numbers_sort_as_numbers(self):
        shuffled = [Diagnostic("ID_DUPLICATE", "ID-1", "error", "", "m", member=n, line=1) for n in (10, 9, 100, 2)]
        self.assertEqual(
            [d["member"] for d in validate._diagnostics(shuffled)],
            ["/manifest/members/%d" % n for n in (2, 9, 10, 100)],
        )

    def test_located_structural_errors_carry_member_and_line(self):
        rendered = validate._structural_records([
            ("/assets/0", "additionalProperties", 3, 12),
            ("/assets/0", "additionalProperties", 3, 12),
            ("", "required", 3, 2),
            ("/id", "type", None, None),
        ])
        self.assertEqual(
            rendered,
            [
                {"path": "/id", "keyword": "type"},
                {"path": "", "keyword": "required", "member": "/manifest/members/3", "line": 2},
                {"path": "/assets/0", "keyword": "additionalProperties", "member": "/manifest/members/3", "line": 12},
            ],
        )

    def test_structural_errors_without_locations_are_unchanged(self):
        class Fake:
            validator = "required"
            absolute_schema_path = ()
            absolute_path = ()

        self.assertEqual(validate._structural_errors([Fake(), Fake()]), [{"path": "", "keyword": "required"}])
        located = validate._structural_errors([Fake(), Fake()], [(5, 7), (5, 8)])
        self.assertEqual(
            located,
            [
                {"path": "", "keyword": "required", "member": "/manifest/members/5", "line": 7},
                {"path": "", "keyword": "required", "member": "/manifest/members/5", "line": 8},
            ],
        )

    def test_text_shows_member_and_line(self):
        d = Diagnostic("ID_DUPLICATE", "ID-1", "error", "/id", "m", member=17, line=4)
        text = validate._human(record_with([d], form="multi-file"), 1)
        self.assertIn("error ID_DUPLICATE member 17 line 4 /id: m\n", text)

    def test_text_shows_member_without_line(self):
        # A member finding with the empty path is about the whole member file: no "(root)".
        d = Diagnostic("MEMBER_LINE_INVALID", "MFP-4", "error", "", "m", member=3)
        text = validate._human(record_with([d], form="multi-file"), 1)
        self.assertIn("error MEMBER_LINE_INVALID member 3: m\n", text)
        d = Diagnostic("MEMBER_MISSING", "MFP-3", "error", "/manifest/members/3/path", "m", member=3)
        text = validate._human(record_with([d], form="multi-file"), 1)
        self.assertIn("error MEMBER_MISSING member 3 /manifest/members/3/path: m\n", text)

    def test_text_shows_root_for_an_empty_path_on_a_line(self):
        d = Diagnostic("INPUT_INVALID", "DOC-1", "error", "", "m", member=3, line=4)
        text = validate._human(record_with([d], form="multi-file"), 1)
        self.assertIn("error INPUT_INVALID member 3 line 4 (root): m\n", text)

    def test_text_for_a_finding_without_location_is_unchanged(self):
        d = Diagnostic("ID_DUPLICATE", "ID-1", "error", "/id", "m")
        text = validate._human(record_with([d]), 1)
        self.assertIn("error ID_DUPLICATE /id: m\n", text)

    def test_text_shows_located_structural_errors(self):
        errors = [{"path": "/id", "keyword": "type", "member": "/manifest/members/2", "line": 8}]
        text = validate._human(record_with([], errors, form="multi-file"), 1)
        self.assertIn("  member 2 line 8 /id keyword type\n", text)

    def test_text_output_never_prints_unlisted_path(self):
        d = Diagnostic("MEMBER_UNLISTED", "MFP-3", "error", "", "m", unlisted_path="assets/customer-x.jsonl")
        text = validate._human(record_with([d], form="multi-file"), 1)
        self.assertNotIn("customer-x", text)
        self.assertIn("error MEMBER_UNLISTED (unlisted file): m\n", text)

    def test_text_for_an_unlisted_file_warning(self):
        d = Diagnostic("FILE_UNLISTED", "MFP-3", "warning", "", "m", unlisted_path="notes/readme.txt")
        text = validate._human(record_with([d], form="multi-file"), 0)
        self.assertIn("warning FILE_UNLISTED (unlisted file): m\n", text)

    def test_unlisted_path_text_is_only_in_json(self):
        d = Diagnostic("FILE_UNLISTED", "MFP-3", "warning", "", "m", unlisted_path="ZZSENTINELZZ/zzsentinelzz.txt")
        record = record_with([d], form="multi-file")
        self.assertIn("ZZSENTINELZZ", json.dumps(record))
        text = validate._human(record, 0)
        for sentinel in SENTINELS:
            self.assertNotIn(sentinel, text)

    def test_member_file_is_named_only_by_its_manifest_position(self):
        d = Diagnostic("MEMBER_CHECKSUM_MISMATCH", "MFP-3", "error", "", "m", member=6)
        record = record_with([d], form="multi-file")
        self.assertEqual(record["diagnostics"][0]["member"], "/manifest/members/6")
        self.assertNotIn(".jsonl", json.dumps(record) + validate._human(record, 1))

    def test_result_schema_accepts_multi_file_locations(self):
        findings = [
            Diagnostic("ID_DUPLICATE", "ID-1", "error", "/id", "m", member=17, line=4),
            Diagnostic("MEMBER_MISSING", "MFP-3", "error", "", "m", member=0),
            Diagnostic("FILE_UNLISTED", "MFP-3", "warning", "", "m", unlisted_path="notes/readme.txt"),
            Diagnostic("MEMBERS_SMALL", "MFP-3", "warning", "/manifest/members", "m"),
        ]
        self.assertEqual(self.schema_errors(record_with(findings, form="multi-file")), [])
        errors = [{"path": "/id", "keyword": "type", "member": "/manifest/members/2", "line": 8}]
        self.assertEqual(self.schema_errors(record_with([], errors, form="multi-file")), [])
        self.assertEqual(self.schema_errors(record_with([])), [])

    def test_result_schema_rejects_bad_locations(self):
        good = Diagnostic("ID_DUPLICATE", "ID-1", "error", "/id", "m", member=1, line=1)
        record = record_with([good], form="multi-file")
        self.assertEqual(self.schema_errors(record), [])
        bad_changes = {
            "member not a pointer": ("member", "17"),
            "member with leading zero": ("member", "/manifest/members/01"),
            "member negative": ("member", "/manifest/members/-1"),
            "member as number": ("member", 17),
            "line zero": ("line", 0),
            "line as text": ("line", "4"),
            "line as float": ("line", 1.5),
            "unknown key": ("zone", "x"),
        }
        for name, (key, value) in bad_changes.items():
            with self.subTest(name):
                changed = json.loads(json.dumps(record))
                changed["diagnostics"][0][key] = value
                self.assertNotEqual(self.schema_errors(changed), [])
        for name, change in {"form missing": None, "form unknown": "archive"}.items():
            with self.subTest(name):
                changed = json.loads(json.dumps(record))
                if change is None:
                    del changed["form"]
                else:
                    changed["form"] = change
                self.assertNotEqual(self.schema_errors(changed), [])

    def test_result_schema_rejects_unlisted_path_on_a_structural_error(self):
        errors = [{"path": "", "keyword": "type", "unlisted_path": "a.txt"}]
        self.assertNotEqual(self.schema_errors(record_with([], errors, form="multi-file")), [])

    def test_result_schema_rejects_bad_structural_error_locations(self):
        for name, extra in {"member text": {"member": "x"}, "line zero": {"line": 0}}.items():
            with self.subTest(name):
                errors = [dict({"path": "", "keyword": "type"}, **extra)]
                self.assertNotEqual(self.schema_errors(record_with([], errors, form="multi-file")), [])


class MultiFileCatalogTests(unittest.TestCase):
    def test_multi_file_entries(self):
        for code, (rule, severity) in MULTI_FILE_CODES.items():
            with self.subTest(code):
                self.assertEqual(CATALOG[code][:2], (rule, severity))

    def test_only_the_two_size_and_listing_codes_are_warnings(self):
        warnings = {code for code, (_rule, severity, _message) in CATALOG.items() if severity == "warning"}
        self.assertEqual(warnings, {"FILE_UNLISTED", "MEMBERS_SMALL"})

    def test_messages_are_fixed_text_without_placeholders(self):
        for code in MULTI_FILE_CODES:
            message = CATALOG[code][2]
            with self.subTest(code):
                self.assertTrue(message.endswith("."))
                self.assertNotIn("\u2014", message)
                for mark in "{}%$<>":
                    self.assertNotIn(mark, message)

    def test_schema_enum_lists_the_new_codes(self):
        codes = load(RESULT_SCHEMA)["$defs"]["diagnostic"]["properties"]["code"]["enum"]
        self.assertLessEqual(set(MULTI_FILE_CODES), set(codes))


class SafePointerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(DEFINITIONS)

    def pairs(self, document):
        parsed = parse_input(json.dumps(document).encode("utf-8"))
        errors = self.bundle.entry_point(document["type"]).validate(parsed)
        return {(validate.safe_pointer(error), validate.schema_keyword(error)) for error in errors}

    def asset(self, **fields):
        """A minimal package that holds one asset with the given fields."""
        package = load(EXAMPLES / "package-minimal.json")
        package["assets"] = [dict({"id": "a-0001", "title": "Example Clip"}, **fields)]
        package["manifest"]["counts"]["assets"] = 1
        return package

    def test_control_package_is_valid(self):
        self.assertEqual(self.pairs(self.asset()), set())

    def test_unknown_key_ends_at_the_object(self):
        self.assertEqual(self.pairs(self.asset(ZZSENTINELZZ=1)), {("/assets/0", "unevaluatedProperties")})

    def test_nested_value_keeps_schema_named_steps(self):
        files = [
            {"id": "f-1", "locations": [{"storage_location": "sl-01", "path": "a.bin"}]},
            {
                "id": "f-2",
                "locations": [{"storage_location": "sl-01", "path": "b.bin"}],
                "checksum": {"algorithm": "md5", "value": "XYZ"},
            },
        ]
        pairs = self.pairs(self.asset(files=files))
        self.assertIn(("/assets/0/files/1/checksum/value", "pattern"), pairs)
        self.assertTrue(all(path == "/assets/0/files/1/checksum/value" for path, _ in pairs), pairs)

    def test_extension_namespace_key_is_cut(self):
        pairs = self.pairs(self.asset(extensions={"ZZSENTINELZZ": {"x": 1}, "oasis": {}}))
        self.assertTrue(pairs)
        for path, _ in pairs:
            self.assertNotIn("ZZSENTINELZZ", path)
            self.assertNotIn("oasis", path)
            self.assertTrue(path in ("/assets/0", "/assets/0/extensions"), pairs)

    def test_false_subschema_is_reported_as_false(self):
        from jsonschema.exceptions import ValidationError

        error = ValidationError("message", validator=None, path=[], schema_path=[])
        self.assertEqual(validate.schema_keyword(error), "false")
        error = ValidationError("message", validator="required", path=[], schema_path=[])
        self.assertEqual(validate.schema_keyword(error), "required")

    def test_hand_built_paths(self):
        from jsonschema.exceptions import ValidationError

        def error(schema_path, instance_path, validator="type"):
            e = ValidationError("message", validator=validator, path=instance_path, schema_path=schema_path)
            return validate.safe_pointer(e)

        self.assertEqual(error(["$ref", "properties", "a", "$ref", "type"], ["a"]), "/a")
        self.assertEqual(error(["properties", "a", "items", "anyOf", 1, "type"], ["a", 3]), "/a/3")
        self.assertEqual(error(["prefixItems", 0, "type"], [0]), "/0")
        self.assertEqual(error(["prefixItems", 0, "type"], [1]), "")
        self.assertEqual(error(["properties", "a", "additionalProperties", "type"], ["a", "secret"]), "/a")
        self.assertEqual(error(["unevaluatedProperties", "type"], ["secret"]), "")
        self.assertEqual(error(["propertyNames", "pattern"], []), "")
        self.assertEqual(error(["properties", "b", "type"], ["a"]), "")
        self.assertEqual(
            error(["allOf", 0, "if", "then", "properties", "a", "oneOf", 2, "not", "type"], ["a"]), "/a"
        )
        self.assertEqual(error(["dependentSchemas", "properties", "properties", "x", "type"], ["x"]), "/x")
        self.assertEqual(error(["$defs", "items", "properties", "x", "type"], ["x"]), "/x")
        self.assertEqual(error(["properties", "a~/b", "type"], ["a~/b"]), "/a~0~1b")
        self.assertEqual(error(["contains", "type"], [0]), "")


class CorpusAgreementTests(unittest.TestCase):
    def test_every_case_agrees_with_the_manifest(self):
        cases = [c for c in load_manifest() if not c.is_package]
        self.assertTrue(cases)
        for case in cases:
            with self.subTest(case.id):
                record = validate.evaluate((FIXTURES / case.path).read_bytes(), DEFINITIONS)
                self.assertEqual(record["execution_status"], case.expected_status)
                self.assertEqual(record["structural"], case.expected_structural)
                pairs = tuple((d["code"], d["path"]) for d in record["diagnostics"])
                self.assertEqual(pairs, case.expected_diagnostics)
                self.assertEqual(record["semantic"], "run" if case.expected_structural == "valid" else "not-run")
                for d in record["diagnostics"]:
                    self.assertEqual((d["rule"], d["severity"], d["message"]), CATALOG[d["code"]])
                clean = (
                    case.expected_status == "complete"
                    and case.expected_structural == "valid"
                    and all(CATALOG[code][1] != "error" for code, _ in case.expected_diagnostics)
                )
                self.assertEqual(validate.exit_code(record), 0 if clean else 1)


if __name__ == "__main__":
    unittest.main()
