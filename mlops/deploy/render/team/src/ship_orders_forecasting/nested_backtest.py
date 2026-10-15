"""Annual outer walk-forward replay with past-only feature selection.

For each decision year, freeze feature/model selection at its first month-end.
The selected specification stays fixed within that year; the estimator is
refitted each month using only labels available by that month's cutoff.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .modeling import metrics
from .publication_lag_forecast import (
    MIN_TRAIN, data_cutoff, direct_grid, eligible_training, month_end,
    predict_at, select_candidates,
)


def annual_replay(
    frame: pd.DataFrame,
    external: list[str],
    published: pd.Series,
    candidates: dict[str, list[str]],
    *,
    years: tuple[int, ...] = (2023, 2024, 2025, 2026),
    horizon: int = 6,
) -> dict:
    """Repeat the same selection rule before each annual outer test block."""
    if horizon != 6:
        raise ValueError("이 재현 평가는 자료 기준 h+6만 대상으로 합니다")
    if not years or sorted(set(years)) != list(years):
        raise ValueError("바깥 평가 연도는 중복 없이 시간순이어야 합니다")
    grid = direct_grid(frame, external, published)
    horizon_rows = grid.xs(horizon, level="선행개월")
    last_origin = horizon_rows.index.max()
    summaries, monthly_rows = [], []

    for year in years:
        freeze = month_end(pd.Timestamp(year=year, month=1, day=1))
        cutoff = data_cutoff(freeze)
        inner_years = tuple(range(year - 3, year))
        inner_kwargs = {
            "first": f"{inner_years[0]}-01",
            "last": f"{inner_years[-1]}-12",
            "selection_cutoff": cutoff.strftime("%Y-%m"),
            "fold_years": inner_years,
        }
        origins = pd.date_range(f"{year}-01", f"{year}-12", freq="MS")
        origins = [month_end(month) for month in origins if month_end(month) <= last_origin]
        if not origins:
            continue

        try:
            chosen, _ = select_candidates(grid, candidates, horizon, **inner_kwargs)
        except ValueError as error:
            summaries.append({
                "기준연도": year, "선택기준일": freeze.strftime("%Y-%m-%d"),
                "선택시최신자료월": cutoff.strftime("%Y-%m"),
                "상태": f"내부 fold 부족: {error}", "기준월수": len(origins),
                "평가월수": 0, "모형": None, "피처목록": [],
                "내부fold별sMAPE": {}, "sMAPE": np.nan,
                "MAE": np.nan, "RMSE": np.nan,
            })
            continue

        # The entire selection must be reproducible at the outer year's
        # first origin, including the inner folds' validation labels.
        for months in chosen["fold별기준월"].values():
            for month in months:
                inner_origin = month_end(pd.Timestamp(month + "-01"))
                row = grid.loc[(inner_origin, horizon)]
                release = row["목표게시일"]
                if (inner_origin >= freeze or row["목표월"] > cutoff
                        or (pd.notna(release) and release > freeze)):
                    raise AssertionError(f"{year}: 변수 선택에 미래 목표값이 포함되었습니다")

        scored = []
        for origin in origins:
            row = horizon_rows.loc[origin]
            missing = [name for name in chosen["피처목록"] if pd.isna(row[name])]
            forecast = predict_at(grid, horizon, origin, chosen["피처목록"], chosen["모형"])
            actual = float(row["실제"]) if pd.notna(row["실제"]) else np.nan
            if forecast is None:
                train_count = len(eligible_training(grid, horizon, origin, chosen["피처목록"]))
                status = "입력 결측" if missing else (
                    "학습행 부족" if train_count < MIN_TRAIN else "예측 불가")
                prediction = np.nan
            else:
                train_count = forecast["학습행수"]
                prediction = float(forecast["예측"])
                status = "평가" if pd.notna(actual) else "실제 미관측"
            result = {
                "기준연도": year,
                "예측기준월": origin.strftime("%Y-%m"),
                "데이터마감월": row["데이터마감월"].strftime("%Y-%m"),
                "목표월": row["목표월"].strftime("%Y-%m"),
                "실제": actual, "예측": prediction,
                "상태": status, "결측입력": missing,
                "학습행수": train_count,
            }
            monthly_rows.append(result)
            if status == "평가":
                scored.append(result)

        score = metrics([row["실제"] for row in scored],
                        [row["예측"] for row in scored]) if scored else None
        summaries.append({
            "기준연도": year, "선택기준일": freeze.strftime("%Y-%m-%d"),
            "선택시최신자료월": cutoff.strftime("%Y-%m"),
            "상태": "12개월 기준연도" if len(origins) == 12 else "진행 중인 기준연도",
            "기준월수": len(origins),
            "목표실제관측월수": sum(pd.notna(horizon_rows.at[origin, "실제"]) for origin in origins),
            "평가월수": len(scored),
            "모형": chosen["모형"], "피처목록": chosen["피처목록"],
            "제거피처": [item["제거변수"] for item in chosen["변수제거경로"]],
            "내부fold별sMAPE": chosen["fold별sMAPE"],
            "내부fold별월수": {name: len(months)
                             for name, months in chosen["fold별기준월"].items()},
            "sMAPE": score["sMAPE"] if score else np.nan,
            "MAE": score["MAE"] if score else np.nan,
            "RMSE": score["RMSE"] if score else np.nan,
        })
    return {"연도별": summaries, "월별": monthly_rows}
