"""유조선: 외생 변수 · 복합 원인(상호작용)을 넣으면 2026 급등을 더 잘 맞히는가 — 지침 구조 그대로 시험.

지침(10/06): 결정 시점 T에 T-3까지 공개된 정보로 T+3 수주량 예측(정보 → 목표 6개월 간격), 시간순 분할, 기준선 비교.
- 기준선: T-3까지 알려진 최근 3개월 평균
- 선택(어떤 피처 세트 · 모델이 나은지)은 검증 연도 2023 · 2024 · 2025 (각 해 직전까지 학습) 로만 판단
- 2026-01~08 은 2025-12 까지 목표월로 학습한 모델로 마지막에 한 번만 평가 (2026 라벨은 선택에 사용 안 함)
"""
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingRegressor, HistGradientBoostingRegressor
from sklearn.linear_model import RidgeCV
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

D = Path(__file__).resolve().parents[2] / "deploy/render/team/data"
OUT = Path(__file__).resolve().parent
H, LAG = 3, 3                     # T+3 예측, 정보는 T-3까지 → 목표와 최신 정보 간격 6개월
G = H + LAG

o = pd.read_csv(D / "processed/유조선/수주실적(유조선).csv")[["기준월", "수주용량(DWT)"]].rename(columns={"수주용량(DWT)": "y"})
f = pd.read_csv(D / "processed/공통/선종별운임(월).csv")[["기준월", "유조선(VLCC)운임(WS점수)"]].rename(columns={"유조선(VLCC)운임(WS점수)": "ws"})
g = pd.read_csv(D / "processed/공통/지정학위험지수(월).csv")[["기준월", "GPR(세계지정학위험지수)"]].rename(columns={"GPR(세계지정학위험지수)": "gpr"})
b = pd.read_csv(D / "processed/공통/국제원자재가(월).csv")[["기준월", "브렌트유 가격(USD/bbl)"]].rename(columns={"브렌트유 가격(USD/bbl)": "brent"})
p = pd.read_csv(D / "processed/공통/신조선가(글로벌, 월).csv"); p = p[p.선종.str.contains("유조")][["기준월", "신조선가_백만USD"]].rename(columns={"신조선가_백만USD": "nb"})
df = o.merge(f, on="기준월", how="left").merge(g, on="기준월", how="left").merge(b, on="기준월", how="left").merge(p, on="기준월", how="left")
df = df.sort_values("기준월").reset_index(drop=True)
df[["ws", "gpr", "brent", "nb"]] = df[["ws", "gpr", "brent", "nb"]].ffill()
ly = np.log1p(df.y)

# 피처는 모두 '목표월 기준 G개월 전' 값까지만 (shift(G) 이상)
X = pd.DataFrame({"기준월": df.기준월})
own = {"y_l": ly.shift(G), "y_m3": ly.rolling(3).mean().shift(G), "y_m6": ly.rolling(6).mean().shift(G), "y_m12": ly.rolling(12).mean().shift(G),
       "y_mom": (ly.rolling(3).mean() - ly.rolling(12).mean()).shift(G)}
ws_ratio = np.log(df.ws / df.ws.rolling(24, min_periods=12).median())
mkt = {"ws_ratio": ws_ratio.shift(G), "ws_chg3": np.log(df.ws).diff(3).shift(G), "gpr_z": ((df.gpr - df.gpr.rolling(36, min_periods=12).mean()) / df.gpr.rolling(36, min_periods=12).std()).shift(G),
       "brent_chg6": np.log(df.brent).diff(6).shift(G), "earn_to_price": np.log(df.ws / df.nb).shift(G)}
X = X.assign(**own, **mkt)
X["ws_x_gpr"] = X.ws_ratio * X.gpr_z.clip(lower=0)          # 복합 원인: 운임 강세 × 지정학 긴장
X["ws_x_mom"] = X.ws_ratio * X.y_mom                         # 운임 강세 × 발주 모멘텀(선주 군집 행동)
X["hot"] = (X.ws_ratio > np.log(1.3)).astype(float)          # 국면 표시: 운임이 2년 중앙값보다 30% 이상
X["y"] = ly; X["y_raw"] = df.y
base = np.expm1(ly.rolling(3).mean().shift(G))               # 기준선: 알려진 최근 3개월 평균

SETS = {"A 자기 이력": list(own), "B +시장 국면(운임·GPR·유가·선가)": list(own) + list(mkt),
        "C +복합 원인(상호작용·국면)": list(own) + list(mkt) + ["ws_x_gpr", "ws_x_mom", "hot"]}
