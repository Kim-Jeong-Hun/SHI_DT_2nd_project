"""파이프라인 등록 — Airflow DAG 태스크가 이 이름으로 `kedro run --pipeline=<이름>` 을 호출한다.

이 저장소는 선박 수주 예측 프로젝트만 다룬다(북극항로 과제는 진행하지 않음).
"""
from kedro.pipeline import Pipeline

from shi_dt.pipelines import ship_orders, ship_pulse


def register_pipelines() -> dict[str, Pipeline]:
    pipes = {
        "ship_orders": ship_orders.create_pipeline(),   # 선박 수주 예측 운영 보고서 갱신 (서빙 /ship/forecast)
        "ship_orders_preprocess": ship_orders.create_preprocess_pipeline(),   # 원자료 → processed → 마스터 (팀 Drive 전체 사본에서만)
        "ship_orders_track": ship_orders.create_track_pipeline(),   # 보고서 → MLflow 실험 ship_orders 기록만 (Render 시작 시)
        "ship_pulse": ship_pulse.create_pipeline(),   # Ship Pulse 최종 설정 재학습 → 서비스 형식 결과 · MLflow 등록
        "ship_pulse_track": ship_pulse.create_track_pipeline(),   # 결과 → MLflow 실험 ship_pulse 기록 · 모델 등록만
    }
    return {**pipes, "__default__": pipes["ship_orders"]}
