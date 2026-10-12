#!/usr/bin/env bash
# Render 컨테이너 시작 — 무료 플랜 512MB 라서 역할(ROLE)별로 서비스를 나눈다 (같은 이미지)
#   ROLE=web    (ship-order-forecast) FastAPI :$PORT — /ship 화면 · /ship API · /mlflow → MLflow 서비스로 이동
#   ROLE=mlflow (ship-order-mlflow)   1) Kedro ship_orders_track — 빌드 때 Kedro 가 만든 보고서를 MLflow(Neon PostgreSQL)에 기록
#                                     2) MLflow 앱(읽기 전용) :$PORT — 한 프로세스
set -uo pipefail
if [ "${ROLE:-web}" != "mlflow" ]; then
  exec uvicorn deploy.render.web:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers
fi
if [ -z "${DATABASE_URL:-}" ]; then echo "[start] DATABASE_URL 없음 — MLflow 서비스를 띄울 수 없습니다"; exit 1; fi
export MLFLOW_TRACKING_URI="$(python -c 'import os,re;print(re.sub(r"^postgres(ql)?://","postgresql+psycopg://",os.environ["DATABASE_URL"]))')"
# 수주 파이프라인만 등록돼 있어 기록 단계 메모리 최대 약 257MB
# 기록은 서버보다 먼저, 끝까지 마친 뒤 프로세스가 내려가 메모리를 돌려준다
kedro run --pipeline=ship_orders_track || echo "[start] MLflow 기록 실패 — 화면은 계속 띄웁니다"
# MLflow 앱 + 읽기 전용 필터를 한 uvicorn 프로세스로 (mlflow server CLI 는 프로세스가 여러 개라 512MB 초과)
exec uvicorn deploy.render.mlflow_proxy:app --host 0.0.0.0 --port "${PORT:-10000}" --proxy-headers
