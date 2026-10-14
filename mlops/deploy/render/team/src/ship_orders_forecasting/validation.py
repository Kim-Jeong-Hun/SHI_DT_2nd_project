"""Annual outer evaluation of the existing lag/feature/model selection process.

This optional audit reads the persisted causal lag table. Each year's selection
sees only labels available at its first forecast origin (January minus the
publication-aware two- or three-month order lag).
The selected configuration stays fixed within that year; monthly fitting expands.
Original data vintages are not reconstructed, so this remains a historical audit.
"""

import logging

import pandas as pd

from .modeling import (
    InsufficientHistoryError, ROLLING_BASELINE, ROLLING_BASELINE_MODEL, TARGET,
    _as_indexed, metrics, select_lags, select_model, walk_forward,
)
from .order_availability import AVAILABLE_LAG_COLUMN


LOGGER = logging.getLogger(__name__)
REPORT_COLUMNS = [
    "선종", "평가연도", "상태", "사유", "선택가능실적종료", "내부검증시작설정",
    "내부검증월수", "내부검증sMAPE", "모형", "피처수", "가용실적월수", "평가월수",
    "미평가월", "외부sMAPE", "기준선sMAPE", "기준선대비개선_pp", "외부RMSE",
    "기준선RMSE", "최초학습월수", "최종학습월수",
]
PREDICTION_COLUMNS = [
    "선종", "평가연도", "기준월", "모형", "실제", "예측", "기준선예측",
    "학습관측월", "학습종료월", "선택가능실적종료",
]


