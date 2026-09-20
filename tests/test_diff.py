# -*- coding: utf-8 -*-
import unittest
from datetime import datetime, timedelta

from korail_monitor.diff import diff, index
from korail_monitor.models import TrainSnapshot
from korail_monitor.window import KST

DEP = datetime(2026, 9, 23, 18, 0, tzinfo=KST)


def train(no="101", general="13", special="00", waiting=False, count=None, dep_at=DEP):
    return TrainSnapshot(
        train_no=no,
        train_name="KTX",
        dep_name="서울",
        arr_name="포항",
        dep_at=dep_at,
        arr_at=dep_at + timedelta(hours=2, minutes=25),
        general_code=general,
        special_code=special,
        waiting=waiting,
        max_bookable=count,
    )


class DiffTest(unittest.TestCase):
    def test_first_poll_is_not_a_change(self):
        self.assertEqual(diff({}, index([train(general="11")])), [])

    def test_sold_out_to_available(self):
        changes = diff(index([train(general="13")]), index([train(general="11")]))
        self.assertEqual([c.kind for c in changes], ["seat_open"])
        self.assertTrue(changes[0].is_good_news)

    def test_available_to_sold_out(self):
        changes = diff(index([train(general="11")]), index([train(general="13")]))
        self.assertEqual([c.kind for c in changes], ["seat_closed"])
        self.assertFalse(changes[0].is_good_news)

    def test_special_seat_alone_counts_as_available(self):
        changes = diff(index([train(general="13", special="13")]),
                       index([train(general="13", special="11")]))
        self.assertEqual([c.kind for c in changes], ["seat_open"])

    def test_count_increase_and_decrease(self):
        up = diff(index([train(general="11", count=2)]), index([train(general="11", count=5)]))
        self.assertEqual([c.kind for c in up], ["count_up"])
        down = diff(index([train(general="11", count=5)]), index([train(general="11", count=2)]))
        self.assertEqual([c.kind for c in down], ["count_down"])

    def test_no_change_produces_nothing(self):
        self.assertEqual(diff(index([train(general="11", count=3)]),
                              index([train(general="11", count=3)])), [])

    def test_new_train_with_seats(self):
        later = train(no="102", general="11", dep_at=DEP + timedelta(hours=1))
        changes = diff(index([train()]), index([train(), later]))
        self.assertEqual([c.kind for c in changes], ["new_train"])

    def test_train_disappearing_while_it_had_seats(self):
        changes = diff(index([train(general="11")]), index([]))
        self.assertEqual([c.kind for c in changes], ["train_gone"])

    def test_waiting_list_opens(self):
        changes = diff(index([train(general="13", waiting=False)]),
                       index([train(general="13", waiting=True)]))
        self.assertEqual([c.kind for c in changes], ["waiting_open"])

    def test_same_train_number_on_different_days_is_different_train(self):
        day2 = train(general="11", dep_at=DEP + timedelta(days=1))
        changes = diff(index([train(general="13")]), index([train(general="13"), day2]))
        self.assertEqual([c.kind for c in changes], ["new_train"])

    def test_good_news_sorts_first(self):
        before = index([train(no="101", general="13"),
                        train(no="102", general="11", dep_at=DEP + timedelta(hours=1))])
        after = index([train(no="101", general="11"),
                       train(no="102", general="13", dep_at=DEP + timedelta(hours=1))])
        self.assertEqual([c.kind for c in diff(before, after)], ["seat_open", "seat_closed"])


if __name__ == "__main__":
    unittest.main()
