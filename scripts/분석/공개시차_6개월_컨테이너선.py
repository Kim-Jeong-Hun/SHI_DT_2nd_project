"""Three-month publication-delay proxy and one direct h+6 model for every ship type.

2025-2026 has already been repeatedly inspected; all scores are development
diagnostics, not a fresh independent test.  No hyperparameter tuning occurs.
"""

from __future__ import annotations

from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from ship_orders_forecasting.modeling import metrics  # noqa: E402
from ship_orders_forecasting.order_availability import publication_dates  # noqa: E402
from ship_orders_forecasting.publication_lag_forecast import (  # noqa: E402
    ORDER_LAGS, data_cutoff, direct_grid, evaluate_period, month_end,
    predict_at, select_candidates,
)


def _existing_audit():
    path = ROOT / "scripts" / "분석" / "2026_독립검증.py"
    spec = spec_from_file_location("ship_orders_existing_2026_audit", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def full_candidate_set(external: list[str]) -> dict[str, list[str]]:
    """Start from every available order and external candidate, without preset subsets."""
    return {"전체 후보": list(dict.fromkeys([*ORDER_LAGS.values(), *external]))}


def _score(rows: list[dict]) -> dict | None:
    if not rows:
        return None
    score = metrics([row["실제"] for row in rows], [row["예측"] for row in rows])
    return {"평가예측건수": len(rows), **{key: value for key, value in score.items()
                                   if key in {"sMAPE", "MAE", "RMSE"}}}


def _jsonable(value):
    if isinstance(value, pd.Timestamp):
        return value.strftime("%Y-%m")
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None
    raise TypeError(f"Cannot serialize {type(value)}")


def run_analysis(ship_type: str = "컨테이너선") -> dict:
    """Compute the selection and forecasts in memory for the notebook."""
    audit = _existing_audit()
    if ship_type not in audit.RULES.SHIP_TYPES:
        raise ValueError(f"알 수 없는 선종: {ship_type}")
    sources = audit.inputs()
    frame, old_lagged = audit.evaluation_frame(ship_type, sources)
    external = [name.rsplit("_", 1)[0] for name in old_lagged]
    candidates = full_candidate_set(external)
    raw = pd.read_csv(audit.RULES.RAW_ORDERS_PATH, encoding="utf-8-sig",
                      dtype=str, keep_default_na=False)
    recorded_publications = publication_dates(raw, audit.RULES.RAW_VESSEL_TYPES[ship_type])
    # Retrospective data-complete assumption: retain D=C-3, but do not reject
    # an observed order merely because its linked article was posted later.
    published = pd.Series(pd.NaT, index=recorded_publications.index,
                          dtype="datetime64[ns]")
    grid = direct_grid(frame, external, published)
    current_origin = pd.Timestamp("2026-10-30")
    six_origins = pd.period_range(current_origin.to_period("M") - 5,
                                  periods=6, freq="M")
    results = []
    all_business_rows = []
    for horizon in (6,):
        print(f"{ship_type} h+{horizon}: 공개시차를 적용한 월별 순차 검증", flush=True)
        selected, ranked = select_candidates(grid, candidates, horizon)
        baseline_rows = []
        baseline_definitions = {
            "확보월 수주용량 유지": [ORDER_LAGS[1]],
            "확보월까지 3개월 수주용량 평균": [ORDER_LAGS[1], ORDER_LAGS[2], ORDER_LAGS[3]],
        }
        for name, columns in baseline_definitions.items():
            scores = {}
            for year, months in selected["fold별기준월"].items():
                actual, predicted = [], []
                for month in months:
                    row = grid.loc[(month_end(pd.Timestamp(month + "-01")), horizon)]
                    actual.append(float(row["실제"]))
                    predicted.append(float(row[columns].mean()))
                scores[year] = metrics(actual, predicted)["sMAPE"]
            values = np.array(list(scores.values()))
            baseline_rows.append({"기준모형": name, "사용피처": columns,
                                  "fold별sMAPE": scores,
                                  "평균sMAPE": float(values.mean()),
                                  "표준편차": float(values.std(ddof=1))})
        selection_reference, _ = evaluate_period(
            grid, horizon, selected, first="2022-01", last="2024-12")
        selection_reference = [row for row in selection_reference
                               if row["목표월"] <= pd.Timestamp("2025-03-01")]
        diagnostic, skipped = evaluate_period(grid, horizon, selected)
        if horizon >= 4:
            all_business_rows.extend(diagnostic)
        future = predict_at(grid, horizon, current_origin,
                            selected["피처목록"], selected["모형"])
        # One h+6 rule, applied at six consecutive historical decision months.
        # February..July cutoff months map to August..January target months.
        forecast_line = []
        for period in six_origins:
            point = predict_at(grid, horizon, period.to_timestamp(),
                               selected["피처목록"], selected["모형"])
            if point is None:
                forecast_line.append({"예측기준일": month_end(period.to_timestamp()),
                                      "데이터마감월": data_cutoff(period.to_timestamp()),
                                      "목표월": data_cutoff(period.to_timestamp()) + pd.DateOffset(months=horizon),
                                      "선행개월": horizon, "예측": None,
                                      "상태": "입력 결측으로 예측 불가"})
            else:
                forecast_line.append({**{key: value for key, value in point.items()
                                         if key != "실제"}, "상태": "예측 가능"})
        # Descriptive scatterplots must use the same as-of feature rows as
        # forecasting, not contemporaneous columns from the master table.
        scatter_rows = []
        for origin, row in grid.xs(horizon, level="선행개월").iterrows():
            if row["목표월"] != row["데이터마감월"] + pd.DateOffset(months=horizon):
                raise AssertionError("산점도 자료의 입력월과 h+6 목표월이 일치하지 않습니다")
            if (pd.isna(row["실제"]) or row["목표월"] > pd.Timestamp("2024-10-01")
                    or row[selected["피처목록"]].isna().any()):
                continue
            scatter_rows.append({"예측기준일": origin,
                                 "데이터마감월": row["데이터마감월"],
                                 "목표월": row["목표월"],
                                 "실제": float(row["실제"]),
                                 **{name: float(row[name]) for name in selected["피처목록"]}})
        result = {
            "선행개월": horizon, "현재이후": horizon >= 4,
            "선택": selected, "변수조합비교": ranked,
            "기준모형비교": baseline_rows,
            "선택구간순차예측_참고": selection_reference,
            "피처산점도자료": scatter_rows,
            "개발진단": {
                "전체": _score(diagnostic),
                "2025": _score([row for row in diagnostic if row["예측기준일"].year == 2025]),
                "2026": _score([row for row in diagnostic if row["예측기준일"].year == 2026]),
                "미평가기준월": skipped,
                "월별예측": diagnostic,
            },
            "2026-10-30_운영예측": ({key: value for key, value in future.items()
                                   if key != "실제"} if future is not None else None),
            "2026-10_6개월전망선": forecast_line,
        }
        results.append(result)
    analysis = {
        "선종": ship_type, "단위": audit.RULES.TARGET_UNITS[ship_type],
        "운영기준월": "2026-10", "최신허용데이터월": data_cutoff(current_origin).strftime("%Y-%m"),
        "공통공개시차개월": 3,
        "선행개월정의": "같은 h+6 규칙을 2026-05~10 매월 말에 적용. 입력 마감월 2026-02~07의 각 D+6은 목표월 2026-08~2027-01. 2026-10 월말에 사용 가능한 최신 자료는 2026-07.",
        "모형": "기존 1차 선형회귀·2차 다항 Ridge·랜덤 포레스트 기본 설정만 비교. 하이퍼파라미터 튜닝 없음.",
        "선택기간": "2022~2024 월별 이동 origin의 3개 연도 fold. 모든 선택 목표 라벨은 2025-01 첫 진단 origin의 데이터마감월 2024-10 이내.",
        "진단기간": "2025-01~2026-10 origin에서 관측된 목표월만 평가; 과거에 결과를 이미 확인했으므로 독립 테스트가 아님.",
        "가용성한계": "공통 D=C-3 자료월 경계는 유지하고 개별 수주실적 게시일 제한은 적용하지 않음. 사후 확보한 관측값도 포함될 수 있으며 당시 수정 전 빈티지는 보존되지 않음. 실제 관측값이 없는 월은 0이나 직전값으로 채우지 않음.",
        "계열내선택": "미국 TPU 2개·세계 거시 3개·지정학 3개 후보군은 매 예측기준일에 해당 시점까지 알려진 학습 라벨과 입력값만으로 상관계수 절댓값 최대 1개를 실제 모형에 투입. 예측 행의 상관선택 필드에 기록.",
        "물동량": "2026년 글로벌 합계 불완전으로 후보에서 제외",
        "후보군": candidates,
        "h6_개발진단": {
            "전체": _score(all_business_rows),
            "2025": _score([row for row in all_business_rows if row["예측기준일"].year == 2025]),
            "2026": _score([row for row in all_business_rows if row["예측기준일"].year == 2026]),
            "해석": "매월 갱신한 기준월에서 각각 여섯 달 뒤 한 달을 예측한 점수. 2025~2026은 독립 테스트가 아님.",
        },
        "결과": results,
    }
    return json.loads(json.dumps(analysis, ensure_ascii=False, default=_jsonable))


if __name__ == "__main__":
    result = run_analysis()
    selected = result["결과"][0]["선택"]
    print(f"완료: {selected['모형']} · 선택 피처 {len(selected['피처목록'])}개")
