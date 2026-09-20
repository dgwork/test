#!/usr/bin/env bash
# 코레일 좌석 모니터 설치 스크립트 (macOS / Linux)
#   ./setup.sh   한 번만 실행하면 가상환경 + 의존성 + .env 준비 + 자체 점검까지 끝납니다.
# 여러 번 실행해도 안전합니다.
set -euo pipefail

cd "$(dirname "$0")"
say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
ok()  { printf '  \033[32m✓\033[0m %s\n' "$*"; }
warn(){ printf '  \033[33m!\033[0m %s\n' "$*"; }

# 1) 파이썬 확인 (zoneinfo 때문에 3.9 이상 필요)
say "1/5 파이썬 확인"
PY=""
for candidate in python3.12 python3.11 python3.10 python3.9 python3; do
  if command -v "$candidate" >/dev/null 2>&1 &&
     "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
    PY="$candidate"
    break
  fi
done
if [ -z "$PY" ]; then
  echo "파이썬 3.9 이상이 필요합니다. https://www.python.org/downloads/ 에서 설치해 주세요." >&2
  exit 1
fi
ok "$($PY -V) ($(command -v "$PY"))"

# 2) 가상환경
say "2/5 가상환경 준비 (.venv)"
if [ ! -d .venv ]; then
  "$PY" -m venv .venv
  ok "새로 만들었습니다"
else
  ok "이미 있어서 그대로 씁니다"
fi
VENV_PY=".venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY=".venv/Scripts/python.exe"   # Git Bash on Windows

# 3) 의존성
say "3/5 의존성 설치"
"$VENV_PY" -m pip install --quiet --upgrade pip
"$VENV_PY" -m pip install --quiet -r requirements.txt
ok "$("$VENV_PY" -m pip list 2>/dev/null | grep -i '^korail2' | tr -s ' ')"

# 4) 계정 설정 파일
say "4/5 코레일 계정 설정 (.env)"
if [ ! -f .env ]; then
  cp .env.example .env
  warn ".env 를 만들었습니다. 편집기로 열어 KORAIL_ID / KORAIL_PW 를 넣어주세요."
  warn "휴대폰번호로 로그인한다면 하이픈을 꼭 넣으세요: 010-1234-5678"
  NEEDS_CREDENTIALS=1
elif grep -qE '^KORAIL_PW=(비밀번호)?$' .env; then
  warn ".env 의 KORAIL_PW 가 아직 예시값입니다. 실제 비밀번호로 바꿔주세요."
  NEEDS_CREDENTIALS=1
else
  ok ".env 에 계정 정보가 들어 있습니다"
  NEEDS_CREDENTIALS=0
fi

# 5) 자체 점검 (계정 없이 확인 가능한 부분까지)
say "5/5 자체 점검"
"$VENV_PY" -m unittest discover -s tests >/dev/null 2>&1 && ok "테스트 통과"
"$VENV_PY" -m korail_monitor --mock --once --log none >/dev/null 2>&1 && ok "모의 조회 정상"

say "설치 완료"
if [ "${NEEDS_CREDENTIALS:-0}" = "1" ]; then
  cat <<'NEXT'
  다음 순서로 진행하세요:
    1) .env 에 코레일 아이디/비밀번호 입력
    2) ./run.sh --once -v      # 실제 API로 1회 조회해 로그인·조회 확인
    3) ./run.sh                # 1분 간격 모니터 시작 (Ctrl+C 로 중단)
NEXT
else
  cat <<'NEXT'
  바로 시작할 수 있습니다:
    ./run.sh --once -v         # 실제 API로 1회 조회해 로그인·조회 확인
    ./run.sh                   # 1분 간격 모니터 시작 (Ctrl+C 로 중단)
NEXT
fi
