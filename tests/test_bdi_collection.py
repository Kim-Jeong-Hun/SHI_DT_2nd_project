"""공개 월별 BDI 원표의 형식·연속성 검증을 확인한다."""

import importlib.util
from pathlib import Path
import unittest


PATH = Path(__file__).resolve().parents[1] / "scripts" / "수집" / "BDI_월별_수집.py"
SPEC = importlib.util.spec_from_file_location("bdi_collection", PATH)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class BdiCollectionTest(unittest.TestCase):
    @staticmethod
    def sample(last_month: str = "2015.02", last_value: str = "300") -> bytes:
        lines = ['"Kuukausi";"Sea freight prices"']
        lines += [f'"{year}.{month:02d}";100' for year in range(2010, 2015) for month in range(1, 13)]
        lines += ['"2015.01";200', f'"{last_month}";{last_value}']
        return ("\n".join(lines) + "\n").encode("utf-8")

    def test_contiguous_valid_source(self):
        self.assertEqual(MODULE.validate(self.sample()), (62, "2010-01", "2015-02"))

    def test_month_gap_rejected(self):
        with self.assertRaisesRegex(ValueError, "불연속"):
            MODULE.validate(self.sample(last_month="2015.03"))

    def test_nonpositive_value_rejected(self):
        with self.assertRaisesRegex(ValueError, "0 이하"):
            MODULE.validate(self.sample(last_value="0"))


if __name__ == "__main__":
    unittest.main()
