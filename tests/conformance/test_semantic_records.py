"""Semantic checks inside one asset: the catalog, value shapes, and timeline edge cases.

Every fixture runs through the full pipeline in ``test_corpus.py``. The
tests here pin the catalog to the adopter guide and test the helpers on
small packages built in memory.
"""

import copy
import re
import unittest
from decimal import Decimal
from pathlib import Path

from tests.conformance import formats, semantic
from tests.conformance.document import ROUTING_CATALOG, route
from tests.conformance.semantic import CATALOG, check, check_value_shape, diagnostic
from tests.conformance.types import Diagnostic

REPO = Path(__file__).resolve().parents[2]
ADOPTION = REPO / "docs" / "ADOPTION.md"

_ROW = re.compile(r"^\| `([A-Z_]+)` \| ([^|]+) \| (error|warning) \|")


def _adoption_rows():
    """(code, rule, severity) for each row of the diagnostic catalog in docs/ADOPTION.md."""
    rows = []
    for line in ADOPTION.read_text(encoding="utf-8").splitlines():
        match = _ROW.match(line)
        if match:
            rule = match.group(2).strip().replace("`", "")
            rows.append((match.group(1), rule, match.group(3)))
    return rows


def _pairs(diagnostics):
    return [(d.code, d.path) for d in diagnostics]


def _package(*assets):
    """A minimal package around the given assets; counts match."""
    return {
        "type": "package",
        "spec_version": "2.0.0-draft.4",
        "id": "pkg-0001",
        "manifest": {
            "producer": {"name": "example-exporter", "version": "0.1.0"},
            "produced_at": "2026-10-05T09:00:00Z",
            "counts": {"storage_locations": 0, "metadata_definitions": 0, "collections": 0, "assets": len(assets)},
            "namespaces": [],
        },
        "storage_locations": [],
        "metadata_definitions": [],
        "collections": [],
        "assets": list(assets),
    }


def _frame_timing(frames=750):
    return {"time_base": {"rate": {"numerator": 25, "denominator": 1}}, "duration_frames": frames}


def _check(package):
    before = copy.deepcopy(package)
    diagnostics = check(package, route(package))
    assert package == before
    return _pairs(diagnostics)


