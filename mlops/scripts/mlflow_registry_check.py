"""MLflow 실험 ship_pulse 의 최근 실행과 등록 모델(alias)을 출력한다 — Airflow 시연 DAG 확인 단계."""
import mlflow
from mlflow import MlflowClient

c = MlflowClient()
exp = c.get_experiment_by_name("ship_pulse")
runs = c.search_runs([exp.experiment_id], order_by=["attributes.start_time DESC"], max_results=6)
print("최근 실행:")
for r in runs:
    m = r.data.metrics
    print(f"  {r.info.run_name:<16} test_ase={m.get('test_ase', float('nan')):,.0f}  q4={m.get('q4', float('nan')):,.0f}  run={r.info.run_id[:8]}")
print("등록 모델:")
for rm in c.search_registered_models():
    if rm.name.startswith("ship_pulse_"):
        vs = c.search_model_versions(f"name='{rm.name}'")
        print(f"  {rm.name:<22} 최신 v{max(int(v.version) for v in vs)}  alias={rm.aliases}")
