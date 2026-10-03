"""Result protocol schema, result builder, and profile pass-through tests."""

import copy
import dataclasses
import hashlib
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from jsonschema import Draft7Validator

from tests.conformance import corpus, loader, results
from tests.conformance.strict_json import parse_input, parse_schema_bytes
from tests.conformance.types import Diagnostic, InputInvalid, NumericResourceRefused, SetupFailed

REPO = Path(__file__).resolve().parents[2]
HERE = REPO / "tests" / "conformance"
FIXTURES = HERE / "fixtures"
REVISION = "0123456789abcdef0123456789abcdef01234567"
CASES = {case.id: case for case in corpus.fixture_cases()}


def build(case_id, *, format_mode="required", root="current", checker=None):
    kwargs = {} if checker is None else {"checker": checker}
    return results.build_validate_result(
        CASES[case_id], format_mode=format_mode, root=root, source_revision=REVISION, **kwargs
    )


def never_called(*_args, **_kwargs):
    raise AssertionError("profile checker must not run for this case")


class SpyChecker:
    """Record each call and return a fixed selected outcome."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.calls = []

    def __call__(self, case, document, structural):
        self.calls.append((case.id, case.profile, document.sha256, structural))
        return self.outcome


class ResultSchemaTest(unittest.TestCase):
    def test_schema_is_draft7_and_offline(self):
        schema = parse_schema_bytes((HERE / "result.schema.json").read_bytes())
        self.assertEqual(schema["$schema"], "http://json-schema.org/draft-07/schema#")
        Draft7Validator.check_schema(schema)
        self.assertNotIn("$ref", json.dumps(schema))

    def test_every_object_rejects_undeclared_fields(self):
        schema = parse_schema_bytes((HERE / "result.schema.json").read_bytes())
        found = []

        def walk(node):
            if isinstance(node, dict):
                if node.get("type") == "object":
                    found.append(node)
                    self.assertIs(node.get("additionalProperties"), False)
                    self.assertEqual(set(node["required"]), set(node["properties"]))
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for value in node:
                    walk(value)

        walk(schema)
        self.assertEqual(len(found), 5)

    def test_code_enum_is_the_catalog(self):
        schema = parse_schema_bytes((HERE / "result.schema.json").read_bytes())
        codes = schema["properties"]["diagnostics"]["items"]["properties"]["code"]["enum"]
        self.assertEqual(set(codes), set(corpus.DIAGNOSTIC_SEVERITY))


class SampleResultTest(unittest.TestCase):
    def assertValidResult(self, result):
        self.assertEqual(results.result_problems(result), [])

    def test_valid_fixture(self):
        result = build("minimal-asset")
        self.assertValidResult(result)
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "valid", "complete"),
        )
        self.assertEqual(result["diagnostics"], [])
        self.assertEqual(result["preservation"], {"status": "not-tested", "paths": []})
        self.assertIsNone(result["output"])
        self.assertEqual(result["direction"], "validate")
        self.assertEqual(result["protocol_version"], "1.0.0")

    def test_implementation_and_reproduction_fields(self):
        result = build("minimal-asset")
        self.assertEqual(result["implementation"], {
            "id": "oasis-python-reference-harness",
            "version": "0.1.0-draft",
            "source_revision": REVISION,
            "authors": ["OASIS conformance harness contributors"],
            "dependencies": ["jsonschema==4.26.0", "referencing==0.37.0", "rfc3339-validator==0.1.4"],
            "independence_claim": False,
        })
        data = (FIXTURES / "records" / "minimal-asset.json").read_bytes()
        manifest = (REPO / "definitions" / "bundle-manifest.json").read_bytes()
        repro = result["reproduction"]
        self.assertEqual(repro["input_sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(repro["artifact_sha256"], hashlib.sha256(manifest).hexdigest())
        self.assertEqual(
            repro["command"],
            "python3 -m tests.conformance.results --fixture minimal-asset --format-mode required --root current",
        )
        self.assertEqual(result["schema_revision"], "1.2.0-draft.1")
        self.assertEqual(build("minimal-asset", root="baseline")["schema_revision"], "v1.1.1-1e2849b287bb")

    def test_baseline_root_uses_its_own_manifest_digest(self):
        result = build("minimal-asset", root="baseline")
        manifest = (HERE / "baseline" / "bundle-manifest.json").read_bytes()
        self.assertEqual(result["reproduction"]["artifact_sha256"], hashlib.sha256(manifest).hexdigest())

    def test_dependencies_match_requirements(self):
        pins = (HERE / "requirements.txt").read_text().split()
        self.assertEqual(list(results.DEPENDENCIES), pins)

    def test_invalid_fixture(self):
        result = build("missing-required-asset")
        self.assertValidResult(result)
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "invalid", "complete"),
        )
        self.assertEqual(result["diagnostics"], [])

    def test_input_invalid_fixture(self):
        result = build("exchange-input-duplicate-members", checker=never_called)
        self.assertValidResult(result)
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "not-run", "input-invalid"),
        )
        self.assertEqual(len(result["diagnostics"]), 1)
        diagnostic = result["diagnostics"][0]
        self.assertEqual((diagnostic["code"], diagnostic["path"], diagnostic["severity"]),
                         ("INPUT_INVALID", "", "error"))

    def test_numeric_refusal_is_setup_failed_with_all_limits(self):
        result = build("exchange-numeric-resource-large-integer", checker=never_called)
        self.assertValidResult(result)
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "not-run", "setup-failed"),
        )
        self.assertEqual(result["diagnostics"], [])
        text = " ".join(result["reproduction"]["limitations"])
        for limit in ("1,024", "10,000", "100,000"):
            self.assertIn(limit, text)
        self.assertIn("Exceeded limit: numeric token length", text)
        self.assertNotIn("99999999", results.dump_result(result).decode("utf-8"))

    def test_loader_setup_failure(self):
        with mock.patch.object(loader, "load_bundle", side_effect=SetupFailed("schema digest does not match file bytes")):
            result = build("minimal-asset")
        self.assertValidResult(result)
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "not-run", "setup-failed"),
        )
        self.assertEqual(result["diagnostics"], [])
        self.assertTrue(result["reproduction"]["limitations"])

    def test_exchange_historical_mode_fails_setup(self):
        result = build("exchange-minimal-asset", format_mode="historical-unchecked", checker=never_called)
        self.assertValidResult(result)
        self.assertEqual(result["execution_status"], "setup-failed")
        self.assertEqual(result["structural"], "not-run")

    def test_unknown_profile_fails_setup(self):
        case = dataclasses.replace(CASES["minimal-asset"], profile="nope-9x")
        result = results.build_validate_result(
            case, format_mode="required", root="current", source_revision=REVISION, checker=never_called
        )
        self.assertValidResult(result)
        self.assertEqual(result["execution_status"], "setup-failed")
        self.assertEqual(result["profile"], "nope-9x")

    def test_historical_mode_is_labelled(self):
        result = build("minimal-asset", format_mode="historical-unchecked")
        self.assertValidResult(result)
        self.assertEqual(result["format_mode"], "historical-unchecked")
        self.assertTrue(result["reproduction"]["limitations"])

    def test_default_checker_runs_the_exchange_profile(self):
        result = build("exchange-minimal-asset")
        self.assertValidResult(result)
        self.assertEqual((result["routing"], result["execution_status"]), ("selected", "complete"))

    def test_bad_arguments_are_refused(self):
        with self.assertRaises(ValueError):
            build("minimal-asset", format_mode="lenient")
        with self.assertRaises(ValueError):
            build("minimal-asset", root="elsewhere")
        with self.assertRaises(ValueError):
            results.build_validate_result(
                CASES["minimal-asset"], format_mode="required", root="current", source_revision="HEAD"
            )

    def test_legacy_corpus_sweep_matches_expectations(self):
        mismatches = []
        for case in CASES.values():
            if case.profile != "legacy-1x":
                continue
            expected = case.validator_expectations["python-jsonschema"]
            for root in ("baseline", "current"):
                for mode in ("required", "historical-unchecked"):
                    if expected[mode] is None:
                        continue
                    result = build(case.id, format_mode=mode, root=root, checker=never_called)
                    want = "valid" if expected[mode] else "invalid"
                    problems = results.result_problems(result)
                    if result["structural"] != want or problems:
                        mismatches.append(f"{case.id} {root} {mode} {result['structural']} {problems}")
        self.assertEqual(mismatches, [])

    def test_no_validation_message_is_copied(self):
        result = build("missing-required-asset")
        self.assertNotIn("is a required property", results.dump_result(result).decode("utf-8"))


def raising(error):
    """A profile checker that raises error after structural evaluation."""
    def checker(case, document, structural):
        raise error
    return checker


class FailureResetTest(unittest.TestCase):
    """Every failure handler resets the outcome fields, and results are checked."""

    NUMERIC_INPUT_TEXT = "refused the input"

    def assert_not_run(self, result, status):
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"]),
            ("not-applied", "not-run", status),
        )

    def temp_dir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def test_deeply_nested_input_is_setup_failed(self):
        case = CASES["minimal-asset"]
        for depth in (100000, 1200):
            with self.subTest(depth=depth):
                fixtures = self.temp_dir()
                target = fixtures / case.path
                target.parent.mkdir(parents=True)
                target.write_bytes(b"[" * depth + b"]" * depth)
                with mock.patch.object(results, "FIXTURES", fixtures):
                    result = build("minimal-asset")
                self.assert_not_run(result, "setup-failed")
                self.assertEqual(result["diagnostics"], [])
                self.assertEqual(
                    result["reproduction"]["limitations"],
                    ["Setup failed: input nesting exceeds the Python interpreter recursion limit."],
                )

    def test_input_invalid_after_structural_resets_outcome(self):
        result = build("exchange-minimal-asset", checker=raising(InputInvalid("late input failure")))
        self.assert_not_run(result, "input-invalid")
        self.assertEqual([(d["code"], d["path"]) for d in result["diagnostics"]], [("INPUT_INVALID", "")])

    def test_numeric_refusal_after_structural_resets_outcome(self):
        error = NumericResourceRefused("numeric token length exceeds 1024 bytes")
        result = build("exchange-minimal-asset", checker=raising(error))
        self.assert_not_run(result, "setup-failed")
        self.assertEqual(result["diagnostics"], [])
        limitations = result["reproduction"]["limitations"]
        self.assertEqual(limitations, ["Setup failed: numeric token length exceeds 1024 bytes."])

    def test_bundle_numeric_refusal_is_not_described_as_input_refusal(self):
        root = self.temp_dir()
        data = b'{"maximum": 1e10001}\n'
        (root / "asset.schema.json").write_bytes(data)
        manifest = {"manifest_version": "1.0.0", "bundle_revision": "test-1", "schemas": [{
            "name": "asset.schema.json", "path": "asset.schema.json",
            "sha256": hashlib.sha256(data).hexdigest(), "id": None,
            "base_uri": "https://schemas.oasis.invalid/bundles/test-1/asset.schema.json", "aliases": [],
        }]}
        (root / "bundle-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        with mock.patch.dict(results.ROOTS, {"current": root}):
            result = build("minimal-asset", checker=never_called)
        self.assert_not_run(result, "setup-failed")
        limitations = result["reproduction"]["limitations"]
        self.assertEqual(limitations, ["Setup failed: absolute decimal exponent exceeds 10000."])
        self.assertNotIn(self.NUMERIC_INPUT_TEXT, " ".join(limitations))

    def test_builder_checks_the_result_before_returning(self):
        for outcome in (
            results.ProfileOutcome(routing="applied", execution_status="complete"),
            results.ProfileOutcome(
                routing="selected", execution_status="complete",
                diagnostics=(Diagnostic("COMPLETENESS_UNVERIFIED", "", "error", "m"),),
            ),
        ):
            with self.subTest(outcome=outcome):
                with self.assertRaises(results.ResultInvalid):
                    build("exchange-minimal-asset", checker=lambda case, document, structural: outcome)


class ReviewRegressionTest(unittest.TestCase):
    """Regressions for setup precedence and artifact identity."""

    def temp_dir(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        return Path(tmp.name)

    def write_bundle(self, root, schema_text, revision):
        data = schema_text.encode("utf-8")
        (root / "asset.schema.json").write_bytes(data)
        manifest = {"manifest_version": "1.0.0", "bundle_revision": revision, "schemas": [{
            "name": "asset.schema.json", "path": "asset.schema.json",
            "sha256": hashlib.sha256(data).hexdigest(), "id": None,
            "base_uri": "https://schemas.oasis.invalid/bundles/test/asset.schema.json", "aliases": [],
        }]}
        raw = json.dumps(manifest).encode("utf-8")
        (root / "bundle-manifest.json").write_bytes(raw)
        return hashlib.sha256(raw).hexdigest()

    def test_deep_derivative_nesting_is_setup_failed(self):
        case = CASES["minimal-asset"]
        fixtures = self.temp_dir()
        target = fixtures / case.path
        target.parent.mkdir(parents=True)
        text = '{"type": "video", "role": "SECRETROLE", "uri": "u"}'
        for _ in range(200):
            text = '{"type": "video", "role": "SECRETROLE", "uri": "u", "derivatives": [%s]}' % text
        target.write_text('{"asset_id": "a", "title": "t", "type": "video", "files": [%s]}' % text, encoding="utf-8")
        with mock.patch.object(results, "FIXTURES", fixtures):
            result = build("minimal-asset")
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"], result["diagnostics"]),
            ("not-applied", "not-run", "setup-failed", []),
        )
        self.assertEqual(
            result["reproduction"]["limitations"],
            ["Setup failed: validation nesting exceeds the Python interpreter recursion limit."],
        )
        self.assertNotIn("SECRETROLE", results.dump_result(result).decode("utf-8"))

    def test_unknown_entry_point_outranks_malformed_input(self):
        case = dataclasses.replace(CASES["exchange-input-duplicate-members"], schema_name="nope.schema.json")
        result = results.build_validate_result(
            case, format_mode="required", root="current", source_revision=REVISION, checker=never_called
        )
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"], result["diagnostics"]),
            ("not-applied", "not-run", "setup-failed", []),
        )
        self.assertEqual(result["reproduction"]["limitations"], ["Setup failed: schema name is not in the bundle manifest."])

    def test_invalid_draft7_schema_is_setup_failed(self):
        root = self.temp_dir()
        self.write_bundle(root, '{"$schema": "http://json-schema.org/draft-07/schema#", "type": 5}\n', "test-1")
        with mock.patch.dict(results.ROOTS, {"current": root}):
            result = build("minimal-asset")
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual(result["execution_status"], "setup-failed")
        self.assertEqual(
            result["reproduction"]["limitations"], ["Setup failed: schema does not conform to the Draft 7 metaschema."]
        )

    def test_artifact_digest_and_outcome_follow_the_same_manifest(self):
        root = self.temp_dir()
        first = self.write_bundle(root, '{"type": "object"}\n', "test-1")
        with mock.patch.dict(results.ROOTS, {"current": root}):
            before = build("minimal-asset")
            second = self.write_bundle(root, '{"type": "string"}\n', "test-2")
            after = build("minimal-asset")
        self.assertNotEqual(first, second)
        self.assertEqual(
            (before["reproduction"]["artifact_sha256"], before["schema_revision"], before["structural"]),
            (first, "test-1", "valid"),
        )
        self.assertEqual(
            (after["reproduction"]["artifact_sha256"], after["schema_revision"], after["structural"]),
            (second, "test-2", "invalid"),
        )


class MalformedResultTest(unittest.TestCase):
    def setUp(self):
        self.good = build("minimal-asset")
        self.assertEqual(results.result_problems(self.good), [])

    def assertRejected(self, mutate):
        result = copy.deepcopy(self.good)
        mutate(result)
        self.assertNotEqual(results.result_problems(result), [])
        with self.assertRaises(results.ResultInvalid):
            results.check_result(result)

    def test_unknown_top_level_field(self):
        self.assertRejected(lambda r: r.update(extra=1))

    def test_unknown_nested_fields(self):
        self.assertRejected(lambda r: r["implementation"].update(extra=1))
        self.assertRejected(lambda r: r["reproduction"].update(extra=1))
        self.assertRejected(lambda r: r["preservation"].update(extra=1))

    def test_unknown_diagnostic_field(self):
        def mutate(r):
            r["diagnostics"] = [{"code": "INPUT_INVALID", "path": "", "severity": "error", "message": "m", "x": 1}]
        self.assertRejected(mutate)

    def test_bad_digests(self):
        for bad in ("A" * 64, "a" * 63, "a" * 65, "a" * 63 + "\n", "g" * 64, "a" * 64 + "\n"):
            with self.subTest(bad=bad):
                self.assertRejected(lambda r: r["reproduction"].update(input_sha256=bad))
                self.assertRejected(lambda r: r["reproduction"].update(artifact_sha256=bad))

    def test_wrong_enums(self):
        for field, bad in (
            ("direction", "inspect"), ("format_mode", "lenient"), ("routing", "applied"),
            ("structural", "ok"), ("execution_status", "done"), ("protocol_version", "1.0.1"),
        ):
            with self.subTest(field=field):
                self.assertRejected(lambda r: r.update({field: bad}))
        self.assertRejected(lambda r: r["preservation"].update(status="kept"))

    def test_missing_field(self):
        self.assertRejected(lambda r: r.pop("context"))

    def test_severity_mismatch(self):
        def mutate(r):
            r["diagnostics"] = [{"code": "INPUT_INVALID", "path": "", "severity": "warning", "message": "m"}]
        self.assertRejected(mutate)

    def test_bad_pointer(self):
        for bad in ("a", "/a~2", "/a~", "\n"):
            with self.subTest(bad=bad):
                self.assertRejected(lambda r: r["preservation"].update(status="changed", paths=[bad]))

    def test_paths_only_when_changed(self):
        self.assertRejected(lambda r: r["preservation"].update(paths=["/a"]))

    def test_validate_direction_requires_not_tested_and_null_output(self):
        self.assertRejected(lambda r: r["preservation"].update(status="preserved"))
        self.assertRejected(lambda r: r.update(output={}))

    def test_not_run_only_for_setup_or_input_failure(self):
        self.assertRejected(lambda r: r.update(structural="not-run"))
        self.assertRejected(lambda r: r.update(execution_status="setup-failed"))

    def test_unsorted_or_duplicate_diagnostics(self):
        warn = {"code": "TIMING_UNINTERPRETED", "severity": "warning", "message": "m"}
        self.assertRejected(lambda r: r.update(diagnostics=[dict(warn, path="/b"), dict(warn, path="/a")]))
        self.assertRejected(lambda r: r.update(diagnostics=[dict(warn, path="/a"), dict(warn, path="/a")]))

    def test_non_boolean_independence_claim(self):
        self.assertRejected(lambda r: r["implementation"].update(independence_claim="false"))


def diag(code, path=""):
    return {"code": code, "path": path, "severity": corpus.DIAGNOSTIC_SEVERITY[code], "message": "m"}


class OutcomeTableTest(unittest.TestCase):
    """check_result enforces the CONTRACT.md outcome table across profile, routing, and status."""

    def setUp(self):
        self.selected = build("exchange-minimal-asset")
        self.legacy = build("minimal-asset")
        self.unsupported = build("exchange-unknown-version")
        for result in (self.selected, self.legacy, self.unsupported):
            self.assertEqual(results.result_problems(result), [])

    def assertRejected(self, base, mutate, expected):
        result = copy.deepcopy(base)
        mutate(result)
        problems = results.result_problems(result)
        self.assertTrue(any(expected in p for p in problems), problems)
        with self.assertRaises(results.ResultInvalid):
            results.check_result(result)

    def assertAccepted(self, base, mutate):
        result = copy.deepcopy(base)
        mutate(result)
        self.assertEqual(results.result_problems(result), [])

    def test_error_diagnostic_with_complete_is_rejected(self):
        self.assertRejected(
            self.selected, lambda r: r.update(diagnostics=[diag("RIGHTS_UNSUPPORTED", "/rights_information")]),
            "error-severity diagnostic requires blocked",
        )

    def test_selected_valid_with_only_warnings_must_be_complete(self):
        warn = [diag("TIMING_UNINTERPRETED", "/a")]
        self.assertAccepted(self.selected, lambda r: r.update(diagnostics=warn))
        self.assertRejected(
            self.selected, lambda r: r.update(diagnostics=warn, execution_status="blocked"),
            "without error-severity diagnostics requires complete",
        )
        self.assertAccepted(
            self.selected,
            lambda r: r.update(diagnostics=[diag("SIZE_UNUSABLE", "/s")], execution_status="blocked"),
        )

    def test_selected_structural_invalid_requires_blocked_without_diagnostics(self):
        self.assertAccepted(self.selected, lambda r: r.update(structural="invalid", execution_status="blocked"))
        self.assertRejected(
            self.selected, lambda r: r.update(structural="invalid"),
            "structural invalid requires blocked",
        )
        self.assertRejected(
            self.selected,
            lambda r: r.update(structural="invalid", execution_status="blocked",
                               diagnostics=[diag("SIZE_UNUSABLE", "/s")]),
            "structural invalid carries no semantic diagnostics",
        )

    def test_selected_rejects_routing_diagnostics(self):
        for code in ("PROFILE_UNSUPPORTED", "VERSION_UNSUPPORTED", "INPUT_INVALID"):
            with self.subTest(code=code):
                self.assertRejected(
                    self.selected, lambda r, c=code: r.update(diagnostics=[diag(c)], execution_status="blocked"),
                    "selected routing carries only semantic diagnostics",
                )

    def test_selected_rejects_unsupported_status(self):
        self.assertRejected(
            self.selected, lambda r: r.update(execution_status="unsupported"),
            "selected routing requires blocked or complete",
        )

    def test_unsupported_routing_requires_unsupported_status(self):
        self.assertRejected(
            self.unsupported, lambda r: r.update(execution_status="blocked"),
            "unsupported routing requires unsupported status",
        )
        self.assertRejected(
            self.selected, lambda r: r.update(execution_status="unsupported", routing="selected",
                                              diagnostics=[diag("VERSION_UNSUPPORTED", "/schema_version")]),
            "selected routing",
        )

    def test_unsupported_status_requires_unsupported_routing(self):
        self.assertRejected(
            self.legacy, lambda r: r.update(execution_status="unsupported"),
            "legacy-1x requires complete",
        )

    def test_unsupported_diagnostics(self):
        self.assertRejected(
            self.unsupported, lambda r: r.update(diagnostics=[]),
            "unsupported routing requires PROFILE_UNSUPPORTED at the root or only VERSION_UNSUPPORTED",
        )
        self.assertRejected(
            self.unsupported,
            lambda r: r.update(diagnostics=[diag("RIGHTS_UNSUPPORTED", "/r"), diag("VERSION_UNSUPPORTED", "/schema_version")]),
            "unsupported routing requires PROFILE_UNSUPPORTED at the root or only VERSION_UNSUPPORTED",
        )
        self.assertRejected(
            self.unsupported, lambda r: r.update(diagnostics=[diag("PROFILE_UNSUPPORTED", "/x")]),
            "unsupported routing requires PROFILE_UNSUPPORTED at the root or only VERSION_UNSUPPORTED",
        )
        self.assertRejected(
            self.unsupported,
            lambda r: r.update(diagnostics=[diag("PROFILE_UNSUPPORTED"), diag("VERSION_UNSUPPORTED", "/schema_version")]),
            "unsupported routing requires PROFILE_UNSUPPORTED at the root or only VERSION_UNSUPPORTED",
        )
        self.assertAccepted(self.unsupported, lambda r: r.update(diagnostics=[diag("PROFILE_UNSUPPORTED")]))
        self.assertAccepted(self.unsupported, lambda r: r.update(structural="invalid"))

    def test_exchange_outcome_requires_routing(self):
        self.assertRejected(
            self.selected, lambda r: r.update(routing="not-applied"),
            "exchange-1x outcome requires selected or unsupported routing",
        )

    def test_legacy_rules(self):
        self.assertAccepted(self.legacy, lambda r: r.update(structural="invalid"))
        self.assertRejected(self.legacy, lambda r: r.update(routing="selected"), "legacy-1x requires not-applied routing")
        self.assertRejected(self.legacy, lambda r: r.update(routing="unsupported"), "legacy-1x requires not-applied routing")
        self.assertRejected(self.legacy, lambda r: r.update(execution_status="blocked"), "legacy-1x requires complete")
        self.assertRejected(
            self.legacy, lambda r: r.update(diagnostics=[diag("TIMING_UNINTERPRETED", "/a")]),
            "legacy-1x carries no semantic diagnostics",
        )

    def test_failures_require_not_applied_routing(self):
        for base in (self.selected, self.unsupported):
            for status, diagnostics in (("setup-failed", []), ("input-invalid", [diag("INPUT_INVALID")])):
                with self.subTest(status=status):
                    self.assertRejected(
                        base, lambda r, s=status, d=diagnostics: r.update(
                            execution_status=s, structural="not-run", diagnostics=d),
                        "setup or input failure requires not-applied routing",
                    )
                    self.assertAccepted(
                        base, lambda r, s=status, d=diagnostics: r.update(
                            execution_status=s, structural="not-run", diagnostics=d, routing="not-applied"),
                    )

    def test_unknown_profile_only_fails_setup(self):
        self.assertRejected(self.legacy, lambda r: r.update(profile="other-1x"), "unknown profile requires setup-failed")
        self.assertAccepted(self.legacy, lambda r: r.update(
            profile="other-1x", structural="not-run", execution_status="setup-failed"))

    def test_unknown_profile_rejects_every_status_but_setup_failed(self):
        for status, structural, diagnostics in (
            ("input-invalid", "not-run", [diag("INPUT_INVALID")]),
            ("complete", "valid", []),
            ("blocked", "valid", [diag("SIZE_UNUSABLE", "/s")]),
        ):
            with self.subTest(status=status):
                self.assertRejected(self.legacy, lambda r, s=status, t=structural, d=diagnostics: r.update(
                    profile="other-1x", execution_status=s, structural=t, diagnostics=d),
                    "unknown profile requires setup-failed")

    def test_every_corpus_result_passes(self):
        problems = []
        for case in CASES.values():
            modes = ("required",) if case.profile == "exchange-1x" else results.FORMAT_MODES
            for root in ("baseline", "current"):
                for mode in modes:
                    result = build(case.id, format_mode=mode, root=root)
                    found = results.result_problems(result)
                    if found:
                        problems.append(f"{case.id} {root} {mode} {found}")
        self.assertEqual(problems, [])



class DirectionPreservationTest(unittest.TestCase):
    """Non-validate directions must record preservation evidence."""

    def setUp(self):
        self.base = build("exchange-minimal-asset")

    def variant(self, direction, status, output, paths=()):
        result = copy.deepcopy(self.base)
        result.update(direction=direction, output=output)
        result["preservation"] = {"status": status, "paths": list(paths)}
        return result

    def test_not_tested_is_rejected(self):
        for direction in ("produce", "consume", "round-trip"):
            for output in (None, {"asset_id": "a"}):
                with self.subTest(direction=direction, output=output):
                    problems = results.result_problems(self.variant(direction, "not-tested", output))
                    self.assertTrue(any("must not be not-tested" in p for p in problems), problems)

    def test_null_output_unsupported_is_accepted(self):
        for direction in ("produce", "consume", "round-trip"):
            with self.subTest(direction=direction):
                self.assertEqual(results.result_problems(self.variant(direction, "unsupported", None)), [])

    def test_comparable_output_is_accepted(self):
        for direction in ("produce", "consume", "round-trip"):
            with self.subTest(direction=direction):
                self.assertEqual(results.result_problems(self.variant(direction, "preserved", {"a": 1})), [])
                self.assertEqual(
                    results.result_problems(self.variant(direction, "changed", {"a": 1}, ["/a"])), [])


class SortTest(unittest.TestCase):
    def test_array_indexes_sort_lexically(self):
        self.assertEqual(
            results.sort_pointers(["/assets/2/asset_id", "/assets/10/asset_id"]),
            ["/assets/10/asset_id", "/assets/2/asset_id"],
        )

    def test_pointers_sort_escaped_by_scalar_value_and_dedupe(self):
        # U+1F600 is above U+FFFF; UTF-16 order would put it before U+FF61.
        pointers = ["/\U0001F600", "/｡", "/a~1b", "/a~0b", "/a~0b", ""]
        self.assertEqual(results.sort_pointers(pointers), ["", "/a~0b", "/a~1b", "/｡", "/\U0001F600"])

    def test_diagnostics_sort_by_path_then_code_and_dedupe(self):
        found = [
            Diagnostic("TIMING_UNINTERPRETED", "/b", "warning", "one"),
            Diagnostic("RANGE_REVERSED", "/b", "error", "two"),
            Diagnostic("TIMING_UNINTERPRETED", "/a", "warning", "three"),
            Diagnostic("RANGE_REVERSED", "/b", "error", "different message"),
        ]
        ordered = results.sort_diagnostics(found)
        self.assertEqual(
            [(d.code, d.path) for d in ordered],
            [("TIMING_UNINTERPRETED", "/a"), ("RANGE_REVERSED", "/b"), ("TIMING_UNINTERPRETED", "/b")],
        )

    def test_catalog_severity_check(self):
        self.assertEqual(results.severity_problems([Diagnostic("RANGE_REVERSED", "", "error", "m")]), [])
        self.assertNotEqual(results.severity_problems([Diagnostic("RANGE_REVERSED", "", "warning", "m")]), [])
        self.assertNotEqual(results.severity_problems([Diagnostic("NOT_A_CODE", "", "error", "m")]), [])


class ProfilePassThroughTest(unittest.TestCase):
    def test_same_input_under_two_profiles(self):
        legacy, exchange = CASES["minimal-asset"], CASES["exchange-minimal-asset"]
        # Fixture loading keeps both profiles for the same input bytes.
        self.assertEqual(legacy.path, exchange.path)
        self.assertEqual((legacy.profile, exchange.profile), ("legacy-1x", "exchange-1x"))

        spy = SpyChecker(results.ProfileOutcome(
            routing="selected", execution_status="complete",
            diagnostics=(Diagnostic("COMPLETENESS_UNVERIFIED", "", "warning", "Export completeness is not established."),),
        ))
        legacy_result = build("minimal-asset", checker=spy)
        self.assertEqual(spy.calls, [])
        exchange_result = build("exchange-minimal-asset", checker=spy)
        digest = hashlib.sha256((FIXTURES / legacy.path).read_bytes()).hexdigest()
        self.assertEqual(spy.calls, [("exchange-minimal-asset", "exchange-1x", digest, "valid")])

        for result, profile in ((legacy_result, "legacy-1x"), (exchange_result, "exchange-1x")):
            with self.subTest(profile=profile):
                self.assertEqual(results.result_problems(result), [])
                reread = parse_input(results.dump_result(result)).value
                self.assertEqual(reread["profile"], profile)
                self.assertEqual(reread["reproduction"]["input_sha256"], digest)

        self.assertEqual(exchange_result["routing"], "selected")
        self.assertEqual(exchange_result["diagnostics"], [{
            "code": "COMPLETENESS_UNVERIFIED", "path": "", "severity": "warning",
            "message": "Export completeness is not established.",
        }])
        self.assertEqual(legacy_result["routing"], "not-applied")
        self.assertEqual(legacy_result["diagnostics"], [])

    def test_checker_setup_failure_reports_not_run(self):
        def failing(case, document, structural):
            raise SetupFailed("profile resource is missing")
        result = build("exchange-minimal-asset", checker=failing)
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual(
            (result["routing"], result["structural"], result["execution_status"], result["diagnostics"]),
            ("not-applied", "not-run", "setup-failed", []),
        )

    def test_checker_diagnostics_are_sorted_and_deduplicated(self):
        warn = Diagnostic("TIMING_UNINTERPRETED", "/b", "warning", "m")
        spy = SpyChecker(results.ProfileOutcome(
            routing="selected", execution_status="complete",
            diagnostics=(warn, dataclasses.replace(warn, path="/a"), warn),
        ))
        result = build("exchange-minimal-asset", checker=spy)
        self.assertEqual([d["path"] for d in result["diagnostics"]], ["/a", "/b"])


class CommandTest(unittest.TestCase):
    def test_reproduction_command_runs(self):
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True, check=True
        ).stdout.strip()
        expected = results.build_validate_result(
            CASES["missing-required-asset"], format_mode="historical-unchecked", root="baseline",
            source_revision=head,
        )
        argv = expected["reproduction"]["command"].split()
        self.assertEqual(argv[:3], ["python3", "-m", "tests.conformance.results"])
        done = subprocess.run(
            [sys.executable, *argv[1:]], cwd=REPO, capture_output=True, check=True
        )
        self.assertEqual(done.stdout, results.dump_result(expected))


if __name__ == "__main__":
    unittest.main()
