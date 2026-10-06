"""Graph-derived prices must remain traceable and separate from article quotes."""

import csv
from importlib.util import module_from_spec, spec_from_file_location
import unittest

import pandas as pd

from ship_orders_forecasting.legacy import PROJECT_ROOT, legacy_module


def collection_rule():
    path = PROJECT_ROOT / "scripts" / "수집" / "신조선가_유승우2018_도표보완.py"
    spec = spec_from_file_location("ship_price_chart_backfill", path)
    module = module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ShipPriceChartBackfillTest(unittest.TestCase):
    def test_raw_backfill_is_complete_and_idempotent(self):
        rule = collection_rule()
        self.assertEqual(
            list(rule.VECTOR_ESTIMATES),
            pd.period_range("2015-01", "2016-05", freq="M").astype(str).tolist(),
        )
        original = rule.RAW.read_text(encoding="utf-8-sig")
        updated, added = rule.build_updated_text(original)
        self.assertEqual((updated, added), (original, 0))
        rows = list(csv.DictReader(original.splitlines()))
        extracted = [row for row in rows if row["source_id"] == rule.SOURCE_ID]
        self.assertEqual(len(extracted), 17)
        self.assertEqual({row["quality_grade"] for row in extracted}, {"D"})
        self.assertEqual({row["source_url"] for row in extracted}, {rule.SOURCE_URL})
        self.assertEqual({row["capacity_avg"] for row in extracted}, {"1975.0"})

    def test_processed_and_master_use_all_seventeen_months(self):
        rule = legacy_module("신조선가_전처리")
        generated = rule.build_output()
        saved = pd.read_csv(rule.OUTPUT_PATH, encoding="utf-8-sig")
        pd.testing.assert_frame_equal(generated, saved, check_dtype=False)
        months = pd.period_range("2015-01", "2016-05", freq="M").astype(str).tolist()
        processed = saved.loc[
            saved["선종"].eq("컨테이너선") & saved["기준월"].isin(months)
        ].sort_values("기준월")
        self.assertEqual(processed["기준월"].tolist(), months)
        self.assertEqual(processed["원자료품질등급"].tolist(), ["D"] * 17)
        self.assertTrue(processed["신조선가_백만USD"].notna().all())
        master = pd.read_csv(
            PROJECT_ROOT / "data" / "master" / "마스터테이블(컨테이너선).csv",
            encoding="utf-8-sig",
        )
        actual = master.set_index("기준월").loc[months, "신조선가_백만USD"].tolist()
        self.assertEqual(actual, processed["신조선가_백만USD"].tolist())
        next_quote = saved.loc[
            saved["선종"].eq("컨테이너선") & saved["기준월"].eq("2016-06")
        ].iloc[0]
        self.assertEqual(next_quote["신조선가_백만USD"], 24.5)
        self.assertEqual(next_quote["원자료품질등급"], "B")


if __name__ == "__main__":
    unittest.main()
