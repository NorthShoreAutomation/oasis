"""The published examples pass every stage with no diagnostic.

Every example is a package (REC-2). A package resolves everything inside
itself, so each example gives no diagnostic at any stage, number limits
(DOC-4) included.
"""

import unittest
from pathlib import Path

from tests.conformance import validate
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.number_limits import check_number_limits
from tests.conformance.semantic import check
from tests.conformance.strict_json import parse_input

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"

EXAMPLE_NAMES = ("package-complete.json", "package-full.json", "package-minimal.json")


class ExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(DEFINITIONS)

    def test_example_set_is_exact(self):
        names = sorted(path.name for path in EXAMPLES.glob("*.json"))
        self.assertEqual(names, sorted(EXAMPLE_NAMES))

    def test_each_example_passes_every_stage(self):
        for name in EXAMPLE_NAMES:
            with self.subTest(example=name):
                parsed = parse_input((EXAMPLES / name).read_bytes())
                routing = route(parsed.value)
                self.assertEqual(routing.status, "selected")
                self.assertEqual(routing.kind, "package")
                self.assertEqual(routing.spec_version, "2.0.0-draft.3")
                self.assertEqual(check_number_limits(parsed.value, self.bundle.property_names), [])
                errors = self.bundle.entry_point(routing.kind).validate(parsed)
                self.assertEqual(errors, [])
                self.assertEqual(check(parsed.value, routing), [])

    def test_validate_command_accepts_each_example(self):
        for name in EXAMPLE_NAMES:
            with self.subTest(example=name):
                record = validate.evaluate((EXAMPLES / name).read_bytes(), DEFINITIONS)
                self.assertEqual(record["execution_status"], "complete")
                self.assertEqual(record["structural"], "valid")
                self.assertEqual(record["semantic"], "run")
                self.assertEqual(record["diagnostics"], [])
                self.assertEqual(validate.exit_code(record), 0)


if __name__ == "__main__":
    unittest.main()
