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
        # No draft.3 code is a warning, but the result record keeps the severity.
        self.assertTrue(all(severity == "error" for _rule, severity, _message in CATALOG.values()))
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
        self.assertEqual((record["type"], record["spec_version"]), ("package", "2.0.0-draft.3"))

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
                self.assertEqual(code, {"complete": 0, "setup-failed": 2}.get(name, 1))

    def test_record_fields(self):
        data = (EXAMPLES / "package-minimal.json").read_bytes()
        record = validate.evaluate(data, DEFINITIONS)
        bundle = load_bundle(DEFINITIONS)
        self.assertEqual(
            record["harness"],
            {
                "id": "oasis-python-reference-harness",
                "version": "2.0.0-draft.3",
                "dependencies": ["jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4"],
            },
        )
        self.assertEqual(record["input_sha256"], parse_input(data).sha256)
        self.assertEqual(record["bundle_manifest_sha256"], bundle.manifest_sha256)
        self.assertEqual(record["type"], "package")
        self.assertEqual(record["spec_version"], "2.0.0-draft.3")
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
        self.assertEqual(len(codes), 54)
        self.assertEqual(schema["$defs"]["diagnostic"]["properties"]["severity"]["enum"], ["error", "warning"])
        self.assertEqual(schema["properties"]["harness"]["properties"]["version"]["const"], validate.HARNESS_VERSION)
        self.assertEqual(schema["properties"]["spec_version"]["enum"], ["2.0.0-draft.3", None])
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
        cases = load_manifest()
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
