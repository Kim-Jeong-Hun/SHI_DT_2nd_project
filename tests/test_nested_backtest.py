"""Annual outer replay must freeze selection before reading its test labels."""

import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

from ship_orders_forecasting.nested_backtest import annual_replay
from ship_orders_forecasting.order_availability import PROCESSED_ORDER_LAG_COLUMNS
from ship_orders_forecasting import nested_backtest


class AnnualReplayTest(unittest.TestCase):
    def test_2024_selection_uses_2021_to_2023_and_october_2023_cutoff(self):
        months = pd.date_range("2015-01", "2025-03", freq="MS")
        frame = pd.DataFrame({
            "수주용량": 100.0 + np.arange(len(months)),
            "유가": 30.0 + np.arange(len(months)) * .1,
        }, index=months)
        for lag, column in PROCESSED_ORDER_LAG_COLUMNS.items():
            frame[column] = frame["수주용량"].shift(lag)
        chosen = {
            "피처목록": ["수주용량_확보월", "유가"],
            "모형": "1차 선형회귀", "변수제거경로": [],
            "fold별기준월": {str(year): [f"{year}-01"] for year in (2021, 2022, 2023)},
            "fold별sMAPE": {str(year): .2 for year in (2021, 2022, 2023)},
        }
        with patch.object(nested_backtest, "select_candidates", return_value=(chosen, [])) as selector:
            replay = annual_replay(
                frame, ["유가"], pd.Series(dtype="datetime64[ns]"),
                {"전체 후보": chosen["피처목록"]}, years=(2024,),
            )
        self.assertEqual(selector.call_args.kwargs["first"], "2021-01")
        self.assertEqual(selector.call_args.kwargs["last"], "2023-12")
        self.assertEqual(selector.call_args.kwargs["selection_cutoff"], "2023-10")
        self.assertEqual(selector.call_args.kwargs["fold_years"], (2021, 2022, 2023))
        self.assertEqual(replay["연도별"][0]["선택시최신자료월"], "2023-10")
        self.assertEqual(replay["월별"][0]["데이터마감월"], "2023-10")
        self.assertEqual(replay["월별"][0]["목표월"], "2024-04")
        self.assertEqual(replay["연도별"][0]["평가월수"], 12)

    def test_future_inner_label_is_rejected(self):
        months = pd.date_range("2015-01", "2025-03", freq="MS")
        frame = pd.DataFrame({"수주용량": np.arange(len(months), dtype=float)}, index=months)
        for lag, column in PROCESSED_ORDER_LAG_COLUMNS.items():
            frame[column] = frame["수주용량"].shift(lag)
        chosen = {
            "피처목록": ["수주용량_확보월"], "모형": "1차 선형회귀",
            "fold별기준월": {"2023": ["2023-12"]},
        }
        with patch.object(nested_backtest, "select_candidates", return_value=(chosen, [])):
            with self.assertRaisesRegex(AssertionError, "미래 목표값"):
                annual_replay(frame, [], pd.Series(dtype="datetime64[ns]"),
                              {"전체 후보": chosen["피처목록"]}, years=(2024,))


if __name__ == "__main__":
    unittest.main()
