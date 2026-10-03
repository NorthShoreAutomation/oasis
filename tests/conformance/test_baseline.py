"""Baseline byte tests and bundle manifest tests."""

import copy
import hashlib
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests.conformance.bundle import BundleManifest, load_bundle_manifest
from tests.conformance import corpus
from tests.conformance.loader import validate_legacy
from tests.conformance.strict_json import parse_input
from tests.conformance.types import InputInvalid, SetupFailed

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests" / "conformance" / "baseline"
DEFINITIONS = ROOT / "definitions"
BASELINE_COMMIT = "1e2849b287bba42fbe6c1767a49f6016ddaff58a"

# SHA-256 of each schema at the public baseline commit. Static, so the byte
# check needs no network and no git history at test time.
BASELINE_SHA256 = {
    "asset.schema.json": "4a8f87de9af09e72bf67d7c470d8fceaf0bf3ee7139735cfac0206f2fa5bb166",
    "asset_batch_import.schema.json": "46251029d189af6ea5def22d4e003d37c83f99b9684bbf0c6699326fb4c133a8",
    "collection.schema.json": "2da96be072f0788d52f2c4c986372c1a35e2b77d5db05f63f5c1f5bcd8cf6a94",
    "collection_batch_import.schema.json": "aad82b60bdbfceed9bcd930c9d48b45a8fa01deb6b51767887247ef48c0175d2",
    "metadata_set.schema.json": "63e3c1858f6369be15326eb0988b8f7223ee60b3fcdd90ddd5b0f21e6c43b8c9",
    "migration-report-output.schema.json": "8a8578824351bb2c5ebff46177407ad83a8da0f306d3b572ae9e71a95e6d22c0",
    "storage_location.schema.json": "dda6e043178797b11c6daa59f3cd4cc4378defef67dc056b9fe2b313908197d1",
    "temporal_annotation.schema.json": "6e711410cd5e89f36b268ad84d7c7aaea4fd6aaa058cb9871cb4a95a730f6948",
}
ABSOLUTE_IDS = {
    "migration-report-output.schema.json": "https://www.northshoreautomation.com/schemas/migration-report-output-v1.0.0.json",
    "temporal_annotation.schema.json": "https://www.northshoreautomation.com/schemas/temporal_annotation.schema.json",
}
FROZEN_REVISION = "v1.1.1-1e2849b287bb"
CURRENT_REVISION = "1.2.0-draft.1"
URI_PREFIX = "https://schemas.oasis.invalid/bundles/"


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


class BaselineBytesTest(unittest.TestCase):
    def test_baseline_has_exactly_eight_schemas(self):
        names = sorted(p.name for p in BASELINE.glob("*.schema.json"))
        self.assertEqual(names, sorted(BASELINE_SHA256))

    def test_baseline_bytes_match_recorded_digests(self):
        for name, digest in BASELINE_SHA256.items():
            with self.subTest(name=name):
                self.assertEqual(sha((BASELINE / name).read_bytes()), digest)

    # The current definitions may differ from the baseline only in descriptions.
    # test_packaging.py proves that, and that the migration report is unchanged.

    def test_baseline_bytes_equal_public_commit_when_reachable(self):
        probe = subprocess.run(
            ["git", "cat-file", "-e", BASELINE_COMMIT + "^{commit}"],
            cwd=ROOT, capture_output=True,
        )
        if probe.returncode != 0:
            self.skipTest("public baseline commit not in local object store")
        for name in BASELINE_SHA256:
            with self.subTest(name=name):
                shown = subprocess.run(
                    ["git", "show", f"{BASELINE_COMMIT}:definitions/{name}"],
                    cwd=ROOT, capture_output=True, check=True,
                ).stdout
                self.assertEqual((BASELINE / name).read_bytes(), shown)


