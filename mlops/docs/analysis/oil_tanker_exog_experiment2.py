"""유조선 대안 시험 — '수준 예측'의 외삽 한계를 피하는 세 방법 (실험 1과 같은 데이터 · 같은 분할 규칙).

1) 비율 목표: 목표 = log(미래 3개월 합 / 알려진 최근 12개월 월평균×3) → 예측 = 최근 수준 × 예측 배수 (전례 없는 수준도 '배수'로 표현 가능)
2) 시장 변수 공개 시차 단축: 운임(WS) · GPR · 유가는 일·월말 즉시 공표 → T-3 대신 T 기준 정보 사용(목표 간격 6 → 3개월). 수주 이력은 그대로 T-3.
3) 급등 경보(분류): '다음 분기 수주가 최근 3년 월평균의 2배 이상'일 확률 — 국면 변수만으로 방향을 맞히는가
선택은 검증 2023·2024·2025, 2026은 마지막 한 번 평가. 단위: 분기(T+1~T+3 합)로 지침의 핵심 평가 단위에 맞춤.
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression, RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

D = Path(__file__).resolve().parents[2] / "deploy/render/team/data"
o = pd.read_csv(D / "processed/유조선/수주실적(유조선).csv")[["기준월", "수주용량(DWT)"]].rename(columns={"수주용량(DWT)": "y"})
f = pd.read_csv(D / "processed/공통/선종별운임(월).csv")[["기준월", "유조선(VLCC)운임(WS점수)"]].rename(columns={"유조선(VLCC)운임(WS점수)": "ws"})
g = pd.read_csv(D / "processed/공통/지정학위험지수(월).csv")[["기준월", "GPR(세계지정학위험지수)"]].rename(columns={"GPR(세계지정학위험지수)": "gpr"})
b = pd.read_csv(D / "processed/공통/국제원자재가(월).csv")[["기준월", "브렌트유 가격(USD/bbl)"]].rename(columns={"브렌트유 가격(USD/bbl)": "brent"})
df = o.merge(f, on="기준월", how="left").merge(g, on="기준월", how="left").merge(b, on="기준월", how="left").sort_values("기준월").reset_index(drop=True)
df[["ws", "gpr", "brent"]] = df[["ws", "gpr", "brent"]].ffill()
y = df.y.fillna(df.y.rolling(3, min_periods=1).mean())

# 결정 시점 T(행) 기준: 목표 = T+1..T+3 합(분기), 수주 이력은 T-3까지만 알려짐
fut = y.shift(-1) + y.shift(-2) + y.shift(-3)
lvl12 = y.rolling(12).mean().shift(3) * 3                   # 알려진 최근 12개월 월평균 × 3
base3 = y.rolling(3).mean().shift(3) * 3                    # 기준선: 알려진 최근 3개월 평균 × 3
lvl36 = y.rolling(36).mean().shift(3)


def mkt(lag):
    r = np.log(df.ws / df.ws.rolling(24, min_periods=12).median())
    gz = (df.gpr - df.gpr.rolling(36, min_periods=12).mean()) / df.gpr.rolling(36, min_periods=12).std()
    return pd.DataFrame({"ws_ratio": r.shift(lag), "ws_chg3": np.log(df.ws).diff(3).shift(lag), "gpr_z": gz.shift(lag),
                         "brent_chg6": np.log(df.brent).diff(6).shift(lag), "ws_x_gpr": (r * gz.clip(lower=0)).shift(lag),
                         "mom": (np.log1p(y.rolling(3).mean()) - np.log1p(y.rolling(12).mean())).shift(3)})


def wape(a, p):
    a, p = np.asarray(a, float), np.asarray(p, float); k = ~np.isnan(a) & ~np.isnan(p)
    return float(np.abs(a[k] - p[k]).sum() / np.abs(a[k]).sum())


months = df.기준월
# 분기 비중첩 평가: 결정 시점 T = 각 분기 직전 달(12·3·6·9월) → 목표 = 다음 분기
dec = months.str[5:].isin(["12", "03", "06", "09"])


def run(lag, label):
    X = mkt(lag); tgt = np.log((fut + 1) / (lvl12 + 1))
    out = {"방법": label}
    for yr in ["2023", "2024", "2025", "2026"]:
        te = dec & (months >= f"{int(yr) - 1}-12") & (months <= f"{yr}-09") & fut.notna()
        if yr == "2026":
            te = dec & months.isin(["2025-12", "2026-03"])          # 2026 Q1 · Q2 (Q3는 9월 실적 전이라 6월 시점은 Q3 7·8월만 → 제외)
        tr = (months <= f"{int(yr) - 1}-09") & X.notna().all(1) & tgt.notna() & lvl12.notna()   # 목표가 학습 마감 전에 끝나는 행만
        m = make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20))).fit(X[tr], tgt[tr])
        pr = (lvl12[te] + 1) * np.exp(m.predict(X[te].fillna(X[tr].median()))) - 1
        out[yr] = wape(fut[te], pr); out[yr + "_예측/실제"] = float(np.nansum(pr) / np.nansum(fut[te]))
    return out


rows = []
for yr_label, pr_series in [("기준선(최근 3개월 평균)", base3)]:
    r = {"방법": yr_label}
    for yr in ["2023", "2024", "2025", "2026"]:
        te = dec & (months >= f"{int(yr) - 1}-12") & (months <= f"{yr}-09") & fut.notna()
        if yr == "2026": te = dec & months.isin(["2025-12", "2026-03"])
        r[yr] = wape(fut[te], pr_series[te]); r[yr + "_예측/실제"] = float(np.nansum(pr_series[te]) / np.nansum(fut[te]))
    rows.append(r)
rows.append(run(3, "① 비율 목표 + 시장변수 T-3"))
rows.append(run(0, "①+② 비율 목표 + 시장변수 T(즉시 공표)"))
res = pd.DataFrame(rows)
res["검증평균"] = res[["2023", "2024", "2025"]].mean(axis=1)
pd.set_option("display.width", 250)
print("분기 WAPE (결정 시점 = 분기 직전 달, 목표 = 다음 분기 합)")
print(res.round(3).to_string(index=False))

# ③ 급등 경보: 다음 분기 월평균 ≥ 최근 3년 월평균 × 2
surge = ((fut / 3) >= 2 * lvl36).astype(float).where(fut.notna() & lvl36.notna())
for lag, lab in [(3, "T-3"), (0, "T")]:
    X = mkt(lag)[["ws_ratio", "ws_chg3", "gpr_z", "ws_x_gpr", "mom"]]
    tr = (months <= "2024-09") & X.notna().all(1) & surge.notna()
    clf = make_pipeline(StandardScaler(), LogisticRegression(C=.5, class_weight="balanced", max_iter=1000)).fit(X[tr], surge[tr])
    te = (months >= "2024-10") & (months <= "2026-05") & X.notna().all(1)
    pp = clf.predict_proba(X[te])[:, 1]
    print(f"\n③ 급등 경보 (시장변수 {lab}, 2024-09까지 학습, 학습 급등 비율 {surge[tr].mean():.0%})")
    for mo, pv, s in zip(months[te], pp, surge[te]):
        print(f"  {mo} 경보확률 {pv:.2f}  실제 다음분기 급등={'예' if s == 1 else ('아니오' if s == 0 else '?')}")
