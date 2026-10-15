#!/usr/bin/env bash
# WSL2(Ubuntu 24.04) 안에 Apache Airflow 설치 — 서버 아키텍처.png 의 "WSL 서버 > Apache Airflow 설치"
#   - Airflow는 Docker 컨테이너가 아니라 WSL에 직접 설치 (그림 그대로)
#   - 메타데이터 DB는 Docker의 DB 컨테이너(PostgreSQL, localhost:5432 / DB명 airflow)
#   - 공식 constraints 파일로 의존성 고정 (Airflow 3.3.2 / Python 3.12, 2026-09-30 존재 확인)
# 사용: 프로젝트 루트에서  bash airflow/install_airflow_wsl.sh
set -euo pipefail

AIRFLOW_VERSION=3.3.2
PYTHON_VERSION=3.12
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
export AIRFLOW_HOME="${AIRFLOW_HOME:-$HOME/airflow}"

set -a; source "$PROJECT_DIR/.env"; set +a

sudo apt-get update && sudo apt-get install -y python3-venv python3-pip
python3 -m venv "$HOME/airflow-venv"
source "$HOME/airflow-venv/bin/activate"
pip install --upgrade pip
pip install "apache-airflow[postgres]==${AIRFLOW_VERSION}" \
  --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-${AIRFLOW_VERSION}/constraints-${PYTHON_VERSION}.txt"

mkdir -p "$AIRFLOW_HOME"
cat > "$AIRFLOW_HOME/airflow.env" <<EOF
export AIRFLOW_HOME=$AIRFLOW_HOME
export AIRFLOW__DATABASE__SQL_ALCHEMY_CONN=postgresql+psycopg2://${POSTGRES_USER}:${POSTGRES_PASSWORD}@localhost:5432/${AIRFLOW_DB}
export AIRFLOW__CORE__DAGS_FOLDER=$PROJECT_DIR/airflow/dags
# 리스너 플러그인: 상태가 바뀔 때마다 실행 현황을 Neon(AIRFLOW_STATUS_DB_URL, 프로젝트 .env)에 남겨 웹 관제 '워크플로' 탭에 보여준다
export AIRFLOW__CORE__PLUGINS_FOLDER=$PROJECT_DIR/airflow/plugins
export AIRFLOW__CORE__LOAD_EXAMPLES=False
# Ubuntu는 localhost를 ::1(IPv6)로 먼저 풀고 api-server는 IPv4(0.0.0.0)만 들어 태스크 러너가 연결 거부됨 → IPv4로 고정
export AIRFLOW__CORE__EXECUTION_API_SERVER_URL=http://127.0.0.1:8080/execution/
export SHI_PROJECT_DIR=$PROJECT_DIR
EOF
source "$AIRFLOW_HOME/airflow.env"

airflow db migrate
echo "설치 완료. 실행:  source ~/airflow-venv/bin/activate && source $AIRFLOW_HOME/airflow.env && airflow standalone"
echo "웹 UI: http://localhost:8080 (첫 실행 시 관리자 비밀번호가 터미널/파일에 출력됨)"
