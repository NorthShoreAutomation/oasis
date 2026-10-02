"""Tests for the exchange-1x profile dispatcher, version routing, and outcomes."""

import json
import subprocess
import sys
import unittest
from decimal import Decimal
from pathlib import Path
from unittest import mock

from tests.conformance import corpus, profiles, results
from tests.conformance.loader import validate_legacy
from tests.conformance.strict_json import parse_input
from tests.conformance.types import Diagnostic, InputInvalid, NumericResourceRefused, ProfileOutcome, SetupFailed

REPO = Path(__file__).resolve().parents[2]
BASELINE = Path(__file__).resolve().parent / "baseline"
REVISION = "0123456789abcdef0123456789abcdef01234567"
CASES = {case.id: case for case in corpus.fixture_cases()}
EMPTY_CONTEXT = {"asset_ids": [], "collection_ids": []}

ASSET = "asset.schema.json"
COLLECTION = "collection.schema.json"
METADATA_SET = "metadata_set.schema.json"
STORAGE = "storage_location.schema.json"
ASSET_BATCH = "asset_batch_import.schema.json"
COLLECTION_BATCH = "collection_batch_import.schema.json"
ANNOTATION = "temporal_annotation.schema.json"
REPORT = "migration-report-output.schema.json"
STANDALONE_WITH_SELECTOR = (ASSET, COLLECTION, METADATA_SET, STORAGE, ASSET_BATCH, COLLECTION_BATCH)


def doc(value):
    return parse_input(json.dumps(value).encode("utf-8"))


def check(name, value, *, structural="valid", context=EMPTY_CONTEXT, profile="exchange-1x"):
    return profiles.validate_profile(
        name, doc(value), profile, structural=structural, reference_context=context,
    )


def codes(outcome):
    """Code/path pairs in contract order: by path, then code."""
    return [(d.code, d.path) for d in sorted(outcome.diagnostics, key=lambda d: (d.path, d.code))]


def warning_rule(name, value, reference_context):
    return [Diagnostic("COMPLETENESS_UNVERIFIED", "", "warning", "Completeness is not established.")]


def error_rule(name, value, reference_context):
    return [Diagnostic("SIZE_UNUSABLE", "/files/0/size", "error", "A declared file size is negative.")]


def exploding_rule(name, value, reference_context):
    raise AssertionError("semantic rules must not run for this input")


class OutcomeTableTest(unittest.TestCase):
    def test_excluded_report_is_profile_unsupported_for_either_structural_result(self):
        with mock.patch.object(profiles, "RULES", [exploding_rule]):
            for structural in ("valid", "invalid"):
                with self.subTest(structural=structural):
                    outcome = check(REPORT, {"report_id": "r"}, structural=structural)
                    self.assertEqual((outcome.routing, outcome.execution_status), ("unsupported", "unsupported"))
                    self.assertEqual(codes(outcome), [("PROFILE_UNSUPPORTED", "")])

    def test_excluded_report_reports_only_the_profile_error(self):
        value = {"schema_version": "9.9.9", "assets": [{"schema_version": 3}], "report_version": "x"}
        outcome = check(REPORT, value)
        self.assertEqual(codes(outcome), [("PROFILE_UNSUPPORTED", "")])

    def test_unsupported_selector_blocks_routing_even_when_structurally_invalid(self):
        with mock.patch.object(profiles, "RULES", [exploding_rule]):
            for structural in ("valid", "invalid"):
                with self.subTest(structural=structural):
                    outcome = check(ASSET, {"schema_version": "2.0.0"}, structural=structural)
                    self.assertEqual((outcome.routing, outcome.execution_status), ("unsupported", "unsupported"))
                    self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/schema_version")])

    def test_selected_structural_rejection_is_blocked_without_semantics(self):
        with mock.patch.object(profiles, "RULES", [exploding_rule]):
            outcome = check(ASSET, {"schema_version": "1.1.0"}, structural="invalid")
        self.assertEqual(outcome, ProfileOutcome("selected", "blocked", ()))

    def test_selected_valid_with_error_is_blocked_with_all_diagnostics(self):
        with mock.patch.object(profiles, "RULES", [warning_rule, error_rule]):
            outcome = check(ASSET, {})
        self.assertEqual((outcome.routing, outcome.execution_status), ("selected", "blocked"))
        self.assertEqual(
            codes(outcome),
            [("COMPLETENESS_UNVERIFIED", ""), ("SIZE_UNUSABLE", "/files/0/size")],
        )

    def test_selected_valid_with_warnings_is_complete(self):
        with mock.patch.object(profiles, "RULES", [warning_rule]):
            outcome = check(ASSET, {})
        self.assertEqual((outcome.routing, outcome.execution_status), ("selected", "complete"))
        self.assertEqual(codes(outcome), [("COMPLETENESS_UNVERIFIED", "")])

    def test_selected_valid_without_diagnostics_is_complete(self):
        self.assertEqual(check(ASSET, {}), ProfileOutcome("selected", "complete", ()))

    def test_rules_receive_entry_point_document_and_context(self):
        calls = []
        context = {"asset_ids": ["a1"], "collection_ids": ["c1"]}

        def spy(name, value, reference_context):
            calls.append((name, value, reference_context))
            return []

        with mock.patch.object(profiles, "RULES", [spy]):
            check(COLLECTION, {"collection_id": "c2"}, context=context)
        self.assertEqual(calls, [(COLLECTION, {"collection_id": "c2"}, context)])

    def test_diagnostic_severity_comes_from_the_catalog(self):
        for code in ("PROFILE_UNSUPPORTED", "VERSION_UNSUPPORTED"):
            self.assertEqual(corpus.DIAGNOSTIC_SEVERITY[code], "error")
        outcome = check(ASSET, {"schema_version": "0.9.0"})
        self.assertEqual(results.severity_problems(outcome.diagnostics), [])

    def test_messages_do_not_echo_input_values(self):
        label = "secret-label-1234"
        outcome = check(ASSET, {"schema_version": label})
        self.assertTrue(all(label not in d.message for d in outcome.diagnostics))

    def test_document_is_not_mutated(self):
        document = doc({"schema_version": "1.0.0", "assets": []})
        before = json.dumps(document.value, sort_keys=True)
        profiles.validate_profile(ASSET_BATCH, document, "exchange-1x", structural="valid",
                                  reference_context=EMPTY_CONTEXT)
        self.assertEqual(json.dumps(document.value, sort_keys=True), before)


class SetupTest(unittest.TestCase):
    def test_unknown_profile_fails_setup(self):
        for profile in ("nope-9x", "Exchange-1x", ""):
            with self.subTest(profile=profile), self.assertRaises(SetupFailed):
                check(ASSET, {}, profile=profile)

    def test_unknown_entry_point_fails_setup(self):
        with self.assertRaises(SetupFailed):
            check("unknown.schema.json", {})

    def test_legacy_profile_is_not_applied_and_runs_nothing(self):
        with mock.patch.object(profiles, "RULES", [exploding_rule]):
            for name in (ASSET, REPORT):
                outcome = check(name, {"schema_version": "2.0.0"}, profile="legacy-1x")
                self.assertEqual(outcome, ProfileOutcome("not-applied", "complete", ()))

    def test_malformed_context_fails_setup(self):
        malformed = [
            None,
            [],
            {"asset_ids": []},
            {"collection_ids": []},
            {"asset_ids": [], "collection_ids": [], "extra": []},
            {"asset_ids": "a1", "collection_ids": []},
            {"asset_ids": [], "collection_ids": ("c1",)},
            {"asset_ids": [1], "collection_ids": []},
            {"asset_ids": [], "collection_ids": [None]},
            {"asset_ids": [""], "collection_ids": []},
        ] + [{"asset_ids": [], "collection_ids": ["x", ws * 2]} for ws in " \t\r\n\f\v"]
        for context in malformed:
            with self.subTest(context=context), self.assertRaises(SetupFailed):
                check(ASSET, {}, context=context)

    def test_wellformed_context_is_accepted(self):
        contexts = [
            EMPTY_CONTEXT,
            {"asset_ids": ["a1", "a1"], "collection_ids": [" c1 "]},
            # A non-ASCII space is not whitespace for this bounded check.
            {"asset_ids": [" "], "collection_ids": ["　"]},
        ]
        for context in contexts:
            with self.subTest(context=context):
                self.assertEqual(check(ASSET, {}, context=context).routing, "selected")

    def test_setup_failure_outranks_profile_routing(self):
        with self.assertRaises(SetupFailed):
            check(REPORT, {}, context={"asset_ids": [""], "collection_ids": []})

    def test_structural_must_be_valid_or_invalid(self):
        with self.assertRaises(ValueError):
            check(ASSET, {}, structural="not-run")


