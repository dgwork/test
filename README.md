# 코레일 좌석 모니터 (서울 → 포항)

지정한 시간대(기본값: **23일 17:00 ~ 24일 12:00**)에 출발하는 **서울 → 포항** 열차의
예매 가능 여부를 **1분마다** 조회하고, 상태가 바뀌면 터미널·웹훅·임의 명령으로 알려줍니다.
**조회만 하며 예매(결제)는 하지 않습니다.**

## 먼저 알아둘 것: "잔여 수량"에 대한 코레일의 한계

코레일 조회 API는 열차마다 *"일반실 몇 석 남음"* 같은 숫자를 주지 않습니다.
돌려주는 것은 좌석 등급별 **상태 코드**뿐입니다 (`00` 없음 / `11` 예약가능 / `13` 매진).

비유하자면 식당 앞 안내판에 **"자리 있음 / 만석"** 이라고만 써 있고 남은 테이블 수는 안 적혀 있는 셈입니다.
대신 *"4명인데 앉을 수 있나요?"* 라고 물어보면 답을 들을 수 있죠. 이 스크립트의 `--probe-max` 가 바로 그 방법입니다.
인원수를 1명부터 하나씩 올려가며 같은 조회를 반복해서 **"이 열차는 최대 몇 명까지 한 번에 끊을 수 있는지"**(1~9명, 코레일 1회 예매 한도)를 알아냅니다.
이것이 코레일이 외부에 알려주는 가장 정확한 "예매가능 수량"입니다.

`--probe-max N` 을 쓰면 조회 요청 수가 최대 N배로 늘어나므로, 필요할 때만 작은 값(2~4)으로 쓰세요.

## 설치

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

cp .env.example .env    # 코레일 아이디/비밀번호 입력
```

코레일 회원 계정이 필요합니다(조회에도 로그인이 필요한 API입니다).
`KORAIL_ID` 는 회원번호 8자리 / 휴대폰번호(`010-0000-0000`) / 이메일 중 하나입니다.

## 사용법

```bash
# 기본: 서울→포항, 다가오는 23일 17:00 ~ 24일 12:00, 60초 간격
python -m korail_monitor

# 몇 명까지 예매 가능한지까지 확인 (요청 수 증가)
python -m korail_monitor --probe-max 4

# 구간을 직접 지정
python -m korail_monitor --start "2026-09-23 17:00" --end "2026-09-24 12:00"

# 좌석이 열리면 슬랙으로 알림
python -m korail_monitor --webhook "https://hooks.slack.com/services/..."

# macOS 알림 센터로 띄우기
python -m korail_monitor --notify-cmd 'osascript -e display notification "{body}" with title "{title}"'

# 계정 없이 동작만 확인 (가짜 데이터)
python -m korail_monitor --mock --once -v
```

주요 옵션:

| 옵션 | 설명 | 기본값 |
| --- | --- | --- |
| `--dep` / `--arr` | 출발역 / 도착역 | 서울 / 포항 |
| `--start` / `--end` | 조회 구간 (`2026-09-23 17:00`, `09-23 17:00`, `23 17:00` 모두 허용) | 다가오는 23일 17:00 ~ 다음 날 12:00 |
| `--interval` | 조회 간격(초) | 60 |
| `--probe-max` | 최대 몇 명까지 예매 가능한지 확인 (1~9) | 1 (확인 안 함) |
| `--train-type` | `all`, `ktx`, `saemaeul`, `mugunghwa`, `itx-cheongchun` | all |
| `--webhook` | Slack/Discord incoming webhook | `KORAIL_WEBHOOK` |
| `--notify-cmd` | 알림 시 실행할 명령 (`{title}`, `{body}` 치환) | 없음 |
| `--log` | 조회 결과 JSONL 경로 (`none` 이면 미기록) | `logs/korail.jsonl` |
| `--notify-all` | 매진 등 나쁜 소식도 알림 | 좋은 소식만 |
| `--once` / `--max-polls` | 1회 / N회만 조회 | 무한 |
| `-v` | 변화가 없어도 매번 현황표 출력 | 변화 있을 때만 |

## 출력 예시

```
코레일 좌석 모니터 시작: 서울 → 포항, 2026-09-23 17:00 ~ 09-24 12:00 (KST), 60초 간격
14:55:03 INFO [14:55:03] 열차 29편 중 예매가능 8편, 예약대기 2편

[14:56:03] 서울 → 포항 변동: 열차 29편 중 예매가능 9편
  🟢 좌석 열림  09/23 21:40→00:05 | KTX 107 | 일반실 예약가능 | 특실 매진 | 최대 2인 예매가능  (이전: 일반실 매진 / 특실 매진)
```

* 변화가 없으면 한 줄 요약만 남기고, **변화가 생겼을 때만** 상세 내역을 알립니다.
* 매 조회 결과는 `logs/korail.jsonl` 에 한 줄씩 쌓여 나중에 추이를 분석할 수 있습니다.

## 구조

| 파일 | 역할 |
| --- | --- |
| `korail_monitor/window.py` | 조회 구간 계산 (자정을 넘는 구간, KST 처리) |
| `korail_monitor/provider.py` | 코레일 API 조회 + 페이지 이어붙이기 + 인원수 탐색 |
| `korail_monitor/diff.py` | 이전 조회 대비 변화 추출 (좌석 열림/매진/인원 증감) |
| `korail_monitor/monitor.py` | 1분 주기 폴링 루프, 실패 시 백오프 |
| `korail_monitor/notify.py` | 콘솔 / 웹훅 / 명령 / JSONL 기록 |
| `korail_monitor/mock.py` | 계정 없이 돌려보는 가짜 조회기 |

## 테스트

```bash
python -m unittest discover -s tests -v
```

## 장시간 돌리기

`nohup` 이나 `screen`/`tmux` 로 띄워두면 됩니다. 구간이 모두 지나면 스스로 종료합니다.

```bash
nohup python -m korail_monitor --probe-max 3 --webhook "$KORAIL_WEBHOOK" > monitor.out 2>&1 &
```

## 주의

* 비공개(모바일 앱용) API를 사용하므로 코레일 사정에 따라 응답 형식이 바뀔 수 있습니다.
* 1분 간격은 사람이 새로고침하는 수준이지만, `--probe-max` 를 크게 잡으면 요청이 배로 늘어납니다.
  `--request-delay` 로 요청 간 간격을 두고 있으니 더 짧게 줄이지 마세요.
* 자동 예매/결제 기능은 의도적으로 넣지 않았습니다. 알림을 받으면 앱이나 홈페이지에서 직접 예매하세요.
