"""선종별 노트북이 공유하는 D=C-3, D+6 분석 진입점."""

from pathlib import Path
import runpy


def run_analysis(ship_type: str) -> dict:
    analysis = runpy.run_path(str(Path(__file__).with_name("공개시차_6개월_컨테이너선.py")))
    return analysis["run_analysis"](ship_type)
