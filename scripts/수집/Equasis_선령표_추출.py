"""Equasis 연간 보고서의 선종별 선령 표에서 원문 합계 열을 추출한다.

입력: references/Equasis_세계상선대_연간보고서/Equasis_세계상선대_YYYY.pdf
출력: data/raw/Equasis_세계선대_선종별선령_연간.csv

PDF 표는 연도에 따라 이미지로 삽입되어 있으므로 OCR이 필요하다.
필요 패키지: pypdf, Pillow, numpy, rapidocr-onnxruntime
외부 명령: pdftoppm (Poppler)
"""

from __future__ import annotations

import csv
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image
from pypdf import PdfReader
from rapidocr_onnxruntime import RapidOCR


ROOT = Path(__file__).resolve().parents[2]
PDF_DIR = ROOT / "references" / "Equasis_세계상선대_연간보고서"
OUTPUT = ROOT / "data" / "raw" / "Equasis_세계선대_선종별선령_연간.csv"
BASE_URL = (
    "https://www.equasis.org/Fichiers/Statistique/MOA/"
    "Documents%20availables%20on%20statistics%20of%20Equasis/"
    "Equasis%20Statistics%20-%20The%20world%20fleet%20"
)

# 1-based PDF physical page number of the 0-4-year-old tables.
FIRST_AGE_PAGE = {
    2005: 9, 2006: 11, 2007: 11, 2008: 11, 2009: 11,
    2010: 8, 2011: 8, 2012: 8, 2013: 8, 2014: 8,
    2015: 8, 2016: 8, 2017: 10, 2018: 10, 2019: 10,
    2020: 10, 2021: 10, 2022: 8,
}
AGE_BANDS = ("0-4", "5-14", "15-24", "25+")
VESSEL_TYPES = (
    "Bulk carriers", "Container ships", "Gas tankers",
    "Oil and chemical tankers",
)

# OCR이 누락하거나 잘못 읽은 셀을 원문 PDF의 해당 표에서 육안으로 대조한 값.
MANUAL_CORRECTIONS = {
    (2006, "5-14", "Bulk carriers", "총톤수_천GT"): 72133,  # PDF 12쪽 표 8
    (2007, "5-14", "Bulk carriers", "총톤수_천GT"): 76740,  # PDF 12쪽 표 8
    (2007, "5-14", "Oil and chemical tankers", "총톤수_천GT"): 86635,  # PDF 12쪽 표 8
    (2008, "5-14", "Bulk carriers", "총톤수_천GT"): 78947,  # PDF 12쪽 표 8
    (2012, "15-24", "Container ships", "선박수_척"): 999,  # PDF 10쪽 표 9
    (2013, "15-24", "Bulk carriers", "총톤수_천GT"): 59909,  # PDF 10쪽 표 10
    (2014, "5-14", "Gas tankers", "선박수_척"): 669,  # PDF 9쪽 표 7
    (2016, "25+", "Bulk carriers", "선박수_척"): 990,  # PDF 11쪽 표 11
    (2021, "25+", "Oil and chemical tankers", "총톤수_천GT"): 9388,  # PDF 13쪽 표 12
}

# 원문 선령표 네 구간의 합과 같은 보고서 Table 1/2의 전체 선대 값이 다른 사례.
# OCR 오차가 아니므로 선령표의 수치를 변경하지 않고 그 차이만 허용한다.
KNOWN_SOURCE_DIFFERENCES = {
    (2008, "Container ships", "총톤수_천GT"): -300,
    (2008, "Gas tankers", "총톤수_천GT"): -801,
    (2020, "Bulk carriers", "선박수_척"): 3,
}

# 원문 전체 선대 표는 1,297로 보이나 OCR에서 앞자리 1이 누락되는 경우.
WHOLE_FLEET_CORRECTIONS = {
    (2006, "Gas tankers", "선박수_척"): 1297,
}


def source_discrepancy_note(year: int, vessel_type: str) -> str:
    notes = []
    for column, unit in (("선박수_척", "척"), ("총톤수_천GT", "천GT")):
        difference = KNOWN_SOURCE_DIFFERENCES.get((year, vessel_type, column))
        if difference is not None:
            notes.append(f"원문 선령구간 합계가 전체 선대표보다 {difference:+d}{unit}")
    return "; ".join(notes)


