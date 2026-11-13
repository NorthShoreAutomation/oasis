"""Tests for the offline 2020-12 bundle loader."""

import hashlib
import json
import shutil
import socket
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

import referencing.exceptions

from tests.conformance import loader
from tests.conformance.bundle import MANIFEST_NAME
from tests.conformance.loader import (
    check_date,
    check_date_time,
    check_regex,
    check_uri,
    load_bundle,
)
from tests.conformance.strict_json import parse_input
from tests.conformance.types import SetupFailed

REPO = Path(__file__).resolve().parents[2]
DEFINITIONS = REPO / "definitions"
EXAMPLES = DEFINITIONS / "examples"


def _example(name):
    return json.loads((EXAMPLES / name).read_text(encoding="utf-8"))


def _doc(value):
    return parse_input(json.dumps(value).encode("utf-8"))


def _keywords(errors):
    """Return every failing keyword in errors, including nested contexts."""
    found = set()
    stack = list(errors)
    while stack:
        error = stack.pop()
        found.add(error.validator)
        stack.extend(error.context or ())
    return found


class _CopiedBundleMixin:
    """Copy the real bundle to a temporary directory and change one schema."""

    def copied_bundle(self, schema_name, mutate):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        manifest = json.loads((DEFINITIONS / MANIFEST_NAME).read_text(encoding="utf-8"))
        for entry in manifest["schemas"]:
            data = (DEFINITIONS / entry["path"]).read_bytes()
            if entry["name"] == schema_name:
                tree = json.loads(data)
                mutate(tree)
                data = (json.dumps(tree, indent=2) + "\n").encode("utf-8")
                entry["sha256"] = hashlib.sha256(data).hexdigest()
            (root / entry["path"]).write_bytes(data)
        (root / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        return root


class BundleLoadTests(unittest.TestCase):
    def test_bundle_loads_from_definitions(self):
        bundle = load_bundle(DEFINITIONS)
        self.assertEqual(bundle.root, DEFINITIONS.resolve())
        self.assertEqual(len(bundle.manifest_sha256), 64)
        self.assertEqual(bundle.manifest.document_roots[0], "package")

    def test_bundle_is_cached(self):
        self.assertIs(load_bundle(DEFINITIONS), load_bundle(DEFINITIONS))

    def test_package_minimal_is_valid(self):
        entry = load_bundle(DEFINITIONS).entry_point("package")
        self.assertEqual(entry.kind, "package")
        document = parse_input((EXAMPLES / "package-minimal.json").read_bytes())
        self.assertEqual(entry.validate(document), [])

    def test_package_is_the_only_document_root(self):
        self.assertEqual(load_bundle(DEFINITIONS).manifest.document_roots, ("package",))
        for kind in ("asset", "collection", "storage_location", "metadata_definition"):
            with self.subTest(kind=kind):
                with self.assertRaises(SetupFailed):
                    load_bundle(DEFINITIONS).entry_point(kind)

    def test_every_example_is_valid_for_its_kind(self):
        bundle = load_bundle(DEFINITIONS)
        paths = sorted(EXAMPLES.glob("*.json"))
        self.assertEqual([p.stem for p in paths], ["package-complete", "package-full", "package-minimal"])
        for path in paths:
            document = parse_input(path.read_bytes())
            kind = document.value["type"]
            with self.subTest(example=path.name):
                errors = bundle.entry_point(kind).validate(document)
                self.assertEqual(
                    [(list(e.absolute_path), e.validator, e.message) for e in errors], []
                )

    def test_common_is_not_a_document_root(self):
        with self.assertRaises(SetupFailed):
            load_bundle(DEFINITIONS).entry_point("common")

    def test_unknown_kind_is_refused(self):
        with self.assertRaises(SetupFailed):
            load_bundle(DEFINITIONS).entry_point("nothing")

    def test_validate_requires_parsed_input(self):
        entry = load_bundle(DEFINITIONS).entry_point("package")
        with self.assertRaises(TypeError):
            entry.validate(_example("package-minimal.json"))


class FileRoleTests(unittest.TestCase):
    def test_file_roles_in_packages_and_member_records(self):
        bundle = load_bundle(DEFINITIONS)
        for role in ("original", "master", "mezzanine", "preview", "thumbnail", "sidecar", "other"):
            with self.subTest(role=role):
                asset = {"id": "a-1", "title": "T", "files": [{"id": "f-1", "role": role}]}
                package = _example("package-minimal.json")
                package["assets"] = [asset]
                self.assertEqual(bundle.entry_point("package").validate(_doc(package)), [])
                self.assertEqual(bundle.record_entry_point("assets").validate(_doc(asset)), [])

    def test_unknown_file_roles_are_rejected(self):
        entry = load_bundle(DEFINITIONS).record_entry_point("assets")
        for role in ("source", "Original", "original ", ""):
            with self.subTest(role=role):
                asset = {"id": "a-1", "title": "T", "files": [{"id": "f-1", "role": role}]}
                self.assertIn("enum", _keywords(entry.validate(_doc(asset))))


class RecordEntryPointTests(_CopiedBundleMixin, unittest.TestCase):
    ASSET = b'{"id": "a-1", "title": "T"}'

    def test_entry_point_kind_is_the_record_type(self):
        bundle = load_bundle(DEFINITIONS)
        for record_type in ("storage_locations", "metadata_definitions", "collections", "assets"):
            with self.subTest(record_type=record_type):
                self.assertEqual(bundle.record_entry_point(record_type).kind, record_type)

    def test_record_entry_points_are_built_once_with_the_bundle(self):
        bundle = load_bundle(DEFINITIONS)
        self.assertIs(bundle.record_entry_point("assets"), bundle.record_entry_point("assets"))
        self.assertIsNot(bundle.record_entry_point("assets"), bundle.record_entry_point("collections"))

    def test_record_types_are_not_document_roots(self):
        bundle = load_bundle(DEFINITIONS)
        with self.assertRaises(SetupFailed):
            bundle.entry_point("assets")
        with self.assertRaises(SetupFailed):
            bundle.record_entry_point("package")

    def test_record_entry_point_uses_the_loaded_bundle(self):
        root = self.copied_bundle("asset", lambda tree: tree["required"].append("zzz"))
        errors = load_bundle(root).record_entry_point("assets").validate(parse_input(self.ASSET))
        self.assertIn("required", _keywords(errors))
        control = load_bundle(DEFINITIONS).record_entry_point("assets").validate(parse_input(self.ASSET))
        self.assertEqual(control, [])

    def test_record_validation_does_not_fetch_anything(self):
        entry = load_bundle(DEFINITIONS).record_entry_point("assets")
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network used")):
            self.assertEqual(entry.validate(parse_input(self.ASSET)), [])


class SetupAuditTests(_CopiedBundleMixin, unittest.TestCase):
    def test_copied_bundle_control_loads(self):
        root = self.copied_bundle("common", lambda tree: None)
        load_bundle(root).entry_point("package")

    def test_external_ref_does_not_resolve(self):
        def mutate(tree):
            tree["$defs"]["outside"] = {"$ref": "https://example.invalid/x"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "does not resolve"):
            load_bundle(root)

    def test_no_network_is_used_for_an_external_ref(self):
        def mutate(tree):
            tree["$defs"]["outside"] = {"$ref": "https://example.invalid/y"}

        root = self.copied_bundle("asset", mutate)
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")):
            with self.assertRaisesRegex(SetupFailed, "does not resolve"):
                load_bundle(root)

    def test_email_format_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["mail"] = {"type": "string", "format": "email"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "format"):
            load_bundle(root)

    def test_pattern_properties_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["pp"] = {"type": "object", "patternProperties": {"^x_": {}}}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "patternProperties"):
            load_bundle(root)

    def test_multiple_of_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["step"] = {"type": "integer", "multipleOf": 2}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "multipleOf"):
            load_bundle(root)

    def test_untranslatable_pattern_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["bad"] = {"type": "string", "pattern": "(?P<n>a)"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "does not translate from ECMA-262"):
            load_bundle(root)

    def test_deep_schema_pattern_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["deep"] = {"type": "string", "pattern": "(" * 1500 + ")" * 1500}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "does not translate from ECMA-262"):
            load_bundle(root)

    def test_other_dialect_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["old"] = {"$schema": "http://json-schema.org/draft-07/schema#"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "only the 2020-12 dialect is configured"):
            load_bundle(root)

    def test_dynamic_ref_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["dynamic"] = {"$dynamicRef": "https://example.invalid/z#a"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, r"\$dynamicRef and \$dynamicAnchor are not supported"):
            load_bundle(root)

    def test_dynamic_anchor_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["dynamic"] = {"$dynamicAnchor": "a"}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, r"\$dynamicRef and \$dynamicAnchor are not supported"):
            load_bundle(root)

    def test_metaschema_check_opens_no_socket(self):
        root = self.copied_bundle("common", lambda tree: None)
        with mock.patch.object(socket, "socket", side_effect=AssertionError("network")):
            load_bundle(root).entry_point("package")

    def test_metaschema_registry_refuses_retrieval(self):
        with self.assertRaises(referencing.exceptions.NoSuchResource):
            loader._METASCHEMA_REGISTRY.get_or_retrieve("https://example.invalid/meta")

    def test_digest_mismatch_fails_setup(self):
        root = self.copied_bundle("common", lambda tree: None)
        (root / "common.schema.json").write_bytes(b"{}\n")
        with self.assertRaisesRegex(SetupFailed, "digest"):
            load_bundle(root)

    def test_metaschema_violation_fails_setup(self):
        def mutate(tree):
            tree["$defs"]["broken"] = {"type": 7}

        root = self.copied_bundle("common", mutate)
        with self.assertRaisesRegex(SetupFailed, "metaschema"):
            load_bundle(root)


