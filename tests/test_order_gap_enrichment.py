"""결측 0건 보완이 재실행 가능하고 미확인 월을 건드리지 않는지 검사한다."""

import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module


class OrderGapEnrichmentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = legacy_module("수주실적_결측보완")
        cls.raw = pd.read_csv(
            cls.rules.SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False
        )

    def test_idempotent_and_provenance_preserved(self):
        result, zeros, sums = self.rules.enriched(self.raw)
        self.assertEqual((zeros, sums), (0, 0))
        pd.testing.assert_frame_equal(result, self.raw, check_dtype=False)
        new_zero = self.raw.loc[
            self.raw["period"].eq("2015-05")
            & self.raw["vessel_type"].eq("Bulk Carrier")
        ].iloc[0]
        self.assertEqual(new_zero["capacity_value"], "0")
        self.assertEqual(new_zero["capacity_unit"], "DWT")
        self.assertEqual(new_zero["observation_method"], "derived_zero_from_exhaustive_monthly_total")
        self.assertTrue(new_zero["source_url"].startswith("https://"))

    def test_known_zero_can_be_rebuilt_without_changing_other_observations(self):
        removed = self.raw.loc[
            ~(
                self.raw["period"].eq("2022-02")
                & self.raw["vessel_type"].eq("Bulk Carrier")
            )
        ].copy()
        rebuilt, zeros, sums = self.rules.enriched(removed)
        self.assertEqual((zeros, sums), (1, 0))
        self.assertEqual(len(rebuilt), len(self.raw))
        self.assertEqual(
            rebuilt.loc[
                rebuilt["period"].eq("2022-02")
                & rebuilt["vessel_type"].eq("Bulk Carrier"), "capacity_value"
            ].iloc[0], "0"
        )

    def test_unverified_months_and_early_chemical_remain_missing(self):
        for month in ("2016-05", "2019-12"):
            self.assertFalse(self.raw["period"].eq(month).any())
        self.assertFalse(
            (self.raw["period"].lt("2016-06")
             & self.raw["vessel_type"].eq("Chemical Tanker")).any()
        )


if __name__ == "__main__":
    unittest.main()
