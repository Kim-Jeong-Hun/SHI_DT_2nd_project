"""공개 월보의 선종별 신규 수주용량을 기존 raw CSV에 검증 후 추가한다.

원문 기사 URL은 아래 REPORTS에 명시한다. 새 월은 URL과 실제 게시일을
확인한 뒤 등록해야 한다. `--write` 없이는 파일을 수정하지 않는다.

    python scripts/수집/수주실적_월보_수집.py
    python scripts/수집/수주실적_월보_수집.py --write

주의: as_of_date는 클락슨 통계 기준일이고 기사 게시일이 아니다. 게시일은
기존 CSV 스키마를 유지하기 위해 definition_notes에 기록한다.
"""

from __future__ import annotations

import argparse
import calendar
import csv
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
import re
from urllib.request import Request, urlopen


PROJECT_ROOT = Path(__file__).resolve().parents[2]
RAW_PATH = PROJECT_ROOT / "data" / "raw" / "수주실적.csv"


@dataclass(frozen=True)
class Report:
    period: str
    url: str
    published_date: str
    publisher: str


# 각각 해당 월을 직접 설명하는 월보의 첫 게시본/재게시본이다. 다음 월보의
# 전월 비교치와 누계는 사후 수정치이므로 여기서 해당 월 값으로 사용하지 않는다.
REPORTS = (
    Report("2026-01", "https://news.metal.net.cn/content-193-7952178-1.html", "2026-02-27", "冶金网 / 国际船舶网"),
    Report("2026-02", "https://zhuzaotoutiao.com/xw/html/22572.shtml", "2026-03-26", "铸造头条 / 国际船舶网"),
    Report("2026-03", "https://zhuzaotoutiao.com/xw/html/22950.shtml", "2026-04-28", "铸造头条 / 国际船舶网"),
    Report("2026-04", "https://zhuzaotoutiao.com/xw/html/23214.shtml", "2026-05-25", "铸造头条 / 国际船舶网"),
    Report("2026-05", "https://zhuzaotoutiao.com/mobile/xw/html/23612.shtml", "2026-06-26", "铸造头条 / 国际船舶网"),
    Report("2026-06", "https://zhuzaotoutiao.com/xw/html/23970.shtml", "2026-07-25", "铸造头条 / 国际船舶网"),
    Report("2026-07", "https://zhuzaotoutiao.com/mobile/xw/html/24320.shtml", "2026-08-24", "铸造头条 / 国际船舶网"),
    Report("2026-08", "https://zhuzaotoutiao.com/xw/html/24728.shtml", "2026-09-28", "铸造头条 / 国际船舶网"),
)

# 중국어 기사 원문의 첫 '从船型上来看' 단락만 읽는다. 인도량/수주잔량
# 단락에도 동일한 선종·단위가 있으므로 기사 전체에서 숫자를 찾으면 안 된다.
TYPES = (
    ("Bulk Carrier", "Bulk Carrier", "散货船", "载重吨", "DWT"),
    ("Chemical Tanker", "Tanker", "化学品船", "载重吨", "DWT"),
    ("Container", "Container", "集装箱船", "标箱", "TEU"),
    ("Gas Carrier", "Gas Carrier", "液化气船", "立方米", "CBM"),
    ("Oil Tanker", "Tanker", "油船", "载重吨", "DWT"),
)


class TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        if data.strip():
            self.parts.append(data.strip())


def fetch_text(url: str) -> str:
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (research data verification)"})
    with urlopen(request, timeout=30) as response:
        html = response.read().decode("utf-8-sig")
    parser = TextExtractor()
    parser.feed(html)
    return " ".join(parser.parts)


def parse_number(token: str) -> int:
    if not re.fullmatch(r"(?:\d+|\d{1,3}(?:,\d{3})+)", token):
        raise ValueError(f"잘못된 숫자 표기: {token}")
    return int(token.replace(",", ""))


