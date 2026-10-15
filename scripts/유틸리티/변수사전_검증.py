"""프로젝트 루트에서 `python scripts/유틸리티/변수사전_검증.py`로 실행."""

from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from ship_orders_forecasting.dictionary_audit import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
