"""기조 논의용 검토 — 5개 선종에서 '복합 · 외생 충격'에 강한 접근을 같은 규칙으로 비교 (팀 파이프라인은 건드리지 않는 분석 전용).

규칙(지침 10/06 그대로): 결정 시점 T에 수주 이력 · 외부 변수는 T-3까지만 사용, 목표 = 다음 분기(T+1~T+3) 합.
평가 = 분기 WAPE (결정 시점 12·3·6·9월). 선택 근거 = 검증 2023 · 2024 · 2025 (각 해 직전 9월까지 끝나는 목표로 학습),
2026 Q1 · Q2 는 마지막에 한 번만 본다. 아래 'M1 선종별'은 팀 모델의 대리(같은 구조의 단순 모형)이지 팀 모델 자체가 아니다.

비교:
  B0 기준선 최근 3개월 평균 · B1 기준선 최근 3년 평균 (지침 최소 기준선)
  M1 선종별 Ridge  — 선종마다 따로, 목표 = log(다음 분기 / 최근 12개월 수준)
  M2 통합(풀링)    — 같은 피처를 5선종 함께 학습(선종 더미 포함) → 국면 전환 사례 수 확대
  M3 결합          — M2 와 B0 의 평균 (모델이 놓친 수준 변화를 기준선이 따라감)
  구간             — M2 예측에 80% 구간(직전 해 검증 오차로 보정한 컨포멀) → 실제가 구간 안에 든 비율
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

D = Path(__file__).resolve().parents[2] / "deploy/render/team/data/processed"
OUT = Path(__file__).resolve().parent
TYPES = {"컨테이너선": "TEU", "벌크선": "DWT", "유조선": "DWT", "케미컬 탱커": "DWT", "가스 운반선": "CBM"}
fr = pd.read_csv(D / "공통/선종별운임(월).csv").rename(columns={"벌크선운임(BDI점수)": "bdi", "유조선(VLCC)운임(WS점수)": "ws", "컨테이너운임_극동북유럽(USD/FEU)": "feu"})
gp = pd.read_csv(D / "공통/지정학위험지수(월).csv").rename(columns={"GPR(세계지정학위험지수)": "gpr"})[["기준월", "gpr"]]
cm = pd.read_csv(D / "공통/국제원자재가(월).csv").rename(columns={"브렌트유 가격(USD/bbl)": "brent", "일본 LNG 가격(USD/MMBtu)": "lng"})[["기준월", "brent", "lng"]]
FREIGHT = {"컨테이너선": "feu", "벌크선": "bdi", "유조선": "ws", "케미컬 탱커": "ws", "가스 운반선": "lng"}
L = 3


def frame(t):
    o = pd.read_csv(D / f"{t}/수주실적({t}).csv")
    o = o[["기준월", o.columns[2]]].rename(columns={o.columns[2]: "y"})
    d = o.merge(fr, on="기준월", how="left").merge(gp, on="기준월", how="left").merge(cm, on="기준월", how="left").sort_values("기준월").reset_index(drop=True)
    d[["bdi", "ws", "feu", "gpr", "brent", "lng"]] = d[["bdi", "ws", "feu", "gpr", "brent", "lng"]].ffill()
    y = d.y.copy()
    yf = y.fillna(y.rolling(3, min_periods=1).mean())          # 결측 월은 학습 피처 계산용으로만 보간 (평가 목표는 원값)
    fx = d[FREIGHT[t]]
    r = np.log(fx / fx.rolling(24, min_periods=12).median())
    gz = (d.gpr - d.gpr.rolling(36, min_periods=12).mean()) / d.gpr.rolling(36, min_periods=12).std()
    out = pd.DataFrame({"선종": t, "기준월": d.기준월,
                        "fut": y.shift(-1) + y.shift(-2) + y.shift(-3),
                        "lvl12": yf.rolling(12).mean().shift(L) * 3, "b0": yf.rolling(3).mean().shift(L) * 3, "b1": yf.rolling(36, min_periods=24).mean().shift(L) * 3,
                        "mom": (np.log1p(yf.rolling(3).mean()) - np.log1p(yf.rolling(12).mean())).shift(L),
                        "vol": (np.log1p(yf).rolling(12).std()).shift(L),
                        "fr_ratio": r.shift(L), "fr_chg3": np.log(fx).diff(3).shift(L), "gpr_z": gz.shift(L),
                        "brent_chg6": np.log(d.brent).diff(6).shift(L), "fr_x_gpr": (r * gz.clip(lower=0)).shift(L)})
    out["tgt"] = np.log((out.fut + 1) / (out.lvl12 + 1))
    return out


P = pd.concat([frame(t) for t in TYPES], ignore_index=True)
FE = ["mom", "vol", "fr_ratio", "fr_chg3", "gpr_z", "brent_chg6", "fr_x_gpr"]
DUM = pd.get_dummies(P.선종, prefix="t", dtype=float)
P = pd.concat([P, DUM], axis=1)
dec = P.기준월.str[5:].isin(["12", "03", "06", "09"])


def ridge():
    return make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 25)))


def test_mask(yr):
    if yr == "2026":
        return dec & P.기준월.isin(["2025-12", "2026-03"])
    return dec & (P.기준월 >= f"{int(yr) - 1}-12") & (P.기준월 <= f"{yr}-09")


def predict(yr, pooled, t=None):
    cut = f"{int(yr) - 1}-09"
    trn = (P.기준월 <= cut) & P[FE + ["tgt", "lvl12"]].notna().all(axis=1)
    # 목표(다음 분기)가 cut 이전에 끝나야 함: 결정 시점 ≤ cut-3개월
    cut_dec = (pd.Period(cut, "M") - 3).strftime("%Y-%m")
    trn &= P.기준월 <= cut_dec
    te = test_mask(yr)
    cols = FE + (list(DUM.columns) if pooled else [])
    if not pooled:
        trn &= P.선종 == t; te &= P.선종 == t
    m = ridge().fit(P.loc[trn, cols], P.loc[trn, "tgt"])
    x = P.loc[te, cols].fillna(P.loc[trn, cols].median())
    lt = m.predict(x)
    return te, (P.loc[te, "lvl12"] + 1) * np.exp(lt) - 1, lt


def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float); k = ~np.isnan(a) & ~np.isnan(p)
    return float(np.abs(a[k] - p[k]).sum() / np.abs(a[k]).sum()) if k.any() else np.nan


rows, cover = [], []
YEARS = ["2022", "2023", "2024", "2025", "2026"]
pred = {}
for yr in YEARS:
    te2, p2, lt2 = predict(yr, True)
    pred[("M2", yr)] = pd.Series(p2.values, index=P.index[te2])
    pred[("M2lt", yr)] = pd.Series(lt2, index=P.index[te2])
    for t in TYPES:
        te1, p1, _ = predict(yr, False, t)
        pred.setdefault(("M1", yr), pd.Series(dtype=float))
        pred[("M1", yr)] = pd.concat([pred[("M1", yr)], pd.Series(p1.values, index=P.index[te1])])

for yr in YEARS[1:]:
    te = test_mask(yr)
    for t in TYPES:
        k = te & (P.선종 == t); idx = P.index[k]
        a = P.loc[idx, "fut"]
        r = {"연도": yr, "선종": t, "B0 최근3개월": wape(a, P.loc[idx, "b0"]), "B1 최근3년": wape(a, P.loc[idx, "b1"]),
             "M1 선종별": wape(a, pred[("M1", yr)].reindex(idx)), "M2 통합": wape(a, pred[("M2", yr)].reindex(idx))}
        r["M3 결합(M2+B0)"] = wape(a, (pred[("M2", yr)].reindex(idx) + P.loc[idx, "b0"]) / 2)
        r["B0+B1 평균"] = wape(a, (P.loc[idx, "b0"] + P.loc[idx, "b1"]) / 2)
        r["M4 결합(M2+B0+B1)"] = wape(a, (pred[("M2", yr)].reindex(idx) + P.loc[idx, "b0"] + P.loc[idx, "b1"]) / 3)
        rows.append(r)
        # 80% 구간: 직전 해 통합 모델의 로그 비율 오차 분위수로 보정 (같은 선종)
        prev = test_mask(str(int(yr) - 1))   # 5선종 오차를 함께 써서 보정 표본을 늘림
        res_prev = (P.loc[prev, "tgt"] - pred[("M2lt", str(int(yr) - 1))].reindex(P.index[prev])).dropna()
        prev2 = test_mask(str(int(yr) - 2)) if yr != "2023" else None
        if prev2 is not None and ("M2lt", str(int(yr) - 2)) in pred:
            res_prev = pd.concat([res_prev, (P.loc[prev2, "tgt"] - pred[("M2lt", str(int(yr) - 2))].reindex(P.index[prev2])).dropna()])
        if len(res_prev) >= 3:
            lo, hi = np.quantile(res_prev, [.1, .9])
            lt = pred[("M2lt", yr)].reindex(idx)
            lv = P.loc[idx, "lvl12"]
            inside = ((a >= (lv + 1) * np.exp(lt + lo) - 1) & (a <= (lv + 1) * np.exp(lt + hi) - 1))[a.notna()]
            cover.append({"연도": yr, "선종": t, "구간 안": int(inside.sum()), "평가 분기": int(inside.size),
                          "아래로 벗어남": int((a < (lv + 1) * np.exp(lt + lo) - 1)[a.notna()].sum()), "위로 벗어남": int((a > (lv + 1) * np.exp(lt + hi) - 1)[a.notna()].sum())})

R = pd.DataFrame(rows)
M = ["B0 최근3개월", "B1 최근3년", "M1 선종별", "M2 통합", "M3 결합(M2+B0)", "B0+B1 평균", "M4 결합(M2+B0+B1)"]
val = R[R.연도.isin(["2023", "2024", "2025"])]
summ = pd.DataFrame({"검증 2023~25 평균": val.groupby("선종")[M].mean().mean(), "2026 Q1·Q2 평균": R[R.연도 == "2026"].groupby("선종")[M].mean().mean()})
summ["검증에서 B1(최근3년) 이긴 선종 수"] = pd.Series({m: int((val.groupby("선종")[m].mean() < val.groupby("선종")["B1 최근3년"].mean()).sum()) for m in M})
pd.set_option("display.width", 250)
print("== 분기 WAPE 요약 (5선종 평균) ==\n", summ.round(3).to_string())
print("\n== 선종별 검증 평균 ==\n", val.groupby("선종")[M].mean().round(3).to_string())
print("\n== 선종별 2026 Q1·Q2 ==\n", R[R.연도 == "2026"].groupby("선종")[M].mean().round(3).to_string())
C = pd.DataFrame(cover)
print("\n== 80% 구간 적중 (M2 + 직전 해 오차 보정) ==\n", C.groupby("연도")[["구간 안", "평가 분기", "아래로 벗어남", "위로 벗어남"]].sum().to_string())
R.round(4).to_csv(OUT / "approach_review_5types.csv", index=False, encoding="utf-8-sig")
C.to_csv(OUT / "approach_review_intervals.csv", index=False, encoding="utf-8-sig")
