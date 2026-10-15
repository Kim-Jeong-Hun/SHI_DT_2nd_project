"""글로벌 HSFO(IFO380)·VLSFO 일별 가격을 월평균으로 집계한다.

출처
- USDA Agricultural Transportation Open Data / Ship & Bunker
  https://agtransport.usda.gov/resource/4v3x-mj86.json
- 2025-10 VLSFO 공개 월평균 보완값(Ship & Bunker, G20):
  https://shipandbunker.com/news/apac/214905-analysis-singapore-october-bunker-sales-dropped-15-year-on-year

원칙
- 파생변수를 만들지 않는다.
- 2015-01부터 달력 월을 유지하되 공개 글로벌 값이 없는 구간은 결측으로 둔다.
- 월평균은 일별 관측이 10일 이상일 때만 채택한다.
- VLSFO 출시 이전 값은 0·보간·대체값으로 채우지 않는다.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


API_ENDPOINT = "https://agtransport.usda.gov/resource/4v3x-mj86.json"
START_MONTH = pd.Period("2015-01", freq="M")
MIN_DAILY_OBSERVATIONS = 10

HSFO_SOURCE_COLUMN = "intermdiate_fuel_oil_380cst"
VLSFO_SOURCE_COLUMN = "vlsfo_fuel_oil_imo_2020_grade_0_5"
HSFO_OUTPUT_COLUMN = "HSFO(IFO380) 월평균 가격(USD/mt)"
VLSFO_OUTPUT_COLUMN = "VLSFO 월평균 가격(USD/mt)"

# USDA 공개 API에 2025-10 자료가 누락되어 같은 G20 지수의 공개 월평균으로 보완한다.
# API에 월별 일자료가 추가되면 아래 값보다 API 집계값을 우선한다.
PUBLIC_MONTHLY_SUPPLEMENTS = {
    pd.Period("2025-10", freq="M"): {VLSFO_OUTPUT_COLUMN: 499.0},
}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "archive" / "선박용 벙커유 가격(월).csv"


def fetch_daily_prices() -> pd.DataFrame:
    params = {
        "$select": f"day,{HSFO_SOURCE_COLUMN},{VLSFO_SOURCE_COLUMN}",
        "$where": "day >= '2015-01-01T00:00:00.000'",
        "$order": "day ASC",
        "$limit": "50000",
    }
    url = f"{API_ENDPOINT}?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "ship-orders-forecasting/1.0"})
    with urlopen(request, timeout=60) as response:
        records = json.load(response)

    if not records:
        raise RuntimeError("USDA 글로벌 벙커유 API에서 자료를 받지 못했습니다.")

    daily = pd.DataFrame.from_records(records)
    required = {"day", HSFO_SOURCE_COLUMN, VLSFO_SOURCE_COLUMN}
    missing = required.difference(daily.columns)
    if missing:
        raise RuntimeError(f"USDA API 필수 컬럼이 없습니다: {sorted(missing)}")

    daily["day"] = pd.to_datetime(daily["day"], errors="coerce")
    daily[HSFO_SOURCE_COLUMN] = pd.to_numeric(daily[HSFO_SOURCE_COLUMN], errors="coerce")
    daily[VLSFO_SOURCE_COLUMN] = pd.to_numeric(daily[VLSFO_SOURCE_COLUMN], errors="coerce")
    return daily.dropna(subset=["day"]).sort_values("day")


def aggregate_monthly(daily: pd.DataFrame) -> pd.DataFrame:
    working = daily.copy()
    working["연월"] = working["day"].dt.to_period("M")

    monthly_parts: dict[str, pd.Series] = {}
    for source_column, output_column in (
        (HSFO_SOURCE_COLUMN, HSFO_OUTPUT_COLUMN),
        (VLSFO_SOURCE_COLUMN, VLSFO_OUTPUT_COLUMN),
    ):
        grouped = working.groupby("연월")[source_column]
        mean = grouped.mean()
        count = grouped.count()
        monthly_parts[output_column] = mean.where(count >= MIN_DAILY_OBSERVATIONS)

    monthly = pd.DataFrame(monthly_parts)
    latest_month = max(
        monthly.index.max(),
        max(PUBLIC_MONTHLY_SUPPLEMENTS),
    )
    full_index = pd.period_range(START_MONTH, latest_month, freq="M")
    monthly = monthly.reindex(full_index)

    for month, values in PUBLIC_MONTHLY_SUPPLEMENTS.items():
        for column, value in values.items():
            if pd.isna(monthly.loc[month, column]):
                monthly.loc[month, column] = value

    monthly = monthly.round(2)
    monthly.index.name = "연월"
    result = monthly.reset_index()
    result["연월"] = result["연월"].astype(str)
    return result


def validate(result: pd.DataFrame) -> None:
    expected_columns = ["연월", HSFO_OUTPUT_COLUMN, VLSFO_OUTPUT_COLUMN]
    if result.columns.tolist() != expected_columns:
        raise ValueError(f"출력 컬럼 불일치: {result.columns.tolist()}")
    if result.empty or result.iloc[0]["연월"] != "2015-01":
        raise ValueError("출력 시작월은 2015-01이어야 합니다.")
    if result["연월"].duplicated().any():
        raise ValueError("연월 중복이 있습니다.")

    periods = pd.PeriodIndex(result["연월"], freq="M")
    expected_periods = pd.period_range(periods.min(), periods.max(), freq="M")
    if not periods.equals(expected_periods):
        raise ValueError("월 시계열에 누락된 달이 있습니다.")

    before_vlsfo = periods < pd.Period("2019-10", freq="M")
    if result.loc[before_vlsfo, VLSFO_OUTPUT_COLUMN].notna().any():
        raise ValueError("VLSFO 출시 이전 구간에 값이 들어갔습니다.")
    if result.loc[periods < pd.Period("2019-02", freq="M"), HSFO_OUTPUT_COLUMN].notna().any():
        raise ValueError("충분한 글로벌 HSFO 관측이 없는 초기 구간에 값이 들어갔습니다.")
    if any("가격차" in column or "spread" in column.lower() for column in result.columns):
        raise ValueError("파생 가격차 컬럼이 포함되어 있습니다.")


def load_output() -> pd.DataFrame:
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"검증할 파일이 없습니다: {OUTPUT_PATH}")
    return pd.read_csv(OUTPUT_PATH, encoding="utf-8-sig")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-only", action="store_true", help="기존 출력 파일만 검증")
    args = parser.parse_args()

    if args.check_only:
        result = load_output()
    else:
        result = aggregate_monthly(fetch_daily_prices())
        validate(result)
        OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(OUTPUT_PATH, index=False, encoding="utf-8-sig", na_rep="")

    validate(result)
    hsfo = result[HSFO_OUTPUT_COLUMN].notna()
    vlsfo = result[VLSFO_OUTPUT_COLUMN].notna()
    print(f"검증 완료: {OUTPUT_PATH}")
    print(f"전체 월: {len(result)} ({result['연월'].iloc[0]}~{result['연월'].iloc[-1]})")
    print(f"HSFO 유효 월: {hsfo.sum()}, {result.loc[hsfo, '연월'].min()}~{result.loc[hsfo, '연월'].max()}")
    print(f"VLSFO 유효 월: {vlsfo.sum()}, {result.loc[vlsfo, '연월'].min()}~{result.loc[vlsfo, '연월'].max()}")


if __name__ == "__main__":
    main()
