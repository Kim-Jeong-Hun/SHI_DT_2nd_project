#!/usr/bin/env bash
# DB 컨테이너 최초 기동 시 1회 실행 (postgres 공식 이미지의 /docker-entrypoint-initdb.d 규칙)
#   - APP_DB    : 서비스 운영 데이터 (사용자·예측 로그·모델 버전)
#   - MLFLOW_DB : MLflow 실험 추적 / 모델 레지스트리 메타데이터
#   - AIRFLOW_DB: WSL에 설치한 Airflow의 메타데이터
set -e  # 이 스크립트는 postgres 엔트리포인트가 source 할 수 있어 -u·pipefail 은 쓰지 않음

for db in "$APP_DB" "$MLFLOW_DB" "$AIRFLOW_DB"; do
  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres \
       -c "CREATE DATABASE \"$db\";"
done

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$APP_DB" \
     -f /docker-entrypoint-initdb.d/sql/app_schema.sql
