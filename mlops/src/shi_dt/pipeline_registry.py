"""파이프라인 등록 — Airflow DAG 태스크가 이 이름으로 `kedro run --pipeline=<이름>` 을 호출한다.

SHI_PIPELINES=ship 이면 선박 수주 파이프라인만 등록한다 — 북극항로(nsr · arctic)의 무거운 의존성(matplotlib · pyproj 등)을
불러오지 않아 Render 무료 인스턴스(512MB)에서 시작 시 MLflow 기록을 가볍게 돌린다. 기본값은 전체 등록(Airflow · Kedro-Viz).
"""
import os

from kedro.pipeline import Pipeline

from shi_dt.pipelines import ship_orders


def register_pipelines() -> dict[str, Pipeline]:
    ship = {
        "ship_orders": ship_orders.create_pipeline(),   # 선박 수주 예측 운영 보고서 갱신 (서빙 /ship/forecast)
        "ship_orders_preprocess": ship_orders.create_preprocess_pipeline(),   # 원자료 → processed → 마스터 (팀 Drive 전체 사본에서만)
        "ship_orders_track": ship_orders.create_track_pipeline(),   # 보고서 → MLflow 실험 ship_orders 기록만 (Render 시작 시)
    }
    if os.environ.get("SHI_PIPELINES") == "ship":
        return {**ship, "__default__": ship["ship_orders"]}
    from shi_dt.pipelines import arctic, nsr, ops

    data, eda, train = nsr.create_pipelines()
    full = data + eda + train
    return {
        "nsr_data": data,      # 원천 → 정제 일별 테이블
        "nsr_eda": eda,        # EDA 그림 + 통계 검정
        "nsr_train": train,    # 학습·평가 + MLflow 기록
        "nsr": full,
        "ops_logs": ops.create_pipeline(),   # 관제 로그 → 병목·항차 표 (운항 빅데이터)
        "arctic": arctic.create_pipeline(),   # 관문 개방 경보 학습 (서빙 /arctic/predict 가 쓰는 모델)
        **ship,
        "__default__": full,
    }
