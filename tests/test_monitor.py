# -*- coding: utf-8 -*-
import os
import json
import tempfile
import unittest
from datetime import datetime, timedelta

from korail_monitor.mock import MockProvider
from korail_monitor.monitor import MonitorConfig, MonitorState, poll_once, run, summarize
from korail_monitor.notify import JsonlRecorder
from korail_monitor.window import KST, now_kst


class RecordingNotifier(object):
    def __init__(self):
        self.sent = []

    def send(self, title, changes):
        self.sent.append((title, list(changes)))


class FlakyProvider(object):
    """처음 두 번은 실패하고 그 뒤로는 정상 응답하는 조회기."""

    def __init__(self):
        self.calls = 0

    def search_with_counts(self, dep, arr, start, end, target=2):
        self.calls += 1
        if self.calls <= 2:
            raise RuntimeError("네트워크 오류")
        return []


def make_config(**kwargs):
    start = now_kst() + timedelta(days=1)
    defaults = dict(start=start, end=start + timedelta(hours=19), interval=0.0, max_polls=3)
    defaults.update(kwargs)
    return MonitorConfig(**defaults)


class PollOnceTest(unittest.TestCase):
    def test_first_poll_stores_state_without_notifying(self):
        provider, notifier = MockProvider(seed=3), RecordingNotifier()
        state = MonitorState()
        changes = poll_once(provider, make_config(), state, [notifier])
        self.assertEqual(changes, [])
        self.assertEqual(notifier.sent, [])
        self.assertTrue(state.previous)
        self.assertEqual(state.polls, 1)

    def test_second_poll_reports_changes(self):
        provider, notifier = MockProvider(seed=3), RecordingNotifier()
        config, state = make_config(), MonitorState()
        poll_once(provider, config, state, [notifier])
        poll_once(provider, config, state, [notifier])
        self.assertEqual(state.polls, 2)
        # 모의 데이터는 조회마다 좌석 상태가 흔들리므로 변화가 잡혀야 한다
        self.assertTrue(notifier.sent, "두 번째 조회에서는 변화 알림이 있어야 한다")

    def test_recorder_writes_one_json_line_per_poll(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "nested", "korail.jsonl")
            recorder = JsonlRecorder(path)
            config, state = make_config(), MonitorState()
            provider = MockProvider(seed=5)
            poll_once(provider, config, state, [], recorder)
            poll_once(provider, config, state, [], recorder)
            with open(path, encoding="utf-8") as fp:
                rows = [json.loads(line) for line in fp]
            self.assertEqual(len(rows), 2)
            self.assertIn("trains", rows[0])
            self.assertIn("polled_at", rows[0])
            self.assertTrue(all("has_seat" in t for t in rows[0]["trains"]))


class RunLoopTest(unittest.TestCase):
    def test_stops_after_max_polls(self):
        slept = []
        state = run(MockProvider(seed=7), make_config(max_polls=3), [], sleeper=slept.append)
        self.assertEqual(state.polls, 3)
        self.assertEqual(len(slept), 2, "마지막 조회 뒤에는 기다리지 않는다")

    def test_stops_when_window_is_over(self):
        past = now_kst() - timedelta(days=2)
        config = MonitorConfig(start=past, end=past + timedelta(hours=1), interval=0.0)
        state = run(MockProvider(seed=7), config, [], sleeper=lambda s: None)
        self.assertEqual(state.polls, 0)

    def test_survives_errors_and_backs_off(self):
        slept = []
        provider = FlakyProvider()
        state = run(provider, make_config(max_polls=3, interval=10.0), [], sleeper=slept.append)
        self.assertEqual(state.attempts, 3, "실패도 시도 횟수로 센다")
        self.assertEqual(state.errors, 2)
        self.assertEqual(state.polls, 1, "성공한 조회만 polls 로 센다")
        self.assertGreater(slept[0], 10.0, "실패 뒤에는 간격을 늘려 다시 시도한다")

    def test_once_gives_up_after_a_single_failed_attempt(self):
        """--once 는 '성공할 때까지'가 아니라 '한 번만' 이어야 한다."""
        slept = []
        provider = FlakyProvider()
        state = run(provider, make_config(max_polls=1, interval=60.0), [], sleeper=slept.append)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(state.polls, 0)
        self.assertEqual(slept, [], "한 번 시도하고 끝이면 기다릴 이유가 없다")


class SummarizeTest(unittest.TestCase):
    def test_counts_available_trains(self):
        snaps = MockProvider(seed=11).search("서울", "포항",
                                             datetime(2026, 9, 23, 17, 0, tzinfo=KST),
                                             datetime(2026, 9, 24, 12, 0, tzinfo=KST))
        text = summarize(snaps)
        self.assertIn("열차 %d편" % len(snaps), text)
        self.assertIn("예매가능", text)


if __name__ == "__main__":
    unittest.main()
