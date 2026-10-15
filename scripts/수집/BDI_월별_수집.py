"""핀란드 기술산업협회가 공개하는 Macrobond 출처 월별 BDI 원표를 보존한다.

원표의 'Sea freight prices'는 BDI 지수(점)이며 월말 관측값으로 판단한다.
수집 시에는 원표를 재가공하지 않고, 구조와 월별 연속성을 검사한 뒤 저장한다.
"""

from __future__ import annotations

import argparse
import csv
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "raw" / "핀란드기술산업협회_BDI_월별_원표.csv"
URL = (
    "https://teknologiateollisuus.fi/documents/"
    "0_MB_HINNAT_Merirahtien_hinnat_kuukausidata_aikasarja_EN.csv"
)


def validate(raw: bytes) -> tuple[int, str, str]:
    rows = list(csv.reader(StringIO(raw.decode("utf-8-sig")), delimiter=";"))
    if not rows or rows[0] != ["Kuukausi", "Sea freight prices"]:
        raise ValueError("BDI 원표 헤더가 예상과 다릅니다.")
    if any(len(row) != 2 for row in rows[1:]):
        raise ValueError("BDI 원표에 열 수가 다른 행이 있습니다.")
    if not rows[1:]:
        raise ValueError("BDI 원표가 비어 있습니다.")
    months = [pd.Period(row[0].replace(".", "-"), freq="M") for row in rows[1:]]
    if months != list(pd.period_range(months[0], months[-1], freq="M")):
        raise ValueError("BDI 원표의 월이 중복되거나 불연속입니다.")
    if months[0] > pd.Period("2015-01", freq="M"):
        raise ValueError("BDI 원표에 2015년 이후 전체 이력이 없습니다.")
    try:
        values = [float(row[1]) for row in rows[1:]]
    except ValueError as exc:
        raise ValueError("BDI 원표에 숫자가 아닌 지수 값이 있습니다.") from exc
    if any(not 0 < value < float("inf") for value in values):
        raise ValueError("BDI 원표에 결측·0 이하·무한대 값이 있습니다.")
    return len(values), str(months[0]), str(months[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    request = Request(URL, headers={"User-Agent": "Mozilla/5.0 (educational research)"})
    with urlopen(request, timeout=30) as response:
        raw = response.read()
    count, first, last = validate(raw)
    if args.check_only:
        if not OUTPUT.exists() or OUTPUT.read_bytes() != raw:
            raise ValueError("저장된 BDI 원표와 온라인 원표가 다릅니다.")
    else:
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        temporary = OUTPUT.with_suffix(".csv.tmp")
        temporary.write_bytes(raw)
        temporary.replace(OUTPUT)
    print(f"BDI 원표 {count}개월 {first}~{last}: {OUTPUT}")


if __name__ == "__main__":
    main()
