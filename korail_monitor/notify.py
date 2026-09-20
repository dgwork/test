# -*- coding: utf-8 -*-
"""알림 채널: 콘솔 / JSONL 기록 / 웹훅(슬랙·디스코드 호환) / 임의 명령."""

from __future__ import annotations

import json
import logging
import os
import shlex
import subprocess
import sys
from datetime import datetime
from typing import Iterable, List, Optional, Sequence

from .diff import Change
from .models import TrainSnapshot

log = logging.getLogger(__name__)


class ConsoleNotifier(object):
    """변화를 터미널에 출력한다. bell=True 면 좋은 소식에 한해 삑 소리를 낸다."""

    def __init__(self, bell: bool = True):
        self.bell = bell

    def send(self, title: str, changes: Sequence[Change]) -> None:
        print("\n" + title)
        for change in changes:
            print("  " + change.describe())
        if self.bell and any(c.is_good_news for c in changes):
            sys.stdout.write("\a")
        sys.stdout.flush()


class WebhookNotifier(object):
    """Slack / Discord 등 `{"text": ...}` 를 받는 incoming webhook."""

    def __init__(self, url: str, timeout: float = 10.0, good_news_only: bool = True):
        self.url = url
        self.timeout = timeout
        self.good_news_only = good_news_only

    def send(self, title: str, changes: Sequence[Change]) -> None:
        picked = [c for c in changes if c.is_good_news] if self.good_news_only else list(changes)
        if not picked:
            return
        text = title + "\n" + "\n".join(c.describe() for c in picked)
        payload = json.dumps({"text": text, "content": text}).encode("utf-8")
        try:
            import urllib.request

            req = urllib.request.Request(
                self.url, data=payload, headers={"Content-Type": "application/json"}
            )
            urllib.request.urlopen(req, timeout=self.timeout).read()
        except Exception as exc:  # 알림 실패가 모니터링을 멈추면 안 된다
            log.warning("웹훅 전송 실패: %s", exc)


class CommandNotifier(object):
    """좋은 소식이 있을 때 임의의 명령을 실행한다 (예: macOS `osascript`, `notify-send`).

    명령 문자열 안의 {title} / {body} 자리표시자가 치환된다.
    """

    def __init__(self, command: str, timeout: float = 15.0):
        self.command = command
        self.timeout = timeout

    def send(self, title: str, changes: Sequence[Change]) -> None:
        picked = [c for c in changes if c.is_good_news]
        if not picked:
            return
        body = "\n".join(c.describe() for c in picked)
        rendered = self.command.format(title=title, body=body)
        try:
            subprocess.run(shlex.split(rendered), timeout=self.timeout, check=False)
        except Exception as exc:
            log.warning("알림 명령 실행 실패: %s", exc)


class JsonlRecorder(object):
    """매 조회 결과를 한 줄 JSON 으로 남긴다 (나중에 추이 분석용)."""

    def __init__(self, path: str):
        self.path = path
        directory = os.path.dirname(os.path.abspath(path))
        if directory:
            os.makedirs(directory, exist_ok=True)

    def record(self, polled_at: datetime, snapshots: Iterable[TrainSnapshot],
               changes: Sequence[Change]) -> None:
        row = {
            "polled_at": polled_at.isoformat(),
            "trains": [snap.to_dict() for snap in snapshots],
            "changes": [
                {"kind": c.kind, "train": c.after.key, "dep_at": c.after.dep_at.isoformat()}
                for c in changes
            ],
        }
        with open(self.path, "a", encoding="utf-8") as fp:
            fp.write(json.dumps(row, ensure_ascii=False) + "\n")


def build_notifiers(webhook: Optional[str], command: Optional[str], bell: bool,
                    notify_all: bool) -> List[object]:
    notifiers: List[object] = [ConsoleNotifier(bell=bell)]
    if webhook:
        notifiers.append(WebhookNotifier(webhook, good_news_only=not notify_all))
    if command:
        notifiers.append(CommandNotifier(command))
    return notifiers
