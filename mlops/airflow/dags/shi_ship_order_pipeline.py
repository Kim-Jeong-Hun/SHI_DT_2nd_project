"""
선박 수주 예측 보고서 월간 갱신 (서버 아키텍처.png 제어 흐름 그대로)
  WSL Airflow → docker compose up → docker exec shi-app kedro run --pipeline=ship_orders
  → Kedro ship_orders (팀 2026_독립검증.py 를 노드 96개로 분해): 공통 입력 → 선종 5 × (평가 프레임 → 고정 선택 → 2026 평가 ·
    1·3·6개월 직접 선행예측 · 운영 모델) → 보고서 → data/01_raw/ship 반영 → 운영 모델 저장 → MLflow 실행 · Models 기록
  → 서빙 /ship/forecast 가 다음 요청부터 반영
수주 월보는 보통 다음 달 말에 게시되므로 매월 5일에 돈다.
"""
import os
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = os.environ.get("SHI_PROJECT_DIR", "/mnt/c/Users/Molly/projects/shi-dt-mlops")
APP = "shi-app"

with DAG(
    dag_id="shi_ship_order_pipeline",
    description="선박 수주 예측: 팀 파이프라인 재실행 → 운영 보고서 갱신 → 서빙 확인",
    schedule="0 6 5 * *",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["shi", "ship_orders", "kedro"],
) as dag:
    containers_up = BashOperator(task_id="docker_containers_up",
                                 bash_command=f"cd {PROJECT_DIR} && docker compose up -d --wait --wait-timeout 300")
    kedro_ship = BashOperator(task_id="kedro_ship_orders", bash_command=f"docker exec {APP} kedro run --pipeline=ship_orders")
    check_api = BashOperator(task_id="check_serving_api",
                             bash_command=f"docker exec {APP} curl -fs 'http://localhost:8000/ship/meta' || echo 'serving off (SERVING_ENABLED)'")
    containers_up >> kedro_ship >> check_api
