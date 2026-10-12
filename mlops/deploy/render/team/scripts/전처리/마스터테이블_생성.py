"""선종별 수주예측 마스터 테이블을 생성한다.

전처리 규칙
1. 선종별 수주실적 가공본의 기준월, 선종, 단위별 수주용량 및
   1·2·3개월 전 수주용량 열을 사용한다.
   척수·용량의 원본 검사는 수주실적 전처리 단계에서 완료한다.
2. 수주실적 시작월부터 수주 또는 월별 외부지표의 최신 완료월까지 월 달력을 만든다.
   수주실적이 아직 없는 최근 월의 목표값은 결측으로 둔다.
3. 원자료에 없는 월의 수주용량은 0으로 바꾸지 않고 결측으로 둔다.
4. 원유 평균은 모든 선종에 공통으로 사용한다.
5. 국제 원자재 가격은 선종과 직접 관련된 후보만 선종별로 선택한다.
6. 공표 지연과 2026년 불완전 합계가 있는 주요 원자재 물동량은 사용하지 않는다.
7. GPR·GPRT·GPRA는 후보로 보존한다. 예측 모형에는 과거 학습구간의
   종속변수와 상관계수 절댓값이 가장 큰 하나만 넣는다. GPRH는 폐기한다.
8. 중국 TPU는 사용한다. 미국 EPUTRADE·Caldara 중에서도 과거 학습구간의
   종속변수와 상관계수 절댓값이 가장 큰 하나만 예측 모형에 넣는다.
9. 모든 선종에 싱가포르 월별 벙커유 총판매량 원값을 결합한다.
   가격·판매량의 증감률 등 파생변수는 만들지 않는다.
10. 벌크선·컨테이너선·유조선에는 대표 용량대 신조선가를 결합한다.
   컨테이너선 2015-01~2016-05는 도표 추출 추정치(D등급)이며, 시차는
   분석 노트북에서 적용한다. 원천 품질·발표일은 processed에서 확인한다.
11. 벌크선·유조선·컨테이너선에 각 선종의 월별 운임지수를 결합한다.
   벌크 BDI는 월말 지수, 유조선 VLCC WS는 월평균, 컨테이너는 XSI-C
   극동→북유럽 항로의 월평균이다. 운임 시차는 노트북에서 적용한다.
12. 위 세 선종에는 UNCTAD 세계 선복량의 전년도 연초 DWT만 결합한다.
   연간·분기 자료는 processed의 사용가능월부터 다음 공표 전까지 계단형으로
   전방 채운다. 기간 시작일부터 미리 채우거나 선형 보간하지 않는다.
   현재 선복량은 기준연도의 다음 해 1월을 보수적인 사용가능월로 둔다.
13. RWI/ISL 컨테이너항만 처리량(계절·근무일 조정), 세계은행 GEM의
    실질 상품 수출·수입·산업생산, 뉴욕연준 GSCPI를 공통 후보로 결합한다.
    RWI 원계열은 processed에서도 제외한다. 세 세계 거시지표 중 하나는
    예측시점마다 학습구간의 목표값과 상관계수 절댓값이 가장 큰 것으로 고른다.
    운영 h+6 모델은 모든 외부지표에 공통 D=C-3 공개시차를 적용한다.
14. t-2 월보의 게시일이 확인되면 t-2, 아니면 t-3에서 끝나는
   최근 확정 단일월 1·2·3번째 수주 이력을 모든 선종에 만든다.
   게시일을 확인할 수 없는 과거 t-2는 사용하지 않는다. t-3의 게시일도
   미상인 과거 행은 보수적 근사로 표시하고 결측월은 0으로 채우지 않는다.
   h+6 분석은 별도로 모든 선종에서 3개월 공통 공개시차를 적용하고,
   processed의 달력 시차 열을 자료 마감월 D에 조회한다.
15. 월 중복·필수 컬럼 누락·과거 설명변수 결측이 있으면 저장하지 않는다.
   최근 12개월 이내의 불완전한 꼬리 구간은 기본 실행 시 결측을 유지한 채 저장한다.
   가장 늦은 완전월 이전의 구멍은 여전히 오류로 처리한다.
16. 출력은 UTF-8 BOM CSV이며 기준월 오름차순으로 저장한다.

실행 예시
    python scripts/전처리/마스터테이블_생성.py
    python scripts/전처리/마스터테이블_생성.py --check-only
    python scripts/전처리/마스터테이블_생성.py --ship-type 벌크선
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from ship_orders_forecasting.order_availability import (  # noqa: E402
    AVAILABLE_LAG_COLUMN,
    AVAILABILITY_STATUS_COLUMN,
    ORDER_POINT_LAG_COLUMNS,
    PROCESSED_ORDER_LAG_COLUMNS,
    available_order_point_lags,
    available_order_windows,
    publication_dates,
)

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
MASTER_DIR = PROJECT_ROOT / "data" / "master"
RAW_ORDERS_PATH = PROJECT_ROOT / "data" / "raw" / "수주실적.csv"
COMMODITY_PATH = PROCESSED_DIR / "공통" / "국제원자재가(월).csv"
RISK_PATH = PROCESSED_DIR / "공통" / "지정학위험지수(월).csv"
TRADE_POLICY_PATH = PROCESSED_DIR / "공통" / "무역정책불확실성지수(월).csv"
SHIP_PRICE_PATH = PROCESSED_DIR / "공통" / "신조선가(글로벌, 월).csv"
FREIGHT_PATH = PROCESSED_DIR / "공통" / "선종별운임(월).csv"
FLEET_PATH = PROCESSED_DIR / "공통" / "현존선복량(글로벌, 연).csv"
BUNKER_SALES_PATH = PROCESSED_DIR / "공통" / "싱가포르 벙커유 판매량(월).csv"
CONTAINER_INDEX_PATH = PROCESSED_DIR / "공통" / "세계 컨테이너항만 처리량지수(월).csv"
GLOBAL_ECONOMY_PATH = PROCESSED_DIR / "공통" / "세계 실질교역과 산업생산(월).csv"
SUPPLY_CHAIN_PATH = PROCESSED_DIR / "공통" / "글로벌 공급망압력지수(월).csv"

SHIP_TYPES = ["벌크선", "케미컬 탱커", "컨테이너선", "가스 운반선", "유조선"]
TARGET_COLUMN = "수주용량"
TARGET_UNIT_COLUMN = "수주용량단위"
ORDER_LAG_COLUMN = "수주용량_2개월전"
ORDER_WINDOW_COLUMNS = {
    1: ORDER_LAG_COLUMN,
    2: "수주용량_최근2개월누적",
    3: "수주용량_최근3개월누적",
    6: "수주용량_최근6개월누적",
}


def order_feature_columns_for(ship_type: str) -> dict[int, str]:
    # 모든 선종의 h+6 분석은 누적합 대신 최근 확정 단일월 1·2·3번째 값을 쓴다.
    return ORDER_POINT_LAG_COLUMNS
TARGET_UNITS = {
    "벌크선": "DWT",
    "케미컬 탱커": "DWT",
    "컨테이너선": "TEU",
    "가스 운반선": "CBM",
    "유조선": "DWT",
}
RAW_VESSEL_TYPES = {
    "벌크선": "Bulk Carrier", "케미컬 탱커": "Chemical Tanker",
    "컨테이너선": "Container", "가스 운반선": "Gas Carrier",
    "유조선": "Oil Tanker",
}
SHIP_PRICE_COLUMN = "신조선가_백만USD"
SHIP_PRICE_TYPES = {"벌크선", "컨테이너선", "유조선"}
FREIGHT_COLUMNS = {
    "벌크선": "벌크선운임(BDI점수)",
    "유조선": "유조선(VLCC)운임(WS점수)",
    "컨테이너선": "컨테이너운임_극동북유럽(USD/FEU)",
}
FLEET_COLUMN = "현존선복량_백만DWT"
FLEET_TYPES = {"벌크선", "유조선", "컨테이너선"}
BUNKER_SALES_COLUMN = "싱가포르_벙커유판매량_천톤"
CONTAINER_INDEX_COLUMNS = [
    "글로벌_컨테이너처리량지수",
]
GLOBAL_ECONOMY_COLUMNS = [
    "세계_실질상품수출_백만2010USD_계절조정",
    "세계_실질상품수입_백만2010USD_계절조정",
    "세계_산업생산_백만2010USD_계절조정",
]
SUPPLY_CHAIN_COLUMNS = ["글로벌_공급망압력지수(표준편차)"]
COMMON_COMMODITY_COLUMNS = [
    "원유 평균 가격(USD/bbl)",
]
SHIP_COMMODITY_COLUMNS = {
    "벌크선": [
        "철광석 가격(USD/dmtu)",
        "호주 석탄 가격(USD/mt)",
        "곡물 가격지수(2010=100)",
        "비료 가격지수(2010=100)",
    ],
    "케미컬 탱커": [
        "팜유 가격(USD/mt)",
        "대두유 가격(USD/mt)",
        "천연가스 가격지수(2010=100)",
    ],
    "컨테이너선": [
        "비에너지 원자재 가격지수(2010=100)",
        "비철금속 가격지수(2010=100)",
        "고무 TSR20 가격(USD/kg)",
        "면화 A지수(USD/kg)",
    ],
    "가스 운반선": [
        "천연가스 가격지수(2010=100)",
        "일본 LNG 가격(USD/MMBtu)",
    ],
    "유조선": [],
}
SHIP_CARGO_VOLUME_COLUMNS = {ship: [] for ship in SHIP_TYPES}
ALL_CARGO_VOLUME_COLUMNS = list(
    dict.fromkeys(
        column
        for columns in SHIP_CARGO_VOLUME_COLUMNS.values()
        for column in columns
    )
)
ALL_COMMODITY_COLUMNS = list(
    dict.fromkeys(
        [
            *COMMON_COMMODITY_COLUMNS,
            *(column for columns in SHIP_COMMODITY_COLUMNS.values() for column in columns),
        ]
    )
)
RISK_COLUMNS = [
    "GPR(세계지정학위험지수)",
    "GPRT(지정학위협지수)",
    "GPRA(지정학행동지수)",
]
TRADE_POLICY_COLUMNS = [
    "미국TPU(EPUTRADE 무역정책불확실성지수)",
    "미국TPU(Caldara 무역정책불확실성지수)",
    "중국TPU(무역정책불확실성지수)",
]


def feature_columns_for(ship_type: str) -> list[str]:
    return [
        *COMMON_COMMODITY_COLUMNS,
        *SHIP_COMMODITY_COLUMNS[ship_type],
        *SHIP_CARGO_VOLUME_COLUMNS[ship_type],
        BUNKER_SALES_COLUMN,
        *CONTAINER_INDEX_COLUMNS,
        *GLOBAL_ECONOMY_COLUMNS,
        *SUPPLY_CHAIN_COLUMNS,
        *([SHIP_PRICE_COLUMN] if ship_type in SHIP_PRICE_TYPES else []),
        *([FREIGHT_COLUMNS[ship_type]] if ship_type in FREIGHT_COLUMNS else []),
        *([FLEET_COLUMN] if ship_type in FLEET_TYPES else []),
        *RISK_COLUMNS,
        *TRADE_POLICY_COLUMNS,
        *PROCESSED_ORDER_LAG_COLUMNS.values(),
        *order_feature_columns_for(ship_type).values(),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="선종별 수주실적과 국제 원자재 가격 원값을 월 기준으로 결합합니다."
    )
    parser.add_argument(
        "--ship-type",
        choices=SHIP_TYPES,
        help="지정한 선종만 처리합니다. 생략하면 5개 선종을 모두 처리합니다.",
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="파일을 저장하지 않고 기존 마스터 테이블과 일치하는지만 검사합니다.",
    )
    parser.add_argument(
        "--end-month",
        help="마스터 종료월(YYYY-MM). 생략하면 수주·월별 외부지표의 최신 완료월까지 만듭니다.",
    )
    parser.add_argument(
        "--strict-complete",
        action="store_true",
        help="최근 결측월도 허용하지 않습니다. 기본은 최대 12개월의 불완전한 꼬리 구간 보존입니다.",
    )
    return parser.parse_args()


def require_columns(data: pd.DataFrame, required: list[str], source: Path) -> None:
    missing = [column for column in required if column not in data.columns]
    if missing:
        raise KeyError(f"{source.name} 필수 컬럼 누락: {missing}")


def normalize_month(series: pd.Series, source: Path) -> pd.Series:
    raw = series.astype("string").str.strip()
    if raw.isna().any() or raw.eq("").any():
        raise ValueError(f"{source.name} 기준월에 빈 값이 있습니다.")
    try:
        parsed = pd.to_datetime(raw, format="%Y-%m", errors="raise")
    except ValueError as error:
        raise ValueError(f"{source.name} 기준월은 YYYY-MM 형식이어야 합니다.") from error
    return parsed.dt.to_period("M").astype(str)


def validate_unique_month(data: pd.DataFrame, source: Path) -> None:
    duplicated = data.loc[data["기준월"].duplicated(keep=False), "기준월"].unique()
    if len(duplicated):
        preview = ", ".join(map(str, duplicated[:10]))
        raise ValueError(f"{source.name} 기준월 중복: {preview}")


def merge_asof_available_month(
    calendar_data: pd.DataFrame,
    releases: pd.DataFrame,
    available_month_column: str,
    value_columns: list[str],
    source_name: str,
) -> pd.DataFrame:
    """공표된 월부터 다음 공표 전까지 저빈도 자료를 사용할 수 있게 결합한다.

    분기·연간 값을 기간 시작월부터 소급해 채우면 아직 공개되지 않은 값이
    과거 예측행에 들어간다. 이 함수는 processed에서 정한 사용가능월을 기준으로
    backward as-of 결합하므로 그런 정보누수를 막는다.
    """
    require_columns(
        releases, [available_month_column, *value_columns], Path(source_name)
    )
    left = calendar_data.copy()
    right = releases[[available_month_column, *value_columns]].copy()
    left["_기준월키"] = pd.to_datetime(left["기준월"], format="%Y-%m", errors="raise")
    right["_사용가능월키"] = pd.to_datetime(
        right[available_month_column], format="%Y-%m", errors="raise"
    )
    if right["_사용가능월키"].duplicated().any():
        raise ValueError(f"{source_name} 사용가능월이 중복됩니다.")
    merged = pd.merge_asof(
        left.sort_values("_기준월키"),
        right.sort_values("_사용가능월키"),
        left_on="_기준월키",
        right_on="_사용가능월키",
        direction="backward",
        allow_exact_matches=True,
    )
    return merged.drop(
        columns=["_기준월키", "_사용가능월키", available_month_column]
    )


def load_commodities(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    commodities = input_data.copy() if input_data is not None else pd.read_csv(COMMODITY_PATH, encoding="utf-8-sig")
    require_columns(
        commodities,
        ["기준월", *ALL_COMMODITY_COLUMNS],
        COMMODITY_PATH,
    )
    commodities = commodities[["기준월", *ALL_COMMODITY_COLUMNS]].copy()
    commodities["기준월"] = normalize_month(
        commodities["기준월"],
        COMMODITY_PATH,
    )
    validate_unique_month(commodities, COMMODITY_PATH)

    for column in ALL_COMMODITY_COLUMNS:
        commodities[column] = pd.to_numeric(commodities[column], errors="raise")
    return commodities.sort_values("기준월").reset_index(drop=True)


def load_geopolitical_risk(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    risk = input_data.copy() if input_data is not None else pd.read_csv(RISK_PATH, encoding="utf-8-sig")
    require_columns(risk, ["기준월", *RISK_COLUMNS], RISK_PATH)
    risk = risk[["기준월", *RISK_COLUMNS]].copy()
    risk["기준월"] = normalize_month(risk["기준월"], RISK_PATH)
    validate_unique_month(risk, RISK_PATH)

    for column in RISK_COLUMNS:
        risk[column] = pd.to_numeric(risk[column], errors="raise")
    if risk[RISK_COLUMNS].isna().any().any():
        missing = risk.loc[risk[RISK_COLUMNS].isna().any(axis=1), "기준월"]
        preview = ", ".join(missing.head(10))
        raise ValueError(f"{RISK_PATH.name} 선택 컬럼 결측 월: {preview}")
    return risk.sort_values("기준월").reset_index(drop=True)


def load_trade_policy_uncertainty(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    trade_policy = input_data.copy() if input_data is not None else pd.read_csv(TRADE_POLICY_PATH, encoding="utf-8-sig")
    require_columns(
        trade_policy,
        ["기준월", *TRADE_POLICY_COLUMNS],
        TRADE_POLICY_PATH,
    )
    trade_policy = trade_policy[["기준월", *TRADE_POLICY_COLUMNS]].copy()
    trade_policy["기준월"] = normalize_month(
        trade_policy["기준월"],
        TRADE_POLICY_PATH,
    )
    validate_unique_month(trade_policy, TRADE_POLICY_PATH)
    for column in TRADE_POLICY_COLUMNS:
        trade_policy[column] = pd.to_numeric(trade_policy[column], errors="raise")
    if trade_policy[TRADE_POLICY_COLUMNS].isna().any().any():
        missing = trade_policy.loc[
            trade_policy[TRADE_POLICY_COLUMNS].isna().any(axis=1), "기준월"
        ]
        preview = ", ".join(missing.head(10))
        raise ValueError(f"{TRADE_POLICY_PATH.name} 선택 컬럼 결측 월: {preview}")
    return trade_policy.sort_values("기준월").reset_index(drop=True)


def load_bunker_sales(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    sales = input_data.copy() if input_data is not None else pd.read_csv(BUNKER_SALES_PATH, encoding="utf-8-sig")
    require_columns(sales, ["기준월", BUNKER_SALES_COLUMN], BUNKER_SALES_PATH)
    sales = sales[["기준월", BUNKER_SALES_COLUMN]].copy()
    sales["기준월"] = normalize_month(sales["기준월"], BUNKER_SALES_PATH)
    validate_unique_month(sales, BUNKER_SALES_PATH)
    sales[BUNKER_SALES_COLUMN] = pd.to_numeric(
        sales[BUNKER_SALES_COLUMN], errors="raise"
    )
    if sales[BUNKER_SALES_COLUMN].isna().any() or sales[BUNKER_SALES_COLUMN].le(0).any():
        raise ValueError(
            f"{BUNKER_SALES_PATH.name} 판매량에 결측 또는 0 이하 값이 있습니다."
        )
    return sales.sort_values("기준월").reset_index(drop=True)


def load_monthly_indicators(
    source: Path,
    columns: list[str],
    input_data: pd.DataFrame | None = None,
    positive: bool = True,
) -> pd.DataFrame:
    data = input_data.copy() if input_data is not None else pd.read_csv(source, encoding="utf-8-sig")
    require_columns(data, ["기준월", *columns], source)
    data = data[["기준월", *columns]].copy()
    data["기준월"] = normalize_month(data["기준월"], source)
    validate_unique_month(data, source)
    for column in columns:
        data[column] = pd.to_numeric(data[column], errors="raise")
    if data[columns].isna().any().any():
        raise ValueError(f"{source.name} 선택 지표에 결측이 있습니다.")
    if positive and data[columns].le(0).any().any():
        raise ValueError(f"{source.name} 선택 지표에 0 이하 값이 있습니다.")
    return data.sort_values("기준월").reset_index(drop=True)


def load_ship_prices(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    prices = input_data.copy() if input_data is not None else pd.read_csv(SHIP_PRICE_PATH, encoding="utf-8-sig")
    require_columns(prices, ["기준월", "선종", SHIP_PRICE_COLUMN], SHIP_PRICE_PATH)
    prices = prices[["기준월", "선종", SHIP_PRICE_COLUMN]].copy()
    prices["기준월"] = normalize_month(prices["기준월"], SHIP_PRICE_PATH)
    if prices.duplicated(["선종", "기준월"]).any():
        raise ValueError(f"{SHIP_PRICE_PATH.name} 선종·기준월 중복이 있습니다.")
    prices[SHIP_PRICE_COLUMN] = pd.to_numeric(prices[SHIP_PRICE_COLUMN], errors="raise")
    if prices[SHIP_PRICE_COLUMN].dropna().le(0).any():
        raise ValueError(f"{SHIP_PRICE_PATH.name} 신조선가에 0 이하 값이 있습니다.")
    return prices


def load_freight(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    freight = input_data.copy() if input_data is not None else pd.read_csv(FREIGHT_PATH, encoding="utf-8-sig")
    require_columns(freight, ["기준월", *FREIGHT_COLUMNS.values()], FREIGHT_PATH)
    freight = freight[["기준월", *FREIGHT_COLUMNS.values()]].copy()
    freight["기준월"] = normalize_month(freight["기준월"], FREIGHT_PATH)
    validate_unique_month(freight, FREIGHT_PATH)
    for column in FREIGHT_COLUMNS.values():
        freight[column] = pd.to_numeric(freight[column], errors="raise")
        if freight[column].dropna().le(0).any():
            raise ValueError(f"{FREIGHT_PATH.name} {column}에 0 이하 값이 있습니다.")
    return freight


def load_fleet(input_data: pd.DataFrame | None = None) -> pd.DataFrame:
    fleet = input_data.copy() if input_data is not None else pd.read_csv(FLEET_PATH, encoding="utf-8-sig")
    require_columns(
        fleet, ["선종", "월별사용시작연도", FLEET_COLUMN], FLEET_PATH
    )
    fleet = fleet[["선종", "월별사용시작연도", FLEET_COLUMN]].copy()
    if fleet.duplicated(["선종", "월별사용시작연도"]).any():
        raise ValueError(f"{FLEET_PATH.name} 선종·사용시작연도 중복이 있습니다.")
    fleet["월별사용시작연도"] = pd.to_numeric(
        fleet["월별사용시작연도"], errors="raise"
    ).astype(int)
    fleet["사용가능월"] = fleet["월별사용시작연도"].astype(str) + "-01"
    fleet[FLEET_COLUMN] = pd.to_numeric(fleet[FLEET_COLUMN], errors="raise")
    if fleet[FLEET_COLUMN].isna().any() or fleet[FLEET_COLUMN].le(0).any():
        raise ValueError(f"{FLEET_PATH.name} 선복량에 결측 또는 0 이하 값이 있습니다.")
    return fleet[["선종", "사용가능월", FLEET_COLUMN]]


def load_orders(ship_type: str, input_data: pd.DataFrame | None = None) -> tuple[pd.DataFrame, Path]:
    source = PROCESSED_DIR / ship_type / f"수주실적({ship_type}).csv"
    orders = input_data.copy() if input_data is not None else pd.read_csv(source, encoding="utf-8-sig")
    unit = TARGET_UNITS[ship_type]
    unit_column = f"수주용량({unit})"
    expected = ["기준월", "선종", unit_column, *PROCESSED_ORDER_LAG_COLUMNS.values()]
    if orders.columns.tolist() != expected:
        raise ValueError(f"{source.name} 컬럼은 {expected}이어야 합니다.")
    orders = orders[expected].copy()
    orders["기준월"] = normalize_month(orders["기준월"], source)
    validate_unique_month(orders, source)
    expected_ship = RAW_VESSEL_TYPES[ship_type]
    if not orders["선종"].eq(expected_ship).all():
        raise ValueError(f"{source.name} 선종은 모두 {expected_ship}이어야 합니다.")
    orders[unit_column] = pd.to_numeric(orders[unit_column], errors="raise")
    if orders[unit_column].lt(0).any():
        raise ValueError(f"{source.name} {unit_column}에 음수가 있습니다.")
    for column in PROCESSED_ORDER_LAG_COLUMNS.values():
        orders[column] = pd.to_numeric(orders[column], errors="raise")
        if orders[column].lt(0).any():
            raise ValueError(f"{source.name} {column}에 음수가 있습니다.")
    return (
        orders[["기준월", unit_column, *PROCESSED_ORDER_LAG_COLUMNS.values()]]
        .rename(columns={unit_column: TARGET_COLUMN})
        .sort_values("기준월").reset_index(drop=True),
        source,
    )


def build_master(
    ship_type: str,
    commodities: pd.DataFrame,
    cargo_volumes: pd.DataFrame,
    bunker_sales: pd.DataFrame,
    geopolitical_risk: pd.DataFrame,
    trade_policy_uncertainty: pd.DataFrame,
    ship_prices: pd.DataFrame,
    freight: pd.DataFrame,
    fleet: pd.DataFrame,
    orders_input: pd.DataFrame | None = None,
    container_index: pd.DataFrame | None = None,
    global_economy: pd.DataFrame | None = None,
    supply_chain: pd.DataFrame | None = None,
    end_month: str | None = None,
    allow_incomplete_after: str | None = None,
) -> tuple[pd.DataFrame, Path, list[str]]:
    container_index = load_monthly_indicators(
        CONTAINER_INDEX_PATH, CONTAINER_INDEX_COLUMNS, container_index
    )
    global_economy = load_monthly_indicators(
        GLOBAL_ECONOMY_PATH, GLOBAL_ECONOMY_COLUMNS, global_economy
    )
    supply_chain = load_monthly_indicators(
        SUPPLY_CHAIN_PATH, SUPPLY_CHAIN_COLUMNS, supply_chain, positive=False
    )
    orders, source = load_orders(ship_type, orders_input)
    requested_end = pd.Period(end_month, freq="M") if end_month is not None else None
    if end_month is not None:
        orders = orders.loc[orders["기준월"].le(end_month)].copy()
        if orders.empty:
            raise ValueError(f"{ship_type}: {end_month}까지 수주실적이 없습니다")
    feature_columns = feature_columns_for(ship_type)
    commodity_columns = [
        *COMMON_COMMODITY_COLUMNS,
        *SHIP_COMMODITY_COLUMNS[ship_type],
    ]
    output_columns = [
        "기준월", TARGET_COLUMN, TARGET_UNIT_COLUMN,
        AVAILABLE_LAG_COLUMN, AVAILABILITY_STATUS_COLUMN, *feature_columns,
    ]
    start_month = pd.Period(orders["기준월"].min(), freq="M")
    last_order_month = pd.Period(orders["기준월"].max(), freq="M")
    if requested_end is None:
        monthly_inputs = (commodities, bunker_sales,
                          geopolitical_risk, trade_policy_uncertainty,
                          ship_prices, freight, container_index,
                          global_economy, supply_chain)
        last_completed_month = pd.Timestamp.today().to_period("M") - 1
        observed_months = [last_order_month]
        for source_frame in monthly_inputs:
            if not source_frame.empty:
                observed_months.append(pd.Period(source_frame["기준월"].max(), freq="M"))
        end_month = min(max(observed_months), last_completed_month)
    else:
        end_month = requested_end
    calendar = pd.DataFrame(
        {"기준월": pd.period_range(start_month, end_month, freq="M").astype(str)}
    )

    master = calendar.merge(orders, on="기준월", how="left", validate="one_to_one")
    # 수주 관측이 없는 달도 이 선종의 단위 자체는 변하지 않는다.
    master[TARGET_UNIT_COLUMN] = TARGET_UNITS[ship_type]
    master = master.merge(
        commodities[["기준월", *commodity_columns]],
        on="기준월",
        how="left",
        validate="one_to_one",
    )
    master = master.merge(
        bunker_sales,
        on="기준월",
        how="left",
        validate="one_to_one",
    )
    for indicators in (container_index, global_economy, supply_chain):
        master = master.merge(indicators, on="기준월", how="left", validate="one_to_one")
    master = master.merge(
        geopolitical_risk,
        on="기준월",
        how="left",
        validate="one_to_one",
    )
    master = master.merge(
        trade_policy_uncertainty,
        on="기준월",
        how="left",
        validate="one_to_one",
    )
    if ship_type in SHIP_PRICE_TYPES:
        matching_prices = ship_prices.loc[
            ship_prices["선종"].eq(ship_type), ["기준월", SHIP_PRICE_COLUMN]
        ]
        master = master.merge(
            matching_prices,
            on="기준월",
            how="left",
            validate="one_to_one",
        )
    if ship_type in FREIGHT_COLUMNS:
        freight_column = FREIGHT_COLUMNS[ship_type]
        master = master.merge(
            freight[["기준월", freight_column]],
            on="기준월", how="left", validate="one_to_one",
        )
    if ship_type in FLEET_TYPES:
        matching_fleet = fleet.loc[
            fleet["선종"].eq(ship_type), ["사용가능월", FLEET_COLUMN]
        ]
        master = merge_asof_available_month(
            master,
            matching_fleet,
            "사용가능월",
            [FLEET_COLUMN],
            FLEET_PATH.name,
        )
    raw_orders = pd.read_csv(RAW_ORDERS_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)
    published = publication_dates(raw_orders, RAW_VESSEL_TYPES[ship_type])
    available = available_order_point_lags(master["기준월"], master[TARGET_COLUMN], published)
    for column in available.columns:
        master[column] = available[column]
    master = master[output_columns]

    if len(master) != len(calendar):
        raise AssertionError(f"{ship_type} 월 달력과 출력 행 수가 다릅니다.")
    if master["기준월"].duplicated().any():
        raise AssertionError(f"{ship_type} 출력에 중복 월이 생겼습니다.")
    external_feature_columns = [
        column for column in feature_columns
        if column not in {*order_feature_columns_for(ship_type).values(),
                          *PROCESSED_ORDER_LAG_COLUMNS.values(), SHIP_PRICE_COLUMN}
    ]
    missing_external = master[external_feature_columns].isna().any(axis=1)
    if allow_incomplete_after == "auto":
        # Do not discard recent orders merely because one upstream monthly
        # source has not published yet.  Earlier gaps still fail validation.
        completion_columns = [column for column in feature_columns
                              if column not in {*order_feature_columns_for(ship_type).values(),
                                                *PROCESSED_ORDER_LAG_COLUMNS.values()}]
        complete = master[completion_columns].notna().all(axis=1)
        last_complete = master.loc[complete, "기준월"].max()
        if pd.isna(last_complete):
            raise ValueError(f"{ship_type}: 외부지표가 모두 갖춰진 기준월이 없습니다")
        trailing = pd.Period(end_month, freq="M") - pd.Period(last_complete, freq="M")
        if trailing.n > 12:
            raise ValueError(f"{ship_type}: 최근 불완전 구간이 {trailing.n}개월로 12개월 한도를 초과합니다")
        allow_incomplete_after = str(pd.Period(last_complete, freq="M") + 1)
    if allow_incomplete_after is not None:
        pd.Period(allow_incomplete_after, freq="M")
        missing_external &= master["기준월"].lt(allow_incomplete_after)
    if missing_external.any():
        missing_months = master.loc[
            missing_external, "기준월"
        ]
        preview = ", ".join(missing_months.head(10))
        raise ValueError(f"{ship_type} 설명변수 결측 월: {preview}")
    if ship_type in SHIP_PRICE_TYPES:
        validation_months = master["기준월"].ge("2022-01")
        if allow_incomplete_after is not None:
            validation_months &= master["기준월"].lt(allow_incomplete_after)
        missing_price = master.loc[
            validation_months & master[SHIP_PRICE_COLUMN].isna(), "기준월"
        ]
        if not missing_price.empty:
            raise ValueError(
                f"{ship_type} 2022년 이후 신조선가 결측 월: "
                + ", ".join(missing_price.head(10))
            )

    expected_months = pd.period_range(start_month, end_month, freq="M").astype(str).tolist()
    if master["기준월"].tolist() != expected_months:
        raise AssertionError(f"{ship_type} 출력 월이 연속적이지 않습니다.")

    return master, source, feature_columns


def save_master(master: pd.DataFrame, output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(output.suffix + ".tmp")
    master.to_csv(temporary, index=False, encoding="utf-8-sig", lineterminator="\n")
    temporary.replace(output)


def check_existing(
    master: pd.DataFrame,
    output: Path,
    output_columns: list[str],
) -> None:
    if not output.exists():
        raise FileNotFoundError(f"비교할 기존 마스터 테이블이 없습니다: {output}")
    existing = pd.read_csv(output, encoding="utf-8-sig")
    if list(existing.columns) != output_columns:
        raise ValueError(f"{output.name} 컬럼 구성이 생성 규칙과 다릅니다.")
    try:
        pd.testing.assert_frame_equal(
            master.reset_index(drop=True),
            existing.reset_index(drop=True),
            check_dtype=False,
            check_exact=False,
            rtol=1e-12,
            atol=1e-12,
        )
    except AssertionError as error:
        raise ValueError(
            f"{output.name} 내용이 현재 입력자료와 생성 규칙에 맞지 않습니다."
        ) from error


def main() -> None:
    args = parse_args()
    commodities = load_commodities()
    cargo_volumes = pd.DataFrame()  # 보관된 물동량은 마스터 입력에서 제외
    bunker_sales = load_bunker_sales()
    geopolitical_risk = load_geopolitical_risk()
    trade_policy_uncertainty = load_trade_policy_uncertainty()
    ship_prices = load_ship_prices()
    freight = load_freight()
    fleet = load_fleet()
    container_index = load_monthly_indicators(CONTAINER_INDEX_PATH, CONTAINER_INDEX_COLUMNS)
    global_economy = load_monthly_indicators(GLOBAL_ECONOMY_PATH, GLOBAL_ECONOMY_COLUMNS)
    supply_chain = load_monthly_indicators(SUPPLY_CHAIN_PATH, SUPPLY_CHAIN_COLUMNS, positive=False)
    selected = [args.ship_type] if args.ship_type else SHIP_TYPES
    summaries: list[dict[str, object]] = []

    for ship_type in selected:
        master, source, feature_columns = build_master(
            ship_type,
            commodities,
            cargo_volumes,
            bunker_sales,
            geopolitical_risk,
            trade_policy_uncertainty,
            ship_prices,
            freight,
            fleet,
            container_index=container_index,
            global_economy=global_economy,
            supply_chain=supply_chain,
            end_month=args.end_month,
            allow_incomplete_after=None if args.strict_complete else "auto",
        )
        output_columns = [
            "기준월", TARGET_COLUMN, TARGET_UNIT_COLUMN,
            AVAILABLE_LAG_COLUMN, AVAILABILITY_STATUS_COLUMN, *feature_columns,
        ]
        output = MASTER_DIR / f"마스터테이블({ship_type}).csv"

        if args.check_only:
            check_existing(master, output, output_columns)
            status = "일치"
        else:
            save_master(master, output)
            check_existing(master, output, output_columns)
            status = "생성 완료"

        summaries.append(
            {
                "선종": ship_type,
                "상태": status,
                "입력행": len(pd.read_csv(source, encoding="utf-8-sig")),
                "출력월": len(master),
                "시작월": master["기준월"].min(),
                "종료월": master["기준월"].max(),
                "수주용량단위": TARGET_UNITS[ship_type],
                "수주용량결측월": int(master[TARGET_COLUMN].isna().sum()),
                "최근확정1개월차결측월": int(master[order_feature_columns_for(ship_type)[1]].isna().sum()),
                "t-3대체월": int(master[AVAILABLE_LAG_COLUMN].eq(3).sum()),
                "t-3게시일미상월": int(master[AVAILABILITY_STATUS_COLUMN].eq("t-3_게시일미상").sum()),
                "수주2번째시차결측월": int(master[order_feature_columns_for(ship_type)[2]].isna().sum()),
                "수주3번째시차결측월": int(master[order_feature_columns_for(ship_type)[3]].isna().sum()),
                **({"수주6번째시차결측월": int(
                    master[order_feature_columns_for(ship_type)[6]].isna().sum())}
                   if 6 in order_feature_columns_for(ship_type) else {}),
                "원자재피처수": len(COMMON_COMMODITY_COLUMNS)
                + len(SHIP_COMMODITY_COLUMNS[ship_type]),
                "물동량피처수": len(SHIP_CARGO_VOLUME_COLUMNS[ship_type]),
                "벙커유판매량관측월": int(master[BUNKER_SALES_COLUMN].notna().sum()),
                "신조선가관측월": int(master[SHIP_PRICE_COLUMN].notna().sum())
                if ship_type in SHIP_PRICE_TYPES else 0,
                "운임관측월": int(master[FREIGHT_COLUMNS[ship_type]].notna().sum())
                if ship_type in FREIGHT_COLUMNS else 0,
                "선복량관측월": int(master[FLEET_COLUMN].notna().sum())
                if ship_type in FLEET_TYPES else 0,
                "외부설명변수결측값": int(
                    master[[column for column in feature_columns
                            if column not in {*order_feature_columns_for(ship_type).values(), SHIP_PRICE_COLUMN}]]
                    .isna()
                    .sum()
                    .sum()
                ),
            }
        )

    print(pd.DataFrame(summaries).to_string(index=False))


if __name__ == "__main__":
    main()

