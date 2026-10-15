"""Direct month-end ship-order forecasts with an explicit information boundary.

Order-report dates are checked against the forecast origin. Older reports with
no recoverable publication date may be used only as a labelled t-3 proxy in
retrospective validation; a live forecast never uses an undated order report.
External monthly series have no observation-level publication dates in this
project, so they are shown in the input audit but are not used by this strict
operational model. No cargo-volume feature is used.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .modeling import MODELS, TARGET, metrics, model_for
from .order_availability import publication_dates


WINDOWS = {1: "확정수주_최근1개월", 2: "확정수주_최근2개월누적",
           3: "확정수주_최근3개월누적", 6: "확정수주_최근6개월누적"}
POINT_LAGS = {lag: f"확정수주_{lag}개월차단일월" for lag in (1, 2, 3)}
BASELINE = "확정수주_최근3개월평균"
BASELINE_MODEL = "최근3개월 확정수주 평균"
MIN_TRAIN = 36


def month_end(month: pd.Timestamp) -> pd.Timestamp:
    """Last Monday-Friday of the month; holidays need an explicit calendar."""
    calendar_end = pd.Timestamp(month).to_period("M").to_timestamp("M")
    return pd.offsets.BMonthEnd().rollback(calendar_end)


def order_history(frame: pd.DataFrame, published: pd.Series, origin: pd.Timestamp,
                  *, allow_undated_history: bool) -> pd.DataFrame:
    """Rows available by the given month-end; never turn absence into zero."""
    origin = pd.Timestamp(origin).normalize()
    records = []
    for month, value in frame[TARGET].items():
        if pd.isna(value) or month > origin:
            continue
        date = published.get(month.strftime("%Y-%m"), pd.NaT)
        if pd.notna(date):
            if pd.Timestamp(date) > origin:
                continue
            evidence = "게시일확인"
        elif allow_undated_history and month <= (origin - pd.DateOffset(months=2)).replace(day=1):
            evidence = "과거t-3근사"
        else:
            continue
        records.append({"관측월": month, "수주용량": float(value),
                        "게시일": pd.Timestamp(date) if pd.notna(date) else pd.NaT,
                        "가용근거": evidence})
    if not records:
        return pd.DataFrame(columns=["수주용량", "게시일", "가용근거"],
                            index=pd.DatetimeIndex([], name="관측월"))
    return pd.DataFrame(records).set_index("관측월").sort_index()


def origin_features(frame: pd.DataFrame, published: pd.Series, origin: pd.Timestamp,
                    *, allow_undated_history: bool, point_lags: bool = False) -> dict:
    history = order_history(frame, published, origin,
                            allow_undated_history=allow_undated_history)
    candidates = POINT_LAGS if point_lags else WINDOWS
    result = {"예측기준일": pd.Timestamp(origin), "최신수주관측월": pd.NaT,
              "최신수주게시일": pd.NaT, "가용근거": "확정수주없음",
              BASELINE: np.nan, f"{BASELINE}_게시일확인": False,
              **{name: np.nan for name in candidates.values()},
              **{f"{name}_게시일확인": False for name in candidates.values()}}
    if history.empty:
        return result
    latest = history.index.max()
    result.update({"최신수주관측월": latest,
                   "최신수주게시일": history.at[latest, "게시일"],
                   "가용근거": history.at[latest, "가용근거"]})
    # A gap inside a window is not an observed zero. All component months
    # must have values *and* satisfy the same as-of publication boundary.
    for size, name in candidates.items():
        if point_lags:
            expected = latest - pd.DateOffset(months=size - 1)
            if expected in history.index:
                result[name] = float(history.at[expected, "수주용량"])
                result[f"{name}_게시일확인"] = (
                    history.at[expected, "가용근거"] == "게시일확인"
                )
            continue
        expected = pd.date_range(latest - pd.DateOffset(months=size - 1),
                                 latest, freq="MS")
        if expected.isin(history.index).all():
            result[name] = float(history.loc[expected, "수주용량"].sum())
            result[f"{name}_게시일확인"] = bool(
                history.loc[expected, "가용근거"].eq("게시일확인").all()
            )
    baseline_months = pd.date_range(latest - pd.DateOffset(months=2), latest, freq="MS")
    if baseline_months.isin(history.index).all():
        result[BASELINE] = float(history.loc[baseline_months, "수주용량"].mean())
        result[f"{BASELINE}_게시일확인"] = bool(
            history.loc[baseline_months, "가용근거"].eq("게시일확인").all()
        )
    return result


def direct_frame(frame: pd.DataFrame, published: pd.Series, horizon: int,
                 last_target: str = "2027-03", *, point_lags: bool = False) -> pd.DataFrame:
    if horizon not in (1, 3, 6):
        raise ValueError("선행개월은 1·3·6 중 하나여야 합니다")
    months = pd.date_range(frame.index.min(), pd.Timestamp(last_target), freq="MS")
    rows = []
    for target_month in months:
        # For target t and horizon h, origin is the end of t-h. E.g. Dec-26,
        # h=3 -> Sep-30; Mar-27, h=6 -> Sep-30.
        origin = month_end(target_month - pd.DateOffset(months=horizon))
        features = origin_features(frame, published, origin,
                                   allow_undated_history=origin < pd.Timestamp("2026-09-01"),
                                   point_lags=point_lags)
        rows.append({"목표월": target_month, "선행개월": horizon,
                     TARGET: float(frame.at[target_month, TARGET])
                     if target_month in frame.index and pd.notna(frame.at[target_month, TARGET])
                     else np.nan, **features})
    return pd.DataFrame(rows).set_index("목표월")


def _fit_predict(data: pd.DataFrame, month: pd.Timestamp, feature: str,
                 model: str, published: pd.Series, *, min_train: int) -> dict | None:
    if month not in data.index or pd.isna(data.at[month, TARGET]) or pd.isna(data.at[month, feature]):
        return None
    origin = data.at[month, "예측기준일"]
    available = order_history(data, published, origin, allow_undated_history=True)
    train = data.loc[(data.index < month) & data.index.isin(available.index), [TARGET, feature]].dropna()
    if len(train) < min_train:
        return None
    if model == BASELINE_MODEL:
        prediction = float(data.at[month, BASELINE])
    else:
        estimator = model_for(model, 42)
        estimator.fit(train[[feature]], train[TARGET])
        prediction = max(0.0, float(estimator.predict(data.loc[[month], [feature]])[0]))
    return {"목표월": month, "예측기준일": origin, "실제": float(data.at[month, TARGET]),
            "예측": prediction, "학습관측월": len(train), "학습종료월": train.index.max(),
            "가용근거": "게시일확인" if data.at[month, f"{feature}_게시일확인"]
                        else "과거t-3근사"}


def _train_rows(data: pd.DataFrame, month: pd.Timestamp, feature: str,
                published: pd.Series) -> pd.DataFrame:
    origin = data.at[month, "예측기준일"]
    available = order_history(data, published, origin, allow_undated_history=True)
    return data.loc[(data.index < month) & data.index.isin(available.index),
                    [TARGET, feature]].dropna()


def select_direct(data: pd.DataFrame, published: pd.Series, horizon: int,
                  *, min_train: int = MIN_TRAIN,
                  point_lags: bool = False) -> tuple[dict, list[dict]]:
    first_origin = month_end(pd.Timestamp("2026-01-01") - pd.DateOffset(months=horizon))
    available = order_history(data, published, first_origin,
                              allow_undated_history=True)
    if available.empty:
        raise ValueError("첫 보류월 이전의 사용 가능한 수주실적이 없습니다")
    selection_end = available.index.max()
    if selection_end >= pd.Timestamp("2026-01-01"):
        raise AssertionError("2026년 라벨은 변수·모형 선택에 사용할 수 없습니다")
    selection_months = data.index[(data.index >= pd.Timestamp("2022-01-01"))
                                  & (data.index <= selection_end)
                                  & data[TARGET].notna()]
    candidates = POINT_LAGS if point_lags else WINDOWS
    # The three-month average remains a benchmark, not an eligible order feature
    # in the container-ship point-lag prototype.
    choices = ([] if point_lags else [(BASELINE, BASELINE_MODEL)]) + [
        (feature, model) for feature in candidates.values() for model in MODELS
    ]
    # Paired candidate scores must use identical target months. A six-month
    # history gap removes that month from *every* combination.
    common = []
    for month in selection_months:
        if all(pd.notna(data.at[month, feature]) and
               len(_train_rows(data, month, feature, published)) >= min_train
               for feature in ([*candidates.values()] if point_lags
                               else [BASELINE, *candidates.values()])):
            common.append(month)
    folds = {str(y): [month for month in common if month.year == y]
             for y in (2022, 2023, 2024, 2025)}
    if any(len(months) < 3 for months in folds.values()):
        raise ValueError(f"{horizon}개월 선행: 개발 연도별 공통 평가월 부족: "
                         f"{ {year: len(months) for year, months in folds.items()} }")
    candidates = []
    for feature, model in choices:
        fold_scores = {}
        for year, months in folds.items():
            rows = [_fit_predict(data, month, feature, model, published,
                                 min_train=min_train) for month in months]
            fold_scores[year] = metrics([row["실제"] for row in rows],
                                         [row["예측"] for row in rows])["sMAPE"]
        values = np.array(list(fold_scores.values()))
        candidates.append({"피처": feature, "모형": model,
                           "fold별sMAPE": fold_scores,
                           "평균sMAPE": float(values.mean()),
                           "표준편차": float(values.std(ddof=1)),
                           "fold별평가월": {year: len(months) for year, months in folds.items()}})
    selected = min(candidates, key=lambda row: (row["평균sMAPE"], row["표준편차"],
                                                 row["피처"], row["모형"]))
    ranked = sorted(candidates, key=lambda row: (row["평균sMAPE"], row["표준편차"],
                                                row["피처"], row["모형"]))
    return {**selected, "선행개월": horizon,
            "변수선택종료월": selection_end.strftime("%Y-%m"),
            "운영대체우선순위": [{"피처": row["피처"], "모형": row["모형"]}
                         for row in ranked]}, candidates


def test_direct(data: pd.DataFrame, published: pd.Series, choice: dict,
                *, min_train: int = MIN_TRAIN) -> dict:
    months = data.loc["2026-01":"2026-08"].index
    observed = [month for month in months if pd.notna(data.at[month, TARGET])]
    rows = [_fit_predict(data, month, choice["피처"], choice["모형"], published,
                         min_train=min_train) for month in observed]
    rows = [row for row in rows if row is not None]
    if not rows:
        return {"평가월수": 0, "월별예측": [], "월별sMAPE": None,
                "미평가월": [month.strftime("%Y-%m") for month in observed]}
    score = metrics([row["실제"] for row in rows], [row["예측"] for row in rows])
    confirmed = [row for row in rows if row["가용근거"] == "게시일확인"]
    confirmed_score = metrics([row["실제"] for row in confirmed],
                              [row["예측"] for row in confirmed])["sMAPE"] if confirmed else None
    return {"평가월수": len(rows), "월별sMAPE": score["sMAPE"],
            "월별RMSE": score["RMSE"],
            "게시일확인평가월수": len(confirmed),
            "게시일확인월sMAPE": confirmed_score,
            "미평가월": [month.strftime("%Y-%m") for month in observed
                     if month not in {row["목표월"] for row in rows}],
            "월별예측": [{key: value.strftime("%Y-%m-%d") if isinstance(value, pd.Timestamp)
                       and key == "예측기준일" else value.strftime("%Y-%m")
                       if isinstance(value, pd.Timestamp) else value
                       for key, value in row.items()} for row in rows]}


def future_direct(data: pd.DataFrame, published: pd.Series, choice: dict,
                  origin: str = "2026-09-30", *, min_train: int = MIN_TRAIN) -> dict:
    origin = pd.Timestamp(origin)
    horizon = choice["선행개월"]
    target = (origin.to_period("M") + horizon).to_timestamp()
    identity = {"목표월": target.strftime("%Y-%m"),
                "예측기준일": origin.strftime("%Y-%m-%d"), "선행개월": horizon}
    if target not in data.index:
        raise ValueError("목표월이 선행예측 데이터 밖입니다")
    if data.at[target, "예측기준일"] != origin:
        raise ValueError("예측기준일과 목표월·선행개월이 맞지 않습니다")
    history = order_history(data, published, origin, allow_undated_history=False)
    ranked = choice.get("운영대체우선순위", [{"피처": choice["피처"], "모형": choice["모형"]}])
    feasible = None
    for candidate in ranked:
        feature = candidate["피처"]
        if pd.isna(data.at[target, feature]) or not data.at[target, f"{feature}_게시일확인"]:
            continue
        train = data.loc[data.index.isin(history.index) & (data.index < target),
                         [TARGET, feature]].dropna()
        if len(train) >= min_train:
            feasible = candidate
            break
    if feasible is None:
        return {**identity, "상태": "게시일확인 입력 또는 학습행 부족", "예측": None}
    feature = feasible["피처"]
    model = feasible["모형"]
    if model == BASELINE_MODEL:
        predicted = float(data.at[target, BASELINE])
    else:
        estimator = model_for(model, 42)
        estimator.fit(train[[feature]], train[TARGET])
        predicted = max(0.0, float(estimator.predict(data.loc[[target], [feature]])[0]))
    return {**identity, "예측": predicted, "학습관측월": len(train),
            "운영피처": feature, "운영모형": model,
            "입력부족대체": feature != choice["피처"] or model != choice["모형"],
            "입력수주관측월": data.at[target, "최신수주관측월"].strftime("%Y-%m"),
            "입력수주게시일": data.at[target, "최신수주게시일"].strftime("%Y-%m-%d")
            if pd.notna(data.at[target, "최신수주게시일"]) else None,
            "상태": "게시일확인"}
