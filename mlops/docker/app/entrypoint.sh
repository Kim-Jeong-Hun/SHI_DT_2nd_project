#!/usr/bin/env bash
# Ubuntu 컨테이너 상주 프로세스
#   1) (선택) 추론/서빙 API  : uvicorn :8000  — SERVING_ENABLED=1 일 때
#   2) MLflow 서버           : :5000
#        메타데이터(실험·런·모델 레지스트리) → DB 컨테이너(PostgreSQL)
#        아티팩트(모델 파일·그림)          → 공유 볼륨 /workspace/data/mlflow_artifacts
# Kedro 파이프라인은 WSL의 Airflow가 `docker exec shi-app kedro run ...` 으로 실행한다.
set -euo pipefail

if [ "${SERVING_ENABLED:-1}" = "1" ]; then
  uvicorn deploy.render.web:app --host 0.0.0.0 --port 8000 &   # 수주 전용 서빙(Render 배포본과 같은 앱)
fi

exec mlflow server \
    --backend-store-uri "${MLFLOW_BACKEND_STORE_URI}" \
    --artifacts-destination /workspace/data/mlflow_artifacts \
    --serve-artifacts \
    --host 0.0.0.0 \
    --port 5000
