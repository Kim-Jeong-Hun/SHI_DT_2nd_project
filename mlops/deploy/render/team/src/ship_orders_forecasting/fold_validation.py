"""Chronological, equal-weight fold scores for notebook feature selection.

Every prediction is fitted using rows no later than the publication-aware
t-2 or t-3 order boundary. Fold
scores are kept separate: pooling all monthly errors would let a long fold
hide deterioration in another period.
"""

from __future__ import annotations

import pandas as pd

from .modeling import metrics, walk_forward


def chronological_folds(months, frequency: str) -> dict[str, pd.DatetimeIndex]:
    """Group preselected forecast months into calendar years or quarters."""
    if frequency not in {"Y", "Q"}:
        raise ValueError("frequency must be Y or Q")
    index = pd.DatetimeIndex(months).sort_values()
    if index.has_duplicates:
        raise ValueError("forecast months must be unique")
    return {
        str(period): index[index.to_period(frequency) == period]
        for period in index.to_period(frequency).unique()
    }


def evaluate_folds(
    data: pd.DataFrame,
    folds: dict[str, pd.DatetimeIndex],
    features: list[str],
    model: str,
    *,
    min_train: int = 48,
    seed: int = 42,
) -> tuple[dict, pd.DataFrame]:
    """Evaluate one fixed combination on identical months in every fold."""
    if len(folds) < 2:
        raise ValueError("at least two chronological folds are required")
    params = {"minimum_train_months": min_train, "random_seed": seed}
    rows = []
    for fold, months in folds.items():
        months = pd.DatetimeIndex(months)
        if months.empty:
            raise ValueError(f"{fold}: empty fold")
        predicted = walk_forward(data, months, features, model, params)
        if not predicted.index.equals(months):
            missing = months.difference(predicted.index)
            raise ValueError(f"{fold}: missing prediction months {missing.tolist()}")
        score = metrics(predicted["실제"], predicted["예측"])
        rows.append({"fold": fold, "검증관측월": len(months), **score})
    detail = pd.DataFrame(rows)
    smape_scores = detail["sMAPE"].to_numpy(dtype=float)
    summary = {
        "sMAPE": float(smape_scores.mean()),
        "sMAPE표준편차": float(smape_scores.std(ddof=1)),
        "MAE": float(detail["MAE"].mean()),
        "RMSE": float(detail["RMSE"].mean()),
        "R2": float(detail["R2"].mean()),
        "폴드수": len(detail),
        "검증관측월": int(detail["검증관측월"].sum()),
    }
    return summary, detail


def fold_improvement(before: pd.DataFrame, after: pd.DataFrame) -> pd.DataFrame:
    """Positive percentage points mean the changed combination improved."""
    paired = before.merge(after, on="fold", suffixes=("_전", "_후"), validate="one_to_one")
    if len(paired) != len(before) or len(paired) != len(after):
        raise ValueError("fold sets differ between candidate combinations")
    if not paired["검증관측월_전"].equals(paired["검증관측월_후"]):
        raise ValueError("candidate combinations used different forecast months")
    return pd.DataFrame({
        "fold": paired["fold"],
        "검증관측월": paired["검증관측월_전"],
        "변경전sMAPE": paired["sMAPE_전"],
        "변경후sMAPE": paired["sMAPE_후"],
        "개선_퍼센트포인트": 100 * (paired["sMAPE_전"] - paired["sMAPE_후"]),
    })
