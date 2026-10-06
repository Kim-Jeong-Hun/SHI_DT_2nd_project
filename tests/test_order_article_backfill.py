"""기사 근거 보완은 중복 없이 재현되고 불확실성 표기를 보존한다."""

import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module


class OrderArticleBackfillTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules = legacy_module("수주실적_기사보완")
        cls.raw = pd.read_csv(
            cls.rules.SOURCE, encoding="utf-8-sig", dtype=str, keep_default_na=False
        )

    def test_idempotent_and_source_quality(self):
        result, added = self.rules.enriched(self.raw)
        self.assertEqual(added, 0)
        pd.testing.assert_frame_equal(result, self.raw, check_dtype=False)
        for month, vessel, capacity, unit in (
            ("2023-07", "Bulk Carrier", "1380000", "DWT"),
            ("2023-07", "Container", "388000", "TEU"),
            ("2023-10", "Container", "2500", "TEU"),
            ("2026-06", "Chemical Tanker", "823300", "DWT"),
        ):
            row = self.raw.loc[
                self.raw["period"].eq(month) & self.raw["vessel_type"].eq(vessel)
            ].iloc[0]
            self.assertEqual((row["capacity_value"], row["capacity_unit"]), (capacity, unit))
            self.assertEqual(row["quality_grade"], "C")
            self.assertIn("published_date=", row["definition_notes"])

    def test_rebuild_only_missing_rows(self):
        removed = self.raw.loc[
            ~(self.raw["period"].eq("2023-10") & self.raw["vessel_type"].eq("Container"))
        ]
        result, added = self.rules.enriched(removed)
        self.assertEqual(added, 1)
        self.assertEqual(len(result), len(self.raw))


if __name__ == "__main__":
    unittest.main()
