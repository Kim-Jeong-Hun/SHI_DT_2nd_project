"""선종별 고정 용량대의 신조선가를 월별 분석용 CSV로 전처리한다.

원자료는 수정하지 않는다. 선형 명칭이 달마다 달라질 수 있으므로 용량 범위로
대표 선형을 고른다. 발표가 없는 월은 이전 관측값을 최대 4개월까지 이월하며,
원관측월과 경과월수를 함께 보존한다. 첫 관측 전의 가격은 결측으로 둔다.
컨테이너선 2015-01~2016-05의 도표 추출 추정치는 raw의 D등급과 출처로
기사 관측값과 구분한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "신조선가_월별.csv"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "공통" / "신조선가(글로벌, 월).csv"

# 원자료의 benchmark_name은 다른 용량에도 재사용되므로 capacity_avg로 고정한다.
# price_index에는 0~4처럼 가격지수로 해석하기 어려운 추출값이 섞여 사용하지 않는다.
PRICE_BANDS = {
    "벌크선": ("Bulk Carrier", 175_000, 185_000, "DWT", "케이프사이즈 17.5~18.5만 DWT"),
    "컨테이너선": ("Container", 1_900, 2_050, "TEU", "약 2,000 TEU 컨테이너선"),
    "유조선": ("Oil Tanker", 110_000, 118_000, "DWT", "수에즈막스 11.0~11.8만 DWT"),
}
MAX_CARRY_MONTHS = 4
OUTPUT_COLUMNS = [
    "기준월",
    "선종",
    "대표선형",
    "원자료평균용량",
    "용량단위",
    "신조선가_백만USD",
    "가격원관측월",
    "가격관측경과월수",
    "원자료품질등급",
    "원자료출처ID",
    "원자료출처URL",
]


def build_output() -> pd.DataFrame:
    raw = pd.read_csv(RAW_PATH, encoding="utf-8-sig")
    required = [
        "period", "vessel_type", "capacity_avg", "capacity_unit",
        "benchmark_price_usd", "quality_grade", "source_id", "source_url",
    ]
    missing = set(required).difference(raw.columns)
    if missing:
        raise KeyError(f"{RAW_PATH.name} 필수 컬럼 누락: {sorted(missing)}")

    raw["period"] = pd.to_datetime(raw["period"], format="%Y-%m", errors="raise")
    for column in ("capacity_avg", "benchmark_price_usd"):
        raw[column] = pd.to_numeric(raw[column], errors="raise")
    if raw["benchmark_price_usd"].isna().any() or raw["benchmark_price_usd"].le(0).any():
        raise ValueError("원자료 신조선가에 결측 또는 0 이하 값이 있습니다.")

    calendar = pd.date_range(raw["period"].min(), raw["period"].max(), freq="MS")
    parts = []
    for ship_type, (raw_type, low, high, unit, label) in PRICE_BANDS.items():
        selected = raw.loc[
            raw["vessel_type"].eq(raw_type)
            & raw["capacity_avg"].between(low, high)
            & raw["capacity_unit"].eq(unit),
            ["period", "capacity_avg", "benchmark_price_usd", "quality_grade", "source_id", "source_url"],
        ].copy()
        if selected.empty:
            raise ValueError(f"{ship_type}의 대표 용량대 가격이 없습니다.")
        if selected["period"].duplicated().any():
            duplicate = selected.loc[selected["period"].duplicated(), "period"].dt.strftime("%Y-%m")
            raise ValueError(f"{ship_type} 대표 용량대에 월별 중복이 있습니다: {duplicate.tolist()[:5]}")

        selected = selected.set_index("period").reindex(calendar)
        selected["가격원관측월"] = pd.Series(calendar, index=calendar).where(
            selected["benchmark_price_usd"].notna()
        )
        carry_columns = [
            "capacity_avg", "benchmark_price_usd", "quality_grade", "source_id",
            "source_url", "가격원관측월",
        ]
        selected[carry_columns] = selected[carry_columns].ffill(limit=MAX_CARRY_MONTHS)
        source_month = selected["가격원관측월"]
        selected["가격관측경과월수"] = (
            (calendar.year * 12 + calendar.month)
            - (source_month.dt.year * 12 + source_month.dt.month)
        ).astype("Int64")
        selected["기준월"] = calendar.strftime("%Y-%m")
        selected["선종"] = ship_type
        selected["대표선형"] = label
        selected["원자료평균용량"] = selected["capacity_avg"]
        selected["용량단위"] = unit
        selected["신조선가_백만USD"] = selected["benchmark_price_usd"] / 1_000_000
        selected["가격원관측월"] = source_month.dt.strftime("%Y-%m")
        selected["원자료품질등급"] = selected["quality_grade"]
        selected["원자료출처ID"] = selected["source_id"]
        selected["원자료출처URL"] = selected["source_url"]
        parts.append(selected[OUTPUT_COLUMNS].reset_index(drop=True))

    output = pd.concat(parts, ignore_index=True).sort_values(["선종", "기준월"])
    if output.duplicated(["선종", "기준월"]).any():
        raise AssertionError("출력에 선종·기준월 중복이 생겼습니다.")
    if output["가격관측경과월수"].dropna().gt(MAX_CARRY_MONTHS).any():
        raise AssertionError("가격 이월 허용기간을 초과했습니다.")
    return output.reset_index(drop=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    output = build_output()
    if args.check_only:
        if not OUTPUT_PATH.exists():
            raise FileNotFoundError(OUTPUT_PATH)
        existing = pd.read_csv(OUTPUT_PATH, encoding="utf-8-sig")
        pd.testing.assert_frame_equal(output, existing, check_dtype=False)
    else:
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT_PATH.with_suffix(".csv.tmp")
        output.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        temporary.replace(OUTPUT_PATH)
    summary = output.groupby("선종", as_index=False).agg(
        전체월=("기준월", "count"),
        가격이용월=("신조선가_백만USD", "count"),
        최대관측경과월=("가격관측경과월수", "max"),
    )
    print(summary.to_string(index=False))


if __name__ == "__main__":
    main()
