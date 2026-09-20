# -*- coding: utf-8 -*-
"""코레일 계정 없이 동작을 확인하기 위한 가짜 조회기.

실제 API 와 같은 인터페이스(`search`, `search_with_counts`)를 제공하며,
조회할 때마다 좌석 상태가 조금씩 바뀌도록 만들어 알림/로그 흐름을 점검할 수 있다.
"""

from __future__ import annotations

import random
from datetime import datetime, timedelta
from typing import List

from .models import TrainSnapshot


class MockProvider(object):
    def __init__(self, seed: int = 0, headway_minutes: int = 40):
        self._rand = random.Random(seed)
        self._headway = headway_minutes
        self.calls = 0

    def _timetable(self, start: datetime, end: datetime) -> List[datetime]:
        times = []
        cursor = start.replace(minute=(start.minute // 10) * 10, second=0, microsecond=0)
        while cursor <= end:
            times.append(cursor)
            cursor += timedelta(minutes=self._headway)
        return times

    def search(self, dep: str, arr: str, start: datetime, end: datetime,
               passengers: int = 1) -> List[TrainSnapshot]:
        self.calls += 1
        snaps = []
        for index, dep_at in enumerate(self._timetable(start, end)):
            roll = self._rand.random() - 0.06 * (passengers - 1)
            general = "11" if roll > 0.75 else "13"
            special = "11" if roll > 0.93 else ("00" if index % 3 == 0 else "13")
            snaps.append(
                TrainSnapshot(
                    train_no="%03d" % (100 + index),
                    train_name="KTX",
                    dep_name=dep,
                    arr_name=arr,
                    dep_at=dep_at,
                    arr_at=dep_at + timedelta(hours=2, minutes=25),
                    general_code=general,
                    special_code=special,
                    waiting=roll > 0.55 and general != "11",
                    reserve_note="(모의 데이터)",
                )
            )
        return snaps

    def search_with_counts(self, dep: str, arr: str, start: datetime, end: datetime,
                           probe_max: int = 1) -> List[TrainSnapshot]:
        import dataclasses

        base = self.search(dep, arr, start, end, passengers=1)
        if probe_max <= 1:
            return base
        return [
            dataclasses.replace(
                snap,
                max_bookable=self._rand.randint(1, probe_max) if snap.has_seat else None,
            )
            for snap in base
        ]