class ManifestContentTest(unittest.TestCase):
    def setUp(self):
        self.frozen = load_bundle_manifest(BASELINE)
        self.current = load_bundle_manifest(DEFINITIONS)

    def test_manifest_files_end_with_newline_and_are_separate(self):
        a = BASELINE / "bundle-manifest.json"
        b = DEFINITIONS / "bundle-manifest.json"
        self.assertNotEqual(a.resolve(), b.resolve())
        for p in (a, b):
            self.assertTrue(p.read_bytes().endswith(b"\n"))

    def test_revisions_are_distinct_and_exact(self):
        self.assertEqual(self.frozen.bundle_revision, FROZEN_REVISION)
        self.assertEqual(self.current.bundle_revision, CURRENT_REVISION)
        self.assertEqual(self.frozen.manifest_version, "1.0.0")
        self.assertEqual(self.current.manifest_version, "1.0.0")

    def test_entries_sorted_by_name_and_cover_all_schemas(self):
        for manifest in (self.frozen, self.current):
            names = [e.name for e in manifest.schemas]
            self.assertEqual(names, sorted(BASELINE_SHA256))

    def test_digests_match_files(self):
        for root, manifest in ((BASELINE, self.frozen), (DEFINITIONS, self.current)):
            for e in manifest.schemas:
                with self.subTest(root=root.name, name=e.name):
                    self.assertEqual(sha((root / e.path).read_bytes()), e.sha256)
                    self.assertEqual(e.path, e.name)

    def test_frozen_digests_equal_public_baseline(self):
        for e in self.frozen.schemas:
            self.assertEqual(e.sha256, BASELINE_SHA256[e.name])

    def test_identifiers_follow_the_rules(self):
        for manifest in (self.frozen, self.current):
            for e in manifest.schemas:
                with self.subTest(rev=manifest.bundle_revision, name=e.name):
                    bundle_uri = f"{URI_PREFIX}{manifest.bundle_revision}/{e.name}"
                    if e.name in ABSOLUTE_IDS:
                        self.assertEqual(e.id, ABSOLUTE_IDS[e.name])
                        self.assertEqual(e.base_uri, e.id)
                        self.assertEqual(e.aliases, (bundle_uri,))
                    else:
                        self.assertIsNone(e.id)
                        self.assertEqual(e.base_uri, bundle_uri)
                        self.assertEqual(e.aliases, ())

    def test_root_ids_come_from_schema_bytes(self):
        for e in self.frozen.schemas:
            doc = json.loads((BASELINE / e.name).read_bytes())
            self.assertEqual(doc.get("$id"), e.id)


class ManifestRejectionTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        for p in BASELINE.glob("*.schema.json"):
            shutil.copy(p, self.dir / p.name)
        self.base = json.loads((BASELINE / "bundle-manifest.json").read_bytes())

    def write(self, manifest):
        (self.dir / "bundle-manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )

    def mutated(self, fn):
        m = copy.deepcopy(self.base)
        fn(m)
        self.write(m)

    def assertRejected(self, fn):
        self.mutated(fn)
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_valid_copy_loads(self):
        self.write(self.base)
        self.assertIsInstance(load_bundle_manifest(self.dir), BundleManifest)

    def test_missing_manifest(self):
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_not_json_and_not_object(self):
        (self.dir / "bundle-manifest.json").write_bytes(b"{nope")
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)
        (self.dir / "bundle-manifest.json").write_bytes(b"[]\n")
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_duplicate_json_keys(self):
        self.write(self.base)
        raw = (self.dir / "bundle-manifest.json").read_text()
        raw = raw.replace('"manifest_version"', '"manifest_version": "1.0.0", "manifest_version"', 1)
        (self.dir / "bundle-manifest.json").write_text(raw)
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_top_level_shape(self):
        self.assertRejected(lambda m: m.update(extra=1))
        self.assertRejected(lambda m: m.pop("schemas"))
        self.assertRejected(lambda m: m.update(manifest_version="1.0.1"))
        self.assertRejected(lambda m: m.update(schemas={}))
        self.assertRejected(lambda m: m.update(schemas=[]))

    def test_entry_shape(self):
        self.assertRejected(lambda m: m["schemas"][0].update(extra=1))
        self.assertRejected(lambda m: m["schemas"][0].pop("aliases"))
        self.assertRejected(lambda m: m["schemas"][0].update(aliases="x"))
        self.assertRejected(lambda m: m["schemas"][0].update(name=3))
        self.assertRejected(lambda m: m["schemas"].__setitem__(0, "x"))

    def test_revision_pattern(self):
        for bad in ("", "-x", ".x", "a/b", "a b", "a%2Fb", "a\\b", "a:b", "a\n", 5):
            with self.subTest(bad=bad):
                self.assertRejected(lambda m, b=bad: m.update(bundle_revision=b))

    def test_paths_inside_bundle(self):
        for bad in ("/etc/passwd", "../asset.schema.json", "sub/../../x",
                    "a\\..\\b", "", "C:/x", "./asset.schema.json", "sub//x"):
            with self.subTest(bad=bad):
                self.assertRejected(lambda m, b=bad: m["schemas"][0].update(path=b))

    def test_symlink_escape_rejected(self):
        outside = tempfile.TemporaryDirectory()
        self.addCleanup(outside.cleanup)
        target = Path(outside.name) / "asset.schema.json"
        shutil.copy(self.dir / "asset.schema.json", target)
        (self.dir / "asset.schema.json").unlink()
        (self.dir / "asset.schema.json").symlink_to(target)
        self.write(self.base)
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_missing_schema_file(self):
        self.write(self.base)
        (self.dir / "asset.schema.json").unlink()
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_digest_format_and_mismatch(self):
        self.assertRejected(lambda m: m["schemas"][0].update(sha256="0" * 64))
        self.assertRejected(lambda m: m["schemas"][0].update(sha256="A" * 64))
        self.assertRejected(lambda m: m["schemas"][0].update(sha256="ab"))

    def test_changed_file_bytes_fail_digest(self):
        self.write(self.base)
        with open(self.dir / "asset.schema.json", "ab") as fh:
            fh.write(b" ")
        with self.assertRaises(SetupFailed):
            load_bundle_manifest(self.dir)

    def test_duplicate_names(self):
        def dup(m):
            m["schemas"][1] = copy.deepcopy(m["schemas"][0])
        self.assertRejected(dup)

    def test_malformed_base_uri_is_setup_failure(self):
        self.assertRejected(lambda m: m["schemas"][0].update(base_uri="https://[bad"))

    def test_malformed_alias_is_setup_failure(self):
        self.assertRejected(lambda m: m["schemas"][0].update(aliases=["https://[bad"]))

    def test_base_uri_must_be_absolute(self):
        self.assertRejected(lambda m: m["schemas"][0].update(base_uri="asset.schema.json"))
        self.assertRejected(lambda m: m["schemas"][0].update(base_uri="/x"))

    def test_id_must_equal_base_uri(self):
        idx = [e["name"] for e in self.base["schemas"]].index("temporal_annotation.schema.json")
        self.assertRejected(lambda m: m["schemas"][idx].update(id="https://example.invalid/x"))

    def test_alias_must_be_absolute(self):
        self.assertRejected(lambda m: m["schemas"][0].update(aliases=["rel/path"]))

    def test_alias_collides_with_other_base(self):
        self.assertRejected(
            lambda m: m["schemas"][0].update(aliases=[m["schemas"][1]["base_uri"]])
        )

    def test_alias_collides_with_other_alias(self):
        def clash(m):
            m["schemas"][0]["aliases"] = ["https://a.invalid/x"]
            m["schemas"][1]["aliases"] = ["https://a.invalid/x"]
        self.assertRejected(clash)

    def test_alias_repeats_own_base_or_itself(self):
        self.assertRejected(
            lambda m: m["schemas"][0].update(aliases=[m["schemas"][0]["base_uri"]])
        )
        self.assertRejected(
            lambda m: m["schemas"][0].update(aliases=["https://a.invalid/x"] * 2)
        )

    def test_duplicate_base_uri(self):
        self.assertRejected(
            lambda m: m["schemas"][1].update(base_uri=m["schemas"][0]["base_uri"])
        )


FIXTURES = ROOT / "tests" / "conformance" / "fixtures"
ROOTS = (("frozen", BASELINE), ("current", DEFINITIONS))
MODES = (("required", True), ("historical-unchecked", False))
# Transcribed from the CONTRACT.md "Diagnostic catalog" table.
ALL_CODES = {
    "INPUT_INVALID", "VERSION_UNSUPPORTED", "PROFILE_UNSUPPORTED", "IDENTITY_UNUSABLE",
    "IDENTITY_DUPLICATE", "COLLECTION_CYCLE", "SIZE_UNUSABLE", "RATE_UNUSABLE",
    "RANGE_REVERSED", "CONNECTION_DATA_UNREVIEWED", "RIGHTS_UNSUPPORTED",
    "REFERENCE_UNRESOLVED", "MEMBERSHIP_UNINTERPRETED", "VALUE_SEMANTICS_UNSPECIFIED",
    "TIMING_UNINTERPRETED", "INTEGRITY_UNVERIFIED", "CHECKSUM_UNINTERPRETED",
    "COMPLETENESS_UNVERIFIED",
}


def _observe(case, root, check_formats):
    """Return the Python engine outcome for one case, root, and mode."""
    try:
        parsed = parse_input((FIXTURES / case.path).read_bytes())
        errors = validate_legacy(case.schema_name, parsed, root=root, check_formats=check_formats)
    except InputInvalid:
        return "input-invalid"
    except SetupFailed:
        return "setup-failed"
    return "valid" if not errors else "invalid"


