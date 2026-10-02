"""Tests for the preservation tree comparator."""

import unittest

from tests.conformance import corpus, results
from tests.conformance.preservation import compare_trees
from tests.conformance.strict_json import parse_input

CASES = {case.id: case for case in corpus.fixture_cases()}


def tree(text):
    return parse_input(text.encode("utf-8")).value


def compare(source, output):
    return compare_trees(tree(source), tree(output))


class ManifestComparisonTest(unittest.TestCase):
    def test_every_manifest_comparison(self):
        comparisons = corpus.preservation_comparisons()
        self.assertEqual(len(comparisons), 6)
        for comparison in comparisons:
            with self.subTest(comparison=comparison.id):
                source = parse_input((results.FIXTURES / CASES[comparison.source_case_id].path).read_bytes())
                output = parse_input((results.FIXTURES / CASES[comparison.output_case_id].path).read_bytes())
                self.assertEqual(
                    compare_trees(source.value, output.value),
                    (comparison.expected_status, list(comparison.paths)),
                )


class EqualityTest(unittest.TestCase):
    def test_equal_trees_are_preserved_with_no_paths(self):
        self.assertEqual(compare('{"a": [1, {"b": null}], "c": "x"}', '{"c": "x", "a": [1, {"b": null}]}'),
                         ("preserved", []))

    def test_scalar_roots(self):
        self.assertEqual(compare("null", "null"), ("preserved", []))
        self.assertEqual(compare("1", "2"), ("changed", [""]))
        self.assertEqual(compare('"a"', "null"), ("changed", [""]))

    def test_equal_numbers_compare_equal_across_representations(self):
        for left, right in (("25", "25.0"), ("25", "2.5e1"), ("25.0", "2.5E+1"), ("0", "-0.0"),
                            ("1.10", "1.1"), ("100000000000000000001", "1.00000000000000000001e20")):
            with self.subTest(left=left, right=right):
                self.assertEqual(compare(f'{{"n": {left}}}', f'{{"n": {right}}}'), ("preserved", []))

    def test_unequal_numbers_are_changed_without_float_rounding(self):
        self.assertEqual(compare('{"n": 9007199254740993}', '{"n": 9007199254740992}'), ("changed", ["/n"]))
        self.assertEqual(compare('{"n": 0.1}', '{"n": 0.10000000000000001}'), ("changed", ["/n"]))

    def test_booleans_are_never_equal_to_numbers(self):
        for number, boolean in (("1", "true"), ("0", "false"), ("1.0", "true"), ("0e0", "false")):
            with self.subTest(number=number, boolean=boolean):
                self.assertEqual(compare(f'{{"v": {number}}}', f'{{"v": {boolean}}}'), ("changed", ["/v"]))
                self.assertEqual(compare(f'{{"v": {boolean}}}', f'{{"v": {number}}}'), ("changed", ["/v"]))
        self.assertEqual(compare('{"v": true}', '{"v": false}'), ("changed", ["/v"]))

    def test_null_is_distinct_from_absent_and_from_empty(self):
        self.assertEqual(compare('{"v": null}', '{}'), ("changed", ["/v"]))
        self.assertEqual(compare('{}', '{"v": null}'), ("changed", ["/v"]))
        for empty in ('""', "[]", "{}", "0", "false"):
            with self.subTest(empty=empty):
                self.assertEqual(compare('{"v": null}', f'{{"v": {empty}}}'), ("changed", ["/v"]))

    def test_strings_are_compared_exactly(self):
        # Composed and decomposed e-acute, trailing space, case, and a date rewrite.
        for left, right in (('"\\u00e9"', '"e\\u0301"'), ('"a"', '"a "'), ('"A"', '"a"'),
                            ('"2024-01-01T00:00:00Z"', '"2024-01-01T00:00:00+00:00"')):
            with self.subTest(left=left, right=right):
                self.assertEqual(compare(f'{{"s": {left}}}', f'{{"s": {right}}}'), ("changed", ["/s"]))

    def test_type_differences_are_reported_at_the_value(self):
        self.assertEqual(compare('{"v": {"a": 1}}', '{"v": [1]}'), ("changed", ["/v"]))
        self.assertEqual(compare('{"v": "1"}', '{"v": 1}'), ("changed", ["/v"]))
        self.assertEqual(compare('{"v": []}', '{"v": {}}'), ("changed", ["/v"]))


