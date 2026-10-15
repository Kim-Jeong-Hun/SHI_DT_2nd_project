"""선박 수주 예측 서비스 계층.

입력: data/01_raw/ship/2026_독립검증.json — 팀 파이프라인(scripts/분석/2026_독립검증.py)이 만든 보고서.
  · 선종 × 선행 1·3·6개월마다 '게시일 확인된 수주만 입력'한 실제 운영 예측(예측기준일 2026-09-30)
  · 같은 설정의 2026-01–08 월별 백테스트(실제 · 예측)
  · 기준일 입력값(확정 수주 최근 1·2·3·6개월)
      data/01_raw/ship/processed/수주실적(선종).csv — 월별 수주 이력

이 모듈은 다시 학습하지 않는다. 재계산은 Kedro ship_orders 파이프라인(팀 스크립트 실행)이 보고서를 갱신하고,
파일 수정 시각이 바뀌면 다음 요청부터 자동으로 새 보고서를 읽는다.
예측 범위는 2026 백테스트의 '실제 ÷ 예측' 비율 10–90% 분위로 만든 경험적 범위이며 표본이 작다(최대 8개월).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(os.environ.get("SHI_PROJECT_DIR", Path(__file__).resolve().parents[3]))
DATA = ROOT / "data" / "01_raw" / "ship"
REPORT = DATA / "2026_독립검증.json"
SHIPS = ["컨테이너선", "케미컬 탱커", "유조선", "벌크선", "가스 운반선"]
HORIZONS = (1, 3, 6)
# 노트북 테스트(2025-04–2026-08) 집계 단위 sMAPE(%) — scripts/분석/수주예측(선종).ipynb 출력
AGG = {"컨테이너선": (57.42, 12.53, 13.33), "케미컬 탱커": (79.58, 58.12, 45.63), "벌크선": (64.22, 44.53, 54.09),
       "가스 운반선": (93.41, 81.69, 76.64), "유조선": (85.10, 73.19, 99.35)}   # 2026-10-06 13시 Drive 재동기화본

_cache: dict = {}


def _report() -> dict:
    m = REPORT.stat().st_mtime
    if _cache.get("m") != m:
        _cache.update(m=m, d=json.loads(REPORT.read_text(encoding="utf-8")), hist={})
    return _cache["d"]


def _entry(ship: str) -> dict:
    for e in _report()["결과"]:
        if e["선종"] == ship:
            return e
    raise KeyError(ship)


def history(ship: str) -> list[list]:
    h = _cache.setdefault("hist", {})
    if ship not in h:
        f = DATA / "processed" / f"수주실적({ship}).csv"
        df = pd.read_csv(f, encoding="utf-8-sig")
        h[ship] = [[r.iloc[0], None if pd.isna(r.iloc[2]) else float(r.iloc[2])] for _, r in df.iterrows()]
    return h[ship]


def meta() -> dict:
    rep = _report()
    ships = []
    for s in SHIPS:
        e = _entry(s)
        ev = e["2026평가"]
        mon, q, half = AGG[s]
        ships.append({"선종": s, "단위": e["단위"], "선택모형": e["선택"]["모형"], "변수수": len(e["선택"]["피처목록"]),
                      "2026월별sMAPE": round(ev["월별sMAPE"], 3), "2026기준선sMAPE": round(ev["기준선sMAPE"], 3),
                      "테스트sMAPE_월별": mon, "테스트sMAPE_분기": q, "테스트sMAPE_반기": half})
    return {"평가기간": rep["평가기간"], "방법": rep["방법"], "제약": rep["제약"], "선행개월": list(HORIZONS),
            "예측기준일": "2026-09-30", "선종": ships, "보고서수정시각": pd.Timestamp(REPORT.stat().st_mtime, unit="s", tz="UTC").tz_convert("Asia/Seoul").isoformat()}


def _band(backtest: list[dict], pred: float | None) -> dict | None:
    ratios = [b["실제"] / b["예측"] for b in backtest if b.get("예측") and b.get("실제") is not None and b["예측"] > 0]
    if pred is None or len(ratios) < 4:
        return None
    lo, mid, hi = np.quantile(ratios, [0.1, 0.5, 0.9])
    bias = "과소 예측 경향" if mid > 1.15 else ("과대 예측 경향" if mid < 0.87 else "치우침 작음")
    return {"하한": round(pred * lo), "상한": round(pred * hi), "실제÷예측_중앙값": round(float(mid), 2), "편향": bias,
            "근거": f"2026 백테스트 {len(ratios)}개월의 실제÷예측 비율 10–90% 분위를 예측값에 곱함"}


def _baseline(ship: str, last_month: str | None) -> float | None:
    """기준선 = 입력 가능한 최신 확정 수주월까지 최근 3개월 평균(관측 없는 달은 제외)."""
    if not last_month:
        return None
    vals = [v for m, v in history(ship) if m <= last_month and v is not None][-3:]
    return round(sum(vals) / len(vals)) if vals else None


def forecast(ship: str, horizon: int) -> dict:
    if ship not in SHIPS:
        raise KeyError(ship)
    if horizon not in HORIZONS:
        raise ValueError(horizon)
    e = _entry(ship)
    d = next(x for x in e["직접선행예측"] if x["선행개월"] == horizon)
    op = d["2026-09-30_실제운영예측"]
    bt = d["2026평가"]["월별예측"]
    pred = op.get("예측")
    return {
        "선종": ship, "단위": e["단위"], "선행개월": horizon, "예측기준일": op["예측기준일"], "목표월": op["목표월"],
        "예측": None if pred is None else round(pred), "상태": op["상태"],
        "예측범위": _band(bt, pred), "기준선_최근3개월평균": _baseline(ship, op.get("입력수주관측월")),
        "근거": {"피처": op.get("운영피처"), "모형": op.get("운영모형"), "입력부족대체": op.get("입력부족대체"),
               "입력수주관측월": op.get("입력수주관측월"), "입력수주게시일": op.get("입력수주게시일"), "학습관측월": op.get("학습관측월")},
        "선택": {"피처": d["선택"]["피처"], "모형": d["선택"]["모형"], "검증평균sMAPE": round(d["선택"]["평균sMAPE"], 3),
               "fold별sMAPE": {k: round(v, 3) for k, v in d["선택"]["fold별sMAPE"].items()}},
        "백테스트": {"월별sMAPE": round(d["2026평가"]["월별sMAPE"], 3),
                  "월별": [{"목표월": b["목표월"], "실제": b["실제"], "예측": round(b["예측"]) if b.get("예측") is not None else None,
                          "가용근거": b.get("가용근거")} for b in bt]},
        "이력": history(ship),
    }
