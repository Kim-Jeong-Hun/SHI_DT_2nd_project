"""민규 10/08 09:01 'GPRC 44개국 후보 확장 → Validation 4선종 개선' 확인용 (분석 전용, 팀 코드 미수정).

질문: 후보 44개를 한꺼번에 넣고 검증으로 고르면, 우연만으로도 '개선'이 얼마나 나오나?
방법: 선종별 대리 모형(Ridge, 목표 = log(다음 분기 / 최근 12개월 수준), 기본 피처 = 수주 모멘텀 · 변동성 · 선종 운임 · GPR)에
      GPRC 1개씩 추가(T-3, 36개월 z점수) → 지침 규칙 '검증 2022 · 2023 · 2024 중 2개 이상 개선'을 통과한 국가 수를 센다.
      같은 절차를 '가짜 후보'(실제 GPRC를 12~84개월 무작위로 순환 이동해 시점 관계만 깨뜨린 것) 44개 × 20회로 반복 → 우연 통과 수와 비교.
자료: GPR 국가별(Caldara & Iacoviello, data_gpr_export.xls, 2026-09까지) — data/gprc_iacoviello.csv
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

R = Path(__file__).resolve().parents[2]
D = R / "deploy/render/team/data/processed"
TYPES = ["컨테이너선", "벌크선", "유조선", "케미컬 탱커", "가스 운반선"]
FREIGHT = {"컨테이너선": "feu", "벌크선": "bdi", "유조선": "ws", "케미컬 탱커": "ws", "가스 운반선": "lng"}
fr = pd.read_csv(D / "공통/선종별운임(월).csv").rename(columns={"벌크선운임(BDI점수)": "bdi", "유조선(VLCC)운임(WS점수)": "ws", "컨테이너운임_극동북유럽(USD/FEU)": "feu"})
cm = pd.read_csv(D / "공통/국제원자재가(월).csv").rename(columns={"일본 LNG 가격(USD/MMBtu)": "lng"})[["기준월", "lng"]]
import os
ALL = os.environ.get("GPR_SET") == "all110"   # 민규 10:13 유조선 시험과 같은 110개(월 · 기사 수 N10/N3H · 설명 열 제외)
g = pd.read_csv(R / ("data/gpr_iacoviello_all.csv" if ALL else "data/gprc_iacoviello.csv")); g["기준월"] = pd.to_datetime(g.month).dt.strftime("%Y-%m")
CC = ([c for c in g.columns if c not in ("month", "N10", "N3H", "var_name", "var_label", "기준월", "GPR")] + ["GPR"]) if ALL else [c for c in g.columns if c.startswith("GPRC_")]
TYPES = [t for t in TYPES if not os.environ.get("ONLY") or t == os.environ["ONLY"]]
L = 3
rng = np.random.default_rng(42)


def z(s):
    return (s - s.rolling(36, min_periods=12).mean()) / s.rolling(36, min_periods=12).std()


def frame(t):
    o = pd.read_csv(D / f"{t}/수주실적({t}).csv"); o = o[["기준월", o.columns[2]]].rename(columns={o.columns[2]: "y"})
    d = o.merge(fr, on="기준월", how="left").merge(cm, on="기준월", how="left").merge(g[["기준월"] + list(dict.fromkeys(["GPR"] + CC))], on="기준월", how="left").sort_values("기준월").reset_index(drop=True)
    d = d.ffill()
    y = d.y; yf = y.fillna(y.rolling(3, min_periods=1).mean()); fx = d[FREIGHT[t]]
    X = pd.DataFrame({"기준월": d.기준월, "fut": y.shift(-1) + y.shift(-2) + y.shift(-3), "lvl12": yf.rolling(12).mean().shift(L) * 3,
                      "mom": (np.log1p(yf.rolling(3).mean()) - np.log1p(yf.rolling(12).mean())).shift(L), "vol": np.log1p(yf).rolling(12).std().shift(L),
                      "fr": np.log(fx / fx.rolling(24, min_periods=12).median()).shift(L), "gpr": z(d.GPR).shift(L)})
    X["tgt"] = np.log((X.fut + 1) / (X.lvl12 + 1))
    C = pd.DataFrame({c: z(d[c]) for c in CC})
    return X, C


def val_wape(X, extra=None):
    out = []
    base = ["mom", "vol", "fr", "gpr"]
    for yr in (2022, 2023, 2024):
        cut = (pd.Period(f"{yr - 1}-09", "M") - 3).strftime("%Y-%m")
        Z = X.copy()
        cols = base
        if extra is not None:
            Z["c"] = extra.shift(L).values; cols = base + ["c"]
        tr = (Z.기준월 <= cut) & Z[cols + ["tgt", "lvl12"]].notna().all(axis=1)
        te = (Z.기준월 >= f"{yr - 1}-10") & (Z.기준월 <= f"{yr}-09") & Z.fut.notna()
        m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 25))).fit(Z.loc[tr, cols], Z.loc[tr, "tgt"])
        p = (Z.loc[te, "lvl12"] + 1) * np.exp(m.predict(Z.loc[te, cols].fillna(Z.loc[tr, cols].median()))) - 1
        a = Z.loc[te, "fut"]; k = a.notna() & p.notna()
        out.append(float(np.abs(a[k] - p[k]).sum() / a[k].abs().sum()))
    return np.array(out)


rows = []
for t in TYPES:
    X, C = frame(t)
    b = val_wape(X)
    real = [c for c in CC if (val_wape(X, C[c]) < b).sum() >= 2]
    fake = []
    for _ in range(20):
        n = 0
        for c in CC:
            s = C[c].dropna()
            sh = pd.Series(np.roll(s.values, rng.integers(12, 85)), index=s.index).reindex(C.index)
            n += int((val_wape(X, sh) < b).sum() >= 2)
        fake.append(n)
    rows.append({"선종": t, "후보수": len(CC), "실제 GPRC 통과": len(real), "가짜 후보 통과(평균)": round(float(np.mean(fake)), 1), "가짜 95% 상한": int(np.quantile(fake, .95)),
                 "통과 국가": " ".join(c[5:] for c in real)})
    print(rows[-1], flush=True)
pd.DataFrame(rows).to_csv(Path(__file__).with_name("gpr110_oil_check.csv" if ALL else "gprc_candidate_check.csv"), index=False, encoding="utf-8-sig")
print("후보 수", len(CC))
