"""Container-ship direct forecasts from a fixed, three-month-old data cutoff.

The origin is the decision month.  At origin C, every input observation and
training label is capped at D=C-3 months.  Horizon h targets D+h, not C+h.
Historical external series are revised snapshots, not archived release vintages;
the common three-month delay is an explicit proxy for their availability.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .modeling import MODELS, TARGET, metrics, model_for
from .operational_forecast import month_end
from .order_availability import PROCESSED_ORDER_LAG_COLUMNS


PUBLICATION_LAG_MONTHS = 3
HORIZONS = tuple(range(1, 7))
ORDER_LAGS = {1: "수주용량_확보월", 2: "수주용량_확보월1개월전",
              3: "수주용량_확보월2개월전"}
MIN_TRAIN = 36
MIN_REMOVAL_GAIN = 0.01  # fold 평균 sMAPE 1%p 개선
MIN_IMPROVED_FOLDS = 2  # 3개 연도 중 최소 2개 연도 개선
CORRELATION_GROUPS = {
    "미국TPU": (
        "미국TPU(EPUTRADE 무역정책불확실성지수)",
        "미국TPU(Caldara 무역정책불확실성지수)",
    ),
    "세계거시": (
        "세계_실질상품수출_백만2010USD_계절조정",
        "세계_실질상품수입_백만2010USD_계절조정",
        "세계_산업생산_백만2010USD_계절조정",
    ),
    "지정학": (
        "GPR(세계지정학위험지수)",
        "GPRT(지정학위협지수)",
        "GPRA(지정학행동지수)",
    ),
}


def select_correlated_features(train: pd.DataFrame, features: list[str]
                               ) -> tuple[list[str], dict[str, dict]]:
    """각 예측 시점의 학습 라벨만으로 후보군별 |상관계수| 최대 1개를 선택."""
    selected = list(features)
    choices = {}
    for group, candidates in CORRELATION_GROUPS.items():
        present = [name for name in candidates if name in selected]
        if not present:
            continue
        correlations = {name: train[name].corr(train["실제"]) for name in present}
        # 상관계수가 정의되지 않는 상수열은 최하위로 두고 원래 순서로 동률 해소.
        winner = max(present, key=lambda name: (
            abs(correlations[name]) if pd.notna(correlations[name]) else -1.0,
            -present.index(name),
        ))
        selected = [name for name in selected if name not in present or name == winner]
        choices[group] = {
            "선택": winner,
            "학습상관계수": (float(correlations[winner])
                       if pd.notna(correlations[winner]) else None),
        }
    return selected, choices


def data_cutoff(origin: pd.Timestamp, lag: int = PUBLICATION_LAG_MONTHS) -> pd.Timestamp:
    """2024-10 decision -> 2024-07 latest observation month."""
    return (pd.Timestamp(origin).to_period("M") - lag).to_timestamp()


def _published_by(published: pd.Series, observation: pd.Timestamp,
                  origin: pd.Timestamp) -> bool:
    """A known late publication overrides the three-month proxy."""
    date = published.get(observation.strftime("%Y-%m"), pd.NaT)
    return pd.isna(date) or pd.Timestamp(date) <= origin


def asof_inputs(frame: pd.DataFrame, external: list[str], published: pd.Series,
                origin: pd.Timestamp) -> dict:
    """Read preprocessed calendar lags at the cutoff month, not future rows."""
    origin = month_end(pd.Timestamp(origin))
    cutoff = data_cutoff(origin)
    result = {"예측기준일": origin, "데이터마감월": cutoff}
    for distance, name in ORDER_LAGS.items():
        observed = cutoff - pd.DateOffset(months=distance - 1)
        source_column = (TARGET if distance == 1
                         else PROCESSED_ORDER_LAG_COLUMNS[distance - 1])
        result[name] = (float(frame.at[cutoff, source_column])
                        if cutoff in frame.index and pd.notna(frame.at[cutoff, source_column])
                        and _published_by(published, observed, origin) else np.nan)
    for name in external:
        result[name] = (float(frame.at[cutoff, name])
                        if cutoff in frame.index and pd.notna(frame.at[cutoff, name])
                        else np.nan)
    return result


def direct_grid(frame: pd.DataFrame, external: list[str], published: pd.Series,
                first_origin: str = "2015-01", last_origin: str = "2026-10") -> pd.DataFrame:
    """One row per decision month and horizon, retaining absent future labels."""
    rows = []
    for origin_month in pd.date_range(first_origin, last_origin, freq="MS"):
        inputs = asof_inputs(frame, external, published, origin_month)
        for horizon in HORIZONS:
            target = inputs["데이터마감월"] + pd.DateOffset(months=horizon)
            actual = (float(frame.at[target, TARGET]) if target in frame.index
                      and pd.notna(frame.at[target, TARGET]) else np.nan)
            rows.append({**inputs, "선행개월": horizon, "목표월": target,
                         "실제": actual, "목표게시일": published.get(target.strftime("%Y-%m"), pd.NaT)})
    return pd.DataFrame(rows).set_index(["예측기준일", "선행개월"]).sort_index()


def eligible_training(grid: pd.DataFrame, horizon: int, origin: pd.Timestamp,
                      features: list[str]) -> pd.DataFrame:
    """For each direct model, only labels already available at this origin."""
    origin = month_end(pd.Timestamp(origin))
    cutoff = data_cutoff(origin)
    history = grid.xs(horizon, level="선행개월")
    history = history.loc[(history.index < origin) & history["목표월"].le(cutoff)]
    date = pd.to_datetime(history["목표게시일"], errors="coerce")
    history = history.loc[date.isna() | date.le(origin)]
    return history.dropna(subset=["실제", *features])


def predict_at(grid: pd.DataFrame, horizon: int, origin: pd.Timestamp,
               features: list[str], model: str, *, min_train: int = MIN_TRAIN) -> dict | None:
    origin = month_end(pd.Timestamp(origin))
    if (origin, horizon) not in grid.index:
        return None
    row = grid.loc[(origin, horizon)]
    if row[features].isna().any():
        return None
    train = eligible_training(grid, horizon, origin, features)
    if len(train) < min_train:
        return None
    fitted_features, correlated_choices = select_correlated_features(train, features)
    estimator = model_for(model, 42)
    estimator.fit(train[fitted_features], train["실제"])
    return {"예측기준일": origin, "데이터마감월": row["데이터마감월"],
            "목표월": row["목표월"], "선행개월": horizon,
            "실제": float(row["실제"]) if pd.notna(row["실제"]) else np.nan,
            "예측": max(0.0, float(estimator.predict(row[fitted_features].to_frame().T)[0])),
            "학습행수": len(train), "학습라벨종료월": train["목표월"].max(),
            "최신입력관측월": row["데이터마감월"],
            "실제투입피처": fitted_features, "상관선택": correlated_choices}


def select_candidates(grid: pd.DataFrame, candidates: dict[str, list[str]],
                      horizon: int, *, first: str = "2022-01",
                      last: str = "2024-12", selection_cutoff: str = "2024-10",
                      fold_years: tuple[int, int, int] = (2022, 2023, 2024)
                      ) -> tuple[dict, list[dict]]:
    """Select on three paired, past-only walk-forward folds."""
    if len(fold_years) != 3 or sorted(fold_years) != list(fold_years):
        raise ValueError("변수 선택에는 시간순 3개 연도 fold가 필요합니다")
    rows = grid.xs(horizon, level="선행개월")
    cutoff = pd.Timestamp(selection_cutoff)
    first_diagnostic_origin = month_end(cutoff + pd.DateOffset(months=3))
    origins = rows.loc[first:last].index
    origins = [origin for origin in origins
               if pd.notna(rows.at[origin, "실제"])
               and rows.at[origin, "목표월"] <= cutoff
               and (pd.isna(rows.at[origin, "목표게시일"])
                    or rows.at[origin, "목표게시일"] <= first_diagnostic_origin)
               and all(not rows.loc[origin, cols].isna().any() for cols in candidates.values())]
    # Filter once so every combination is compared on exactly the same months.
    origins = [origin for origin in origins if all(
        len(eligible_training(grid, horizon, origin, cols)) >= MIN_TRAIN
        for cols in candidates.values())]
    folds = {str(year): [origin for origin in origins if origin.year == year]
             for year in fold_years}
    if any(len(months) < 3 for months in folds.values()):
        raise ValueError(f"h+{horizon}: paired development origins insufficient: "
                         f"{ {year: len(months) for year, months in folds.items()} }")
    results = []
    for group, features in candidates.items():
        for model in MODELS:
            fold_scores = {}
            for year, months in folds.items():
                predicted = [predict_at(grid, horizon, origin, features, model)
                             for origin in months]
                if any(row is None for row in predicted):
                    raise AssertionError("Paired forecast origin unexpectedly unavailable")
                fold_scores[year] = metrics([row["실제"] for row in predicted],
                                            [row["예측"] for row in predicted])["sMAPE"]
            values = np.array(list(fold_scores.values()))
            results.append({"변수조합": group, "피처목록": features, "모형": model,
                            "fold별sMAPE": fold_scores,
                            "fold별평가월": {year: len(months) for year, months in folds.items()},
                            "평균sMAPE": float(values.mean()),
                            "표준편차": float(values.std(ddof=1))})
    ranked = sorted(results, key=lambda row: (row["평균sMAPE"], row["표준편차"],
                                          len(row["피처목록"]), row["변수조합"], row["모형"]))
    # Start with the full candidate set and remove one feature per accepted step.
    # Every trial uses the same monthly as-of validation origins. Stop when no
    # removal gains >=1 percentage point on average and improves >=2 of 3 years.
    chosen = ranked[0]
    starting_choice = chosen.copy()
    removal_path = []
    removal_trials = []
    for step in range(1, len(starting_choice["피처목록"])):
        alternatives = []
        for removed in chosen["피처목록"]:
            features = [name for name in chosen["피처목록"] if name != removed]
            if not set(features).intersection(ORDER_LAGS.values()):
                continue
            scores = {}
            for year, months in folds.items():
                predicted = [predict_at(grid, horizon, origin, features, chosen["모형"])
                             for origin in months]
                scores[year] = metrics([row["실제"] for row in predicted],
                                       [row["예측"] for row in predicted])["sMAPE"]
            values = np.array(list(scores.values()))
            improvement = {year: chosen["fold별sMAPE"][year] - value
                           for year, value in scores.items()}
            alternatives.append({"변수조합": chosen["변수조합"], "피처목록": features,
                                 "모형": chosen["모형"], "제거변수": removed,
                                 "fold별sMAPE": scores,
                                 "fold별개선": improvement,
                                 "fold별평가월": chosen["fold별평가월"],
                                 "평균sMAPE": float(values.mean()),
                                 "표준편차": float(values.std(ddof=1))})
        ranked.extend(alternatives)
        approved = [row for row in alternatives
                    if chosen["평균sMAPE"] - row["평균sMAPE"] >= MIN_REMOVAL_GAIN
                    and sum(delta > 0 for delta in row["fold별개선"].values())
                    >= MIN_IMPROVED_FOLDS]
        next_choice = (min(approved, key=lambda row: (row["평균sMAPE"], row["표준편차"],
                                                    row["제거변수"])) if approved else None)
        for alternative in alternatives:
            removal_trials.append({
                "단계": step, "제거변수": alternative["제거변수"],
                "시작피처목록": chosen["피처목록"],
                "제거후피처목록": alternative["피처목록"],
                "제거전평균sMAPE": chosen["평균sMAPE"],
                "제거후평균sMAPE": alternative["평균sMAPE"],
                "평균개선_퍼센트포인트": 100 * (chosen["평균sMAPE"]
                                              - alternative["평균sMAPE"]),
                "fold별개선_퍼센트포인트": {
                    year: 100 * value for year, value in alternative["fold별개선"].items()},
                "채택": alternative is next_choice,
            })
        if next_choice is None:
            break
        removal_path.append({"단계": step, "제거변수": next_choice["제거변수"],
                             "개선_퍼센트포인트": 100 * (chosen["평균sMAPE"]
                                                       - next_choice["평균sMAPE"]),
                             "fold별개선_퍼센트포인트": {
                                 year: 100 * value
                                 for year, value in next_choice["fold별개선"].items()}})
        chosen = next_choice
    # Final-set ablation, on exactly the same as-of folds. The earlier removal
    # path is not a complete importance measure when the last step was accepted.
    final_ablation = []
    ablation_sets = []
    grouped = set()
    for group, candidates in CORRELATION_GROUPS.items():
        present = [name for name in candidates if name in chosen["피처목록"]]
        if len(present) > 1:
            ablation_sets.append((f"{group} 계열 전체", present))
            grouped.update(present)
    ablation_sets.extend((name, [name]) for name in chosen["피처목록"]
                         if name not in grouped)
    for label, removed_columns in ablation_sets:
        remaining = [name for name in chosen["피처목록"] if name not in removed_columns]
        if not remaining:
            continue
        existing = next((item for item in ranked
                         if item["모형"] == chosen["모형"]
                         and item["피처목록"] == remaining), None)
        if existing is None:
            scores = {}
            for year, months in folds.items():
                predicted = [predict_at(grid, horizon, origin, remaining, chosen["모형"])
                             for origin in months]
                scores[year] = metrics([row["실제"] for row in predicted],
                                       [row["예측"] for row in predicted])["sMAPE"]
        else:
            scores = existing["fold별sMAPE"]
        changes = {year: 100 * (scores[year] - chosen["fold별sMAPE"][year])
                   for year in folds}
        final_ablation.append({"피처": label, "제거피처목록": removed_columns,
                               "제거시평균sMAPE": float(np.mean(list(scores.values()))),
                               "제거시sMAPE증가_퍼센트포인트": float(np.mean(list(changes.values()))),
                               "fold별증가_퍼센트포인트": changes})
    return {**chosen, "시작모형후보": starting_choice,
            "fold별기준월": {year: [month.strftime("%Y-%m") for month in months]
                           for year, months in folds.items()},
            "단계별제거시험": removal_trials,
            "변수제거경로": removal_path,
            "최종피처제거중요도": final_ablation}, ranked


def evaluate_period(grid: pd.DataFrame, horizon: int, choice: dict,
                    first: str = "2025-01", last: str = "2026-10") -> tuple[list[dict], list[str]]:
    rows, skipped = [], []
    candidates = grid.xs(horizon, level="선행개월").loc[first:last]
    for origin, row in candidates.iterrows():
        if pd.isna(row["실제"]):
            continue
        result = predict_at(grid, horizon, origin, choice["피처목록"], choice["모형"])
        if result is None:
            skipped.append(origin.strftime("%Y-%m"))
        else:
            rows.append(result)
    return rows, skipped
