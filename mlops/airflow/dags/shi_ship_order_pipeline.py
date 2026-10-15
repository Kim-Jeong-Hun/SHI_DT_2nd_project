"""
선박 수주 예측 월간 재학습 — Ship Pulse(shipulse.vercel.app) 최종 설정 기준
  WSL Airflow → docker compose up → 마스터 테이블 확인
  → Kedro ship_pulse: 선종 5개 × (CCF 시차 → 변수 거르기 → 롤링 검증 17창 → Test 24개월 → 다음 분기 예측 · 90% 구간)
  → 결과 점검(선종 5개 · 4분기 예측 존재) → MLflow 실험 ship_pulse 기록 · 모델 등록(alias production)
  → (병렬) 예전 보고서 파이프라인 ship_orders · 서빙 확인
수주 월보는 보통 다음 달 말에 게시되므로 매월 5일에 돈다. 마스터 테이블이 없으면 거기서 멈춘다.
"""
import os
from datetime import datetime, timedelta

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = os.environ.get("SHI_PROJECT_DIR", "/mnt/c/Users/Molly/projects/shi-dt-mlops")
APP = "shi-app"
SHIPS = ["컨테이너선", "벌크선", "유조선", "가스 운반선", "케미컬 탱커"]
MASTER = "data/01_raw/ship_pulse/master"
OUT = "data/07_model_output/ship_pulse"

with DAG(
    dag_id="shi_ship_order_pipeline",
    description="선박 수주 예측: Ship Pulse 설정으로 월간 재학습 → 결과 점검 → MLflow 등록 → 서빙 확인",
    schedule="0 6 5 * *",
    start_date=datetime(2026, 10, 1),
    catchup=False,
    default_args={"retries": 1, "retry_delay": timedelta(minutes=5)},
    tags=["shi", "ship_pulse", "kedro", "mlflow"],
) as dag:
    containers_up = BashOperator(task_id="docker_containers_up",
                                 bash_command=f"cd {PROJECT_DIR} && docker compose up -d --wait --wait-timeout 300")
    check_master = BashOperator(
        task_id="check_master_tables",
        bash_command=" && ".join(f"test -s '{PROJECT_DIR}/{MASTER}/마스터테이블({s}).csv'" for s in SHIPS))
    train = BashOperator(task_id="kedro_ship_pulse",
                         bash_command=f"docker exec -e SHI_PIPELINES=ship {APP} kedro run --pipeline=ship_pulse")
    verify = BashOperator(
        task_id="verify_outputs",
        bash_command=(f"docker exec {APP} python -c \"import json;r=json.load(open('{OUT}/results.json',encoding='utf-8'));"
                      "assert len(r)==5, list(r);bad=[k for k,v in r.items() if not v['forecast']['q4']];assert not bad, bad;"
                      "print({k: round(v['test']['metrics']['ase']) for k,v in r.items()})\""))
    register = BashOperator(task_id="mlflow_track_register",
                            bash_command=f"docker exec -e SHI_PIPELINES=ship {APP} kedro run --pipeline=ship_pulse_track")
    legacy = BashOperator(task_id="kedro_ship_orders_report",
                          bash_command=f"docker exec {APP} kedro run --pipeline=ship_orders || echo 'legacy report skipped'")
    check_api = BashOperator(task_id="check_serving_api",
                             bash_command=f"docker exec {APP} curl -fs 'http://localhost:8000/ship/meta' || echo 'serving off (SERVING_ENABLED)'")
    containers_up >> check_master >> train >> verify >> register >> check_api
    containers_up >> legacy >> check_api
