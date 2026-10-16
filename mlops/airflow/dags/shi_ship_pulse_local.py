"""
Ship Pulse 재학습 — Docker 없이 로컬에서 시연할 때 쓰는 DAG
  WSL Airflow → (Windows 쪽 Python) Kedro ship_pulse → MLflow(sqlite: data/09_tracking/mlflow.db) 기록 · 모델 등록
  → 결과 점검 → MLflow 등록 확인(5개 모델 · alias production, 하나라도 없으면 실패) (결과는 mlops/data 아래에만 쓰고, frontend · backend · deploy 파일은 건드리지 않는다)
운영 DAG(shi_ship_order_pipeline)는 같은 순서를 docker exec 로 컨테이너 안에서 돌린다. 이 DAG는 수동 실행 전용.
"""
import os
from datetime import datetime

from airflow.providers.standard.operators.bash import BashOperator
from airflow.sdk import DAG

PROJECT_DIR = os.environ.get("SHI_PROJECT_DIR", "/mnt/c/Users/Molly/projects/shi-dt-mlops")   # mlops 폴더(WSL 경로)
SHIPS = ["컨테이너선", "벌크선", "유조선", "가스 운반선", "케미컬 탱커"]
OUT = f"{PROJECT_DIR}/data/07_model_output/ship_pulse"


def ps(cmd: str) -> str:
    """WSL 에서 프로젝트 폴더(/mnt/c/...)로 이동한 뒤 Windows PowerShell 로 명령을 실행한다 — PowerShell 은 그 폴더에서 시작한다(Kedro · MLflow 는 Windows Python)."""
    # bash 큰따옴표 안이라 PowerShell 의 $ 는 \$ 로 넘긴다 · 파이프 뒤에서도 실패 코드가 살아 있게 pipefail
    env = ("\\$env:PYTHONUTF8='1';\\$env:SHI_PIPELINES='ship';\\$env:KEDRO_DISABLE_TELEMETRY='true';"
           "\\$env:MLFLOW_DISABLE_AGENT_HINT='1';\\$env:MLFLOW_TRACKING_URI='sqlite:///data/09_tracking/mlflow.db';")
    return f'set -o pipefail; cd "{PROJECT_DIR}" && powershell.exe -NoProfile -Command "{env} {cmd}; exit \\$LASTEXITCODE" | tr -d "\\r"'


with DAG(
    dag_id="shi_ship_pulse_local",
    description="Ship Pulse 재학습 시연: Airflow → Kedro → MLflow (Docker 없이)",
    schedule=None,
    start_date=datetime(2026, 10, 1),
    catchup=False,
    tags=["shi", "ship_pulse", "kedro", "mlflow", "local"],
) as dag:
    check_master = BashOperator(   # 서비스 런타임 마스터(팀 저장소: deploy/render/custom_runtime · 이 저장소: vendor 사본)
        task_id="check_master_tables",
        bash_command=(f"D={PROJECT_DIR}/deploy/render/custom_runtime/data/master; [ -d \"$D\" ] || D={PROJECT_DIR}/vendor/ship_pulse_service/custom_runtime/data/master; "
                      "n=$(ls \"$D\"/마스터테이블*.csv | wc -l); echo \"서비스 런타임 마스터 $n개: $D\"; [ \"$n\" -eq 5 ]"))
    train = BashOperator(task_id="kedro_ship_pulse", bash_command=ps("kedro run --pipeline=ship_pulse"))
    verify = BashOperator(
        task_id="verify_outputs",
        bash_command=(f"python3 -c \"import json;r=json.load(open('{OUT}/results.json',encoding='utf-8'));"
                      "assert len(r)==5, list(r);bad=[k for k,v in r.items() if not v['forecast']['retrained']];assert not bad, bad;"
                      f"import os;assert os.path.exists('{OUT}/retrained_forecasts.json') and os.path.exists('{OUT}/dashboard_reference.json');"
                      "[print(v['vesselName'],'| 변수',len(v['features']),'| Test ASE',round(v['test']['metrics']['ase']),"
                      "'| 대시보드와 차이(%)',list(v['forecast']['gapPct'].values())) for v in r.values()]\""))
    registry = BashOperator(task_id="mlflow_registry_check", bash_command=ps("python scripts/mlflow_registry_check.py"))
    check_master >> train >> verify >> registry
