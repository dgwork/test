# -*- coding: utf-8 -*-
"""'몇 매까지 함께 끊을 수 있는지' 확인 로직 (1매 ~ 목표 매수)."""

import unittest
from datetime import datetime, timedelta

from korail_monitor.models import TrainSnapshot
from korail_monitor.provider import KorailProvider
from korail_monitor.window import KST

START = datetime(2026, 9, 23, 17, 0, tzinfo=KST)
END = datetime(2026, 9, 24, 12, 0, tzinfo=KST)


class FakeCountProvider(KorailProvider):
    """열차별 '실제 남은 매수'를 알고 있는 가짜 조회기.

    korail2 없이 매수 확인 로직만 검증하려고 __init__ 을 그대로 덮어쓴다.
    """

    def __init__(self, capacity):
        self.capacity = capacity  # {열차번호: 남은 매수}
        self.asked = []           # 몇 명으로 조회했는지 기록

    def search(self, dep, arr, start, end, passengers=1):
        self.asked.append(passengers)
        snaps = []
        for offset, (train_no, seats_left) in enumerate(sorted(self.capacity.items())):
            dep_at = START + timedelta(minutes=30 * offset)
            snaps.append(
                TrainSnapshot(
                    train_no=train_no,
                    train_name="KTX",
                    dep_name=dep,
                    arr_name=arr,
                    dep_at=dep_at,
                    arr_at=dep_at + timedelta(hours=2, minutes=25),
                    # 요청 인원이 남은 매수 이하일 때만 '예약가능'
                    general_code="11" if seats_left >= passengers else "13",
                    special_code="00",
                    waiting=False,
                )
            )
        return snaps


class SearchWithCountsTest(unittest.TestCase):
    def test_reports_one_and_two_tickets_separately(self):
        provider = FakeCountProvider({"101": 0, "102": 1, "103": 5})
        by_no = {s.train_no: s for s in provider.search_with_counts("서울", "포항", START, END, target=2)}

        self.assertIsNone(by_no["101"].max_bookable)   # 매진
        self.assertEqual(by_no["102"].max_bookable, 1)  # 1매만 가능 → 미리 한 장 잡을지 판단용
        self.assertEqual(by_no["103"].max_bookable, 2)  # 목표 2매 가능

    def test_never_asks_beyond_the_target(self):
        provider = FakeCountProvider({"101": 9})
        provider.search_with_counts("서울", "포항", START, END, target=2)
        self.assertEqual(provider.asked, [1, 2], "2매가 목표면 3매 이상은 물어보지 않는다")

    def test_target_one_makes_a_single_pass(self):
        provider = FakeCountProvider({"101": 4})
        snaps = provider.search_with_counts("서울", "포항", START, END, target=1)
        self.assertEqual(provider.asked, [1])
        self.assertEqual(snaps[0].max_bookable, 1)

    def test_skips_the_second_pass_when_nothing_has_even_one_seat(self):
        provider = FakeCountProvider({"101": 0, "102": 0})
        snaps = provider.search_with_counts("서울", "포항", START, END, target=2)
        self.assertEqual(provider.asked, [1], "1매도 없으면 2매 조회는 낭비")
        self.assertTrue(all(s.max_bookable is None for s in snaps))

    def test_target_is_clamped_to_korail_limit(self):
        provider = FakeCountProvider({"101": 9})
        provider.search_with_counts("서울", "포항", START, END, target=99)
        self.assertEqual(max(provider.asked), 9, "코레일 1회 예매 한도는 9매")

    def test_description_mentions_ticket_count(self):
        provider = FakeCountProvider({"101": 1, "102": 3})
        snaps = provider.search_with_counts("서울", "포항", START, END, target=2)
        self.assertIn("1매 예매가능", snaps[0].describe())
        self.assertIn("2매 예매가능", snaps[1].describe())


if __name__ == "__main__":
    unittest.main()
