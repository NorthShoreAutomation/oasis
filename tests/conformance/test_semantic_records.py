"""Record-level semantic checks: every fixture, the catalog, no mutation."""

import copy
import unittest
from decimal import Decimal
from pathlib import Path

from tests.conformance import formats, semantic
from tests.conformance.document import route
from tests.conformance.loader import load_bundle
from tests.conformance.semantic import CATALOG, check, check_value_shape, diagnostic
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic

REPO = Path(__file__).resolve().parents[2]
RECORDS = Path(__file__).resolve().parent / "fixtures" / "records"

# name: complete sorted [(code, path), ...]
CASES = {
    "time-rate-not-lowest-terms": [("RATE_NOT_LOWEST_TERMS", "/timing/time_base/rate")],
    "time-range-not-increasing": [("RANGE_NOT_INCREASING", "/annotations/0/end_frame")],
    "time-seconds-disagree": [("SECONDS_DISAGREE", "/annotations/0/start_seconds")],
    "time-seconds-tie-toward-zero": [],
    "time-rate-decimal-spelling-ok": [],
    "time-timecode-disagree": [("TIMECODE_DISAGREE", "/annotations/0/start_timecode")],
    "time-timecode-drop-frame-minute-boundary": [],
    "time-timecode-rollover": [],
    "time-frame-out-of-bounds": [("FRAME_OUT_OF_BOUNDS", "/annotations/0/end_frame")],
    "time-point-at-duration": [("FRAME_OUT_OF_BOUNDS", "/annotations/0/start_frame")],
    "time-range-end-equals-duration-ok": [],
    "time-standalone-annotation-timeline-unavailable": [("TIMELINE_UNAVAILABLE", "")],
    "time-standalone-relationship-range": [("TIMELINE_UNAVAILABLE", "/relationships/0/range")],
    "group-sequence-range-empty": [("SEQUENCE_RANGE_EMPTY", "/file_groups/0/members/0/sequence_range")],
    "group-track-duplicate": [("TRACK_DUPLICATE", "/file_groups/0/members/1")],
    "group-file-unresolved": [("FILE_REFERENCE_UNRESOLVED", "/file_groups/0/members/0/file")],
    "group-segments-ok": [],
    "group-segment-index-duplicate": [("SEGMENT_INDEX_DUPLICATE", "/file_groups/0/members/1/segment_index")],
    "group-segment-index-missing": [("SEGMENT_INDEX_MISSING", "/file_groups/0/members/1")],
    "group-segment-out-of-order": [("SEGMENT_OUT_OF_ORDER", "/file_groups/0/members/1/segment_index")],
    "group-segment-gap-complete": [("SEGMENT_GAP", "/file_groups/0/members/1/segment_index")],
    "group-segment-gap-incomplete-ok": [],
    "group-segment-single-incomplete-ok": [],
    "version-ordinal-duplicate": [("ORDINAL_DUPLICATE", "/versions/1/ordinal")],
    "version-reference-unresolved": [("VERSION_REFERENCE_UNRESOLVED", "/files/0/version")],
    "version-without-versions": [("VERSION_WITHOUT_VERSIONS", "/file_groups/0/version")],
    "relationship-self": [("RELATIONSHIP_SELF", "/relationships/0/target")],
    "nested-id-duplicate-files": [("NESTED_ID_DUPLICATE", "/files/1/id")],
    "nested-id-duplicate-options": [("NESTED_ID_DUPLICATE", "/options/1/id")],
    "collection-self-parent": [("COLLECTION_CYCLE", "/parent")],
    "metadata-definition-repeated": [
        ("DEFINITION_UNAVAILABLE", "/metadata/0"),
        ("DEFINITION_UNAVAILABLE", "/metadata/1"),
        ("DEFINITION_REPEATED", "/metadata/1/definition"),
    ],
    "metadata-value-definition-unavailable": [("DEFINITION_UNAVAILABLE", "/metadata/0")],
    "sentinel-strings": [("DEFINITION_UNAVAILABLE", "/metadata/0")],
}

