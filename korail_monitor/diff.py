# -*- coding: utf-8 -*-
"""두 조회 결과를 비교해 '알릴 만한 변화'를 뽑아낸다."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional

from .models import TrainSnapshot, seat_label

#: 알림을 보낼 만한 변화 종류
GOOD_KINDS = ("seat_open", "count_up", "new_train", "waiting_open")


@dataclass(frozen=True)
class Change:
    kind: str
    after: TrainSnapshot
    before: Optional[TrainSnapshot] = None

    @property
    def is_good_news(self) -> bool:
        return self.kind in GOOD_KINDS

    def describe(self) -> str:
        label = {
            "seat_open": "🟢 좌석 열림",
            "count_up": "🟢 예매가능 매수 증가",
            "new_train": "🟢 새 열차 등장",
            "waiting_open": "🟡 예약대기 가능",
            "seat_closed": "🔴 매진",
            "count_down": "🔻 예매가능 매수 감소",
            "train_gone": "⚫ 목록에서 사라짐",
        }.get(self.kind, self.kind)

        detail = self.after.describe()
        if self.kind == "seat_open" and self.before is not None:
            detail += "  (이전: 일반실 %s / 특실 %s)" % (
                seat_label(self.before.general_code),
                seat_label(self.before.special_code),
            )
        if self.kind in ("count_up", "count_down") and self.before is not None:
            detail += "  (이전: %s매)" % (self.before.max_bookable or 0)
        return "%s  %s" % (label, detail)


def index(snapshots: Iterable[TrainSnapshot]) -> Dict[str, TrainSnapshot]:
    return {snap.key: snap for snap in snapshots}


def diff(before: Dict[str, TrainSnapshot], after: Dict[str, TrainSnapshot]) -> List[Change]:
    """이전 조회 결과 대비 변화 목록. 첫 조회(before 가 비어있음)는 변화로 보지 않는다."""
    changes: List[Change] = []
    if not before:
        return changes

    for key, now in after.items():
        was = before.get(key)
        if was is None:
            if now.has_seat:
                changes.append(Change("new_train", now))
            continue

        if now.has_seat and not was.has_seat:
            changes.append(Change("seat_open", now, was))
        elif was.has_seat and not now.has_seat:
            changes.append(Change("seat_closed", now, was))
        elif now.has_seat and was.has_seat:
            new_count, old_count = now.max_bookable, was.max_bookable
            if new_count is not None and old_count is not None:
                if new_count > old_count:
                    changes.append(Change("count_up", now, was))
                elif new_count < old_count:
                    changes.append(Change("count_down", now, was))

        if now.waiting and not was.waiting and not now.has_seat:
            changes.append(Change("waiting_open", now, was))

    for key, was in before.items():
        if key not in after and was.has_seat:
            changes.append(Change("train_gone", was, was))

    changes.sort(key=lambda c: (not c.is_good_news, c.after.dep_at))
    return changes