class ObjectTest(unittest.TestCase):
    def test_key_order_is_ignored(self):
        self.assertEqual(compare('{"a": 1, "b": 2}', '{"b": 2, "a": 1}'), ("preserved", []))

    def test_missing_and_added_members_are_reported_at_the_member_path(self):
        self.assertEqual(compare('{"a": 1, "b": {"c": 2}}', '{"a": 1, "b": {"d": 2}}'),
                         ("changed", ["/b/c", "/b/d"]))

    def test_whole_missing_subtree_is_one_path(self):
        self.assertEqual(compare('{"a": {"b": {"c": 1}}}', '{}'), ("changed", ["/a"]))

    def test_keys_with_slash_and_tilde_are_escaped(self):
        self.assertEqual(compare('{"a/b": 1, "m~n": 2, "~/": 3}', '{"a/b": 0, "m~n": 0, "~/": 0}'),
                         ("changed", ["/a~1b", "/m~0n", "/~0~1"]))

    def test_empty_key_is_a_member(self):
        self.assertEqual(compare('{"": 1}', '{"": 2}'), ("changed", ["/"]))


class ArrayTest(unittest.TestCase):
    def test_array_order_is_significant(self):
        self.assertEqual(compare('{"a": [1, 2]}', '{"a": [2, 1]}'), ("changed", ["/a/0", "/a/1"]))

    def test_length_difference_reports_the_array_and_compares_the_shared_prefix(self):
        self.assertEqual(compare('{"a": [1, 2, 3, 4]}', '{"a": [1, 9]}'), ("changed", ["/a", "/a/1"]))
        self.assertEqual(compare('{"a": [1]}', '{"a": [1, 2, 3]}'), ("changed", ["/a"]))
        self.assertEqual(compare('{"a": []}', '{"a": [1]}'), ("changed", ["/a"]))

    def test_nested_arrays(self):
        self.assertEqual(compare('[[1, [2, 3]], [4]]', '[[1, [2, 3, 5]], [4.0]]'), ("changed", ["/0/1"]))
        self.assertEqual(compare('[[1, [2, 3]], [4]]', '[[1, [2, true]], [4, 5]]'), ("changed", ["/0/1/1", "/1"]))

    def test_paths_sort_lexically_and_are_unique(self):
        source = "[" + ", ".join(str(n) for n in range(12)) + "]"
        output = "[" + ", ".join("0" if n in (2, 10) else str(n) for n in range(12)) + "]"
        self.assertEqual(compare(source, output), ("changed", ["/10", "/2"]))

    def test_sorting_uses_the_escaped_form(self):
        # "~1" sorts after "0" by scalar value, matching the manifest example.
        self.assertEqual(compare('{"a/b": 1, "a0": 1}', '{}'), ("changed", ["/a0", "/a~1b"]))


class PurityTest(unittest.TestCase):
    def test_deep_trees_do_not_exhaust_the_stack(self):
        source, output = [], []
        for _ in range(5000):
            source, output = [source], [output]
        self.assertEqual(compare_trees(source, output), ("preserved", []))

    def test_inputs_are_not_mutated(self):
        source, output = tree('{"a": [1, {"b": 2.50}]}'), tree('{"a": [1, {"b": 3}], "c": null}')
        before = (repr(source), repr(output))
        compare_trees(source, output)
        self.assertEqual((repr(source), repr(output)), before)


if __name__ == "__main__":
    unittest.main()
