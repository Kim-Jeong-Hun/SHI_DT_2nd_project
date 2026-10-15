"""Calendar-lag monthly walk-forward selection and evaluation.

Every forecast of month t uses observed orders through t-2, or t-3 when the
t-2 observation is absent. Recent 1/2/3/6-month order totals are compared on
identical development months without public release-date restrictions.
The 2025+ holdout is never consulted while choosing lags, features, or model family.
"""

from __future__ import annotations

import json
from functools import lru_cache

import numpy as np
import pandas as pd
from sklearn.compose import TransformedTargetRegressor
from sklearn.base import BaseEstimator, RegressorMixin, clone
from sklearn.cross_decomposition import PLSRegression
from sklearn.decomposition import PCA
from sklearn.ensemble import (ExtraTreesRegressor, GradientBoostingRegressor,
                              HistGradientBoostingRegressor, RandomForestRegressor,
                              VotingRegressor)
from sklearn.linear_model import ElasticNet, HuberRegressor, LinearRegression, Ridge, QuantileRegressor
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import FeatureUnion, make_pipeline
from sklearn.preprocessing import PolynomialFeatures, SplineTransformer, StandardScaler
from sklearn.svm import SVR

from .legacy import legacy_module
from .order_availability import AVAILABLE_LAG_COLUMN
from .order_availability import ORDER_POINT_LAG_COLUMNS


MODELS = ("1차 선형회귀", "2차 다항 Ridge", "랜덤 포레스트")
TARGET = "수주용량"
TARGET_LAG = "수주용량_2개월전"
PUBLISHED_LABEL_COLUMN = "수주실적게시일"
ORDER_WINDOWS = {
    1: TARGET_LAG,
    2: "수주용량_최근2개월누적",
    3: "수주용량_최근3개월누적",
    6: "수주용량_최근6개월누적",
}
ROLLING_BASELINE = "확정수주용량_최근3개월평균"
ROLLING_BASELINE_MODEL = "최근3개월 확정수주 평균"


class InsufficientHistoryError(ValueError):
    """A chronological fold has too few observations for model selection."""


def selection_history(data: pd.DataFrame, params: dict) -> pd.DataFrame:
    """Limit selection labels to those available at the first holdout origin."""
    indexed = _as_indexed(data)
    first_holdout = pd.Timestamp(params["holdout_start"])
    lag = params.get("holdout_order_lag")
    if lag is None and (
        AVAILABLE_LAG_COLUMN in indexed and first_holdout in indexed.index
    ):
        lag = indexed.loc[first_holdout, AVAILABLE_LAG_COLUMN]
    if lag is None:
        lag = 3
    if pd.isna(lag):
        raise ValueError("첫 보류월의 수주 공표 가용성이 확인되지 않습니다")
    cutoff = first_holdout - pd.DateOffset(months=int(lag))
    return indexed.loc[:cutoff]


def feature_groups(ship_type: str) -> dict[str, list[str]]:
    rules = legacy_module("마스터테이블_생성")
    return {
        "commodities": [*rules.COMMON_COMMODITY_COLUMNS, *rules.SHIP_COMMODITY_COLUMNS[ship_type]],
        "bunker": [rules.BUNKER_SALES_COLUMN],
        "prices": [
            *([rules.SHIP_PRICE_COLUMN] if ship_type in rules.SHIP_PRICE_TYPES else []),
            *rules.MARKET_PRICE_FEATURE_COLUMNS.get(ship_type, []),
        ],
        "freight": [*rules.SHIP_FREIGHT_COLUMNS.get(ship_type, []),
                    *rules.ROUTE_FREIGHT_COLUMNS_BY_SHIP.get(ship_type, [])],
        "fleet": list(rules.FLEET_FEATURE_COLUMNS_BY_SHIP.get(ship_type, [])),
        "cargo": rules.SHIP_CARGO_VOLUME_COLUMNS[ship_type],
        "risk": rules.RISK_COLUMNS,
        "trade": rules.TRADE_POLICY_COLUMNS,
        "additional": rules.COMPLETE_PERIOD_CANDIDATES.get(ship_type, []),
    }


