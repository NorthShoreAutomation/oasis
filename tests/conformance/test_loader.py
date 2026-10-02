"""Tests for the offline schema loader and the Python structural adapter."""

import copy
import hashlib
import json
import socket
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tests.conformance import loader
from tests.conformance.loader import load_schema, validate_legacy
from tests.conformance.strict_json import parse_input
from tests.conformance.types import SetupFailed

REPO = Path(__file__).resolve().parents[2]
CURRENT = REPO / "definitions"
FROZEN = REPO / "tests" / "conformance" / "baseline"
FIXTURES = REPO / "tests" / "conformance" / "fixtures"
RECORDS = FIXTURES / "records"


def record(name):
    return parse_input((RECORDS / name).read_bytes())


def doc(text):
    return parse_input(text.encode("utf-8"))


def manifest_cases():
    return json.loads((FIXTURES / "manifest.json").read_bytes())["cases"]


class _NoSocket:
    """Stand-in for socket.socket that records and refuses every use."""

    calls = 0

    def __init__(self, *args, **kwargs):
        type(self).calls += 1
        raise AssertionError("network socket was opened")


class _TempBundleMixin:
    """Build a one-off bundle in a temporary directory."""

    def make_bundle(self, schemas, revision="test-1"):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        entries = []
        for name, schema in schemas.items():
            text = schema if isinstance(schema, str) else json.dumps(schema, indent=2) + "\n"
            data = text.encode("utf-8")
            (root / name).write_bytes(data)
            entries.append(
                {
                    "name": name,
                    "path": name,
                    "sha256": hashlib.sha256(data).hexdigest(),
                    "id": None,
                    "base_uri": "https://schemas.oasis.invalid/bundles/%s/%s" % (revision, name),
                    "aliases": [],
                }
            )
        manifest = {"manifest_version": "1.0.0", "bundle_revision": revision, "schemas": entries}
        (root / "bundle-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return root


class LoadSchemaTest(unittest.TestCase):
    def test_loads_exact_tree(self):
        schema = load_schema("temporal_annotation.schema.json", CURRENT)
        self.assertIsInstance(schema, dict)
        minimum = schema["properties"]["start_frame"]["minimum"]
        self.assertEqual(minimum, 0)
        self.assertIs(type(minimum), int)

    def test_unknown_name_fails_setup(self):
        with self.assertRaises(SetupFailed):
            load_schema("nope.schema.json", CURRENT)

    def test_frozen_and_current_do_not_share_a_registry(self):
        frozen = loader._bundle(FROZEN)
        current = loader._bundle(CURRENT)
        self.assertIsNot(frozen, current)
        self.assertIsNot(frozen.registry, current.registry)
        self.assertIs(loader._bundle(CURRENT), current)
        for root in (FROZEN, CURRENT):
            with self.subTest(root=root.name):
                self.assertEqual(validate_legacy("asset.schema.json", record("minimal-asset.json"), root=root), [])


class ContextTest(unittest.TestCase):
    def validate(self, schema, name):
        return validate_legacy(schema, record(name), root=CURRENT)

    def test_metadata_set_id_standalone_optional_embedded_required(self):
        self.assertEqual(self.validate("metadata_set.schema.json", "standalone-metadata-value.json"), [])
        errors = self.validate("asset.schema.json", "embedded-metadata-missing-id.json")
        self.assertTrue(any(e.validator == "required" and "set_id" in e.validator_value for e in errors))

    def test_membership_items_standalone_strings_embedded_open(self):
        self.assertNotEqual(self.validate("collection.schema.json", "standalone-object-membership.json"), [])
        self.assertEqual(self.validate("asset.schema.json", "embedded-object-membership.json"), [])

    def test_file_keys_are_closed(self):
        errors = self.validate("asset.schema.json", "file-filename-closed.json")
        self.assertTrue(any(e.validator == "additionalProperties" for e in errors))


class DateTimeTest(_TempBundleMixin, unittest.TestCase):
    def check(self, value, check_formats=True):
        text = json.dumps({"asset_id": "a", "title": "t", "type": "video", "created_date": value})
        return validate_legacy("asset.schema.json", doc(text), root=CURRENT, check_formats=check_formats) == []

    def test_on_and_off(self):
        self.assertFalse(self.check("not-a-date"))
        self.assertTrue(self.check("not-a-date", check_formats=False))

    def test_every_corpus_date_time_case(self):
        cases = [c for c in manifest_cases() if c["id"].startswith("exchange-date-") or c["id"] == "asset-invalid-date"]
        self.assertEqual(len(cases), 8)
        for case in cases:
            expected = case["validator_expectations"]["python-jsonschema"]
            for mode, check_formats in (("required", True), ("historical-unchecked", False)):
                with self.subTest(case=case["id"], mode=mode):
                    document = parse_input((FIXTURES / case["path"]).read_bytes())
                    errors = validate_legacy(case["schema_name"], document, root=CURRENT, check_formats=check_formats)
                    self.assertEqual(errors == [], expected[mode])

    def test_grammar_accepts(self):
        for value in (
            "2024-02-29T00:00:00Z",
            "2000-02-29T23:59:59z",
            "0001-01-01t00:00:00Z",
            "9999-12-31T23:59:59.9+23:59",
            "2026-09-29T12:00:00-00:00",
            "2026-09-29T12:00:00.000000000000001Z",
        ):
            with self.subTest(value=value):
                self.assertTrue(self.check(value))

    def test_grammar_rejects(self):
        for value in (
            "2023-02-29T00:00:00Z",
            "1900-02-29T00:00:00Z",
            "0000-01-01T00:00:00Z",
            "2026-13-01T00:00:00Z",
            "2026-00-01T00:00:00Z",
            "2026-04-31T00:00:00Z",
            "2026-09-29T24:00:00Z",
            "2026-09-29T12:60:00Z",
            "2026-09-29T12:00:60Z",
            "2026-09-29T12:00:00.Z",
            "2026-09-29T12:00:00+24:00",
            "2026-09-29T12:00:00+01:60",
            "2026-09-29T12:00:00",
            "2026-09-29T12:00:00+01",
            "2026-09-29 12:00:00Z",
            "2026-09-29T12:00:00Z\n",
            "\n2026-09-29T12:00:00Z",
            "20260-09-29T12:00:00Z",
            "2026-09-29T12:00Z",
            "２026-09-29T12:00:00Z",
            "2026-09-29T12:00:00.١Z",
        ):
            with self.subTest(value=value):
                self.assertFalse(self.check(value))

    def test_non_string_passes_format(self):
        schema = {"type": ["string", "number"], "format": "date-time"}
        root = self.make_bundle({"t.schema.json": schema})
        self.assertEqual(validate_legacy("t.schema.json", doc("5"), root=root), [])
        self.assertNotEqual(validate_legacy("t.schema.json", doc('"x"'), root=root), [])

    def test_missing_rfc3339_validator_fails_setup(self):
        loader._bundle.cache_clear()
        self.addCleanup(loader._bundle.cache_clear)
        with mock.patch.dict(sys.modules, {"rfc3339_validator": None}):
            with self.assertRaises(SetupFailed):
                validate_legacy("asset.schema.json", record("minimal-asset.json"), root=CURRENT)

    def test_date_time_checker_is_registered(self):
        checker = loader._bundle(CURRENT).format_checker
        self.assertIn("date-time", checker.checkers)


class PatternTest(_TempBundleMixin, unittest.TestCase):
    def test_corpus_pattern_cases_in_both_modes(self):
        ids = {
            "exchange-timecode-pattern-newline",
            "exchange-timecode-pattern-unicode-digits",
            "legacy-report-pattern-newline",
            "legacy-report-pattern-unicode-digits",
        }
        cases = [c for c in manifest_cases() if c["id"] in ids]
        self.assertEqual(len(cases), 4)
        for case in cases:
            for check_formats in (True, False):
                with self.subTest(case=case["id"], check_formats=check_formats):
                    document = parse_input((FIXTURES / case["path"]).read_bytes())
                    errors = validate_legacy(case["schema_name"], document, root=CURRENT, check_formats=check_formats)
                    self.assertTrue(any(e.validator == "pattern" for e in errors))

    def annotation(self, timecode, check_formats=True):
        text = json.dumps({"source_id": "a", "is_point_marker": True, "start_timecode": timecode})
        return validate_legacy("temporal_annotation.schema.json", doc(text), root=CURRENT, check_formats=check_formats)

    def test_timecode_ascii_digits_and_absolute_end(self):
        for check_formats in (True, False):
            for good in ("01:00:00", "1:00:00", "01:00:00:12", "01:00:00'12", "01:00:00.12"):
                with self.subTest(good=good, check_formats=check_formats):
                    self.assertEqual(self.annotation(good, check_formats), [])
            for bad in ("01:00:00\n", "١:00:00", "01:00:0٠", "01:00:00:123", "x01:00:00"):
                with self.subTest(bad=bad, check_formats=check_formats):
                    self.assertNotEqual(self.annotation(bad, check_formats), [])

    def report(self, **changes):
        data = json.loads((RECORDS / "minimal-migration-report-output.json").read_bytes())
        data.update(changes)
        return doc(json.dumps(data))

    def test_report_fields_ascii_digits_and_absolute_end(self):
        name = "migration-report-output.schema.json"
        for check_formats in (True, False):
            with self.subTest(check_formats=check_formats):
                self.assertEqual(validate_legacy(name, self.report(), root=CURRENT, check_formats=check_formats), [])
                for changes in (
                    {"report_id": "20260929_120000\n"},
                    {"report_id": "2026092٩_120000"},
                    {"report_version": "1.0.0\n"},
                    {"report_version": "1.٠.0"},
                ):
                    errors = validate_legacy(name, self.report(**changes), root=CURRENT, check_formats=check_formats)
                    self.assertTrue(any(e.validator == "pattern" for e in errors), changes)

    def test_extension_keys_use_translated_pattern(self):
        name = "migration-report-output.schema.json"
        self.assertEqual(validate_legacy(name, self.report(extensions={"x_a": 1}), root=CURRENT), [])
        errors = validate_legacy(name, self.report(extensions={"y_a": 1}), root=CURRENT)
        self.assertTrue(any(e.validator == "additionalProperties" for e in errors))
        errors = validate_legacy(name, self.report(extensions={"\nx_a": 1}), root=CURRENT)
        self.assertTrue(any(e.validator == "additionalProperties" for e in errors))

    def test_unlisted_pattern_fails_at_setup(self):
        root = self.make_bundle({"t.schema.json": {"properties": {"a": {"pattern": "^a$"}}}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_unlisted_pattern_property_fails_at_setup(self):
        root = self.make_bundle({"t.schema.json": {"patternProperties": {"^y_": {}}}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_pattern_under_definitions_fails_at_setup(self):
        root = self.make_bundle({"t.schema.json": {"definitions": {"d": {"pattern": "[a-z]"}}}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_pattern_named_property_is_data_not_assertion(self):
        root = self.make_bundle({"t.schema.json": {"properties": {"pattern": {"type": "string"}}}})
        self.assertEqual(validate_legacy("t.schema.json", doc('{"pattern": "[unclosed"}'), root=root), [])


class SetupGuardTest(_TempBundleMixin, unittest.TestCase):
    def test_multiple_of_fails_setup(self):
        root = self.make_bundle({"t.schema.json": {"properties": {"a": {"multipleOf": 0.01}}}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_bundle_has_no_multiple_of(self):
        for root in (FROZEN, CURRENT):
            with self.subTest(root=root.name):
                loader._bundle(root)

    def test_missing_resource_fails_setup(self):
        root = self.make_bundle({"t.schema.json": {"properties": {"a": {"$ref": "./missing.schema.json"}}}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_missing_fragment_fails_setup(self):
        root = self.make_bundle({"t.schema.json": {"$ref": "#/definitions/Nope"}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_network_reference_fails_setup_without_socket(self):
        root = self.make_bundle({"t.schema.json": {"$ref": "https://example.com/remote.schema.json"}})
        _NoSocket.calls = 0
        with mock.patch.object(socket, "socket", _NoSocket):
            with self.assertRaises(SetupFailed):
                validate_legacy("t.schema.json", doc("{}"), root=root)
        self.assertEqual(_NoSocket.calls, 0)

    def test_metaschema_reference_is_not_a_bundle_resource(self):
        root = self.make_bundle({"t.schema.json": {"$ref": "http://json-schema.org/draft-07/schema#"}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_batch_references_resolve_offline(self):
        _NoSocket.calls = 0
        with mock.patch.object(socket, "socket", _NoSocket):
            for root in (FROZEN, CURRENT):
                loader._bundle.cache_clear()
                for schema, good, bad in (
                    ("asset_batch_import.schema.json", "minimal-asset_batch_import.json", "missing-required-asset_batch_import.json"),
                    ("collection_batch_import.schema.json", "minimal-collection_batch_import.json", "missing-required-collection_batch_import.json"),
                ):
                    with self.subTest(root=root.name, schema=schema):
                        self.assertEqual(validate_legacy(schema, record(good), root=root), [])
                        self.assertNotEqual(validate_legacy(schema, record(bad), root=root), [])
        self.assertEqual(_NoSocket.calls, 0)

    def test_batch_items_are_checked_through_reference(self):
        text = json.dumps({"assets": [{"asset_id": "a", "title": "t", "type": "video", "created_date": "bad"}]})
        errors = validate_legacy("asset_batch_import.schema.json", doc(text), root=CURRENT)
        self.assertTrue(any(e.validator == "format" for e in errors))

    def test_referenced_roots_keep_the_extended_validator(self):
        # The referenced asset root declares $schema. The exact-number type
        # checker must still apply after crossing that reference.
        template = (
            '{"assets": [{"asset_id": "a", "title": "t", "type": "video", "temporal_annotations":'
            ' [{"source_id": "a", "is_point_marker": true, "start_frame": FRAME}]}]}'
        )
        name = "asset_batch_import.schema.json"
        self.assertEqual(validate_legacy(name, doc(template.replace("FRAME", "1.0")), root=CURRENT), [])
        self.assertNotEqual(validate_legacy(name, doc(template.replace("FRAME", "1.5")), root=CURRENT), [])

    def test_extended_checks_hold_across_relative_draft7_reference(self):
        # Both schemas declare Draft 7, so the stock evolve would switch back
        # to the stock validator after the reference. The pattern, integer,
        # and patternProperties cases differ under the stock checks: stock
        # patterns match Unicode digits and a final newline, and the stock
        # type checker rejects Decimal 1.0 as an integer. The date-time
        # checker must also still apply behind the reference.
        draft7 = "http://json-schema.org/draft-07/schema#"
        target = {
            "$schema": draft7,
            "type": "object",
            "properties": {
                "id": {"type": "string", "pattern": r"^\d{8}_\d{6}$"},
                "count": {"type": "integer"},
                "when": {"type": "string", "format": "date-time"},
                "tags": {
                    "type": "object",
                    "patternProperties": {r"^\d{8}_\d{6}$": {"type": "integer"}},
                    "additionalProperties": False,
                },
            },
        }
        root = self.make_bundle({"a.json": {"$schema": draft7, "$ref": "./b.json"}, "b.json": target})
        good = (
            '{"id": "20260929_120000", "count": 1.0, "when": "2026-09-29T12:00:00Z",'
            ' "tags": {"20260929_120000": 2.0}}'
        )
        for check_formats in (True, False):
            with self.subTest(check_formats=check_formats):
                self.assertEqual(validate_legacy("a.json", doc(good), root=root, check_formats=check_formats), [])
        for bad, keyword in (
            ('{"id": "2026092\u0669_120000"}', "pattern"),
            ('{"id": "20260929_120000\\n"}', "pattern"),
            ('{"tags": {"2026092\u0669_120000": 1}}', "additionalProperties"),
            ('{"tags": {"20260929_120000": 1.5}}', "type"),
            ('{"count": 1.5}', "type"),
            ('{"count": true}', "type"),
        ):
            for check_formats in (True, False):
                with self.subTest(bad=bad, check_formats=check_formats):
                    errors = validate_legacy("a.json", doc(bad), root=root, check_formats=check_formats)
                    self.assertEqual([e.validator for e in errors], [keyword])
        errors = validate_legacy("a.json", doc('{"when": "2026-09-29T12:00:00"}'), root=root)
        self.assertEqual([e.validator for e in errors], ["format"])
        self.assertEqual(
            validate_legacy("a.json", doc('{"when": "2026-09-29T12:00:00"}'), root=root, check_formats=False), []
        )

    def test_other_dialect_fails_setup(self):
        root = self.make_bundle({"t.schema.json": {"$schema": "https://json-schema.org/draft/2020-12/schema"}})
        with self.assertRaises(SetupFailed):
            loader._bundle(root)

    def test_non_parsed_input_is_rejected(self):
        for value in ({"asset_id": "a"}, b"{}", "{}", None):
            with self.subTest(value=type(value).__name__):
                with self.assertRaises(TypeError):
                    validate_legacy("asset.schema.json", value, root=CURRENT)


class ReviewRegressionTest(_TempBundleMixin, unittest.TestCase):
    """Regressions for setup classification."""

    def test_deep_derivative_nesting_fails_setup_without_echo(self):
        text = '{"type": "video", "role": "SECRETROLE", "uri": "u"}'
        for _ in range(200):
            text = '{"type": "video", "role": "SECRETROLE", "uri": "u", "derivatives": [%s]}' % text
        document = doc('{"asset_id": "a", "title": "t", "type": "video", "files": [%s]}' % text)
        with self.assertRaises(SetupFailed) as caught:
            validate_legacy("asset.schema.json", document, root=CURRENT)
        self.assertEqual(str(caught.exception), "validation nesting exceeds the Python interpreter recursion limit")
        self.assertNotIn("SECRETROLE", str(caught.exception))

    def test_invalid_draft7_schema_fails_setup(self):
        root = self.make_bundle({"t.schema.json": {"$schema": "http://json-schema.org/draft-07/schema#", "type": 5}})
        with self.assertRaises(SetupFailed) as caught:
            loader._bundle(root)
        self.assertEqual(str(caught.exception), "schema does not conform to the Draft 7 metaschema")
        with self.assertRaises(SetupFailed):
            validate_legacy("t.schema.json", doc("{}"), root=root)

    def test_exact_number_bounds_pass_the_metaschema(self):
        root = self.make_bundle({"t.schema.json": (
            '{"type": "object", "properties": {"a": {"type": "number", "minimum": 0.5, "maximum": 1e3},'
            ' "b": {"type": "string", "maxLength": 12}}}\n'
        )})
        schema = loader._bundle(root).schemas["t.schema.json"]
        self.assertIs(type(schema["properties"]["a"]["minimum"]), Decimal)
        self.assertEqual(validate_legacy("t.schema.json", doc('{"a": 0.75}'), root=root), [])

    def test_integral_decimal_limits_pass_the_metaschema_at_any_depth(self):
        placements = {
            "properties": '{"type": "object", "properties": {"a": {"type": "string", "maxLength": LIMIT}}}',
            "items": '{"type": "array", "items": {"type": "array", "minItems": LIMIT}}',
            "definitions": '{"definitions": {"d": {"type": "string", "maxLength": LIMIT}}, "$ref": "#/definitions/d"}',
        }
        for place, template in placements.items():
            for limit in ("1.0", "1e0"):
                with self.subTest(place=place, limit=limit):
                    root = self.make_bundle({"t.schema.json": template.replace("LIMIT", limit) + "\n"})
                    self.assertIn("t.schema.json", loader._bundle(root).schemas)

    def test_non_integral_limit_fails_the_metaschema(self):
        for place, template in (
            ("top", '{"maxLength": 1.5}'),
            ("properties", '{"properties": {"a": {"maxLength": 1.5}}}'),
        ):
            with self.subTest(place=place):
                root = self.make_bundle({"t.schema.json": template + "\n"})
                with self.assertRaises(SetupFailed):
                    loader._bundle(root)

    def test_shipped_bundles_pass_the_metaschema(self):
        for root in (FROZEN, CURRENT):
            with self.subTest(root=root.name):
                loader._bundle.cache_clear()
                self.assertTrue(loader._bundle(root).schemas)

    def test_unknown_entry_point_fails_setup_without_input(self):
        bundle = loader.load_bundle(CURRENT)
        with self.assertRaises(SetupFailed):
            bundle.entry_point("nope.schema.json", check_formats=True)
        self.assertIsNotNone(bundle.entry_point("asset.schema.json", check_formats=True))

    def test_cached_bundle_follows_manifest_changes(self):
        root = self.make_bundle({"t.schema.json": {"type": "object"}})
        self.assertEqual(validate_legacy("t.schema.json", doc("{}"), root=root), [])
        data = (json.dumps({"type": "string"}) + "\n").encode("utf-8")
        (root / "t.schema.json").write_bytes(data)
        # Schema bytes changed but the manifest was not updated: setup fails.
        with self.assertRaises(SetupFailed):
            validate_legacy("t.schema.json", doc("{}"), root=root)
        manifest = json.loads((root / "bundle-manifest.json").read_bytes())
        manifest["schemas"][0]["sha256"] = hashlib.sha256(data).hexdigest()
        (root / "bundle-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertNotEqual(validate_legacy("t.schema.json", doc("{}"), root=root), [])


class ExactNumberTest(_TempBundleMixin, unittest.TestCase):
    def annotation(self, fields):
        body = ", ".join('"%s": %s' % item for item in fields.items())
        text = '{"source_id": "a", "is_point_marker": true, %s}' % body
        return validate_legacy("temporal_annotation.schema.json", doc(text), root=CURRENT)

    def test_tiny_negative_is_below_minimum(self):
        # Binary64 rounds -1E-400 to -0.0, which would pass minimum 0.
        self.assertNotEqual(self.annotation({"start_seconds": "-1E-400"}), [])
        self.assertEqual(self.annotation({"start_seconds": "0E-400"}), [])
        self.assertEqual(self.annotation({"start_seconds": "-0"}), [])

    def test_rates_and_large_integers(self):
        for value in ("23.976", "29.97", "59.94", "1E+400"):
            with self.subTest(value=value):
                self.assertEqual(self.annotation({"start_seconds": "0", "frame_rate": value}), [])
        for value in ("9007199254740993", "123456789012345678901234567890", "1.0", "1E+3", "2.50E+1"):
            with self.subTest(value=value):
                self.assertEqual(self.annotation({"start_frame": value}), [])
        for value in ("1.5", "1E-1", "9007199254740993.5", "true"):
            with self.subTest(value=value):
                self.assertNotEqual(self.annotation({"start_frame": value}), [])
        self.assertNotEqual(self.annotation({"start_frame": "-1"}), [])
        self.assertNotEqual(self.annotation({"start_seconds": "true"}), [])

    def test_decimal_bound_against_large_integer(self):
        root = self.make_bundle({"t.schema.json": '{"minimum": 9007199254740992.5, "maximum": 9007199254740993}'})
        schema = loader._bundle(root).schemas["t.schema.json"]
        self.assertEqual(schema["minimum"], Decimal("9007199254740992.5"))
        self.assertEqual(validate_legacy("t.schema.json", doc("9007199254740993"), root=root), [])
        self.assertNotEqual(validate_legacy("t.schema.json", doc("9007199254740992"), root=root), [])
        self.assertNotEqual(validate_legacy("t.schema.json", doc("9007199254740993.0000000000000001"), root=root), [])

    def test_enum_and_const_equality(self):
        root = self.make_bundle({"t.schema.json": {"enum": [1, False, 2.5]}})
        for good in ("1", "1.0", "1E0", "false", "2.50", "25E-1"):
            with self.subTest(good=good):
                self.assertEqual(validate_legacy("t.schema.json", doc(good), root=root), [])
        for bad in ("true", "0", "0.0", "1.0000000000000000000001", '"1"'):
            with self.subTest(bad=bad):
                self.assertNotEqual(validate_legacy("t.schema.json", doc(bad), root=root), [])
        root = self.make_bundle({"c.schema.json": {"const": False}}, revision="test-2")
        self.assertEqual(validate_legacy("c.schema.json", doc("false"), root=root), [])
        self.assertNotEqual(validate_legacy("c.schema.json", doc("0"), root=root), [])


class NoMutationTest(unittest.TestCase):
    def test_defaults_are_not_inserted(self):
        for schema, name in (
            ("asset.schema.json", "embedded-token-absent.json"),
            ("temporal_annotation.schema.json", "annotation-token-absent.json"),
            ("asset_batch_import.schema.json", "batch-token-absent.json"),
        ):
            with self.subTest(name=name):
                document = record(name)
                before = copy.deepcopy(document.value)
                self.assertEqual(validate_legacy(schema, document, root=CURRENT), [])
                self.assertEqual(document.value, before)
                self.assertNotIn("annotation_type", json.dumps(document.value))

    def test_schema_tree_is_not_mutated(self):
        schema = load_schema("temporal_annotation.schema.json", CURRENT)
        before = copy.deepcopy(schema)
        validate_legacy("temporal_annotation.schema.json", record("minimal-temporal_annotation.json"), root=CURRENT)
        self.assertEqual(load_schema("temporal_annotation.schema.json", CURRENT), before)


if __name__ == "__main__":
    unittest.main()