class VersionRoutingTest(unittest.TestCase):
    def test_each_accepted_label_routes_at_each_root_selector(self):
        for name in STANDALONE_WITH_SELECTOR:
            for label in ("1.0.0", "1.1.0", "1.1.1", "1.2.0-draft.1"):
                with self.subTest(name=name, label=label):
                    outcome = check(name, {"schema_version": label})
                    batch = name in (ASSET_BATCH, COLLECTION_BATCH)
                    self.assertEqual((outcome.routing, outcome.execution_status), ("selected", "complete"))
                    self.assertEqual(codes(outcome), [("COMPLETENESS_UNVERIFIED", "")] if batch else [])

    def test_unknown_labels_are_unsupported_at_each_root_selector(self):
        labels = ["2.0.0", "1.2.0", "1.0", "1.1.2", "1.2.0-draft.2", " 1.0.0", "1.0.0 ", "v1.0.0", ""]
        for name in STANDALONE_WITH_SELECTOR:
            for label in labels:
                with self.subTest(name=name, label=label):
                    outcome = check(name, {"schema_version": label})
                    self.assertEqual((outcome.routing, outcome.execution_status), ("unsupported", "unsupported"))
                    self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/schema_version")])

    def test_non_string_selectors_are_unsupported(self):
        for label in (1, 1.0, True, False, None, ["1.0.0"], {"v": "1.0.0"}):
            with self.subTest(label=label):
                outcome = check(ASSET, {"schema_version": label}, structural="invalid")
                self.assertEqual(outcome.routing, "unsupported")
                self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/schema_version")])

    def test_absent_selectors_route_by_caller_selection(self):
        for name in STANDALONE_WITH_SELECTOR + (ANNOTATION,):
            with self.subTest(name=name):
                self.assertEqual(check(name, {}).routing, "selected")
        self.assertEqual(check(ASSET_BATCH, {"assets": [{}, {}]}).routing, "selected")
        self.assertEqual(check(COLLECTION_BATCH, {"collections": [{}]}).routing, "selected")

    def test_asset_batch_items_are_selectors(self):
        value = {"schema_version": "1.1.1", "assets": [
            {"schema_version": "1.0.0"}, {"schema_version": "3.0.0"}, {}, {"schema_version": 7},
        ]}
        outcome = check(ASSET_BATCH, value)
        self.assertEqual((outcome.routing, outcome.execution_status), ("unsupported", "unsupported"))
        self.assertEqual(
            codes(outcome),
            [("VERSION_UNSUPPORTED", "/assets/1/schema_version"), ("VERSION_UNSUPPORTED", "/assets/3/schema_version")],
        )

    def test_collection_batch_items_are_selectors(self):
        value = {"collections": [{"schema_version": "1.2.0-draft.1"}, {"schema_version": "0.1.0"}]}
        outcome = check(COLLECTION_BATCH, value)
        self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/collections/1/schema_version")])

    def test_unsupported_batch_root_and_items_are_all_reported(self):
        value = {"schema_version": "2.0.0", "assets": [{"schema_version": "2.0.0"}]}
        outcome = check(ASSET_BATCH, value)
        self.assertEqual(
            codes(outcome),
            [("VERSION_UNSUPPORTED", "/assets/0/schema_version"), ("VERSION_UNSUPPORTED", "/schema_version")],
        )

    def test_mixed_supported_labels_coexist_in_a_batch(self):
        value = {"schema_version": "1.2.0-draft.1", "assets": [
            {"schema_version": "1.0.0"}, {"schema_version": "1.1.0"}, {"schema_version": "1.1.1"}, {},
        ]}
        outcome = check(ASSET_BATCH, value)
        self.assertEqual((outcome.routing, outcome.execution_status), ("selected", "complete"))
        self.assertEqual(codes(outcome), [("COMPLETENESS_UNVERIFIED", "")])

    def test_mixed_supported_and_unsupported_batch_blocks_routing(self):
        value = {"schema_version": "1.1.0", "assets": [{"schema_version": "2.0.0"}, {"schema_version": "1.1.0"}]}
        with mock.patch.object(profiles, "RULES", [exploding_rule]):
            outcome = check(ASSET_BATCH, value)
        self.assertEqual((outcome.routing, outcome.execution_status), ("unsupported", "unsupported"))
        self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/assets/0/schema_version")])

    def test_batch_arrays_belong_only_to_their_own_entry_point(self):
        # An asset batch has no collections array selector, and vice versa.
        self.assertEqual(check(ASSET_BATCH, {"collections": [{"schema_version": "9"}]}).routing, "selected")
        self.assertEqual(check(COLLECTION_BATCH, {"assets": [{"schema_version": "9"}]}).routing, "selected")
        # A standalone asset or collection has no batch item selectors.
        self.assertEqual(check(COLLECTION, {"assets": [{"schema_version": "9"}]}).routing, "selected")
        self.assertEqual(check(ASSET, {"collections": [{"schema_version": "9"}]}).routing, "selected")

    def test_embedded_and_custom_objects_are_not_selectors(self):
        value = {
            "schema_version": "1.1.0",
            "files": [{"schema_version": "9", "derivatives": [{"schema_version": "9"}]}],
            "metadata_sets": [{"schema_version": "9"}],
            "temporal_annotations": [{"schema_version": "9"}],
            "extensions": {"schema_version": "9", "nested": {"schema_version": "9"}},
            "rights_information": {"schema_version": "9"},
        }
        self.assertEqual(check(ASSET, value).routing, "selected")
        collection = {"parent_storage": {"schema_version": "9"}, "metadata_sets": [{"schema_version": "9"}],
                      "extensions": {"schema_version": "9"}}
        self.assertEqual(check(COLLECTION, collection).routing, "selected")
        batch = {"assets": [{"files": [{"schema_version": "9"}], "extensions": {"schema_version": "9"}}],
                 "extensions": {"schema_version": "9"}}
        self.assertEqual(check(ASSET_BATCH, batch).routing, "selected")

    def test_annotation_custom_schema_version_is_not_a_selector(self):
        for label in ("9.9.9", 4, None):
            with self.subTest(label=label):
                value = {"schema_version": label, "metadata": {"schema_version": label}}
                self.assertEqual(check(ANNOTATION, value).routing, "selected")

    def test_asset_version_is_not_a_selector(self):
        for label in ("2.0.0", 3, None):
            with self.subTest(label=label):
                self.assertEqual(check(ASSET, {"version": label}).routing, "selected")

    def test_selectors_under_non_objects_are_not_inspected(self):
        for value in ([{"schema_version": "9"}], "1.0.0", 5, None):
            with self.subTest(value=value):
                self.assertEqual(check(ASSET, value, structural="invalid").routing, "selected")
        for items in ({"0": {"schema_version": "9"}}, "x", None):
            with self.subTest(items=items):
                self.assertEqual(check(ASSET_BATCH, {"assets": items}, structural="invalid").routing, "selected")
        value = {"assets": ["x", 3, None, [{"schema_version": "9"}], {"schema_version": "9"}]}
        outcome = check(ASSET_BATCH, value, structural="invalid")
        self.assertEqual(codes(outcome), [("VERSION_UNSUPPORTED", "/assets/4/schema_version")])

    def test_corpus_routing_cases(self):
        for case_id in (
            "exchange-v2-blocked", "exchange-unknown-version", "exchange-mixed-version-batch",
            "exchange-report-excluded", "exchange-nonstring-selector",
            "exchange-version-and-shape-failure", "exchange-final-label-not-draft",
        ):
            case = CASES[case_id]
            with self.subTest(case=case_id):
                document = parse_input((results.FIXTURES / case.path).read_bytes())
                structural = "valid" if case.expected_valid else "invalid"
                outcome = profiles.exchange_checker(case, document, structural)
                self.assertEqual(outcome.routing, case.expected_routing)
                self.assertEqual(outcome.execution_status, case.expected_execution_status)
                expected = sorted(case.expected_diagnostics, key=lambda d: (d.path, d.code))
                self.assertEqual(codes(outcome), [(d.code, d.path) for d in expected])


RELATIONSHIP_CODES = frozenset({
    "IDENTITY_UNUSABLE", "IDENTITY_DUPLICATE", "REFERENCE_UNRESOLVED",
    "MEMBERSHIP_UNINTERPRETED", "COLLECTION_CYCLE",
})
WHITESPACE_CHARACTERS = (" ", "\t", "\r", "\n", "\f", "\v")


def ctx(assets=(), collections=()):
    return {"asset_ids": list(assets), "collection_ids": list(collections)}


def locations(name, value):
    return [(template, pointer) for template, pointer, _ in profiles.entity_locations(name, value)]


class RuleRegistrationTest(unittest.TestCase):
    def test_relationship_rules_are_registered_in_order(self):
        self.assertEqual(profiles.RULES[:4], [
            profiles.identity_rule, profiles.duplicate_rule,
            profiles.reference_rule, profiles.cycle_rule,
        ])


