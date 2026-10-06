"""Regression checks for information boundaries and honest annual comparisons."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ship_orders_forecasting.modeling import (
    InsufficientHistoryError, ROLLING_BASELINE, ROLLING_BASELINE_MODEL,
    TARGET, TARGET_LAG, evaluate_holdout, metrics, select_lags, select_model,
)
from ship_orders_forecasting.validation import annual_validation, summarize_validation_audit
from ship_orders_forecasting.order_availability import AVAILABLE_LAG_COLUMN


class AnnualValidationTest(unittest.TestCase):
    def setUp(self):
        index = pd.date_range("2016-01-01", "2025-12-01", freq="MS")
        y = pd.Series(100 + np.arange(len(index)) + 10 * np.sin(np.arange(len(index))), index=index)
        self.data = pd.DataFrame({"기준월": index.strftime("%Y-%m"), TARGET: y.to_numpy(),
                                  AVAILABLE_LAG_COLUMN: 2,
                                  TARGET_LAG: y.shift(2).to_numpy(),
                                  ROLLING_BASELINE: y.shift(2).rolling(3, min_periods=1).mean().to_numpy(),
                                  "x_1개월전": np.arange(len(index)),
                                  "x_2개월전": np.arange(len(index)) - 1})
        for months in (2, 3, 6):
            self.data[f"수주용량_최근{months}개월누적"] = (
                y.shift(2).rolling(months, min_periods=months).sum().to_numpy()
            )
        self.policies = pd.DataFrame([{"원본피처": "x", "허용시차": "1,2"}])
        self.params = {"validation_start": "2022-01", "holdout_start": "2025-01",
                       "minimum_train_months": 48, "minimum_validation_months": 24,
                       "maximum_removed_features": 1, "minimum_relative_smape_improvement": 0.01,
                       "random_seed": 42}

    def test_unconfirmed_december_and_future_labels_cannot_change_selection(self):
        # January predictions are issued before December order labels are available.
        changed = self.data.copy()
        changed.loc[changed["기준월"] >= "2024-12", TARGET] = 1e12
        first_lags = select_lags(self.data, self.policies, self.params)
        second_lags = select_lags(changed, self.policies, self.params)
        pd.testing.assert_frame_equal(first_lags, second_lags)
        groups = {"commodities": ["x"], "freight": [], "fleet": [], "cargo": []}
        with patch("ship_orders_forecasting.modeling.feature_groups", return_value=groups), \
             patch("ship_orders_forecasting.modeling.MODELS", ("1차 선형회귀",)):
            first_result = select_model(self.data, first_lags, self.params, "test")
            first = first_result[-1]
            second = select_model(changed, second_lags, self.params, "test")[-1]
            history_only = self.data.loc[self.data["기준월"] <= "2024-11"]
            third = select_model(history_only, first_lags,
                                 {**self.params, "holdout_order_lag": 2}, "test")[-1]
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(first["검증종료"], "2024-11")
        window_rows = first_result[0].loc[
            first_result[0]["변수집합"].eq("수주 누적 창 비교")
        ]
        self.assertEqual(window_rows["수주창개월"].tolist(), [1, 2, 3, 6])
        self.assertEqual(window_rows["검증관측월"].nunique(), 1)

    def test_complete_year_holdout_reports_annual_total_error(self):
        selected = {"선종": "test", "모형": ROLLING_BASELINE_MODEL,
                    "변수집합": "시계열 기준선", "피처목록": [ROLLING_BASELINE]}
        predictions, report = evaluate_holdout(self.data, selected, self.params)
        annual = predictions.loc[predictions["구간"].eq("2025+ 테스트")]
        expected = metrics([annual["실제"].sum()], [annual["예측"].sum()])
        self.assertEqual(report.loc[0, "연간누적평가연수"], 1)
        self.assertAlmostEqual(report.loc[0, "연간누적sMAPE"], expected["sMAPE"])
        self.assertTrue(np.isnan(expected["R2"]))

    def test_annual_reselection_excludes_future_but_monthly_training_expands(self):
        seen = []

        def selection(history, lags, params, ship_type):
            seen.append((history["기준월"].max(), params["validation_start"]))
            selected = {"모형": ROLLING_BASELINE_MODEL, "피처목록": [ROLLING_BASELINE],
                        "검증관측월": 30, "검증sMAPE": 0.1}
            return None, None, pd.DataFrame(), None, selected

        lags = self.policies.assign(선택=True)
        with patch("ship_orders_forecasting.validation.select_lags", return_value=lags), \
             patch("ship_orders_forecasting.validation.select_model", side_effect=selection):
            report, predictions, snapshot = annual_validation(
                self.data, self.policies, self.params,
                {"evaluation_years": [2024, 2025]}, "test")
        self.assertEqual(seen, [("2023-11", "2021-01"), ("2024-11", "2022-01")])
        self.assertTrue(report["상태"].eq("완료").all())
        self.assertTrue(report["평가월수"].eq(12).all())
        np.testing.assert_array_equal(predictions["예측"], predictions["기준선예측"])
        for row in predictions.itertuples(index=False):
            self.assertLessEqual(pd.Timestamp(row.학습종료월),
                                 pd.Timestamp(row.기준월) - pd.DateOffset(months=2))
        self.assertGreater(predictions.iloc[-1]["학습관측월"], predictions.iloc[0]["학습관측월"])
        self.assertEqual(len(snapshot["연도별선택"]), 2)

    def test_insufficient_inner_history_is_reported_without_relaxing_threshold(self):
        with patch("ship_orders_forecasting.validation.select_lags",
                   side_effect=InsufficientHistoryError("공통 검증월 14개 < 최소 24개")):
            report, predictions, snapshot = annual_validation(
                self.data, self.policies, self.params,
                {"evaluation_years": [2024]}, "test")
        self.assertEqual(report.iloc[0]["상태"], "생략")
        self.assertIn("14개", report.iloc[0]["사유"])
        self.assertTrue(predictions.empty)
        self.assertEqual(snapshot["연도별선택"], {})

    def test_baseline_and_model_scores_use_identical_outer_months(self):
        missing = self.data.copy()
        missing.loc[missing["기준월"].eq("2024-02"), "x_1개월전"] = np.nan
        selected = {"모형": "1차 선형회귀", "피처목록": ["x_1개월전"],
                    "검증관측월": 30, "검증sMAPE": 0.1}
        with patch("ship_orders_forecasting.validation.select_lags", return_value=self.policies.assign(선택=True)), \
             patch("ship_orders_forecasting.validation.select_model",
                   return_value=(None, None, pd.DataFrame(), None, selected)):
            report, predictions, _ = annual_validation(
                missing, self.policies, self.params, {"evaluation_years": [2024]}, "test")
        self.assertEqual(report.iloc[0]["가용실적월수"], 12)
        self.assertEqual(report.iloc[0]["평가월수"], 11)
        self.assertEqual(report.iloc[0]["미평가월"], "2024-02")
        expected = metrics(predictions["실제"], predictions["기준선예측"])["sMAPE"]
        self.assertAlmostEqual(report.iloc[0]["기준선sMAPE"], expected)

    def test_one_year_feature_frequency_is_not_labelled_stable(self):
        reports = [pd.DataFrame([{"선종": str(i), "평가연도": 2025}]) for i in range(5)]
        snapshots = [{"선종": str(i), "연도별선택": {"2025": {
            "상태": "완료", "최종선택": {"피처목록": ["x_1개월전"]}}}} for i in range(5)]
        _, stability = summarize_validation_audit(*reports, *snapshots)
        self.assertTrue(stability["해석"].str.contains("안정성 판단 불가").all())


if __name__ == "__main__":
    unittest.main()
