"""싱가포르 MPA 월별 벙커유 총판매량을 내려받아 분석용 CSV를 만든다.

출처
- Singapore Government Data / Maritime and Port Authority of Singapore
- Bunker Sales Total, Monthly
- https://data.gov.sg/datasets/d_89d2874dad74a273270369334f1e7d28/view

원칙
- 공식 API 응답은 영문 컬럼 그대로 raw에 보존한다.
- processed에는 검증된 2015-01~2026-08 월별 값을 사용한다.
- 원자료 값은 연간 공식 발표치와 대조하면 천 톤 단위이므로 단위를 컬럼명에 표시한다.
- 합계·증감률 등 파생변수는 만들지 않는다.
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd


DATASET_ID = "d_89d2874dad74a273270369334f1e7d28"
API_ENDPOINT = "https://data.gov.sg/api/action/datastore_search"
START_MONTH = "2015-01"
END_MONTH = "2026-08"
OUTPUT_COLUMN = "싱가포르_벙커유판매량_천톤"

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "BunkerSalesTotalMonthly.csv"
PROCESSED_PATH = (
    PROJECT_ROOT / "data" / "processed" / "공통" / "싱가포르 벙커유 판매량(월).csv"
)


def fetch_all_records() -> pd.DataFrame:
    records: list[dict[str, object]] = []
    offset = 0
    limit = 1000

    while True:
        query = urlencode(
            {"resource_id": DATASET_ID, "limit": limit, "offset": offset}
        )
        request = Request(
            f"{API_ENDPOINT}?{query}",
            headers={"User-Agent": "ship-orders-forecasting/1.0"},
        )
        with urlopen(request, timeout=60) as response:
            payload = json.load(response)

        if not payload.get("success"):
            raise RuntimeError("싱가포르 공공데이터 API 요청이 실패했습니다.")
        result = payload["result"]
        page = result.get("records", [])
        records.extend(page)
        offset += len(page)
        if not page or offset >= int(result["total"]):
            break

    raw = pd.DataFrame.from_records(records)
    required = ["_id", "month", "bunker_sales"]
    missing = [column for column in required if column not in raw.columns]
    if missing:
        raise RuntimeError(f"싱가포르 원자료 필수 컬럼 누락: {missing}")
    raw = raw[required].copy()
    raw["_id"] = pd.to_numeric(raw["_id"], errors="raise").astype(int)
    raw = raw.sort_values("_id").reset_index(drop=True)
    if raw["_id"].duplicated().any() or raw["month"].duplicated().any():
        raise ValueError("싱가포르 원자료에 중복 ID 또는 중복 월이 있습니다.")
    return raw


def build_processed(raw: pd.DataFrame) -> pd.DataFrame:
    processed = raw.loc[
        raw["month"].between(START_MONTH, END_MONTH), ["month", "bunker_sales"]
    ].rename(
        columns={"month": "기준월", "bunker_sales": OUTPUT_COLUMN}
    )
    processed["기준월"] = pd.to_datetime(
        processed["기준월"], format="%Y-%m", errors="raise"
    ).dt.to_period("M").astype(str)
    processed[OUTPUT_COLUMN] = pd.to_numeric(
        processed[OUTPUT_COLUMN], errors="raise"
    )
    processed = processed.sort_values("기준월").reset_index(drop=True)

    expected_months = pd.period_range(
        START_MONTH, END_MONTH, freq="M"
    ).astype(str).tolist()
    if processed["기준월"].tolist() != expected_months:
        actual = set(processed["기준월"])
        missing = [month for month in expected_months if month not in actual]
        raise ValueError(f"싱가포르 벙커유 판매량 누락 월: {missing}")
    if processed[OUTPUT_COLUMN].isna().any() or processed[OUTPUT_COLUMN].le(0).any():
        raise ValueError("싱가포르 벙커유 판매량에 결측 또는 0 이하 값이 있습니다.")

    # MPA 2024년 공식 연간 발표 54.92백만 톤과 원자료 합계가 일치하는지 확인한다.
    total_2024 = processed.loc[
        processed["기준월"].str.startswith("2024-"), OUTPUT_COLUMN
    ].sum()
    if not 54_800 <= total_2024 <= 55_100:
        raise ValueError(
            "2024년 합계가 MPA 공식 발표 범위와 다릅니다: "
            f"{total_2024:,.2f}천 톤"
        )
    return processed


def save_csv(data: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    data.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(output)


def main() -> None:
    raw = fetch_all_records()
    processed = build_processed(raw)
    save_csv(raw, RAW_PATH)
    save_csv(processed, PROCESSED_PATH)
    print(
        f"원자료 {len(raw)}행 저장: {RAW_PATH}\n"
        f"가공자료 {len(processed)}개월 "
        f"({processed['기준월'].min()}~{processed['기준월'].max()}) 저장: "
        f"{PROCESSED_PATH}"
    )


if __name__ == "__main__":
    main()