class DateTimeTests(unittest.TestCase):
    def test_accepts(self):
        for value in ("2026-01-02T03:04:05Z", "2026-01-02t03:04:05.5-00:00"):
            with self.subTest(value=value):
                self.assertTrue(check_date_time(value))

    def test_rejects(self):
        for value in (
            "2026-01-02 03:04:05Z",
            "2026-02-30T00:00:00Z",
            "2026-01-02T23:59:60Z",
            "2026-01-02T03:04:05+0100",
        ):
            with self.subTest(value=value):
                self.assertFalse(check_date_time(value))


class DateTests(unittest.TestCase):
    def test_accepts(self):
        self.assertTrue(check_date("2024-02-29"))

    def test_rejects(self):
        for value in ("2023-02-29", "0000-01-01", "2026-1-2"):
            with self.subTest(value=value):
                self.assertFalse(check_date(value))


class RegexFormatTests(unittest.TestCase):
    def test_rejects_python_named_group(self):
        self.assertFalse(check_regex("(?P<n>a)"))

    def test_accepts_ecma_pattern(self):
        self.assertTrue(check_regex("^[a-z]+$"))


class UriTests(unittest.TestCase):
    def test_accepts(self):
        for value in ("https://example.invalid/s#x", "urn:x:y", "https://[::1]:8080/a?b=c#d", "http:"):
            with self.subTest(value=value):
                self.assertTrue(check_uri(value))

    def test_rejects(self):
        for value in (
            "example.invalid/s",
            "https://a b",
            "urn:x:%GG",
            "https://host:abc/",
            "https://[::1",
            "//no-scheme",
        ):
            with self.subTest(value=value):
                self.assertFalse(check_uri(value))


    def test_ipvfuture_version_letter_is_case_insensitive(self):
        # RFC 3986 section 3.2.2: ABNF string literals such as "v" ignore case.
        for value in ("https://[V1.a]/schema", "https://[v1.a]/schema"):
            with self.subTest(value=value):
                self.assertTrue(check_uri(value))
        for value in ("https://[w1.a]/schema", "https://[V.a]/schema"):
            with self.subTest(value=value):
                self.assertFalse(check_uri(value))


