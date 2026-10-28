# tests/conformance/test_ecma_regex.py
import re
import unittest

from tests.conformance import ecma_regex
from tests.conformance.ecma_regex import RegexResourceLimit, RegexSyntaxError, Untranslatable

VALID = [
    r"^[a-z][a-z0-9_]{0,62}$", r"\S", r"^\S([\s\S]*\S)?$", r"^(?!0000)[0-9]{4}-(0[1-9]|1[0-2])$",
    r"a|b", r"(a)(b)\2", r"(?<x>a)\k<x>", r"(?<=a)b", r"[\d-]", r"A", r"\x41", r"\cJ", r"a{2,3}?",
    r"[]", r"[^]", r"\/", r"\.", r"(?:a)", r"$^", r"a\b", r"[+-]", r"[a-z-]", r"\-", r"[\-]", r"\ ",
    r"^[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}/[A-Za-z0-9][A-Za-z0-9!#$&^_.+-]{0,126}$", r"^[A-Za-z][A-Za-z0-9+.-]*:",
]
INVALID = [
    r"(?P<n>a)", r"\A", r"\Z", r"(?i)a", r"a*+", r"\p{L}", r"a{", r"{1}", r"a{3,1}", r"(a", r"a)",
    r"[b-a]", r"\1", r"(a)\2", r"(?<x>a)(?<x>b)", r"*a", r"^*", r"\q", r"a{,1}", r"[a-\d]",
    "a(?#x)", r"\8",
]
UNTRANSLATABLE = [r"(a)\1", r"(?<x>a)", r"(?<=a)b", r"(?<!a)b"]


class ValidityTest(unittest.TestCase):
    def test_valid_patterns(self):
        for source in VALID:
            with self.subTest(source=source):
                self.assertTrue(ecma_regex.is_valid(source))

    def test_deep_nesting_is_resource_limit(self):
        # Valid syntax nested beyond the parser limit is neither valid nor invalid.
        source = "(" * 3000 + ")" * 3000
        with self.assertRaises(RegexResourceLimit):
            ecma_regex.is_valid(source)
        with self.assertRaises(RegexResourceLimit):
            ecma_regex.to_python(source)

    def test_invalid_patterns(self):
        for source in INVALID:
            with self.subTest(source=source):
                self.assertFalse(ecma_regex.is_valid(source))
                with self.assertRaises(RegexSyntaxError):
                    ecma_regex.to_python(source)


class IdentifierTest(unittest.TestCase):
    """IdentityEscape and RegExpIdentifierName follow ECMA ID_Start and ID_Continue."""

    def test_identity_escape_of_id_continue_is_invalid(self):
        # U+309B is ID_Continue but not XID_Continue; U+00B7 is Other_ID_Continue.
        # U+200C and U+200D are ID_Continue too.
        for source in ("\\\u309b", "\\\u00b7", "\\\uff9e", "\\\u0e33", "\\\u200c", "\\\u200d"):
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), False)

    def test_unicode_15_1_additions(self):
        # Python 3.12 carries Unicode 15.0; the grammar uses Unicode 15.1, which
        # added U+30FB and U+FF65 to Other_ID_Continue and U+2EBF0 to U+2EE5D to ID_Start.
        self.assertEqual(ecma_regex.UNICODE_VERSION, "15.1")
        cases = {
            "\\\u30fb": False,
            "\\\uff65": False,
            "(?<a\u30fbb>x)": True,
            "(?<a\uff65b>x)": True,
            r"(?<a\u30fbb>x)": True,
            r"(?<\u{2EBF0}>x)": True,
            r"(?<a\u{2EE5D}>x)": True,
            r"(?<\ud87a\udff0>x)": True,
            "(?<\U0002EBF0>x)": True,
            r"(?<\u{2EE5E}>x)": False,
            r"(?<\u{2EBEF}>x)": False,
        }
        for source, valid in cases.items():
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), valid)

    def test_identity_escape_of_non_identifier_is_valid(self):
        for source in ("\\\u00a1", "\\\u2014"):
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), True)

    def test_group_names(self):
        cases = {
            r"(?<a\u200cb>x)": True,
            "(?<a\u200cb>x)": True,
            "(?<a\u200db>x)": True,
            r"(?<\u{61}>x)": True,
            r"(?<\u0061>x)": True,
            r"(?<\ud835\udc9c>x)": True,
            r"(?<$a_1>x)": True,
            "(?<\U0001D49C>x)": True,
            r"(?<1a>x)": False,
            "(?<\u200ca>x)": False,
            r"(?<a\u{110000}>x)": False,
            r"(?<\ud835>x)": False,
            r"(?<>x)": False,
            r"(?<a\x41>x)": False,
            r"(?<a\u{61}b>x)\k<aab>": True,
        }
        for source, valid in cases.items():
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), valid)


