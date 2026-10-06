"""Guard chronological fold scoring and per-fold feature-change reporting."""

import unittest

import numpy as np
import pandas as pd

from ship_orders_forecasting.fold_validation import (
    chronological_folds, evaluate_folds, fold_improvement,
)


class FoldValidationTest(unittest.TestCase):
    def test_annual_folds_and_equal_weight_mean(self):
        index = pd.date_range("2015-01-01", "2024-12-01", freq="MS")
        data = pd.DataFrame({
            "수주용량": np.arange(len(index), dtype=float),
            "피처": np.arange(len(index), dtype=float),
        }, index=index)
        months = pd.DatetimeIndex(["2022-01-01", "2022-02-01", "2023-01-01", "2024-01-01"])
        folds = chronological_folds(months, "Y")
        self.assertEqual(list(folds), ["2022", "2023", "2024"])
        summary, detail = evaluate_folds(data, folds, ["피처"], "1차 선형회귀")
        self.assertEqual(detail["검증관측월"].tolist(), [2, 1, 1])
        self.assertEqual(summary["폴드수"], 3)
        self.assertAlmostEqual(summary["sMAPE"], detail["sMAPE"].mean())
        self.assertAlmostEqual(summary["sMAPE표준편차"], detail["sMAPE"].std(ddof=1))

    def test_fold_improvement_keeps_each_period(self):
        before = pd.DataFrame({"fold": ["2022", "2023", "2024"],
                               "검증관측월": [12, 7, 6], "sMAPE": [.8, .7, .6]})
        after = pd.DataFrame({"fold": ["2022", "2023", "2024"],
                              "검증관측월": [12, 7, 6], "sMAPE": [.4, .7, .8]})
        result = fold_improvement(before, after)
        np.testing.assert_allclose(result["개선_퍼센트포인트"], [40., 0., -20.])

    def test_missing_month_is_not_silently_dropped(self):
        index = pd.date_range("2015-01-01", "2024-12-01", freq="MS")
        data = pd.DataFrame({"수주용량": 1., "피처": 1.}, index=index)
        data.loc[pd.Timestamp("2023-01-01"), "피처"] = np.nan
        folds = chronological_folds(pd.DatetimeIndex(["2022-01-01", "2023-01-01"]), "Y")
        with self.assertRaisesRegex(ValueError, "missing prediction months"):
            evaluate_folds(data, folds, ["피처"], "1차 선형회귀")

    def test_future_test_rows_do_not_change_development_fold_scores(self):
        index = pd.date_range("2015-01-01", "2025-12-01", freq="MS")
        data = pd.DataFrame({
            "수주용량": np.arange(len(index), dtype=float),
            "피처": np.arange(len(index), dtype=float),
        }, index=index)
        folds = chronological_folds(pd.DatetimeIndex(["2022-01-01", "2023-01-01"]), "Y")
        original, _ = evaluate_folds(data, folds, ["피처"], "1차 선형회귀")
        changed = data.copy()
        changed.loc["2025", ["수주용량", "피처"]] = 1_000_000.
        after, _ = evaluate_folds(changed, folds, ["피처"], "1차 선형회귀")
        self.assertEqual(original, after)


if __name__ == "__main__":
    unittest.main()
