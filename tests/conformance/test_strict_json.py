"""Strict input parser tests: parse policy, exact numbers, and numeric guards."""

import builtins
import dataclasses
import hashlib
import json
import unittest
from decimal import Decimal
from unittest import mock

from tests.conformance import strict_json
from tests.conformance.strict_json import parse_input, parse_schema_bytes
from tests.conformance.types import (
    Diagnostic,
    ExpectedDiagnostic,
    FixtureCase,
    InputInvalid,
    NumericResourceRefused,
    ParsedInput,
    SetupFailed,
)


class ParsePolicyTests(unittest.TestCase):
    def assert_invalid(self, data):
        with self.assertRaises(InputInvalid):
            parse_input(data)

    def test_duplicate_member_names_rejected(self):
        self.assert_invalid(b'{"a": 1, "a": 2}')

    def test_duplicate_after_escape_decoding_rejected(self):
        self.assert_invalid(b'{"a": 1, "\\u0061": 2}')

    def test_nested_duplicate_rejected(self):
        self.assert_invalid(b'{"x": [{"b": true, "b": false}]}')

    def test_byte_order_mark_rejected(self):
        self.assert_invalid(b'\xef\xbb\xbf{"a": 1}')

    def test_invalid_utf8_rejected(self):
        self.assert_invalid(b'{"a": "\xff"}')

    def test_encoded_surrogate_bytes_rejected(self):
        # CESU-style encoding of U+D800 is not valid UTF-8.
        self.assert_invalid(b'{"a": "\xed\xa0\x80"}')

    def test_nonfinite_constants_rejected(self):
        for token in (b"NaN", b"Infinity", b"-Infinity"):
            with self.subTest(token=token):
                self.assert_invalid(b'{"a": ' + token + b"}")

    def test_malformed_json_rejected(self):
        for data in (b"", b"{", b'{"a": 1,}', b"[1 2]", b'{"a": 01}'):
            with self.subTest(data=data):
                self.assert_invalid(data)

    def test_unpaired_surrogate_in_key_rejected(self):
        self.assert_invalid(b'{"\\ud800": 1}')

    def test_unpaired_surrogate_in_value_rejected(self):
        self.assert_invalid(b'{"a": ["ok", "\\udc00"]}')

    def test_reversed_surrogate_pair_rejected(self):
        self.assert_invalid(b'"\\ude00\\ud83d"')

    def test_valid_surrogate_pair_accepted(self):
        parsed = parse_input(b'{"\\ud83d\\ude00": "\\ud83d\\ude00"}')
        self.assertEqual(parsed.value, {"\U0001F600": "\U0001F600"})

    def test_message_does_not_echo_input(self):
        secret = "SECRETVALUE123"
        with self.assertRaises(InputInvalid) as caught:
            parse_input(('{"%s": 1, "%s": 2}' % (secret, secret)).encode())
        self.assertNotIn(secret, str(caught.exception))

    def test_schema_bytes_use_same_policy(self):
        with self.assertRaises(InputInvalid):
            parse_schema_bytes(b'{"type": "object", "type": "array"}')
        with self.assertRaises(NumericResourceRefused):
            parse_schema_bytes(b'{"maximum": 1e10001}')


