"""The published examples pass every stage with no diagnostic.

Every example is a package (REC-2). A package resolves everything inside
itself, so each example gives no diagnostic at any stage, number limits
(DOC-4) included.

The multi-file example folder holds the records of ``package-complete.json``
as a multi-file package, with one plain member file for each record list.
The two are equivalent under contract rule ``MFP-9``: the same root fields
other than ``manifest.members``, the same present and absent record lists,
and the same records in any order.
"""

import gzip
import tempfile
import unittest
from collections import Counter
from decimal import Decimal
from pathlib import Path

from tests.conformance import exact_json, multifile, validate
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.multifile_testing import member_entry
from tests.conformance.number_limits import check_number_limits
from tests.conformance.semantic import REGISTRIES, check
from tests.conformance.strict_json import parse_input

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"

EXAMPLE_NAMES = ("package-complete.json", "package-full.json", "package-minimal.json")

# The multi-file example folder, and the single document that it is equivalent to.
MULTI_FILE_EXAMPLE = EXAMPLES / "multi-file-complete"
MULTI_FILE_SOURCE = "package-complete.json"


def _canonical(value):
    """A hashable form of a parsed JSON value, equal for values that are the same JSON value.

    Numbers compare by value (``DOC-2``): an ``int`` and a ``Decimal`` with
    the same value are equal and hash the same. ``true`` and ``false`` stay
    apart from numbers. Strings compare by code points, with no normalization
    (``DOC-3``). Arrays keep their order; objects do not.
    """
    if value is None:
        return ("null",)
    if isinstance(value, bool):
        return ("boolean", value)
    if isinstance(value, (int, Decimal)):
        return ("number", value)
    if isinstance(value, str):
        return ("string", value)
    if isinstance(value, list):
        return ("array", tuple(_canonical(item) for item in value))
    return ("object", frozenset((key, _canonical(item)) for key, item in value.items()))


def _member_records(folder: Path, entry: dict) -> list:
    """The parsed records of one member file, one for each line."""
    data = (folder / entry["path"]).read_bytes()
    if entry["path"].endswith(".gz"):
        data = gzip.decompress(data)
    return [parse_input(line).value for line in data.split(b"\n")[:-1]]


def _equivalence_problems(single: dict, manifest_root: dict, folder: Path) -> list:
    """Return the ways in which a single document and a multi-file package differ (``MFP-9``).

    An empty list means that the two are equivalent.
    """
    problems = []
    members = manifest_root["manifest"]["members"]
    single_root = {key: value for key, value in single.items() if key not in REGISTRIES}
    multi_root = {key: value for key, value in manifest_root.items() if key not in REGISTRIES}
    multi_root["manifest"] = {key: value for key, value in multi_root["manifest"].items() if key != "members"}
    if _canonical(single_root) != _canonical(multi_root):
        problems.append("the root fields other than the record lists and members differ")
    for registry in REGISTRIES:
        entries = [entry for entry in members if entry["record_type"] == registry]
        if (registry in single) != bool(entries):
            problems.append(f"{registry}: present in one form and absent in the other")
            continue
        records = [record for entry in entries for record in _member_records(folder, entry)]
        if Counter(map(_canonical, single.get(registry, []))) != Counter(map(_canonical, records)):
            problems.append(f"{registry}: the records differ")
    return problems


class ExamplesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(DEFINITIONS)

    def test_example_set_is_exact(self):
        names = sorted(path.name for path in EXAMPLES.glob("*.json"))
        self.assertEqual(names, sorted(EXAMPLE_NAMES))
        folders = sorted(path.name for path in EXAMPLES.iterdir() if path.is_dir())
        self.assertEqual(folders, [MULTI_FILE_EXAMPLE.name])

    def test_each_example_passes_every_stage(self):
        for name in EXAMPLE_NAMES:
            with self.subTest(example=name):
                parsed = parse_input((EXAMPLES / name).read_bytes())
                routing = route(parsed.value)
                self.assertEqual(routing.status, "selected")
                self.assertEqual(routing.kind, "package")
                self.assertEqual(routing.spec_version, "2.0.0-draft.4")
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

    def test_draft3_example_passes_after_only_the_version_changes(self):
        data = (EXAMPLES / "package-full.json").read_bytes()
        record = validate.evaluate(data, DEFINITIONS)
        self.assertEqual(validate.exit_code(record), 0)
        # The same bytes with the draft.3 version string are unsupported: the version is the only difference.
        old = data.replace(b"2.0.0-draft.4", b"2.0.0-draft.3")
        self.assertNotEqual(old, data)
        self.assertEqual(validate.exit_code(validate.evaluate(old, DEFINITIONS)), 1)

    def test_multi_file_example_passes(self):
        manifest = MULTI_FILE_EXAMPLE / multifile.MANIFEST_NAME
        record = multifile.evaluate_folder(manifest, DEFINITIONS, None, multifile.ReadLimits(), from_folder=True)
        self.assertEqual(record["form"], validate.FORM_MULTI)
        self.assertEqual(record["execution_status"], "complete")
        self.assertEqual(record["structural"], "valid")
        self.assertEqual(record["semantic"], "run")
        self.assertEqual(record["diagnostics"], [])
        self.assertEqual(record["limitations"], [])
        self.assertEqual(validate.exit_code(record), 0)

    def test_examples_are_equivalent(self):
        single = parse_input((EXAMPLES / MULTI_FILE_SOURCE).read_bytes()).value
        manifest_root = parse_input((MULTI_FILE_EXAMPLE / multifile.MANIFEST_NAME).read_bytes()).value
        self.assertTrue(multifile.has_members(manifest_root))
        self.assertEqual(_equivalence_problems(single, manifest_root, MULTI_FILE_EXAMPLE), [])


class EquivalenceHelperTest(unittest.TestCase):
    """The equivalence helper finds each kind of difference, so the example test can fail."""

    def setUp(self):
        self.single = parse_input((EXAMPLES / "package-complete.json").read_bytes()).value
        self.root = {key: value for key, value in self.single.items() if key not in REGISTRIES}
        self.root["manifest"] = dict(self.root["manifest"], members=[])

    def test_numbers_compare_by_value_and_booleans_stay_apart(self):
        self.assertEqual(_canonical({"a": [1, Decimal("2.50")]}), _canonical({"a": [Decimal("1.0"), Decimal("2.5")]}))
        self.assertNotEqual(_canonical(True), _canonical(1))
        self.assertNotEqual(_canonical([1, 2]), _canonical([2, 1]))
        self.assertNotEqual(_canonical("é"), _canonical("é"))

    def test_lists_that_are_absent_in_one_form_differ(self):
        problems = _equivalence_problems(self.single, self.root, EXAMPLES)
        self.assertEqual(problems, [f"{registry}: present in one form and absent in the other" for registry in REGISTRIES])

    def test_a_changed_root_field_differs(self):
        single = dict(self.single, id="pkg-other")
        for registry in REGISTRIES:
            single.pop(registry)
        self.assertEqual(_equivalence_problems(single, self.root, EXAMPLES), [
            "the root fields other than the record lists and members differ",
        ])

    def _write_members(self, folder: Path, lists: dict) -> list:
        """Write one plain member file for each record list; return the member entries."""
        entries = []
        for registry, records in lists.items():
            path = f"{registry}/part-00001.jsonl"
            data = b"".join(exact_json.dumps(record).encode("utf-8") + b"\n" for record in records)
            (folder / registry).mkdir()
            (folder / path).write_bytes(data)
            entries.append(member_entry(path, data))
        return entries

    def test_records_compare_as_a_multiset(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            reordered = {registry: list(reversed(self.single[registry])) for registry in REGISTRIES}
            self.root["manifest"]["members"] = self._write_members(folder, reordered)
            self.assertEqual(_equivalence_problems(self.single, self.root, folder), [])

    def test_a_changed_record_differs(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            changed = {registry: list(self.single[registry]) for registry in REGISTRIES}
            changed["assets"][0] = dict(changed["assets"][0], title="Another title")
            self.root["manifest"]["members"] = self._write_members(folder, changed)
            self.assertEqual(_equivalence_problems(self.single, self.root, folder), ["assets: the records differ"])


if __name__ == "__main__":
    unittest.main()
