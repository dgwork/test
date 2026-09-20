# -*- coding: utf-8 -*-
"""collect_window 가 코레일 조회 API 의 '10편씩 끊어주기'를 제대로 따라가는지 확인."""

import unittest
from datetime import datetime, timedelta

from korail_monitor.provider import MAX_PAGES_PER_DAY, collect_window
from korail_monitor.window import KST


class FakeTrain(object):
    """korail2.Train 과 같은 모양의 최소 스텁."""

    def __init__(self, dep_at, train_no, general="11", special="13"):
        arr_at = dep_at + timedelta(hours=2, minutes=25)
        self.train_no = train_no
        self.train_type_name = "KTX"
        self.dep_name, self.arr_name = "서울", "포항"
        self.dep_date, self.dep_time = dep_at.strftime("%Y%m%d"), dep_at.strftime("%H%M%S")
        self.arr_date, self.arr_time = arr_at.strftime("%Y%m%d"), arr_at.strftime("%H%M%S")
        self.general_seat, self.special_seat = general, special
        self.reserve_possible_name = "예약가능"

    def has_waiting_list(self):
        return False


class FakeApi(object):
    """30분 간격 시간표를 가지고, 한 번에 4편씩만 돌려주는 가짜 API."""

    PAGE_SIZE = 4

    def __init__(self, first: datetime, last: datetime, headway_minutes=30):
        self.timetable = []
        cursor = first
        while cursor <= last:
            self.timetable.append(cursor)
            cursor += timedelta(minutes=headway_minutes)
        self.requests = []

    def __call__(self, date, time_str):
        self.requests.append((date, time_str))
        asked = datetime.strptime(date + time_str, "%Y%m%d%H%M%S").replace(tzinfo=KST)
        # 같은 날, 요청 시각 이후 열차만 (실제 API 와 동일하게 날짜 경계를 넘지 않는다)
        upcoming = [t for t in self.timetable if t >= asked and t.date() == asked.date()]
        return [FakeTrain(t, "%03d" % (self.timetable.index(t) + 100))
                for t in upcoming[: self.PAGE_SIZE]]


class CollectWindowTest(unittest.TestCase):
    def setUp(self):
        self.start = datetime(2026, 9, 23, 17, 0, tzinfo=KST)
        self.end = datetime(2026, 9, 24, 12, 0, tzinfo=KST)
        self.api = FakeApi(datetime(2026, 9, 23, 5, 0, tzinfo=KST),
                           datetime(2026, 9, 24, 23, 30, tzinfo=KST))

    def test_collects_every_train_across_midnight(self):
        snaps = collect_window(self.api, self.start, self.end)
        expected = [t for t in self.api.timetable if self.start <= t <= self.end]
        self.assertEqual([s.dep_at for s in snaps], expected)

    def test_excludes_trains_outside_the_window(self):
        snaps = collect_window(self.api, self.start, self.end)
        self.assertTrue(all(self.start <= s.dep_at <= self.end for s in snaps))
        self.assertGreater(len(snaps), self.api.PAGE_SIZE, "여러 페이지를 이어붙여야 한다")

    def test_results_are_sorted_and_deduplicated(self):
        snaps = collect_window(self.api, self.start, self.end)
        keys = [s.key for s in snaps]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual([s.dep_at for s in snaps], sorted(s.dep_at for s in snaps))

    def test_stops_paging_once_past_the_window_end(self):
        collect_window(self.api, self.start, self.end)
        # 구간이 끝나는 24일 12:00 이후를 다시 물어보지 않는다
        asked_after_end = [r for r in self.api.requests if r[0] == "20260924" and r[1] > "120000"]
        self.assertEqual(asked_after_end, [])

    def test_page_budget_is_respected(self):
        per_day = {}
        collect_window(self.api, self.start, self.end)
        for date, _ in self.api.requests:
            per_day[date] = per_day.get(date, 0) + 1
        self.assertTrue(all(count <= MAX_PAGES_PER_DAY for count in per_day.values()))

    def test_empty_result_ends_the_day_early(self):
        empty = lambda date, time_str: []
        self.assertEqual(collect_window(empty, self.start, self.end), [])

    def test_seat_codes_are_mapped(self):
        snaps = collect_window(self.api, self.start, self.end)
        self.assertTrue(snaps[0].has_general)
        self.assertFalse(snaps[0].has_special)
        self.assertTrue(snaps[0].has_seat)


if __name__ == "__main__":
    unittest.main()