# The expected diagnostic catalog: code -> (rule, severity, message).
EXPECTED_CATALOG = {
    "INPUT_INVALID": ("DOC-1", "error", "Input bytes cannot be parsed under the strict JSON policy."),
    "TYPE_UNSUPPORTED": ("UNS-1", "error", "The document root has no supported record type."),
    "VERSION_UNSUPPORTED": ("REC-4, UNS-1", "error", "The declared spec_version is not supported by this checker."),
    "COUNT_MISMATCH": ("PKG-3", "error", "A declared count does not equal the length of its array."),
    "REFERENCE_UNRESOLVED": ("PKG-6", "error", "A reference does not resolve in a complete registry."),
    "REFERENCE_UNRESOLVED_PARTIAL": ("PKG-6", "warning", "A reference does not resolve in a partial registry."),
    "ID_DUPLICATE": ("ID-1", "error", "A record id is repeated within its record type."),
    "NESTED_ID_DUPLICATE": ("ID-4", "error", "A nested id is repeated within its record."),
    "SNAPSHOT_MISMATCH": ("ID-6", "error", "A collection snapshot differs from the registry record."),
    "RATE_NOT_LOWEST_TERMS": ("TIME-2", "error", "A rate is not written in lowest terms."),
    "RANGE_NOT_INCREASING": ("TIME-4", "error", "A range does not end after it starts."),
    "TIMELINE_UNDECLARED": ("TIME-5, TIME-12", "error", "A frame field belongs to a timeline with no time base."),
    "TIMELINE_UNAVAILABLE": (
        "TIME-12, ANN-3",
        "warning",
        "The owning asset is not in the document, so timing agreement was not checked.",
    ),
    "SECONDS_DISAGREE": ("TIME-7", "error", "A derived seconds value names a different frame."),
    "TIMECODE_DISAGREE": (
        "TIME-7, TIME-8",
        "error",
        "A timecode label differs from the label derived from the frame value.",
    ),
    "FRAME_OUT_OF_BOUNDS": ("TIME-9", "error", "A frame position lies outside the asset duration."),
    "SEQUENCE_RANGE_EMPTY": ("GRP-3", "error", "An image sequence range does not end after it starts."),
    "TRACK_DUPLICATE": ("GRP-4", "error", "A file group repeats a track type and index pair."),
    "FILE_REFERENCE_UNRESOLVED": ("GRP-4", "error", "A file group member names a file that is not in the asset."),
    "SEGMENT_INDEX_MISSING": (
        "GRP-6",
        "error",
        "A file group member shares a track type and index pair with a segment but has no segment_index.",
    ),
    "SEGMENT_INDEX_DUPLICATE": (
        "GRP-6",
        "error",
        "A file group repeats a segment_index within one track type and index pair.",
    ),
    "SEGMENT_OUT_OF_ORDER": ("GRP-6", "error", "File group segments are not in ascending segment_index order."),
    "SEGMENT_GAP": (
        "GRP-6",
        "error",
        "A complete file group has a gap in the segment_index values of one track type and index pair.",
    ),
    "ORDINAL_DUPLICATE": ("VER-2", "error", "Two versions share an ordinal."),
    "VERSION_REFERENCE_UNRESOLVED": ("VER-3", "error", "A version reference names no version in the asset."),
    "VERSION_WITHOUT_VERSIONS": ("VER-3", "error", "A version reference appears on an asset with no versions."),
    "RELATIONSHIP_SELF": ("REL-3", "error", "A relationship targets its own asset."),
    "COLLECTION_CYCLE": ("COL-4", "error", "A collection is its own ancestor."),
    "MEMBERSHIP_DISAGREES": ("COL-5", "error", "An asset claims membership that a complete collection list denies."),
    "VALUE_SHAPE_MISMATCH": (
        "MD-4",
        "error",
        "A metadata value does not match the value_type and cardinality of its definition.",
    ),
    "VALUE_DATE_INVALID": ("MD-4, DT-1, DT-3", "error", "A date or date-time metadata value is not valid."),
    "VALUE_OPTION_UNKNOWN": ("MD-4", "error", "An enum value is not an option id of its definition."),
    "VALUE_OPTION_REPEATED": ("MD-4", "error", "A multiple enum value repeats an option id."),
    "DEFINITION_UNAVAILABLE": (
        "MD-4",
        "warning",
        "The metadata definition is not in the document, so the value shape was not checked.",
    ),
    "DEFINITION_REPEATED": ("MD-5", "error", "A metadata array names the same definition twice."),
    "NAMESPACE_UNDECLARED": ("EXT-2", "error", "An extension namespace is used but not declared in the manifest."),
    "NAMESPACE_DECLARED_TWICE": ("EXT-2", "error", "A namespace token is declared more than once."),
}