class EntityLocationsTest(unittest.TestCase):
    def test_standalone_roots(self):
        self.assertEqual(locations(ASSET, {}), [("A", "")])
        self.assertEqual(locations(COLLECTION, {}), [("C", "")])
        self.assertEqual(locations(STORAGE, {}), [("S", "")])
        self.assertEqual(locations(METADATA_SET, {}), [("M", "")])
        self.assertEqual(locations(ANNOTATION, {}), [("T", "")])

    def test_excluded_entry_point_has_no_locations(self):
        self.assertEqual(locations(REPORT, {"assets": [{}], "collections": [{}]}), [])

    def test_batches(self):
        self.assertEqual(locations(ASSET_BATCH, {"assets": [{}, {}]}), [("A", "/assets/0"), ("A", "/assets/1")])
        self.assertEqual(locations(COLLECTION_BATCH, {"collections": [{}]}), [("C", "/collections/0")])
        self.assertEqual(locations(ASSET_BATCH, {"collections": [{}]}), [])
        self.assertEqual(locations(COLLECTION_BATCH, {"assets": [{}]}), [])

    def test_asset_children_and_recursive_derivatives(self):
        value = {
            "files": [{
                "storage_location": {},
                "derivatives": [{"derivatives": [{"storage_location": {}}]}],
            }],
            "metadata_sets": [{}],
            "collections": [{"parent_storage": {}, "metadata_sets": [{}]}],
            "temporal_annotations": [{}],
        }
        self.assertEqual(sorted(locations(ASSET, value)), sorted([
            ("A", ""),
            ("F", "/files/0"),
            ("S", "/files/0/storage_location"),
            ("F", "/files/0/derivatives/0"),
            ("F", "/files/0/derivatives/0/derivatives/0"),
            ("S", "/files/0/derivatives/0/derivatives/0/storage_location"),
            ("M", "/metadata_sets/0"),
            ("C", "/collections/0"),
            ("S", "/collections/0/parent_storage"),
            ("M", "/collections/0/metadata_sets/0"),
            ("T", "/temporal_annotations/0"),
        ]))

    def test_batch_asset_children_use_batch_pointers(self):
        value = {"assets": [{}, {"files": [{"storage_location": {}}], "collections": [{}]}]}
        self.assertEqual(sorted(locations(ASSET_BATCH, value)), sorted([
            ("A", "/assets/0"), ("A", "/assets/1"), ("F", "/assets/1/files/0"),
            ("S", "/assets/1/files/0/storage_location"), ("C", "/assets/1/collections/0"),
        ]))

    def test_collection_children(self):
        value = {"parent_storage": {}, "metadata_sets": [{}, {}], "assets": [{}]}
        self.assertEqual(sorted(locations(COLLECTION, value)), sorted([
            ("C", ""), ("S", "/parent_storage"), ("M", "/metadata_sets/0"), ("M", "/metadata_sets/1"),
        ]))

    def test_yields_the_entity_objects(self):
        storage = {"storage_id": "s1"}
        value = {"files": [{"storage_location": storage}]}
        found = {(t, p): o for t, p, o in profiles.entity_locations(ASSET, value)}
        self.assertIs(found[("S", "/files/0/storage_location")], storage)

    def test_never_enters_opaque_or_undeclared_content(self):
        nested = {"files": [{}], "collections": [{}], "metadata_sets": [{}], "temporal_annotations": [{}],
                  "storage_location": {}, "parent_storage": {}, "derivatives": [{}], "assets": [{}]}
        value = {
            "extensions": nested,
            "rights_information": nested,
            "unknown": nested,
            "files": [{"technical_metadata": nested, "extensions": nested,
                       "storage_location": {"connection_details": nested, "security": nested, "extensions": nested}}],
            "temporal_annotations": [{"metadata": nested}],
            "collections": [{"permissions": nested, "extensions": nested, "assets": [nested]}],
        }
        self.assertEqual(sorted(locations(ASSET, value)), sorted([
            ("A", ""), ("F", "/files/0"), ("S", "/files/0/storage_location"),
            ("T", "/temporal_annotations/0"), ("C", "/collections/0"),
        ]))
        self.assertEqual(locations(STORAGE, {"connection_details": nested, "security": nested}), [("S", "")])
        self.assertEqual(locations(ANNOTATION, {"metadata": nested}), [("T", "")])
        self.assertEqual(locations(ASSET_BATCH, {"assets": [], "extensions": nested}), [])

    def test_skips_values_of_undeclared_types(self):
        for root in ([], "x", 3, None):
            with self.subTest(root=root):
                self.assertEqual(locations(ASSET, root), [])
        value = {
            "files": [None, "x", {"storage_location": "s", "derivatives": {"0": {}}}],
            "metadata_sets": {"0": {}},
            "collections": [3, {"parent_storage": []}],
            "temporal_annotations": "t",
        }
        self.assertEqual(sorted(locations(ASSET, value)), sorted([
            ("A", ""), ("F", "/files/2"), ("C", "/collections/1"),
        ]))
        self.assertEqual(locations(ASSET_BATCH, {"assets": [None, {}]}), [("A", "/assets/1")])
        self.assertEqual(locations(COLLECTION_BATCH, {"collections": {"0": {}}}), [])

    def test_deep_derivative_chain_does_not_exhaust_the_stack(self):
        depth = 5000
        file = {}
        value = {"files": [file]}
        for _ in range(depth):
            child = {}
            file["derivatives"] = [child]
            file = child
        found = locations(ASSET, value)
        self.assertEqual(len([t for t, _ in found if t == "F"]), depth + 1)


class RelationshipCase(unittest.TestCase):
    """Compare only this step's relationship codes, in contract order."""

    def assert_relationship(self, name, value, expected, context=EMPTY_CONTEXT):
        outcome = check(name, value, context=context)
        found = [pair for pair in codes(outcome) if pair[0] in RELATIONSHIP_CODES]
        self.assertEqual(found, sorted(expected, key=lambda pair: (pair[1], pair[0])))
        return outcome


class IdentityTest(RelationshipCase):
    def test_each_whitespace_character_and_empty_is_unusable(self):
        for blank in [""] + list(WHITESPACE_CHARACTERS) + [" \t\r\n\f\v"]:
            with self.subTest(blank=blank):
                outcome = self.assert_relationship(ASSET, {"asset_id": blank}, [("IDENTITY_UNUSABLE", "/asset_id")])
                self.assertEqual(outcome.execution_status, "blocked")

    def test_non_ascii_space_and_padded_ids_are_usable(self):
        for identity in (" ", "　", " ", " a ", "\ta", "a"):
            with self.subTest(identity=identity):
                self.assert_relationship(ASSET, {"asset_id": identity}, [])

    def test_every_identity_location_in_an_asset(self):
        value = {
            "asset_id": " ",
            "files": [{"storage_location": {"storage_id": ""},
                       "derivatives": [{"storage_location": {"storage_id": "\t"}}]}],
            "metadata_sets": [{"set_id": "\n", "fields": [{"name": "ok"}, {"name": "\v"}]}],
            "collections": [{"collection_id": "\f", "parent_storage": {"storage_id": "\r"},
                             "metadata_sets": [{"set_id": "", "fields": [{"name": " "}]}]}],
            "temporal_annotations": [{"source_id": "  "}],
        }
        self.assert_relationship(ASSET, value, [
            ("IDENTITY_UNUSABLE", "/asset_id"),
            ("IDENTITY_UNUSABLE", "/files/0/storage_location/storage_id"),
            ("IDENTITY_UNUSABLE", "/files/0/derivatives/0/storage_location/storage_id"),
            ("IDENTITY_UNUSABLE", "/metadata_sets/0/set_id"),
            ("IDENTITY_UNUSABLE", "/metadata_sets/0/fields/1/name"),
            ("IDENTITY_UNUSABLE", "/collections/0/collection_id"),
            ("IDENTITY_UNUSABLE", "/collections/0/parent_storage/storage_id"),
            ("IDENTITY_UNUSABLE", "/collections/0/metadata_sets/0/set_id"),
            ("IDENTITY_UNUSABLE", "/collections/0/metadata_sets/0/fields/0/name"),
            ("IDENTITY_UNUSABLE", "/temporal_annotations/0/source_id"),
        ])

    def test_standalone_identity_roots(self):
        self.assert_relationship(COLLECTION, {"collection_id": " "}, [("IDENTITY_UNUSABLE", "/collection_id")])
        self.assert_relationship(STORAGE, {"storage_id": ""}, [("IDENTITY_UNUSABLE", "/storage_id")])
        self.assert_relationship(METADATA_SET, {"set_id": "\t", "fields": [{"name": ""}]}, [
            ("IDENTITY_UNUSABLE", "/set_id"), ("IDENTITY_UNUSABLE", "/fields/0/name"),
        ])
        self.assert_relationship(ANNOTATION, {"source_id": "\n"}, [("IDENTITY_UNUSABLE", "/source_id")])
        self.assert_relationship(ASSET_BATCH, {"assets": [{"asset_id": "a"}, {"asset_id": " "}]},
                                 [("IDENTITY_UNUSABLE", "/assets/1/asset_id")])
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"collection_id": ""}]},
                                 [("IDENTITY_UNUSABLE", "/collections/0/collection_id")])

    def test_absent_identity_is_not_required(self):
        for name in (ASSET, COLLECTION, STORAGE, METADATA_SET, ANNOTATION):
            with self.subTest(name=name):
                self.assert_relationship(name, {}, [])
        self.assert_relationship(METADATA_SET, {"fields": [{}]}, [])

    def test_titles_labels_and_other_names_are_not_identities(self):
        self.assert_relationship(ASSET, {"asset_id": "a", "title": " ", "temporal_annotations": [{"name": ""}],
                                         "collections": [{"collection_id": "c", "label": ""}]}, [])
        self.assert_relationship(ANNOTATION, {"name": " "}, [])
        self.assert_relationship(METADATA_SET, {"label": "", "fields": [{"name": "n", "label": ""}]}, [])

    def test_identity_keys_inside_opaque_content_are_ignored(self):
        blank = {"asset_id": "", "collection_id": " ", "storage_id": "", "set_id": "", "source_id": "",
                 "name": "", "fields": [{"name": ""}]}
        value = {"asset_id": "a", "extensions": blank, "rights_information": blank,
                 "files": [{"technical_metadata": blank,
                            "storage_location": {"storage_id": "s", "connection_details": blank, "security": blank}}],
                 "temporal_annotations": [{"metadata": blank}],
                 "collections": [{"permissions": blank, "assets": [blank]}]}
        self.assert_relationship(ASSET, value, [("MEMBERSHIP_UNINTERPRETED", "/collections/0/assets/0")])

    def test_non_string_identities_are_skipped(self):
        self.assert_relationship(ASSET, {"asset_id": 5, "collections": [{"collection_id": None}]}, [])

    def test_relationship_messages_do_not_echo_input_values(self):
        value = {"collections": [{"collection_id": "secret-c", "parent": "secret-c", "assets": ["secret-a", {}]},
                                 {"collection_id": "secret-c"}, {"collection_id": " "}]}
        outcome = check(COLLECTION_BATCH, value)
        self.assertEqual({d.code for d in outcome.diagnostics}, {
            "IDENTITY_UNUSABLE", "IDENTITY_DUPLICATE", "REFERENCE_UNRESOLVED", "MEMBERSHIP_UNINTERPRETED",
            "COMPLETENESS_UNVERIFIED",
        })
        self.assertTrue(all("secret" not in d.message for d in outcome.diagnostics))
        outcome = check(COLLECTION, {"collection_id": "secret-c", "parent": "secret-c"})
        self.assertEqual(codes(outcome), [("COLLECTION_CYCLE", "/parent")])
        self.assertTrue(all("secret" not in d.message for d in outcome.diagnostics))
        self.assertEqual(results.severity_problems(outcome.diagnostics), [])

    def test_identity_values_are_not_rewritten(self):
        document = doc({"assets": [{"asset_id": " a "}, {"asset_id": " a "}, {"asset_id": " "}]})
        before = json.dumps(document.value)
        profiles.validate_profile(ASSET_BATCH, document, "exchange-1x", structural="valid",
                                  reference_context=EMPTY_CONTEXT)
        self.assertEqual(json.dumps(document.value), before)


