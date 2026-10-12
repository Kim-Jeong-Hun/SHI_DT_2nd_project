"""유조선 2026 수주 급등 소명 자료 — 그림 1장 + 표(CSV). 팀 파이프라인 사본(deploy/render/team/data)만 사용.
실행: python docs/analysis/oil_tanker_2026_surge.py  → docs/analysis/oil_tanker_2026_surge.png · _table.csv
"""
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
D = ROOT / "deploy/render/team/data"
OUT = Path(__file__).resolve().parent
plt.rcParams.update({"font.family": "Malgun Gothic", "axes.unicode_minus": False, "font.size": 9})

raw = pd.read_csv(D / "raw/수주실적.csv")
o = raw[raw.vessel_type == "Oil Tanker"][["period", "new_orders_no", "capacity_value", "source_id", "as_of_date", "quality_grade", "source_url"]]
o = o.rename(columns={"period": "기준월", "new_orders_no": "척수", "capacity_value": "DWT"})
f = pd.read_csv(D / "processed/공통/선종별운임(월).csv")[["기준월", "유조선(VLCC)운임(WS점수)"]].rename(columns={"유조선(VLCC)운임(WS점수)": "VLCC운임WS"})
g = pd.read_csv(D / "processed/공통/지정학위험지수(월).csv")[["기준월", "GPR(세계지정학위험지수)"]].rename(columns={"GPR(세계지정학위험지수)": "GPR"})
b = pd.read_csv(D / "processed/공통/국제원자재가(월).csv")[["기준월", "브렌트유 가격(USD/bbl)"]].rename(columns={"브렌트유 가격(USD/bbl)": "브렌트"})
m = o.merge(f, on="기준월", how="left").merge(g, on="기준월", how="left").merge(b, on="기준월", how="left").sort_values("기준월")
m["척당DWT"] = (m.DWT / m.척수.where(m.척수 > 0)).round(0)
m.to_csv(OUT / "oil_tanker_2026_surge_table.csv", index=False, encoding="utf-8-sig")

m["t"] = pd.to_datetime(m.기준월)
fig, ax = plt.subplots(3, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [2.2, 1.4, 1.2]})
c = ["#c0504d" if x >= "2025-10" else "#8ea9c1" for x in m.기준월]
ax[0].bar(m.t, m.DWT / 1e6, width=25, color=c)
ax[0].set_ylabel("유조선 수주 (백만 DWT)")
ax[0].set_title("유조선 월별 수주량 — 2025년 10월부터 구조적 급증 (빨강), 2026년 1~8월 누적 5,968만 DWT = 2015년 이후 어느 해 전체보다 많음", loc="left")
NOTE = chr(10).join(["주요 월 (Clarksons 인용 원문 대조 완료)", "2025-11  43척 · 987만 DWT · VLCC 24척", "2026-02  51척 · 1,243만 DWT · VLCC 31척", "2026-03  41척 · 1,062만 DWT · VLCC 28척"])
ax[0].text(pd.Timestamp("2025-06"), 11.6, NOTE,
           fontsize=8, va="top", ha="right", bbox={"boxstyle": "round,pad=.4", "fc": "white", "ec": "#ccc"})
ax[1].plot(m.t, m.VLCC운임WS, color="#1f4e79", lw=1.4)
ax[1].axhline(m[m.기준월 < "2025"].VLCC운임WS.median(), color="#999", ls=":", lw=1)
ax[1].text(pd.Timestamp("2015-03"), 75, "2015~2024 중앙값 53", fontsize=8, color="#666")
ax[1].set_ylabel("VLCC 운임 (WS)")
ax[1].annotate("2025-09 89 → 11월 123\n(이전 10년 최고 156)", (pd.Timestamp("2025-11"), 123), xytext=(-150, 60), textcoords="offset points", fontsize=8, arrowprops={"arrowstyle": "->", "color": "#666"})
ax[1].annotate("2026-03 호르무즈 봉쇄\n434 → 5월 587 (역대 최고)", (pd.Timestamp("2026-05"), 587), xytext=(-190, -10), textcoords="offset points", fontsize=8, arrowprops={"arrowstyle": "->", "color": "#666"})
ax[2].plot(m.t, m.GPR, color="#7f6000", lw=1.2, label="지정학위험지수 GPR")
ax2 = ax[2].twinx(); ax2.plot(m.t, m.브렌트, color="#548235", lw=1.2, label="브렌트 (USD/bbl)")
ax[2].set_ylabel("GPR"); ax2.set_ylabel("브렌트")
ax[2].annotate("2026-03 GPR 330 (2015년 이후 최고)", (pd.Timestamp("2026-03"), 330), xytext=(-220, -5), textcoords="offset points", fontsize=8, arrowprops={"arrowstyle": "->", "color": "#666"})
h1, l1 = ax[2].get_legend_handles_labels(); h2, l2 = ax2.get_legend_handles_labels(); ax[2].legend(h1 + h2, l1 + l2, loc="upper left", fontsize=8, frameon=False)
for a in ax:
    a.axvspan(pd.Timestamp("2025-09-15"), pd.Timestamp("2026-08-31"), color="#c0504d", alpha=.06)
    a.spines[["top", "right"]].set_visible(False)
fig.text(.01, .005, "자료: 팀 파이프라인 data/raw/수주실적.csv (Clarksons 월간 집계 인용 · 중국 언론 게재본), processed/공통 선종별운임·지정학위험지수·국제원자재가", fontsize=7.5, color="#666")
fig.tight_layout(rect=(0, .015, 1, 1))
fig.savefig(OUT / "oil_tanker_2026_surge.png", dpi=150)
print("saved")
