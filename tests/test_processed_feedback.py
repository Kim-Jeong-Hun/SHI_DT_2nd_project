"""검토한 processed 스키마와 h+6 외부 입력 후보를 함께 확인한다."""

import unittest

import pandas as pd

from ship_orders_forecasting.legacy import legacy_module
from ship_orders_forecasting.publication_lag_forecast import CORRELATION_GROUPS


rules = legacy_module("마스터테이블_생성")
processed = rules.PROCESSED_DIR / "공통"


class ProcessedFeedbackTest(unittest.TestCase):
    def test_removed_columns_are_absent_from_processed(self):
        rwi = pd.read_csv(rules.CONTAINER_INDEX_PATH, encoding="utf-8-sig")
        risk = pd.read_csv(rules.RISK_PATH, encoding="utf-8-sig")
        self.assertEqual(rwi.columns.tolist(),
                         ["기준월", "글로벌_컨테이너처리량지수"])
        self.assertNotIn("GPRH(역사지정학위험지수)", risk.columns)

    def test_renamed_files_and_cargo_archive(self):
        self.assertTrue(rules.SHIP_PRICE_PATH.is_file())
        self.assertTrue(rules.FLEET_PATH.is_file())
        self.assertFalse((processed / "신조선가(월).csv").exists())
        self.assertFalse((processed / "세계현존선복량(연).csv").exists())
        self.assertFalse((processed / "주요 원자재 물동량(월).csv").exists())
        archived = rules.PROCESSED_DIR / "archive" / "물동량_사용보류_20261005"
        self.assertTrue((archived / "주요 원자재 물동량(월).csv").is_file())
        self.assertTrue((archived / "주요 원자재 물동량(2026잠정).csv").is_file())

    def test_master_has_candidate_families_but_no_cargo(self):
        for ship_type in rules.SHIP_TYPES:
            master = pd.read_csv(rules.MASTER_DIR / f"마스터테이블({ship_type}).csv",
                                 encoding="utf-8-sig")
            self.assertFalse(any("수입량" in name or "수출량" in name
                                 for name in master.columns
                                 if name not in rules.GLOBAL_ECONOMY_COLUMNS))
            for family in CORRELATION_GROUPS.values():
                self.assertTrue(set(family).issubset(master.columns))
            self.assertTrue(master.loc[master["기준월"].eq("2026-07"),
                                       list(CORRELATION_GROUPS["세계거시"])].notna().all().all())


if __name__ == "__main__":
    unittest.main()
