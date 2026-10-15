"""Common monthly processed data must follow the analysis calendar."""

import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module


class ProcessedMonthlyPeriodTest(unittest.TestCase):
    def test_long_history_sources_start_at_2015_and_have_no_month_gaps(self):
        for script, builder, path_name in [
            ("국제원자재가_전처리", "build_output", "OUTPUT_PATH"),
            ("지정학위험지수_전처리", "build_processed", "OUTPUT_PATH"),
        ]:
            with self.subTest(script=script):
                rule = legacy_module(script)
                generated = getattr(rule, builder)()
                saved = pd.read_csv(getattr(rule, path_name), encoding="utf-8-sig")
                pd.testing.assert_frame_equal(generated, saved, check_dtype=False)
                months = saved["기준월"].tolist()
                self.assertEqual(months[0], "2015-01")
                self.assertEqual(
                    months,
                    pd.period_range(months[0], months[-1], freq="M").astype(str).tolist(),
                )


if __name__ == "__main__":
    unittest.main()
