"""raw/물동량의 원자료 CSV 10개를 보류용 월별 CSV로 직접 집계한다.

2026년 세계 합계가 불완전하므로 출력은 processed/archive에만 보관하고
마스터·모델 입력에는 연결하지 않는다.

집계 기준은 기존 팀 취합본의 변수정보 시트에 기록된 정의를 따른다.
가공 XLSX는 입력으로 사용하지 않는다. --check-only는 원자료 재집계값과
현재 processed CSV를 비교하며 파일을 수정하지 않는다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw" / "물동량"
ARCHIVE_DIR = PROJECT_ROOT / "data" / "processed" / "archive" / "물동량_사용보류_20261005"
OUTPUT_CSV = ARCHIVE_DIR / "주요 원자재 물동량(월).csv"
PROVISIONAL_2026_CSV = ARCHIVE_DIR / "주요 원자재 물동량(2026잠정).csv"
FIRST_MONTH = "2015-01"
LAST_MONTH = "2025-12"
MONTHS = pd.period_range(FIRST_MONTH, LAST_MONTH, freq="M").astype(str)

# JODI: KBBL/1,000=백만배럴, M3/1,000=십억m³(원자료 M3는 백만m³ 단위).
JODI_SERIES = {
    "세계 원유 수입량(백만배럴)": (
        "원유통계데이터.csv", "CRUDEOIL", "TOTIMPSB", "KBBL"
    ),
    "세계 LNG 수입량(십억m³)": (
        "천연가스통계데이터.csv", "NATGAS", "IMPLNG", "M3"
    ),
}

# UN Comtrade: 순중량이 결측일 때만 양수 총중량으로 대체한다.
# 순중량 0은 관측된 0이므로 총중량으로 대체하지 않는다.
COMTRADE_SERIES = {
    "세계 대두유 수입량(백만톤)": ("대두유 무역량.csv", "1507", "M", None),
    "세계 면화 수입량(백만톤)": ("면화 무역량.csv", "5201", "M", None),
    "일본 LNG 수입량(백만톤)": ("일본 LNG 무역량.csv", "271111", "M", "JPN"),
    "세계 천연고무 수입량(백만톤)": ("천연고무 무역량.csv", "4001", "M", None),
    "세계 천연고무 TSR20 수입량(백만톤)": (
        "천연고무 TSR20 무역량.csv", "400122", "M", None
    ),
    "세계 철광석 수입량(백만톤)": ("철광석 무역량.csv", "2601", "M", None),
    "세계 팜유 수입량(백만톤)": ("팜유 무역량.csv", "1511", "M", None),
    "호주 석탄 수출량(백만톤)": ("호주 석탄 무역량.csv", "2701", "X", "AUS"),
}
STANDARD_COLUMNS = ["기준월", *JODI_SERIES.keys(), *COMTRADE_SERIES.keys()]


def require_source(filename: str) -> Path:
    source = RAW_DIR / filename
    if not source.is_file():
        raise FileNotFoundError(f"물동량 원자료가 없습니다: {source}")
    return source


def read_jodi(filename: str, product: str, flow: str, unit: str,
              start_month: str = FIRST_MONTH, end_month: str = LAST_MONTH) -> pd.Series:
    source = require_source(filename)
    columns = [
        "TIME_PERIOD", "ENERGY_PRODUCT", "FLOW_BREAKDOWN",
        "UNIT_MEASURE", "OBS_VALUE",
    ]
    monthly = pd.Series(dtype="float64")
    for chunk in pd.read_csv(source, usecols=columns, chunksize=200_000):
        selected = chunk.loc[
            chunk["ENERGY_PRODUCT"].eq(product)
            & chunk["FLOW_BREAKDOWN"].eq(flow)
            & chunk["UNIT_MEASURE"].eq(unit)
            & chunk["TIME_PERIOD"].between(start_month, end_month),
            ["TIME_PERIOD", "OBS_VALUE"],
        ].copy()
        selected["OBS_VALUE"] = pd.to_numeric(selected["OBS_VALUE"], errors="coerce")
        selected = selected.dropna(subset=["OBS_VALUE"])
        sums = selected.groupby("TIME_PERIOD")["OBS_VALUE"].sum()
        monthly = monthly.add(sums, fill_value=0)
    if monthly.empty:
        raise ValueError(f"{source.name}: {product}/{flow}/{unit} 관측값이 없습니다.")
    return monthly / 1_000


def read_comtrade(
    filename: str, commodity: str, flow: str, reporter: str | None,
    start_month: str = FIRST_MONTH, end_month: str = LAST_MONTH,
) -> pd.Series:
    source = require_source(filename)
    columns = [
        "period", "reporterISO", "flowCode", "partnerCode", "partner2Code",
        "cmdCode", "customsCode", "motCode", "netWgt", "grossWgt",
    ]
    data = pd.read_csv(source, usecols=columns, dtype={"cmdCode": "string"})
    selected = data.loc[
        data["cmdCode"].eq(commodity)
        & data["flowCode"].eq(flow)
        & data["partnerCode"].eq(0)
        & data["partner2Code"].eq(0)
        & data["customsCode"].eq("C00")
        & data["motCode"].eq(0)
    ].copy()
    if reporter is not None:
        selected = selected.loc[selected["reporterISO"].eq(reporter)].copy()
    if selected.empty:
        raise ValueError(f"{source.name}: {commodity}/{flow}/{reporter} 관측값이 없습니다.")
    period = selected["period"].astype(str)
    if not period.str.fullmatch(r"\d{6}").all():
        raise ValueError(f"{source.name}: period가 YYYYMM 형식이 아닙니다.")
    selected["기준월"] = period.str[:4] + "-" + period.str[4:]
    selected = selected.loc[selected["기준월"].between(start_month, end_month)]
    net = pd.to_numeric(selected["netWgt"], errors="coerce")
    gross = pd.to_numeric(selected["grossWgt"], errors="coerce")
    selected["중량_kg"] = net.where(net.notna(), gross.where(gross.gt(0), 0))
    return selected.groupby("기준월")["중량_kg"].sum() / 1_000_000_000


def build_processed() -> pd.DataFrame:
    result = pd.DataFrame({"기준월": MONTHS})
    for column, args in JODI_SERIES.items():
        result[column] = result["기준월"].map(read_jodi(*args))
    for column, args in COMTRADE_SERIES.items():
        result[column] = result["기준월"].map(read_comtrade(*args))
    if result["기준월"].duplicated().any():
        raise ValueError("물동량 기준월이 중복되었습니다.")
    if result[STANDARD_COLUMNS[1:]].isna().any().any():
        missing = result.columns[result.isna().any()].tolist()
        raise ValueError(f"물동량 결측 열: {missing}")
    if result[STANDARD_COLUMNS[1:]].lt(0).any().any():
        raise ValueError("물동량에 음수가 있습니다.")
    return result[STANDARD_COLUMNS]


def build_provisional_2026() -> pd.DataFrame:
    """Keep currently reported 2026 trade totals separate from the model input.

    Late country submissions can revise worldwide sums. Missing months remain
    NaN, and even present totals are not automatically deemed model-ready.
    """
    start, end = "2026-01", "2026-08"
    result = pd.DataFrame({"기준월": pd.period_range(start, end, freq="M").astype(str)})
    for column, (filename, product, flow, unit) in JODI_SERIES.items():
        source = "원유통계데이터_2026.csv" if product == "CRUDEOIL" else filename
        result[column] = result["기준월"].map(
            read_jodi(source, product, flow, unit, start, end)
        )
    for column, (filename, commodity, flow, reporter) in COMTRADE_SERIES.items():
        source = filename.replace(".csv", "_2026.csv")
        result[column] = result["기준월"].map(
            read_comtrade(source, commodity, flow, reporter, start, end)
        )
    result["자료상태"] = "국가별 보고 지연이 반영되지 않은 잠정 글로벌 합계; 모델 미연결"
    return result[[*STANDARD_COLUMNS, "자료상태"]]


def check_existing(expected: pd.DataFrame) -> None:
    if not OUTPUT_CSV.is_file():
        raise FileNotFoundError(f"검사할 CSV가 없습니다: {OUTPUT_CSV}")
    actual = pd.read_csv(OUTPUT_CSV, encoding="utf-8-sig")
    if list(actual.columns) != list(expected.columns):
        raise ValueError("CSV 열 구성이 raw 재집계 결과와 다릅니다.")
    pd.testing.assert_frame_equal(
        actual, expected, check_dtype=False, check_exact=False,
        rtol=1e-12, atol=1e-12,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-only", action="store_true",
        help="CSV를 저장하지 않고 raw 재집계 결과와 기존 CSV를 비교합니다.",
    )
    parser.add_argument(
        "--provisional-2026", action="store_true",
        help="기존 모델 입력과 분리된 2026년 잠정 집계 CSV를 만듭니다.",
    )
    args = parser.parse_args()
    result = build_provisional_2026() if args.provisional_2026 else build_processed()
    output = PROVISIONAL_2026_CSV if args.provisional_2026 else OUTPUT_CSV
    if args.check_only:
        if args.provisional_2026:
            pd.testing.assert_frame_equal(result, pd.read_csv(output, encoding="utf-8-sig"), check_dtype=False)
        else:
            check_existing(result)
        action = "검증"
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        result.to_csv(output, index=False, encoding="utf-8-sig")
        action = "저장"
    print(
        f"{action}: {output.name} | {len(result)}개월 | "
        f"{len(result.columns) - 1}개 물동량 변수 | "
        f"{result['기준월'].iloc[0]}~{result['기준월'].iloc[-1]}"
    )


if __name__ == "__main__":
    main()