def _parsed(name):
    return parse_input((RECORDS / (name + ".json")).read_bytes())


def _pairs(diagnostics):
    return [(d.code, d.path) for d in diagnostics]


class RecordFixtureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = load_bundle(REPO / "definitions")

    def _check_fixture(self, name):
        parsed = _parsed(name)
        routing = route(parsed.value)
        self.assertEqual(routing.status, "selected")
        errors = self.bundle.entry_point(routing.kind).validate(parsed)
        self.assertEqual([(list(e.absolute_path), e.validator) for e in errors], [])
        diagnostics = check(parsed.value, routing)
        self.assertEqual(diagnostics, sorted(diagnostics, key=lambda d: (d.path, d.code)))
        for d in diagnostics:
            self.assertEqual(d, diagnostic(d.code, d.path))
        return _pairs(diagnostics)

    def test_every_case_has_a_fixture(self):
        for name in CASES:
            with self.subTest(name):
                self.assertTrue((RECORDS / (name + ".json")).is_file())

    def test_fixtures(self):
        for name, expected in CASES.items():
            with self.subTest(name):
                self.assertEqual(self._check_fixture(name), expected)

    def test_tree_unchanged(self):
        for name in CASES:
            with self.subTest(name):
                value = _parsed(name).value
                before = copy.deepcopy(value)
                check(value, route(value))
                self.assertEqual(value, before)
                self.assertEqual(repr(value), repr(before))

    def test_reversed_range_starting_past_duration(self):
        value = copy.deepcopy(_parsed("time-frame-out-of-bounds").value)
        value["annotations"][0]["start_frame"] = 800
        value["annotations"][0]["end_frame"] = 10
        self.assertEqual(
            _pairs(check(value, route(value))),
            [
                ("RANGE_NOT_INCREASING", "/annotations/0/end_frame"),
                ("FRAME_OUT_OF_BOUNDS", "/annotations/0/start_frame"),
            ],
        )

    def test_no_float_in_source(self):
        for module in (semantic, formats):
            with self.subTest(module.__name__):
                text = Path(module.__file__).read_text(encoding="utf-8")
                self.assertNotIn("float", text)


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_expected(self):
        self.assertEqual(len(EXPECTED_CATALOG), 37)
        self.assertEqual(CATALOG, EXPECTED_CATALOG)
        self.assertEqual(list(CATALOG), list(EXPECTED_CATALOG))

    def test_routing_uses_the_same_catalog(self):
        from tests.conformance import document

        for code in ("TYPE_UNSUPPORTED", "VERSION_UNSUPPORTED"):
            self.assertEqual(document.ROUTING_CATALOG[code], CATALOG[code])

    def test_diagnostic(self):
        self.assertEqual(
            diagnostic("RELATIONSHIP_SELF", "/relationships/0/target"),
            Diagnostic(
                "RELATIONSHIP_SELF",
                "REL-3",
                "error",
                "/relationships/0/target",
                "A relationship targets its own asset.",
            ),
        )

    def test_pointer_escapes_tilde_and_slash(self):
        self.assertEqual(semantic.pointer("", "a~b/c", 3), "/a~0b~1c/3")
        self.assertEqual(semantic.pointer("/x"), "/x")

    def test_as_int(self):
        self.assertEqual(semantic.as_int(25), 25)
        self.assertEqual(semantic.as_int(Decimal("25.0")), 25)
        self.assertEqual(semantic.as_int(Decimal("1E0")), 1)
        self.assertIs(type(semantic.as_int(Decimal("1E0"))), int)


def _definition(type_, cardinality, options=None):
    definition = {"value_type": type_, "cardinality": cardinality}
    if options is not None:
        definition["options"] = [{"id": o} for o in options]
    return definition


