"""Exact-number JSON text for the working store of the semantic stage."""

import unittest
from decimal import Decimal

from tests.conformance import exact_json


class ExactJsonTests(unittest.TestCase):
    def assertSameTree(self, a, b):
        self.assertEqual(a, b)
        self.assertEqual(repr(a), repr(b))

    def test_round_trip_keeps_each_value_and_type(self):
        value = {"a": 1, "b": Decimal("1.0"), "c": [Decimal("2.5e-3")]}
        back = exact_json.loads(exact_json.dumps(value))
        self.assertEqual(back, value)
        self.assertIs(type(back["a"]), int)
        self.assertIs(type(back["b"]), Decimal)
        self.assertEqual(str(back["b"]), "1.0")
        self.assertIs(type(back["c"][0]), Decimal)
        self.assertEqual(back["c"][0], Decimal("2.5e-3"))

    def test_text_is_compact_and_keeps_key_order(self):
        self.assertEqual(
            exact_json.dumps({"z": [1, True, None], "a": "x", "m": Decimal("1.0")}),
            '{"z":[1,true,null],"a":"x","m":1.0}',
        )

    def test_integral_decimal_stays_a_decimal(self):
        for text in ("5E0", "-0", "1E+2", "0E-7"):
            with self.subTest(text):
                back = exact_json.loads(exact_json.dumps([Decimal(text)]))
                self.assertIs(type(back[0]), Decimal)
                self.assertEqual(back[0], Decimal(text))

    def test_strings_and_nesting(self):
        value = {"t": "café \"q\" \\ \n", "n": {"k": [[], {}, [Decimal("-12.50")]]}, "b": False}
        self.assertSameTree(exact_json.loads(exact_json.dumps(value)), value)

    def test_binary_numbers_are_refused(self):
        with self.assertRaises(TypeError):
            exact_json.dumps({"x": 0.5})
        with self.assertRaises(ValueError):
            exact_json.loads("[NaN]")


if __name__ == "__main__":
    unittest.main()
