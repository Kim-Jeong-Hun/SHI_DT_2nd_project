"""Publication-date boundary checks for month-end order forecasting."""

import unittest

import numpy as np
import pandas as pd

from ship_orders_forecasting.order_availability import (
    AVAILABLE_LAG_COLUMN, AVAILABILITY_STATUS_COLUMN, ORDER_POINT_LAG_COLUMNS,
    ORDER_WINDOW_COLUMNS, available_order_point_lags, available_order_windows,
    last_weekday_of_previous_month,
    publication_date_from_row,
)


class OrderAvailabilityTest(unittest.TestCase):
    def setUp(self):
        self.months = pd.Series(pd.period_range("2026-01", periods=11, freq="M").astype(str))
        self.values = pd.Series(np.arange(1, 12, dtype=float) * 10)

    def test_month_end_cutoff_uses_last_weekday(self):
        self.assertEqual(last_weekday_of_previous_month(pd.Timestamp("2026-11-01")),
                         pd.Timestamp("2026-10-30"))

    def test_timely_report_uses_t_minus_two(self):
        published = pd.Series({"2026-09": pd.Timestamp("2026-10-29")})
        row = available_order_windows(self.months, self.values, published).iloc[-1]
        self.assertEqual(row[AVAILABLE_LAG_COLUMN], 2)
        self.assertEqual(row[ORDER_WINDOW_COLUMNS[1]], 90)
        self.assertEqual(row[ORDER_WINDOW_COLUMNS[3]], 240)
        self.assertEqual(row[AVAILABILITY_STATUS_COLUMN], "게시일확인")

    def test_late_report_falls_back_to_t_minus_three(self):
        published = pd.Series({"2026-09": pd.Timestamp("2026-10-31"),
                               "2026-08": pd.Timestamp("2026-09-28")})
        row = available_order_windows(self.months, self.values, published).iloc[-1]
        self.assertEqual(row[AVAILABLE_LAG_COLUMN], 3)
        self.assertEqual(row[ORDER_WINDOW_COLUMNS[1]], 80)
        self.assertEqual(row[ORDER_WINDOW_COLUMNS[3]], 210)

    def test_unknown_t_minus_two_is_not_used(self):
        row = available_order_windows(self.months, self.values, pd.Series(dtype="datetime64[ns]")).iloc[-1]
        self.assertEqual(row[AVAILABLE_LAG_COLUMN], 3)
        self.assertEqual(row[AVAILABILITY_STATUS_COLUMN], "t-3_게시일미상")

    def test_no_available_report_and_incomplete_window_stay_missing(self):
        published = pd.Series({"2026-09": pd.Timestamp("2026-11-01"),
                               "2026-08": pd.Timestamp("2026-11-01")})
        row = available_order_windows(self.months, self.values, published).iloc[-1]
        self.assertTrue(pd.isna(row[AVAILABLE_LAG_COLUMN]))
        self.assertTrue(pd.isna(row[ORDER_WINDOW_COLUMNS[1]]))
        values = self.values.copy()
        values.iloc[5] = np.nan
        published["2026-08"] = pd.Timestamp("2026-09-28")
        row = available_order_windows(self.months, values, published).iloc[-1]
        self.assertEqual(row[AVAILABLE_LAG_COLUMN], 3)
        self.assertTrue(pd.isna(row[ORDER_WINDOW_COLUMNS[3]]))

    def test_publication_date_is_not_snapshot_date(self):
        row = pd.Series({"definition_notes": "published_date=2026-09-28",
                         "source_url": "https://example.org/article", "as_of_date": "2026-08-01"})
        self.assertEqual(publication_date_from_row(row), pd.Timestamp("2026-09-28"))
        row["definition_notes"] = ""
        self.assertTrue(pd.isna(publication_date_from_row(row)))

    def test_point_lags_do_not_propagate_a_single_missing_month(self):
        published = pd.Series({"2026-09": pd.Timestamp("2026-10-29")})
        values = self.values.copy()
        values.iloc[7] = np.nan  # 2026-08, the second available month for November.
        row = available_order_point_lags(self.months, values, published).iloc[-1]
        self.assertEqual(row[AVAILABLE_LAG_COLUMN], 2)
        self.assertEqual(row[ORDER_POINT_LAG_COLUMNS[1]], 90)
        self.assertTrue(pd.isna(row[ORDER_POINT_LAG_COLUMNS[2]]))
        self.assertEqual(row[ORDER_POINT_LAG_COLUMNS[3]], 70)
        self.assertEqual(tuple(ORDER_POINT_LAG_COLUMNS), (1, 2, 3))
        self.assertEqual(set(row.index).intersection(ORDER_POINT_LAG_COLUMNS.values()),
                         set(ORDER_POINT_LAG_COLUMNS.values()))

    def test_point_lag_blocks_report_published_after_origin(self):
        published = pd.Series({"2026-09": pd.Timestamp("2026-10-29"),
                               "2026-07": pd.Timestamp("2026-11-01")})
        row = available_order_point_lags(self.months, self.values, published).iloc[-1]
        self.assertEqual(row[ORDER_POINT_LAG_COLUMNS[1]], 90)
        self.assertTrue(pd.isna(row[ORDER_POINT_LAG_COLUMNS[3]]))


if __name__ == "__main__":
    unittest.main()
