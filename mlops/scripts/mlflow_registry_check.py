"""MLflow 등록 확인 — 선종 5개 모델(ship_pulse_<선종>)의 alias production 이 모두 있고,
그 버전들이 지금 결과(results.json 지문 results_sha)로 만든 모델이어야 통과한다.

Airflow 시연 DAG 의 마지막 단계. 하나라도 어긋나면 종료 코드 1로 끝나 작업이 실패한다.
results.json 이 없으면 지문 비교는 건너뛰고 alias 존재만 본다.
"""
import sys
from pathlib import Path

from mlflow import MlflowClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from shi_dt.pipelines.ship_pulse import service_nodes as N  # noqa: E402
from shi_dt.pipelines.ship_pulse.spec import SHIPS  # noqa: E402


def main(client=None, digest=None) -> int:
    c = client or MlflowClient()
    if digest is None and (N.OUT / "results.json").exists():
        digest = N.results_digest()
    exp = c.get_experiment_by_name("ship_pulse")
    if exp is None:
        print("실패: MLflow 실험 ship_pulse 가 없어요")
        return 1
    runs = c.search_runs([exp.experiment_id], order_by=["attributes.start_time DESC"], max_results=6)
    print("최근 실행:")
    for r in runs:
        m = r.data.metrics
        print(f"  {r.info.run_name:<16} test_ase={m.get('test_ase', float('nan')):,.0f}  재학습4분기={m.get('retrained_q4', float('nan')):,.0f}  run={r.info.run_id[:8]}")
    probs = N.verify_registry(c, list(SHIPS), digest)
    for vid in SHIPS:
        name = f"ship_pulse_{vid}"
        if not any(p.startswith(name + ":") for p in probs):
            print(f"  {name:<22} production → v{c.get_model_version_by_alias(name, 'production').version}")
    if probs:
        print("실패:\n  " + "\n  ".join(probs))
        return 1
    print(f"통과: 선종 {len(SHIPS)}개 모델 · alias production 확인" + (f" · 모두 results_sha={digest}" if digest else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
