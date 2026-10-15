"""Ship Pulse 운영 파이프라인 — 팀 서비스(shipulse.vercel.app)의 선종별 최종 설정으로 다시 학습하고 MLflow 에 등록한다.

  ship_pulse        선종 5개 × (마스터 → CCF 시차 → 변수 거르기 → 롤링 검증 17창 → Test 24개월 → 다음 분기 예측)
                    → results.json · notebook_forecasts.json(서비스 형식) · comparison.json(팀 값 대조) → MLflow
  ship_pulse_track  이미 만든 결과를 MLflow 에만 기록(Render MLflow 서비스 시작 때)
"""
from functools import partial, update_wrapper

from kedro.pipeline import Pipeline, node

from . import nodes as N
from .spec import SHIPS


def _bind(fn, vid):
    f = partial(fn, vid=vid)
    update_wrapper(f, fn)
    return f


def create_pipeline() -> Pipeline:
    pipes, outs = [], []
    for vid in SHIPS:
        sub = Pipeline([
            node(partial(N.load_master, vid), None, "master", name="load_master"),
            node(N.lag_features, "master", "lagged", name="ccf_lag_features"),
            node(_bind(N.select_features, vid), "lagged", "selected", name="select_features"),
            node(_bind(N.rolling_validation, vid), ["lagged", "selected"], "validation", name="rolling_validation"),
            node(_bind(N.test_evaluation, vid), ["lagged", "selected"], "test", name="test_24m"),
            node(_bind(N.forecast, vid), ["lagged", "selected", "validation", "test"], "forecast", name="forecast_next_quarter"),
            node(partial(N.assemble_vessel, vid), ["lagged", "selected", "validation", "test", "forecast"], "result", name="assemble"),
        ], namespace=f"sp_{vid}", outputs={"result": f"sp_{vid}_result"})
        pipes.append(sub)
        outs.append(f"sp_{vid}_result")
    tail = Pipeline([node(N.export_results, outs, "ship_pulse_export", name="export_results"),
                     node(N.track_mlflow, "ship_pulse_export", "ship_pulse_tracking", name="track_mlflow_register")])
    return sum(pipes, Pipeline([])) + tail


def create_track_pipeline() -> Pipeline:
    return Pipeline([node(N.track_mlflow, None, "ship_pulse_tracking", name="ship_pulse_track_only")])
