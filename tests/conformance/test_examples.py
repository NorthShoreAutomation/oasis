"""Check the published examples in definitions/examples/.

Each example must strictly parse, be structurally valid against the current
bundle with date-time formats checked, and complete under ``exchange-1x``
with empty reference context and exactly its declared warnings.
"""

import unittest
from pathlib import Path

from tests.conformance import loader, profiles
from tests.conformance.corpus import DIAGNOSTIC_SEVERITY
from tests.conformance.strict_json import parse_input

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES_DIR = DEFINITIONS / "examples"
EMPTY_CONTEXT = {"asset_ids": [], "collection_ids": []}

# File name: (entry point, expected exchange-1x code/path pairs).
EXAMPLES = {
    "asset.json": ("asset.schema.json", [
        ("CHECKSUM_UNINTERPRETED", "/files/0/checksum"),
        ("INTEGRITY_UNVERIFIED", "/files/0/derivatives/0"),
        ("VALUE_SEMANTICS_UNSPECIFIED", "/metadata_sets/0/fields/0/value"),
        ("VALUE_SEMANTICS_UNSPECIFIED", "/metadata_sets/0/fields/1/value"),
    ]),
    "asset-batch.json": ("asset_batch_import.schema.json", [
        ("COMPLETENESS_UNVERIFIED", ""),
        ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/checksum"),
        ("CHECKSUM_UNINTERPRETED", "/assets/1/files/0/checksum"),
    ]),
    "collection.json": ("collection.schema.json", [
        ("REFERENCE_UNRESOLVED", "/assets/0"),
        ("REFERENCE_UNRESOLVED", "/assets/1"),
    ]),
    "collection-batch.json": ("collection_batch_import.schema.json", [
        ("COMPLETENESS_UNVERIFIED", ""),
    ]),
    "metadata-set.json": ("metadata_set.schema.json", []),
    "storage-location.json": ("storage_location.schema.json", []),
    "temporal-annotation.json": ("temporal_annotation.schema.json", []),
}


def _read(name):
    path = EXAMPLES_DIR / name
    if not path.is_file():
        raise AssertionError(f"example {name} is missing")
    return path.read_bytes()


class ExampleSetTest(unittest.TestCase):
    def test_examples_cover_every_interchange_entry_point(self):
        covered = {entry_point for entry_point, _ in EXAMPLES.values()}
        self.assertEqual(covered, set(profiles.INTERCHANGE_ENTRY_POINTS))

    def test_example_directory_holds_exactly_the_declared_examples(self):
        found = sorted(p.name for p in EXAMPLES_DIR.glob("*.json"))
        self.assertEqual(found, sorted(EXAMPLES))

    def test_readme_names_every_example_and_entry_point(self):
        readme = (EXAMPLES_DIR / "README.md").read_text(encoding="utf-8")
        for name, (entry_point, _) in EXAMPLES.items():
            with self.subTest(example=name):
                self.assertIn(f"`{name}`", readme)
                self.assertIn(f"`{entry_point}`", readme)

    def test_expected_diagnostics_are_warnings(self):
        for name, (_, expected) in EXAMPLES.items():
            for code, _path in expected:
                with self.subTest(example=name, code=code):
                    self.assertEqual(DIAGNOSTIC_SEVERITY[code], "warning")


class ExampleValidityTest(unittest.TestCase):
    def test_each_example_is_valid_and_exchange_complete(self):
        bundle = loader.load_bundle(DEFINITIONS)
        for name, (entry_point, expected) in EXAMPLES.items():
            with self.subTest(example=name):
                document = parse_input(_read(name))
                errors = bundle.entry_point(entry_point, check_formats=True).validate(document)
                self.assertEqual([list(e.absolute_path) for e in errors], [])
                outcome = profiles.validate_profile(
                    entry_point, document, "exchange-1x",
                    structural="valid", reference_context=EMPTY_CONTEXT,
                )
                self.assertEqual(outcome.routing, "selected")
                self.assertEqual(outcome.execution_status, "complete")
                actual = sorted((d.code, d.path) for d in outcome.diagnostics)
                self.assertEqual(actual, sorted(expected))
                self.assertTrue(all(d.severity == "warning" for d in outcome.diagnostics))


if __name__ == "__main__":
    unittest.main()
