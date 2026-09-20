#!/usr/bin/env bash
# 가상환경을 알아서 쓰는 실행 래퍼. 옵션은 그대로 전달됩니다.
#   ./run.sh                 1분 간격 모니터 (서울→포항, 23일 17:00~24일 12:00, 목표 2매)
#   ./run.sh --once -v       실제 API로 1회만 조회
#   ./run.sh --seats 1       1매만 확인
set -euo pipefail

cd "$(dirname "$0")"
VENV_PY=".venv/bin/python"
[ -x "$VENV_PY" ] || VENV_PY=".venv/Scripts/python.exe"
if [ ! -x "$VENV_PY" ]; then
  echo "가상환경이 없습니다. 먼저 ./setup.sh 를 실행하세요." >&2
  exit 1
fi
exec "$VENV_PY" -m korail_monitor "$@"