class NumericGuardTests(unittest.TestCase):
    def test_five_thousand_digit_integer_refused(self):
        with self.assertRaises(NumericResourceRefused):
            parse_input(b"[" + b"9" * 5000 + b"]")

    def test_refusal_is_setup_failure_not_input_invalid(self):
        with self.assertRaises(SetupFailed) as caught:
            parse_input(b"9" * 5000)
        self.assertNotIsInstance(caught.exception, InputInvalid)

    def test_malformed_input_with_huge_number_is_input_invalid(self):
        for data in (
            b"[" + b"9" * 5000 + b",]",
            b'{"a": ' + b"9" * 5000 + b', "a": 1}',
            b'["\\ud800", ' + b"9" * 5000 + b"]",
            b'["\\ud800", 1e99999999999999999999]',
        ):
            with self.subTest(size=len(data)):
                with self.assertRaises(InputInvalid):
                    parse_input(data)

    def test_token_length_boundary(self):
        accepted = b"1" * 1024
        parsed = parse_input(accepted)
        self.assertEqual(parsed.value, int(accepted))
        refused = b"1" * 1025
        with self.assertRaises(NumericResourceRefused) as caught:
            parse_input(refused)
        self.assertIn("1024", str(caught.exception))

    def test_token_length_counts_sign_and_exponent_syntax(self):
        # 1,020 digits plus "-", "e", "+", "0" is 1,024 bytes.
        accepted = b"-" + b"1" * 1020 + b"e+0"
        self.assertEqual(len(accepted), 1024)
        self.assertEqual(parse_input(accepted).value, Decimal(accepted.decode()))
        refused = b"-" + b"1" * 1021 + b"e+0"
        with self.assertRaises(NumericResourceRefused):
            parse_input(refused)

    def test_exponent_boundary(self):
        self.assertEqual(parse_input(b"1e10000").value, Decimal("1e10000"))
        self.assertEqual(parse_input(b"1e-10000").value, Decimal("1e-10000"))
        for data in (b"1e10001", b"1E-10001", b"1e+10001"):
            with self.subTest(data=data):
                with self.assertRaises(NumericResourceRefused) as caught:
                    parse_input(data)
                self.assertIn("10000", str(caught.exception))

    def test_exponent_leading_zeros_ignored_for_digit_count(self):
        self.assertEqual(parse_input(b"1e0000010000").value, Decimal("1e10000"))

    def test_twenty_digit_exponent_refused_without_building_integer(self):
        exponent = "9" * 20
        calls = []
        real_int = builtins.int

        def recording_int(*args, **kwargs):
            calls.append(args)
            return real_int(*args, **kwargs)

        with mock.patch.object(strict_json, "int", recording_int, create=True):
            with self.assertRaises(NumericResourceRefused) as caught:
                parse_input(("1e" + exponent).encode())
        self.assertFalse(
            any(exponent in str(a) for args in calls for a in args),
            "exponent text was converted to an integer",
        )
        self.assertNotIn(exponent, str(caught.exception))

    def test_cumulative_budget_boundary(self):
        # "1e9999" charges 1 coefficient digit plus 9,999 = 10,000 units.
        ten = b"[" + b",".join([b"1e9999"] * 10) + b"]"
        self.assertEqual(len(parse_input(ten).value), 10)
        with self.assertRaises(NumericResourceRefused) as caught:
            parse_input(b"[" + b",".join([b"1e9999"] * 10) + b",0]")
        self.assertIn("100000", str(caught.exception))

    def test_budget_counts_fraction_and_leading_zero_digits(self):
        # "0.5e9997" charges 2 + 9,997 = 9,999; ten of them is 99,990.
        # Plus "0.00000000" (9 digits) is 99,999; plus "10" is 100,001.
        tokens = [b"0.5e9997"] * 10 + [b"0.00000000"]
        parse_input(b"[" + b",".join(tokens) + b"]")
        with self.assertRaises(NumericResourceRefused):
            parse_input(b"[" + b",".join(tokens + [b"10"]) + b"]")

    def test_budget_counts_object_member_values(self):
        members = b",".join(b'"k%d": 1e9999' % i for i in range(10))
        parse_input(b"{" + members + b"}")
        with self.assertRaises(NumericResourceRefused):
            parse_input(b"{" + members + b', "z": 1}')

    def test_int_digit_limit_setup_check(self):
        for limit in (0, 1024, 4300):
            with mock.patch.object(strict_json.sys, "get_int_max_str_digits", return_value=limit):
                strict_json.check_int_digit_limit()
        with mock.patch.object(strict_json.sys, "get_int_max_str_digits", return_value=640):
            with self.assertRaises(SetupFailed):
                strict_json.check_int_digit_limit()


class NestingLimitTests(unittest.TestCase):
    SECRET = "SECRETVALUE123"

    def nested(self, depth):
        return ("[" * depth + '"%s"' % self.SECRET + "]" * depth).encode()

    def assert_nesting_refused(self, parse, data):
        with self.assertRaises(SetupFailed) as caught:
            parse(data)
        self.assertIs(type(caught.exception), SetupFailed)
        self.assertEqual(str(caught.exception), strict_json.NESTING_LIMIT_MESSAGE)
        self.assertIn("interpreter recursion limit", str(caught.exception))
        self.assertNotIn(self.SECRET, str(caught.exception))

    def test_deep_nesting_refused_by_json_loads_is_setup_failure(self):
        data = self.nested(100000)
        with self.assertRaises(RecursionError):
            json.loads(data)
        for parse in (parse_input, parse_schema_bytes):
            with self.subTest(parse=parse.__name__):
                self.assert_nesting_refused(parse, data)

    def test_open_brackets_only_is_setup_failure(self):
        self.assert_nesting_refused(parse_input, b"[" * 100000)

    def test_nesting_json_loads_accepts_is_setup_failure(self):
        # json.loads accepts this depth; the later tree walks would recurse too deep.
        data = self.nested(1200)
        json.loads(data)
        for parse in (parse_input, parse_schema_bytes):
            with self.subTest(parse=parse.__name__):
                self.assert_nesting_refused(parse, data)

    def test_moderate_nesting_is_accepted(self):
        value = parse_input(self.nested(100)).value
        for _ in range(100):
            value = value[0]
        self.assertEqual(value, self.SECRET)


