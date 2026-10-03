"""Description-only schema patch tests.

The current interchange schemas may differ from the frozen baseline only in
``description`` string values. These tests prove that: the parsed trees match
once descriptions are masked, the raw bytes match once description string
literals are masked, the retained migration report is byte-identical, every
corpus case has the same outcome against both bundles, and the current bundle
still resolves offline. They also check the corrected wording for names that
must not appear in a neutral standard.
"""

import re
import unittest
from pathlib import Path

import referencing.exceptions

from tests.conformance import corpus, loader, results
from tests.conformance.strict_json import parse_input, parse_schema_bytes
from tests.conformance.types import SetupFailed

REPO = Path(__file__).resolve().parents[2]
BASELINE = REPO / "tests" / "conformance" / "baseline"
DEFINITIONS = REPO / "definitions"
REVISION = "0123456789abcdef0123456789abcdef01234567"
MIGRATION_REPORT = "migration-report-output.schema.json"
INTERCHANGE = (
    "asset.schema.json",
    "asset_batch_import.schema.json",
    "collection.schema.json",
    "collection_batch_import.schema.json",
    "metadata_set.schema.json",
    "storage_location.schema.json",
    "temporal_annotation.schema.json",
)
ALL_SCHEMAS = tuple(sorted(INTERCHANGE + (MIGRATION_REPORT,)))
BATCH_REFERENCES = {
    "asset_batch_import.schema.json": ("assets", "./asset.schema.json", "asset.schema.json"),
    "collection_batch_import.schema.json": ("collections", "./collection.schema.json", "collection.schema.json"),
}
# Case-insensitive. Applies to the interchange schemas only.
FORBIDDEN_WORDING = ("catdv", "iconik", "exodus", "target system", "tracking database")
PLACEHOLDER = "<description>"
# A "description" key whose value is a JSON string literal. A property named
# "description" has an object value, so it never matches.
_DESCRIPTION_LITERAL = re.compile(rb'("description"\s*:\s*)"(?:[^"\\]|\\.)*"')


def _mask_tree(node):
    """Return a copy of node with every string description value replaced."""
    if isinstance(node, dict):
        return {
            key: PLACEHOLDER if key == "description" and isinstance(value, str) else _mask_tree(value)
            for key, value in node.items()
        }
    if isinstance(node, list):
        return [_mask_tree(item) for item in node]
    return node


def _descriptions(node, pointer=""):
    """Yield (pointer, text) for every string description value in node."""
    if isinstance(node, dict):
        for key, value in node.items():
            child = pointer + "/" + key.replace("~", "~0").replace("/", "~1")
            if key == "description" and isinstance(value, str):
                yield child, value
            else:
                yield from _descriptions(value, child)
    elif isinstance(node, list):
        for index, item in enumerate(node):
            yield from _descriptions(item, f"{pointer}/{index}")


def _mask_bytes(data: bytes) -> bytes:
    return _DESCRIPTION_LITERAL.sub(rb'\1"' + PLACEHOLDER.encode() + rb'"', data)


def _tree(root: Path, name: str):
    return parse_schema_bytes((root / name).read_bytes())


class DescriptionOnlyTest(unittest.TestCase):
    def test_trees_equal_after_masking_descriptions(self):
        for name in ALL_SCHEMAS:
            with self.subTest(name=name):
                self.assertEqual(_mask_tree(_tree(DEFINITIONS, name)), _mask_tree(_tree(BASELINE, name)))

    def test_bytes_equal_after_masking_description_literals(self):
        for name in ALL_SCHEMAS:
            with self.subTest(name=name):
                current = (DEFINITIONS / name).read_bytes()
                frozen = (BASELINE / name).read_bytes()
                self.assertEqual(_mask_bytes(current), _mask_bytes(frozen))

    def test_description_pointers_are_unchanged(self):
        for name in ALL_SCHEMAS:
            with self.subTest(name=name):
                current = [p for p, _ in _descriptions(_tree(DEFINITIONS, name))]
                frozen = [p for p, _ in _descriptions(_tree(BASELINE, name))]
                self.assertEqual(current, frozen)

    def test_migration_report_bytes_equal_baseline(self):
        self.assertEqual(
            (DEFINITIONS / MIGRATION_REPORT).read_bytes(), (BASELINE / MIGRATION_REPORT).read_bytes()
        )

    def test_interchange_schemas_are_ascii(self):
        for name in INTERCHANGE:
            with self.subTest(name=name):
                (DEFINITIONS / name).read_bytes().decode("ascii")