class CorpusLoadTest(unittest.TestCase):
    def test_corpus_has_145_unique_cases(self):
        cases = corpus.fixture_cases()
        self.assertEqual(len(cases), 145)
        self.assertEqual(len({c.id for c in cases}), 145)

    def test_case_fields_are_mapped(self):
        case = {c.id: c for c in corpus.fixture_cases()}["minimal-asset"]
        self.assertEqual(case.schema_name, "asset.schema.json")
        self.assertEqual(case.profile, "legacy-1x")
        self.assertIs(case.expected_valid, True)
        self.assertEqual(case.expected_diagnostics, ())

    def test_diagnostics_become_expected_diagnostic_pairs(self):
        found = [d for c in corpus.fixture_cases() for d in c.expected_diagnostics]
        self.assertTrue(found)
        self.assertEqual({d.code for d in found} - ALL_CODES, set())

    def test_severity_map_holds_exactly_the_catalog(self):
        self.assertEqual(set(corpus.DIAGNOSTIC_SEVERITY), ALL_CODES)
        errors = sum(v == "error" for v in corpus.DIAGNOSTIC_SEVERITY.values())
        self.assertEqual((errors, len(ALL_CODES) - errors), (11, 7))

    def test_preservation_comparisons_load(self):
        found = corpus.preservation_comparisons()
        self.assertEqual(len(found), 6)
        ids = {c.id for c in corpus.fixture_cases()}
        for item in found:
            self.assertIn(item.source_case_id, ids)
            self.assertIn(item.output_case_id, ids)


class CorpusSweepTest(unittest.TestCase):
    def test_python_engine_matches_expectations_in_every_root_and_mode(self):
        mismatches = []
        for case in corpus.fixture_cases():
            expected = case.validator_expectations["python-jsonschema"]
            for root_name, root in ROOTS:
                for mode_name, check_formats in MODES:
                    observed = _observe(case, root, check_formats)
                    status = expected["adapter_status"]
                    if status == "complete":
                        want = expected[mode_name]
                        want = None if want is None else ("valid" if want else "invalid")
                    else:
                        want = status
                    if observed != want:
                        mismatches.append(
                            f"{case.id} root={root_name} mode={mode_name} "
                            f"expected={want} observed={observed}"
                        )
        self.assertEqual(mismatches, [], "\n" + "\n".join(mismatches))


class FixtureManifestRejectionTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        (self.dir / "records").mkdir()
        (self.dir / "records" / "a.json").write_text("{}")
        (self.dir / "records" / "b.json").write_text("{}")
        self.manifest = json.loads((FIXTURES / "manifest.json").read_text())
        first = copy.deepcopy(self.manifest["cases"][0])
        first["path"] = "records/a.json"
        second = copy.deepcopy(first)
        second.update(id="second", path="records/b.json")
        self.manifest["cases"] = [first, second]
        self.manifest["preservation_comparisons"] = []

    def write(self):
        path = self.dir / "manifest.json"
        path.write_text(json.dumps(self.manifest))
        return path

    def assertRejected(self, mutate, loader=corpus.fixture_cases):
        mutate(self.manifest)
        with self.assertRaises(SetupFailed):
            loader(self.write())

    def case(self, n=0):
        return self.manifest["cases"][n]

    def test_unmodified_temporary_manifest_loads(self):
        self.assertEqual(len(corpus.fixture_cases(self.write())), 2)

    def test_unknown_profile(self):
        self.assertRejected(lambda m: m["cases"][0].update(profile="exchange-9x"))

    def test_unknown_profile_in_manifest_profiles(self):
        self.assertRejected(lambda m: m["profiles"].append("other-profile"))

    def test_case_profile_not_declared(self):
        self.assertRejected(lambda m: m.update(profiles=["exchange-1x"]))

    def test_missing_input_file(self):
        self.assertRejected(lambda m: m["cases"][0].update(path="records/none.json"))

    def test_path_escapes_fixture_directory(self):
        self.assertRejected(lambda m: m["cases"][0].update(path="../manifest.json"))
        self.assertRejected(lambda m: m["cases"][0].update(path=str(self.dir / "records" / "a.json")))

    def test_duplicate_fixture_id(self):
        self.assertRejected(lambda m: m["cases"][1].update(id=m["cases"][0]["id"]))

    def test_unknown_diagnostic_code(self):
        self.assertRejected(lambda m: m["cases"][0].update(
            expected_diagnostics=[{"code": "NOT_A_CODE", "path": ""}]))

    def test_invalid_pointers(self):
        for bad in ("a", "/a~", "/a~2", "~0", " /a", None, 3):
            with self.subTest(pointer=bad):
                self.manifest["cases"][0]["expected_diagnostics"] = [
                    {"code": "INPUT_INVALID", "path": bad}]
                with self.assertRaises(SetupFailed):
                    corpus.fixture_cases(self.write())

    def test_valid_pointers_accepted(self):
        for good in ("", "/", "/a/0", "/a~0b/~1", "//"):
            with self.subTest(pointer=good):
                self.manifest["cases"][0]["expected_diagnostics"] = [
                    {"code": "INPUT_INVALID", "path": good}]
                self.assertEqual(len(corpus.fixture_cases(self.write())), 2)

    def test_vocabularies(self):
        for field, bad in (
            ("context", "elsewhere"), ("input_kind", "yaml"),
            ("expected_execution_status", "done"), ("expected_routing", "sideways"),
        ):
            with self.subTest(field=field):
                self.assertRejected(lambda m: m["cases"][0].update({field: bad}))
                self.manifest["cases"][0] = copy.deepcopy(self.manifest["cases"][1])
                self.manifest["cases"][0]["id"] = "minimal-asset"

    def test_expected_valid_must_be_boolean_or_null(self):
        self.assertRejected(lambda m: m["cases"][0].update(expected_valid="yes"))

    def test_adapter_status_vocabulary(self):
        self.assertRejected(lambda m: m["cases"][0]["validator_expectations"]
                            ["python-jsonschema"].update(adapter_status="broken"))

    def test_expectation_shape(self):
        self.assertRejected(lambda m: m["cases"][0]["validator_expectations"].pop("python-jsonschema"))
        self.assertRejected(lambda m: m["cases"][1]["validator_expectations"]
                            ["python-jsonschema"].update(required="true"))
        self.assertRejected(lambda m: m["cases"][1]["validator_expectations"]
                            ["python-jsonschema"].update(limitation=5))
        self.assertRejected(lambda m: m["cases"][1]["validator_expectations"]
                            ["python-jsonschema"].update(extra=1))

    def test_expectations_accept_only_known_engines(self):
        self.assertEqual(corpus.ENGINES, ("python-jsonschema",))
        self.assertRejected(lambda m: m["cases"][0]["validator_expectations"].update(
            {"go-jsonschema": dict(m["cases"][0]["validator_expectations"]["python-jsonschema"])}))

    def test_exclusion_shape(self):
        good = {"validator": "python-jsonschema", "status": "proposed", "reason": "why"}
        for bad in (
            {**good, "status": "granted"}, {**good, "validator": "other"},
            {**good, "validator": "go-jsonschema"},
            {"validator": "python-jsonschema", "status": "proposed"}, {**good, "reason": None},
        ):
            with self.subTest(bad=bad):
                self.manifest["cases"][0]["exclusions"] = [bad]
                with self.assertRaises(SetupFailed):
                    corpus.fixture_cases(self.write())
        self.manifest["cases"][0]["exclusions"] = [good]
        self.assertEqual(len(corpus.fixture_cases(self.write())), 2)

    def test_missing_manifest_or_bad_json(self):
        with self.assertRaises(SetupFailed):
            corpus.fixture_cases(self.dir / "absent.json")
        (self.dir / "manifest.json").write_text("{")
        with self.assertRaises(SetupFailed):
            corpus.fixture_cases(self.dir / "manifest.json")

    def comparison(self, **changes):
        item = {"id": "c", "source_case_id": "minimal-asset", "output_case_id": "second",
                "expected_status": "changed", "paths": ["/a"]}
        item.update(changes)
        self.manifest["cases"][0]["id"] = "minimal-asset"
        self.manifest["preservation_comparisons"] = [item]
        return self.write()

    def test_comparison_loads(self):
        self.assertEqual(len(corpus.preservation_comparisons(self.comparison())), 1)

    def test_comparison_rejections(self):
        for changes in (
            {"source_case_id": "nope"}, {"output_case_id": "nope"},
            {"expected_status": "same"}, {"paths": ["/b", "/a"]}, {"paths": ["/a", "/a"]},
            {"paths": ["bad"]},
        ):
            with self.subTest(changes=changes):
                with self.assertRaises(SetupFailed):
                    corpus.preservation_comparisons(self.comparison(**changes))

    def test_comparison_duplicate_id(self):
        self.comparison()
        self.manifest["preservation_comparisons"] *= 2
        with self.assertRaises(SetupFailed):
            corpus.preservation_comparisons(self.write())


if __name__ == "__main__":
    unittest.main()
