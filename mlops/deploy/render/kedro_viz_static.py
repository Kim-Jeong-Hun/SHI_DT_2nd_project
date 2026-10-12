"""`kedro viz build` 결과(build/)를 서빙 경로로 옮긴다 — 외부 분석 스크립트(Heap)는 빼고.

kedro-viz 12.5 의 정적 index.html 은 heap.load(…) 추적 스크립트를 무조건 넣는다. 공개 화면에서 방문자 정보가
외부로 나가지 않게 그 <script> 블록만 지운다. 첫 화면은 ship_orders 파이프라인으로 바꾼다. 사용: python kedro_viz_static.py <build 폴더> <대상 폴더>
"""
import re
import shutil
import sys
from pathlib import Path

src, dst = Path(sys.argv[1]), Path(sys.argv[2])
idx = src / "index.html"
html = idx.read_text(encoding="utf-8")
html, n = re.subn(r"<script[^>]*>(?:(?!</script>).)*heap\.load(?:(?!</script>).)*</script>\s*", "", html, flags=re.S)
idx.write_text(html, encoding="utf-8")
# 첫 화면 = 선박 수주 파이프라인 (다른 파이프라인은 왼쪽 위 목록에서 그대로 고를 수 있다)
first = src / "api" / "pipelines" / "ship_orders"
if first.exists():
    shutil.copyfile(first, src / "api" / "main")
if dst.exists():
    shutil.rmtree(dst)
shutil.move(str(src), str(dst))
print(f"kedro-viz 정적 화면 → {dst} (Heap 스크립트 {n}개 제거)")
