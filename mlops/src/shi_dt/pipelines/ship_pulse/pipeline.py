"""Ship Pulse 운영 파이프라인 — 서비스(대시보드)와 같은 모델 · 같은 데이터로 재학습하고 MLflow 에 등록한다.

  ship_pulse        선종 5개 × (서비스 런타임 데이터 · 모델 사양 → Test 24개월 평가 → 7~12월 재예측 · 최종 모델 저장)
                    → results.json · notebook_forecasts.json(대시보드 값 그대로) · comparison.json(대시보드 vs 재학습) → MLflow
  ship_pulse_track  이미 만든 결과를 MLflow 에만 기록(Render MLflow 서비스 시작 때)
"""
from functools import partial

from kedro.pipeline import Pipeline, node

from . import service_nodes as N
from .spec import SHIPS


def create_pipeline() -> Pipeline:
    pipes, outs = [], []
    for vid in SHIPS:
        sub = Pipeline([
            node(partial(N.load_service, vid), None, "service", name="load_service_runtime"),
            node(N.test_service, "service", "test", name="test_24m"),
            node(N.forecast_service, "service", "forecast", name="retrain_forecast"),
            node(partial(N.assemble, vid), ["service", "test", "forecast"], "result", name="assemble"),
        ], namespace=f"sp_{vid}", outputs={"result": f"sp_{vid}_result"})
        pipes.append(sub)
        outs.append(f"sp_{vid}_result")
    tail = Pipeline([node(N.export_results, outs, "ship_pulse_export", name="export_results"),
                     node(N.track_mlflow, "ship_pulse_export", "ship_pulse_tracking", name="track_mlflow_register")])
    return sum(pipes, Pipeline([])) + tail


def create_track_pipeline() -> Pipeline:
    return Pipeline([node(N.track_mlflow, None, "ship_pulse_tracking", name="ship_pulse_track_only")])