class ValueShapeTests(unittest.TestCase):
    def shape(self, definition, value):
        return _pairs(check_value_shape(definition, value, "/metadata/0/value"))

    def test_matching_values(self):
        cases = [
            (_definition("string", "single"), "x"),
            (_definition("integer", "single"), 3),
            (_definition("integer", "single"), Decimal("3.0")),
            (_definition("number", "single"), Decimal("0.5")),
            (_definition("number", "single"), 2),
            (_definition("boolean", "single"), False),
            (_definition("date", "single"), "2024-02-29"),
            (_definition("datetime", "single"), "2024-02-29T10:00:00Z"),
            (_definition("enum", "single", ["a", "b"]), "b"),
            (_definition("asset_reference", "single"), "a-1"),
            (_definition("collection_reference", "multiple"), ["c-1", "c-2"]),
            (_definition("integer", "multiple"), [1, 2]),
            (_definition("enum", "multiple", ["a", "b"]), ["a", "b"]),
        ]
        for definition, value in cases:
            with self.subTest(definition=definition, value=value):
                self.assertEqual(self.shape(definition, value), [])

    def test_empty_multiple_allowed(self):
        for type_ in ("string", "integer", "enum", "date"):
            with self.subTest(type_):
                self.assertEqual(self.shape(_definition(type_, "multiple", ["a"] if type_ == "enum" else None), []), [])

    def test_type_mismatch(self):
        cases = [
            (_definition("string", "single"), 1),
            (_definition("integer", "single"), Decimal("1.5")),
            (_definition("integer", "single"), True),
            (_definition("number", "single"), "1"),
            (_definition("number", "single"), True),
            (_definition("boolean", "single"), 0),
            (_definition("date", "single"), 20240229),
            (_definition("enum", "single", ["a"]), 1),
            (_definition("asset_reference", "single"), False),
        ]
        for definition, value in cases:
            with self.subTest(definition=definition, value=value):
                self.assertEqual(self.shape(definition, value), [("VALUE_SHAPE_MISMATCH", "/metadata/0/value")])

    def test_cardinality_mismatch(self):
        self.assertEqual(
            self.shape(_definition("string", "single"), ["x"]),
            [("VALUE_SHAPE_MISMATCH", "/metadata/0/value")],
        )
        self.assertEqual(
            self.shape(_definition("string", "multiple"), "x"),
            [("VALUE_SHAPE_MISMATCH", "/metadata/0/value")],
        )

    def test_item_mismatch_points_at_item(self):
        self.assertEqual(
            self.shape(_definition("integer", "multiple"), [1, "2", 3]),
            [("VALUE_SHAPE_MISMATCH", "/metadata/0/value/1")],
        )

    def test_date_validity(self):
        for value in ("2023-02-29", "2024-13-01", "24-01-01", "0000-01-01"):
            with self.subTest(value):
                self.assertEqual(
                    self.shape(_definition("date", "single"), value),
                    [("VALUE_DATE_INVALID", "/metadata/0/value")],
                )
        self.assertEqual(
            self.shape(_definition("date", "multiple"), ["2024-01-01", "2024-02-30"]),
            [("VALUE_DATE_INVALID", "/metadata/0/value/1")],
        )

    def test_date_time_validity(self):
        for value in ("2024-02-30T10:00:00Z", "2024-01-01T24:00:00Z", "2024-01-01 10:00:00Z", "2024-01-01T10:00:00"):
            with self.subTest(value):
                self.assertEqual(
                    self.shape(_definition("datetime", "single"), value),
                    [("VALUE_DATE_INVALID", "/metadata/0/value")],
                )

    def test_option_unknown(self):
        self.assertEqual(
            self.shape(_definition("enum", "single", ["a", "b"]), "c"),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value")],
        )
        self.assertEqual(
            self.shape(_definition("enum", "multiple", ["a", "b"]), ["a", "c"]),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value/1")],
        )

    def test_option_repeated(self):
        self.assertEqual(
            self.shape(_definition("enum", "multiple", ["a", "b"]), ["a", "b", "a", "a"]),
            [
                ("VALUE_OPTION_REPEATED", "/metadata/0/value/2"),
                ("VALUE_OPTION_REPEATED", "/metadata/0/value/3"),
            ],
        )

    def test_unknown_repeated_option_is_unknown_only(self):
        self.assertEqual(
            self.shape(_definition("enum", "multiple", ["a", "b"]), ["c", "a", "c", "a"]),
            [
                ("VALUE_OPTION_UNKNOWN", "/metadata/0/value/0"),
                ("VALUE_OPTION_UNKNOWN", "/metadata/0/value/2"),
                ("VALUE_OPTION_REPEATED", "/metadata/0/value/3"),
            ],
        )

    def test_no_value_in_message(self):
        for d in check_value_shape(_definition("enum", "single", ["a"]), "SECRET-VALUE", "/v"):
            self.assertNotIn("SECRET-VALUE", d.message)


if __name__ == "__main__":
    unittest.main()
