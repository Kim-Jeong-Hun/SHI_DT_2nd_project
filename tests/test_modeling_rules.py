"""Regression checks for monthly forecasting assumptions."""

import unittest

import numpy as np
import pandas as pd

from ship_orders_forecasting.modeling import (
    ORDER_WINDOWS, PUBLISHED_LABEL_COLUMN, ROLLING_BASELINE,
    ROLLING_BASELINE_MODEL, lagged_data, metrics,
    monthly_splits, walk_forward,
)
from ship_orders_forecasting.legacy import legacy_module
from ship_orders_forecasting.order_availability import (
    AVAILABLE_LAG_COLUMN, available_order_windows,
)


class PipelineRulesTest(unittest.TestCase):
    def test_order_windows_follow_available_report_and_preserve_missing(self):
        rules = legacy_module("마스터테이블_생성")
        self.assertEqual(ORDER_WINDOWS, rules.ORDER_WINDOW_COLUMNS)
        values = pd.Series([10., 20., np.nan, 40., 50., 60., 70., 80.])
        months = pd.Series(pd.period_range("2026-01", periods=8, freq="M").astype(str))
        published = pd.Series({"2026-05": pd.Timestamp("2026-06-29"),
                               "2026-06": pd.Timestamp("2026-07-30")})
        windows = available_order_windows(months, values, published)
        self.assertEqual(windows[AVAILABLE_LAG_COLUMN].iloc[7], 2)
        self.assertEqual(windows[ORDER_WINDOWS[1]].iloc[7], 60.)
        self.assertEqual(windows[ORDER_WINDOWS[3]].iloc[7], 150.)
        self.assertTrue(np.isnan(windows[ORDER_WINDOWS[6]].iloc[7]))
        self.assertTrue(np.isnan(windows[ORDER_WINDOWS[2]].iloc[5]))

    def test_smape_treats_zero_zero_as_zero(self):
        result = metrics([0, 10], [0, 0])
        self.assertAlmostEqual(result["sMAPE"], 1.0)

    def test_monthly_training_respects_selected_publication_lag(self):
        index = pd.date_range("2018-01-01", periods=60, freq="MS")
        data = pd.DataFrame({"수주용량": np.arange(60), "피처": np.arange(60),
                             AVAILABLE_LAG_COLUMN: 2}, index=index)
        split = list(monthly_splits(data, [pd.Timestamp("2022-12-01")], ["피처"], 48))
        self.assertEqual(len(split), 1)
        self.assertEqual(split[0][1].index.max(), pd.Timestamp("2022-10-01"))
        self.assertEqual(len(split[0][1]), 58)
        data.loc["2022-12-01", AVAILABLE_LAG_COLUMN] = 3
        split = list(monthly_splits(data, [pd.Timestamp("2022-12-01")], ["피처"], 48))
        self.assertEqual(split[0][1].index.max(), pd.Timestamp("2022-09-01"))

    def test_rolling_baseline_uses_only_orders_through_t_minus_two(self):
        index = pd.date_range("2018-01-01", periods=60, freq="MS")
        values = pd.Series(np.arange(60, dtype=float), index=index)
        rolling = values.shift(2).rolling(3, min_periods=1).mean()
        self.assertEqual(rolling.loc["2022-12-01"], np.mean([55, 56, 57]))
        data = pd.DataFrame({"수주용량": values, ROLLING_BASELINE: rolling})
        result = walk_forward(
            data, [pd.Timestamp("2022-12-01")], [ROLLING_BASELINE],
            ROLLING_BASELINE_MODEL, {"minimum_train_months": 48, "random_seed": 42},
        )
        self.assertEqual(result["예측"].iloc[0], rolling.loc["2022-12-01"])

    def test_known_late_training_label_is_excluded_even_when_old(self):
        index = pd.date_range("2025-09-01", "2026-03-01", freq="MS")
        data = pd.DataFrame({
            "수주용량": np.arange(len(index), dtype=float),
            "피처": np.arange(len(index), dtype=float),
            AVAILABLE_LAG_COLUMN: 2,
            PUBLISHED_LABEL_COLUMN: pd.NaT,
        }, index=index)
        data.loc["2025-11-01", PUBLISHED_LABEL_COLUMN] = pd.Timestamp("2026-06-23")
        data.loc["2026-01-01", PUBLISHED_LABEL_COLUMN] = pd.Timestamp("2026-02-20")
        split = list(monthly_splits(data, [pd.Timestamp("2026-03-01")], ["피처"], 1))
        train = split[0][1]
        self.assertNotIn(pd.Timestamp("2025-11-01"), train.index)
        self.assertIn(pd.Timestamp("2025-12-01"), train.index)
        self.assertIn(pd.Timestamp("2026-01-01"), train.index)
        data.loc["2026-01-01", PUBLISHED_LABEL_COLUMN] = pd.NaT
        train = list(monthly_splits(data, [pd.Timestamp("2026-03-01")], ["피처"], 1))[0][1]
        self.assertNotIn(pd.Timestamp("2026-01-01"), train.index)


if __name__ == "__main__":
    unittest.main()
