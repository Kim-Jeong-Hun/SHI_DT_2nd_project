"""2026 holdout assembly must not mistake incomplete cargo for observed input."""

import importlib.util
from pathlib import Path
import unittest

import pandas as pd


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "분석" / "2026_독립검증.py"
SPEC = importlib.util.spec_from_file_location("audit_2026", SCRIPT)
AUDIT = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDIT)


class Holdout2026Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = AUDIT.inputs()

    def test_2026_frame_keeps_cargo_out_of_candidate_features(self):
        frame, candidates = AUDIT.evaluation_frame("벌크선", self.sources)
        self.assertEqual(frame.index.max(), pd.Timestamp("2026-08-01"))
        self.assertEqual(frame.loc["2026-01":"2026-08", AUDIT.TARGET].notna().sum(), 8)
        self.assertTrue(
            frame.loc["2026-01":"2026-08", AUDIT.RULES.SHIP_CARGO_VOLUME_COLUMNS["벌크선"]]
            .isna().all().all()
        )
        self.assertFalse(any("철광석 수입량" in name or "석탄 수출량" in name for name in candidates))
        self.assertFalse(frame.loc["2026-01":"2026-08", candidates].isna().any().any())

    def test_first_holdout_only_allows_pre_2026_labels_for_selection(self):
        frame, _ = AUDIT.evaluation_frame("벌크선", self.sources)
        lag = int(frame.loc[AUDIT.FIRST_TEST_MONTH, AUDIT.AVAILABLE_LAG_COLUMN])
        possible_end = AUDIT.FIRST_TEST_MONTH - pd.DateOffset(months=lag)
        self.assertEqual(possible_end, pd.Timestamp("2025-10-01"))
        verified = frame.loc[
            (frame.index <= possible_end)
            & frame[AUDIT.PUBLISHED_LABEL_COLUMN].notna()
            & frame[AUDIT.PUBLISHED_LABEL_COLUMN].le(pd.Timestamp("2025-12-31"))
        ]
        self.assertEqual(verified.index.max(), pd.Timestamp("2025-08-01"))
        self.assertTrue(pd.isna(frame.loc["2026-02-01", AUDIT.AVAILABLE_LAG_COLUMN]))
        self.assertEqual(
            frame.loc["2026-01-01", AUDIT.AVAILABILITY_STATUS_COLUMN],
            "t-3_게시일미상",
        )
        split = list(AUDIT.monthly_splits(
            frame, [pd.Timestamp("2026-03-01")], ["원유 평균 가격(USD/bbl)_2개월전"], 48,
        ))
        self.assertEqual(len(split), 1)
        self.assertNotIn(pd.Timestamp("2025-11-01"), split[0][1].index)

    def test_september_asof_table_separates_observation_and_release(self):
        frame, external = AUDIT.evaluation_frame("벌크선", self.sources)
        raw = pd.read_csv(AUDIT.RULES.RAW_ORDERS_PATH, dtype=str,
                          encoding="utf-8-sig", keep_default_na=False)
        published = AUDIT.publication_dates(
            raw, AUDIT.RULES.RAW_VESSEL_TYPES["벌크선"],
        )
        table = AUDIT.asof_input_table(
            "벌크선", frame, external, self.sources, published,
        )
        order = table.loc[table["피처"].eq("확정수주_1개월차단일월")].iloc[0]
        self.assertEqual(order["관측월"], "2026-08")
        self.assertEqual(order["게시일"], "2026-09-28")
        self.assertTrue(order["게시일검증"])
        self.assertGreater(order["입력가능값"], 0)
        other = table.loc[table["피처"].eq(external[0])].iloc[0]
        self.assertFalse(other["게시일검증"])
        self.assertTrue(pd.isna(other["입력가능값"]))

    def test_container_point_lags_have_distinct_observation_months(self):
        frame, external = AUDIT.evaluation_frame("컨테이너선", self.sources)
        raw = pd.read_csv(AUDIT.RULES.RAW_ORDERS_PATH, dtype=str,
                          encoding="utf-8-sig", keep_default_na=False)
        published = AUDIT.publication_dates(
            raw, AUDIT.RULES.RAW_VESSEL_TYPES["컨테이너선"],
        )
        table = AUDIT.asof_input_table(
            "컨테이너선", frame, external, self.sources, published,
        )
        orders = table.loc[table["피처"].str.startswith("확정수주_")]
        self.assertEqual(orders["관측월"].tolist(),
                         ["2026-08", "2026-07", "2026-06"])


if __name__ == "__main__":
    unittest.main()
