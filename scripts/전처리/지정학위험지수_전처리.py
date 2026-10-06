"""지정학 위험 원본 엑셀에서 선택한 월별 원본 지수 4개만 추출한다.

원본은 변경하지 않는다. 시차, 이동평균, 변화율 등 파생변수는 만들지 않는다.
출력 컬럼은 기준월, GPR, GPRT, GPRA의 한글명으로 고정한다.
가공본은 분석 시작월인 2015-01부터 최신 원본 월까지 연속된 월만 저장한다.

실행 예시
    python scripts/전처리/지정학위험지수_전처리.py
    python scripts/전처리/지정학위험지수_전처리.py --check-only
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_PATH = PROJECT_ROOT / "data" / "raw" / "위험지수_모든컬럼.xlsx"
OUTPUT_PATH = PROJECT_ROOT / "data" / "processed" / "공통" / "지정학위험지수(월).csv"
ANALYSIS_START_MONTH = "2015-01"

COLUMN_MAP = {
    "month": "기준월",
    "GPR": "GPR(세계지정학위험지수)",
    "GPRT": "GPRT(지정학위협지수)",
    "GPRA": "GPRA(지정학행동지수)",
}
OUTPUT_COLUMNS = list(COLUMN_MAP.values())


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="지정학 위험 원본에서 선택한 4개 월별 지수만 추출합니다."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="저장하지 않고 기존 가공본과 현재 생성 결과가 일치하는지 검사합니다.",
    )
    return parser.parse_args()


def build_processed() -> pd.DataFrame:
    source = pd.read_excel(SOURCE_PATH, sheet_name="data")
    missing = [column for column in COLUMN_MAP if column not in source.columns]
    if missing:
        raise KeyError(f"{SOURCE_PATH.name} 필수 컬럼 누락: {missing}")

    processed = source[list(COLUMN_MAP)].rename(columns=COLUMN_MAP).copy()
    raw_month = processed["기준월"].astype("string").str.strip()
    try:
        parsed_month = pd.to_datetime(raw_month, format="%Y-%m", errors="raise")
    except ValueError as error:
        raise ValueError("month 컬럼은 YYYY-MM 형식이어야 합니다.") from error
    processed["기준월"] = parsed_month.dt.to_period("M").astype(str)

    if processed["기준월"].duplicated().any():
        duplicated = processed.loc[
            processed["기준월"].duplicated(keep=False), "기준월"
        ].unique()
        raise ValueError(f"기준월 중복: {', '.join(duplicated[:10])}")

    feature_columns = OUTPUT_COLUMNS[1:]
    for column in feature_columns:
        processed[column] = pd.to_numeric(processed[column], errors="raise")
    if processed[feature_columns].isna().any().any():
        missing_months = processed.loc[
            processed[feature_columns].isna().any(axis=1), "기준월"
        ]
        raise ValueError(f"선택 지수 결측 월: {', '.join(missing_months.head(10))}")

    processed = processed.loc[processed["기준월"].ge(ANALYSIS_START_MONTH), OUTPUT_COLUMNS]
    processed = processed.sort_values("기준월").reset_index(drop=True)
    if processed.empty or processed.at[0, "기준월"] != ANALYSIS_START_MONTH:
        raise ValueError(f"분석 시작월 {ANALYSIS_START_MONTH}의 지정학위험지수가 없습니다.")
    expected_months = pd.period_range(
        ANALYSIS_START_MONTH, processed.at[len(processed) - 1, "기준월"], freq="M"
    ).astype(str)
    if processed["기준월"].tolist() != expected_months.tolist():
        raise ValueError("지정학위험지수 출력 월이 연속적이지 않습니다.")
    return processed


def save_processed(processed: pd.DataFrame) -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    temporary = OUTPUT_PATH.with_suffix(OUTPUT_PATH.suffix + ".tmp")
    processed.to_csv(
        temporary,
        index=False,
        encoding="utf-8-sig",
        lineterminator="\n",
    )
    temporary.replace(OUTPUT_PATH)


def check_existing(processed: pd.DataFrame) -> None:
    if not OUTPUT_PATH.exists():
        raise FileNotFoundError(f"비교할 기존 가공본이 없습니다: {OUTPUT_PATH}")
    existing = pd.read_csv(OUTPUT_PATH, encoding="utf-8-sig")
    if list(existing.columns) != OUTPUT_COLUMNS:
        raise ValueError(f"{OUTPUT_PATH.name} 컬럼 구성이 전처리 규칙과 다릅니다.")
    try:
        pd.testing.assert_frame_equal(
            processed,
            existing,
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            f"{OUTPUT_PATH.name} 내용이 현재 원본과 전처리 규칙에 맞지 않습니다."
        ) from error


def main() -> None:
    args = parse_args()
    processed = build_processed()
    if args.check_only:
        check_existing(processed)
        status = "일치"
    else:
        save_processed(processed)
        check_existing(processed)
        status = "생성 완료"

    print(
        pd.DataFrame(
            [{
                "상태": status,
                "행": len(processed),
                "시작월": processed["기준월"].min(),
                "종료월": processed["기준월"].max(),
                "결측값": int(processed[OUTPUT_COLUMNS[1:]].isna().sum().sum()),
                "출력파일": str(OUTPUT_PATH),
            }]
        ).to_string(index=False)
    )


if __name__ == "__main__":
    main()

