"""OPEC MOMR의 VLCC 중동→동아시아 항로 월평균 Worldscale 표를 수집한다.

원표의 가장 오른쪽 월 값만 사용하며, PDF 발행월과 운임 관측월을 분리한다.
접근/추출 실패 월은 빈 값과 상태를 남긴다. 결측을 보간하지 않는다.
"""

from __future__ import annotations

import argparse
import csv
from datetime import date
from io import BytesIO
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "raw" / "OPEC_VLCC_중동동아시아_월별_원표추출.csv"
MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]
FIRST_REPORT = (2015, 2)
# 기본 수집 범위는 검증한 보고서까지 고정하되, --end로 후속 보고서를 지정할 수 있다.
DEFAULT_LAST_REPORT = (2026, 8)
LATEST_POSSIBLE_REPORT = (date.today().year, date.today().month)
ROUTE_ROW = re.compile(
    r"(?m)^\s*Middle East/East\s+230\s*[-–]\s*280\s+"
    r"([\d,.]+)\s+([\d,.]+)\s+([\d,.]+)(?:\s|$)"
)


def month_before(year: int, month: int) -> str:
    return f"{year - 1 if month == 1 else year:04d}-{12 if month == 1 else month - 1:02d}"


def extract_three_months(pdf_bytes: bytes) -> tuple[float, float, float] | None:
    reader = PdfReader(BytesIO(pdf_bytes))
    # OPEC의 tanker 표는 이 기간 보고서의 약 55~80쪽에 있다.
    for page in reader.pages[50:85]:
        text = page.extract_text() or ""
        match = ROUTE_ROW.search(text)
        if match:
            return tuple(float(value.replace(",", "")) for value in match.groups())
    return None


def extract_last_month(pdf_bytes: bytes) -> float | None:
    values = extract_three_months(pdf_bytes)
    return values[2] if values else None


def add_month(year: int, month: int, months: int) -> tuple[int, int]:
    index = year * 12 + month - 1 + months
    return divmod(index, 12)[0], divmod(index, 12)[1] + 1


def repair_from_following_reports(rows: list[dict[str, str]]) -> None:
    """원발행 PDF가 막힌 월은 다음 호의 3개월 원표 가운데 값으로 검증 보완."""
    by_month = {row["기준월"]: row for row in rows}
    for row in rows:
        if row["수집상태"] in {"추출", "후속보고서보완"}:
            continue
        year, month = map(int, row["기준월"].split("-"))
        report_year, report_month = add_month(year, month, 2)
        if (report_year, report_month) > LATEST_POSSIBLE_REPORT:
            continue
        url = ("https://www.opec.org/assets/assetdb/"
               f"momr-{MONTHS[report_month - 1]}-{report_year}.pdf")
        try:
            request = Request(url, headers={"User-Agent": "Mozilla/5.0 (educational research)"})
            with urlopen(request, timeout=20) as response:
                values = extract_three_months(response.read())
            if values is None:
                continue
            for neighbor_offset, extracted in ((-1, values[0]), (1, values[2])):
                neighbor_year, neighbor_month = add_month(year, month, neighbor_offset)
                neighbor = by_month.get(f"{neighbor_year:04d}-{neighbor_month:02d}")
                if neighbor and neighbor["유조선운임_VLCC_중동동아시아_WS"]:
                    saved = float(neighbor["유조선운임_VLCC_중동동아시아_WS"])
                    if abs(saved - extracted) > 1e-9:
                        row["수집상태"] = "후속보고서이웃값불일치"
                        break
            else:
                row["유조선운임_VLCC_중동동아시아_WS"] = f"{values[1]:g}"
                row["보고서월"] = f"{report_year:04d}-{report_month:02d}"
                row["보고서URL"] = url
                row["수집상태"] = "후속보고서보완"
        except (HTTPError, URLError, TimeoutError):
            continue
        print("보완", row["기준월"], row["수집상태"], row["유조선운임_VLCC_중동동아시아_WS"], flush=True)


