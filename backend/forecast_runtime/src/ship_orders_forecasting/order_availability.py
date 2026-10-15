"""Calendar lags for monthly order history and source-date audit helpers.

Forecast inputs use observed months at fixed calendar lags. Article dates are
retained as provenance and do not determine whether a value enters training.
"""

from __future__ import annotations

import re

import numpy as np
import pandas as pd


AVAILABLE_LAG_COLUMN = "수주정보시차(개월)"
AVAILABILITY_STATUS_COLUMN = "수주정보가용근거"
ORDER_WINDOW_COLUMNS = {
    1: "수주용량_2개월전",
    2: "수주용량_최근2개월누적",
    3: "수주용량_최근3개월누적",
    6: "수주용량_최근6개월누적",
}
ORDER_POINT_LAG_COLUMNS = {
    lag: f"수주용량_최근확정{lag}개월차" for lag in (1, 2, 3)
}
# 기준월을 기준으로 한 순수한 달력 시차. 게시일은 입력 제한에 사용하지 않는다.
PROCESSED_ORDER_LAG_COLUMNS = {
    lag: f"수주용량_기준월{lag}개월전" for lag in (1, 2, 3)
}


def publication_date_from_row(row: pd.Series) -> pd.Timestamp | pd.NaT:
    """Read an explicit date or a date encoded in the original article URL."""
    note = str(row.get("definition_notes", ""))
    match = re.search(r"published_date=(\d{4}-\d{2}-\d{2})", note)
    if match:
        return pd.Timestamp(match.group(1))

    url = str(row.get("source_url", ""))
    match = re.search(r"/html/(20\d{2})/NewShipMarket_(\d{2})(\d{2})/", url)
    if match:
        return pd.Timestamp(*map(int, match.groups()))
    match = re.search(r"/(20\d{2})[-/](\d{2})[-/](\d{2})(?:/|$)", url)
    if match:
        return pd.Timestamp(*map(int, match.groups()))
    match = re.search(r"/html/(20\d{2})(\d{2})/(\d{2})/", url)
    if match:
        return pd.Timestamp(*map(int, match.groups()))
    match = re.search(r"H3_AP(20\d{2})(\d{2})(\d{2})", url)
    if match:
        return pd.Timestamp(*map(int, match.groups()))
    return pd.NaT


def publication_dates(raw: pd.DataFrame, vessel_type: str) -> pd.Series:
    """Return one publication date (or NaT) per observed month and vessel."""
    required = {"frequency", "period", "vessel_type", "source_url", "definition_notes"}
    missing = required.difference(raw.columns)
    if missing:
        raise KeyError(f"수주 원자료에 게시일 검증 컬럼이 없습니다: {sorted(missing)}")
    selected = raw.loc[
        raw["frequency"].eq("monthly") & raw["vessel_type"].eq(vessel_type)
    ].copy()
    if selected["period"].duplicated().any():
        raise ValueError(f"{vessel_type}: 중복된 수주 기준월이 있습니다")
    selected["publication_date"] = selected.apply(publication_date_from_row, axis=1)
    return selected.set_index("period")["publication_date"]


def last_weekday_of_previous_month(target_month: pd.Timestamp) -> pd.Timestamp:
    """Forecast cutoff: previous month's final Monday-Friday.

    National holidays need a separate calendar before production scheduling.
    """
    day = pd.Timestamp(target_month).replace(day=1) - pd.Timedelta(days=1)
    return pd.offsets.BMonthEnd().rollback(day)


def available_order_windows(
    months: pd.Series,
    target: pd.Series,
    published: pd.Series | None = None,
) -> pd.DataFrame:
    """Choose the latest observed t-2 or t-3 month without filling gaps."""
    periods = pd.PeriodIndex(months.astype(str), freq="M")
    if periods.has_duplicates or not periods.equals(pd.period_range(periods.min(), periods.max(), freq="M")):
        raise ValueError("수주 가용성 계산에는 중복 없는 연속 월 달력이 필요합니다")
    values = pd.to_numeric(target, errors="coerce").reset_index(drop=True)
    rows: list[dict[str, object]] = []
    for position, period in enumerate(periods):
        selected_lag: int | None = None
        status = "확정수주없음"
        for lag in (2, 3):
            source_pos = position - lag
            if source_pos < 0 or pd.isna(values.iloc[source_pos]):
                continue
            selected_lag = lag
            status = "달력시차가정"
            break
        row: dict[str, object] = {
            AVAILABLE_LAG_COLUMN: selected_lag,
            AVAILABILITY_STATUS_COLUMN: status,
        }
        for window, column in ORDER_WINDOW_COLUMNS.items():
            if selected_lag is None or position - selected_lag - window + 1 < 0:
                row[column] = np.nan
                continue
            window_values = values.iloc[
                position - selected_lag - window + 1: position - selected_lag + 1
            ]
            row[column] = float(window_values.sum()) if window_values.notna().all() else np.nan
        rows.append(row)
    return pd.DataFrame(rows, index=months.index)


def available_order_point_lags(
    months: pd.Series,
    target: pd.Series,
    published: pd.Series | None = None,
) -> pd.DataFrame:
    """Return observed months counted back from the latest t-2/t-3 report."""
    periods = pd.PeriodIndex(months.astype(str), freq="M")
    if periods.has_duplicates or not periods.equals(
        pd.period_range(periods.min(), periods.max(), freq="M")
    ):
        raise ValueError("수주 가용성 계산에는 중복 없는 연속 월 달력이 필요합니다")
    values = pd.to_numeric(target, errors="coerce").reset_index(drop=True)
    rows: list[dict[str, object]] = []
    for position, period in enumerate(periods):
        selected_lag: int | None = None
        status = "확정수주없음"
        for lag in (2, 3):
            source_pos = position - lag
            if source_pos < 0 or pd.isna(values.iloc[source_pos]):
                continue
            selected_lag = lag
            status = "달력시차가정"
            break
        row: dict[str, object] = {
            AVAILABLE_LAG_COLUMN: selected_lag,
            AVAILABILITY_STATUS_COLUMN: status,
        }
        for ordinal, column in ORDER_POINT_LAG_COLUMNS.items():
            source_pos = position - selected_lag - ordinal + 1 if selected_lag else -1
            if source_pos < 0 or pd.isna(values.iloc[source_pos]):
                row[column] = np.nan
                continue
            row[column] = float(values.iloc[source_pos])
        rows.append(row)
    return pd.DataFrame(rows, index=months.index)
