"""공개 글로벌 지표 원본을 직접 읽어 월별 분석 CSV로 정리한다.

원천 (raw 파일은 다운로드 당시의 원형을 보존)
- RWI/ISL Container Throughput Index: https://www.isl.org/en/services/rwiisl-container-throughput-index
- World Bank Global Economic Monitor: https://datacatalog.worldbank.org/infrastructure-data/search/dataset/0037798/global-economic-monitor
- New York Fed GSCPI: https://www.newyorkfed.org/research/policy/gscpi

processed의 PK는 YYYY-MM 형식의 기준월이다. 원천별로 실제 공개되어
결측 없이 확인된 마지막 월까지만 저장한다. 이후 원본 갱신 시 종료월을 검증한다.
GSCPI 제공 URL의 확장자는 xlsx이지만 실제 파일은 구형 xls이므로 xlrd가 필요하다.
"""

from __future__ import annotations

import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "공개글로벌월별지표"
OUT = ROOT / "data" / "processed" / "공통"
START = "2015-01"
RWI_END = "2026-08"
GEM_END = "2026-07"
GSCPI_END = "2026-08"


def expected_months(end: str) -> list[str]:
    return pd.period_range(START, end, freq="M").astype(str).tolist()

RWI_RAW = RAW / "RWI_ISL_세계컨테이너항만처리량지수_202609.xlsx"
GEM_RAW = RAW / "세계은행_GEM_20261004.zip"
GSCPI_RAW = RAW / "뉴욕연준_GSCPI_20261004.xls"

RWI_OUT = OUT / "세계 컨테이너항만 처리량지수(월).csv"
GEM_OUT = OUT / "세계 실질교역과 산업생산(월).csv"
GSCPI_OUT = OUT / "글로벌 공급망압력지수(월).csv"

GEM_FILES = {
    "세계_실질상품수출_백만2010USD_계절조정":
        "Exports Merchandise, Customs, constant 2010 US$, millions, seas. adj..xlsx",
    "세계_실질상품수입_백만2010USD_계절조정":
        "Imports Merchandise, Customs, constant 2010 US$, millions, seas. adj..xlsx",
    "세계_산업생산_백만2010USD_계절조정":
        "Industrial Production, constant 2010 US$, seas. adj..xlsx",
}


def validate_monthly(frame: pd.DataFrame, name: str, end: str) -> pd.DataFrame:
    if "기준월" not in frame or frame.columns.duplicated().any():
        raise ValueError(f"{name}: PK 또는 컬럼 이름에 오류가 있습니다.")
    frame = frame.loc[frame["기준월"].between(START, end)].copy()
    frame = frame.sort_values("기준월").reset_index(drop=True)
    if frame["기준월"].tolist() != expected_months(end):
        raise ValueError(f"{name}: {START}~{end} 월이 누락·중복되었거나 PK가 잘못되었습니다.")
    numeric = frame.columns.drop("기준월")
    frame[numeric] = frame[numeric].apply(pd.to_numeric, errors="raise")
    if frame[numeric].isna().any().any():
        raise ValueError(f"{name}: 분석 기간에 결측값이 있습니다.")
    return frame


def build_rwi() -> pd.DataFrame:
    # Output 시트 7행부터 월별 자료. B=원계열, C=계절·근무일 조정.
    source = pd.read_excel(RWI_RAW, sheet_name="Output", header=None)
    dates = pd.to_datetime(source.iloc[:, 0], format="%Y-%m-%d", errors="coerce")
    rows = source.loc[dates.notna(), [1, 2]].copy()
    rows.insert(0, "기준월", dates.loc[dates.notna()].dt.strftime("%Y-%m"))
    rows.columns = [
        "기준월",
        "RWI_원계열_미사용",
        "글로벌_컨테이너처리량지수",
    ]
    rows = rows.drop(columns="RWI_원계열_미사용")
    result = validate_monthly(rows, "RWI/ISL", RWI_END)
    if (result.iloc[:, 1:] <= 0).any().any():
        raise ValueError("RWI/ISL 지수에 0 이하 값이 있습니다.")
    return result


