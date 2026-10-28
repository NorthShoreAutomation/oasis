# tests/conformance/test_timecode.py
import builtins
import unittest
from decimal import Decimal
from unittest import mock

from tests.conformance import timecode
from tests.conformance.timecode import derive_label, index_to_label, label_to_index, nearest_frame

NEAREST_CASES = [
    ((Decimal("4.170833"), 24000, 1001), 100),
    ((Decimal("6.25625"), 24000, 1001), 150),
    ((Decimal("1.001"), 30000, 1001), 30),
    ((Decimal("0.02"), 25, 1), 0),  # 0.02 * 25 = 0.5, a tie rounds toward zero
    ((Decimal("0.06"), 25, 1), 1),  # 0.06 * 25 = 1.5, a tie rounds toward zero
    ((Decimal("0.061"), 25, 1), 2),
    ((10, 25, 1), 250),
]

DERIVE_CASES = [
    (("01:00:59;00", 30, 30000, 1001, True), "01:01:00;02"),
    (("01:00:59;00", 60, 30000, 1001, True), "01:01:01;02"),
    (("01:00:00:00", 100, 24000, 1001, False), "01:00:04:04"),
    (("01:00:00:00", 150, 24000, 1001, False), "01:00:06:06"),
    (("10:00:00:00", 250, 25, 1, False), "10:00:10:00"),
    (("23:59:59:24", 1, 25, 1, False), "00:00:00:00"),
    (("00:09:59;29", 1, 30000, 1001, True), "00:10:00;00"),  # minute 10 does not skip
    (("00:00:59;59", 1, 60000, 1001, True), "00:01:00;04"),
]


class _NoFloat(float):
    """Stands in for ``float``: isinstance checks still work, construction fails."""

    def __new__(cls, *args, **kwargs):
        raise AssertionError("float was created")


class NearestFrameTest(unittest.TestCase):
    def test_cases(self):
        for args, expected in NEAREST_CASES:
            with self.subTest(args=args):
                self.assertEqual(nearest_frame(*args), expected)

    def test_no_float_is_created(self):
        with mock.patch.object(builtins, "float", _NoFloat):
            for args, expected in NEAREST_CASES:
                with self.subTest(args=args):
                    self.assertEqual(nearest_frame(*args), expected)
            for args, expected in DERIVE_CASES:
                with self.subTest(args=args):
                    self.assertEqual(derive_label(*args), expected)


class DeriveLabelTest(unittest.TestCase):
    def test_cases(self):
        for args, expected in DERIVE_CASES:
            with self.subTest(args=args):
                self.assertEqual(derive_label(*args), expected)

    def test_rate_outside_table_raises(self):
        with self.assertRaises(ValueError):
            derive_label("01:00:00:00", 1, 12, 1, False)

    def test_skipped_anchor_is_refused(self):
        with self.assertRaises(ValueError):
            derive_label("01:01:00;00", 1, 30000, 1001, True)
        with self.assertRaises(ValueError):
            label_to_index("01:01:00;01", 30, 2)
        with self.assertRaises(ValueError):
            label_to_index("00:01:00;03", 60, 4)

    def test_unskipped_minute_starts_are_accepted(self):
        self.assertEqual(label_to_index("00:10:00;00", 30, 2), 17982)
        self.assertEqual(label_to_index("00:01:00;02", 30, 2), 1800)


class RoundTripTest(unittest.TestCase):
    def _round_trip(self, fps, skip):
        day = 24 * 3600 * fps - skip * (1440 - 144)
        indexes = set(range(0, day, 997))
        for minute in range(1440):
            indexes.add(minute * 60 * fps - skip * (minute - minute // 10))
        for index in sorted(indexes):
            label = index_to_label(index, fps, skip)
            if label_to_index(label, fps, skip) != index:
                self.fail(f"index {index} gave label {label}")

    def test_round_trip_25_non_drop(self):
        self._round_trip(25, 0)

    def test_round_trip_30_drop(self):
        self._round_trip(30, 2)

    def test_tables(self):
        self.assertEqual(timecode.LABEL_RATES[(30000, 1001)], 30)
        self.assertEqual(timecode.DROP_SKIP, {(30000, 1001): 2, (60000, 1001): 4})


if __name__ == "__main__":
    unittest.main()