class ExactNumberTests(unittest.TestCase):
    def test_media_rates_are_exact_decimals(self):
        parsed = parse_input(b"[23.976, 29.97, 59.94]")
        self.assertEqual(parsed.value, [Decimal("23.976"), Decimal("29.97"), Decimal("59.94")])
        for number in parsed.value:
            self.assertIsInstance(number, Decimal)
        self.assertNotEqual(parsed.value[0], Decimal(23.976))

    def test_one_point_zero_is_integral_decimal(self):
        value = parse_input(b"1.0").value
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, 1)
        self.assertEqual(value, value.to_integral_value())

    def test_neighboring_large_integers_distinct(self):
        parsed = parse_input(b"[9007199254740993, 9007199254740992]")
        self.assertEqual(parsed.value, [9007199254740993, 9007199254740992])
        self.assertIs(type(parsed.value[0]), int)
        self.assertNotEqual(parsed.value[0], parsed.value[1])

    def test_integer_lexemes_become_int(self):
        parsed = parse_input(b'{"a": -0, "b": 42, "c": true, "d": null}')
        self.assertEqual(parsed.value, {"a": 0, "b": 42, "c": True, "d": None})
        self.assertIs(type(parsed.value["b"]), int)

    def test_exponent_without_fraction_is_decimal(self):
        value = parse_input(b"25e-1").value
        self.assertIsInstance(value, Decimal)
        self.assertEqual(value, Decimal("2.5"))

    def test_no_tagged_lexeme_left_in_tree(self):
        value = parse_input(b'{"a": [1, 2.5, {"b": 3e2}], "c": "1"}').value
        self.assertEqual(value, {"a": [1, Decimal("2.5"), {"b": Decimal("3e2")}], "c": "1"})
        self.assertIs(type(value["c"]), str)

    def test_schema_bytes_return_plain_tree(self):
        tree = parse_schema_bytes(b'{"multipleOf": 0.01, "maximum": 9007199254740993}')
        self.assertNotIsInstance(tree, ParsedInput)
        self.assertEqual(tree, {"multipleOf": Decimal("0.01"), "maximum": 9007199254740993})


class ParsedInputTests(unittest.TestCase):
    def test_digest_is_sha256_of_input_bytes(self):
        data = b'{ "a" : 1.50 }\n'
        self.assertEqual(parse_input(data).sha256, hashlib.sha256(data).hexdigest())

    def test_direct_construction_refused(self):
        with self.assertRaises(TypeError):
            ParsedInput({"a": 1}, "0" * 64)
        with self.assertRaises(TypeError):
            ParsedInput(value={"a": 1}, sha256="0" * 64)

    def test_parsed_input_is_frozen(self):
        parsed = parse_input(b"{}")
        with self.assertRaises(dataclasses.FrozenInstanceError):
            parsed.sha256 = "0" * 64


class SharedTypesTests(unittest.TestCase):
    def test_fixture_case_fields(self):
        names = [f.name for f in dataclasses.fields(FixtureCase)]
        self.assertEqual(
            names,
            [
                "id",
                "schema_name",
                "path",
                "expected_valid",
                "profile",
                "context",
                "validator_expectations",
                "expected_diagnostics",
                "expected_execution_status",
                "expected_routing",
                "input_kind",
                "reference_context",
                "provenance",
                "exclusions",
            ],
        )

    def test_expected_diagnostics_default_empty(self):
        case = FixtureCase(
            id="c",
            schema_name="asset",
            path="p.json",
            expected_valid=None,
            profile="legacy",
            context="standalone",
            validator_expectations={},
            expected_execution_status="completed",
            expected_routing="structural",
            input_kind="record",
            reference_context=None,
            provenance=None,
            exclusions=(),
        )
        self.assertEqual(case.expected_diagnostics, ())

    def test_diagnostic_types(self):
        expected = ExpectedDiagnostic(code="X", path="/a")
        self.assertEqual((expected.code, expected.path), ("X", "/a"))
        diagnostic = Diagnostic(code="X", path="/a", severity="error", message="m")
        self.assertEqual(diagnostic.severity, "error")
        for instance in (expected, diagnostic):
            with self.assertRaises(dataclasses.FrozenInstanceError):
                instance.code = "Y"


if __name__ == "__main__":
    unittest.main()