def lagged_data(master: pd.DataFrame, ship_type: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    groups = feature_groups(ship_type)
    rules = legacy_module("마스터테이블_생성")
    first_order_feature = rules.order_feature_columns_for(ship_type)[1]
    required = list(dict.fromkeys(["기준월", "수주용량단위", TARGET,
                                   AVAILABLE_LAG_COLUMN, first_order_feature,
                                   *rules.feature_columns_for(ship_type)]))
    missing = set(required).difference(master.columns)
    if missing:
        raise KeyError(f"{ship_type} 마스터 테이블 누락 컬럼: {sorted(missing)}")
    if not master["수주용량단위"].eq(rules.TARGET_UNITS[ship_type]).all():
        raise ValueError(f"{ship_type} 수주용량단위가 일치하지 않습니다.")
    data = master[required].copy()
    data["기준월"] = pd.to_datetime(data["기준월"], format="%Y-%m")
    data = data.set_index("기준월").sort_index()
    if data.index.duplicated().any() or len(data) != len(pd.date_range(data.index.min(), data.index.max(), freq="MS")):
        raise ValueError(f"{ship_type} 기준월이 중복되거나 연속적이지 않습니다.")
    # The benchmark follows the same calendar t-2/t-3 choice.
    # Missing order months are not assumed to be zero.
    recent_two = data[TARGET].shift(2).rolling(3, min_periods=1).mean()
    recent_three = data[TARGET].shift(3).rolling(3, min_periods=1).mean()
    data[ROLLING_BASELINE] = np.where(
        data[AVAILABLE_LAG_COLUMN].eq(2), recent_two,
        np.where(data[AVAILABLE_LAG_COLUMN].eq(3), recent_three, np.nan),
    )
    policies = []
    for group in ("commodities", "bunker", "prices", "freight", "fleet", "cargo", "risk", "trade"):
        for feature in groups[group]:
            allowed = (1, 2, 3, 6) if group in {"commodities", "freight", "fleet"} else (2, 3, 6)
            for months in allowed:
                data[f"{feature}_{months}개월전"] = data[feature].shift(months)
            policies.append({"원본피처": feature, "그룹": group, "허용시차": ",".join(map(str, allowed))})
    return data.reset_index().assign(기준월=lambda frame: frame["기준월"].dt.strftime("%Y-%m")), pd.DataFrame(policies)


def smape(actual, predicted) -> float:
    """Symmetric mean absolute percentage error as a fraction (0–2)."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    denom = np.abs(actual) + np.abs(predicted)
    return float(np.mean(np.divide(
        2 * np.abs(actual - predicted), denom,
        out=np.zeros_like(denom, dtype=float), where=denom != 0,
    )))


def wape(actual, predicted) -> float:
    """Total absolute error / total absolute actual volume, as a fraction.

    Individual zero months are valid; a zero-total period is undefined (NaN).
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    total = float(np.abs(actual).sum())
    return float(np.abs(actual - predicted).sum() / total) if total else np.nan


def metrics(actual, predicted) -> dict[str, float]:
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    return {
        "WAPE": wape(actual, predicted),
        "sMAPE": smape(actual, predicted),
        "MAE": float(mean_absolute_error(actual, predicted)),
        "RMSE": float(np.sqrt(mean_squared_error(actual, predicted))),
        "R2": float(r2_score(actual, predicted)) if len(actual) >= 2 else np.nan,
    }


class NonNegativeRegressor(RegressorMixin, BaseEstimator):
    """Keep ensemble member outputs consistent with the monthly forecast floor."""
    def __init__(self, estimator):
        self.estimator = estimator

    def fit(self, x, y):
        self.estimator_ = clone(self.estimator).fit(x, y)
        self.n_features_in_ = self.estimator_.n_features_in_
        return self

    def predict(self, x):
        return np.maximum(0.0, self.estimator_.predict(x))


class AdaptivePLSRegressor(RegressorMixin, BaseEstimator):
    """PLS regression with a Train-window-safe component upper bound."""
    def __init__(self, n_components=2, scale=True, max_iter=1000, tol=1e-6):
        self.n_components = n_components
        self.scale = scale
        self.max_iter = max_iter
        self.tol = tol

    def fit(self, x, y):
        values = np.asarray(x, dtype=float)
        centered = values - values.mean(axis=0, keepdims=True)
        maximum = min(values.shape[0] - 1, values.shape[1],
                      int(np.linalg.matrix_rank(centered)))
        if maximum < 1:
            raise ValueError("PLS Regression에 사용할 학습행과 피처가 필요합니다")
        self.n_components_ = min(int(self.n_components), maximum)
        self.estimator_ = PLSRegression(
            n_components=self.n_components_, scale=self.scale,
            max_iter=self.max_iter, tol=self.tol,
        ).fit(x, y)
        self.n_features_in_ = self.estimator_.n_features_in_
        if hasattr(self.estimator_, "feature_names_in_"):
            self.feature_names_in_ = self.estimator_.feature_names_in_
        return self

    def predict(self, x):
        return self.estimator_.predict(x)


class RidgeXGBoostRegressor(RegressorMixin, BaseEstimator):
    """Extrapolate with Ridge and learn Train-only nonlinear residuals with XGBoost."""

    def __init__(self, ridge_alpha=1.0, xgb_n_estimators=80,
                 xgb_learning_rate=0.05, xgb_max_depth=2,
                 xgb_min_child_weight=5, xgb_reg_lambda=5.0,
                 random_state=42):
        self.ridge_alpha = ridge_alpha
        self.xgb_n_estimators = xgb_n_estimators
        self.xgb_learning_rate = xgb_learning_rate
        self.xgb_max_depth = xgb_max_depth
        self.xgb_min_child_weight = xgb_min_child_weight
        self.xgb_reg_lambda = xgb_reg_lambda
        self.random_state = random_state

    def fit(self, x, y):
        values = np.asarray(x, dtype=float)
        target = np.asarray(y, dtype=float).reshape(-1)
        self.ridge_ = make_pipeline(StandardScaler(), Ridge(alpha=self.ridge_alpha))
        self.ridge_.fit(values, target)
        residual = target - self.ridge_.predict(values)
        self.xgb_ = model_for("XGBoost", self.random_state).set_params(
            n_estimators=self.xgb_n_estimators,
            learning_rate=self.xgb_learning_rate,
            max_depth=self.xgb_max_depth,
            min_child_weight=self.xgb_min_child_weight,
            reg_lambda=self.xgb_reg_lambda,
        )
        self.xgb_.fit(values, residual)
        self.n_features_in_ = values.shape[1]
        return self

    def predict(self, x):
        values = np.asarray(x, dtype=float)
        return self.ridge_.predict(values) + self.xgb_.predict(values)


def model_for(name: str | dict, seed: int):
    if isinstance(name, dict):
        if name.get("kind") == "ensemble":
            return VotingRegressor(
                estimators=[(f"member{i}", NonNegativeRegressor(model_for(member, seed)))
                            for i, member in enumerate(name["members"])],
                weights=name["weights"], n_jobs=1,
            )
        estimator = model_for(name["base"], seed)
        inner = estimator.steps[-1][1] if hasattr(estimator, "steps") else estimator
        if isinstance(inner, TransformedTargetRegressor):
            inner = inner.regressor
        inner.set_params(**name.get("params", {}))
        return estimator
    if name in {"1차 선형회귀", "OLS"}:
        return make_pipeline(StandardScaler(), LinearRegression())
    if name == "TVP Regression":
        from .tvp_regression import TVPRegressor
        return TVPRegressor()
    if name == 'Tweedie Regression':
        from .statistical_forecasters import ScaledTweedieRegressor
        return ScaledTweedieRegressor()
    if name in {'ARIMAX', 'SARIMAX', 'VAR', 'VARX', 'VECM',
                'Markov Switching AR', 'State Space / Kalman Filter'}:
        from .statistical_forecasters import StatisticalForecastRegressor
        return StatisticalForecastRegressor(kind=name)
    if name == "Ridge":
        return make_pipeline(StandardScaler(), TransformedTargetRegressor(
            regressor=Ridge(alpha=1.0), transformer=StandardScaler(),
        ))
    if name == "Ridge + XGBoost":
        return RidgeXGBoostRegressor(random_state=seed)
    if name == "GAM (선형 외삽형)":
        # Combine a linear term with one spline basis per feature. Constant
        # spline tails leave the linear term to extrapolate beyond Train.
        return make_pipeline(
            StandardScaler(),
            FeatureUnion([
                ("linear", "passthrough"),
                ("spline", SplineTransformer(
                    n_knots=4, degree=3, extrapolation="constant",
                    include_bias=False,
                )),
            ]),
            Ridge(alpha=10.0),
        )
    if name == "Huber Regression":
        return make_pipeline(StandardScaler(), TransformedTargetRegressor(
            regressor=HuberRegressor(epsilon=1.35, alpha=0.01, max_iter=1000),
            transformer=StandardScaler(),
        ))
    if name == "SVR (Linear)":
        return make_pipeline(StandardScaler(), TransformedTargetRegressor(
            regressor=SVR(kernel="linear", C=1.0, epsilon=0.1),
            transformer=StandardScaler(),
        ))
    if name == "2차 다항 Ridge":
        return make_pipeline(PolynomialFeatures(degree=2, include_bias=False),
                             StandardScaler(), Ridge(alpha=10.0))
    if name == "PLS Regression":
        # PLS scales both X and y using statistics learned only from each Train window.
        # Predictions are inverse-transformed to the original TEU/DWT target units.
        return AdaptivePLSRegressor(n_components=2, scale=True, max_iter=1000, tol=1e-6)
    if name == "PCA + Ridge":
        # Keep enough Train-only principal components to explain 95% of X variance.
        return make_pipeline(StandardScaler(),
                             PCA(n_components=0.95, svd_solver="full"),
                             Ridge(alpha=10.0))
    if name == "랜덤 포레스트":
        return RandomForestRegressor(n_estimators=60, min_samples_leaf=3,
                                     max_features=1.0, random_state=seed, n_jobs=1)
    if name == "ElasticNet":
        # Fit both scalers on each training window; predictions stay in TEU/DWT.
        return make_pipeline(StandardScaler(), TransformedTargetRegressor(
            regressor=ElasticNet(alpha=0.05, l1_ratio=0.5, max_iter=10000,
                                 random_state=seed),
            transformer=StandardScaler(),
        ))
    if name == "Quantile Regression":
        # Conditional median, not a prediction interval. Both scalers fit on
        # Train only; weak default L1 may be tuned using Train-only CV.
        return make_pipeline(StandardScaler(), TransformedTargetRegressor(
            regressor=QuantileRegressor(quantile=0.5, alpha=0.01, solver='highs'),
            transformer=StandardScaler(),
        ))
    if name == "CatBoost":
        from catboost import CatBoostRegressor
        return CatBoostRegressor(
            iterations=80, depth=3, learning_rate=0.05, l2_leaf_reg=5.0,
            loss_function='RMSE', random_seed=seed, thread_count=1,
            has_time=True, bootstrap_type='No', use_best_model=False,
            allow_const_label=True, allow_writing_files=False, verbose=False,
        )
    if name == "GBM":
        return GradientBoostingRegressor(
            n_estimators=80, learning_rate=0.05, max_depth=2,
            min_samples_leaf=5, random_state=seed,
        )
    if name == "Extra Trees":
        return ExtraTreesRegressor(
            n_estimators=60, max_depth=5, min_samples_leaf=3,
            max_features=1.0, random_state=seed, n_jobs=1,
        )
    if name == "HistGradientBoosting":
        return HistGradientBoostingRegressor(
            max_iter=80, learning_rate=0.05, max_leaf_nodes=7,
            min_samples_leaf=8, l2_regularization=1.0,
            early_stopping=False, random_state=seed,
        )
    if name == "LightGBM":
        from .lightgbm_safe import FeatureNameSafeLGBMRegressor
        return FeatureNameSafeLGBMRegressor(
            objective="regression", n_estimators=80, learning_rate=0.05,
            max_depth=3, num_leaves=7, min_child_samples=8,
            reg_lambda=5.0, subsample=1.0, colsample_bytree=1.0,
            random_state=seed, n_jobs=1, verbosity=-1,
            deterministic=True, force_col_wise=True,
        )
    if name == "XGBoost":
        from xgboost import XGBRegressor
        return XGBRegressor(
            objective="reg:squarederror", tree_method="hist", n_estimators=80,
            learning_rate=0.05, max_depth=2, min_child_weight=5,
            reg_lambda=5.0, subsample=1.0, colsample_bytree=1.0,
            random_state=seed, n_jobs=1, verbosity=0,
        )
    raise ValueError(f"지원하지 않는 모형: {name}")


def monthly_splits(data: pd.DataFrame, months, features: list[str], min_train: int):
    columns = [TARGET, *features]
    if AVAILABLE_LAG_COLUMN in data:
        columns.append(AVAILABLE_LAG_COLUMN)
    available = data[columns].dropna(subset=[TARGET, *features])
    for month in months:
        if month not in available.index:
            continue
        lag = available.loc[month, AVAILABLE_LAG_COLUMN] if AVAILABLE_LAG_COLUMN in available else 3
        if pd.isna(lag):
            continue
        train = available.loc[available.index <= month - pd.DateOffset(months=int(lag))]
        if len(train) >= min_train:
            yield month, train, available.loc[[month]]


def walk_forward(data: pd.DataFrame, months, features: list[str], model: str,
                 params: dict) -> pd.DataFrame:
    rows = []
    for month, train, test in monthly_splits(data, months, features, params["minimum_train_months"]):
        if model == ROLLING_BASELINE_MODEL:
            if features != [ROLLING_BASELINE]:
                raise ValueError("The rolling baseline requires its own derived feature only")
            predicted = float(test[ROLLING_BASELINE].iloc[0])
        else:
            estimator = model_for(model, params["random_seed"])
            estimator.fit(train[features], train[TARGET])
            predicted = max(0.0, float(estimator.predict(test[features])[0]))
        rows.append({"기준월": month, "실제": float(test[TARGET].iloc[0]),
                     "예측": predicted, "학습관측월": len(train),
                     "학습종료월": train.index.max()})
    result = pd.DataFrame(rows)
    if not result.empty:
        result = result.set_index("기준월")
    return result


def _as_indexed(data: pd.DataFrame) -> pd.DataFrame:
    frame = data.copy()
    frame["기준월"] = pd.to_datetime(frame["기준월"], format="%Y-%m")
    return frame.set_index("기준월").sort_index()


def select_lags(data: pd.DataFrame, policies: pd.DataFrame, params: dict) -> pd.DataFrame:
    data = selection_history(data, params)
    start = pd.Timestamp(params["validation_start"])
    end = pd.Timestamp(params["holdout_start"])
    rows = []
    for policy in policies.itertuples(index=False):
        feature = policy.원본피처
        candidates = [int(months) for months in policy.허용시차.split(",")]
        columns = [f"{feature}_{months}개월전" for months in candidates]
        common = data[[TARGET, TARGET_LAG, AVAILABLE_LAG_COLUMN, *columns]].dropna(
            subset=[TARGET, TARGET_LAG, *columns]
        )
        validation_months = common.index[(common.index >= start) & (common.index < end)]
        valid_splits = list(monthly_splits(common, validation_months,
                                          [columns[0], TARGET_LAG], params["minimum_train_months"]))
        shared_months = pd.DatetimeIndex([month for month, _, _ in valid_splits])
        if shared_months.empty:
            raise InsufficientHistoryError(f"{feature}: 시차 검증월이 없습니다.")
        for months, column in zip(candidates, columns):
            result = walk_forward(common, shared_months, [column, TARGET_LAG],
                                  "2차 다항 Ridge", params)
            if len(result) != len(shared_months):
                raise ValueError(f"{feature}: 시차 후보의 검증월이 일치하지 않습니다.")
            rows.append({"원본피처": feature, "시차개월": months,
                         "검증관측월": len(result), **metrics(result["실제"], result["예측"])})
    table = pd.DataFrame(rows)
    best = table.sort_values(["원본피처", "sMAPE", "RMSE", "시차개월"]).drop_duplicates("원본피처")
    choice = dict(zip(best["원본피처"], best["시차개월"]))
    table["선택"] = [row.시차개월 == choice[row.원본피처] for row in table.itertuples()]
    return table


def select_model(data: pd.DataFrame, lags: pd.DataFrame, params: dict,
                 ship_type: str) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, dict]:
    full_indexed = _as_indexed(data)
    first_holdout = pd.Timestamp(params["holdout_start"])
    first_lag = params.get("holdout_order_lag")
    if first_lag is None and (
        AVAILABLE_LAG_COLUMN in full_indexed and first_holdout in full_indexed.index
    ):
        first_lag = full_indexed.loc[first_holdout, AVAILABLE_LAG_COLUMN]
    if first_lag is None:
        first_lag = 3
    if pd.isna(first_lag):
        raise ValueError("첫 보류월의 수주 공표 가용성이 확인되지 않습니다")
    data = selection_history(data, params)
    groups = feature_groups(ship_type)
    chosen = dict(zip(lags.loc[lags["선택"], "원본피처"], lags.loc[lags["선택"], "시차개월"]))
    external = [f"{feature}_{chosen[feature]}개월전" for group in groups.values() for feature in group]
    order_candidates = (
        ORDER_POINT_LAG_COLUMNS if ship_type == "컨테이너선" else ORDER_WINDOWS
    )
    common_features = [*external, *order_candidates.values()]
    # 컨테이너선은 다른 시차의 결측 때문에 선택된 한 시차의 학습행을 버리지 않는다.
    required_features = [TARGET, ROLLING_BASELINE, *external]
    if ship_type != "컨테이너선":
        required_features += list(order_candidates.values())
    model_data = data[[TARGET, ROLLING_BASELINE, AVAILABLE_LAG_COLUMN, *common_features]].dropna(
        subset=required_features
    )
    validation_start = pd.Timestamp(params["validation_start"])
    holdout_start = pd.Timestamp(params["holdout_start"])
    development = model_data.loc[model_data.index < holdout_start]
    if len(development) < 60:
        raise InsufficientHistoryError(f"{ship_type}: 공통 개발 관측치가 60개 미만입니다.")
    validation = development.index[development.index >= validation_start]
    comparison_development = development.dropna(subset=list(order_candidates.values()))
    shared_months = pd.DatetimeIndex([month for month, _, _ in monthly_splits(
        comparison_development, validation, common_features, params["minimum_train_months"]
    )])
    minimum_validation = params.get("minimum_validation_months", 24)
    if len(shared_months) < minimum_validation:
        raise InsufficientHistoryError(
            f"{ship_type}: 공통 검증월 {len(shared_months)}개 < 최소 {minimum_validation}개"
        )
    window_scores = []
    for months, column in order_candidates.items():
        result = walk_forward(development, shared_months, [*external, column],
                              "2차 다항 Ridge", params)
        if len(result) != len(shared_months):
            raise ValueError(f"{ship_type}: 수주 시차 후보의 검증월이 일치하지 않습니다.")
        window_scores.append((months, column, metrics(result["실제"], result["예측"])))
    chosen_months, chosen_window, _ = min(
        window_scores, key=lambda row: (row[2]["sMAPE"], row[2]["RMSE"], row[0])
    )
    all_features = [*external, chosen_window]
    market = {f"{feature}_{chosen[feature]}개월전" for group in ("freight", "fleet", "cargo")
              for feature in groups[group]}
    old_features = [feature for feature in external if feature not in market] + [chosen_window]

    @lru_cache(maxsize=None)
    def evaluate(name: str, feature_tuple: tuple[str, ...]):
        result = walk_forward(development, shared_months, list(feature_tuple), name, params)
        if len(result) != len(shared_months):
            raise ValueError(f"{ship_type}: 모형 후보의 검증월이 일치하지 않습니다.")
        return metrics(result["실제"], result["예측"])

    comparison = [
        {"변수집합": "수주 시차 비교" if ship_type == "컨테이너선" else "수주 누적 창 비교", "모형": "2차 다항 Ridge",
         "수주창개월": months, "수주피처": column, "선택": column == chosen_window,
         "피처수": len(external) + 1, **score, "검증관측월": len(shared_months)}
        for months, column, score in window_scores
    ]
    baseline = []
    for month, train, test in monthly_splits(development, shared_months, [], params["minimum_train_months"]):
        baseline.append((float(test[TARGET].iloc[0]), float(train[TARGET].mean())))
    base_metrics = metrics(*zip(*baseline))
    comparison.append({"변수집합": "기준값", "모형": "훈련구간 평균", "피처수": 0,
                       **base_metrics, "검증관측월": len(shared_months)})
    rolling_metrics = evaluate(ROLLING_BASELINE_MODEL, (ROLLING_BASELINE,))
    comparison.append({"변수집합": "시계열 기준선", "모형": ROLLING_BASELINE_MODEL,
                       "피처수": 1, **rolling_metrics, "검증관측월": len(shared_months)})
    for name in MODELS:
        for label, features in (("기존 외부지표", old_features[:-1]),
                                ("기존 전체", old_features), ("전체", all_features)):
            comparison.append({"변수집합": label, "모형": name, "피처수": len(features),
                               **evaluate(name, tuple(features)), "검증관측월": len(shared_months)})

    path = []
    candidates = [{"변수집합": "시계열 기준선", "모형": ROLLING_BASELINE_MODEL,
                   "피처목록": [ROLLING_BASELINE], "피처수": 1, **rolling_metrics}]
    path.append({"변수집합": "시계열 기준선", "모형": ROLLING_BASELINE_MODEL,
                 "단계": 0, "제거변수": "-", "피처수": 1,
                 "검증sMAPE": rolling_metrics["sMAPE"],
                 "검증RMSE": rolling_metrics["RMSE"],
                 "sMAPE개선_퍼센트포인트": np.nan})
    for label, start_features in (("기존 변수", old_features), ("시장지표 추가", all_features)):
        for name in MODELS:
            current = list(start_features)
            current_metrics = evaluate(name, tuple(current))
            path.append({"변수집합": label, "모형": name, "단계": 0, "제거변수": "-",
                         "피처수": len(current), "검증sMAPE": current_metrics["sMAPE"],
                         "검증RMSE": current_metrics["RMSE"], "sMAPE개선_퍼센트포인트": np.nan})
            while len(current) > 1 and len(start_features) - len(current) < params["maximum_removed_features"]:
                options = []
                for removed in current:
                    remaining = [feature for feature in current if feature != removed]
                    options.append((evaluate(name, tuple(remaining)), removed, remaining))
                next_metrics, removed, remaining = min(options, key=lambda item: (item[0]["sMAPE"], item[0]["RMSE"]))
                gain = current_metrics["sMAPE"] - next_metrics["sMAPE"]
                if gain <= current_metrics["sMAPE"] * params["minimum_relative_smape_improvement"]:
                    break
                current, current_metrics = remaining, next_metrics
                path.append({"변수집합": label, "모형": name, "단계": len(start_features) - len(current),
                             "제거변수": removed, "피처수": len(current),
                             "검증sMAPE": current_metrics["sMAPE"], "검증RMSE": current_metrics["RMSE"],
                             "sMAPE개선_퍼센트포인트": 100 * gain})
            candidates.append({"변수집합": label, "모형": name, "피처목록": list(current),
                               "피처수": len(current), **current_metrics})
    sorted_candidates = sorted(candidates, key=lambda item: (item["sMAPE"], item["RMSE"], item["피처수"], item["모형"]))
    winner = sorted_candidates[0]
    importance = []
    for feature in winner["피처목록"]:
        remaining = [item for item in winner["피처목록"] if item != feature]
        without = evaluate(winner["모형"], tuple(remaining))["sMAPE"] if remaining else np.nan
        importance.append({"피처": feature, "제거후sMAPE": without,
                           "제거시sMAPE증가_퍼센트포인트": 100 * (without - winner["sMAPE"])})
    selected = {"선종": ship_type, "모형": winner["모형"], "변수집합": winner["변수집합"],
                "수주누적창개월": chosen_months, "수주누적피처": chosen_window,
                "피처목록": winner["피처목록"], "검증sMAPE": winner["sMAPE"],
                "검증RMSE": winner["RMSE"], "검증관측월": len(shared_months),
                "검증시작": shared_months.min().strftime("%Y-%m"),
                "검증종료": shared_months.max().strftime("%Y-%m"),
                "선택가능실적종료": (holdout_start - pd.DateOffset(months=int(first_lag))).strftime("%Y-%m")}
    candidate_table = pd.DataFrame([{**row, "피처목록": json.dumps(row["피처목록"], ensure_ascii=False)}
                                    for row in sorted_candidates])
    return (pd.DataFrame(comparison), pd.DataFrame(path), candidate_table,
            pd.DataFrame(importance).sort_values("제거시sMAPE증가_퍼센트포인트", ascending=False), selected)