def read_gem_world(archive: ZipFile, member: str, column: str) -> pd.DataFrame:
    # 월별 시트의 첫 행은 지역명, 둘째 행은 공백, 이후 YYYYMMM 행이다.
    source = pd.read_excel(BytesIO(archive.read(member)), sheet_name="monthly")
    if "World (WBG members)" not in source.columns:
        raise ValueError(f"GEM 세계 집계 컬럼이 없습니다: {member}")
    dates = source.iloc[:, 0].astype(str)
    valid = dates.str.fullmatch(r"\d{4}M\d{2}")
    rows = source.loc[valid, [source.columns[0], "World (WBG members)"]].copy()
    rows.columns = ["기준월", column]
    rows["기준월"] = pd.to_datetime(
        rows["기준월"].str.replace("M", "-", regex=False),
        format="%Y-%m", errors="raise",
    ).dt.strftime("%Y-%m")
    if column.startswith("세계_산업생산"):
        # GEM 산업생산 원자료는 달러 단위. 다른 두 지표와 단위를 맞춰 백만 달러로 변환.
        rows[column] = pd.to_numeric(rows[column], errors="raise") / 1_000_000
    return validate_monthly(rows, f"GEM {column}", GEM_END)


def build_gem() -> pd.DataFrame:
    result = pd.DataFrame({"기준월": expected_months(GEM_END)})
    with ZipFile(GEM_RAW) as archive:
        for column, member in GEM_FILES.items():
            part = read_gem_world(archive, member, column)
            result = result.merge(part, on="기준월", how="left", validate="one_to_one")
    result = validate_monthly(result, "GEM 통합", GEM_END)
    if (result.iloc[:, 1:] <= 0).any().any():
        raise ValueError("GEM 자료에 0 이하 값이 있습니다.")
    return result


def build_gscpi() -> pd.DataFrame:
    source = pd.read_excel(GSCPI_RAW, sheet_name="GSCPI Monthly Data", engine="xlrd")
    dates = pd.to_datetime(source["Date"], format="%d-%b-%Y", errors="coerce")
    rows = source.loc[dates.notna(), ["GSCPI"]].copy()
    rows.insert(0, "기준월", dates.loc[dates.notna()].dt.strftime("%Y-%m"))
    rows = rows.rename(columns={"GSCPI": "글로벌_공급망압력지수(표준편차)"})
    return validate_monthly(rows, "뉴욕연준 GSCPI", GSCPI_END)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", choices=("rwi", "gem", "gscpi"),
                        help="지정한 원천만 재생성합니다.")
    choice = parser.parse_args().only
    builders = {"rwi": (RWI_OUT, build_rwi),
                "gem": (GEM_OUT, build_gem),
                "gscpi": (GSCPI_OUT, build_gscpi)}
    outputs = [(path, build()) for name, (path, build) in builders.items()
               if choice is None or name == choice]
    OUT.mkdir(parents=True, exist_ok=True)
    for path, frame in outputs:
        if path.exists():
            existing = pd.read_csv(path, encoding="utf-8-sig")
            schema_changed = list(existing.columns) != list(frame.columns)
            # 이미 검토한 출력 스키마가 달라진 경우에도 원천에서 다시 만든
            # 동일 관측값만 덮어쓴다. 종전 열의 보존 여부는 별도 archive에서 확인한다.
            comparable = frame.iloc[:len(existing)].reset_index(drop=True)
            if path == RWI_OUT:
                existing = existing.rename(columns={
                    "세계_컨테이너항만처리량지수_계절근무일조정(2015=100)":
                    "글로벌_컨테이너처리량지수",
                }).drop(columns=["세계_컨테이너항만처리량지수_원계열(2015=100)"],
                        errors="ignore")
            try:
                pd.testing.assert_frame_equal(
                    existing, comparable, check_dtype=False, check_exact=False,
                    rtol=1e-12, atol=1e-12,
                )
            except AssertionError as error:
                raise FileExistsError(
                    f"기존 processed 파일의 내용이 다릅니다. 확인 후 갱신하세요: {path}"
                ) from error
            else:
                if len(existing) < len(frame) or schema_changed:
                    frame.to_csv(path, index=False, encoding="utf-8-sig")
                    print(f"{path.name}: 원천값 검증 후 스키마 갱신")
                    continue
                print(f"{path.name}: 기존 파일과 동일하여 유지")
                continue
        frame.to_csv(path, index=False, encoding="utf-8-sig")
        print(f"{path.name}: {len(frame)}개월, {len(frame.columns) - 1}개 지표")


if __name__ == "__main__":
    main()