class TypeCheckerTests(unittest.TestCase):
    def test_integral_decimal_is_integer(self):
        self.assertTrue(loader.TYPE_CHECKER.is_type(Decimal("1.0"), "integer"))
        self.assertTrue(loader.TYPE_CHECKER.is_type(Decimal("1.0"), "number"))

    def test_fractional_decimal_is_not_integer(self):
        self.assertFalse(loader.TYPE_CHECKER.is_type(Decimal("1.5"), "integer"))

    def test_bool_is_not_a_number(self):
        self.assertFalse(loader.TYPE_CHECKER.is_type(True, "number"))
        self.assertFalse(loader.TYPE_CHECKER.is_type(True, "integer"))


def _decimals(node):
    """Every Decimal in a parsed tree."""
    if isinstance(node, Decimal):
        yield node
    elif isinstance(node, dict):
        for value in node.values():
            yield from _decimals(value)
    elif isinstance(node, list):
        for item in node:
            yield from _decimals(item)


class CrossReferenceTests(unittest.TestCase):
    """The custom pattern and type checks hold across every cross-file $ref."""

    RATE = '"time_base": {"rate": {"numerator": 24, "denominator": 1}'

    def setUp(self):
        self.entry = load_bundle(DEFINITIONS).entry_point("package")

    def test_token_dollar_does_not_match_before_trailing_newline(self):
        # The token pattern lives in common.schema.json; package.schema.json refers to it.
        package = _example("package-minimal.json")
        package["manifest"]["namespaces"] = [{"token": "vendor_a", "owner": "Example Archive"}]
        self.assertEqual(self.entry.validate(_doc(package)), [])
        package["manifest"]["namespaces"][0]["token"] = "vendor_a\n"
        errors = self.entry.validate(_doc(package))
        self.assertIn("pattern", _keywords(errors))

    def test_integral_decimal_rate_accepted(self):
        text = (EXAMPLES / "package-full.json").read_text(encoding="utf-8")
        self.assertEqual(text.count(self.RATE), 1)
        text = text.replace(self.RATE, self.RATE.replace("24,", "24.0,"))
        document = parse_input(text.encode("utf-8"))
        self.assertIn(Decimal("24.0"), list(_decimals(document.value)))
        self.assertEqual(self.entry.validate(document), [])

    def test_bool_rate_numerator_rejected(self):
        text = (EXAMPLES / "package-full.json").read_text(encoding="utf-8")
        text = text.replace(self.RATE, self.RATE.replace("24,", "true,"))
        errors = self.entry.validate(parse_input(text.encode("utf-8")))
        self.assertNotEqual(errors, [])


