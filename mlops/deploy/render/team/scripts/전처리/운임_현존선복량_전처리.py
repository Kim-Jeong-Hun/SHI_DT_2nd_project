"""공개 운임과 UNCTAD 현존 선복량을 월별 수주예측 입력으로 정리한다.

운임은 관측월 원값을 보존한다. 선복량은 연초의 연간 재고(stock)이므로
월간 값으로 보간하지 않는다. 마스터 단계에서 전년도 연초 재고만 사용한다.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed" / "공통"
BDI_PATH = RAW / "핀란드기술산업협회_BDI_월별_원표.csv"
XSI_PATH = RAW / "xsi_c_csv_20261002" / "XSI-C_전노선_월평균운임_한글.csv"
OPEC_PATH = RAW / "OPEC_VLCC_중동동아시아_월별_원표추출.csv"
FLEET_PATH = RAW / "US_MerchantFleet.csv"
FREIGHT_OUT = OUT / "선종별운임(월).csv"
FLEET_OUT = OUT / "현존선복량(글로벌, 연).csv"
FIRST_MONTH = "2015-01"
LAST_MONTH = "2026-09"

FREIGHT_COLUMNS = [
    "기준월", "벌크선운임(BDI점수)",
    "유조선(VLCC)운임(WS점수)",
    "컨테이너운임_극동북유럽(USD/FEU)",
]
FLEET_TYPES = {"2": "벌크선", "1": "유조선", "4": "컨테이너선"}


def read_bdi() -> pd.DataFrame:
    source = pd.read_csv(BDI_PATH, sep=";", encoding="utf-8-sig", dtype={"Kuukausi": "string"})
    if source.columns.tolist() != ["Kuukausi", "Sea freight prices"]:
        raise ValueError("BDI 원표 헤더가 예상과 다릅니다.")
    months = pd.PeriodIndex(source["Kuukausi"].str.replace(".", "-", regex=False), freq="M")
    if source.empty or list(months) != list(pd.period_range(months[0], months[-1], freq="M")):
        raise ValueError("BDI 원표의 월이 비었거나 중복·불연속입니다.")
    if months[0] > pd.Period(FIRST_MONTH, freq="M"):
        raise ValueError("BDI 원표에 2015-01부터의 이력이 없습니다.")
    source["벌크선운임(BDI점수)"] = pd.to_numeric(source["Sea freight prices"], errors="raise")
    if source["벌크선운임(BDI점수)"].isna().any() or source["벌크선운임(BDI점수)"].le(0).any():
        raise ValueError("BDI 원표에 결측 또는 0 이하 값이 있습니다.")
    source["기준월"] = months.astype(str)
    return source.loc[
        source["기준월"].between(FIRST_MONTH, LAST_MONTH), ["기준월", "벌크선운임(BDI점수)"]
    ].copy()


def read_opec() -> pd.DataFrame:
    source = pd.read_csv(OPEC_PATH, encoding="utf-8-sig")
    raw_column = "유조선운임_VLCC_중동동아시아_WS"
    column = "유조선(VLCC)운임(WS점수)"
    needed = ["기준월", raw_column, "보고서월", "보고서URL", "수집상태"]
    if any(name not in source for name in needed):
        raise KeyError(f"OPEC 운임 필수 컬럼 누락: {needed}")
    if source["기준월"].duplicated().any():
        raise ValueError("OPEC 운임에 중복 월이 있습니다.")
    source = source.sort_values("기준월").reset_index(drop=True)
    if source.empty or source["기준월"].iloc[0] != FIRST_MONTH:
        raise ValueError("OPEC 운임은 2015-01부터 시작해야 합니다.")
    if source["기준월"].tolist() != pd.period_range(
        FIRST_MONTH, source["기준월"].iloc[-1], freq="M"
    ).astype(str).tolist():
        raise ValueError("OPEC 운임 월별 구간이 연속적이지 않습니다.")
    if source["기준월"].iloc[-1] > LAST_MONTH:
        raise ValueError("OPEC 운임이 현재 전처리 종료월 이후까지 포함됩니다.")
    if not source["수집상태"].isin(["추출", "후속보고서보완"]).all():
        raise ValueError("OPEC 운임 원표 추출 실패 월이 남았습니다.")
    source[raw_column] = pd.to_numeric(source[raw_column], errors="raise")
    if source[raw_column].isna().any() or source[raw_column].le(0).any():
        raise ValueError("OPEC 운임에 결측 또는 0 이하 값이 있습니다.")
    report = pd.to_datetime(source["보고서월"] + "-01", errors="raise")
    observed = pd.to_datetime(source["기준월"] + "-01", errors="raise")
    lag = (report.dt.year - observed.dt.year) * 12 + report.dt.month - observed.dt.month
    if not lag.between(1, 2).all():
        raise ValueError("OPEC 보고서월은 관측월보다 1~2개월 늦어야 합니다.")
    if not source["보고서URL"].str.startswith("https://www.opec.org/").all():
        raise ValueError("OPEC 보고서 URL이 불분명합니다.")
    return source[["기준월", raw_column]].rename(columns={raw_column: column})


def build_freight() -> pd.DataFrame:
    bdi = read_bdi()

    xsi = pd.read_csv(XSI_PATH, encoding="utf-8-sig")
    route = "극동→북유럽(USD/FEU)"
    needed = ["년도", "월", route]
    if any(column not in xsi for column in needed):
        raise KeyError(f"XSI-C 필수 컬럼 누락: {needed}")
    xsi["기준월"] = pd.to_datetime(
        dict(year=xsi["년도"], month=xsi["월"], day=1), errors="raise"
    ).dt.strftime("%Y-%m")
    if xsi["기준월"].duplicated().any():
        raise ValueError("XSI-C에 중복 월이 있습니다.")
    xsi[route] = pd.to_numeric(xsi[route], errors="raise")
    if xsi[route].dropna().le(0).any():
        raise ValueError("XSI-C 운임에 0 이하 값이 있습니다.")
    xsi = xsi.loc[
        xsi["기준월"].between(FIRST_MONTH, LAST_MONTH), ["기준월", route]
    ].rename(columns={route: "컨테이너운임_극동북유럽(USD/FEU)"})

    calendar = pd.DataFrame(
        {"기준월": pd.period_range(FIRST_MONTH, LAST_MONTH, freq="M").astype(str)}
    )
    out = calendar.merge(bdi, on="기준월", how="left", validate="one_to_one")
    out = out.merge(xsi, on="기준월", how="left", validate="one_to_one")
    out = out.merge(read_opec(), on="기준월", how="left", validate="one_to_one")
    required_through_last_month = ["컨테이너운임_극동북유럽(USD/FEU)"]
    if out[required_through_last_month].isna().any().any():
        missing = out.loc[out[required_through_last_month].isna().any(axis=1), "기준월"]
        raise ValueError(f"운임 결측 월: {missing.tolist()[:10]}")
    return out[FREIGHT_COLUMNS]


def build_fleet() -> pd.DataFrame:
    source = pd.read_csv(
        FLEET_PATH, encoding="utf-8-sig", low_memory=False,
        dtype={"Economy": "string", "ShipType": "string"},
    )
    required = [
        "Year", "Economy", "ShipType", "ShipType Label",
        "Dead weight tons in thousands", "Number of ships",
    ]
    if any(column not in source for column in required):
        raise KeyError(f"UNCTAD 필수 컬럼 누락: {required}")
    world = source.loc[
        source["Economy"].eq("0000")
        & source["ShipType"].isin(FLEET_TYPES)
        & source["Year"].between(2014, 2026),
        required,
    ].copy()
    if world.duplicated(["Year", "ShipType"]).any():
        raise ValueError("UNCTAD 세계·연도·선종 중복이 있습니다.")
    world["현존선복량_백만DWT"] = pd.to_numeric(
        world["Dead weight tons in thousands"], errors="raise"
    ) / 1000
    world["현존선박척수"] = pd.to_numeric(world["Number of ships"], errors="raise")
    if world[["현존선복량_백만DWT", "현존선박척수"]].isna().any().any():
        raise ValueError("UNCTAD 선복량·척수에 결측이 있습니다.")
    if world[["현존선복량_백만DWT", "현존선박척수"]].le(0).any().any():
        raise ValueError("UNCTAD 선복량·척수에 0 이하 값이 있습니다.")
    world["선종"] = world["ShipType"].map(FLEET_TYPES)
    world["기준연도"] = world["Year"].astype(int)
    world["월별사용시작연도"] = world["기준연도"] + 1
    out = world[[
        "기준연도", "선종", "현존선복량_백만DWT", "현존선박척수",
        "월별사용시작연도",
    ]].sort_values(["선종", "기준연도"]).reset_index(drop=True)
    for ship_type in FLEET_TYPES.values():
        years = out.loc[out["선종"].eq(ship_type), "기준연도"]
        if not set(range(2014, 2027)).issubset(set(years)):
            raise ValueError(f"{ship_type} 2014~2026 선복량이 연속적이지 않습니다.")
    return out


def save_or_check(data: pd.DataFrame, path: Path, check_only: bool) -> None:
    if check_only:
        existing = pd.read_csv(path, encoding="utf-8-sig")
        pd.testing.assert_frame_equal(data, existing, check_dtype=False, rtol=1e-12)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    data.to_csv(path, index=False, encoding="utf-8-sig", lineterminator="\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    freight = build_freight()
    fleet = build_fleet()
    save_or_check(freight, FREIGHT_OUT, args.check_only)
    save_or_check(fleet, FLEET_OUT, args.check_only)
    print(f"운임 {len(freight)}개월 {freight['기준월'].min()}~{freight['기준월'].max()}")
    print(f"선복량 {len(fleet)}행 {fleet['기준연도'].min()}~{fleet['기준연도'].max()}")


if __name__ == "__main__":
    main()
