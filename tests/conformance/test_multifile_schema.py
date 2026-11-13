"""Schema tests for the manifest member list and the record-level validators."""

import copy
import json
import unittest
from pathlib import Path

from tests.conformance.loader import load_bundle
from tests.conformance.strict_json import parse_input
from tests.conformance.types import SetupFailed

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"

MEMBER = {
    "path": "assets/part-00001.jsonl",
    "record_type": "assets",
    "count": 1,
    "size_bytes": 10,
    "sha256": "0" * 64,
}
RECORD_ARRAYS = ("storage_locations", "metadata_definitions", "collections", "assets")


def _keywords(errors):
    """Return every failing keyword in errors, including nested contexts."""
    found = set()
    stack = list(errors)
    while stack:
        error = stack.pop()
        found.add(error.validator)
        stack.extend(error.context or ())
    return found


def _manifest_file(members=None):
    """A multi-file manifest file built from package-minimal.json: members, no record arrays."""
    document = json.loads((EXAMPLES / "package-minimal.json").read_text(encoding="utf-8"))
    for name in RECORD_ARRAYS:
        document.pop(name, None)
    document["manifest"]["members"] = [dict(MEMBER)] if members is None else members
    return document


class MultiFileSchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry = load_bundle(DEFINITIONS).entry_point("package")

    def errors(self, document):
        return self.entry.validate(parse_input(json.dumps(document).encode("utf-8")))

    def member_errors(self, **changes):
        member = dict(MEMBER)
        member.update(changes)
        return self.errors(_manifest_file([member]))

    def test_manifest_with_members_and_no_arrays_is_valid(self):
        self.assertEqual(self.errors(_manifest_file()), [])

    def test_manifest_with_empty_members_and_no_arrays_is_valid(self):
        self.assertEqual(self.errors(_manifest_file([])), [])

    def test_single_document_without_members_stays_valid(self):
        document = json.loads((EXAMPLES / "package-minimal.json").read_text(encoding="utf-8"))
        self.assertEqual(self.errors(document), [])
        document["assets"] = []
        self.assertEqual(self.errors(document), [])

    def test_members_and_a_record_array_is_invalid(self):
        for name in RECORD_ARRAYS:
            with self.subTest(array=name):
                document = _manifest_file()
                document[name] = []
                self.assertTrue(self.errors(document))

    def test_members_must_be_an_array(self):
        document = _manifest_file()
        document["manifest"]["members"] = {}
        self.assertIn("type", _keywords(self.errors(document)))

    def test_member_entry_rejects_unknown_key(self):
        member = dict(MEMBER, extra=1)
        self.assertIn("additionalProperties", _keywords(self.errors(_manifest_file([member]))))

    def test_member_entry_requires_every_field(self):
        for name in MEMBER:
            with self.subTest(field=name):
                member = {key: value for key, value in MEMBER.items() if key != name}
                self.assertIn("required", _keywords(self.errors(_manifest_file([member]))))

    def test_member_path_pattern(self):
        bad = [
            "assets/../x.jsonl",
            "/assets/x.jsonl",
            "assets/.x.jsonl",
            "assets//x.jsonl",
            "assets\\x.jsonl",
            "other/x.jsonl",
            "assets/x.json",
            "assets/x.zip",
            "assets/café.jsonl",
            "assets/x.jsonl\n",
            "assets/x.jsonl.gz.gz",
            "assets/.jsonl",
            "assets/x.jsonl/",
            "assets",
            "assets/",
            "assets/x y.jsonl",
            "Assets/x.jsonl",
        ]
        good = [
            "assets/x.jsonl",
            "assets/x.jsonl.gz",
            "assets/source=dalet/part-1.jsonl",
            "collections/_a.jsonl",
            "storage_locations/part-00001.jsonl",
            "metadata_definitions/a/b/c.d.jsonl.gz",
        ]
        for path in bad:
            with self.subTest(path=path):
                self.assertIn("pattern", _keywords(self.member_errors(path=path)))
        for path in good:
            with self.subTest(path=path):
                self.assertEqual(self.member_errors(path=path), [])

    def test_member_path_must_be_a_string(self):
        self.assertIn("type", _keywords(self.member_errors(path=1)))

    def test_member_sha256_is_64_lowercase_hex(self):
        for value in ("0" * 63, "0" * 65, "A" * 64, "g" * 64, ("0" * 63 + "F"), "0" * 64 + "\n", ""):
            with self.subTest(sha256=value):
                self.assertIn("pattern", _keywords(self.member_errors(sha256=value)))
        self.assertEqual(self.member_errors(sha256="0123456789abcdef" * 4), [])
        self.assertIn("type", _keywords(self.member_errors(sha256=0)))

    def test_record_type_enum(self):
        for value in ("asset", "Assets", "", "packages", "annotations"):
            with self.subTest(record_type=value):
                self.assertIn("enum", _keywords(self.member_errors(record_type=value)))
        for value in RECORD_ARRAYS:
            with self.subTest(record_type=value):
                self.assertEqual(self.member_errors(record_type=value), [])

    def test_count_and_size_are_non_negative_integers(self):
        for field in ("count", "size_bytes"):
            with self.subTest(field=field, case="negative"):
                self.assertIn("minimum", _keywords(self.member_errors(**{field: -1})))
            with self.subTest(field=field, case="fraction"):
                self.assertIn("type", _keywords(self.member_errors(**{field: 1.5})))
            with self.subTest(field=field, case="string"):
                self.assertIn("type", _keywords(self.member_errors(**{field: "1"})))
            with self.subTest(field=field, case="zero"):
                self.assertEqual(self.member_errors(**{field: 0}), [])
            with self.subTest(field=field, case="large"):
                self.assertEqual(self.member_errors(**{field: 10**12}), [])

    def test_members_can_list_several_files(self):
        members = [
            dict(MEMBER, path="assets/part-00001.jsonl"),
            dict(MEMBER, path="assets/part-00002.jsonl.gz"),
            dict(MEMBER, path="collections/part-00001.jsonl", record_type="collections"),
        ]
        self.assertEqual(self.errors(_manifest_file(members)), [])


class RecordEntryPointTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(DEFINITIONS)

    def test_record_entry_point_validates_one_record(self):
        asset = parse_input(b'{"id": "a-1", "title": "T"}')
        self.assertEqual(self.bundle.record_entry_point("assets").validate(asset), [])
        bad = parse_input(b'{"id": "a-1"}')
        self.assertTrue(self.bundle.record_entry_point("assets").validate(bad))

    def test_every_record_type_has_an_entry_point(self):
        for record_type in RECORD_ARRAYS:
            with self.subTest(record_type=record_type):
                entry = self.bundle.record_entry_point(record_type)
                self.assertTrue(entry.validate(parse_input(b"[]")))

    def test_each_record_type_validates_its_own_schema(self):
        document = json.loads((EXAMPLES / "package-complete.json").read_text(encoding="utf-8"))
        for record_type in RECORD_ARRAYS:
            records = document[record_type]
            self.assertTrue(records, record_type)
            for index, record in enumerate(records):
                with self.subTest(record_type=record_type, index=index):
                    parsed = parse_input(json.dumps(record).encode("utf-8"))
                    self.assertEqual(self.bundle.record_entry_point(record_type).validate(parsed), [])

    def test_record_entry_points_are_not_interchangeable(self):
        document = json.loads((EXAMPLES / "package-complete.json").read_text(encoding="utf-8"))
        asset = parse_input(json.dumps(document["assets"][0]).encode("utf-8"))
        self.assertTrue(self.bundle.record_entry_point("collections").validate(asset))

    def test_record_is_checked_with_the_record_schema_rules(self):
        record = copy.deepcopy(json.loads((EXAMPLES / "package-complete.json").read_text(encoding="utf-8"))["assets"][0])
        record["unknown_field"] = 1
        errors = self.bundle.record_entry_point("assets").validate(parse_input(json.dumps(record).encode("utf-8")))
        self.assertIn("unevaluatedProperties", _keywords(errors))

    def test_unknown_record_type_raises_setup_failed(self):
        for value in ("asset", "package", "", None, 1):
            with self.subTest(value=value):
                with self.assertRaises(SetupFailed):
                    self.bundle.record_entry_point(value)

    def test_validate_refuses_a_value_that_is_not_parsed_input(self):
        with self.assertRaises(TypeError):
            self.bundle.record_entry_point("assets").validate({"id": "a-1", "title": "T"})


if __name__ == "__main__":
    unittest.main()
