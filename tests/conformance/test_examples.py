"""The published examples pass every stage with exactly the expected diagnostics.

A standalone record cannot see its owning asset or its metadata definitions,
so some examples carry the two standalone warnings. The package examples
resolve everything inside themselves and give no diagnostic.
"""

import unittest
from pathlib import Path

from tests.conformance import validate
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.semantic import check
from tests.conformance.strict_json import parse_input

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"

# Sorted (code, path) pairs that check returns for each example.
EXPECTED = {
    "annotation-full.json": [
        ("DEFINITION_UNAVAILABLE", "/metadata/0"),
        ("TIMELINE_UNAVAILABLE", ""),
    ],
    "annotation-minimal.json": [],
    "asset-full.json": [
        ("DEFINITION_UNAVAILABLE", "/annotations/0/metadata/0"),
        ("DEFINITION_UNAVAILABLE", "/metadata/0"),
        ("DEFINITION_UNAVAILABLE", "/metadata/1"),
        ("DEFINITION_UNAVAILABLE", "/metadata/2"),
        ("TIMELINE_UNAVAILABLE", "/relationships/1/range"),
    ],
    "asset-minimal.json": [],
    "collection-full.json": [("DEFINITION_UNAVAILABLE", "/metadata/0")],
    "collection-minimal.json": [],
    "metadata_definition-full.json": [],
    "metadata_definition-minimal.json": [],
    "storage_location-full.json": [],
    "storage_location-minimal.json": [],
    "package-minimal.json": [],
    "package-full.json": [],
    "package-complete.json": [],
}


class ExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(DEFINITIONS)

    def test_example_set_is_exact(self):
        names = sorted(path.name for path in EXAMPLES.glob("*.json"))
        self.assertEqual(names, sorted(EXPECTED))

    def test_each_example_passes_every_stage(self):
        for name, expected in EXPECTED.items():
            with self.subTest(example=name):
                parsed = parse_input((EXAMPLES / name).read_bytes())
                routing = route(parsed.value)
                self.assertEqual(routing.status, "selected")
                self.assertEqual(routing.kind, name.split("-", 1)[0])
                errors = self.bundle.entry_point(routing.kind).validate(parsed)
                self.assertEqual(errors, [])
                found = sorted((d.code, d.path) for d in check(parsed.value, routing))
                self.assertEqual(found, sorted(expected))

    def test_validate_command_accepts_each_example(self):
        for name in EXPECTED:
            with self.subTest(example=name):
                record = validate.evaluate((EXAMPLES / name).read_bytes(), DEFINITIONS)
                self.assertEqual(record["execution_status"], "complete")
                self.assertEqual(record["structural"], "valid")
                self.assertEqual(validate.exit_code(record), 0)


if __name__ == "__main__":
    unittest.main()
