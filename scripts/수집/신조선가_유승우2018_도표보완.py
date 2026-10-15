"""유승우(2018) 2쪽 도표에서 읽은 컨테이너선 초기 신조선가를 raw에 추가한다.

도표: 1,850~2,100 TEU Containership Newbuilding Prices, Clarksons Research.
PDF 벡터 경로의 월 중앙 좌표를 읽고 0.25백만 USD 단위로 반올림했다.
이는 월별 원표/실거래가격이 아니라 저해상도 도표에서 복원한 추정치다.

벡터 눈금 교정: 2015-01 x=400.32pt, 2016-01 x=436.86pt,
26백만 USD y=465.21pt, 가격 1백만 USD당 10.08pt.
2016-06~12의 기사 관측값과 비교해 도표 위치와 단위를 검증했다.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "references" / "(유승우, 2018).pdf"
RAW = ROOT / "data" / "raw" / "신조선가_월별.csv"
PDF_SHA256 = "e6ad131bd698fd94373baa89d6b2079e73dd59bc52e799cd6256b8c3a2fe14ed"
SOURCE_URL = "https://file.mk.co.kr/imss/write/20180726114344__00.pdf"
SOURCE_ID = "SK_YU_2018_CHART_P2"

# PDF 벡터 선의 해당 월 중앙값, 백만 USD. 원표의 월별 숫자가 아님.
VECTOR_ESTIMATES = {
    "2015-01": 26.994, "2015-02": 26.994, "2015-03": 26.994,
    "2015-04": 26.981, "2015-05": 26.494, "2015-06": 27.268,
    "2015-07": 27.744, "2015-08": 27.744, "2015-09": 27.543,
    "2015-10": 26.742, "2015-11": 26.494, "2015-12": 26.244,
    "2016-01": 26.244, "2016-02": 26.085, "2016-03": 25.744,
    "2016-04": 25.690, "2016-05": 25.189,
}


def supplement_rows(header: list[str]) -> dict[str, list[str]]:
    expected = {
        "period", "source_id", "vessel_type", "price_index", "benchmark_name",
        "capacity_min", "capacity_max", "capacity_avg", "capacity_unit",
        "benchmark_price_usd", "source_url", "source_page_url",
        "extraction_method", "quality_grade", "raw_excerpt",
    }
    if set(header) != expected:
        raise ValueError("신조선가 raw 스키마가 예상과 다릅니다.")
    result = {}
    for period, estimate in VECTOR_ESTIMATES.items():
        price = round(estimate * 4) * 250_000
        values = {
            "period": period,
            "source_id": SOURCE_ID,
            "vessel_type": "Container",
            "price_index": "",
            "benchmark_name": "Container_1975TEU",
            "capacity_min": "1850.0",
            "capacity_max": "2100.0",
            "capacity_avg": "1975.0",
            "capacity_unit": "TEU",
            "benchmark_price_usd": str(price),
            "source_url": SOURCE_URL,
            "source_page_url": f"{SOURCE_URL}#page=2",
            "extraction_method": "pdf_vector_month_midpoint_round_0.25m",
            "quality_grade": "D",
            "raw_excerpt": (
                "2018-07-26 SK증권 p.2; Clarksons Research 1850-2100 TEU 도표; "
                f"월중앙 벡터 추정 {estimate:.3f}백만USD; 0.25백만USD 반올림"
            ),
        }
        result[period] = [values[column] for column in header]
    return result


def build_updated_text(original: str) -> tuple[str, int]:
    rows = list(csv.reader(io.StringIO(original)))
    header, body = rows[0], rows[1:]
    supplement = supplement_rows(header)
    idx = {column: header.index(column) for column in header}
    periods = [row[idx["period"]] for row in body]
    if periods != sorted(periods):
        raise ValueError("raw 원본의 기준월 순서가 정렬되지 않았습니다.")
    existing = set()
    for row in body:
        period = row[idx["period"]]
        if period not in supplement:
            continue
        if row[idx["vessel_type"]] != "Container":
            continue
        if row[idx["capacity_unit"]] != "TEU":
            continue
        if float(row[idx["capacity_avg"]]) != 1975.0:
            continue
        if row != supplement[period]:
            raise ValueError(f"{period}의 기존 1,975 TEU 가격과 보완값이 충돌합니다.")
        existing.add(period)

    to_add = {period: row for period, row in supplement.items() if period not in existing}
    if not to_add:
        return original, 0
    source_lines = original.splitlines(keepends=True)
    if len(source_lines) != len(rows):
        raise ValueError("raw 셀에 줄바꿈이 있어 원본 행을 그대로 보존할 수 없습니다.")
    output_lines = [source_lines[0]]
    pending = iter(sorted(to_add))
    next_period = next(pending, None)
    for index, row in enumerate(body):
        period = row[idx["period"]]
        while next_period is not None and next_period < period:
            new_line = io.StringIO(newline="")
            csv.writer(new_line, lineterminator="\n").writerow(to_add[next_period])
            output_lines.append(new_line.getvalue())
            next_period = next(pending, None)
        output_lines.append(source_lines[index + 1])
        if next_period == period and (index + 1 == len(body) or body[index + 1][idx["period"]] != period):
            new_line = io.StringIO(newline="")
            csv.writer(new_line, lineterminator="\n").writerow(to_add[period])
            output_lines.append(new_line.getvalue())
            next_period = next(pending, None)
    while next_period is not None:
        new_line = io.StringIO(newline="")
        csv.writer(new_line, lineterminator="\n").writerow(to_add[next_period])
        output_lines.append(new_line.getvalue())
        next_period = next(pending, None)
    updated = "".join(output_lines)
    check = list(csv.reader(io.StringIO(updated)))
    if len(check) != len(rows) + len(to_add):
        raise AssertionError("raw 추가 행수 검사가 실패했습니다.")
    return updated, len(to_add)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    if not PDF.is_file() or hashlib.sha256(PDF.read_bytes()).hexdigest() != PDF_SHA256:
        raise ValueError("참조 PDF가 없거나 검증한 유승우(2018) 파일과 다릅니다.")
    original = RAW.read_text(encoding="utf-8-sig")
    updated, added = build_updated_text(original)
    if not args.check_only and added:
        temporary = RAW.with_suffix(".csv.tmp")
        temporary.write_text(updated, encoding="utf-8-sig", newline="")
        temporary.replace(RAW)
    print(f"유승우(2018) 도표 추정치: {len(VECTOR_ESTIMATES)}개월, 신규 {added}행")


if __name__ == "__main__":
    main()