class NeutralWordingTest(unittest.TestCase):
    def test_no_product_names_or_destination_workflow_in_descriptions(self):
        found = []
        for name in INTERCHANGE:
            for pointer, text in _descriptions(_tree(DEFINITIONS, name)):
                lowered = text.lower()
                found.extend(f"{name}#{pointer}: {word}" for word in FORBIDDEN_WORDING if word in lowered)
        self.assertEqual(found, [], "\n" + "\n".join(found))

    def test_checker_detects_the_frozen_wording(self):
        # Guards the check itself: the frozen baseline holds every listed term.
        text = " ".join(
            t.lower() for name in INTERCHANGE for _, t in _descriptions(_tree(BASELINE, name))
        )
        # "iconik" and "exodus" never appeared in the frozen schema descriptions.
        for word in ("catdv", "target system", "tracking database"):
            with self.subTest(word=word):
                self.assertIn(word, text)


def _outcome(result):
    return (
        result["routing"],
        result["structural"],
        result["execution_status"],
        sorted((d["code"], d["path"]) for d in result["diagnostics"]),
    )


class CorpusOutcomeEqualityTest(unittest.TestCase):
    def test_every_case_has_the_same_outcome_in_both_roots(self):
        mismatches = []
        checked = 0
        for case in corpus.fixture_cases():
            for mode in results.FORMAT_MODES:
                if case.profile == "exchange-1x" and mode != "required":
                    continue
                frozen, current = (
                    _outcome(results.build_validate_result(
                        case, format_mode=mode, root=root, source_revision=REVISION
                    ))
                    for root in ("baseline", "current")
                )
                checked += 1
                if case.validator_expectations["python-jsonschema"]["adapter_status"] == "complete":
                    self.assertNotEqual(current[2], "setup-failed", f"{case.id} mode={mode}")
                if frozen != current:
                    mismatches.append(f"{case.id} mode={mode} baseline={frozen} current={current}")
        self.assertGreater(checked, 145)
        self.assertEqual(mismatches, [], "\n" + "\n".join(mismatches))


class OfflineResolutionTest(unittest.TestCase):
    def setUp(self):
        self.bundle = loader.load_bundle(DEFINITIONS)

    def test_bundle_lists_every_schema(self):
        self.assertEqual(sorted(e.name for e in self.bundle.manifest.schemas), list(ALL_SCHEMAS))

    def test_retrieval_is_denied(self):
        resolver = self.bundle.registry.resolver()
        with self.assertRaises(referencing.exceptions.Unresolvable):
            resolver.lookup("https://schemas.oasis.invalid/not-in-bundle.json")

    def test_every_entry_point_compiles_and_runs_in_both_modes(self):
        document = parse_input(b"{}")
        for entry in self.bundle.manifest.schemas:
            for check_formats in (True, False):
                with self.subTest(name=entry.name, check_formats=check_formats):
                    try:
                        self.bundle.entry_point(entry.name, check_formats=check_formats).validate(document)
                    except SetupFailed as error:
                        self.fail(f"setup failed: {error}")

    def test_batch_references_resolve_inside_the_bundle(self):
        entries = {e.name: e for e in self.bundle.manifest.schemas}
        for batch, (key, reference, target) in BATCH_REFERENCES.items():
            with self.subTest(batch=batch):
                resolver = self.bundle.registry.resolver(base_uri=entries[batch].base_uri)
                resolved = resolver.lookup(reference)
                self.assertIs(resolved.contents, self.bundle.schemas[target])
                # Validation descends into the referenced record schema.
                document = parse_input(('{"%s": [{}]}' % key).encode())
                errors = self.bundle.entry_point(batch, check_formats=True).validate(document)
                self.assertTrue(errors)
                self.assertTrue(all(list(e.absolute_path)[:2] == [key, 0] for e in errors))


if __name__ == "__main__":
    unittest.main()