class CatalogTests(unittest.TestCase):
    def test_catalog_matches_the_adopter_guide(self):
        # The guide lists every code in catalog order: the single-document codes,
        # then the multi-file codes (rules MFP-*).
        rows = _adoption_rows()
        single_document = [code for code, (rule, _s, _m) in CATALOG.items() if not rule.startswith("MFP-")]
        self.assertEqual(len(rows), 70)
        self.assertEqual(len(CATALOG), 70)
        self.assertEqual([code for code, _r, _s in rows], list(CATALOG))
        self.assertEqual(list(CATALOG)[:54], single_document)
        for code, rule, severity in rows:
            with self.subTest(code):
                self.assertEqual(CATALOG[code][:2], (rule, severity))

    def test_every_single_document_code_is_an_error(self):
        severities = {severity for _rule, severity, _message in CATALOG.values() if not _rule.startswith("MFP-")}
        self.assertEqual(severities, {"error"})

    def test_messages_are_fixed_sentences(self):
        for code, (_rule, _severity, message) in CATALOG.items():
            with self.subTest(code):
                self.assertTrue(message.endswith("."))
                self.assertNotIn("\u2014", message)

    def test_removed_codes_are_gone(self):
        removed = (
            "TYPE_UNSUPPORTED", "REFERENCE_UNRESOLVED_PARTIAL", "SNAPSHOT_MISMATCH", "TIMELINE_UNAVAILABLE",
            "FRAME_OUT_OF_BOUNDS", "SEGMENT_GAP", "VERSION_WITHOUT_VERSIONS", "MEMBERSHIP_DISAGREES",
            "VALUE_OPTION_REPEATED", "DEFINITION_UNAVAILABLE",
        )
        for code in removed:
            with self.subTest(code):
                self.assertNotIn(code, CATALOG)

    def test_routing_uses_the_same_catalog(self):
        for code in ("NOT_EXCHANGE_DOCUMENT", "VERSION_UNSUPPORTED"):
            self.assertEqual(ROUTING_CATALOG[code], CATALOG[code])

    def test_diagnostic(self):
        self.assertEqual(
            diagnostic("RELATIONSHIP_SELF", "/assets/0/relationships/0/target"),
            Diagnostic(
                "RELATIONSHIP_SELF",
                "REL-3",
                "error",
                "/assets/0/relationships/0/target",
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
        for bad in (True, Decimal("1.5"), "1"):
            with self.subTest(bad=bad):
                with self.assertRaises(TypeError):
                    semantic.as_int(bad)

    def test_no_float_in_source(self):
        for module in (semantic, formats):
            with self.subTest(module.__name__):
                text = Path(module.__file__).read_text(encoding="utf-8")
                self.assertNotIn("float", text)


class TimelineTests(unittest.TestCase):
    def test_reversed_range_starting_past_the_length(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": _frame_timing(),
            "annotations": [{"id": "n-0001", "start_frame": 800, "end_frame": 10}],
        }
        self.assertEqual(
            _check(_package(asset)),
            [
                ("RANGE_NOT_INCREASING", "/assets/0/annotations/0/end_frame"),
                ("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/start_frame"),
            ],
        )

    def test_point_at_the_end_boundary_is_in_bounds(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": _frame_timing(),
            "annotations": [{"id": "n-0001", "start_frame": 750}],
        }
        self.assertEqual(_check(_package(asset)), [])

    def test_range_start_frame_at_the_length_is_out_of_bounds(self):
        # TIME-9: a range satisfies start_frame < end_frame <= D, so its start
        # at D is out of bounds, reported at the start as well as the end.
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": _frame_timing(),
            "annotations": [{"id": "n-0001", "start_frame": 750, "end_frame": 751}],
        }
        self.assertEqual(
            _check(_package(asset)),
            [
                ("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/end_frame"),
                ("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/start_frame"),
            ],
        )

    def test_range_start_seconds_at_the_length_is_out_of_bounds(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {"duration_seconds": 30},
            "annotations": [{"id": "n-0001", "start_seconds": 30, "end_seconds": 31}],
        }
        self.assertEqual(
            _check(_package(asset)),
            [
                ("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/end_seconds"),
                ("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/start_seconds"),
            ],
        )

    def test_point_seconds_at_the_length_is_in_bounds(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {"duration_seconds": 30},
            "annotations": [{"id": "n-0001", "start_seconds": 30}],
        }
        self.assertEqual(_check(_package(asset)), [])

    def test_range_start_sample_at_the_sample_length_is_out_of_bounds(self):
        # TIME-13: a range's start_sample MUST be less than duration_samples,
        # also when the range has no end_sample.
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {"duration_seconds": 1, "sample_rate": 10, "duration_samples": 10},
            "annotations": [
                {"id": "n-0001", "start_seconds": Decimal("0.96"), "end_seconds": 1, "start_sample": 10}
            ],
        }
        self.assertEqual(
            _check(_package(asset)), [("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/start_sample")]
        )

    def test_frame_range_start_sample_at_the_sample_length_is_out_of_bounds(self):
        timing = {
            "time_base": {"rate": {"numerator": 24, "denominator": 1}, "drop_frame": False},
            "duration_frames": 24,
            "duration_seconds": 1,
            "sample_rate": 10,
            "duration_samples": 10,
        }
        marker = {
            "id": "n-0001",
            "start_frame": 23,
            "end_frame": 24,
            "start_seconds": Decimal("0.958333"),
            "start_sample": 10,
        }
        asset = {"id": "a-0001", "title": "Example Clip", "timing": timing, "annotations": [marker]}
        self.assertEqual(
            _check(_package(asset)), [("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/start_sample")]
        )

    def test_point_sample_at_the_sample_length_is_in_bounds(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {"duration_seconds": 1, "sample_rate": 10, "duration_samples": 10},
            "annotations": [{"id": "n-0001", "start_seconds": 1, "start_sample": 10}],
        }
        self.assertEqual(_check(_package(asset)), [])

    def test_seconds_form_source_timecode_reads_no_time_base(self):
        # TIME-14: a seconds-form timing may carry source_timecode with its own
        # timecode_base. The checks never read time_base when it is absent.
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {
                "duration_seconds": Decimal("30.0"),
                "source_timecode": "01:00:00:00",
                "timecode_base": {"rate": {"numerator": 25, "denominator": 1}},
            },
            "annotations": [{"id": "n-0001", "start_seconds": Decimal("1.5"), "end_seconds": 31}],
        }
        self.assertEqual(_check(_package(asset)), [("POSITION_OUT_OF_BOUNDS", "/assets/0/annotations/0/end_seconds")])

    def test_seconds_form_timecode_base_rate_in_lowest_terms(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {
                "duration_seconds": 30,
                "source_timecode": "01:00:00:00",
                "timecode_base": {"rate": {"numerator": 50, "denominator": 2}},
            },
        }
        self.assertEqual(_check(_package(asset)), [("RATE_NOT_LOWEST_TERMS", "/assets/0/timing/timecode_base/rate")])

    def test_sample_rate_undeclared_once_per_marker(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {"duration_seconds": 30},
            "annotations": [{"id": "n-0001", "start_sample": 0, "end_sample": 48000}],
        }
        self.assertEqual(
            _check(_package(asset)), [("SAMPLE_RATE_UNDECLARED", "/assets/0/annotations/0/start_sample")]
        )

    def test_integral_decimal_spellings(self):
        asset = {
            "id": "a-0001",
            "title": "Example Clip",
            "timing": {
                "time_base": {"rate": {"numerator": Decimal("25.0"), "denominator": Decimal("1E0")}},
                "duration_frames": Decimal("750.0"),
            },
            "annotations": [{"id": "n-0001", "start_frame": Decimal("750.0")}],
        }
        self.assertEqual(_check(_package(asset)), [])


