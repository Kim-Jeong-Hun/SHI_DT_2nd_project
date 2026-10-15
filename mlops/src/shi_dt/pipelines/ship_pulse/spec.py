"""Ship Pulse 운영 사양 — 팀 서비스(shipulse.vercel.app)가 쓰는 선종별 최종 설정.

출처: 팀 저장소 frontend/src/data/notebookForecasts.ts(reference.json 으로 복사) 와
조장 최종 실험 '롤링 VALIDATION 분할' 그림 5장(학습 전략 · 창 개수).
여기 값을 바꾸면 파이프라인이 그 설정으로 다시 학습한다.
"""
import json
from pathlib import Path

REFERENCE = json.loads((Path(__file__).with_name("reference.json")).read_text(encoding="utf-8"))

# 공통 시점 설계: 3개월 전 데이터로 예측(C+3) · 검증 3개월씩 겹치지 않게 · Test 24개월
HORIZON = 3                 # 변수는 목표월보다 최소 3개월 앞선 값만 쓴다
MAX_EXTRA_LAG = 6           # CCF 로 고르는 추가 시차 0~6개월
VAL_MONTHS = 3              # 검증 창 길이 = 이동 간격 (서로 겹치지 않음)
LAST_VAL_START = "2024-01"  # 마지막 검증 창 2024-01~03
TEST = ("2024-07", "2026-06")      # 조장 최종 그림(Test 24개월) — 마지막 검증 2024-01~03 뒤 3개월 띄움
TRAIN_GAP = 4               # 학습 목표월은 검증 시작 4개월 전까지 (조장 그림 기준)
VIF_MAX = 10.0
WEAK_SHARE = 2 / 3          # 세 지표가 함께 하위 30%인 창이 2/3 넘으면 제거

SHIPS = {
    "container": {"name": "컨테이너선", "unit": "TEU", "model": "tweedie_xgb", "strategy": ("A", [24, 36, 48, 60]), "windows": 17},
    "bulk":      {"name": "벌크선", "unit": "DWT", "model": "pls", "strategy": ("S", 24), "windows": 17},
    "tanker":    {"name": "유조선", "unit": "DWT", "model": "quantile", "strategy": ("S", 60), "windows": 17},
    "gas":       {"name": "가스 운반선", "unit": "CBM", "model": "huber", "strategy": ("S", 36), "windows": 17},
    "chemical":  {"name": "케미컬 탱커", "unit": "DWT", "model": "xgboost", "strategy": ("A", [24, 36, 48]), "windows": 13},
}
for _k, _v in SHIPS.items():
    _v["n_features"] = REFERENCE["vessels"][_k]["featureCount"]   # 팀 최종 모형의 변수 개수(Top-N)
