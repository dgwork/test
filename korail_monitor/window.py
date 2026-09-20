# -*- coding: utf-8 -*-
"""조회 구간(출발 시각 범위) 계산 유틸."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Iterator, Tuple

try:  # Python 3.9+
    from zoneinfo import ZoneInfo

    KST = ZoneInfo("Asia/Seoul")
except Exception:  # pragma: no cover - zoneinfo 가 없는 환경 대비
    from datetime import timezone

    KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


def default_window(reference: datetime) -> Tuple[datetime, datetime]:
    """기본 조회 구간: 다가오는 23일 17:00 ~ 24일 12:00 (한국시간).

    reference 가 이미 23일 17시를 지났다면 다음 달 23일을 사용한다.
    """
    start = reference.replace(day=23, hour=17, minute=0, second=0, microsecond=0)
    if start <= reference:
        year, month = reference.year, reference.month
        if month == 12:
            year, month = year + 1, 1
        else:
            month += 1
        start = start.replace(year=year, month=month)
    end = (start + timedelta(days=1)).replace(hour=12, minute=0)
    return start, end


def parse_when(text: str, reference: datetime) -> datetime:
    """'2026-09-23 17:00', '09-23 17:00', '23 17:00' 형식을 모두 받아준다."""
    text = text.strip().replace("T", " ")
    patterns = ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%m-%d %H:%M", "%d %H:%M")
    for fmt in patterns:
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        if "%Y" not in fmt:
            parsed = parsed.replace(year=reference.year)
            if "%m" not in fmt:
                parsed = parsed.replace(month=reference.month)
        return parsed.replace(tzinfo=reference.tzinfo)
    raise ValueError("시각 형식을 이해할 수 없습니다: %r (예: '2026-09-23 17:00')" % text)


def iter_days(start: datetime, end: datetime) -> Iterator[datetime]:
    """구간이 걸쳐 있는 날짜들의 00:00 시각을 순서대로 돌려준다."""
    day = start.replace(hour=0, minute=0, second=0, microsecond=0)
    last = end.replace(hour=0, minute=0, second=0, microsecond=0)
    while day <= last:
        yield day
        day += timedelta(days=1)


def within(moment: datetime, start: datetime, end: datetime) -> bool:
    return start <= moment <= end


def format_window(start: datetime, end: datetime) -> str:
    return "%s ~ %s (KST)" % (
        start.strftime("%Y-%m-%d %H:%M"),
        end.strftime("%m-%d %H:%M"),
    )