class DuplicateTest(RelationshipCase):
    def test_every_repeat_after_the_first_is_reported(self):
        value = {"assets": [{"asset_id": "a"}, {"asset_id": "b"}, {"asset_id": "a"}, {"asset_id": "a"}]}
        self.assert_relationship(ASSET_BATCH, value, [
            ("IDENTITY_DUPLICATE", "/assets/2/asset_id"), ("IDENTITY_DUPLICATE", "/assets/3/asset_id"),
        ])
        value = {"collections": [{"collection_id": "c"}, {"collection_id": "c"}]}
        outcome = self.assert_relationship(COLLECTION_BATCH, value, [
            ("IDENTITY_DUPLICATE", "/collections/1/collection_id"),
        ])
        self.assertEqual(outcome.execution_status, "blocked")

    def test_comparison_is_exact(self):
        value = {"assets": [{"asset_id": "a"}, {"asset_id": "A"}, {"asset_id": " a"}, {"asset_id": "a "},
                            {"asset_id": "é"}, {"asset_id": "é"}]}
        self.assert_relationship(ASSET_BATCH, value, [])

    def test_absent_ids_are_not_duplicates(self):
        self.assert_relationship(ASSET_BATCH, {"assets": [{}, {}, {"asset_id": "a"}]}, [])

    def test_repeated_unusable_ids_are_unusable_and_duplicate(self):
        value = {"assets": [{"asset_id": " "}, {"asset_id": " "}]}
        self.assert_relationship(ASSET_BATCH, value, [
            ("IDENTITY_UNUSABLE", "/assets/0/asset_id"), ("IDENTITY_UNUSABLE", "/assets/1/asset_id"),
            ("IDENTITY_DUPLICATE", "/assets/1/asset_id"),
        ])

    def test_repeated_embedded_entities_are_preserved_without_duplicates(self):
        value = {
            "asset_id": "a",
            "collections": [{"collection_id": "c"}, {"collection_id": "c"}],
            "files": [{"storage_location": {"storage_id": "s"}}, {"storage_location": {"storage_id": "s"}}],
            "metadata_sets": [{"set_id": "m", "fields": [{"name": "f"}, {"name": "f"}]}, {"set_id": "m"}],
            "temporal_annotations": [{"source_id": "t"}, {"source_id": "t"}],
        }
        self.assert_relationship(ASSET, value, [])
        batch = {"assets": [{"asset_id": "a", "collections": [{"collection_id": "c"}]},
                            {"asset_id": "b", "collections": [{"collection_id": "c"}]}]}
        self.assert_relationship(ASSET_BATCH, batch, [])
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"collection_id": "c", "assets": ["x"]},
                                                                    {"collection_id": "d", "assets": ["x"]}]},
                                 [("REFERENCE_UNRESOLVED", "/collections/0/assets/0"),
                                  ("REFERENCE_UNRESOLVED", "/collections/1/assets/0")])

    def test_asset_and_collection_namespaces_are_separate(self):
        value = {"assets": [{"asset_id": "x", "collections": [{"collection_id": "x"}]}]}
        self.assert_relationship(ASSET_BATCH, value, [])


class ReferenceTest(RelationshipCase):
    def test_unknown_standalone_parent_is_unresolved_warning(self):
        outcome = self.assert_relationship(COLLECTION, {"collection_id": "c", "parent": "p"},
                                           [("REFERENCE_UNRESOLVED", "/parent")])
        self.assertEqual(outcome.execution_status, "complete")

    def test_null_and_absent_parent_mean_no_link(self):
        self.assert_relationship(COLLECTION, {"collection_id": "c", "parent": None}, [])
        self.assert_relationship(COLLECTION, {"collection_id": "c"}, [])
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"collection_id": "c", "parent": None}]}, [])

    def test_blank_parent_is_a_reference_that_cannot_resolve(self):
        for blank in ("", " "):
            with self.subTest(blank=blank):
                self.assert_relationship(COLLECTION, {"collection_id": "c", "parent": blank},
                                         [("REFERENCE_UNRESOLVED", "/parent")])

    def test_context_only_targets_resolve(self):
        context = ctx(assets=["a1", "a1"], collections=["p"])
        self.assert_relationship(COLLECTION, {"collection_id": "c", "parent": "p", "assets": ["a1"]}, [],
                                 context=context)
        self.assert_relationship(COLLECTION, {"parent": "p", "assets": ["a1"]}, [], context=context)
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"parent": "p", "assets": ["a1"]}]}, [],
                                 context=context)
        self.assert_relationship(ASSET, {"collections": [{"parent": "p", "assets": ["a1"]}]}, [], context=context)
        self.assert_relationship(ASSET_BATCH, {"assets": [{"collections": [{"parent": "p", "assets": ["a1"]}]}]},
                                 [], context=context)

    def test_context_kinds_do_not_cross(self):
        context = ctx(assets=["x"], collections=["y"])
        self.assert_relationship(COLLECTION, {"parent": "x", "assets": ["y"]}, [
            ("REFERENCE_UNRESOLVED", "/parent"), ("REFERENCE_UNRESOLVED", "/assets/0"),
        ], context=context)

    def test_standalone_collection_knows_its_own_id_but_not_as_an_asset(self):
        self.assert_relationship(COLLECTION, {"collection_id": "c", "assets": ["c"]},
                                 [("REFERENCE_UNRESOLVED", "/assets/0")])

    def test_unusable_own_id_does_not_resolve(self):
        self.assert_relationship(COLLECTION, {"collection_id": " ", "parent": " "}, [
            ("IDENTITY_UNUSABLE", "/collection_id"), ("REFERENCE_UNRESOLVED", "/parent"),
        ])
        self.assert_relationship(ASSET, {"asset_id": "", "collections": [{"assets": [""]}]}, [
            ("IDENTITY_UNUSABLE", "/asset_id"), ("REFERENCE_UNRESOLVED", "/collections/0/assets/0"),
        ])

    def test_membership_resolution_and_partial_lists(self):
        self.assert_relationship(COLLECTION, {"assets": []}, [])
        self.assert_relationship(COLLECTION, {"assets": ["a", "b", "a"]}, [
            ("REFERENCE_UNRESOLVED", "/assets/0"), ("REFERENCE_UNRESOLVED", "/assets/1"),
            ("REFERENCE_UNRESOLVED", "/assets/2"),
        ], context=ctx())
        self.assert_relationship(COLLECTION, {"assets": ["a", "b"]}, [("REFERENCE_UNRESOLVED", "/assets/1")],
                                 context=ctx(assets=["a"]))

    def test_collection_batch_ids_resolve_parents_but_not_assets(self):
        value = {"collections": [{"collection_id": "c1", "parent": "c2"},
                                 {"collection_id": "c2", "assets": ["c1"]}]}
        self.assert_relationship(COLLECTION_BATCH, value, [("REFERENCE_UNRESOLVED", "/collections/1/assets/0")])

    def test_excluded_duplicates_do_not_resolve_even_from_context(self):
        value = {"collections": [{"collection_id": "d"}, {"collection_id": "d"},
                                 {"collection_id": "e", "parent": "d"}]}
        for context in (ctx(), ctx(collections=["d"])):
            with self.subTest(context=context):
                self.assert_relationship(COLLECTION_BATCH, value, [
                    ("IDENTITY_DUPLICATE", "/collections/1/collection_id"),
                    ("REFERENCE_UNRESOLVED", "/collections/2/parent"),
                ], context=context)

    def test_asset_knows_own_id_and_its_embedded_collections(self):
        value = {"asset_id": "a", "collections": [
            {"collection_id": "c1", "parent": "c2", "assets": ["a", "b"]},
            {"collection_id": "c2", "parent": "c3"},
        ]}
        self.assert_relationship(ASSET, value, [
            ("REFERENCE_UNRESOLVED", "/collections/0/assets/1"),
            ("REFERENCE_UNRESOLVED", "/collections/1/parent"),
        ])

    def test_repeated_embedded_collection_ids_do_not_resolve(self):
        value = {"collections": [{"collection_id": "c"}, {"collection_id": "c"}, {"parent": "c"}]}
        for context in (ctx(), ctx(collections=["c"])):
            with self.subTest(context=context):
                self.assert_relationship(ASSET, value, [("REFERENCE_UNRESOLVED", "/collections/2/parent")],
                                         context=context)

    def test_asset_batch_ids_resolve_membership_and_collections_stay_local(self):
        value = {"assets": [
            {"asset_id": "a1", "collections": [{"collection_id": "c1", "assets": ["a2", "a3"]}]},
            {"asset_id": "a2", "collections": [{"collection_id": "c2", "parent": "c1"}]},
            {"asset_id": "a3"},
            {"asset_id": "a3"},
        ]}
        for context in (ctx(), ctx(assets=["a3"])):
            with self.subTest(context=context):
                self.assert_relationship(ASSET_BATCH, value, [
                    ("REFERENCE_UNRESOLVED", "/assets/0/collections/0/assets/1"),
                    ("REFERENCE_UNRESOLVED", "/assets/1/collections/0/parent"),
                    ("IDENTITY_DUPLICATE", "/assets/3/asset_id"),
                ], context=context)

    def test_other_entry_points_have_no_reference_checks(self):
        self.assert_relationship(STORAGE, {"parent": "p", "assets": [{}]}, [])
        self.assert_relationship(METADATA_SET, {"parent": "p", "assets": ["x"]}, [])
        self.assert_relationship(ANNOTATION, {"parent": "p", "assets": ["x"]}, [])
        self.assert_relationship(ASSET, {"parent": "p", "assets": ["x"]}, [])

    def test_non_string_items_are_uninterpreted_membership(self):
        items = [{"asset_id": "a"}, {"asset_id": " "}, 5, None, True, ["a"]]
        value = {"asset_id": "a", "collections": [{"assets": items}]}
        outcome = self.assert_relationship(ASSET, value, [
            ("MEMBERSHIP_UNINTERPRETED", f"/collections/0/assets/{i}") for i in range(len(items))
        ])
        self.assertEqual(outcome.execution_status, "complete")

    def test_embedded_object_membership_never_becomes_identity(self):
        value = {"assets": [{"asset_id": "a", "collections": [{"assets": [{"asset_id": "a"}]}]},
                            {"asset_id": "b", "collections": [{"assets": [{"asset_id": "a"}]}]}]}
        self.assert_relationship(ASSET_BATCH, value, [
            ("MEMBERSHIP_UNINTERPRETED", "/assets/0/collections/0/assets/0"),
            ("MEMBERSHIP_UNINTERPRETED", "/assets/1/collections/0/assets/0"),
        ])

    def test_non_string_parent_is_skipped(self):
        self.assert_relationship(COLLECTION, {"parent": 3}, [])


