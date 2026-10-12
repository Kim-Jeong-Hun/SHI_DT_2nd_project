"""기조 논의용 2차 검토 — '이상 조짐 · 국면에 따라 비중이 바뀌는' 예측이 고정 비중보다 나은가 (분석 전용, 팀 코드 미수정).

지침 준수: 수주 이력은 T-3까지, 목표 = 다음 분기 합, 분기 WAPE.
  검증(선택) = 2022 · 2023 · 2024 / 평가 = 2025 전체 · 2026 Q1·Q2 (2025·2026은 선택에 쓰지 않음 — CLAUDE.md)
구성 요소: B0 최근 3개월 평균, B1 최근 3년 평균, M2 5선종 통합 Ridge(비율 목표)
비교:
  F  고정 등가중 (M2+B0+B1)/3
  R1 국면 전환 결합 — 이상 조짐 지표가 켜지면 '최근 수준(B0)' 비중을 올린다. 비중 후보는 검증 연도로만 고름
       이상 조짐: 선종 운임이 2년 중앙값보다 30% 이상 높거나(또는 3개월 +30%), 최근 3개월 수주가 12개월 평균의 1.5배 이상
       운임 시차: T-3(지침) / T(운임·GPR은 즉시 공표) 두 가지
  R2 성과 기반 동적 비중 — 결과가 확정된 직전 4개 분기의 구성 요소별 오차의 역수로 비중 (매 시점 자동 갱신)
  R3 최근 표본 가중 — M2 학습 때 최근 자료에 더 큰 가중(반감기 24개월), 결합은 F와 같음
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

D = Path(__file__).resolve().parents[2] / "deploy/render/team/data/processed"
OUT = Path(__file__).resolve().parent
TYPES = ["컨테이너선", "벌크선", "유조선", "케미컬 탱커", "가스 운반선"]
fr = pd.read_csv(D / "공통/선종별운임(월).csv").rename(columns={"벌크선운임(BDI점수)": "bdi", "유조선(VLCC)운임(WS점수)": "ws", "컨테이너운임_극동북유럽(USD/FEU)": "feu"})
gp = pd.read_csv(D / "공통/지정학위험지수(월).csv").rename(columns={"GPR(세계지정학위험지수)": "gpr"})[["기준월", "gpr"]]
cm = pd.read_csv(D / "공통/국제원자재가(월).csv").rename(columns={"브렌트유 가격(USD/bbl)": "brent", "일본 LNG 가격(USD/MMBtu)": "lng"})[["기준월", "brent", "lng"]]
FREIGHT = {"컨테이너선": "feu", "벌크선": "bdi", "유조선": "ws", "케미컬 탱커": "ws", "가스 운반선": "lng"}
L = 3


def frame(t):
    o = pd.read_csv(D / f"{t}/수주실적({t}).csv"); o = o[["기준월", o.columns[2]]].rename(columns={o.columns[2]: "y"})
    d = o.merge(fr, on="기준월", how="left").merge(gp, on="기준월", how="left").merge(cm, on="기준월", how="left").sort_values("기준월").reset_index(drop=True)
    d[["bdi", "ws", "feu", "gpr", "brent", "lng"]] = d[["bdi", "ws", "feu", "gpr", "brent", "lng"]].ffill()
    y = d.y; yf = y.fillna(y.rolling(3, min_periods=1).mean()); fx = d[FREIGHT[t]]
    r = np.log(fx / fx.rolling(24, min_periods=12).median()); c3 = np.log(fx).diff(3)
    gz = (d.gpr - d.gpr.rolling(36, min_periods=12).mean()) / d.gpr.rolling(36, min_periods=12).std()
    mom_raw = np.log1p(yf.rolling(3).mean()) - np.log1p(yf.rolling(12).mean())
    o = pd.DataFrame({"선종": t, "기준월": d.기준월, "fut": y.shift(-1) + y.shift(-2) + y.shift(-3),
                      "lvl12": yf.rolling(12).mean().shift(L) * 3, "b0": yf.rolling(3).mean().shift(L) * 3, "b1": yf.rolling(36, min_periods=24).mean().shift(L) * 3,
                      "mom": mom_raw.shift(L), "vol": np.log1p(yf).rolling(12).std().shift(L),
                      "fr_ratio": r.shift(L), "fr_chg3": c3.shift(L), "gpr_z": gz.shift(L), "brent_chg6": np.log(d.brent).diff(6).shift(L),
                      "fr_x_gpr": (r * gz.clip(lower=0)).shift(L)})
    for lag in (3, 0):   # 이상 조짐 지표 (운임 시차 두 가지, 수주 모멘텀은 항상 T-3)
        o[f"sig{lag}"] = ((r.shift(lag) > np.log(1.3)) | (c3.shift(lag) > np.log(1.3)) | (mom_raw.shift(L) > np.log(1.5))).astype(float)
    o["tgt"] = np.log((o.fut + 1) / (o.lvl12 + 1))
    return o


P = pd.concat([frame(t) for t in TYPES], ignore_index=True)
FE = ["mom", "vol", "fr_ratio", "fr_chg3", "gpr_z", "brent_chg6", "fr_x_gpr"]
DUM = pd.get_dummies(P.선종, prefix="t", dtype=float); P = pd.concat([P, DUM], axis=1); COLS = FE + list(DUM.columns)
dec = P.기준월.str[5:].isin(["12", "03", "06", "09"])


def m2_preds(decay):
    """매년 직전 9월까지 끝나는 목표로 재학습 → 그 해 결정 시점(월별) 예측. 동적 비중 계산을 위해 2019년부터."""
    out = pd.Series(np.nan, index=P.index)
    for yr in range(2019, 2027):
        cut_dec = (pd.Period(f"{yr - 1}-09", "M") - 3).strftime("%Y-%m")
        trn = (P.기준월 <= cut_dec) & P[FE + ["tgt", "lvl12"]].notna().all(axis=1)
        te = (P.기준월 >= f"{yr - 1}-10") & (P.기준월 <= f"{yr}-09")
        w = None
        if decay:
            age = (pd.PeriodIndex(cut_dec, freq="M") - pd.PeriodIndex(P.loc[trn, "기준월"], freq="M")).map(lambda x: x.n).astype(float) if False else None
            ages = np.array([(pd.Period(cut_dec, "M") - pd.Period(m, "M")).n for m in P.loc[trn, "기준월"]], float)
            w = 0.5 ** (ages / 24)
        m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 25)))
        m.fit(P.loc[trn, COLS], P.loc[trn, "tgt"], ridgecv__sample_weight=w)
        out[te] = ((P.loc[te, "lvl12"] + 1) * np.exp(m.predict(P.loc[te, COLS].fillna(P.loc[trn, COLS].median()))) - 1).values
    return out.clip(lower=0)


P["m2"] = m2_preds(False); P["m2d"] = m2_preds(True)


def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float); k = ~np.isnan(a) & ~np.isnan(p)
    return float(np.abs(a[k] - p[k]).sum() / np.abs(a[k]).sum()) if k.any() else np.nan


def regime_combo(wb0_on, sig):
    on = P[sig] == 1
    rest = (1 - wb0_on) / 2
    return np.where(on, wb0_on * P.b0 + rest * P.m2 + rest * P.b1, (P.m2 + P.b0 + P.b1) / 3)


# R2 동적 비중: 같은 선종에서 결과가 확정된(목표 종료 ≤ T-3) 직전 4개 분기 결정의 절대 오차 합의 역수
def dynamic():
    res = pd.Series(np.nan, index=P.index)
    for t in TYPES:
        idx = P.index[(P.선종 == t)]
        sub = P.loc[idx].reset_index()
        for i, row in sub.iterrows():
            # 결정 시점 i 에서 알 수 있는 과거 분기 결정: i-3-3 이하(목표 끝 = 결정+3 ≤ i-3)
            past = sub.iloc[max(0, i - 6 - 12): max(0, i - 5)]
            past = past[past.기준월.str[5:].isin(["12", "03", "06", "09"])].tail(4).dropna(subset=["fut", "m2", "b0", "b1"])
            if len(past) < 2:
                res[row["index"]] = (row.m2 + row.b0 + row.b1) / 3; continue
            err = np.array([np.abs(past.fut - past[c]).sum() for c in ("m2", "b0", "b1")]) + 1e-9
            w = (1 / err) / (1 / err).sum()
            res[row["index"]] = w[0] * row.m2 + w[1] * row.b0 + w[2] * row.b1
    return res


P["F"] = (P.m2 + P.b0 + P.b1) / 3
P["R2"] = dynamic()
P["R3"] = (P.m2d + P.b0 + P.b1) / 3

VAL, TEST = ["2022", "2023", "2024"], ["2025", "2026"]


def mask(yr):
    if yr == "2026":
        return dec & P.기준월.isin(["2025-12", "2026-03"])
    return dec & (P.기준월 >= f"{int(yr) - 1}-12") & (P.기준월 <= f"{yr}-09")


def score(col_or_arr):
    s = pd.Series(col_or_arr, index=P.index) if not isinstance(col_or_arr, str) else P[col_or_arr]
    out = {}
    for yr in VAL + TEST:
        out[yr] = np.mean([wape(P.fut[mask(yr) & (P.선종 == t)], s[mask(yr) & (P.선종 == t)]) for t in TYPES])
    out["검증평균"] = np.mean([out[y] for y in VAL])
    return out


# R1 비중 후보는 검증 평균으로만 선택
best = {}
for lag in (3, 0):
    cands = {w: score(regime_combo(w, f"sig{lag}"))["검증평균"] for w in (0.34, 0.5, 0.6, 0.7, 0.8)}
    best[lag] = min(cands, key=cands.get)
    print(f"R1 운임 T-{lag}: 검증 평균 WAPE 후보 {{{', '.join(f'{k}:{v:.3f}' for k, v in cands.items())}}} → B0 비중 {best[lag]}")

rows = {"B0 최근3개월": score("b0"), "B1 최근3년": score("b1"), "M2 통합": score("m2"), "F 고정 등가중": score("F"),
        f"R1 국면 전환(운임 T-3, B0 {best[3]})": score(regime_combo(best[3], "sig3")),
        f"R1 국면 전환(운임 T, B0 {best[0]})": score(regime_combo(best[0], "sig0")),
        "R2 성과 기반 동적 비중": score("R2"), "R3 최근 표본 가중": score("R3")}
T = pd.DataFrame(rows).T[["검증평균"] + VAL + TEST]
pd.set_option("display.width", 250)
print("\n== 5선종 평균 분기 WAPE (검증 2022~24로 선택 · 2025/2026은 평가만) ==\n", T.round(3).to_string())
T.round(4).to_csv(OUT / "regime_weighting_review.csv", encoding="utf-8-sig")

# 유조선: 이상 조짐 지표가 언제 켜졌나 + 각 방법의 다음 분기 예측
o = P[(P.선종 == "유조선") & (P.기준월 >= "2025-06") & (P.기준월 <= "2026-05")]
print("\n== 유조선 결정 시점별 (만 DWT, 다음 분기 합) ==")
r1 = pd.Series(regime_combo(best[0], "sig0"), index=P.index)
for i, r in o.iterrows():
    print(f"  {r.기준월}  조짐T-3={int(r.sig3)} 조짐T={int(r.sig0)}  실제 {r.fut/1e4:7.0f}  F {r.F/1e4:6.0f}  R1(T) {r1[i]/1e4:6.0f}  R2 {r.R2/1e4:6.0f}  B0 {r.b0/1e4:6.0f}")


# R4 조짐 시 상향 배수 — '비중'이 아니라 '수준'을 올린다. 배수 = 학습 기간(목표가 해당 연도 전에 끝난 결정)에서
#     조짐이 켜졌던 시점들의 실제/F 비율 중앙값(5선종 공통). 매년 재추정, 2025·2026 라벨은 쓰지 않음.
def uplift(sig):
    s = P.F.copy()
    info = []
    for yr in range(2022, 2027):
        cut_dec = (pd.Period(f"{yr - 1}-09", "M") - 3).strftime("%Y-%m")
        h = (P.기준월 <= cut_dec) & (P[sig] == 1) & P.fut.notna() & P.F.notna() & (P.F > 0)
        mult = float(np.clip(np.median(P.fut[h] / P.F[h]), 1, 3)) if h.sum() >= 8 else 1.0
        te = (P.기준월 >= f"{yr - 1}-10") & (P.기준월 <= f"{yr}-09") & (P[sig] == 1)
        s[te] = P.F[te] * mult
        info.append(f"{yr}:{mult:.2f}(n={int(h.sum())})")
    return s, info


for lag in (3, 0):
    s, info = uplift(f"sig{lag}")
    P[f"R4_{lag}"] = s
    print(f"\nR4 상향 배수(운임 T-{lag}) 연도별 배수: {' '.join(info)}")
T2 = pd.DataFrame({"F 고정 등가중": score("F"), "R4 조짐 상향(운임 T-3)": score("R4_3"), "R4 조짐 상향(운임 T)": score("R4_0")}).T[["검증평균"] + VAL + TEST]
print(T2.round(3).to_string())
# 조짐 정확도: 조짐이 켜졌을 때 다음 분기가 F보다 컸던 비율 (검증 / 평가)
for lag in (3, 0):
    for nm, yrs in (("검증", VAL), ("평가", TEST)):
        k = pd.concat([mask(y) for y in yrs], axis=1).any(axis=1) & (P[f"sig{lag}"] == 1) & P.fut.notna()
        k0 = pd.concat([mask(y) for y in yrs], axis=1).any(axis=1) & (P[f"sig{lag}"] == 0) & P.fut.notna()
        print(f"  조짐 T-{lag} {nm}: 켜짐 {int(k.sum())}회 중 실제>F {float((P.fut[k] > P.F[k]).mean()):.0%} · 꺼짐 {int(k0.sum())}회 중 실제>F {float((P.fut[k0] > P.F[k0]).mean()):.0%}")
o = P[(P.선종 == "유조선") & (P.기준월 >= "2025-08") & (P.기준월 <= "2026-03")]
print("유조선 R4(운임 T):", [(m, round(v / 1e4)) for m, v in zip(o.기준월, o.R4_0)])
pd.concat([T, T2.iloc[1:]]).round(4).to_csv(OUT / "regime_weighting_review.csv", encoding="utf-8-sig")
