"""월보에서 입증되는 선종별 0건만 수주실적 원본에 복원한다.

월보의 선종별 신규수주 척수 합이 해당 월 전체 척수와 일치하고,
2016-06 이후 별도 집계되는 분석 선종이 그 목록에 없을 때만 0으로 본다.
2016-05 등 월보 자체가 없는 달과 2015년의 케미컬선 공백은 채우지 않는다.
수정된 후속 누계에서 월별 값을 역산하거나 선형 보간하지 않는다.

아래 표는 각 월의 기사 본문 첫 번째 '从船型上来看' 신규수주 내역을
2026-10-04에 확인한 결과다. 숫자는 월보의 전 선종 신규수주 총 척수다.
기사 URL과 발표일은 동일 월의 기존 raw 행에서 이어받는다.
2016-07 기사의 소제목에는 54척이라는 오기가 있으나, 본문 총계와
선종별 합계는 모두 25척이다. 2022-02 등 후속 누계가 수정되는 사례가
있으므로 보완된 0은 해당 월보 발표 당시의 빈티지로만 해석한다.

실행: python scripts/전처리/수주실적_결측보완.py [--check-only]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "raw" / "수주실적.csv"
UNITS = {
    "Bulk Carrier": "DWT",
    "Chemical Tanker": "DWT",
    "Container": "TEU",
    "Gas Carrier": "CBM",
    "Oil Tanker": "DWT",
}
PARENTS = {"Chemical Tanker": "Tanker", "Oil Tanker": "Tanker"}

# month: (published all-ship count, absent separately classified ship types)
ZERO_EVIDENCE = {
    "2015-05": (64, "Bulk Carrier"),
    "2016-01": (17, "Gas Carrier"),
    "2016-03": (45, "Container", "Gas Carrier"),
    "2016-07": (25, "Bulk Carrier", "Chemical Tanker", "Gas Carrier"),
    "2016-08": (43, "Gas Carrier"),
    "2016-09": (20, "Bulk Carrier", "Oil Tanker"),
    "2016-10": (42, "Container", "Gas Carrier"),
    "2016-12": (24, "Chemical Tanker", "Oil Tanker"),
    "2017-01": (33, "Bulk Carrier"),
    "2017-02": (41, "Container", "Gas Carrier"),
    "2017-04": (41, "Container"),
    "2017-05": (62, "Container"),
    "2017-07": (34, "Container"),
    "2017-08": (36, "Gas Carrier"),
    "2017-10": (43, "Chemical Tanker", "Oil Tanker"),
    "2017-11": (64, "Gas Carrier"),
    "2018-06": (62, "Oil Tanker"),
    "2019-01": (83, "Chemical Tanker"),
    "2019-04": (46, "Container"),
    "2019-05": (35, "Container"),
    "2019-07": (32, "Container", "Gas Carrier"),
    "2019-08": (43, "Container"),
    "2019-10": (53, "Chemical Tanker"),
    "2020-01": (37, "Container"),
    "2020-04": (85, "Container"),
    "2020-05": (32, "Bulk Carrier"),
    "2020-06": (33, "Container"),
    "2021-08": (74, "Chemical Tanker"),
    "2021-11": (76, "Oil Tanker"),
    "2021-12": (63, "Chemical Tanker"),
    "2022-01": (100, "Oil Tanker"),
    "2022-02": (49, "Bulk Carrier", "Chemical Tanker"),
    "2022-04": (83, "Oil Tanker"),
}


def blank_row(columns: list[str]) -> dict[str, str]:
    return dict.fromkeys(columns, "")


def source_for_month(data: pd.DataFrame, month: str) -> pd.Series:
    same_month = data.loc[data["period"].eq(month)]
    if same_month.empty:
        raise ValueError(f"근거가 되는 원본 월이 없습니다: {month}")
    for field in ("source_id", "source_url", "as_of_date", "publisher"):
        if same_month[field].nunique() != 1 or not same_month[field].iloc[0]:
            raise ValueError(f"{month}의 {field}가 단일한 값이 아닙니다.")
    first = same_month.iloc[0]
    if first["source_id"] != "EWS_" + month.replace("-", "_"):
        raise ValueError(f"{month}은 검증된 Eworldship 기사와 연결되지 않습니다.")
    return first


def make_zero(
    columns: list[str], source: pd.Series, month: str, vessel: str, total: int
) -> dict[str, str]:
    period = pd.Period(month, freq="M")
    row = blank_row(columns)
    for field in ("source_id", "publisher", "source_url", "as_of_date"):
        row[field] = source[field]
    row.update({
        "frequency": "monthly",
        "period": month,
        "period_start": period.start_time.date().isoformat(),
        "period_end": period.end_time.date().isoformat(),
        "vessel_type": vessel,
        "parent_vessel_type": PARENTS.get(vessel, vessel),
        "new_orders_no": "0",
        "capacity_value": "0",
        "capacity_unit": UNITS[vessel],
        "observation_method": "derived_zero_from_exhaustive_monthly_total",
        "quality_grade": "B",
        "is_approximate": "false",
        "revision_risk": "high",
        "target_usable": "true",
        "ml_target_complete": "true",
        "definition_notes": (
            f"At {source['as_of_date']} snapshot, the reported {total} all-ship orders "
            "equal the sum of listed vessel-category counts; this category was "
            "absent. Inferred zero, not a direct observation; later revisions may "
            "change it."
        ),
    })
    if month == "2015-05" and vessel == "Bulk Carrier":
        row["definition_notes"] += (
            " Independent contemporary confirmation of no bulk orders: "
            "https://wap.ejc56.com/Home/DTDetail?id=54141"
        )
    return row


def make_tanker_sum(
    columns: list[str], oil: pd.Series, chemical: pd.Series
) -> dict[str, str]:
    if any(oil[field] != chemical[field] for field in ("source_id", "source_url", "as_of_date")):
        raise ValueError(f"{oil['period']} 유조선·케미컬선 출처 빈티지가 다릅니다.")
    row = blank_row(columns)
    for field in (
        "frequency", "period", "period_start", "period_end", "source_id",
        "publisher", "source_url", "as_of_date",
    ):
        row[field] = oil[field]
    row.update({
        "vessel_type": "Tanker incl. Chemical",
        "parent_vessel_type": "Tanker",
        "new_orders_no": str(int(oil["new_orders_no"]) + int(chemical["new_orders_no"])),
        "capacity_value": str(int(oil["capacity_value"]) + int(chemical["capacity_value"])),
        "capacity_unit": "DWT",
        "observation_method": "derived_sum_oil_plus_chemical",
        "quality_grade": "B",
        "is_approximate": "false",
        "revision_risk": "high",
        "target_usable": "true",
        "ml_target_complete": "true",
        "definition_notes": (
            "Oil tanker plus chemical tanker from the same monthly report "
            "vintage. Includes inferred zero where marked in component rows."
        ),
    })
    return row


def enriched(data: pd.DataFrame) -> tuple[pd.DataFrame, int, int]:
    if data.duplicated(["frequency", "period", "vessel_type"]).any():
        raise ValueError("기존 원본에 주기·월·선종 중복이 있습니다.")
    columns = data.columns.tolist()
    new_rows: list[dict[str, str]] = []
    for month, evidence in ZERO_EVIDENCE.items():
        total, *missing_types = evidence
        if not isinstance(total, int) or total <= 0:
            raise ValueError(f"{month} 월보 총 척수가 유효하지 않습니다.")
        source = source_for_month(data, month)
        for vessel in missing_types:
            if vessel not in UNITS or (vessel == "Chemical Tanker" and month < "2016-06"):
                raise ValueError(f"{month}의 선종 분류는 0 추론이 불가능합니다: {vessel}")
            existing = data.loc[data["period"].eq(month) & data["vessel_type"].eq(vessel)]
            if existing.empty:
                new_rows.append(make_zero(columns, source, month, vessel, total))
            elif (
                len(existing) != 1
                or existing.iloc[0]["observation_method"] != "derived_zero_from_exhaustive_monthly_total"
                or existing.iloc[0]["new_orders_no"] != "0"
                or existing.iloc[0]["capacity_value"] != "0"
                or existing.iloc[0]["capacity_unit"] != UNITS[vessel]
            ):
                raise ValueError(f"{month} {vessel}이 기존 관측값과 충돌합니다.")

    with_zeros = pd.concat([data, pd.DataFrame(new_rows, columns=columns)], ignore_index=True)
    extra_sums: list[dict[str, str]] = []
    for month, group in with_zeros.groupby("period", sort=True):
        by_vessel = group.set_index("vessel_type")
        if not by_vessel.index.is_unique:
            raise ValueError(f"{month}에 선종 중복이 있습니다.")
        if not {"Oil Tanker", "Chemical Tanker"}.issubset(by_vessel.index):
            continue
        oil = by_vessel.loc["Oil Tanker"]
        chemical = by_vessel.loc["Chemical Tanker"]
        expected = make_tanker_sum(columns, oil, chemical)
        if "Tanker incl. Chemical" not in by_vessel.index:
            extra_sums.append(expected)
        else:
            actual = by_vessel.loc["Tanker incl. Chemical"]
            if any(actual[field] != expected[field] for field in ("new_orders_no", "capacity_value", "capacity_unit")):
                raise ValueError(f"{month} 기존 Tanker 합계가 구성 선종과 다릅니다.")

    result = pd.concat([with_zeros, pd.DataFrame(extra_sums, columns=columns)], ignore_index=True)
    result["_order"] = range(len(result))
    result = result.sort_values(["period", "_order"], kind="stable").drop(columns="_order").reset_index(drop=True)
    if result.duplicated(["frequency", "period", "vessel_type"]).any():
        raise ValueError("결과 원본에 주기·월·선종 중복이 있습니다.")
    return result, len(new_rows), len(extra_sums)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true", help="저장 없이 변경 행 수를 확인합니다.")
    args = parser.parse_args()
    data = pd.read_csv(SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    result, zeros, sums = enriched(data)
    if not args.check_only and (zeros or sums):
        temporary = SOURCE.with_suffix(".csv.tmp")
        result.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        temporary.replace(SOURCE)
    print(f"0건 보완={zeros}, Tanker 합계 추가={sums}, 전체 행={len(result)}")


if __name__ == "__main__":
    main()
