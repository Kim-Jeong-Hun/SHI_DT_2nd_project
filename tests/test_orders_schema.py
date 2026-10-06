"""The compact processed orders schema must retain upstream quality checks."""

import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module
from ship_orders_forecasting.order_availability import PROCESSED_ORDER_LAG_COLUMNS


class OrdersSchemaTest(unittest.TestCase):
    def setUp(self):
        self.processor = legacy_module("수주실적_전처리")
        self.master = legacy_module("마스터테이블_생성")
        self.raw = pd.DataFrame({
            "frequency": ["monthly", "monthly"],
            "period": ["2025-01", "2025-02"],
            "vessel_type": ["Bulk Carrier", "Bulk Carrier"],
            "new_orders_no": ["2", "0"],
            "capacity_value": ["100000", "0"],
            "capacity_unit": ["DWT", "DWT"],
        })

    def test_compact_output_and_master_input(self):
        processed = self.processor.build_processed(self.raw, "벌크선")
        self.assertEqual(processed.columns.tolist(), [
            "기준월", "선종", "수주용량(DWT)", *PROCESSED_ORDER_LAG_COLUMNS.values()
        ])
        self.assertTrue(pd.isna(processed.loc[0, PROCESSED_ORDER_LAG_COLUMNS[1]]))
        self.assertEqual(processed.loc[1, PROCESSED_ORDER_LAG_COLUMNS[1]], 100000)
        orders, _ = self.master.load_orders("벌크선", processed)
        self.assertEqual(orders.columns.tolist(), [
            "기준월", "수주용량", *PROCESSED_ORDER_LAG_COLUMNS.values()
        ])
        self.assertEqual(orders["수주용량"].tolist(), [100000, 0])

    def test_wrong_unit_is_rejected_before_saving(self):
        raw = self.raw.copy()
        raw.loc[0, "capacity_unit"] = "TEU"
        with self.assertRaisesRegex(ValueError, "수주용량단위"):
            self.processor.build_processed(raw, "벌크선")

    def test_zero_mismatch_is_rejected_before_saving(self):
        raw = self.raw.copy()
        raw.loc[1, "capacity_value"] = "10"
        with self.assertRaisesRegex(ValueError, "0 여부"):
            self.processor.build_processed(raw, "벌크선")

    def test_duplicate_month_is_rejected_before_saving(self):
        raw = self.raw.copy()
        raw.loc[1, "period"] = "2025-01"
        with self.assertRaisesRegex(ValueError, "중복"):
            self.processor.build_processed(raw, "벌크선")

    def test_master_rejects_wrong_ship_and_extra_column(self):
        processed = self.processor.build_processed(self.raw, "벌크선")
        wrong_ship = processed.copy()
        wrong_ship.loc[0, "선종"] = "Oil Tanker"
        with self.assertRaisesRegex(ValueError, "선종"):
            self.master.load_orders("벌크선", wrong_ship)
        extra_column = processed.assign(신규수주척수=2)
        with self.assertRaisesRegex(ValueError, "컬럼"):
            self.master.load_orders("벌크선", extra_column)

    def test_lag_uses_calendar_month_not_previous_observed_row(self):
        raw = self.raw.copy()
        raw.loc[1, "period"] = "2025-03"
        raw.loc[1, "capacity_value"] = "200000"
        raw.loc[1, "new_orders_no"] = "2"
        processed = self.processor.build_processed(raw, "벌크선")
        self.assertEqual(processed["기준월"].tolist(), ["2025-01", "2025-02", "2025-03"])
        self.assertTrue(pd.isna(processed.loc[1, "수주용량(DWT)"]))
        self.assertEqual(processed.loc[1, PROCESSED_ORDER_LAG_COLUMNS[1]], 100000)
        self.assertTrue(pd.isna(processed.loc[2, PROCESSED_ORDER_LAG_COLUMNS[1]]))
        self.assertEqual(processed.loc[2, PROCESSED_ORDER_LAG_COLUMNS[2]], 100000)
        self.assertTrue(pd.isna(processed.loc[2, PROCESSED_ORDER_LAG_COLUMNS[3]]))


if __name__ == "__main__":
    unittest.main()