class CycleTest(RelationshipCase):
    def test_two_and_three_record_batch_cycles(self):
        two = {"collections": [{"collection_id": "a", "parent": "b"}, {"collection_id": "b", "parent": "a"}]}
        outcome = self.assert_relationship(COLLECTION_BATCH, two, [
            ("COLLECTION_CYCLE", "/collections/0/parent"), ("COLLECTION_CYCLE", "/collections/1/parent"),
        ])
        self.assertEqual(outcome.execution_status, "blocked")
        three = {"collections": [{"collection_id": "a", "parent": "b"}, {"collection_id": "b", "parent": "c"},
                                 {"collection_id": "c", "parent": "a"}]}
        self.assert_relationship(COLLECTION_BATCH, three, [
            ("COLLECTION_CYCLE", f"/collections/{i}/parent") for i in range(3)
        ])

    def test_only_edges_on_the_cycle_are_reported(self):
        value = {"collections": [
            {"collection_id": "tail", "parent": "a"},
            {"collection_id": "a", "parent": "b"},
            {"collection_id": "b", "parent": "a"},
            {"collection_id": "root"},
            {"collection_id": "child", "parent": "root"},
        ]}
        self.assert_relationship(COLLECTION_BATCH, value, [
            ("COLLECTION_CYCLE", "/collections/1/parent"), ("COLLECTION_CYCLE", "/collections/2/parent"),
        ])

    def test_self_parent_in_each_placement(self):
        self.assert_relationship(COLLECTION, {"collection_id": "a", "parent": "a"}, [("COLLECTION_CYCLE", "/parent")])
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"collection_id": "a", "parent": "a"}]},
                                 [("COLLECTION_CYCLE", "/collections/0/parent")])
        self.assert_relationship(ASSET, {"collections": [{"collection_id": "a", "parent": "a"}]},
                                 [("COLLECTION_CYCLE", "/collections/0/parent")])
        self.assert_relationship(ASSET_BATCH, {"assets": [{"collections": [{"collection_id": "a", "parent": "a"}]}]},
                                 [("COLLECTION_CYCLE", "/assets/0/collections/0/parent")])

    def test_embedded_multi_record_cycles_are_not_reported(self):
        value = {"collections": [{"collection_id": "a", "parent": "b"}, {"collection_id": "b", "parent": "a"}]}
        self.assert_relationship(ASSET, value, [])

    def test_excluded_ids_break_cycles_and_self_loops(self):
        value = {"collections": [
            {"collection_id": "a", "parent": "b"},
            {"collection_id": "b", "parent": "a"},
            {"collection_id": "a", "parent": "a"},
        ]}
        self.assert_relationship(COLLECTION_BATCH, value, [
            ("REFERENCE_UNRESOLVED", "/collections/1/parent"),
            ("IDENTITY_DUPLICATE", "/collections/2/collection_id"),
            ("REFERENCE_UNRESOLVED", "/collections/2/parent"),
        ])
        embedded = {"collections": [{"collection_id": "a", "parent": "a"}, {"collection_id": "a"}]}
        self.assert_relationship(ASSET, embedded, [("REFERENCE_UNRESOLVED", "/collections/0/parent")],
                                 context=ctx(collections=["a"]))

    def test_cycles_through_context_records_are_not_reported(self):
        value = {"collections": [{"collection_id": "a", "parent": "x"}]}
        self.assert_relationship(COLLECTION_BATCH, value, [], context=ctx(collections=["x"]))

    def test_unusable_self_parent_is_not_a_cycle(self):
        self.assert_relationship(COLLECTION_BATCH, {"collections": [{"collection_id": " ", "parent": " "}]}, [
            ("IDENTITY_UNUSABLE", "/collections/0/collection_id"),
            ("REFERENCE_UNRESOLVED", "/collections/0/parent"),
        ])

    def test_long_chain_and_cycle_do_not_exhaust_the_stack(self):
        size = 5000
        chain = [{"collection_id": f"c{i}", "parent": f"c{i + 1}"} for i in range(size)]
        chain.append({"collection_id": f"c{size}"})
        self.assert_relationship(COLLECTION_BATCH, {"collections": chain}, [])
        ring = [{"collection_id": f"c{i}", "parent": f"c{(i + 1) % size}"} for i in range(size)]
        outcome = check(COLLECTION_BATCH, {"collections": ring})
        self.assertEqual(len([d for d in outcome.diagnostics if d.code == "COLLECTION_CYCLE"]), size)


class RelationshipCorpusTest(unittest.TestCase):
    def test_corpus_relationship_diagnostics(self):
        checked = 0
        for case in CASES.values():
            if case.profile != "exchange-1x" or not case.id.startswith("exchange-") or case.expected_valid is not True:
                continue
            try:
                document = parse_input((results.FIXTURES / case.path).read_bytes())
            except NumericResourceRefused:
                continue  # A setup refusal: no profile runs.
            with self.subTest(case=case.id):
                outcome = profiles.exchange_checker(case, document, "valid")
                found = [pair for pair in codes(outcome) if pair[0] in RELATIONSHIP_CODES]
                expected = sorted(
                    ((d.code, d.path) for d in case.expected_diagnostics if d.code in RELATIONSHIP_CODES),
                    key=lambda pair: (pair[1], pair[0]),
                )
                self.assertEqual(found, expected)
                checked += 1
        self.assertGreater(checked, 40)


FILE_CODES = frozenset({
    "SIZE_UNUSABLE", "INTEGRITY_UNVERIFIED", "CHECKSUM_UNINTERPRETED", "COMPLETENESS_UNVERIFIED",
    "VALUE_SEMANTICS_UNSPECIFIED", "CONNECTION_DATA_UNREVIEWED", "RIGHTS_UNSUPPORTED",
})


def valid_file(**storage):
    """A structurally valid file object whose storage location carries extra members."""
    location = {"storage_id": "s1", "system": "filesystem", "path": "/p"}
    location.update(storage)
    return {"type": "video", "role": "essence", "uri": "u", "checksum": "c", "storage_location": location}


def assert_structurally_valid(test, name, value):
    test.assertEqual(validate_legacy(name, doc(value), root=BASELINE), [])


class FileCase(unittest.TestCase):
    """Compare only this step's codes, in contract order."""

    def assert_file_codes(self, name, value, expected, context=EMPTY_CONTEXT):
        outcome = check(name, value, context=context)
        found = [pair for pair in codes(outcome) if pair[0] in FILE_CODES]
        self.assertEqual(found, sorted(expected, key=lambda pair: (pair[1], pair[0])))
        return outcome


class FileRuleRegistrationTest(unittest.TestCase):
    def test_file_rules_are_registered_after_relationship_rules(self):
        self.assertEqual(profiles.RULES[4:9], [
            profiles.file_rule, profiles.completeness_rule, profiles.metadata_value_rule,
            profiles.connection_rule, profiles.rights_rule,
        ])


class FileRuleTest(FileCase):
    def test_negative_size_is_unusable_and_blocks(self):
        outcome = check(ASSET, {"files": [{"checksum": "x", "size": -1}]})
        self.assertIn(("SIZE_UNUSABLE", "/files/0/size"), codes(outcome))
        self.assertEqual(outcome.execution_status, "blocked")

    def test_negative_decimal_and_big_integer_sizes_compare_exactly(self):
        parsed = parse_input(b'{"files":[{"checksum":"x","size":-0.0000000000000000000000000001},'
                             b'{"checksum":"x","size":0.0},{"checksum":"x","size":-0},'
                             b'{"checksum":"x","size":-100000000000000000000000000000}]}')
        found = [p for p in codes(profiles.validate_profile(
            ASSET, parsed, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT))
            if p[0] == "SIZE_UNUSABLE"]
        self.assertEqual(found, [("SIZE_UNUSABLE", "/files/0/size"), ("SIZE_UNUSABLE", "/files/3/size")])

    def test_zero_positive_and_absent_size_are_quiet(self):
        value = {"files": [{"checksum": "x", "size": 0}, {"checksum": "x", "size": 5}, {"checksum": "x"}]}
        self.assert_file_codes(ASSET, value, [("CHECKSUM_UNINTERPRETED", f"/files/{i}/checksum") for i in range(3)])

    def test_absent_or_empty_checksum_is_unverified_at_the_file(self):
        value = {"files": [{}, {"checksum": ""}, {"checksum": "abc"}]}
        self.assert_file_codes(ASSET, value, [
            ("INTEGRITY_UNVERIFIED", "/files/0"), ("INTEGRITY_UNVERIFIED", "/files/1"),
            ("CHECKSUM_UNINTERPRETED", "/files/2/checksum"),
        ])

    def test_whitespace_checksum_is_nonempty(self):
        self.assert_file_codes(ASSET, {"files": [{"checksum": " "}]},
                               [("CHECKSUM_UNINTERPRETED", "/files/0/checksum")])

    def test_file_rules_follow_derivatives_and_batches(self):
        derivative = {"size": -1, "derivatives": [{"checksum": "z"}]}
        value = {"assets": [{"files": [{"checksum": "a", "derivatives": [derivative]}]}]}
        self.assert_file_codes(ASSET_BATCH, value, [
            ("COMPLETENESS_UNVERIFIED", ""),
            ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/checksum"),
            ("INTEGRITY_UNVERIFIED", "/assets/0/files/0/derivatives/0"),
            ("SIZE_UNUSABLE", "/assets/0/files/0/derivatives/0/size"),
            ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/derivatives/0/derivatives/0/checksum"),
        ])

    def test_file_with_no_files_and_nonfile_places_are_quiet(self):
        self.assert_file_codes(ASSET, {"extensions": {"files": [{"size": -1}]}}, [])
        self.assert_file_codes(COLLECTION, {"files": [{"size": -1}]}, [])