def collect(start: tuple[int, int], end: tuple[int, int], delay: float,
            existing: dict[str, dict[str, str]] | None = None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for year in range(start[0], end[0] + 1):
        for month in range(1, 13):
            if (year, month) < start or (year, month) > end:
                continue
            report_month = f"{year:04d}-{month:02d}"
            url = f"https://www.opec.org/assets/assetdb/momr-{MONTHS[month-1]}-{year}.pdf"
            row = {
                "기준월": month_before(year, month),
                "유조선운임_VLCC_중동동아시아_WS": "",
                "보고서월": report_month,
                "보고서URL": url,
                "출처": "OPEC Monthly Oil Market Report / 원표의 2차 출처는 보고서별 확인",
                "수집상태": "",
            }
            if existing and row["기준월"] in existing:
                old_row = existing[row["기준월"]]
                if old_row["수집상태"] in {"추출", "후속보고서보완"}:
                    rows.append(old_row)
                    continue
            try:
                request = Request(url, headers={"User-Agent": "Mozilla/5.0 (educational research)"})
                with urlopen(request, timeout=20) as response:
                    payload = response.read()
                if not payload.startswith(b"%PDF"):
                    row["수집상태"] = "PDF아님"
                else:
                    value = extract_last_month(payload)
                    if value is None:
                        row["수집상태"] = "표추출실패"
                    elif value <= 0:
                        row["수집상태"] = "비정상값"
                    else:
                        row["유조선운임_VLCC_중동동아시아_WS"] = f"{value:g}"
                        row["수집상태"] = "추출"
            except (HTTPError, URLError, TimeoutError) as error:
                row["수집상태"] = f"접근실패:{getattr(error, 'code', type(error).__name__)}"
            except Exception as error:
                row["수집상태"] = f"추출오류:{type(error).__name__}"
            rows.append(row)
            print(row["기준월"], row["수집상태"], row["유조선운임_VLCC_중동동아시아_WS"], flush=True)
            time.sleep(delay)
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", default="2015-02", help="첫 PDF 발행월 YYYY-MM")
    parser.add_argument("--end", default=f"{DEFAULT_LAST_REPORT[0]:04d}-{DEFAULT_LAST_REPORT[1]:02d}",
                        help="마지막 PDF 발행월 YYYY-MM (기본: 검증 완료된 2026-08)")
    parser.add_argument("--delay", type=float, default=0.1)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--retry-missing", action="store_true", help="기존 정상 행은 유지하고 실패 월만 다시 수집")
    parser.add_argument("--repair-neighbor", action="store_true", help="접근 불가 월을 다음 보고서의 중간 월 값으로 검증 보완")
    args = parser.parse_args()
    start = tuple(map(int, args.start.split("-")))
    end = tuple(map(int, args.end.split("-")))
    if not (FIRST_REPORT <= start <= end <= LATEST_POSSIBLE_REPORT):
        raise ValueError("PDF 발행월은 2015-02부터 현재 월까지 지정할 수 있습니다.")
    existing = None
    if args.retry_missing and args.output.exists():
        with args.output.open("r", encoding="utf-8-sig", newline="") as file:
            existing = {row["기준월"]: row for row in csv.DictReader(file)}
    if args.repair_neighbor:
        if not args.output.exists():
            raise FileNotFoundError(args.output)
        with args.output.open("r", encoding="utf-8-sig", newline="") as file:
            rows = list(csv.DictReader(file))
        repair_from_following_reports(rows)
    else:
        rows = collect(start, end, args.delay, existing)
        repair_from_following_reports(rows)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    count = sum(bool(row["유조선운임_VLCC_중동동아시아_WS"]) for row in rows)
    print(f"저장: {args.output} / 관측 {count}/{len(rows)}")


if __name__ == "__main__":
    main()