# 목표는 원래 단위(DWT)로 학습 — 로그 목표는 0인 달 때문에 기하평균 쪽으로 크게 낮아진다(첫 시험에서 예측합이 실제의 4~18%)
MODELS = {"Ridge": lambda: make_pipeline(StandardScaler(), RidgeCV(alphas=np.logspace(-2, 3, 20))),
          "GBM(제곱오차)": lambda: GradientBoostingRegressor(n_estimators=300, max_depth=2, learning_rate=.03, subsample=.8, random_state=42),
          "GBM(포아송)": lambda: HistGradientBoostingRegressor(loss="poisson", max_depth=2, learning_rate=.05, max_iter=300, min_samples_leaf=10, random_state=42)}


def wape(a, f):
    a, f = np.asarray(a, float), np.asarray(f, float); k = ~np.isnan(a) & ~np.isnan(f)
    return float(np.abs(a[k] - f[k]).sum() / np.abs(a[k]).sum())


def qsum(x):   # 분기 합 (월 수가 3의 배수가 아니면 남는 달은 버림, 결측 달은 0 대신 제외 — 2023-11 결측)
    x = np.asarray(x, float); n = len(x) // 3 * 3
    return np.nansum(x[:n].reshape(-1, 3), 1)


def fit_pred(cols, mk, train_end, test_months):
    tr = X[(X.기준월 <= train_end)].dropna(subset=cols + ["y"])
    te = X[X.기준월.isin(test_months)]
    m = mk(); m.fit(tr[cols], tr.y_raw)
    return np.clip(m.predict(te[cols].fillna(tr[cols].median())), 0, None)


rows = []
for name, cols in SETS.items():
    for mn, mk in MODELS.items():
        r = {"세트": name, "모형": mn}
        for yr in ["2023", "2024", "2025"]:
            months = X.기준월[X.기준월.str.startswith(yr)].tolist()
            pr = fit_pred(cols, mk, f"{int(yr) - 1}-12", months)
            a = X.y_raw[X.기준월.isin(months)].values
            r[f"검증{yr}_WAPE"] = wape(a, pr)
            r[f"검증{yr}_분기WAPE"] = wape(qsum(a), qsum(pr))
        months = [f"2026-{m:02d}" for m in range(1, 9)]
        pr = fit_pred(cols, mk, "2025-12", months)
        a = X.y_raw[X.기준월.isin(months)].values
        r["2026_WAPE"] = wape(a, pr); r["2026_분기WAPE(1~6월)"] = wape(qsum(a[:6]), qsum(pr[:6]))
        r["2026_예측합/실제합"] = pr.sum() / a.sum()
        r["_pred"] = pr
        rows.append(r)
res = pd.DataFrame(rows)
# 기준선
bl = {"세트": "기준선(최근 3개월 평균)", "모형": "-"}
for yr in ["2023", "2024", "2025"]:
    mm = X.기준월.str.startswith(yr); a = X.y_raw[mm].values; pr = base[mm].values
    bl[f"검증{yr}_WAPE"] = wape(a, pr); bl[f"검증{yr}_분기WAPE"] = wape(qsum(a), qsum(pr))
mm = X.기준월.isin([f"2026-{m:02d}" for m in range(1, 9)]); a = X.y_raw[mm].values; pr = base[mm].values
bl["2026_WAPE"] = wape(a, pr); bl["2026_분기WAPE(1~6월)"] = wape(qsum(a[:6]), qsum(pr[:6])); bl["2026_예측합/실제합"] = pr.sum() / a.sum(); bl["_pred"] = pr
res = pd.concat([pd.DataFrame([bl]), res], ignore_index=True)
vc = [c for c in res if c.startswith("검증") and c.endswith("_WAPE")]
res["검증평균WAPE"] = res[vc].mean(axis=1)
pd.set_option("display.width", 250)
show = res.drop(columns="_pred").round(3)
print(show.to_string(index=False))
show.to_csv(OUT / "oil_tanker_exog_experiment.csv", index=False, encoding="utf-8-sig")
best = res.iloc[1:].sort_values("검증평균WAPE").iloc[0]
print("\n검증 기준 최선:", best.세트, best.모형)
print("2026 월별 실제(만 DWT):", (a / 1e4).round(0).tolist())
print("최선 예측        :", (best._pred / 1e4).round(0).tolist())
print("기준선           :", (bl["_pred"] / 1e4).round(0).tolist())
