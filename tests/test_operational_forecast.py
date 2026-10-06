"""Publication boundaries and direct horizons must not use later observations."""

import unittest

import numpy as np
import pandas as pd

from ship_orders_forecasting.operational_forecast import (
    POINT_LAGS, WINDOWS, direct_frame, month_end, origin_features, order_history,
)


class OperationalForecastTest(unittest.TestCase):
    def setUp(self):
        months = pd.date_range("2026-01-01", "2026-10-01", freq="MS")
        self.frame = pd.DataFrame({"수주용량": range(1, len(months) + 1)}, index=months)
        self.published = pd.Series({month.strftime("%Y-%m"): month + pd.offsets.MonthEnd(1)
                                    for month in months})
        self.published.loc["2026-08"] = pd.Timestamp("2026-09-28")
        self.published.loc["2026-09"] = pd.Timestamp("2026-10-15")

    def test_september_end_cannot_see_september_order(self):
        history = order_history(self.frame, self.published,
                                pd.Timestamp("2026-09-30"), allow_undated_history=False)
        self.assertEqual(history.index.max(), pd.Timestamp("2026-08-01"))
        features = origin_features(self.frame, self.published,
                                   pd.Timestamp("2026-09-30"), allow_undated_history=False)
        self.assertEqual(features[WINDOWS[1]], 8)
        self.assertEqual(features[WINDOWS[3]], 8 + 7 + 6)

    def test_month_end_uses_final_weekday(self):
        self.assertEqual(month_end(pd.Timestamp("2026-10-01")),
                         pd.Timestamp("2026-10-30"))

    def test_direct_three_and_six_months_share_correct_origin(self):
        three = direct_frame(self.frame, self.published, 3)
        six = direct_frame(self.frame, self.published, 6)
        self.assertEqual(three.at[pd.Timestamp("2026-12-01"), "예측기준일"],
                         pd.Timestamp("2026-09-30"))
        self.assertEqual(six.at[pd.Timestamp("2027-03-01"), "예측기준일"],
                         pd.Timestamp("2026-09-30"))
        self.assertEqual(three.at[pd.Timestamp("2026-12-01"), WINDOWS[1]], 8)
        self.assertEqual(six.at[pd.Timestamp("2027-03-01"), WINDOWS[1]], 8)

    def test_missing_component_does_not_become_zero(self):
        frame = self.frame.copy()
        frame.at[pd.Timestamp("2026-07-01"), "수주용량"] = np.nan
        features = origin_features(frame, self.published,
                                   pd.Timestamp("2026-09-30"), allow_undated_history=False)
        self.assertEqual(features[WINDOWS[1]], 8)
        self.assertTrue(np.isnan(features[WINDOWS[2]]))
        self.assertTrue(np.isnan(features[WINDOWS[3]]))

    def test_undated_report_disallowed_in_live_input(self):
        published = self.published.copy()
        published.loc["2026-08"] = pd.NaT
        features = origin_features(self.frame, published,
                                   pd.Timestamp("2026-09-30"), allow_undated_history=False)
        self.assertEqual(features["최신수주관측월"], pd.Timestamp("2026-07-01"))

    def test_container_point_lags_keep_other_months_when_one_is_missing(self):
        frame = self.frame.copy()
        frame.at[pd.Timestamp("2026-07-01"), "수주용량"] = np.nan
        features = origin_features(
            frame, self.published, pd.Timestamp("2026-09-30"),
            allow_undated_history=False, point_lags=True,
        )
        self.assertEqual(features[POINT_LAGS[1]], 8)
        self.assertTrue(np.isnan(features[POINT_LAGS[2]]))
        self.assertEqual(features[POINT_LAGS[3]], 6)
        self.assertEqual(tuple(POINT_LAGS), (1, 2, 3))


if __name__ == "__main__":
    unittest.main()
