"""Append manually checked 2026 benchmark newbuilding prices to raw CSV.

Each monthly report names the benchmark size and USD price. Only the three
fixed-size benchmarks actually used by the model are entered. January lacks
a separately verified report and is left for the existing four-month carry
rule, rather than inventing an observation.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data/raw/신조선가_월별.csv"
# USD millions: Capesize 180/182 KDWT, Aframax 113/115 KDWT,
# Handy container 1800/2100 TEU. Verified against each linked monthly report.
REPORTS = {
    "2026-02": ("https://zhuzaotoutiao.com/xw/html/22572.shtml", 75.0, 72.5, 32.0),
    "2026-03": ("https://zhuzaotoutiao.com/xw/html/22950.shtml", 75.0, 73.5, 32.0),
    "2026-04": ("https://zhuzaotoutiao.com/xw/html/23214.shtml", 75.5, 74.0, 32.75),
    "2026-05": ("https://zhuzaotoutiao.com/mobile/xw/html/23612.shtml", 75.5, 74.5, 32.75),
    "2026-06": ("https://zhuzaotoutiao.com/xw/html/23970.shtml", 76.0, 75.0, 32.75),
    "2026-07": ("https://zhuzaotoutiao.com/mobile/xw/html/24320.shtml", 76.0, 75.0, 33.5),
    "2026-08": ("https://zhuzaotoutiao.com/xw/html/24728.shtml", 76.0, 75.5, 33.5),
}
BANDS = (
    ("Bulk Carrier", "Capesize", 180_000, 182_000, "DWT", 1),
    ("Oil Tanker", "Aframax", 113_000, 115_000, "DWT", 2),
    ("Container", "Handy container", 1_800, 2_100, "TEU", 3),
)


def main() -> None:
    existing = pd.read_csv(RAW, encoding="utf-8-sig")
    rows = []
    for period, (url, bulk, tanker, container) in REPORTS.items():
        prices = (bulk, tanker, container)
        for vessel, name, low, high, unit, position in BANDS:
            price = prices[position - 1]
            rows.append({
                "period": period,
                "source_id": f"CISN_{period.replace('-', '_')}",
                "vessel_type": vessel,
                "price_index": pd.NA,
                "benchmark_name": name,
                "capacity_min": float(low),
                "capacity_max": float(high),
                "capacity_avg": (low + high) / 2,
                "capacity_unit": unit,
                "benchmark_price_usd": int(price * 1_000_000),
                "source_url": url,
                "source_page_url": url,
                "extraction_method": "monthly_report_benchmark_price_manually_verified",
                "quality_grade": "C",
                "raw_excerpt": f"{name} {low}-{high} {unit}: USD {price:g} million",
            })
    added = pd.DataFrame(rows, columns=existing.columns)
    key = ["period", "vessel_type", "capacity_avg", "capacity_unit"]
    existing_keys = pd.MultiIndex.from_frame(existing[key])
    added_keys = pd.MultiIndex.from_frame(added[key])
    if added_keys.has_duplicates:
        raise ValueError("2026 신조선가 보완 행이 중복됩니다")
    overlapping = added_keys.isin(existing_keys)
    if overlapping.any():
        prior = existing.set_index(key).loc[added_keys[overlapping]].reset_index()
        current = added.loc[overlapping]
        if prior["benchmark_price_usd"].to_numpy().tolist() != current["benchmark_price_usd"].to_numpy().tolist():
            raise ValueError("기존 신조선가와 다른 가격이 있어 자동 덮어쓰지 않습니다")
    new = added.loc[~overlapping]
    if new.empty:
        print("2026 신조선가: 이미 반영됨")
        return
    combined = pd.concat([existing, new], ignore_index=True)
    combined = combined.sort_values(["period", "vessel_type", "capacity_avg"]).reset_index(drop=True)
    temporary = RAW.with_suffix(".csv.tmp")
    combined.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(RAW)
    print(f"2026 신조선가 {len(new)}행 추가: {new['period'].min()}~{new['period'].max()}")


if __name__ == "__main__":
    main()