def evaluate_holdout(data: pd.DataFrame, selected: dict, params: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    data = _as_indexed(data)
    start = pd.Timestamp(params["holdout_start"])
    features = selected["피처목록"]
    available = data[[TARGET, *features]].dropna()
    holdout_months = available.index[available.index >= start]
    holdout = walk_forward(data, holdout_months, features, selected["모형"], params)
    if len(holdout) != len(holdout_months):
        raise ValueError(f"{selected['선종']}: 보류 구간에서 예측할 수 없는 월이 있습니다.")
    historical_months = available.index[available.index < start]
    historical = walk_forward(data, historical_months, features, selected["모형"], params)
    historical["구간"] = np.where(historical.index < pd.Timestamp(params["validation_start"]), "학습 참고", "개발 검증")
    holdout["구간"] = "2025+ 테스트"
    predictions = pd.concat([historical, holdout]).sort_index().reset_index()
    for column in ("기준월", "학습종료월"):
        predictions[column] = predictions[column].dt.strftime("%Y-%m")
    holdout_metrics = metrics(holdout["실제"], holdout["예측"])
    complete_years = []
    for year, group in holdout.groupby(holdout.index.year):
        if group.index.month.tolist() == list(range(1, 13)):
            complete_years.append({"연도": int(year), "실제": group["실제"].sum(),
                                   "예측": group["예측"].sum()})
    annual = pd.DataFrame(complete_years)
    annual_metrics = metrics(annual["실제"], annual["예측"]) if not annual.empty else None
    report = pd.DataFrame([{"선종": selected["선종"], "모형": selected["모형"],
                            "변수집합": selected["변수집합"], "피처수": len(features),
                            **holdout_metrics, "평가관측월": len(holdout),
                            "평가시작": holdout.index.min().strftime("%Y-%m"),
                            "평가종료": holdout.index.max().strftime("%Y-%m"),
                            "연간누적평가연수": len(annual),
                            "연간누적sMAPE": annual_metrics["sMAPE"] if annual_metrics else np.nan,
                            "연간누적MAE": annual_metrics["MAE"] if annual_metrics else np.nan,
                            "연간누적RMSE": annual_metrics["RMSE"] if annual_metrics else np.nan}])
    return predictions, report
