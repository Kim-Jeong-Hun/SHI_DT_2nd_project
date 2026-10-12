"""월간 선종별 수주용량의 근거가 확인된 빈칸만 raw에 보완한다.

반올림 기사값과 쉼표 오탈자 정규화 값은 C 등급·근사값으로 명시한다.
다른 선종, 다른 단위(CGT/DWT/TEU/CBM), 인도량, 수정된 누계 차감값은
월간 신규수주 실측치로 간주하지 않는다. 재실행 시 중복 행을 만들지 않는다.

실행: python scripts/전처리/수주실적_기사보완.py [--check-only]
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "data" / "raw" / "수주실적.csv"

# period, vessel, count, capacity, unit, source id, publisher, URL,
# snapshot date (blank when the report gives none), article date, method, note.
EVIDENCE = (
    (
        "2023-07", "Bulk Carrier", 17, 1380000, "DWT", "CSERC_2023_07",
        "中国船舶经研中心 / Sohu", "https://www.sohu.com/a/711112375_121119389",
        "", "2023-08-12", "rounded_monthly_report",
        "Article reports 17 bulk carriers and 1.38 million DWT. Rounded to 0.01 million DWT; "
        "its all-ship count differs from the Clarksons monthly-report vintage used for adjacent months.",
    ),
    (
        "2023-07", "Container", 28, 388000, "TEU", "ZSCF_2023_07",
        "招商期货 / Clarksons", "https://www.fxbaogao.com/detail/3842136",
        "", "2023-08-12", "rounded_monthly_report",
        "Report states 28 new container ships and 388 thousand TEU; rounded to 1000 TEU. "
        "This is a different report vintage from adjacent Clarksons-cited monthly snapshots.",
    ),
    (
        "2023-10", "Container", 2, 2500, "TEU", "QH168_2023_10",
        "期货研究报告 / Clarksons", "https://www.qh168.com.cn/Upload/file/20231218/20231218103099899989.pdf",
        "", "2023-12-18", "secondary_monthly_report",
        "Report states two global container newbuilding orders totaling 2500 TEU in October 2023. "
        "Source vintage differs from adjacent monthly reports.",
    ),
    (
        "2026-06", "Chemical Tanker", 26, 823300, "DWT", "CISN_2026_06",
        "铸造头条 / 国际船舶网", "https://zhuzaotoutiao.com/xw/html/23970.shtml",
        "2026-07-09", "2026-07-23", "malformed_separator_normalized",
        "The monthly report prints 26 chemical tankers and '8,233,00' DWT. "
        "Removing the malformed thousands separators yields 823300 DWT; "
        "the corrected figure is not independently confirmed, so treat it as provisional.",
    ),
)

PARENTS = {"Chemical Tanker": "Tanker", "Oil Tanker": "Tanker"}
APPROXIMATE = {"rounded_monthly_report", "malformed_separator_normalized"}


def enriched(raw: pd.DataFrame) -> tuple[pd.DataFrame, int]:
    if raw.duplicated(["frequency", "period", "vessel_type"]).any():
        raise ValueError("기존 raw에 주기·월·선종 중복이 있습니다.")
    additions = []
    for (month, vessel, count, capacity, unit, source_id, publisher, url,
         snapshot, published, method, note) in EVIDENCE:
        match = raw.loc[
            raw["frequency"].eq("monthly") & raw["period"].eq(month)
            & raw["vessel_type"].eq(vessel)
        ]
        if not match.empty:
            existing = match.iloc[0]
            if (str(existing["capacity_value"]) != str(capacity)
                    or existing["capacity_unit"] != unit
                    or str(existing["new_orders_no"]) != str(count)):
                raise ValueError(f"기존 값과 보완 근거가 충돌합니다: {month} {vessel}")
            continue
        period = pd.Period(month, freq="M")
        row = dict.fromkeys(raw.columns, "")
        row.update({
            "frequency": "monthly", "period": month,
            "period_start": period.start_time.date().isoformat(),
            "period_end": period.end_time.date().isoformat(),
            "vessel_type": vessel, "parent_vessel_type": PARENTS.get(vessel, vessel),
            "new_orders_no": str(count), "capacity_value": str(capacity),
            "capacity_unit": unit, "source_id": source_id,
            "publisher": publisher, "source_url": url, "as_of_date": snapshot,
            "observation_method": method, "quality_grade": "C",
            "is_approximate": str(method in APPROXIMATE).lower(),
            "revision_risk": "high", "target_usable": "true",
            "ml_target_complete": "true",
            "definition_notes": f"{note} published_date={published}",
        })
        additions.append(row)
    result = pd.concat([raw, pd.DataFrame(additions, columns=raw.columns)], ignore_index=True)
    result["_order"] = range(len(result))
    result = result.sort_values(["period", "_order"], kind="stable").drop(columns="_order")
    return result.reset_index(drop=True), len(additions)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    raw = pd.read_csv(SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    result, added = enriched(raw)
    if not args.check_only and added:
        temporary = SOURCE.with_suffix(".csv.tmp")
        result.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
        temporary.replace(SOURCE)
    print(f"근거 기반 보완 행={added}, 전체 행={len(result)}")


if __name__ == "__main__":
    main()