class CompletenessTest(FileCase):
    def test_both_batch_entry_points_report_at_root(self):
        for name, value in ((ASSET_BATCH, {"assets": []}), (COLLECTION_BATCH, {"collections": []})):
            with self.subTest(name=name):
                outcome = self.assert_file_codes(name, value, [("COMPLETENESS_UNVERIFIED", "")])
                self.assertEqual(outcome.execution_status, "complete")

    def test_batch_with_count_or_checksum_still_reports(self):
        self.assert_file_codes(ASSET_BATCH, {"assets": [], "total_count": 0, "checksum": "x"},
                               [("COMPLETENESS_UNVERIFIED", "")])

    def test_single_entry_points_do_not_report(self):
        for name in (ASSET, COLLECTION, METADATA_SET, STORAGE, ANNOTATION):
            with self.subTest(name=name):
                self.assert_file_codes(name, {}, [])


class MetadataValueTest(FileCase):
    def test_present_value_of_any_kind_is_reported(self):
        fields = [{"value": v} for v in (None, 0, "", False, [], {}, "x", 1)] + [{"name": "n"}]
        self.assert_file_codes(METADATA_SET, {"fields": fields},
                               [("VALUE_SEMANTICS_UNSPECIFIED", f"/fields/{i}/value") for i in range(8)])

    def test_asset_and_collection_metadata_sets(self):
        sets = [{"fields": [{"value": 1}]}]
        self.assert_file_codes(ASSET, {"metadata_sets": sets, "collections": [{"metadata_sets": sets}]}, [
            ("VALUE_SEMANTICS_UNSPECIFIED", "/metadata_sets/0/fields/0/value"),
            ("VALUE_SEMANTICS_UNSPECIFIED", "/collections/0/metadata_sets/0/fields/0/value"),
        ])
        self.assert_file_codes(COLLECTION_BATCH, {"collections": [{"metadata_sets": sets}]}, [
            ("COMPLETENESS_UNVERIFIED", ""),
            ("VALUE_SEMANTICS_UNSPECIFIED", "/collections/0/metadata_sets/0/fields/0/value"),
        ])

    def test_value_is_not_inspected_and_declarations_are_not_executed(self):
        field = {"name": "n", "type": "integer", "required": True, "value": {"value": 1, "fields": [{"value": 2}]}}
        self.assert_file_codes(METADATA_SET, {"fields": [field]}, [("VALUE_SEMANTICS_UNSPECIFIED", "/fields/0/value")])


class ConnectionDataTest(FileCase):
    def test_nonempty_object_is_unreviewed_at_every_storage(self):
        details = {"endpoint": "e"}
        value = {"files": [{"checksum": "x", "storage_location": {"connection_details": details}}],
                 "collections": [{"parent_storage": {"connection_details": details}}]}
        outcome = self.assert_file_codes(ASSET, value, [
            ("CONNECTION_DATA_UNREVIEWED", "/files/0/storage_location/connection_details"),
            ("CONNECTION_DATA_UNREVIEWED", "/collections/0/parent_storage/connection_details"),
            ("CHECKSUM_UNINTERPRETED", "/files/0/checksum"),
        ])
        self.assertEqual(outcome.execution_status, "blocked")
        self.assert_file_codes(STORAGE, {"connection_details": details},
                               [("CONNECTION_DATA_UNREVIEWED", "/connection_details")])

    def test_empty_object_is_permitted_and_contents_are_not_entered(self):
        self.assert_file_codes(STORAGE, {"connection_details": {}}, [])
        self.assert_file_codes(STORAGE, {"extensions": {"connection_details": {"a": 1}}}, [])

    def test_message_does_not_echo_values(self):
        outcome = check(STORAGE, {"connection_details": {"password": "hunter2"}})
        self.assertNotIn("hunter2", repr(outcome.diagnostics))

    def test_derivative_and_batch_asset_storage_paths_are_exact(self):
        sensitive = {"connection_details": {"endpoint": "e"}, "security": {"acl": "x"}}
        derivative_file = valid_file()
        derivative_file["derivatives"] = [valid_file(**sensitive)]
        asset = {"asset_id": "a1", "title": "T", "type": "video", "rights_information": "All rights reserved", "files": [derivative_file]}
        asset["files"][0]["derivatives"][0]["checksum"] = "c"
        batch = {"assets": [dict(asset, files=[dict(derivative_file)])]}
        assert_structurally_valid(self, ASSET, asset)
        assert_structurally_valid(self, ASSET_BATCH, batch)
        self.assert_file_codes(ASSET, asset, [
            ("CHECKSUM_UNINTERPRETED", "/files/0/checksum"),
            ("CHECKSUM_UNINTERPRETED", "/files/0/derivatives/0/checksum"),
            ("RIGHTS_UNSUPPORTED", "/rights_information"),
            ("CONNECTION_DATA_UNREVIEWED", "/files/0/derivatives/0/storage_location/connection_details"),
            ("RIGHTS_UNSUPPORTED", "/files/0/derivatives/0/storage_location/security"),
        ])
        self.assert_file_codes(ASSET_BATCH, batch, [
            ("COMPLETENESS_UNVERIFIED", ""),
            ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/checksum"),
            ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/derivatives/0/checksum"),
            ("RIGHTS_UNSUPPORTED", "/assets/0/rights_information"),
            ("CONNECTION_DATA_UNREVIEWED",
             "/assets/0/files/0/derivatives/0/storage_location/connection_details"),
            ("RIGHTS_UNSUPPORTED", "/assets/0/files/0/derivatives/0/storage_location/security"),
        ])

    def test_batch_asset_direct_file_storage_paths_are_exact(self):
        batch = {"assets": [{"asset_id": "a1", "title": "T", "type": "video", "files": [valid_file(
            connection_details={"endpoint": "e"}, security={"acl": "x"})]}]}
        assert_structurally_valid(self, ASSET_BATCH, batch)
        self.assert_file_codes(ASSET_BATCH, batch, [
            ("COMPLETENESS_UNVERIFIED", ""),
            ("CHECKSUM_UNINTERPRETED", "/assets/0/files/0/checksum"),
            ("CONNECTION_DATA_UNREVIEWED", "/assets/0/files/0/storage_location/connection_details"),
            ("RIGHTS_UNSUPPORTED", "/assets/0/files/0/storage_location/security"),
        ])


class RightsTest(FileCase):
    def test_asset_rights_information_nonempty_string(self):
        self.assert_file_codes(ASSET, {"rights_information": "All rights reserved"},
                               [("RIGHTS_UNSUPPORTED", "/rights_information")])
        self.assert_file_codes(ASSET, {"rights_information": ""}, [])
        self.assert_file_codes(ASSET, {}, [])

    def test_collection_permissions_nonempty_object(self):
        self.assert_file_codes(COLLECTION, {"permissions": {"read": ["a"]}}, [("RIGHTS_UNSUPPORTED", "/permissions")])
        self.assert_file_codes(COLLECTION, {"permissions": {}}, [])
        self.assert_file_codes(ASSET, {"collections": [{"permissions": {"a": 1}}]},
                               [("RIGHTS_UNSUPPORTED", "/collections/0/permissions")])

    def test_storage_security_nonempty_object(self):
        self.assert_file_codes(STORAGE, {"security": {"acl": "x"}}, [("RIGHTS_UNSUPPORTED", "/security")])
        self.assert_file_codes(STORAGE, {"security": {}}, [])
        outcome = self.assert_file_codes(
            COLLECTION, {"parent_storage": {"security": {"a": 1}}}, [("RIGHTS_UNSUPPORTED", "/parent_storage/security")])
        self.assertEqual(outcome.execution_status, "blocked")

    def test_only_declared_locations_are_inspected(self):
        self.assert_file_codes(ASSET, {"files": [{"checksum": "x", "permissions": {"a": 1}, "security": {"a": 1}}]},
                               [("CHECKSUM_UNINTERPRETED", "/files/0/checksum")])
        self.assert_file_codes(COLLECTION, {"rights_information": "x", "security": {"a": 1}}, [])


