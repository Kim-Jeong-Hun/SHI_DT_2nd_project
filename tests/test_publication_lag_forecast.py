"""Point-in-time boundaries for the conservative publication-lag prototype."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ship_orders_forecasting.publication_lag_forecast import (
    ORDER_LAGS, asof_inputs, data_cutoff, direct_grid,
    eligible_training, predict_at, select_correlated_features,
)
from ship_orders_forecasting.order_availability import PROCESSED_ORDER_LAG_COLUMNS
from ship_orders_forecasting import publication_lag_forecast as forecast


class PublicationLagForecastTest(unittest.TestCase):
    def setUp(self):
        months = pd.date_range("2015-01", "2025-01", freq="MS")
        self.frame = pd.DataFrame({
            "수주용량": 100.0 + np.arange(len(months)) * 3,
            "유가": 30.0 + np.arange(len(months)) * .2,
        }, index=months)
        for lag, column in PROCESSED_ORDER_LAG_COLUMNS.items():
            self.frame[column] = self.frame["수주용량"].shift(lag)
        self.published = pd.Series(dtype="datetime64[ns]")

    def test_october_2024_uses_july_and_targets_august_to_january(self):
        self.assertEqual(tuple(ORDER_LAGS), (1, 2, 3))
        origin = pd.Timestamp("2024-10-31")
        self.assertEqual(data_cutoff(origin), pd.Timestamp("2024-07-01"))
        grid = direct_grid(self.frame, ["유가"], self.published,
                           first_origin="2024-10", last_origin="2024-10")
        self.assertEqual(grid.loc[(pd.Timestamp("2024-10-31"), 1), "목표월"],
                         pd.Timestamp("2024-08-01"))
        self.assertEqual(grid.loc[(pd.Timestamp("2024-10-31"), 6), "목표월"],
                         pd.Timestamp("2025-01-01"))
        self.assertEqual(grid.loc[(pd.Timestamp("2024-10-31"), 6), "유가"],
                         self.frame.at[pd.Timestamp("2024-07-01"), "유가"])
        self.assertEqual(grid.loc[(pd.Timestamp("2024-10-31"), 6), ORDER_LAGS[2]],
                         self.frame.at[pd.Timestamp("2024-07-01"),
                                       PROCESSED_ORDER_LAG_COLUMNS[1]])

    def test_future_external_and_label_mutations_cannot_change_forecast(self):
        origin = pd.Timestamp("2024-10-31")
        features = [ORDER_LAGS[1], "유가"]
        before = direct_grid(self.frame, ["유가"], self.published,
                             first_origin="2015-01", last_origin="2024-10")
        first = predict_at(before, 6, origin, features, "1차 선형회귀", min_train=12)
        self.assertIsNotNone(first)
        self.assertLessEqual(first["학습라벨종료월"], pd.Timestamp("2024-07-01"))
        changed = self.frame.copy()
        changed.loc["2024-08":, ["유가", "수주용량"]] = 999999.0
        after = direct_grid(changed, ["유가"], self.published,
                            first_origin="2015-01", last_origin="2024-10")
        second = predict_at(after, 6, origin, features, "1차 선형회귀", min_train=12)
        self.assertAlmostEqual(first["예측"], second["예측"])
        self.assertTrue((eligible_training(after, 6, origin, features)["목표월"]
                         <= pd.Timestamp("2024-07-01")).all())

    def test_known_late_order_publication_blocks_even_cutoff_month(self):
        published = pd.Series({"2024-07": pd.Timestamp("2024-11-10")})
        inputs = asof_inputs(self.frame, ["유가"], published, pd.Timestamp("2024-10-31"))
        self.assertTrue(np.isnan(inputs[ORDER_LAGS[1]]))
        self.assertEqual(inputs["유가"], self.frame.at[pd.Timestamp("2024-07-01"), "유가"])

    def test_retrospective_mode_keeps_month_cutoff_without_article_date_gate(self):
        recorded = pd.Series({"2024-07": pd.Timestamp("2024-11-10")})
        retrospective = pd.Series(pd.NaT, index=recorded.index, dtype="datetime64[ns]")
        inputs = asof_inputs(self.frame, ["유가"], retrospective,
                             pd.Timestamp("2024-10-31"))
        self.assertEqual(inputs["데이터마감월"], pd.Timestamp("2024-07-01"))
        self.assertEqual(inputs[ORDER_LAGS[1]],
                         self.frame.at[pd.Timestamp("2024-07-01"), "수주용량"])

    def test_group_uses_largest_absolute_training_correlation(self):
        training = pd.DataFrame({
            "실제": [1, 2, 3, 4, 5],
            "GPR(세계지정학위험지수)": [5, 4, 3, 2, 1],
            "GPRT(지정학위협지수)": [1, 1, 2, 2, 3],
            "GPRA(지정학행동지수)": [2, 1, 1, 2, 1],
        })
        candidates = [name for name in training if name != "실제"]
        selected, audit = select_correlated_features(training, candidates)
        self.assertEqual(selected, ["GPR(세계지정학위험지수)"])
        self.assertAlmostEqual(audit["지정학"]["학습상관계수"], -1.0)

    def test_group_selection_never_reads_future_observation(self):
        training = pd.DataFrame({
            "실제": [1, 2, 3, 4],
            "미국TPU(EPUTRADE 무역정책불확실성지수)": [4, 3, 2, 1],
            "미국TPU(Caldara 무역정책불확실성지수)": [1, 2, 2, 3],
        })
        features = [name for name in training if name != "실제"]
        before, _ = select_correlated_features(training, features)
        # 미래행을 별도로 가진 전체표가 바뀌어도 함수에 전달한 학습행은 불변.
        future = pd.concat([training, pd.DataFrame({
            "실제": [999], features[0]: [999], features[1]: [-999],
        })], ignore_index=True)
        after, _ = select_correlated_features(future.iloc[:len(training)], features)
        self.assertEqual(before, after)

    def test_full_candidate_backward_selection_uses_paired_year_folds(self):
        origins = pd.date_range("2022-01-31", "2024-12-31", freq="ME")
        features = [*ORDER_LAGS.values(), "불필요변수", "유지변수"]
        rows = pd.DataFrame({
            "선행개월": 6,
            "실제": 100.0,
            "목표월": origins + pd.DateOffset(months=3),
            "목표게시일": pd.NaT,
            **{name: 1.0 for name in features},
        }, index=origins.rename("예측기준일"))
        grid = rows.reset_index().set_index(["예측기준일", "선행개월"])

        def fake_predict(_grid, _horizon, _origin, chosen, _model):
            return {"실제": 100.0, "예측": 150.0 if "불필요변수" in chosen else 100.0}

        with (patch.object(forecast, "MODELS", ("가상모형",)),
              patch.object(forecast, "eligible_training", return_value=pd.DataFrame(index=range(36))),
              patch.object(forecast, "predict_at", side_effect=fake_predict)):
            selected, ranked = forecast.select_candidates(
                grid, {"전체 후보": features}, 6,
            )
        self.assertEqual(selected["시작모형후보"]["피처목록"], features)
        self.assertEqual(selected["변수제거경로"][0]["제거변수"], "불필요변수")
        self.assertEqual(len(selected["변수제거경로"]), 1)
        self.assertNotIn("불필요변수", selected["피처목록"])
        fold_counts = {year: len(months) for year, months in selected["fold별기준월"].items()}
        self.assertTrue(all(row["fold별평가월"] == fold_counts for row in ranked))


if __name__ == "__main__":
    unittest.main()
