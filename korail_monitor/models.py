# -*- coding: utf-8 -*-
"""모니터가 다루는 값 객체들."""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from typing import Optional

#: 코레일이 좌석 상태로 내려주는 코드 (korail2 의 h_gen_rsv_cd / h_spe_rsv_cd)
SEAT_CODE_LABEL = {
    "00": "없음",
    "11": "예약가능",
    "13": "매진",
}


def seat_label(code: Optional[str]) -> str:
    if code is None:
        return "-"
    return SEAT_CODE_LABEL.get(code, "코드%s" % code)


@dataclass(frozen=True)
class TrainSnapshot:
    """한 번의 조회 시점에서 본 열차 한 편의 상태."""

    train_no: str
    train_name: str
    dep_name: str
    arr_name: str
    dep_at: datetime
    arr_at: datetime
    general_code: Optional[str]
    special_code: Optional[str]
    waiting: bool
    reserve_note: str = ""
    #: 좌석이 남아 있는 것으로 확인된 최대 인원수(1~probe_max). 미탐색이면 None.
    max_bookable: Optional[int] = None

    @property
    def key(self) -> str:
        """열차를 식별하는 키. 같은 열차번호라도 날짜가 다르면 다른 열차."""
        return "%s@%s" % (self.train_no, self.dep_at.strftime("%Y%m%d"))

    @property
    def has_general(self) -> bool:
        return self.general_code == "11"

    @property
    def has_special(self) -> bool:
        return self.special_code == "11"

    @property
    def has_seat(self) -> bool:
        return self.has_general or self.has_special

    def describe(self) -> str:
        parts = [
            "%s→%s" % (self.dep_at.strftime("%m/%d %H:%M"), self.arr_at.strftime("%H:%M")),
            "%s %s" % (self.train_name, self.train_no),
            "일반실 %s" % seat_label(self.general_code),
            "특실 %s" % seat_label(self.special_code),
        ]
        if self.waiting:
            parts.append("예약대기 가능")
        if self.max_bookable is not None:
            parts.append("최대 %d인 예매가능" % self.max_bookable)
        elif self.has_seat:
            parts.append("1인 예매가능")
        return " | ".join(parts)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["dep_at"] = self.dep_at.isoformat()
        d["arr_at"] = self.arr_at.isoformat()
        d["key"] = self.key
        d["has_seat"] = self.has_seat
        return d