def parse_report(report: Report) -> tuple[list[dict[str, str]], list[str]]:
    text = fetch_text(report.url)
    year, month = map(int, report.period.split("-"))
    if report.published_date not in text:
        raise ValueError(f"{report.period}: 기사 게시일이 URL 본문과 다릅니다")
    header = re.search(
        rf"{year}年{month}月份全球新签订单\s*(\d+)艘", text
    )
    if not header:
        raise ValueError(f"{report.period}: 해당 월의 신규 수주 문단을 찾지 못했습니다")
    monthly_count = int(header.group(1))
    snapshot = re.search(r"截至\s*(\d{4})年(\d{1,2})月(\d{1,2})日", text)
    if not snapshot:
        raise ValueError(f"{report.period}: 통계 기준일을 찾지 못했습니다")
    as_of_date = f"{int(snapshot.group(1)):04d}-{int(snapshot.group(2)):02d}-{int(snapshot.group(3)):02d}"
    if as_of_date[:7] != f"{year + (month == 12):04d}-{month % 12 + 1:02d}":
        raise ValueError(f"{report.period}: 기준일 {as_of_date}가 다음 달이 아닙니다")
    section = re.search(
        r"从船型上来看\s*[，,:：]?\s*(.*?)\s*从订单类型来看", text, re.DOTALL
    )
    if not section:
        raise ValueError(f"{report.period}: 월별 선종 내역을 찾지 못했습니다")
    paragraph = section.group(1)
    extracted: dict[str, tuple[int, int]] = {}
    issues: list[str] = []
    for name, _, chinese, chinese_unit, _ in TYPES + (
        ("Other", "Other", "其他船型", "CGT", "CGT"),
        ("Offshore", "Offshore", "海工船", "CGT", "CGT"),
    ):
        match = re.search(
            rf"{chinese}(?:订单)?\s*(\d+)艘\s*[，,]\s*共计\s*([\d,]+)\s*{chinese_unit}",
            paragraph,
        )
        if not match:
            raise ValueError(f"{report.period}: {name}의 월별 척수·용량을 찾지 못했습니다")
        count = int(match.group(1))
        try:
            capacity = parse_number(match.group(2))
        except ValueError:
            if name != "Chemical Tanker" or report.period != "2026-06":
                raise
            issues.append(f"{report.period} Chemical Tanker: 원문 용량 '{match.group(2)}' 오기; 확정 전 제외")
            capacity = -1
        extracted[name] = (count, capacity)

    if sum(count for count, _ in extracted.values()) != monthly_count:
        raise ValueError(f"{report.period}: 선종별 척수 합이 기사 총척수와 다릅니다")
    period_end = calendar.monthrange(year, month)[1]
    common = {
        "frequency": "monthly",
        "period": report.period,
        "period_start": f"{report.period}-01",
        "period_end": f"{report.period}-{period_end:02d}",
        "source_id": f"CISN_{year}_{month:02d}",
        "publisher": report.publisher,
        "source_url": report.url,
        "as_of_date": as_of_date,
        "observation_method": "direct_monthly_report",
        "quality_grade": "B",
        "is_approximate": "false",
        "revision_risk": "high",
        "target_usable": "true",
        "ml_target_complete": "true",
        "definition_notes": (
            f"Clarksons-cited monthly snapshot; published_date={report.published_date}. "
            "Native capacity unit; later vintages may revise this month."
        ),
    }
    rows: list[dict[str, str]] = []
    for name, parent, _, _, unit in TYPES:
        count, capacity = extracted[name]
        if capacity < 0:
            continue
        rows.append({
            **common,
            "vessel_type": name,
            "parent_vessel_type": parent,
            "new_orders_no": str(count),
            "capacity_value": str(capacity),
            "capacity_unit": unit,
        })
    oil_count, oil_capacity = extracted["Oil Tanker"]
    chemical_count, chemical_capacity = extracted["Chemical Tanker"]
    if chemical_capacity >= 0:
        rows.append({
            **common,
            "vessel_type": "Tanker incl. Chemical",
            "parent_vessel_type": "Tanker",
            "new_orders_no": str(oil_count + chemical_count),
            "capacity_value": str(oil_capacity + chemical_capacity),
            "capacity_unit": "DWT",
            "source_id": f"CISN_{year}_{month:02d}+CISN_{year}_{month:02d}",
            "observation_method": "derived_sum_oil_plus_chemical",
            "definition_notes": (
                f"Oil tanker plus chemical tanker; published_date={report.published_date}. "
                "Both same-month components observed in the monthly report."
            ),
        })
    return rows, issues


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="검증한 신규 행을 raw CSV에 추가")
    args = parser.parse_args()

    with RAW_PATH.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        columns = reader.fieldnames
        if not columns or not {"period", "vessel_type", "capacity_value"}.issubset(columns):
            raise ValueError("기존 raw CSV 스키마가 예상과 다릅니다")
        existing = {(row["period"], row["vessel_type"]): row for row in reader}

    candidates: list[dict[str, str]] = []
    issues: list[str] = []
    for report in REPORTS:
        rows, report_issues = parse_report(report)
        candidates.extend(rows)
        issues.extend(report_issues)

    new_rows = []
    for row in sorted(candidates, key=lambda item: (item["period"], item["vessel_type"])):
        key = (row["period"], row["vessel_type"])
        if key in existing:
            old = existing[key]
            fields = ("new_orders_no", "capacity_value", "capacity_unit", "source_url")
            if any(old[field] != row[field] for field in fields):
                raise ValueError(f"기존 행과 새 월보가 다릅니다. 자동 덮어쓰기 금지: {key}")
            continue
        new_rows.append(row)

    for row in new_rows:
        print(f"{row['period']} {row['vessel_type']:<21} {row['capacity_value']:>10} {row['capacity_unit']}")
    for issue in issues:
        print(f"확인 필요: {issue}")
    print(f"검증 완료: {len(candidates)}행, 신규 {len(new_rows)}행, 이슈 {len(issues)}건")

    if args.write and new_rows:
        with RAW_PATH.open("a", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=columns, lineterminator="\n")
            for row in new_rows:
                writer.writerow({column: row.get(column, "") for column in columns})
        print(f"추가 완료: {RAW_PATH}")
    elif not args.write:
        print("미리보기만 수행했습니다. 실제 추가: --write")


if __name__ == "__main__":
    main()