def normalized(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def type_from_label(value: str) -> str | None:
    word = normalized(value)
    if word.startswith("bulk") and "carrier" in word:
        return "Bulk carriers"
    if word.startswith("container") and "ship" in word:
        return "Container ships"
    if word.startswith("gas") and "tanker" in word:
        return "Gas tankers"
    if word.startswith("oilandchem"):
        return "Oil and chemical tankers"
    return None


def numeric(value: str) -> int | float | None:
    text = value.strip().replace(" ", "")
    if re.fullmatch(r"\d{1,3}\.\d{3}", text):
        text = text.replace(".", "")
    text = text.replace(",", "")
    if not re.fullmatch(r"\d+(?:\.\d+)?", text):
        return None
    number = float(text) if "." in text else int(text)
    return number


def find_pdftoppm() -> str:
    found = shutil.which("pdftoppm")
    if found:
        return found
    bundled = (
        Path.home() / ".cache" / "codex-runtimes" / "codex-primary-runtime"
        / "dependencies" / "native" / "poppler" / "Library" / "bin" / "pdftoppm.exe"
    )
    if bundled.exists():
        return str(bundled)
    raise FileNotFoundError("pdftoppm을 찾지 못했습니다.")


def extract_page(pdf: Path, page_number: int, ocr: RapidOCR, pdftoppm: str):
    with tempfile.TemporaryDirectory(prefix="equasis_age_") as temp:
        prefix = Path(temp) / "page"
        subprocess.run(
            [pdftoppm, "-f", str(page_number), "-l", str(page_number),
             "-r", "200", "-png", "-singlefile", str(pdf), str(prefix)],
            check=True, capture_output=True,
        )
        with Image.open(f"{prefix}.png") as image:
            width, height = image.size
            # 아래의 그래프는 표 추출에 필요하지 않다.
            pixels = np.asarray(image.crop((0, 0, width, int(height * 0.75))).convert("RGB"))
        result, _ = ocr(pixels)
    items = []
    for box, label, score in result or []:
        items.append({
            "x": float(box[0][0]), "y": float(box[0][1]),
            "text": label, "score": float(score),
        })
    return items, width


def tables_on_page(items: list[dict], width: int):
    headers = sorted(
        ((item["y"], item["x"]) for item in items
        if normalized(item["text"]) == "total" and item["x"] > width * 0.72)
    )
    # 두 표 각각의 맨 오른쪽 'Total' 표제만 선택한다.
    if len(headers) != 2:
        raise ValueError(f"표 머리글 Total 2개가 필요합니다: {headers}")
    return headers


def read_total(items: list[dict], header_x: float, row_y: float, max_y: float):
    candidates = []
    for item in items:
        if not (header_x - 100 < item["x"] < header_x + 20):
            continue
        if not (row_y - 10 <= item["y"] <= min(row_y + 24, max_y)):
            continue
        value = numeric(item["text"])
        if value is not None:
            candidates.append((abs(item["y"] - row_y), abs(item["x"] - (header_x - 40)), value))
    if not candidates:
        return None
    return sorted(candidates)[0][2]


def extract_year(year: int, ocr: RapidOCR, pdftoppm: str):
    pdf = PDF_DIR / f"Equasis_세계상선대_{year}.pdf"
    reader = PdfReader(pdf)
    rows = {}
    for age_index, age_band in enumerate(AGE_BANDS):
        page = FIRST_AGE_PAGE[year] + age_index
        if page > len(reader.pages):
            raise ValueError(f"{year}: PDF 쪽 범위 초과 {page}")
        items, width = extract_page(pdf, page, ocr, pdftoppm)
        headers = tables_on_page(items, width)
        labels = []
        for item in items:
            vessel_type = type_from_label(item["text"])
            if vessel_type and item["x"] < width * 0.35:
                labels.append((item["y"], vessel_type))
        for measure_index, (start, end) in enumerate(
            ((headers[0][0] + 10, headers[1][0] - 15),
             (headers[1][0] + 10, float("inf")))
        ):
            measure_labels = [(y, kind) for y, kind in labels if start <= y < end]
            for row_y, vessel_type in measure_labels:
                value = read_total(items, headers[measure_index][1], row_y, end)
                key = (age_band, vessel_type)
                row = rows.setdefault(key, {
                    "기준연도": year,
                    "선령구간": age_band,
                    "선종_원문": vessel_type,
                    "선박수_척": None,
                    "총톤수_천GT": None,
                    "총톤수_원문단위": "1000 t" if year <= 2013 else "1000 GT",
                    "선박수_표번호": 3 + age_index * 2 if year == 2005 else 5 + age_index * 2,
                    "총톤수_표번호": 4 + age_index * 2 if year == 2005 else 6 + age_index * 2,
                    "PDF_물리쪽": page,
                    "PDF_파일명": pdf.name,
                    "원천_URL": f"{BASE_URL}{year}.pdf",
                    "원문내부대조_비고": source_discrepancy_note(year, vessel_type),
                })
                row["선박수_척" if measure_index == 0 else "총톤수_천GT"] = value
    for (correction_year, age_band, vessel_type, column), value in MANUAL_CORRECTIONS.items():
        if correction_year == year:
            rows[(age_band, vessel_type)][column] = value
    missing = []
    for age_band in AGE_BANDS:
        for vessel_type in VESSEL_TYPES:
            row = rows.get((age_band, vessel_type))
            if not row or row["선박수_척"] is None or row["총톤수_천GT"] is None:
                missing.append((age_band, vessel_type, row))
    return rows, missing


def verify_against_whole_fleet(year: int, rows: dict, ocr: RapidOCR, pdftoppm: str):
    """선령 네 구간 합계를 원문 Table 1/2의 선종별 전체값과 독립 대조."""
    pdf = PDF_DIR / f"Equasis_세계상선대_{year}.pdf"
    page = FIRST_AGE_PAGE[year] - (1 if year == 2005 else 2)
    items, width = extract_page(pdf, page, ocr, pdftoppm)
    headers = tables_on_page(items, width)
    all_fleet = {}
    for measure_index, (start, end) in enumerate(
        ((headers[0][0] + 10, headers[1][0] - 15),
         (headers[1][0] + 10, float("inf")))
    ):
        for item in items:
            vessel_type = type_from_label(item["text"])
            if not vessel_type or item["x"] >= width * 0.35 or not (start <= item["y"] < end):
                continue
            all_fleet[(vessel_type, measure_index)] = read_total(
                items, headers[measure_index][1], item["y"], end
            )
    problems = []
    for vessel_type in VESSEL_TYPES:
        for measure_index, column in enumerate(("선박수_척", "총톤수_천GT")):
            expected = all_fleet.get((vessel_type, measure_index))
            expected = WHOLE_FLEET_CORRECTIONS.get((year, vessel_type, column), expected)
            observed = sum(rows[(age, vessel_type)][column] for age in AGE_BANDS)
            tolerance = 0 if measure_index == 0 else 3
            source_difference = KNOWN_SOURCE_DIFFERENCES.get((year, vessel_type, column))
            if expected is None or (abs(expected - observed) > tolerance and observed - expected != source_difference):
                problems.append((vessel_type, column, observed, expected))
    return problems


def main():
    if sys.argv[1:] == ["--repair-existing"]:
        # 원문 대조로 확정한 OCR 오독만 기존 추출본에서 바로잡고 전체 표와 재대조한다.
        with OUTPUT.open(encoding="utf-8-sig", newline="") as stream:
            all_rows = list(csv.DictReader(stream))
        if len(all_rows) != len(FIRST_AGE_PAGE) * len(AGE_BANDS) * len(VESSEL_TYPES):
            raise ValueError("기존 CSV의 행 수가 예상과 다릅니다. 전체 재추출이 필요합니다.")
        indexed = {}
        for row in all_rows:
            row["기준연도"] = int(row["기준연도"])
            for column in ("선박수_척", "총톤수_천GT"):
                row[column] = numeric(row[column])
            indexed[(row["기준연도"], row["선령구간"], row["선종_원문"])] = row
        if len(indexed) != len(all_rows):
            raise ValueError("기존 CSV에 중복 키가 있습니다. 전체 재추출이 필요합니다.")
        for (year, age, vessel_type, column), value in MANUAL_CORRECTIONS.items():
            indexed[(year, age, vessel_type)][column] = value
        for (year, _, vessel_type), row in indexed.items():
            row["원문내부대조_비고"] = source_discrepancy_note(year, vessel_type)
        ocr = RapidOCR()
        pdftoppm = find_pdftoppm()
        problems = []
        for year in FIRST_AGE_PAGE:
            rows = {(age, vessel_type): indexed[(year, age, vessel_type)]
                    for age in AGE_BANDS for vessel_type in VESSEL_TYPES}
            problems.extend((year, *issue) for issue in verify_against_whole_fleet(year, rows, ocr, pdftoppm))
            print(f"{year}: 전체 선대 표 대조 완료", flush=True)
        if problems:
            raise ValueError(f"전체 선대 대조 불일치: {problems}")
        with OUTPUT.open("w", encoding="utf-8-sig", newline="") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(all_rows[0]))
            writer.writeheader()
            writer.writerows(all_rows)
        print(f"원문 대조 보정 및 저장: {OUTPUT} ({len(all_rows)}행)")
        return
    if sys.argv[1:]:
        raise ValueError("사용법: Equasis_선령표_추출.py [--repair-existing]")
    ocr = RapidOCR()
    pdftoppm = find_pdftoppm()
    all_rows = []
    issues = []
    reconciliation_issues = []
    for year in FIRST_AGE_PAGE:
        rows, missing = extract_year(year, ocr, pdftoppm)
        all_rows.extend(rows.values())
        issues.extend((year, *problem) for problem in missing)
        if not missing:
            reconciliation_issues.extend(
                (year, *problem)
                for problem in verify_against_whole_fleet(year, rows, ocr, pdftoppm)
            )
        print(f"{year}: {len(rows)}개 선종·선령 조합, 누락 {len(missing)}개", flush=True)
    if issues:
        for issue in issues:
            print("누락:", issue, flush=True)
        raise ValueError(f"OCR 누락 {len(issues)}개: 원문과 대조 후 보완해야 합니다.")
    if reconciliation_issues:
        for issue in reconciliation_issues:
            print("전체 선대 대조 불일치:", issue, flush=True)
        raise ValueError(f"전체 선대 대조 불일치 {len(reconciliation_issues)}개")
    keys = list(all_rows[0])
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with OUTPUT.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=keys)
        writer.writeheader()
        writer.writerows(sorted(all_rows, key=lambda r: (r["기준연도"], AGE_BANDS.index(r["선령구간"]), r["선종_원문"])))
    print(f"저장: {OUTPUT} ({len(all_rows)}행)")


if __name__ == "__main__":
    main()
