"""OPEC 원표의 주요 시기별 추출 형식을 확인한다."""

import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "수집" / "OPEC_VLCC_월별_수집.py"
MODULE = None
if importlib.util.find_spec("pypdf") is not None:
    SPEC = importlib.util.spec_from_file_location("opec_vlcc_collection", PATH)
    MODULE = importlib.util.module_from_spec(SPEC)
    SPEC.loader.exec_module(MODULE)


@unittest.skipIf(MODULE is None, "pypdf 수집 의존성 미설치")
class OpecVlccCollectionTest(unittest.TestCase):
    def test_route_row_old_and_indented_format(self):
        for row, expected in [
            ("Middle East/East 230-280 62 70 67 -3", "67"),
            ("  Middle East/East 230-280 36 42 43 1", "43"),
            ("  Middle East/East 230-280 112 77 49 -2 8", "49"),
        ]:
            with self.subTest(row=row):
                self.assertEqual(MODULE.ROUTE_ROW.search(row).group(3), expected)

    def test_publication_month_is_after_observation_month(self):
        self.assertEqual(MODULE.month_before(2015, 2), "2015-01")
        self.assertEqual(MODULE.month_before(2026, 1), "2025-12")
        self.assertEqual(MODULE.add_month(2025, 12, 2), (2026, 2))


if __name__ == "__main__":
    unittest.main()
