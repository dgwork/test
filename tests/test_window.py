# -*- coding: utf-8 -*-
import unittest
from datetime import datetime

from korail_monitor.window import KST, default_window, iter_days, parse_when, within


class DefaultWindowTest(unittest.TestCase):
    def test_upcoming_23rd_in_same_month(self):
        start, end = default_window(datetime(2026, 9, 20, 5, 48, tzinfo=KST))
        self.assertEqual(start, datetime(2026, 9, 23, 17, 0, tzinfo=KST))
        self.assertEqual(end, datetime(2026, 9, 24, 12, 0, tzinfo=KST))

    def test_rolls_to_next_month_when_passed(self):
        start, _ = default_window(datetime(2026, 9, 23, 18, 0, tzinfo=KST))
        self.assertEqual(start, datetime(2026, 10, 23, 17, 0, tzinfo=KST))

    def test_rolls_over_year_boundary(self):
        start, end = default_window(datetime(2026, 12, 25, 9, 0, tzinfo=KST))
        self.assertEqual(start, datetime(2027, 1, 23, 17, 0, tzinfo=KST))
        self.assertEqual(end, datetime(2027, 1, 24, 12, 0, tzinfo=KST))


class ParseWhenTest(unittest.TestCase):
    def setUp(self):
        self.ref = datetime(2026, 9, 20, 5, 48, tzinfo=KST)

    def test_full_date(self):
        self.assertEqual(parse_when("2026-09-23 17:00", self.ref),
                         datetime(2026, 9, 23, 17, 0, tzinfo=KST))

    def test_month_day_borrows_year(self):
        self.assertEqual(parse_when("09-24 12:00", self.ref),
                         datetime(2026, 9, 24, 12, 0, tzinfo=KST))

    def test_day_only_borrows_year_and_month(self):
        self.assertEqual(parse_when("23 17:00", self.ref),
                         datetime(2026, 9, 23, 17, 0, tzinfo=KST))

    def test_iso_separator(self):
        self.assertEqual(parse_when("2026-09-23T17:00", self.ref),
                         datetime(2026, 9, 23, 17, 0, tzinfo=KST))

    def test_rejects_garbage(self):
        with self.assertRaises(ValueError):
            parse_when("내일 저녁", self.ref)


class IterDaysTest(unittest.TestCase):
    def test_covers_both_days_of_overnight_window(self):
        start = datetime(2026, 9, 23, 17, 0, tzinfo=KST)
        end = datetime(2026, 9, 24, 12, 0, tzinfo=KST)
        self.assertEqual([d.day for d in iter_days(start, end)], [23, 24])
        self.assertTrue(within(datetime(2026, 9, 24, 0, 5, tzinfo=KST), start, end))
        self.assertFalse(within(datetime(2026, 9, 24, 12, 1, tzinfo=KST), start, end))


if __name__ == "__main__":
    unittest.main()