def _definition(type_, cardinality, options=None, list_type="fixed"):
    definition = {"value_type": type_, "cardinality": cardinality}
    if options is not None:
        definition["options"] = [{"id": o} for o in options]
        definition["list_type"] = list_type
    return definition


class ValueShapeTests(unittest.TestCase):
    def shape(self, definition, value):
        return sorted(_pairs(check_value_shape(definition, value, "/metadata/0/value")), key=lambda p: (p[1], p[0]))

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
            (_definition("boolean", "multiple"), [True, False]),
        ]
        for definition, value in cases:
            with self.subTest(definition=definition, value=value):
                self.assertEqual(self.shape(definition, value), [])

    def test_empty_multiple_allowed(self):
        for type_ in ("string", "integer", "enum", "date"):
            with self.subTest(type_):
                options = ["a"] if type_ == "enum" else None
                self.assertEqual(self.shape(_definition(type_, "multiple", options), []), [])

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

    def test_option_unknown_on_a_fixed_list(self):
        self.assertEqual(
            self.shape(_definition("enum", "single", ["a", "b"]), "c"),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value")],
        )
        self.assertEqual(
            self.shape(_definition("enum", "multiple", ["a", "b"]), ["a", "c"]),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value/1")],
        )

    def test_empty_fixed_list_accepts_no_item(self):
        self.assertEqual(
            self.shape(_definition("enum", "single", []), "a"),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value")],
        )

    def test_open_list_accepts_any_string(self):
        self.assertEqual(self.shape(_definition("enum", "single", ["a"], "open"), "c"), [])
        self.assertEqual(self.shape(_definition("enum", "multiple", [], "open"), ["c", "d"]), [])

    def test_option_ids_compare_by_code_points(self):
        self.assertEqual(
            self.shape(_definition("enum", "single", ["é"]), "é"),
            [("VALUE_OPTION_UNKNOWN", "/metadata/0/value")],
        )

    def test_value_repeated_for_every_type(self):
        cases = [
            (_definition("enum", "multiple", ["a", "b"]), ["a", "b", "a", "a"], [2, 3]),
            (_definition("string", "multiple"), ["x", "y", "x"], [2]),
            (_definition("integer", "multiple"), [1, Decimal("1.0"), 2], [1]),
            (_definition("number", "multiple"), [Decimal("0.5"), Decimal("0.50")], [1]),
            (_definition("boolean", "multiple"), [True, True], [1]),
            (_definition("asset_reference", "multiple"), ["a-1", "a-1"], [1]),
        ]
        for definition, value, repeats in cases:
            with self.subTest(definition=definition, value=value):
                self.assertEqual(
                    self.shape(definition, value),
                    [("VALUE_REPEATED", "/metadata/0/value/%d" % k) for k in repeats],
                )

    def test_strings_with_different_code_points_are_not_repeats(self):
        self.assertEqual(self.shape(_definition("string", "multiple"), ["é", "é"]), [])

    def test_unknown_repeated_option_gets_both_findings(self):
        # MD-7 and MD-8: an item can get both an option finding and a repeat finding.
        self.assertEqual(
            self.shape(_definition("enum", "multiple", ["a", "b"]), ["c", "a", "c", "a"]),
            [
                ("VALUE_OPTION_UNKNOWN", "/metadata/0/value/0"),
                ("VALUE_OPTION_UNKNOWN", "/metadata/0/value/2"),
                ("VALUE_REPEATED", "/metadata/0/value/2"),
                ("VALUE_REPEATED", "/metadata/0/value/3"),
            ],
        )

    def test_no_value_in_message(self):
        for d in check_value_shape(_definition("enum", "single", ["a"]), "SENTINEL-VALUE", "/v"):
            self.assertNotIn("SENTINEL-VALUE", d.message)


if __name__ == "__main__":
    unittest.main()
