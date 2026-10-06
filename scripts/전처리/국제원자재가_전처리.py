"""세계은행 Pink Sheet에서 선종별 원자재 가격 후보를 월별 CSV로 만든다.

전처리 규칙
1. 원본 XLSX는 수정하지 않는다.
2. Monthly Prices와 Monthly Indices 시트에서 지정한 원값만 추출한다.
3. 원자료의 `YYYYMmm` 기간키를 `YYYY-MM` 형식의 `기준월`로 통일한다.
4. `…`와 빈 셀은 결측으로 유지하고 0으로 바꾸지 않는다.
5. 시차, 변화율, 이동평균 등 파생변수는 만들지 않는다.
6. 가공본은 분석 시작월인 2015-01부터 최신 원본 월까지만 남긴다.
7. 2015-01~2025-12 모델 구간에서 선택 피처에 결측이 있으면 저장하지 않는다.
8. 출력은 UTF-8 BOM CSV이며 월 오름차순으로 저장한다.

실행 예시
    python scripts/전처리/국제원자재가_전처리.py
    python scripts/전처리/국제원자재가_전처리.py --check-only
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "세계은행_원자재가격_PinkSheet_월별.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "공통" / "국제원자재가(월).csv"
LEGACY_OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "공통" / "국제유가(월).csv"
ANALYSIS_START_MONTH = "2015-01"

PRICE_COLUMNS = {
    "Crude oil, average": "원유 평균 가격(USD/bbl)",
    "Crude oil, Brent": "브렌트유 가격(USD/bbl)",
    "Crude oil, Dubai": "두바이유 가격(USD/bbl)",
    "Crude oil, WTI": "WTI 가격(USD/bbl)",
    "Coal, Australian": "호주 석탄 가격(USD/mt)",
    "Liquefied natural gas, Japan": "일본 LNG 가격(USD/MMBtu)",
    "Natural gas index": "천연가스 가격지수(2010=100)",
    "Palm oil": "팜유 가격(USD/mt)",
    "Soybean oil": "대두유 가격(USD/mt)",
    "Rubber, TSR20 **": "고무 TSR20 가격(USD/kg)",
    "Cotton, A Index": "면화 A지수(USD/kg)",
    "Iron ore, cfr spot": "철광석 가격(USD/dmtu)",
}

INDEX_COLUMNS = {
    "Non-energy **": "비에너지 원자재 가격지수(2010=100)",
    "Grains": "곡물 가격지수(2010=100)",
    "Fertilizers **": "비료 가격지수(2010=100)",
    "Base Metals (ex. iron ore)": "비철금속 가격지수(2010=100)",
}

MODEL_COLUMNS = [
    "원유 평균 가격(USD/bbl)",
    "호주 석탄 가격(USD/mt)",
    "일본 LNG 가격(USD/MMBtu)",
    "천연가스 가격지수(2010=100)",
    "팜유 가격(USD/mt)",
    "대두유 가격(USD/mt)",
    "고무 TSR20 가격(USD/kg)",
    "면화 A지수(USD/kg)",
    "철광석 가격(USD/dmtu)",
    "비에너지 원자재 가격지수(2010=100)",
    "곡물 가격지수(2010=100)",
    "비료 가격지수(2010=100)",
    "비철금속 가격지수(2010=100)",
]

OUTPUT_COLUMNS = [
    "기준월",
    "연도",
    "월",
    *PRICE_COLUMNS.values(),
    *INDEX_COLUMNS.values(),
    "유효지표수",
    "모델사용가능",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="세계은행 Pink Sheet에서 선종별 국제 원자재 가격 후보를 추출합니다."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="파일을 저장하지 않고 기존 가공 CSV와 일치하는지만 검사합니다.",
    )
    return parser.parse_args()


def normalize_label(value: object) -> str:
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def find_column(raw: pd.DataFrame, header_rows: range, label: str) -> int:
    normalized = normalize_label(label)
    matches = [
        column
        for column in range(raw.shape[1])
        if any(normalize_label(raw.iat[row, column]) == normalized for row in header_rows)
    ]
    if len(matches) != 1:
        raise ValueError(f"{label!r} 열 검색 결과가 1개가 아닙니다: {matches}")
    return matches[0]


def extract_sheet(
    sheet_name: str,
    header_rows: range,
    data_start: int,
    mapping: dict[str, str],
) -> pd.DataFrame:
    raw = pd.read_excel(RAW_PATH, sheet_name=sheet_name, header=None, dtype=object)
    period_raw = raw.iloc[data_start:, 0].astype("string").str.strip()
    valid_period = period_raw.str.fullmatch(r"\d{4}M\d{2}", na=False)
    if not valid_period.any():
        raise ValueError(f"{sheet_name} 시트에서 월별 기간키를 찾지 못했습니다.")

    selected_rows = raw.iloc[data_start:].loc[valid_period.to_numpy()].copy()
    periods = period_raw.loc[valid_period]
    result = pd.DataFrame(
        {
            "기준월": periods.str.replace("M", "-", regex=False).to_numpy(),
        }
    )

    for source_column, output_column in mapping.items():
        column_index = find_column(raw, header_rows, source_column)
        result[output_column] = pd.to_numeric(
            selected_rows.iloc[:, column_index].replace({"…": pd.NA, "..": pd.NA, "": pd.NA}),
            errors="coerce",
        ).to_numpy()

    if result["기준월"].duplicated().any():
        duplicated = result.loc[result["기준월"].duplicated(keep=False), "기준월"]
        raise ValueError(f"{sheet_name} 시트에 중복 월이 있습니다: {duplicated.head().tolist()}")
    return result.sort_values("기준월").reset_index(drop=True)


def build_output() -> pd.DataFrame:
    prices = extract_sheet(
        "Monthly Prices",
        header_rows=range(4, 6),
        data_start=6,
        mapping=PRICE_COLUMNS,
    )
    indices = extract_sheet(
        "Monthly Indices",
        header_rows=range(5, 9),
        data_start=9,
        mapping=INDEX_COLUMNS,
    )
    output = prices.merge(indices, on="기준월", how="left", validate="one_to_one")
    output = output.loc[output["기준월"].ge(ANALYSIS_START_MONTH)].reset_index(drop=True)
    if output.empty or output.at[0, "기준월"] != ANALYSIS_START_MONTH:
        raise ValueError(f"분석 시작월 {ANALYSIS_START_MONTH}의 원자재 자료가 없습니다.")

    parsed_month = pd.to_datetime(output["기준월"], format="%Y-%m", errors="raise")
    expected_months = pd.period_range(
        parsed_month.min().to_period("M"),
        parsed_month.max().to_period("M"),
        freq="M",
    ).astype(str)
    if output["기준월"].tolist() != expected_months.tolist():
        raise ValueError("출력 월이 연속적이지 않습니다.")

    output.insert(1, "연도", parsed_month.dt.year)
    output.insert(2, "월", parsed_month.dt.month)
    value_columns = [*PRICE_COLUMNS.values(), *INDEX_COLUMNS.values()]
    output["유효지표수"] = output[value_columns].notna().sum(axis=1)
    output["모델사용가능"] = output[MODEL_COLUMNS].notna().all(axis=1)
    output = output[OUTPUT_COLUMNS]

    model_window = output.loc[output["기준월"].between(ANALYSIS_START_MONTH, "2025-12")]
    if len(model_window) != 132:
        raise ValueError(f"모델 구간 월 수가 132개월이 아닙니다: {len(model_window)}")
    if model_window[MODEL_COLUMNS].isna().any().any():
        missing = model_window.loc[
            model_window[MODEL_COLUMNS].isna().any(axis=1),
            "기준월",
        ]
        raise ValueError(f"모델 구간 원자재 피처 결측 월: {missing.head(10).tolist()}")
    return output


def save_atomic(data: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    data.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(output)


def check_existing(data: pd.DataFrame, output: Path) -> None:
    if not output.exists():
        raise FileNotFoundError(f"비교할 기존 파일이 없습니다: {output}")
    existing = pd.read_csv(output, encoding="utf-8-sig")
    pd.testing.assert_frame_equal(
        data.reset_index(drop=True),
        existing.reset_index(drop=True),
        check_dtype=False,
        check_exact=False,
        rtol=1e-12,
        atol=1e-12,
    )


def main() -> None:
    args = parse_args()
    output = build_output()
    if args.check_only:
        check_existing(output, OUTPUT_PATH)
        status = "일치"
    else:
        save_atomic(output, OUTPUT_PATH)
        check_existing(output, OUTPUT_PATH)
        if LEGACY_OUTPUT_PATH.exists():
            LEGACY_OUTPUT_PATH.unlink()
        status = "생성 완료"

    print(
        pd.DataFrame(
            [
                {
                    "상태": status,
                    "파일": OUTPUT_PATH.name,
                    "행": len(output),
                    "시작월": output["기준월"].min(),
                    "종료월": output["기준월"].max(),
                    "컬럼": len(output.columns),
                    "모델구간결측": int(
                        output.loc[
                            output["기준월"].between(ANALYSIS_START_MONTH, "2025-12"),
                            MODEL_COLUMNS,
                        ].isna().sum().sum()
                    ),
                }
            ]
        ).to_string(index=False)
    )


if __name__ == "__main__":
    main()
