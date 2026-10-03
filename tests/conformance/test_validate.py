"""Check the ``python3 -m tests.conformance.validate`` command.

Each test runs the command as a subprocess from the repository root, the way
an adopter runs it. Corpus records cover each outcome-table row and each exit
code. ``--json`` outcomes must match ``results.build_validate_result`` for
the same case. No output may echo an input value.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from tests.conformance import results
from tests.conformance.corpus import fixture_cases
from tests.conformance.test_examples import EXAMPLES

REPO = Path(__file__).resolve().parents[2]
FIXTURES = REPO / "tests" / "conformance" / "fixtures"
EXAMPLES_DIR = REPO / "definitions" / "examples"
CASES = {case.id: case for case in fixture_cases()}
REVISION = "0" * 40
SENTINEL = "SENTINEL-7b2f-do-not-echo"
REFERENCE_UNRESOLVED_MESSAGE = "A collection reference cannot resolve within explicit context."
FORGED_LINE = "PASS status=complete routing=selected structural=valid"


def run(*args):
    return subprocess.run(
        [sys.executable, "-m", "tests.conformance.validate", *args],
        cwd=REPO, capture_output=True, text=True, check=False,
    )


def case_args(case, *extra, root="definitions"):
    args = [str(FIXTURES / case.path), "--schema", case.schema_name, "--profile", case.profile, "--root", root]
    if case.reference_context != {"asset_ids": [], "collection_ids": []}:
        args += ["--context", json.dumps(case.reference_context)]
    return args + list(extra)


def run_case(case_id, *extra, root="definitions"):
    return run(*case_args(CASES[case_id], *extra, root=root))


def run_json(*args):
    completed = run(*args, "--json")
    return completed, json.loads(completed.stdout)


class ExitCodeTest(unittest.TestCase):
    def assertOutcome(self, case_id, exit_code, first_word, status):
        completed = run_case(case_id)
        self.assertEqual(completed.returncode, exit_code, completed.stdout + completed.stderr)
        first = completed.stdout.splitlines()[0]
        self.assertTrue(first.startswith(first_word + " "), first)
        self.assertIn(f"status={status}", first)
        return completed

    def test_legacy_valid_passes(self):
        completed = self.assertOutcome("minimal-asset", 0, "PASS", "complete")
        self.assertIn("structural=valid", completed.stdout)
        self.assertIn("routing=not-applied", completed.stdout)

    def test_legacy_invalid_fails_and_lists_schema_error_locations(self):
        completed = self.assertOutcome("missing-required-asset", 1, "FAIL", "complete")
        self.assertIn("structural=invalid", completed.stdout)
        self.assertRegex(completed.stdout, r"schema errors: [1-9]")
        self.assertIn("(root) keyword required", completed.stdout)

    def test_exchange_complete_with_warnings_passes(self):
        completed = self.assertOutcome("exchange-unresolved-parent", 0, "PASS", "complete")
        self.assertIn("routing=selected", completed.stdout)
        self.assertRegex(completed.stdout, r"(?m)^warning REFERENCE_UNRESOLVED /\S+: ")

    def test_exchange_semantic_error_is_blocked(self):
        completed = self.assertOutcome("exchange-negative-size", 1, "FAIL", "blocked")
        self.assertRegex(completed.stdout, r"(?m)^error SIZE_UNUSABLE /files/0/size: ")

    def test_exchange_structural_rejection_is_blocked(self):
        completed = self.assertOutcome("exchange-structural-rejection", 1, "FAIL", "blocked")
        self.assertIn("structural=invalid", completed.stdout)

    def test_unsupported_version_fails(self):
        completed = self.assertOutcome("exchange-unknown-version", 1, "FAIL", "unsupported")
        self.assertRegex(completed.stdout, r"(?m)^error VERSION_UNSUPPORTED /schema_version: ")

    def test_excluded_report_entry_point_fails(self):
        completed = self.assertOutcome("exchange-report-excluded", 1, "FAIL", "unsupported")
        self.assertRegex(completed.stdout, r"(?m)^error PROFILE_UNSUPPORTED \(root\): ")
        self.assertNotIn("VERSION_UNSUPPORTED", completed.stdout)

    def test_input_invalid_fails(self):
        completed = self.assertOutcome("exchange-input-duplicate-members", 1, "FAIL", "input-invalid")
        self.assertRegex(completed.stdout, r"(?m)^error INPUT_INVALID \(root\): ")
        self.assertIn("structural=not-run", completed.stdout)

    def test_context_resolves_membership(self):
        self.assertOutcome("exchange-membership-resolved", 0, "PASS", "complete")

    def test_legacy_historical_unchecked_ignores_date_time(self):
        completed = run_case("asset-invalid-date", "--format-mode", "historical-unchecked")
        self.assertEqual(completed.returncode, 0, completed.stdout)
        self.assertTrue(completed.stdout.startswith("PASS "))

    def test_baseline_root(self):
        completed = run_case("minimal-asset", root="baseline")
        self.assertEqual(completed.returncode, 0, completed.stdout)


class SetupFailureTest(unittest.TestCase):
    def assertSetupFailed(self, *args):
        completed = run(*args)
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        self.assertTrue(completed.stdout.startswith("ERROR status=setup-failed"), completed.stdout)
        self.assertIn("Setup failed", completed.stdout)
        return completed

    def test_unknown_profile(self):
        self.assertSetupFailed(str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json", "--profile", "other-1x")

    def test_unknown_profile_outranks_invalid_input(self):
        path = str(FIXTURES / CASES["exchange-input-nan-number"].path)
        self.assertSetupFailed(path, "--schema", "asset.schema.json", "--profile", "other-1x")

    def test_exchange_with_historical_unchecked(self):
        self.assertSetupFailed(
            str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json",
            "--format-mode", "historical-unchecked",
        )

    def test_malformed_context_outranks_invalid_input(self):
        path = str(FIXTURES / CASES["exchange-input-nan-number"].path)
        self.assertSetupFailed(path, "--schema", "asset.schema.json", "--context", '{"asset_ids": []}')

    def test_context_that_is_not_json(self):
        self.assertSetupFailed(str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json", "--context", "{")

    def test_unknown_schema_name(self):
        self.assertSetupFailed(str(EXAMPLES_DIR / "asset.json"), "--schema", "nothing.schema.json")

    def test_numeric_resource_refusal(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "big.json"
            path.write_text('{"asset_id": "a", "title": "t", "type": "video", "size": ' + "9" * 2000 + "}")
            completed = run(str(path), "--schema", "asset.schema.json")
        self.assertEqual(completed.returncode, 2, completed.stdout)
        self.assertTrue(completed.stdout.startswith("ERROR status=setup-failed"), completed.stdout)
        self.assertIn("Numeric resource guards refused the input", completed.stdout)
        self.assertNotIn("9" * 50, completed.stdout)


class ArgumentErrorTest(unittest.TestCase):
    def assertUnreadable(self, path):
        completed = run(path, "--schema", "asset.schema.json")
        self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
        lines = completed.stdout.splitlines()
        self.assertEqual(lines[0], "ERROR status=setup-failed routing=not-applied structural=not-run")
        self.assertIn("note: Setup failed: input file cannot be read.", lines)
        completed, record = run_json(path, "--schema", "asset.schema.json")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertIsNone(record["input_sha256"])
        self.assertEqual(record["limitations"], ["Setup failed: input file cannot be read."])

    def test_missing_input_file(self):
        self.assertUnreadable("tmp/does-not-exist.json")

    def test_directory_as_input(self):
        self.assertUnreadable(str(EXAMPLES_DIR))

    def test_missing_schema_argument_is_a_usage_error(self):
        completed = run(str(EXAMPLES_DIR / "asset.json"))
        self.assertEqual(completed.returncode, 2)
        self.assertIn("usage:", completed.stderr)
        self.assertEqual(completed.stdout, "")

    def test_unknown_root_is_a_usage_error(self):
        completed = run(str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json", "--root", "current")
        self.assertEqual(completed.returncode, 2)
        self.assertIn("usage:", completed.stderr)
        self.assertEqual(completed.stdout, "")


class ContextDecodingTest(unittest.TestCase):
    DEEP = "[" * 10000 + "]" * 10000

    def test_legacy_ignores_context(self):
        for context in (self.DEEP, "{", '{"asset_ids": []}'):
            with self.subTest(context=context[:10]):
                completed = run_case("minimal-asset", "--context", context)
                self.assertEqual(completed.returncode, 0, completed.stdout + completed.stderr)
                self.assertTrue(completed.stdout.startswith("PASS "))

    def test_exchange_deep_context_is_a_setup_failure(self):
        for extra in ((), ("--json",)):
            with self.subTest(json=bool(extra)):
                completed = run(str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json",
                                "--context", self.DEEP, *extra)
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                expected = "Setup failed: reference context cannot be decoded as JSON."
                if extra:
                    self.assertEqual(json.loads(completed.stdout)["limitations"], [expected])
                else:
                    self.assertIn("note: " + expected, completed.stdout.splitlines())


class ExampleTest(unittest.TestCase):
    def test_all_seven_examples_pass(self):
        self.assertEqual(len(EXAMPLES), 7)
        for name, (schema, expected) in EXAMPLES.items():
            with self.subTest(example=name):
                completed, record = run_json(str(EXAMPLES_DIR / name), "--schema", schema)
                self.assertEqual(completed.returncode, 0, completed.stdout)
                self.assertEqual(record["execution_status"], "complete")
                self.assertEqual(
                    sorted((d["code"], d["path"]) for d in record["diagnostics"]), sorted(expected)
                )

    def test_human_output_for_an_example(self):
        completed = run(str(EXAMPLES_DIR / "collection.json"), "--schema", "collection.schema.json")
        lines = completed.stdout.splitlines()
        self.assertEqual(lines[0], "PASS status=complete routing=selected structural=valid")
        self.assertEqual(lines[1:], [
            "warning REFERENCE_UNRESOLVED /assets/0: " + REFERENCE_UNRESOLVED_MESSAGE,
            "warning REFERENCE_UNRESOLVED /assets/1: " + REFERENCE_UNRESOLVED_MESSAGE,
        ])


class JsonOutputTest(unittest.TestCase):
    COMPARED = (
        "minimal-asset", "missing-required-asset", "exchange-unresolved-parent",
        "exchange-negative-size", "exchange-structural-rejection", "exchange-unknown-version",
        "exchange-report-excluded", "exchange-input-duplicate-members", "exchange-membership-resolved",
        "exchange-lexical-diagnostic-order",
    )

    def test_json_matches_result_builder(self):
        for case_id in self.COMPARED:
            case = CASES[case_id]
            with self.subTest(case=case_id):
                _, record = run_json(*case_args(case))
                expected = results.build_validate_result(
                    case, format_mode="required", root="current", source_revision=REVISION
                )
                for key in ("routing", "structural", "execution_status", "diagnostics", "profile", "format_mode"):
                    self.assertEqual(record[key], expected[key], key)
                self.assertEqual(record["schema"], expected["schema_name"])
                self.assertEqual(record["input_sha256"], expected["reproduction"]["input_sha256"])
                self.assertEqual(record["artifact_sha256"], expected["reproduction"]["artifact_sha256"])

    def test_json_fields(self):
        case = CASES["missing-required-asset"]
        completed, record = run_json(*case_args(case))
        self.assertEqual(completed.returncode, 1)
        self.assertEqual(record["file"], str(FIXTURES / case.path))
        self.assertEqual(record["root"], "definitions")
        self.assertTrue(record["structural_errors"])
        for error in record["structural_errors"]:
            self.assertEqual(set(error), {"path", "keyword"})
        self.assertEqual(set(record), {
            "file", "schema", "profile", "format_mode", "root", "routing", "structural",
            "execution_status", "diagnostics", "input_sha256", "artifact_sha256",
            "structural_errors", "limitations",
        })

    def test_json_setup_failure(self):
        completed, record = run_json(str(EXAMPLES_DIR / "asset.json"), "--schema", "asset.schema.json", "--profile", "x")
        self.assertEqual(completed.returncode, 2)
        self.assertEqual(record["execution_status"], "setup-failed")
        self.assertEqual(record["structural"], "not-run")


class NoEchoTest(unittest.TestCase):
    RECORDS = {
        "date": {"asset_id": "asset-a", "title": "t", "type": "video", "created_date": SENTINEL},
        "version": {"asset_id": "asset-a", "title": "t", "type": "video", "schema_version": SENTINEL},
        "type": {"asset_id": "asset-a", "title": "t", "type": SENTINEL, "files": [{"size": SENTINEL}]},
        "identity": {"asset_id": " ", "title": SENTINEL, "type": "video"},
    }

    def run_record(self, schema, record, profile="legacy-1x", *extra):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "record.json"
            path.write_text(json.dumps(record))
            return run(str(path), "--schema", schema, "--profile", profile, *extra)

    def report(self, **changes):
        record = json.loads((FIXTURES / CASES["minimal-migration-report-output"].path).read_text())
        for key, value in changes.items():
            record[key] = value
        return record

    def assertNoEcho(self, schema, record, profile="legacy-1x"):
        outputs = []
        for extra in ((), ("--json",)):
            completed = self.run_record(schema, record, profile, *extra)
            self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
            self.assertNotIn(SENTINEL, completed.stdout + completed.stderr)
            outputs.append(completed.stdout)
        return outputs

    def test_author_key_is_not_echoed_in_schema_error_paths(self):
        summary = dict(self.report()["asset_summary"], asset_types={SENTINEL: "many"})
        text, raw = self.assertNoEcho("migration-report-output.schema.json", self.report(asset_summary=summary))
        self.assertIn("  /asset_summary/asset_types keyword type", text)
        self.assertEqual(
            json.loads(raw)["structural_errors"], [{"path": "/asset_summary/asset_types", "keyword": "type"}]
        )

    def test_newline_key_cannot_forge_a_status_line(self):
        key = SENTINEL + "\n" + FORGED_LINE
        summary = dict(self.report()["asset_summary"], asset_types={key: "many"})
        text, _ = self.assertNoEcho("migration-report-output.schema.json", self.report(asset_summary=summary))
        lines = text.splitlines()
        self.assertTrue(lines[0].startswith("FAIL "))
        self.assertNotIn(FORGED_LINE, lines)
        self.assertEqual([line for line in lines if line.startswith(("PASS", "FAIL", "ERROR"))], [lines[0]])

    def test_enum_failure_is_not_echoed(self):
        record = {"source_id": "annotation-a", "start_seconds": 2, "annotation_type": SENTINEL}
        text, _ = self.assertNoEcho("temporal_annotation.schema.json", record, "exchange-1x")
        self.assertIn("  /annotation_type keyword enum", text)

    def test_pattern_failure_is_not_echoed(self):
        text, _ = self.assertNoEcho("migration-report-output.schema.json", self.report(report_id=SENTINEL))
        self.assertIn("  /report_id keyword pattern", text)

    def test_no_input_value_in_output(self):
        with tempfile.TemporaryDirectory() as directory:
            for label, record in self.RECORDS.items():
                path = Path(directory) / f"{label}.json"
                path.write_text(json.dumps(record))
                for profile in ("exchange-1x", "legacy-1x"):
                    for extra in ((), ("--json",)):
                        with self.subTest(record=label, profile=profile, json=bool(extra)):
                            completed = run(str(path), "--schema", "asset.schema.json", "--profile", profile, *extra)
                            self.assertIn(completed.returncode, (0, 1))
                            self.assertNotIn(SENTINEL, completed.stdout + completed.stderr)


class SafePointerTest(unittest.TestCase):
    """Schema error paths keep only schema-named properties and array indexes."""

    SCHEMA = {
        "definitions": {"leaf": {"type": "integer"}},
        "type": "object",
        "properties": {
            "named": {"type": "array", "items": {"$ref": "#/definitions/leaf"}},
            "tuple": {"type": "array", "items": [{"type": "integer"}], "additionalItems": {"type": "integer"}},
            "pattern": {"type": "object", "patternProperties": {"^x_": {"type": "integer"}}},
            "extra": {"type": "object", "additionalProperties": {"properties": {"inner": {"type": "integer"}}}},
            "closed": {"type": "object", "additionalProperties": False},
            "choice": {"anyOf": [{"type": "integer"}, {"type": "object", "properties": {"a": {"type": "integer"}}}]},
            "all": {"allOf": [{"properties": {"a": {"type": "integer"}}}]},
        },
    }

    def paths(self, document):
        from jsonschema import Draft7Validator
        from tests.conformance.validate import safe_pointer
        return sorted(safe_pointer(error) for error in Draft7Validator(self.SCHEMA).iter_errors(document))

    def test_named_properties_and_indexes_are_kept(self):
        self.assertEqual(self.paths({"named": [1, "a"]}), ["/named/1"])
        self.assertEqual(self.paths({"tuple": ["a", 1, "b"]}), ["/tuple/0", "/tuple/2"])
        self.assertEqual(self.paths({"all": {"a": "s"}}), ["/all/a"])

    def test_author_keys_are_cut(self):
        self.assertEqual(self.paths({"pattern": {"x_" + SENTINEL: "s"}}), ["/pattern"])
        self.assertEqual(self.paths({"extra": {SENTINEL: {"inner": "s"}}}), ["/extra"])
        self.assertEqual(self.paths({"closed": {SENTINEL: 1}}), ["/closed"])

    def test_any_of_branch_path(self):
        self.assertEqual(self.paths({"choice": "s"}), ["/choice"])


class MissingPackageTest(unittest.TestCase):
    """Shadow a pinned package with one whose import fails in a chosen way."""

    def run_shadowed(self, package, body, *extra):
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory) / package).mkdir()
            (Path(directory) / package / "__init__.py").write_text(body)
            return subprocess.run(
                [sys.executable, "-m", "tests.conformance.validate", str(EXAMPLES_DIR / "asset.json"),
                 "--schema", "asset.schema.json", *extra],
                cwd=REPO, capture_output=True, text=True, check=False,
                env=dict(os.environ, PYTHONPATH=directory),
            )

    def test_missing_package_is_a_setup_error(self):
        for package in ("jsonschema", "referencing"):
            body = f"raise ModuleNotFoundError('No module named ' + {package!r}, name={package!r})\n"
            for extra in ((), ("--json",)):
                with self.subTest(package=package, json=bool(extra)):
                    completed = self.run_shadowed(package, body, *extra)
                    self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)
                    if extra:
                        self.assertEqual(json.loads(completed.stdout)["execution_status"], "setup-failed")
                    else:
                        self.assertTrue(completed.stdout.startswith("ERROR status=setup-failed"))
                        self.assertIn("package", completed.stdout)

    def test_missing_transitive_dependency_is_a_setup_error(self):
        for package in ("attrs", "rpds", "jsonschema_specifications"):
            body = f"raise ModuleNotFoundError('No module named ' + {package!r}, name={package!r})\n"
            for extra in ((), ("--json",)):
                with self.subTest(package=package, json=bool(extra)):
                    completed = self.run_shadowed(package, body, *extra)
                    self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                    self.assertNotIn("Traceback", completed.stderr)
                    if extra:
                        self.assertEqual(json.loads(completed.stdout)["execution_status"], "setup-failed")
                    else:
                        self.assertTrue(completed.stdout.startswith("ERROR status=setup-failed"))

    def test_guarded_names_cover_the_lock_file(self):
        from tests.conformance.validate import LOCKED_IMPORT_NAMES
        lock = (REPO / "tests" / "conformance" / "requirements-lock.txt").read_text()
        names = {
            line.split("==")[0].strip().lower() for line in lock.splitlines()
            if "==" in line and not line.lstrip().startswith(("#", "--"))
        }
        imports = {{"rpds-py": "rpds"}.get(name, name.replace("-", "_")) for name in names}
        self.assertEqual(set(LOCKED_IMPORT_NAMES), imports)

    def test_low_integer_digit_limit_is_a_setup_error(self):
        env = dict(os.environ, PYTHONINTMAXSTRDIGITS="640")
        for extra in ((), ("--json",)):
            with self.subTest(json=bool(extra)):
                completed = subprocess.run(
                    [sys.executable, "-m", "tests.conformance.validate", str(EXAMPLES_DIR / "asset.json"),
                     "--schema", "asset.schema.json", *extra],
                    cwd=REPO, capture_output=True, text=True, check=False, env=env,
                )
                self.assertEqual(completed.returncode, 2, completed.stdout + completed.stderr)
                self.assertNotIn("Traceback", completed.stderr)
                if extra:
                    record = json.loads(completed.stdout)
                    self.assertEqual(record["execution_status"], "setup-failed")
                    self.assertIn("get_int_max_str_digits", record["limitations"][0])
                else:
                    self.assertTrue(completed.stdout.startswith("ERROR status=setup-failed"))
                    self.assertIn("get_int_max_str_digits", completed.stdout)

    def test_other_import_errors_surface(self):
        bodies = {
            "broken package": "raise ImportError('broken package')\n",
            "missing unrelated module": "raise ModuleNotFoundError('No module named x', name='not_a_pinned_package')\n",
        }
        for label, body in bodies.items():
            with self.subTest(case=label):
                completed = self.run_shadowed("jsonschema", body)
                self.assertNotEqual(completed.returncode, 2)
                self.assertIn("Traceback", completed.stderr)
                self.assertEqual(completed.stdout, "")

if __name__ == "__main__":
    unittest.main()