class NoIoTest(unittest.TestCase):
    def test_checker_runs_with_sockets_and_open_blocked(self):
        value = {"files": [{"size": -1, "storage_location": {"connection_details": {"a": 1},
                                                             "security": {"b": 1}}}],
                 "rights_information": "r", "metadata_sets": [{"fields": [{"value": 1}]}]}
        document = doc(value)

        def refuse(*args, **kwargs):
            raise AssertionError("I/O attempted")

        with mock.patch("socket.socket", side_effect=refuse), mock.patch("builtins.open", side_effect=refuse):
            outcome = profiles.validate_profile(
                ASSET, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(len([d for d in outcome.diagnostics if d.code in FILE_CODES]), 6)

    def test_locator_looking_values_are_never_opened_or_fetched(self):
        file = valid_file(path="https://example.invalid/media.mov")
        file["uri"] = "file:///etc/passwd"
        value = {"asset_id": "a1", "title": "T", "type": "video", "files": [file]}
        assert_structurally_valid(self, ASSET, value)
        document = doc(value)

        def refuse(*args, **kwargs):
            raise AssertionError("I/O attempted")

        with mock.patch("socket.socket", side_effect=refuse) as sock, \
                mock.patch("builtins.open", side_effect=refuse) as opener:
            outcome = profiles.validate_profile(
                ASSET, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(codes(outcome), [("CHECKSUM_UNINTERPRETED", "/files/0/checksum")])
        self.assertEqual(outcome.execution_status, "complete")
        sock.assert_not_called()
        opener.assert_not_called()

    def test_document_is_not_mutated(self):
        value = {"files": [{"size": -1}], "rights_information": "r"}
        document = doc(value)
        before = json.dumps(document.value, default=str)
        profiles.validate_profile(ASSET, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(json.dumps(document.value, default=str), before)


class LegacyCollisionTest(unittest.TestCase):
    def test_custom_root_keys_colliding_with_typed_proposals_stay_opaque(self):
        """Legacy-collision case: custom root keys that match typed proposals are opaque."""
        value = {
            "asset_id": "asset-a",
            "title": "Synthetic interview",
            "type": "video",
            "source_system": {"schema_version": "9.9", "asset_id": "inner", "connection_details": {"a": 1}},
            "collections": [
                {"collection_id": "c1", "label": "L",
                 "assets": [{"asset_id": "inner-1"}, {"asset_id": "asset-a"}]},
            ],
            "extensions": {
                "schema_version": "unsupported", "connection_details": {"endpoint": "e"}, "checksum": "x",
                "asset_id": " ", "parent_collection_id": "asset-a",
            },
        }
        assert_structurally_valid(self, ASSET, value)
        before = json.dumps(doc(value).value, default=str)
        document = doc(value)
        outcome = profiles.validate_profile(
            ASSET, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(codes(outcome), [
            ("MEMBERSHIP_UNINTERPRETED", "/collections/0/assets/0"),
            ("MEMBERSHIP_UNINTERPRETED", "/collections/0/assets/1"),
        ])
        self.assertEqual(outcome.routing, "selected")
        self.assertEqual(outcome.execution_status, "complete")
        self.assertEqual(json.dumps(document.value, default=str), before)


class FileCorpusTest(unittest.TestCase):
    def test_corpus_file_diagnostics(self):
        checked, skipped = 0, []
        for case in CASES.values():
            if case.profile != "exchange-1x" or case.expected_valid is not True or case.expected_routing != "selected":
                continue
            try:
                document = parse_input((results.FIXTURES / case.path).read_bytes())
            except (NumericResourceRefused, InputInvalid):
                skipped.append(case.id)
                continue
            with self.subTest(case=case.id):
                outcome = profiles.exchange_checker(case, document, "valid")
                found = [pair for pair in codes(outcome) if pair[0] in FILE_CODES]
                expected = sorted(
                    ((d.code, d.path) for d in case.expected_diagnostics if d.code in FILE_CODES),
                    key=lambda pair: (pair[1], pair[0]),
                )
                self.assertEqual(found, expected)
                checked += 1
        self.assertEqual(sorted(skipped), ["exchange-numeric-resource-large-integer"])
        self.assertGreater(checked, 40)


TIMING_CODES = frozenset({"RATE_UNUSABLE", "RANGE_REVERSED", "TIMING_UNINTERPRETED"})


class TimingCase(unittest.TestCase):
    """Compare only this step's codes, in contract order."""

    def assert_timing(self, value, expected, name=ANNOTATION):
        outcome = check(name, value)
        found = [pair for pair in codes(outcome) if pair[0] in TIMING_CODES]
        self.assertEqual(found, sorted(expected, key=lambda pair: (pair[1], pair[0])))
        return outcome


def note(**timing):
    return {"source_id": "m1", **timing}


class TimingRuleRegistrationTest(unittest.TestCase):
    def test_timing_rule_is_registered_last(self):
        self.assertEqual(profiles.RULES[9:], [profiles.timing_rule])


class AnnotationTimingTest(TimingCase):
    def test_zero_rate_is_unusable_and_blocks(self):
        for lexeme in ("0", "0.0", "0e5", "-0"):
            with self.subTest(rate=lexeme):
                document = parse_input(
                    ('{"source_id": "m1", "start_seconds": 1, "end_seconds": 2, "frame_rate": %s}' % lexeme).encode())
                outcome = profiles.validate_profile(
                    ANNOTATION, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
                self.assertEqual(codes(outcome), [("RATE_UNUSABLE", "/frame_rate")])
                self.assertEqual(outcome.execution_status, "blocked")

    def test_positive_decimal_rate_is_retained_literally(self):
        document = parse_input(b'{"source_id": "m1", "start_frame": 1, "end_frame": 2, "frame_rate": 29.970}')
        outcome = profiles.validate_profile(
            ANNOTATION, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(codes(outcome), [])
        self.assertEqual(outcome.execution_status, "complete")
        rate = document.value["frame_rate"]
        self.assertIsInstance(rate, Decimal)
        self.assertEqual(str(rate), "29.970")

    def test_tiny_positive_rate_is_usable(self):
        document = parse_input(b'{"source_id": "m1", "start_frame": 1, "end_frame": 2, "frame_rate": 1e-400}')
        outcome = profiles.validate_profile(
            ANNOTATION, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(codes(outcome), [])

    def test_reversed_frames(self):
        outcome = self.assert_timing(note(start_frame=10, end_frame=9, frame_rate=24),
                                     [("RANGE_REVERSED", "/end_frame")])
        self.assertEqual(outcome.execution_status, "blocked")

    def test_reversed_seconds_compare_exactly(self):
        document = parse_input(
            b'{"source_id": "m1", "start_seconds": 1.00000000000000000001, "end_seconds": 1}')
        outcome = profiles.validate_profile(
            ANNOTATION, document, "exchange-1x", structural="valid", reference_context=EMPTY_CONTEXT)
        self.assertEqual(codes(outcome), [("RANGE_REVERSED", "/end_seconds")])

    def test_equal_and_forward_pairs_are_quiet(self):
        self.assert_timing(note(start_seconds=2, end_seconds=2), [])
        self.assert_timing(note(start_frame=2, end_frame=3, frame_rate=25), [])

    def test_reversed_pair_on_a_point_marker_is_reported(self):
        self.assert_timing(note(is_point_marker=True, start_seconds=5, end_seconds=4),
                           [("RANGE_REVERSED", "/end_seconds")])

    def test_mixed_units_are_uninterpreted_once(self):
        self.assert_timing(note(start_frame=1, end_seconds=2, frame_rate=24), [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_frame=1, end_frame=2, start_seconds=1, end_seconds=2, frame_rate=24),
                           [("TIMING_UNINTERPRETED", "")])

    def test_both_pairs_reversed_with_mixed_units(self):
        self.assert_timing(
            note(start_frame=9, end_frame=1, start_seconds=9, end_seconds=1, frame_rate=24),
            [("RANGE_REVERSED", "/end_frame"), ("RANGE_REVERSED", "/end_seconds"), ("TIMING_UNINTERPRETED", "")])

    def test_any_timecode_field_is_uninterpreted(self):
        self.assert_timing(note(start_timecode="00:00:01:00", end_timecode="00:00:02:00"),
                           [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_seconds=1, end_seconds=2, end_timecode="00:00:02:00"),
                           [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_timecode="00:00:01:00", frame_rate=25, is_point_marker=True),
                           [("TIMING_UNINTERPRETED", "")])

    def test_timecode_is_not_converted_or_compared(self):
        self.assert_timing(note(start_timecode="00:00:09:00", end_timecode="00:00:01:00"),
                           [("TIMING_UNINTERPRETED", "")])

    def test_rate_without_frames_is_not_a_frame_position(self):
        self.assert_timing(note(start_seconds=1, end_seconds=2, frame_rate=24), [])
        self.assert_timing(note(start_seconds=1, is_point_marker=True, frame_rate=24), [])

    def test_frames_without_positive_rate(self):
        self.assert_timing(note(start_frame=1, end_frame=2), [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_frame=1, is_point_marker=True), [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_frame=1, end_frame=2, frame_rate=0),
                           [("RATE_UNUSABLE", "/frame_rate"), ("TIMING_UNINTERPRETED", "")])

    def test_point_marker_with_frames_and_positive_rate_is_quiet(self):
        self.assert_timing(note(start_frame=1, is_point_marker=True, frame_rate=24), [])

    def test_point_without_start(self):
        # Only the embedded definition lets a structurally valid annotation omit every start.
        asset = {"temporal_annotations": [note(is_point_marker=True), note(is_point_marker=True, end_seconds=3)]}
        self.assert_timing(asset, [("TIMING_UNINTERPRETED", "/temporal_annotations/0"),
                                   ("TIMING_UNINTERPRETED", "/temporal_annotations/1")], name=ASSET)

    def test_incomplete_range(self):
        self.assert_timing(note(start_seconds=1), [("TIMING_UNINTERPRETED", "")])
        self.assert_timing(note(start_seconds=1, is_point_marker=False), [("TIMING_UNINTERPRETED", "")])
        asset = {"temporal_annotations": [note(end_seconds=1), note()]}
        self.assert_timing(asset, [("TIMING_UNINTERPRETED", "/temporal_annotations/0"),
                                   ("TIMING_UNINTERPRETED", "/temporal_annotations/1")], name=ASSET)

    def test_complete_range_and_point_with_start_are_quiet(self):
        self.assert_timing(note(start_seconds=1, end_seconds=2), [])
        self.assert_timing(note(start_seconds=1, is_point_marker=True), [])

    def test_at_most_one_warning_per_annotation(self):
        # Mixed units, timecode, no complete pair, and frames without a rate all hold.
        outcome = self.assert_timing(note(start_frame=1, end_seconds=2, start_timecode="00:00:01:00"),
                                     [("TIMING_UNINTERPRETED", "")])
        self.assertEqual(outcome.execution_status, "complete")

    def test_embedded_annotations_in_assets_and_batches(self):
        bad = note(start_frame=5, end_frame=4, frame_rate=0)
        self.assert_timing({"temporal_annotations": [note(start_seconds=0, end_seconds=1), bad]}, [
            ("RATE_UNUSABLE", "/temporal_annotations/1/frame_rate"),
            ("RANGE_REVERSED", "/temporal_annotations/1/end_frame"),
            ("TIMING_UNINTERPRETED", "/temporal_annotations/1"),
        ], name=ASSET)
        self.assert_timing({"assets": [{"temporal_annotations": [bad]}]}, [
            ("RATE_UNUSABLE", "/assets/0/temporal_annotations/0/frame_rate"),
            ("RANGE_REVERSED", "/assets/0/temporal_annotations/0/end_frame"),
            ("TIMING_UNINTERPRETED", "/assets/0/temporal_annotations/0"),
        ], name=ASSET_BATCH)

    def test_metadata_and_other_places_are_not_inspected(self):
        self.assert_timing(note(start_seconds=1, end_seconds=2,
                                metadata={"frame_rate": 0, "start_frame": 9, "end_frame": 1,
                                          "start_timecode": "00:00:01:00"}), [])
        self.assert_timing({"extensions": {"temporal_annotations": [note(frame_rate=0)]},
                            "frame_rate": 0, "start_frame": 2, "end_frame": 1}, [], name=ASSET)

    def test_messages_do_not_echo_values(self):
        outcome = check(ANNOTATION, note(start_frame=987654, end_frame=123456, frame_rate=0,
                                         start_timecode="11:22:33:44"))
        self.assertEqual(len(outcome.diagnostics), 3)
        for d in outcome.diagnostics:
            for text in ("987654", "123456", "11:22:33:44", "m1"):
                self.assertNotIn(text, d.message)

    def test_document_is_not_mutated(self):
        document = parse_input(b'{"source_id": "m1", "start_frame": 2, "end_frame": 1, "frame_rate": 0.0}')
        before = json.dumps(document.value, default=str)
        profiles.validate_profile(ANNOTATION, document, "exchange-1x", structural="valid",
                                  reference_context=EMPTY_CONTEXT)
        self.assertEqual(json.dumps(document.value, default=str), before)


class TimingCorpusTest(unittest.TestCase):
    def test_corpus_timing_diagnostics(self):
        checked, skipped = 0, []
        for case in CASES.values():
            if case.profile != "exchange-1x" or case.expected_valid is not True or case.expected_routing != "selected":
                continue
            try:
                document = parse_input((results.FIXTURES / case.path).read_bytes())
            except (NumericResourceRefused, InputInvalid):
                skipped.append(case.id)
                continue
            with self.subTest(case=case.id):
                outcome = profiles.exchange_checker(case, document, "valid")
                found = [pair for pair in codes(outcome) if pair[0] in TIMING_CODES]
                expected = sorted(
                    ((d.code, d.path) for d in case.expected_diagnostics if d.code in TIMING_CODES),
                    key=lambda pair: (pair[1], pair[0]),
                )
                self.assertEqual(found, expected)
                checked += 1
        self.assertEqual(sorted(skipped), ["exchange-numeric-resource-large-integer"])
        self.assertGreater(checked, 40)


class ExchangeCheckerTest(unittest.TestCase):
    def test_adapter_passes_case_fields(self):
        case = CASES["exchange-minimal-asset"]
        document = doc({})
        with mock.patch.object(profiles, "validate_profile", return_value="sentinel") as spy:
            self.assertEqual(profiles.exchange_checker(case, document, "invalid"), "sentinel")
        spy.assert_called_once_with(
            case.schema_name, document, case.profile, structural="invalid",
            reference_context=case.reference_context,
        )

    def test_default_checker_of_results_is_exchange_checker(self):
        import inspect
        default = inspect.signature(results.build_validate_result).parameters["checker"].default
        self.assertIs(default, profiles.exchange_checker)

    def test_profile_outcome_stays_importable_from_results(self):
        self.assertIs(results.ProfileOutcome, ProfileOutcome)

    def test_default_build_runs_exchange_profile(self):
        result = results.build_validate_result(
            CASES["exchange-v2-blocked"], format_mode="required", root="current", source_revision=REVISION,
        )
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual((result["routing"], result["structural"], result["execution_status"]),
                         ("unsupported", "valid", "unsupported"))
        self.assertEqual([(d["code"], d["path"]) for d in result["diagnostics"]],
                         [("VERSION_UNSUPPORTED", "/schema_version")])

    def _build_with_context(self, case_id, context):
        import dataclasses
        case = dataclasses.replace(CASES[case_id], reference_context=context)
        return results.build_validate_result(
            case, format_mode="required", root="current", source_revision=REVISION,
        )

    def test_malformed_context_outranks_invalid_input(self):
        result = self._build_with_context(
            "exchange-input-duplicate-members", {"asset_ids": [""], "collection_ids": []},
        )
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual((result["execution_status"], result["structural"], result["routing"]),
                         ("setup-failed", "not-run", "not-applied"))
        self.assertEqual(result["diagnostics"], [])
        self.assertTrue(result["reproduction"]["limitations"])

    def test_malformed_context_with_valid_input_is_setup_failed(self):
        result = self._build_with_context(
            "exchange-v2-blocked", {"asset_ids": [""], "collection_ids": []},
        )
        self.assertEqual(results.result_problems(result), [])
        self.assertEqual((result["execution_status"], result["structural"]), ("setup-failed", "not-run"))
        self.assertEqual(result["diagnostics"], [])
        self.assertTrue(result["reproduction"]["limitations"])

    def test_default_build_never_calls_profile_checks_for_legacy(self):
        with mock.patch.object(profiles, "validate_profile", side_effect=AssertionError("called")):
            result = results.build_validate_result(
                CASES["minimal-asset"], format_mode="required", root="current", source_revision=REVISION,
            )
        self.assertEqual((result["routing"], result["execution_status"]), ("not-applied", "complete"))

    def test_cli_uses_the_exchange_checker(self):
        done = subprocess.run(
            [sys.executable, "-m", "tests.conformance.results", "--fixture", "exchange-report-excluded",
             "--format-mode", "required", "--root", "current"],
            cwd=REPO, capture_output=True, check=True,
        )
        result = json.loads(done.stdout)
        self.assertEqual((result["routing"], result["execution_status"]), ("unsupported", "unsupported"))
        self.assertEqual([(d["code"], d["path"]) for d in result["diagnostics"]], [("PROFILE_UNSUPPORTED", "")])


def engine_override(case):
    """The outcome a Python engine limitation forces, or None when the engine is complete.

    CONTRACT.md: adapter status setup-failed or input-invalid overrides the
    fully capable case outcome for that engine.
    """
    adapter_status = case.validator_expectations["python-jsonschema"]["adapter_status"]
    if adapter_status == "setup-failed":
        return "not-applied", "setup-failed", []
    if adapter_status == "input-invalid":
        return "not-applied", "input-invalid", [("INPUT_INVALID", "")]
    return None


def expected_exchange_outcome(case):
    """Routing, execution status, and sorted unique code/path pairs from the manifest."""
    pairs = {(d.code, d.path) for d in case.expected_diagnostics}
    manifest = case.expected_routing, case.expected_execution_status, sorted(pairs, key=lambda p: (p[1], p[0]))
    return engine_override(case) or manifest


def expected_legacy_outcome(case):
    """legacy-1x never runs semantic checks, so it is unchanged by the exchange profile."""
    return engine_override(case) or ("not-applied", "complete", [])


def sweep(profile, expected_outcome, checker=profiles.exchange_checker):
    """Build a required-mode result for every case of a profile at every root.

    Returns the number of checked results and one mismatch line per failing
    fixture and root.
    """
    built, mismatches = 0, []
    for case in CASES.values():
        if case.profile != profile:
            continue
        for root in sorted(results.ROOTS):
            where = f"{case.id} @ {root}"
            try:
                result = results.build_validate_result(
                    case, format_mode="required", root=root, source_revision=REVISION, checker=checker,
                )
                results.check_result(result)
            except (SetupFailed, results.ResultInvalid) as error:
                mismatches.append(f"{where}: no checked result ({type(error).__name__})")
                continue
            built += 1
            for diagnostic in result["diagnostics"]:
                if diagnostic["severity"] != corpus.DIAGNOSTIC_SEVERITY[diagnostic["code"]]:
                    mismatches.append(f"{where}: {diagnostic['code']} severity is not the catalog severity")
            actual = (result["routing"], result["execution_status"],
                      [(d["code"], d["path"]) for d in result["diagnostics"]])
            expected = expected_outcome(case)
            if actual != expected:
                mismatches.append(f"{where}: expected {expected}, got {actual}")
    return built, mismatches


class CorpusSweepTest(unittest.TestCase):
    def test_every_exchange_case_matches_its_expectations_at_both_roots(self):
        built, mismatches = sweep("exchange-1x", expected_exchange_outcome)
        self.assertEqual(mismatches, [], "\n".join(mismatches))
        count = sum(case.profile == "exchange-1x" for case in CASES.values())
        self.assertGreater(count, 70)
        self.assertEqual(built, count * len(results.ROOTS))

    def test_every_legacy_case_is_unchanged_at_both_roots(self):
        built, mismatches = sweep("legacy-1x", expected_legacy_outcome)
        self.assertEqual(mismatches, [], "\n".join(mismatches))
        count = sum(case.profile == "legacy-1x" for case in CASES.values())
        self.assertGreater(count, 60)
        self.assertEqual(built, count * len(results.ROOTS))

    def test_engine_overrides_replace_the_case_outcome(self):
        refused = CASES["exchange-numeric-resource-large-integer"]
        self.assertEqual(expected_exchange_outcome(refused), ("not-applied", "setup-failed", []))
        raw = [case for case in CASES.values() if case.profile == "exchange-1x"
               and case.validator_expectations["python-jsonschema"]["adapter_status"] == "input-invalid"]
        self.assertEqual(len(raw), 3)
        for case in raw:
            self.assertEqual(expected_exchange_outcome(case), ("not-applied", "input-invalid", [("INPUT_INVALID", "")]))

    def test_sweep_reports_every_mismatch_by_fixture_and_root(self):
        def quiet(case, document, structural):
            return ProfileOutcome("selected", "complete", ())

        _, mismatches = sweep("exchange-1x", expected_exchange_outcome, checker=quiet)
        report = "\n".join(mismatches)
        self.assertIn("exchange-v2-blocked @ baseline: expected", report)
        self.assertIn("exchange-v2-blocked @ current: expected", report)
        self.assertNotIn("exchange-numeric-resource-large-integer", report)

    def test_sweep_reports_a_severity_that_is_not_the_catalog_severity(self):
        case = CASES["exchange-minimal-asset"]

        def wrong_severity(case, document, structural):
            return ProfileOutcome("selected", "complete", (
                Diagnostic("COMPLETENESS_UNVERIFIED", "", "error", "Completeness is not established."),))

        with mock.patch.dict(CASES, {case.id: case}, clear=True):
            _, mismatches = sweep("exchange-1x", expected_exchange_outcome, checker=wrong_severity)
        self.assertEqual(len(mismatches), len(results.ROOTS))
        self.assertTrue(all("no checked result (ResultInvalid)" in line for line in mismatches))


if __name__ == "__main__":
    unittest.main()
