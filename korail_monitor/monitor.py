# -*- coding: utf-8 -*-
"""1분 주기 폴링 루프."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Sequence

from .diff import Change, diff, index
from .models import TrainSnapshot
from .window import format_window, now_kst

log = logging.getLogger(__name__)


@dataclass
class MonitorConfig:
    dep: str = "서울"
    arr: str = "포항"
    start: datetime = None  # type: ignore[assignment]
    end: datetime = None  # type: ignore[assignment]
    interval: float = 60.0
    probe_max: int = 1
    #: 변화가 없어도 매 조회마다 현황표를 출력할지
    verbose: bool = False
    #: 매진 등 '나쁜 소식'도 알림 채널로 보낼지
    notify_all: bool = False
    max_polls: Optional[int] = None


@dataclass
class MonitorState:
    previous: Dict[str, TrainSnapshot] = field(default_factory=dict)
    polls: int = 0
    errors: int = 0
    consecutive_errors: int = 0


def summarize(snapshots: Sequence[TrainSnapshot]) -> str:
    """조회 결과 한 줄 요약."""
    available = [s for s in snapshots if s.has_seat]
    waiting = [s for s in snapshots if s.waiting and not s.has_seat]
    counted = [s.max_bookable for s in available if s.max_bookable]
    summary = "열차 %d편 중 예매가능 %d편" % (len(snapshots), len(available))
    if counted:
        summary += " (최대 %d인까지 가능한 열차 있음)" % max(counted)
    if waiting:
        summary += ", 예약대기 %d편" % len(waiting)
    return summary


def render_table(snapshots: Sequence[TrainSnapshot]) -> str:
    if not snapshots:
        return "  (구간 내 열차 없음)"
    return "\n".join("  " + snap.describe() for snap in snapshots)


def poll_once(provider, config: MonitorConfig, state: MonitorState,
              notifiers: Sequence[object], recorder=None) -> List[Change]:
    """한 번 조회하고, 변화가 있으면 알린다."""
    polled_at = now_kst()
    snapshots = provider.search_with_counts(
        config.dep, config.arr, config.start, config.end, probe_max=config.probe_max
    )
    current = index(snapshots)
    changes = diff(state.previous, current)
    if not config.notify_all:
        notify_changes = [c for c in changes if c.is_good_news]
    else:
        notify_changes = list(changes)

    stamp = polled_at.strftime("%H:%M:%S")
    if notify_changes:
        title = "[%s] %s → %s 변동: %s" % (stamp, config.dep, config.arr, summarize(snapshots))
        for notifier in notifiers:
            notifier.send(title, notify_changes)
    elif config.verbose:
        print("[%s] %s" % (stamp, summarize(snapshots)))
        print(render_table(snapshots))
    else:
        log.info("[%s] %s", stamp, summarize(snapshots))

    if recorder is not None:
        recorder.record(polled_at, snapshots, changes)

    state.previous = current
    state.polls += 1
    return changes


def run(provider, config: MonitorConfig, notifiers: Sequence[object], recorder=None,
        state: Optional[MonitorState] = None, sleeper=time.sleep) -> MonitorState:
    """중단(Ctrl+C)하거나 구간이 지날 때까지 `interval` 초마다 조회한다."""
    state = state or MonitorState()
    print("코레일 좌석 모니터 시작: %s → %s, %s, %d초 간격"
          % (config.dep, config.arr, format_window(config.start, config.end), int(config.interval)))
    if config.probe_max > 1:
        print("예매가능 인원 탐색: 최대 %d명까지 (조회 요청이 그만큼 늘어납니다)" % config.probe_max)

    try:
        while True:
            if config.max_polls is not None and state.polls >= config.max_polls:
                break
            if now_kst() > config.end:
                print("조회 구간이 모두 지났습니다. 모니터를 종료합니다.")
                break

            started = time.monotonic()
            try:
                poll_once(provider, config, state, notifiers, recorder)
                state.consecutive_errors = 0
            except KeyboardInterrupt:
                raise
            except Exception as exc:
                state.errors += 1
                state.consecutive_errors += 1
                log.warning("조회 실패(%d회 연속): %s", state.consecutive_errors, exc)
                if state.consecutive_errors >= 10:
                    log.error("연속 실패가 많아 모니터를 종료합니다.")
                    break

            if config.max_polls is not None and state.polls >= config.max_polls:
                break

            # 실패가 이어지면 간격을 늘려 서버에 부담을 주지 않는다
            backoff = min(2 ** state.consecutive_errors, 8) if state.consecutive_errors else 1
            elapsed = time.monotonic() - started
            sleeper(max(0.0, config.interval * backoff - elapsed))
    except KeyboardInterrupt:
        print("\n사용자 중단. 총 %d회 조회, 실패 %d회." % (state.polls, state.errors))

    return state