class NestingTests(unittest.TestCase):
    def test_document_nested_1500_levels_fails_setup_at_parse(self):
        nested = '{"a":' * 1500 + "{}" + "}" * 1500
        package = json.dumps(_example("package-minimal.json"))
        text = package[:-1] + ', "extensions": {"vendor_a": ' + nested + "}}"
        with self.assertRaisesRegex(SetupFailed, "input nesting exceeds"):
            parse_input(text.encode("utf-8"))

    def test_constraint_pattern_nested_1500_levels_fails_setup(self):
        # Valid ECMA-262 syntax nested beyond the checker limit is not "invalid".
        package = _example("package-full.json")
        definitions = [d for d in package["metadata_definitions"] if "pattern" in d.get("constraints", {})]
        self.assertTrue(definitions)
        definitions[0]["constraints"]["pattern"] = "(" * 1500 + "a" + ")" * 1500
        entry = load_bundle(DEFINITIONS).entry_point("package")
        with self.assertRaisesRegex(SetupFailed, "^pattern nesting exceeds the checker's resource limit$"):
            entry.validate(_doc(package))


class ValidateGuardTests(unittest.TestCase):
    """EntryPoint.validate turns evaluation failures into SetupFailed."""

    def setUp(self):
        self.entry = load_bundle(DEFINITIONS).entry_point("package")
        self.document = parse_input((EXAMPLES / "package-minimal.json").read_bytes())

    def _raising(self, error):
        validator_class = type(self.entry._validator)
        return mock.patch.object(validator_class, "iter_errors", side_effect=error)

    def test_recursion_error_is_setup_failed(self):
        with self._raising(RecursionError()):
            with self.assertRaisesRegex(
                SetupFailed, "^validation nesting exceeds the Python interpreter recursion limit$"
            ):
                self.entry.validate(self.document)

    def test_unresolvable_is_setup_failed(self):
        with self._raising(referencing.exceptions.Unresolvable(ref="https://example.invalid/u")):
            with self.assertRaisesRegex(
                SetupFailed, "^schema reference does not resolve inside the bundle$"
            ):
                self.entry.validate(self.document)

    def test_no_such_resource_is_setup_failed(self):
        with self._raising(referencing.exceptions.NoSuchResource(ref="https://example.invalid/n")):
            with self.assertRaisesRegex(
                SetupFailed, "^schema reference does not resolve inside the bundle$"
            ):
                self.entry.validate(self.document)


if __name__ == "__main__":
    unittest.main()
