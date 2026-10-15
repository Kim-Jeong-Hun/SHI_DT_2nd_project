"""2024 Equasis 보고서의 서로 다른 모집단에 속한 선령표를 별도 CSV로 추출한다.

Table 3: 전체 선대 GT>=100, 선령×선박 규모(선종 구분 없음).
Table 17: PSC 집계기간 2022-2024, GT>=500, PSC 선종×선령.
두 표는 기존 2005-2022년 선종별 선령·총톤수 표와 이어 붙일 수 없다.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path

from pypdf import PdfReader


ROOT = Path(__file__).resolve().parents[2]
PDF = ROOT / "references" / "Equasis_세계상선대_연간보고서" / "Equasis_세계상선대_2024.pdf"
RAW = ROOT / "data" / "raw"
SOURCE_URL = (
    "https://www.equasis.org/Fichiers/Statistique/MOA/"
    "Documents%20availables%20on%20statistics%20of%20Equasis/"
    "Equasis%20Statistics%20-%20The%20world%20fleet%202024.pdf"
)
AGE_LABELS = (
    ("0-4 years old", "0-4"),
    ("5-14 years old", "5-14"),
    ("15-24 years old", "15-24"),
    ("+25 years old", "25+"),
)
SIZES = (
    ("Small", "GT<500"),
    ("Medium", "500<=GT<25000"),
    ("Large", "25000<=GT<60000"),
    ("Very large", "GT>=60000"),
    ("Total", "GT>=100"),
)
PSC_TYPES = (
    "Bulk carrier", "Chemical tanker", "Combination carrier", "Container",
    "Gas carrier", "General cargo/multipurpose", "Heavy load", "NLS tanker",
    "Offshore supply", "Oil tanker", "Other", "Other special activities",
    "Passenger ship", "Refrigerated cargo", "Ro-ro cargo", "Ro-ro passenger ship",
    "Special purpose ship", "Tug",
)
NUMBER_PERCENT = re.compile(r"(\d[\d,]*)\s+(\d+(?:\.\d+)?)%")
PSC_TRIPLE = re.compile(r"(\d[\d,]*)\s+(\d[\d,]*)\s+(\d+(?:\.\d+)?%|Na)")


def integer(text: str) -> int:
    return int(text.replace(",", ""))


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        raise ValueError(f"추출 행이 없습니다: {path.name}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    print(f"저장: {path} ({len(rows)}행)")


def extract_whole_fleet(text: str) -> list[dict]:
    table = text.split("Table 3 –", 1)[1].split("Graph 3 –", 1)[0]
    rows = []
    for source_age, age in AGE_LABELS:
        line = next(line for line in table.splitlines() if line.strip().startswith(source_age))
        values = NUMBER_PERCENT.findall(line[len(source_age):])
        if len(values) != len(SIZES):
            raise ValueError(f"Table 3 {age}: 규모별 수치 {len(values)}개")
        counts = [integer(count) for count, _ in values]
        if sum(counts[:4]) != counts[4]:
            raise ValueError(f"Table 3 {age}: 규모별 합계 불일치")
        for (size, gt_range), (count, share) in zip(SIZES, values):
            rows.append({
                "보고서연도": 2024,
                "모집단_원문": "World fleet, ships >=100 GT",
                "선령구간": age,
                "규모구간_원문": size,
                "규모기준_GT": gt_range,
                "선박수_척": integer(count),
                "해당규모내_비중_pct": float(share),
                "PDF_표번호": 3,
                "PDF_물리쪽": 7,
                "PDF_파일명": PDF.name,
                "원천_URL": SOURCE_URL,
            })
    total_line = next(line for line in table.splitlines() if re.match(r"^Total\s+\d", line.strip()))
    source_totals = [integer(count) for count, _ in NUMBER_PERCENT.findall(total_line)]
    computed = [sum(row["선박수_척"] for row in rows if row["규모구간_원문"] == size)
                for size, _ in SIZES]
    if computed != source_totals or source_totals[-1] != 132940:
        raise ValueError(f"Table 3 원문 열 합계 대조 실패: {computed} != {source_totals}")
    return rows


def extract_psc_age(text: str) -> list[dict]:
    table = text.split("Table 17 –", 1)[1].split("Source: Equasis.", 1)[0]
    table = re.sub(r"\s+", " ", table)
    rows = []
    position = table.index("Bulk carrier")
    for index, vessel_type in enumerate(PSC_TYPES):
        start = table.index(vessel_type, position) + len(vessel_type)
        next_type = PSC_TYPES[index + 1] if index + 1 < len(PSC_TYPES) else "Total "
        end = table.index(next_type, start)
        values = PSC_TRIPLE.findall(table[start:end])
        if len(values) != 5:
            raise ValueError(f"Table 17 {vessel_type}: 선령별 수치 {len(values)}개")
        globals_ = [integer(global_count) for global_count, _, _ in values]
        inspected = [integer(inspection_count) for _, inspection_count, _ in values]
        if sum(globals_[:4]) != globals_[4] or sum(inspected[:4]) != inspected[4]:
            raise ValueError(f"Table 17 {vessel_type}: 선령별 합계 불일치")
        for age, (global_count, inspection_count, percentage) in zip(
            ("0-4", "5-14", "15-24", "25+", "전체"), values
        ):
            if integer(inspection_count) > integer(global_count):
                raise ValueError(f"Table 17 {vessel_type} {age}: 검사척수 > 전체척수")
            rows.append({
                "보고서연도": 2024,
                "집계기간_원문": "2022-2024",
                "모집단_원문": "PSC ships GT>=500 with and without inspections",
                "PSC_선종_원문": vessel_type,
                "선령구간": age,
                "선박수_Global_척": integer(global_count),
                "검사선박수_척": integer(inspection_count),
                "검사율_pct": "" if percentage == "Na" else float(percentage.rstrip("%")),
                "검사율_원문비고": "Na" if percentage == "Na" else "",
                "PDF_표번호": 17,
                "PDF_물리쪽": 18,
                "PDF_파일명": PDF.name,
                "원천_URL": SOURCE_URL,
            })
        position = end
    total_values = PSC_TRIPLE.findall(table[position:])
    if len(total_values) != 5:
        raise ValueError("Table 17 전체 합계 행을 찾지 못했습니다.")
    source_totals = [(integer(global_count), integer(inspection_count))
                     for global_count, inspection_count, _ in total_values]
    computed = [
        (sum(row["선박수_Global_척"] for row in rows if row["선령구간"] == age),
         sum(row["검사선박수_척"] for row in rows if row["선령구간"] == age))
        for age in ("0-4", "5-14", "15-24", "25+", "전체")
    ]
    if computed != source_totals:
        raise ValueError(f"Table 17 원문 열 합계 대조 실패: {computed} != {source_totals}")
    return rows


def main() -> None:
    reader = PdfReader(PDF)
    if len(reader.pages) != 22:
        raise ValueError(f"예상 밖 PDF 페이지 수: {len(reader.pages)}")
    whole = extract_whole_fleet(reader.pages[6].extract_text())
    psc = extract_psc_age(reader.pages[17].extract_text())
    write_csv(RAW / "Equasis_2024_전체선대_선령별.csv", whole)
    write_csv(RAW / "Equasis_2024보고서_PSC선종별선령_2022-2024.csv", psc)


if __name__ == "__main__":
    main()
