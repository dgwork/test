# -*- coding: utf-8 -*-
"""좌석 조회 백엔드.

`KorailProvider` 는 korail2 라이브러리를 통해 코레일 모바일 API(smart.letskorail.com)를
호출한다. 코레일은 "잔여 좌석 몇 석" 이라는 숫자를 공개하지 않고 일반실/특실별
예약가능·매진 코드만 내려주기 때문에, 수량이 필요하면 `probe_max` 를 켜서
'몇 명까지 한 번에 예매되는지'(1~9명)를 계단식으로 확인한다.
"""

from __future__ import annotations

import logging
import time as _time
from datetime import datetime, timedelta
from typing import List, Optional, Sequence

from .models import TrainSnapshot
from .window import KST, iter_days

log = logging.getLogger(__name__)

#: 한 번의 예매로 끊을 수 있는 최대 인원 (코레일 정책)
MAX_PASSENGERS = 9

#: 하루치를 훑을 때 허용하는 최대 페이지 수 (무한 루프 방지)
MAX_PAGES_PER_DAY = 12


class ProviderError(RuntimeError):
    pass


def _to_snapshot(train, max_bookable: Optional[int] = None) -> TrainSnapshot:
    """korail2.Train → TrainSnapshot"""

    def _dt(date_str: str, time_str: str) -> datetime:
        return datetime.strptime(date_str + time_str[:6], "%Y%m%d%H%M%S").replace(tzinfo=KST)

    return TrainSnapshot(
        train_no=str(train.train_no),
        train_name=str(train.train_type_name or "").strip(),
        dep_name=str(train.dep_name),
        arr_name=str(train.arr_name),
        dep_at=_dt(train.dep_date, train.dep_time),
        arr_at=_dt(train.arr_date, train.arr_time),
        general_code=train.general_seat,
        special_code=train.special_seat,
        waiting=bool(train.has_waiting_list()),
        reserve_note=str(train.reserve_possible_name or "").replace("\n", " ").strip(),
        max_bookable=max_bookable,
    )



def collect_window(search_page, start: datetime, end: datetime) -> List[TrainSnapshot]:
    """`search_page(date, time)` 를 이어 호출하며 구간 전체의 열차를 모은다.

    코레일 조회 API 는 지정한 시각 이후 열차를 10편 안팎씩만 돌려주므로,
    마지막 열차 출발 시각 + 1분을 다음 조회 시각으로 삼아 구간 끝까지 따라간다.
    자정을 넘는 구간은 날짜를 바꿔가며 같은 방식으로 훑는다.
    """
    found = {}
    for day in iter_days(start, end):
        cursor = start if day.date() == start.date() else day
        for _page in range(MAX_PAGES_PER_DAY):
            trains = search_page(cursor.strftime("%Y%m%d"), cursor.strftime("%H%M%S"))
            if not trains:
                break

            last_dep = None
            for train in trains:
                snap = _to_snapshot(train)
                last_dep = snap.dep_at if last_dep is None else max(last_dep, snap.dep_at)
                if start <= snap.dep_at <= end:
                    found[snap.key] = snap

            if last_dep is None or last_dep >= end:
                break
            if last_dep.hour == 23 and last_dep.minute == 59:
                break
            cursor = last_dep + timedelta(minutes=1)
            if cursor.date() != day.date():
                break

    return sorted(found.values(), key=lambda s: s.dep_at)


class KorailProvider(object):
    """코레일 실 API 조회기."""

    def __init__(self, korail_id: str, korail_pw: str, request_delay: float = 0.4,
                 train_type: Optional[str] = None):
        try:
            from korail2 import Korail, TrainType  # noqa: F401
        except ImportError as exc:  # pragma: no cover - 설치 안내
            raise ProviderError(
                "korail2 가 설치되어 있지 않습니다. `pip install -r requirements.txt` 를 먼저 실행하세요."
            ) from exc

        from korail2 import TrainType

        self._korail_id = korail_id
        self._korail_pw = korail_pw
        self._request_delay = request_delay
        self._train_type = train_type or TrainType.ALL
        self._client = None

    # -- 연결 -----------------------------------------------------------
    def _connect(self):
        from korail2 import Korail

        if self._client is None:
            log.info("코레일 로그인 중...")
            self._client = Korail(self._korail_id, self._korail_pw, auto_login=True)
            if not self._client.logined:
                raise ProviderError("코레일 로그인에 실패했습니다. 아이디/비밀번호를 확인하세요.")
            log.info("로그인 성공 (%s)", self._client.name or self._korail_id)
        return self._client

    def _search_page(self, dep: str, arr: str, date: str, time_str: str, passengers: int):
        from korail2 import AdultPassenger, NeedToLoginError, NoResultsError, SoldOutError

        client = self._connect()
        psgrs = [AdultPassenger(passengers)]
        for attempt in (1, 2):
            try:
                return client.search_train(
                    dep, arr, date=date, time=time_str,
                    train_type=self._train_type,
                    passengers=psgrs,
                    include_no_seats=True,
                    include_waiting_list=True,
                )
            except (NoResultsError, SoldOutError):
                return []
            except NeedToLoginError:
                if attempt == 2:
                    raise
                log.warning("세션이 만료되어 재로그인합니다.")
                self._client = None
            finally:
                if self._request_delay:
                    _time.sleep(self._request_delay)
        return []

    # -- 조회 -----------------------------------------------------------
    def search(self, dep: str, arr: str, start: datetime, end: datetime,
               passengers: int = 1) -> List[TrainSnapshot]:
        """구간 [start, end] 안에 출발하는 열차 목록을 조회한다."""
        return collect_window(
            lambda date, time_str: self._search_page(dep, arr, date, time_str, passengers),
            start, end,
        )

    def search_with_counts(self, dep: str, arr: str, start: datetime, end: datetime,
                           probe_max: int = 1) -> List[TrainSnapshot]:
        """좌석 상태 + '최대 몇 명까지 예매 가능한지'를 함께 조회한다.

        인원수를 1명부터 하나씩 올려가며 같은 조회를 반복한다. 어떤 열차도
        좌석을 내주지 않는 인원수에 도달하면 더 올리지 않고 멈춘다.
        (요청 수 = 인원 단계 수 × 구간 페이지 수 이므로 probe_max 는 작게 쓰는 편이 좋다.)
        """
        probe_max = max(1, min(int(probe_max), MAX_PASSENGERS))
        base = {s.key: s for s in self.search(dep, arr, start, end, passengers=1)}
        if probe_max == 1:
            return sorted(base.values(), key=lambda s: s.dep_at)

        best = {key: (1 if snap.has_seat else 0) for key, snap in base.items()}
        for count in range(2, probe_max + 1):
            snaps = self.search(dep, arr, start, end, passengers=count)
            any_seat = False
            for snap in snaps:
                if snap.has_seat and snap.key in best:
                    best[snap.key] = count
                    any_seat = True
            if not any_seat:
                break

        merged = [_with_count(snap, best.get(key, 0)) for key, snap in base.items()]
        return sorted(merged, key=lambda s: s.dep_at)


def _with_count(snap: TrainSnapshot, count: int) -> TrainSnapshot:
    import dataclasses

    return dataclasses.replace(snap, max_bookable=count if count else None)
