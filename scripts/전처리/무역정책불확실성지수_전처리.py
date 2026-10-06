"""공식 월별 무역정책 불확실성 원자료를 내려받아 하나의 한글 표로 통합한다.

원자료는 data/raw에 원형 그대로 보존한다. 출력은 2015-01~2026-08의
월별 원지수만 포함하며 시차, 이동평균, 변화율 같은 파생변수는 만들지 않는다.

실행 예시
    python scripts/전처리/무역정책불확실성지수_전처리.py
    python scripts/전처리/무역정책불확실성지수_전처리.py --skip-download
    python scripts/전처리/무역정책불확실성지수_전처리.py --check-only
"""

from __future__ import annotations

import argparse
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_DIR = PROJECT_ROOT / "data" / "raw"
OUTPUT_PATH = (
    PROJECT_ROOT / "data" / "processed" / "공통" / "무역정책불확실성지수(월).csv"
)

START_MONTH = pd.Period("2015-01", freq="M")
END_MONTH = pd.Period("2026-08", freq="M")

SOURCES = {
    "fred": {
        "url": "https://fred.stlouisfed.org/graph/fredgraph.csv?id=EPUTRADE",
        "path": RAW_DIR / "FRED_EPUTRADE.csv",
    },
    "caldara": {
        "url": "https://www.matteoiacoviello.com/tpu_files/tpu_web_latest.xlsx",
        "path": RAW_DIR / "Caldara_TPU.xlsx",
    },
    "china": {
        "url": "https://policyuncertainty.com/media/China_Mainland_Paper_EPU.xlsx",
        "path": RAW_DIR / "China_Mainland_Paper_EPU.xlsx",
    },
}

OUTPUT_COLUMNS = [
    "기준월",
    "미국TPU(EPUTRADE 무역정책불확실성지수)",
    "미국TPU(Caldara 무역정책불확실성지수)",
    "중국TPU(무역정책불확실성지수)",
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="공식 무역정책 불확실성 월별 원자료를 내려받아 통합합니다."
    )
    parser.add_argument(
        "--skip-download",
        action="store_true",
        help="기존 raw 원자료를 사용하고 다운로드를 생략합니다.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="저장하지 않고 기존 가공본이 현재 raw 원자료와 일치하는지 검사합니다.",
    )
    return parser.parse_args()


def download_file(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".download")
    request = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(request, timeout=120) as response:
        payload = response.read()
    if len(payload) < 100:
        raise ValueError(f"다운로드 파일이 비정상적으로 작습니다: {url}")
    if destination.suffix == ".xlsx" and not payload.startswith(b"PK"):
        raise ValueError(f"Excel 파일 형식이 아닙니다: {url}")
    temporary.write_bytes(payload)
    temporary.replace(destination)


def download_sources() -> None:
    for source in SOURCES.values():
        download_file(source["url"], source["path"])


def normalize_month(values: pd.Series) -> pd.Series:
    parsed = pd.to_datetime(values, errors="raise")
    return parsed.dt.to_period("M")


def load_fred() -> pd.DataFrame:
    source = pd.read_csv(SOURCES["fred"]["path"])
    required = {"observation_date", "EPUTRADE"}
    if not required.issubset(source.columns):
        raise KeyError(f"FRED 원자료 필수 컬럼 누락: {sorted(required - set(source.columns))}")
    return pd.DataFrame({
        "기준월": normalize_month(source["observation_date"]),
        OUTPUT_COLUMNS[1]: pd.to_numeric(source["EPUTRADE"], errors="raise"),
    })


def load_caldara() -> pd.DataFrame:
    source = pd.read_excel(SOURCES["caldara"]["path"], sheet_name="TPU_MONTHLY")
    required = {"DATE", "TPU"}
    if not required.issubset(source.columns):
        raise KeyError(
            f"Caldara 원자료 필수 컬럼 누락: {sorted(required - set(source.columns))}"
        )
    return pd.DataFrame({
        "기준월": normalize_month(source["DATE"]),
        OUTPUT_COLUMNS[2]: pd.to_numeric(source["TPU"], errors="raise"),
    })


def load_china() -> pd.DataFrame:
    source = pd.read_excel(SOURCES["china"]["path"], sheet_name="TPU 2000 onwards")
    required = {"year", "month", "TPU"}
    if not required.issubset(source.columns):
        raise KeyError(
            f"중국 TPU 원자료 필수 컬럼 누락: {sorted(required - set(source.columns))}"
        )
    month = pd.to_datetime(
        {"year": source["year"], "month": source["month"], "day": 1},
        errors="raise",
    ).dt.to_period("M")
    return pd.DataFrame({
        "기준월": month,
        OUTPUT_COLUMNS[3]: pd.to_numeric(source["TPU"], errors="raise"),
    })


def validate_source(data: pd.DataFrame, label: str) -> None:
    if data["기준월"].duplicated().any():
        duplicated = data.loc[data["기준월"].duplicated(keep=False), "기준월"]
        raise ValueError(f"{label} 기준월 중복: {duplicated.astype(str).unique()[:10]}")


def build_processed() -> pd.DataFrame:
    source_tables = [load_fred(), load_caldara(), load_china()]
    for label, data in zip(("FRED", "Caldara", "중국 TPU"), source_tables):
        validate_source(data, label)

    expected = pd.DataFrame({
        "기준월": pd.period_range(START_MONTH, END_MONTH, freq="M")
    })
    processed = expected
    for data in source_tables:
        processed = processed.merge(data, on="기준월", how="left", validate="one_to_one")

    feature_columns = OUTPUT_COLUMNS[1:]
    if processed[feature_columns].isna().any().any():
        missing = processed.loc[
            processed[feature_columns].isna().any(axis=1), "기준월"
        ].astype(str)
        raise ValueError(f"통합표 결측 월: {', '.join(missing.head(12))}")

    processed["기준월"] = processed["기준월"].astype(str)
    expected_count = len(pd.period_range(START_MONTH, END_MONTH, freq="M"))
    if len(processed) != expected_count:
        raise ValueError(f"예상 행 수 {expected_count}와 다릅니다: {len(processed)}")
    return processed[OUTPUT_COLUMNS]


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
            f"{OUTPUT_PATH.name} 내용이 현재 원자료와 전처리 규칙에 맞지 않습니다."
        ) from error


def main() -> None:
    args = parse_args()
    if not args.skip_download and not args.check_only:
        download_sources()

    missing_sources = [
        source["path"] for source in SOURCES.values() if not source["path"].exists()
    ]
    if missing_sources:
        raise FileNotFoundError(f"raw 원자료 누락: {missing_sources}")

    processed = build_processed()
    if args.check_only:
        check_existing(processed)
        status = "일치"
    else:
        save_processed(processed)
        check_existing(processed)
        status = "생성 완료"

    print(pd.DataFrame([{
        "상태": status,
        "행": len(processed),
        "시작월": processed["기준월"].min(),
        "종료월": processed["기준월"].max(),
        "결측값": int(processed[OUTPUT_COLUMNS[1:]].isna().sum().sum()),
        "출력파일": str(OUTPUT_PATH),
    }]).to_string(index=False))


if __name__ == "__main__":
    main()