class CodeUnitTest(unittest.TestCase):
    """Without the u flag, ECMA-262 reads the source as UTF-16 code units."""

    def test_astral_ranges_are_judged_per_code_unit(self):
        for source in ("[\U0001F4A9-\U0001F600]", "[^\U0001F4A9-\U0001F600]", "[\U0001F600-\U0001F4A9]"):
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), False)

    def test_surrogate_range_is_valid(self):
        self.assertIs(ecma_regex.is_valid(r"[\uD83D-\uDBFF]"), True)

    def test_astral_literal_is_valid_but_untranslatable(self):
        for source in ("[\U0001F600]", "\U0001F600"):
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), True)
                with self.assertRaises(Untranslatable):
                    ecma_regex.to_python(source)


class QuantifierBoundTest(unittest.TestCase):
    """Bounds of any length compare without integer conversion limits."""

    def test_huge_bound_is_valid_but_untranslatable(self):
        source = "a{" + "9" * 5000 + "}"
        self.assertIs(ecma_regex.is_valid(source), True)
        with self.assertRaises(Untranslatable):
            ecma_regex.to_python(source)

    def test_huge_bounds_out_of_order_are_invalid(self):
        self.assertIs(ecma_regex.is_valid("a{" + "9" * 5000 + "," + "9" * 4999 + "}"), False)

    def test_huge_bounds_in_order_are_valid(self):
        self.assertIs(ecma_regex.is_valid("a{" + "9" * 4999 + "," + "1" + "0" * 4999 + "}"), True)

    def test_bound_order_ignores_leading_zeros(self):
        cases = {"a{10,9}": False, "a{0010,9}": False, "a{9,0010}": True, "a{0010,10}": True}
        for source, valid in cases.items():
            with self.subTest(source=source):
                self.assertIs(ecma_regex.is_valid(source), valid)

    def test_huge_backreference_is_invalid(self):
        self.assertIs(ecma_regex.is_valid("(a)\\" + "9" * 5000), False)

    def test_leading_zero_bound_translates(self):
        compiled = re.compile(ecma_regex.to_python("^a{0002,03}$"))
        self.assertIsNotNone(compiled.search("aaa"))
        self.assertIsNone(compiled.search("a"))

class TranslationTest(unittest.TestCase):
    def test_digit_class_is_ascii(self):
        compiled = re.compile(ecma_regex.to_python(r"^\d$"))
        self.assertIsNotNone(compiled.search("7"))
        self.assertIsNone(compiled.search("٣"))

    def test_end_anchor_is_absolute(self):
        compiled = re.compile(ecma_regex.to_python(r"^ab$"))
        self.assertIsNone(compiled.search("ab\n"))

    def test_whitespace_class_matches_ecma_set_only(self):
        compiled = re.compile(ecma_regex.to_python(r"^\s$"))
        self.assertIsNotNone(compiled.search("﻿"))
        self.assertIsNone(compiled.search("\x1c"))

    def test_dot_excludes_line_terminators(self):
        compiled = re.compile(ecma_regex.to_python(r"^.$"))
        self.assertIsNone(compiled.search(" "))
        self.assertIsNotNone(compiled.search("x"))

    def test_untranslatable_constructs(self):
        for source in UNTRANSLATABLE:
            with self.subTest(source=source):
                self.assertTrue(ecma_regex.is_valid(source))
                with self.assertRaises(Untranslatable):
                    ecma_regex.to_python(source)

    def test_surrogate_and_astral_are_untranslatable(self):
        for source in ("^\U0001F600$", r"[\uD83D]", "a\U00010000b"):
            with self.subTest(source=source):
                self.assertTrue(ecma_regex.is_valid(source))
                with self.assertRaises(Untranslatable):
                    ecma_regex.to_python(source)

    def test_every_bundle_pattern_translates_and_compiles(self):
        import json
        from pathlib import Path
        root = Path(__file__).resolve().parents[2] / "definitions"
        found = []

        def walk(node):
            if isinstance(node, dict):
                if isinstance(node.get("pattern"), str):
                    found.append(node["pattern"])
                for value in node.values():
                    walk(value)
            elif isinstance(node, list):
                for item in node:
                    walk(item)

        for path in root.glob("*.schema.json"):
            walk(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(len(set(found)), 18)
        for source in set(found):
            with self.subTest(source=source[:40]):
                re.compile(ecma_regex.to_python(source))
