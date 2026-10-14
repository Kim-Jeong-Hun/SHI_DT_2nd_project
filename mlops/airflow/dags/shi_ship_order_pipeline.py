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

# 환경 변수가 없으면 이 파일 기준 mlops 폴더(airflow/dags 의 두 단계 위)
PROJECT_DIR = os.environ.get("SHI_PROJECT_DIR") or os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
APP = "shi-app"
CHECK_API = r"""
set -euo pipefail
if [ "$(docker exec "$APP" printenv SERVING_ENABLED || echo 1)" != "1" ]; then
  echo "SERVING_ENABLED != 1 → 서빙 확인 건너뜀"; exit 99
fi
docker exec "$APP" curl -fsS --retry 5 --retry-delay 3 --retry-all-errors --max-time 10   'http://localhost:8000/ship/forecast?ship=%EC%BB%A8%ED%85%8C%EC%9D%B4%EB%84%88%EC%84%A0&horizon=3' > /dev/null
docker exec "$APP" curl -fsS --retry 5 --retry-delay 3 --retry-all-errors --max-time 10 'http://localhost:8000/ship/meta'   | docker exec -i -e RUN_START="$RUN_START" "$APP" python3 -c '
import json, os, sys
from datetime import datetime
m = json.load(sys.stdin)
n = len(m.get("선종", []))
assert n == 5, f"선종 {n}개 (5개여야 함)"
rep = datetime.fromisoformat(m["보고서수정시각"]); run = datetime.fromisoformat(os.environ["RUN_START"])
assert rep >= run, f"보고서가 이번 실행 전 것: 보고서 {rep} < 실행 시작 {run}"
print(f"서빙 정상: 선종 {n}개 · 보고서 {rep}")
'
"""

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
    # 서빙 확인: 실패는 실패로 남긴다(예전에는 `|| echo` 때문에 API가 죽어도 DAG가 성공했다).
    #   SERVING_ENABLED != 1 → exit 99 = Airflow '건너뜀'(skipped) · 응답 없음/5개 선종 아님/보고서가 이번 실행 전 것 → 실패
    check_api = BashOperator(
        task_id="check_serving_api",
        bash_command=CHECK_API,
        env={"APP": APP, "RUN_START": "{{ dag_run.start_date.isoformat() }}"},
        append_env=True,
        retries=0,
    )
    containers_up >> kedro_ship >> check_api
