"""통합 수주실적 원본에서 5개 선종의 월별 가공본을 재현한다.

처리 규칙
1. data/raw/수주실적.csv를 문자열로 읽어 원본 표기를 보존한다.
2. frequency가 monthly인 행만 사용한다.
3. 지정한 5개 vessel_type을 각각 분리한다.
4. 원본에서 단위, 척수·용량의 0 여부, 월 키를 검증한다.
5. 가공본은 첫 관측월부터 마지막 관측월까지 월 달력을 유지한다. 원본에 없는
   월의 수주용량은 결측으로 두고, 정확히 1·2·3개월 전의 수주용량을 붙인다.
   원본에 없는 월을 0이나 직전 관측월로 대체하지 않는다.
6. 기존 processed 파일을 직접 수정하지 않으며 스크립트 실행 결과로만 저장한다.

실행 예시
    python scripts/전처리/수주실적_전처리.py
    python scripts/전처리/수주실적_전처리.py --check-only
    python scripts/전처리/수주실적_전처리.py --ship-type 벌크선
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from ship_orders_forecasting.order_availability import PROCESSED_ORDER_LAG_COLUMNS  # noqa: E402

SOURCE_PATH = PROJECT_ROOT / "data" / "raw" / "수주실적.csv"
PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"

SHIP_TYPES = {
    "벌크선": "Bulk Carrier",
    "케미컬 탱커": "Chemical Tanker",
    "컨테이너선": "Container",
    "가스 운반선": "Gas Carrier",
    "유조선": "Oil Tanker",
}

COLUMN_MAP = {
    "frequency": "주기",
    "period": "기준월",
    "period_start": "기간시작일",
    "period_end": "기간종료일",
    "vessel_type": "선종",
    "parent_vessel_type": "상위선종",
    "new_orders_no": "신규수주척수",
    "capacity_value": "수주용량",
    "capacity_unit": "수주용량단위",
    "source_id": "출처ID",
    "publisher": "발행기관",
    "source_url": "출처URL",
    "as_of_date": "자료발표일",
    "observation_method": "관측방법",
    "quality_grade": "품질등급",
    "is_approximate": "근사값여부",
    "revision_risk": "수정위험도",
    "target_usable": "종속변수사용가능여부",
    "ml_target_complete": "ML종속변수완비여부",
    "definition_notes": "정의및주의사항",
    "reported_contract_value_usd": "실제계약금액_USD",
    "newbuilding_price_index": "신조선가지수",
    "benchmark_newbuilding_price_usd": "기준신조선가_USD",
    "benchmark_capacity_value": "기준선박용량",
    "benchmark_capacity_unit": "기준선박용량단위",
    "estimated_order_value_usd": "월간추정수주금액_USD",
    "value_estimation_method": "금액추정방법",
    "value_source_url": "금액출처URL",
    "value_quality_grade": "금액품질등급",
}

TARGET_UNITS = {
    "벌크선": "DWT",
    "케미컬 탱커": "DWT",
    "컨테이너선": "TEU",
    "가스 운반선": "CBM",
    "유조선": "DWT",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="통합 수주실적 원본에서 선종별 월별 가공본 5개를 생성합니다."
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="저장하지 않고 기존 가공본이 현재 원본과 일치하는지 검사합니다.",
    )
    parser.add_argument(
        "--ship-type",
        choices=list(SHIP_TYPES),
        help="지정한 선종만 생성하거나 검사합니다. 생략하면 5개 선종을 모두 처리합니다.",
    )
    return parser.parse_args()


def load_source() -> pd.DataFrame:
    source = pd.read_csv(
        SOURCE_PATH,
        encoding="utf-8-sig",
        dtype=str,
        keep_default_na=False,
    )
    expected = list(COLUMN_MAP)
    if source.columns.tolist() != expected:
        missing = [column for column in expected if column not in source.columns]
        extra = [column for column in source.columns if column not in expected]
        raise ValueError(
            "수주실적.csv 컬럼 구성이 전처리 규칙과 다릅니다. "
            f"누락={missing}, 추가={extra}"
        )
    return source


def build_processed(source: pd.DataFrame, ship_type: str) -> pd.DataFrame:
    source_name = SHIP_TYPES[ship_type]
    selected = source.loc[
        source["frequency"].eq("monthly")
        & source["vessel_type"].eq(source_name),
        ["period", "vessel_type", "new_orders_no", "capacity_value", "capacity_unit"],
    ].copy()

    if selected.empty:
        raise ValueError(f"월별 수주실적이 없습니다: {ship_type} ({source_name})")
    if not selected["period"].str.fullmatch(r"\d{4}-(0[1-9]|1[0-2])").all():
        raise ValueError(f"{ship_type} 기준월에 YYYY-MM 이외의 값이 있습니다.")
    if selected["period"].duplicated().any():
        duplicated = selected.loc[
            selected["period"].duplicated(keep=False), "period"
        ].unique()
        raise ValueError(f"{ship_type} 기준월 중복: {', '.join(duplicated[:10])}")
    if not selected["vessel_type"].eq(source_name).all():
        raise ValueError(f"{ship_type} 가공본에 다른 선종이 포함됐습니다.")
    unit = TARGET_UNITS[ship_type]
    if not selected["capacity_unit"].eq(unit).all():
        invalid_units = sorted(set(selected["capacity_unit"]) - {unit})
        raise ValueError(f"{ship_type} 수주용량단위는 {unit}이어야 합니다: {invalid_units}")
    for column in ("new_orders_no", "capacity_value"):
        selected[column] = pd.to_numeric(selected[column], errors="raise")
        if selected[column].isna().any() or selected[column].lt(0).any():
            raise ValueError(f"{ship_type} {column}에 결측 또는 음수가 있습니다.")
    if ((selected["new_orders_no"] == 0) != (selected["capacity_value"] == 0)).any():
        raise ValueError(f"{ship_type} 척수와 수주용량의 0 여부가 다릅니다.")

    processed = selected[["period", "vessel_type", "capacity_value"]].rename(
        columns={"period": "기준월", "vessel_type": "선종", "capacity_value": f"수주용량({unit})"}
    )
    processed = processed.sort_values("기준월", kind="stable").reset_index(drop=True)
    periods = pd.period_range(processed["기준월"].min(),
                              processed["기준월"].max(), freq="M")
    calendar = pd.DataFrame({"기준월": periods.astype(str)})
    processed = calendar.merge(processed, on="기준월", how="left", validate="one_to_one")
    processed["선종"] = source_name
    capacity = f"수주용량({unit})"
    values = pd.Series(processed[capacity].to_numpy(), index=periods)
    for lag, column in PROCESSED_ORDER_LAG_COLUMNS.items():
        processed[column] = values.reindex(periods - lag).to_numpy()
    return processed


def output_path(ship_type: str) -> Path:
    return PROCESSED_DIR / ship_type / f"수주실적({ship_type}).csv"


def csv_text(processed: pd.DataFrame) -> str:
    return processed.to_csv(index=False, lineterminator="\n", float_format="%.15g")


def save_processed(processed: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    temporary.write_text(csv_text(processed), encoding="utf-8-sig", newline="")
    temporary.replace(output)


def check_existing(processed: pd.DataFrame, output: Path) -> None:
    if not output.exists():
        raise FileNotFoundError(f"비교할 기존 가공본이 없습니다: {output}")
    existing = output.read_text(encoding="utf-8-sig")
    expected = csv_text(processed)
    if existing != expected:
        raise ValueError(f"{output.name} 내용이 현재 원본과 전처리 규칙에 맞지 않습니다.")


def main() -> None:
    args = parse_args()
    source = load_source()
    selected = [args.ship_type] if args.ship_type else list(SHIP_TYPES)
    summaries: list[dict[str, object]] = []

    for ship_type in selected:
        processed = build_processed(source, ship_type)
        output = output_path(ship_type)
        if args.check_only:
            check_existing(processed, output)
            status = "일치"
        else:
            save_processed(processed, output)
            check_existing(processed, output)
            status = "생성 완료"

        summaries.append({
            "상태": status,
            "선종": ship_type,
            "행": len(processed),
            "시작월": processed["기준월"].min(),
            "종료월": processed["기준월"].max(),
            "출력파일": str(output),
        })

    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()