def annual_validation(data: pd.DataFrame, policies: pd.DataFrame, params: dict,
                      audit: dict, ship_type: str):
    years = [int(year) for year in audit["evaluation_years"]]
    configured_start = pd.Timestamp(params["validation_start"])
    configured_end = pd.Timestamp(params["holdout_start"])
    lookback = 12 * (configured_end.year - configured_start.year) + configured_end.month - configured_start.month
    if not years or len(years) != len(set(years)) or lookback < 1:
        raise ValueError("Audit years must be unique and the inner lookback positive")
    indexed = _as_indexed(data)
    reports, predictions, selections = [], [], {}
    for year in sorted(years):
        start = pd.Timestamp(year=year, month=1, day=1)
        end = start + pd.DateOffset(years=1)
        lag = indexed.loc[start, AVAILABLE_LAG_COLUMN] if (
            AVAILABLE_LAG_COLUMN in indexed and start in indexed.index
        ) else 3
        if pd.isna(lag):
            reports.append({"선종": ship_type, "평가연도": year, "상태": "생략",
                            "사유": "연초 수주 공표 가용성이 확인되지 않음"})
            continue
        cutoff = start - pd.DateOffset(months=int(lag))
        fold_params = {**params, "holdout_start": start.strftime("%Y-%m"),
                       "validation_start": (start - pd.DateOffset(months=lookback)).strftime("%Y-%m"),
                       "holdout_order_lag": int(lag)}
        observed_months = indexed.loc[
            (indexed.index >= start) & (indexed.index < end) & indexed[TARGET].notna()
        ].index
        row = {"선종": ship_type, "평가연도": year,
               "선택가능실적종료": cutoff.strftime("%Y-%m"),
               "내부검증시작설정": fold_params["validation_start"],
               "가용실적월수": len(observed_months), "평가월수": 0}
        if len(observed_months) < 2:
            reports.append({**row, "상태": "생략", "사유": "평가연도의 관측 실적이 2개월 미만"})
            continue

        # Physically exclude unconfirmed/future labels from both selection calls.
        history = indexed.loc[:cutoff].reset_index()
        history["기준월"] = history["기준월"].dt.strftime("%Y-%m")
        LOGGER.info("%s %s audit: selecting with labels through %s", ship_type, year, cutoff.date())
        try:
            lags = select_lags(history, policies, fold_params)
            _, _, candidates, _, selected = select_model(history, lags, fold_params, ship_type)
        except InsufficientHistoryError as error:
            LOGGER.info("%s %s audit skipped: %s", ship_type, year, error)
            reports.append({**row, "상태": "생략", "사유": str(error)})
            continue

        selections[str(year)] = {
            "상태": "선택완료", "설정": fold_params, "최종선택": selected,
            "선택시차": lags.loc[lags["선택"]].to_dict(orient="records"),
            "모형후보": candidates.to_dict(orient="records"),
        }
        # No feature or model reselection using any result from the outer year.
        evaluation_data = indexed.loc[indexed.index < end]
        result = walk_forward(evaluation_data, observed_months,
                              selected["피처목록"], selected["모형"], fold_params)
        baseline = walk_forward(evaluation_data, observed_months,
                                [ROLLING_BASELINE], ROLLING_BASELINE_MODEL, fold_params)
        common = result.index.intersection(baseline.index)
        row.update({"내부검증월수": selected["검증관측월"],
                    "내부검증sMAPE": selected["검증sMAPE"], "모형": selected["모형"],
                    "피처수": len(selected["피처목록"]), "평가월수": len(common),
                    "미평가월": ",".join(month.strftime("%Y-%m") for month in observed_months.difference(common))})
        if len(common) < 2:
            reports.append({**row, "상태": "생략", "사유": "모형과 기준선의 공통 평가월이 2개월 미만"})
            continue
        paired = result.loc[common].copy()
        paired["기준선예측"] = baseline.loc[common, "예측"]
        model_metrics = metrics(paired["실제"], paired["예측"])
        baseline_metrics = metrics(paired["실제"], paired["기준선예측"])
        reports.append({**row, "상태": "완료", "사유": "",
                        "외부sMAPE": model_metrics["sMAPE"],
                        "기준선sMAPE": baseline_metrics["sMAPE"],
                        "기준선대비개선_pp": 100 * (baseline_metrics["sMAPE"] - model_metrics["sMAPE"]),
                        "외부RMSE": model_metrics["RMSE"], "기준선RMSE": baseline_metrics["RMSE"],
                        "최초학습월수": int(paired["학습관측월"].iloc[0]),
                        "최종학습월수": int(paired["학습관측월"].iloc[-1])})
        paired = paired.reset_index()
        paired["선종"], paired["평가연도"], paired["모형"] = ship_type, year, selected["모형"]
        paired["선택가능실적종료"] = cutoff.strftime("%Y-%m")
        for column in ("기준월", "학습종료월"):
            paired[column] = paired[column].dt.strftime("%Y-%m")
        predictions.append(paired[PREDICTION_COLUMNS])
        selections[str(year)]["상태"] = "완료"
        LOGGER.info("%s %s audit done: sMAPE %.1f%%, baseline %.1f%%, %s months",
                    ship_type, year, 100 * model_metrics["sMAPE"],
                    100 * baseline_metrics["sMAPE"], len(common))
    return (pd.DataFrame(reports).reindex(columns=REPORT_COLUMNS),
            pd.concat(predictions, ignore_index=True) if predictions else pd.DataFrame(columns=PREDICTION_COLUMNS),
            {"선종": ship_type, "검증설정": audit,
             "주의": "원자료 당시 빈티지는 미복원. 이미 관찰한 과거 구간의 절차 검증이며 신규 블라인드 테스트가 아님.",
             "연도별선택": selections})


def summarize_validation_audit(*inputs):
    reports, snapshots = inputs[:5], inputs[5:]
    if len(reports) != 5 or len(snapshots) != 5:
        raise ValueError("Expected five annual reports and five selection snapshots")
    summary = pd.concat(reports, ignore_index=True).sort_values(["선종", "평가연도"])
    stability = []
    for snapshot in snapshots:
        completed = {year: fold for year, fold in snapshot["연도별선택"].items() if fold["상태"] == "완료"}
        features = sorted({feature for fold in completed.values() for feature in fold["최종선택"]["피처목록"]})
        for feature in features:
            selected_years = [year for year, fold in completed.items() if feature in fold["최종선택"]["피처목록"]]
            stability.append({"선종": snapshot["선종"], "피처_시차포함": feature,
                              "선택연도": ",".join(selected_years), "선택횟수": len(selected_years),
                              "평가연도수": len(completed), "선택비율": len(selected_years) / len(completed),
                              "해석": "연도 1개: 안정성 판단 불가" if len(completed) < 2 else "재선택 빈도이며 인과적 중요도가 아님"})
    columns = ["선종", "피처_시차포함", "선택연도", "선택횟수", "평가연도수", "선택비율", "해석"]
    return summary, pd.DataFrame(stability, columns=columns)
