# -*- coding: utf-8 -*-
"""명령행 진입점."""

from __future__ import annotations

import argparse
import logging
import os
import sys
from datetime import timedelta
from typing import Optional

from .monitor import MonitorConfig, run
from .notify import JsonlRecorder, build_notifiers
from .window import default_window, format_window, now_kst, parse_when

TRAIN_TYPES = ("all", "ktx", "saemaeul", "mugunghwa", "itx-cheongchun")


def load_dotenv(path: str = ".env") -> None:
    """의존성 없이 아주 단순하게 .env 를 읽어 환경변수에 채운다."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


#: .env.example 을 복사만 하고 채우지 않은 상태를 걸러내기 위한 값들
PLACEHOLDER_VALUES = {"", "비밀번호", "실제비밀번호", "010-1234-5678", "01012345678", "your-password"}


def looks_like_placeholder(korail_id: str, korail_pw: str) -> bool:
    return korail_id.strip() in PLACEHOLDER_VALUES or korail_pw.strip() in PLACEHOLDER_VALUES


def resolve_train_type(name: str):
    from korail2 import TrainType

    return {
        "all": TrainType.ALL,
        "ktx": TrainType.KTX,
        "saemaeul": TrainType.ITX_SAEMAEUL,
        "mugunghwa": TrainType.MUGUNGHWA,
        "itx-cheongchun": TrainType.ITX_CHEONGCHUN,
    }[name]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="korail-monitor",
        description="코레일 좌석 현황을 주기적으로 조회해 변화가 생기면 알려줍니다 (예매는 하지 않습니다).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "예)\n"
            "  python -m korail_monitor                      # 서울→포항, 23일 17:00~24일 12:00, 1·2매 확인, 60초 간격\n"
            "  python -m korail_monitor --seats 1            # 1매만 확인 (요청 수 절반)\n"
            "  python -m korail_monitor --mock --once -v     # 계정 없이 동작만 확인\n"
        ),
    )
    parser.add_argument("--dep", default="서울", help="출발역 (기본: 서울)")
    parser.add_argument("--arr", default="포항", help="도착역 (기본: 포항)")
    parser.add_argument("--start", help="구간 시작 (기본: 다가오는 23일 17:00). 예 '2026-09-23 17:00'")
    parser.add_argument("--end", help="구간 끝 (기본: 그 다음 날 12:00)")
    parser.add_argument("--interval", type=float, default=60.0, help="조회 간격(초). 기본 60")
    parser.add_argument("--seats", type=int, default=2, metavar="N",
                        help="목표 매수. 1매부터 N매까지 각각 예매 가능한지 확인한다 (기본 2)")
    parser.add_argument("--train-type", choices=TRAIN_TYPES, default="all", help="열차 종류 (기본: all)")
    parser.add_argument("--request-delay", type=float, default=0.4,
                        help="API 요청 사이 대기(초). 기본 0.4")
    parser.add_argument("--webhook", default=os.environ.get("KORAIL_WEBHOOK"),
                        help="Slack/Discord incoming webhook URL (환경변수 KORAIL_WEBHOOK 도 가능)")
    parser.add_argument("--notify-cmd", help="알림 시 실행할 명령. {title}, {body} 치환 가능")
    parser.add_argument("--log", dest="log_path", default="logs/korail.jsonl",
                        help="조회 결과 JSONL 경로 (기본 logs/korail.jsonl, 'none' 이면 기록 안 함)")
    parser.add_argument("--once", action="store_true", help="한 번만 조회하고 종료")
    parser.add_argument("--max-polls", type=int, help="지정한 횟수만큼만 조회")
    parser.add_argument("--mock", action="store_true", help="코레일 계정 없이 가짜 데이터로 실행")
    parser.add_argument("--notify-all", action="store_true", help="매진 같은 나쁜 소식도 알림")
    parser.add_argument("--no-bell", action="store_true", help="터미널 알림음 끄기")
    parser.add_argument("-v", "--verbose", action="store_true", help="변화가 없어도 매번 현황표 출력")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = build_parser().parse_args(argv)
    # 로그 시각도 열차 시각과 같은 한국시간으로 찍는다
    logging.Formatter.converter = lambda *_args: now_kst().timetuple()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    load_dotenv()

    reference = now_kst()
    start, end = default_window(reference)
    if args.start:
        start = parse_when(args.start, reference)
        # --start 만 준 경우 끝 시각은 '다음 날 정오'로 맞춘다
        end = (start + timedelta(days=1)).replace(hour=12, minute=0)
    if args.end:
        end = parse_when(args.end, reference)
    if end <= start:
        print("끝 시각이 시작 시각보다 빠릅니다: %s" % format_window(start, end), file=sys.stderr)
        return 2

    if args.mock:
        from .mock import MockProvider

        provider = MockProvider(seed=1)
    else:
        from .provider import KorailProvider, ProviderError

        korail_id = os.environ.get("KORAIL_ID")
        korail_pw = os.environ.get("KORAIL_PW")
        if not korail_id or not korail_pw:
            print(
                "코레일 로그인 정보가 없습니다. 환경변수 KORAIL_ID / KORAIL_PW 를 설정하거나 "
                ".env 파일을 만들어 주세요. (계정 없이 확인만 하려면 --mock)",
                file=sys.stderr,
            )
            return 2
        if looks_like_placeholder(korail_id, korail_pw):
            print(
                ".env 의 KORAIL_ID / KORAIL_PW 가 아직 예시값입니다. 실제 계정 정보로 바꿔주세요.\n"
                "  휴대폰번호로 로그인한다면 하이픈을 넣어야 합니다: 010-1234-5678 형식\n"
                "  (계정 없이 동작만 보려면 --mock)",
                file=sys.stderr,
            )
            return 2
        try:
            provider = KorailProvider(
                korail_id, korail_pw,
                request_delay=args.request_delay,
                train_type=resolve_train_type(args.train_type),
            )
        except ProviderError as exc:
            print(str(exc), file=sys.stderr)
            return 2

    config = MonitorConfig(
        dep=args.dep,
        arr=args.arr,
        start=start,
        end=end,
        interval=args.interval,
        seats=args.seats,
        verbose=args.verbose,
        notify_all=args.notify_all,
        max_polls=1 if args.once else args.max_polls,
    )
    notifiers = build_notifiers(
        webhook=args.webhook,
        command=args.notify_cmd,
        bell=not args.no_bell,
        notify_all=args.notify_all,
    )
    recorder = None
    if args.log_path and args.log_path.lower() != "none":
        recorder = JsonlRecorder(args.log_path)

    state = run(provider, config, notifiers, recorder)
    return 0 if state.polls else 1
