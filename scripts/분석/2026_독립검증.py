"""Freeze a pre-2026 configuration, then score observed 2026 monthly orders.

This is a retrospective holdout audit, not a reconstruction of historical
external-data vintages. Incomplete 2026 Comtrade/JODI cargo totals are excluded
from *both* development and holdout candidate features. The ordinary master
builder remains strict; its relaxed recent-month option is used only in memory.
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ship_orders_forecasting.fold_validation import (  # noqa: E402
    chronological_folds, evaluate_folds,
)
from ship_orders_forecasting.legacy import legacy_module  # noqa: E402
from ship_orders_forecasting.modeling import (  # noqa: E402
    MODELS, PUBLISHED_LABEL_COLUMN, ROLLING_BASELINE, ROLLING_BASELINE_MODEL, TARGET,
    metrics, monthly_splits, walk_forward,
)
from ship_orders_forecasting.order_availability import (  # noqa: E402
    AVAILABLE_LAG_COLUMN, AVAILABILITY_STATUS_COLUMN,
    last_weekday_of_previous_month, publication_dates,
)
from ship_orders_forecasting.operational_forecast import (  # noqa: E402
    BASELINE, POINT_LAGS, WINDOWS, direct_frame, future_direct, origin_features,
    select_direct, test_direct,
)


RULES = legacy_module("마스터테이블_생성")
FIRST_TEST_MONTH = pd.Timestamp("2026-01-01")
LAST_TEST_MONTH = pd.Timestamp("2026-08-01")
MINIMUM_TRAIN = 48
SEED = 42
OUTPUT = ROOT / "reports" / "2026_독립검증.json"
ASOF_ORIGIN = pd.Timestamp("2026-09-30")


def inputs() -> dict:
    """Read the same processed sources and joins as the production master."""
    return {
        "commodities": RULES.load_commodities(),
        "cargo_volumes": pd.DataFrame(),
        "bunker_sales": RULES.load_bunker_sales(),
        "geopolitical_risk": RULES.load_geopolitical_risk(),
        "trade_policy_uncertainty": RULES.load_trade_policy_uncertainty(),
        "ship_prices": RULES.load_ship_prices(),
        "freight": RULES.load_freight(),
        "fleet": RULES.load_fleet(),
        "container_index": RULES.load_monthly_indicators(
            RULES.CONTAINER_INDEX_PATH, RULES.CONTAINER_INDEX_COLUMNS,
        ),
        "global_economy": RULES.load_monthly_indicators(
            RULES.GLOBAL_ECONOMY_PATH, RULES.GLOBAL_ECONOMY_COLUMNS,
        ),
        "supply_chain": RULES.load_monthly_indicators(
            RULES.SUPPLY_CHAIN_PATH, RULES.SUPPLY_CHAIN_COLUMNS, positive=False,
        ),
    }


def evaluation_frame(ship_type: str, sources: dict) -> tuple[pd.DataFrame, list[str]]:
    master, _, _ = RULES.build_master(
        ship_type, **sources, end_month="2026-08",
        allow_incomplete_after="2026-01",
    )
    frame = master.copy()
    frame["기준월"] = pd.to_datetime(frame["기준월"], format="%Y-%m")
    frame = frame.set_index("기준월").sort_index()
    if not frame.index.is_unique or not frame.index.equals(
        pd.date_range(frame.index.min(), frame.index.max(), freq="MS")
    ):
        raise ValueError(f"{ship_type}: 평가 월 달력이 연속적이지 않습니다")
    raw_orders = pd.read_csv(
        RULES.RAW_ORDERS_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False,
    )
    published = publication_dates(raw_orders, RULES.RAW_VESSEL_TYPES[ship_type])
    frame[PUBLISHED_LABEL_COLUMN] = pd.to_datetime(
        pd.Series(frame.index.strftime("%Y-%m"), index=frame.index).map(published),
    )

    cargo = set(RULES.SHIP_CARGO_VOLUME_COLUMNS[ship_type])
    order_windows = set(RULES.order_feature_columns_for(ship_type).values())
    raw_external = [
        name for name in RULES.feature_columns_for(ship_type)
        if name not in cargo | order_windows | set(RULES.PROCESSED_ORDER_LAG_COLUMNS.values())
    ]
    # All monthly indicators use a conservative two-month lag. Daily/weekly
    # freight and already delayed annual fleet capacity may use one month.
    fast = {*RULES.FREIGHT_COLUMNS.values(), RULES.FLEET_COLUMN}
    lagged = []
    for name in raw_external:
        months = 1 if name in fast else 2
        column = f"{name}_{months}개월전"
        frame[column] = frame[name].shift(months)
        lagged.append(column)

    # Recheck *every* month contributing to a rolling feature. A timely t-2
    # endpoint does not prove that an older report inside its window existed.
    for month in frame.index:
        lag = frame.at[month, AVAILABLE_LAG_COLUMN]
        if pd.isna(lag):
            frame.at[month, ROLLING_BASELINE] = np.nan
            continue
        cutoff = last_weekday_of_previous_month(month)
        recent = []
        for offset in range(max(RULES.order_feature_columns_for(ship_type))):
            source_month = month - pd.DateOffset(months=int(lag) + offset)
            if source_month not in frame.index:
                recent.append(np.nan)
                continue
            value = frame.at[source_month, TARGET]
            date = frame.at[source_month, PUBLISHED_LABEL_COLUMN]
            usable = pd.notna(value) and (
                (pd.notna(date) and date <= cutoff)
                or (pd.isna(date) and int(lag) + offset >= 3)
            )
            recent.append(float(value) if usable else np.nan)
        recent_three = [value for value in recent[:3] if pd.notna(value)]
        frame.at[month, ROLLING_BASELINE] = (
            float(np.mean(recent_three)) if recent_three else np.nan
        )
        for length, column in RULES.order_feature_columns_for(ship_type).items():
            frame.at[month, column] = recent[length - 1]
    return frame, lagged


def frozen_choice(ship_type: str, frame: pd.DataFrame,
                  external: list[str]) -> tuple[dict, list[dict]]:
    lag = frame.loc[FIRST_TEST_MONTH, AVAILABLE_LAG_COLUMN]
    if pd.isna(lag):
        raise ValueError("2026-01 예측시점의 수주 공표 가용성을 확인할 수 없습니다")
    possible_end = FIRST_TEST_MONTH - pd.DateOffset(months=int(lag))
    origin = last_weekday_of_previous_month(FIRST_TEST_MONTH)
    verified_labels = frame.loc[
        (frame.index <= possible_end)
        & frame[TARGET].notna()
        & frame[PUBLISHED_LABEL_COLUMN].notna()
        & frame[PUBLISHED_LABEL_COLUMN].le(origin)
    ].index
    if verified_labels.empty:
        raise ValueError("2026-01 이전에 게시일이 확인된 수주실적이 없습니다")
    # The generic t-3 allowance is only an approximation for undated reports.
    # Freeze selection at the last *verified* published label instead.
    selection_end = verified_labels.max()
    windows = list(RULES.order_feature_columns_for(ship_type).items())
    needed = [TARGET, AVAILABLE_LAG_COLUMN, PUBLISHED_LABEL_COLUMN, ROLLING_BASELINE,
              *external, *(column for _, column in windows)]
    required = [name for name in needed if name != PUBLISHED_LABEL_COLUMN]
    required = [name for name in required if name not in dict(windows).values()]
    development = frame.loc[:selection_end, needed].dropna(subset=required)
    comparison = development.dropna(subset=[column for _, column in windows])
    possible = development.index[
        (development.index >= pd.Timestamp("2022-01-01"))
        & (development.index.year <= 2025)
    ]
    params = {"minimum_train_months": MINIMUM_TRAIN, "random_seed": SEED}
    shared = pd.DatetimeIndex([
        month for month, _, _ in monthly_splits(
            comparison, possible, [*external, windows[0][1]], MINIMUM_TRAIN,
        )
    ])
    folds = chronological_folds(shared, "Y")
    if set(folds) != {"2022", "2023", "2024", "2025"}:
        raise ValueError(f"개발 fold가 부족합니다: {list(folds)}")
    if any(len(months) < 3 for months in folds.values()):
        raise ValueError("월별 개발 fold에 평가월이 3개 미만입니다")

    order_scores = []
    for length, column in windows:
        score, details = evaluate_folds(
            development, folds, [*external, column], "2차 다항 Ridge",
            min_train=MINIMUM_TRAIN, seed=SEED,
        )
        order_scores.append((length, column, score, details))
    chosen_window = min(
        order_scores,
        key=lambda item: (item[2]["sMAPE"], item[2]["sMAPE표준편차"], item[0]),
    )[1]

    choices = [("시계열 기준선", ROLLING_BASELINE_MODEL, [ROLLING_BASELINE])]
    for group, features in (
        ("수주 이력", [chosen_window]),
        ("외부지표+수주 이력", [*external, chosen_window]),
    ):
        choices.extend((group, name, features) for name in MODELS)

    candidates = []
    for group, model, features in choices:
        score, details = evaluate_folds(
            development, folds, features, model,
            min_train=MINIMUM_TRAIN, seed=SEED,
        )
        candidates.append({
            "변수집합": group, "모형": model, "피처목록": features,
            "평균sMAPE": score["sMAPE"],
            "sMAPE표준편차": score["sMAPE표준편차"],
            "평균RMSE": score["RMSE"],
            "fold별sMAPE": {row.fold: float(row.sMAPE) for row in details.itertuples()},
            "fold별평가월": {name: len(months) for name, months in folds.items()},
        })
    winner = min(candidates, key=lambda row: (
        row["평균sMAPE"], row["sMAPE표준편차"], row["평균RMSE"], len(row["피처목록"]),
    ))
    return {
        **winner,
        "선택가능수주실적종료": selection_end.strftime("%Y-%m"),
        "선택된수주창": chosen_window,
        "수주창비교": [
            {"시차순번": length, "피처": column,
             "평균sMAPE": score["sMAPE"],
             "fold별sMAPE": {row.fold: float(row.sMAPE) for row in details.itertuples()}}
            for length, column, score, details in order_scores
        ],
    }, candidates


def holdout(frame: pd.DataFrame, choice: dict) -> dict:
    observed = frame.loc[FIRST_TEST_MONTH:LAST_TEST_MONTH]
    observed = observed.index[observed[TARGET].notna()]
    params = {"minimum_train_months": MINIMUM_TRAIN, "random_seed": SEED}
    predicted = walk_forward(
        frame, observed, choice["피처목록"], choice["모형"], params,
    )
    baseline = walk_forward(
        frame, observed, [ROLLING_BASELINE], ROLLING_BASELINE_MODEL, params,
    )
    common = observed.intersection(predicted.index).intersection(baseline.index)
    if common.empty:
        raise ValueError("2026년 공통 평가월이 없습니다")
    predicted = predicted.loc[common]
    baseline = baseline.loc[common]
    if not predicted["실제"].equals(baseline["실제"]):
        raise AssertionError("모형과 기준선의 실제값이 다릅니다")
    model_score = metrics(predicted["실제"], predicted["예측"])
    baseline_score = metrics(predicted["실제"], baseline["예측"])
    verified = pd.DatetimeIndex([
        month for month in common
        if frame.loc[month, AVAILABILITY_STATUS_COLUMN] == "게시일확인"
    ])
    verified_model = metrics(
        predicted.loc[verified, "실제"], predicted.loc[verified, "예측"],
    ) if len(verified) else None
    verified_baseline = metrics(
        predicted.loc[verified, "실제"], baseline.loc[verified, "예측"],
    ) if len(verified) else None
    rows = []
    for month, row in predicted.iterrows():
        rows.append({
            "기준월": month.strftime("%Y-%m"),
            "실제": float(row["실제"]), "예측": float(row["예측"]),
            "기준선예측": float(baseline.loc[month, "예측"]),
            "수주정보시차(개월)": int(frame.loc[month, AVAILABLE_LAG_COLUMN]),
            "수주정보가용근거": frame.loc[month, AVAILABILITY_STATUS_COLUMN],
            "학습관측월": int(row["학습관측월"]),
            "학습종료월": row["학습종료월"].strftime("%Y-%m"),
        })
    return {
        "평가월수": len(common),
        "관측실적월수": len(observed),
        "미평가월": [month.strftime("%Y-%m") for month in observed.difference(common)],
        "수주실적미관측월": [month.strftime("%Y-%m") for month in pd.date_range(
            FIRST_TEST_MONTH, LAST_TEST_MONTH, freq="MS",
        ).difference(observed)],
        "월별sMAPE": model_score["sMAPE"],
        "월별RMSE": model_score["RMSE"],
        "월별MAE": model_score["MAE"],
        "기준선sMAPE": baseline_score["sMAPE"],
        "기준선RMSE": baseline_score["RMSE"],
        "수주월보게시일확인평가월수": len(verified),
        "게시일확인월sMAPE": verified_model["sMAPE"] if verified_model else None,
        "게시일확인월기준선sMAPE": verified_baseline["sMAPE"] if verified_baseline else None,
        "월별예측": rows,
    }


def asof_input_table(ship_type: str, frame: pd.DataFrame, external: list[str],
                     sources: dict, published: pd.Series,
                     origin: pd.Timestamp = ASOF_ORIGIN) -> pd.DataFrame:
    """Audit each candidate's observation month separately from publication.

    External processed files have no per-observation release timestamp. Their
    t-1/t-2 values are *candidates*, never marked publication-confirmed input.
    """
    target = (origin.to_period("M") + 1).to_timestamp()
    rows = []
    point_lags = True
    orders = origin_features(frame, published, origin,
                             allow_undated_history=False, point_lags=point_lags)
    order_features = POINT_LAGS if point_lags else WINDOWS
    for ordinal, name in order_features.items():
        observed = orders["최신수주관측월"]
        if point_lags and pd.notna(observed):
            observed = observed - pd.DateOffset(months=ordinal - 1)
        release = (published.get(observed.strftime("%Y-%m"), pd.NaT)
                   if point_lags and pd.notna(observed)
                   else orders["최신수주게시일"])
        rows.append({"선종": ship_type, "예측기준일": origin.strftime("%Y-%m-%d"),
                     "예측대상월": target.strftime("%Y-%m"), "피처": name,
                     "관측월": observed.strftime("%Y-%m") if pd.notna(observed) else None,
                     "게시일": release.strftime("%Y-%m-%d") if pd.notna(release) else None,
                     "입력가능값": orders[name] if orders[f"{name}_게시일확인"] else None,
                     "미검증후보값": orders[name] if pd.notna(orders[name])
                     and not orders[f"{name}_게시일확인"] else None,
                     "게시일검증": orders[f"{name}_게시일확인"],
                     "상태": "게시일확인" if orders[f"{name}_게시일확인"]
                             else "수주공표일미확인또는결측",
                     "단위": RULES.TARGET_UNITS[ship_type],
                     "출처파일": RULES.RAW_ORDERS_PATH.name})
    paths = {
        "commodities": RULES.COMMODITY_PATH, "bunker_sales": RULES.BUNKER_SALES_PATH,
        "geopolitical_risk": RULES.RISK_PATH,
        "trade_policy_uncertainty": RULES.TRADE_POLICY_PATH,
        "ship_prices": RULES.SHIP_PRICE_PATH, "freight": RULES.FREIGHT_PATH,
        "fleet": RULES.FLEET_PATH, "container_index": RULES.CONTAINER_INDEX_PATH,
        "global_economy": RULES.GLOBAL_ECONOMY_PATH,
        "supply_chain": RULES.SUPPLY_CHAIN_PATH,
    }
    for feature in external:
        raw_name, lag_text = feature.rsplit("_", 1)
        lag = int(lag_text.removesuffix("개월전"))
        desired = (target - pd.DateOffset(months=lag)).strftime("%Y-%m")
        source_key = next((key for key, source in sources.items()
                           if key != "cargo_volumes" and raw_name in source.columns), None)
        if source_key is None:
            raise KeyError(f"외부 피처의 원천을 찾지 못했습니다: {raw_name}")
        source = sources[source_key]
        if "선종" in source.columns:
            source = source.loc[source["선종"].eq(ship_type)]
        month_key = "사용가능월" if source_key == "fleet" else "기준월"
        matches = source.loc[source[month_key].le(desired)].sort_values(month_key)
        # Monthly indicators must match the selected observation month. The
        # fleet is an annually published stock, so its latest usable year holds.
        if source_key != "fleet":
            matches = matches.loc[matches[month_key].eq(desired)]
        row = matches.iloc[-1] if len(matches) else None
        value = float(row[raw_name]) if row is not None and pd.notna(row[raw_name]) else None
        rows.append({"선종": ship_type, "예측기준일": origin.strftime("%Y-%m-%d"),
                     "예측대상월": target.strftime("%Y-%m"), "피처": feature,
                     "관측월": str(row[month_key]) if row is not None else desired,
                     "게시일": None, "입력가능값": None,
                     "미검증후보값": value, "게시일검증": False,
                     "상태": "공표일미기록·시차가정" if value is not None else "관측값없음",
                     "단위": "피처명참조",
                     "출처파일": paths[source_key].name})
    return pd.DataFrame(rows)


def main() -> None:
    sources = inputs()
    results = []
    asof_tables = []
    for ship_type in RULES.SHIP_TYPES:
        print(f"{ship_type}: 2026 이전 변수·모형 선택 중", flush=True)
        frame, external = evaluation_frame(ship_type, sources)
        choice, one_candidates = frozen_choice(ship_type, frame, external)
        test = holdout(frame, choice)
        raw_orders = pd.read_csv(RULES.RAW_ORDERS_PATH, encoding="utf-8-sig",
                                 dtype=str, keep_default_na=False)
        published = publication_dates(raw_orders, RULES.RAW_VESSEL_TYPES[ship_type])
        asof = asof_input_table(ship_type, frame, external, sources, published)
        asof_tables.extend(json.loads(asof.to_json(orient="records", force_ascii=False)))
        direct_results = []
        for horizon in (1, 3, 6):
            print(f"{ship_type}: {horizon}개월 직접 선행예측 검증 중", flush=True)
            point_lags = True
            direct = direct_frame(frame, published, horizon, point_lags=point_lags)
            direct_choice, direct_candidates = select_direct(
                direct, published, horizon, point_lags=point_lags,
            )
            direct_test = test_direct(direct, published, direct_choice)
            future = future_direct(direct, published, direct_choice)
            direct_results.append({"선행개월": horizon, "선택": direct_choice,
                                   "개발후보": direct_candidates, "2026평가": direct_test,
                                   "2026-09-30_실제운영예측": future})
        results.append({
            "선종": ship_type, "단위": RULES.TARGET_UNITS[ship_type],
            "선택": choice, "개발후보": one_candidates, "2026평가": test,
            "직접선행예측": direct_results,
        })
        print(
            f"{ship_type}: {test['평가월수']}개월 | "
            f"sMAPE {test['월별sMAPE']:.1%} | "
            f"기준선 {test['기준선sMAPE']:.1%}", flush=True,
        )
    report = {
        "평가기간": "2026-01~2026-08",
        "방법": "2025년까지 이용 가능한 수주 라벨로 2022~2025 연도별 fold 선택; "
                "선택된 변수·모형을 고정하고 2026년은 월별 재학습만 수행",
        "물동량": "2026 잠정 글로벌 합계는 개발·보류구간 모두 피처에서 제외",
        "제약": "외부지표의 당시 발표 빈티지는 복원하지 못한 후향적 평가. "
                "2026-01은 수주 월보 게시일 미상인 t-3 근사이므로 게시일확인월 점수를 별도 표기. "
                "컨테이너선 단일월 시차 설계는 2026년 결과를 이미 확인한 뒤 변경했으므로 "
                "새 설계의 2026년 점수는 독립 테스트가 아닌 개발 진단.",
        "기준일입력": asof_tables,
        "선행예측방법": "1·3·6개월 모델은 목표월에서 각각 1·3·6개월 전 월말에 게시된 수주 이력만 입력. "
                    "과거 미상 게시일은 t-3 근사로 명시하며, 실제 2026-09-30 예측에는 게시일 확인 수주만 사용. "
                    "컨테이너선은 누적합 대신 최신 확정월 기준 1·2·3번째 단일 월 값을 후보로 사용. "
                    "2026년 1~8월 라벨은 코드의 변수·모형 재선택에 사용하지 않음.",
        "결과": results,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"저장: {OUTPUT}")


if __name__ == "__main__":
    main()
