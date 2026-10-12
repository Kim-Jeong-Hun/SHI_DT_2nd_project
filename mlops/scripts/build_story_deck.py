"""발표 스크롤 장표(serving/static/ship_story.html)용 데이터·도판 생성.

입력 (모두 팀 산출물, 값은 바꾸지 않는다)
  - 팀 마스터 테이블: ~/projects/ship-order-drive/data/master/마스터테이블(선종).csv
  - 정훈 군집 분석: data/slack_attach_1007/마스터테이블_탐색적_분석_및_군집_여부.zip
  - UI팀 분석 파이프라인 PDF(10/09, 78쪽): 피라미드·VIF·필터 도판을 잘라 쓰고,
    3.4 창별 RMSSE 막대와 2.5 Rolling 창 위치는 픽셀에서 판독한다(격자선으로 눈금 보정,
    가중평균을 반감기 12개월 가중치로 다시 계산해 그림의 빨간 점선과 대조).
출력: serving/static/story/data.js, serving/static/story/img/*.webp
사용: python scripts/build_story_deck.py --pdf "<PDF 경로>"
"""
from __future__ import annotations

import argparse
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd
import pypdfium2 as pdfium

ROOT = Path(__file__).resolve().parents[1]
TEAM = Path.home() / "projects" / "ship-order-drive"
OUT = ROOT / "serving" / "static" / "story"
SHIPS = ["컨테이너선", "벌크선", "유조선", "가스 운반선", "케미컬 탱커"]
UNIT = {"컨테이너선": "TEU", "벌크선": "DWT", "유조선": "DWT", "가스 운반선": "CBM", "케미컬 탱커": "DWT"}
# PDF 쪽 번호: 선종별 15쪽 묶음의 첫 쪽(1.2 초기 피라미드)
FIRST_PAGE = {"컨테이너선": 4, "벌크선": 19, "유조선": 34, "가스 운반선": 49, "케미컬 탱커": 64}
FIGS = {"pyr0": 0, "vif": 1, "weak": 2, "pyr1": 3, "pyr1t": 4, "pi": 8, "topn": 9, "psm": 13}   # 묶음 안 순번
REDUCED_N = {"컨테이너선": 20, "벌크선": 29, "유조선": 21, "가스 운반선": 24, "케미컬 탱커": 24}  # 1.3.2 그림 제목
TRAIN_MONTHS = {"케미컬 탱커": 36}
META = {"기준월", "수주용량단위", "수주정보시차(개월)", "수주정보가용근거"}


def short(name: str) -> str:
    return name.replace("_", " ")


def master(ship: str) -> pd.DataFrame:
    df = pd.read_csv(TEAM / "data" / "master" / f"마스터테이블({ship}).csv", encoding="utf-8-sig")
    return df.set_index("기준월")


def feature_block(ship: str) -> dict:
    df = master(ship)
    cols = [c for c in df.columns if c not in META and not c.startswith("수주용량_")]
    feats = [c for c in cols if c != "수주용량"]
    target = df["수주용량"]
    # 동월 Spearman 순위상관 상위 3개를 강조 후보로 (설명용, 모형 선택과 무관)
    rho = {c: df[c].corr(target, method="spearman") for c in feats}
    top = [c for c, _ in sorted(rho.items(), key=lambda kv: -abs(kv[1]) if pd.notna(kv[1]) else 0)[:3]]
    series = []
    for c in ["수주용량", *feats]:
        s = df[c].astype(float)
        lo, hi = s.min(), s.max()
        norm = ((s - lo) / (hi - lo)) if hi > lo else s * 0
        series.append({"name": c, "label": short(c), "rho": None if c == "수주용량" else round(float(rho[c]), 3),
                       "v": [None if pd.isna(x) else round(float(x), 4) for x in norm],
                       "raw": [None if pd.isna(x) else round(float(x), 3) for x in s]})
    zero = int(target.eq(0).sum())
    return {"months": list(df.index), "series": series, "top": top, "nFeat": len(feats),
            "orders": [None if pd.isna(x) else float(x) for x in target],
            "zeroMonths": zero, "observed": int(target.notna().sum())}


def clusters() -> dict:
    z = zipfile.ZipFile(ROOT / "data" / "slack_attach_1007" / "마스터테이블_탐색적_분석_및_군집_여부.zip")
    base = "마스터테이블_탐색적_분석_및_군집_여부/근거자료/"
    monthly = pd.read_csv(io.BytesIO(z.read(base + "컨테이너선_시장수준_월별군집.csv")), encoding="utf-8-sig")
    summary = pd.read_csv(io.BytesIO(z.read(base + "컨테이너선_시장수준_군집요약.csv")), encoding="utf-8-sig")
    names = {1: "고선가·고물동량 / 운임 완화", 2: "저운임·저선가", 3: "고운임·공급망 압박"}
    return {
        "rows": [{"m": r["기준월"], "y": r["수주용량"], "freight": r["컨테이너운임_극동북유럽(USD/FEU)"],
                  "price": r["신조선가_백만USD"], "port": r["글로벌_컨테이너처리량지수"],
                  "gscpi": r["글로벌_공급망압력지수(표준편차)"], "c": int(r["군집"]),
                  "next3": None if pd.isna(r["향후3개월수주합"]) else float(r["향후3개월수주합"])}
                 for _, r in monthly.iterrows()],
        "summary": [{"c": int(r["군집"]), "name": names[int(r["군집"])], "months": int(r["개월수"]),
                     "first": r["최초월"], "last": r["최종월"], "median": float(r["동월수주중앙값"]),
                     "zero": float(r["수주0비율"]), "next3": float(r["향후3개월합중앙값"]),
                     "freight": float(r["컨테이너운임_극동북유럽(USD/FEU)"]), "price": float(r["신조선가_백만USD"])}
                    for _, r in summary.iterrows()],
        "silhouette": 0.477, "ari": 0.983, "k": 3,
    }


def render(pdf, page: int, scale: float = 2.2):
    return pdf[page - 1].render(scale=scale).to_pil().convert("RGB")


def crop_figures(pdf) -> dict:
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    paths = {}
    for ship, first in FIRST_PAGE.items():
        key = SHIPS.index(ship)
        for tag, offset in FIGS.items():
            im = render(pdf, first + offset)
            w, h = im.size
            box = (int(w * .045), int(h * .145), int(w * .955), int(h * .765))
            name = f"s{key}_{tag}.webp"
            im.crop(box).save(OUT / "img" / name, "WEBP", quality=80, method=6)
            paths.setdefault(ship, {})[tag] = f"story/img/{name}"
        # 4.1 Test 평가와 운영 예측 시계열(묶음 15번째) — 위 패널(실제·Validation·Test·D+3 전망)만 크게
        im = render(pdf, first + 14, 4.2)
        w, h = im.size
        name = f"s{key}_hold.webp"
        im.crop((int(w * .045), int(h * .232), int(w * .468), int(h * .408))).save(OUT / "img" / name, "WEBP", quality=88, method=6)
        paths[ship]["hold"] = f"story/img/{name}"
    return paths


def robustness(pdf) -> dict:
    out = {}
    for ship, first in FIRST_PAGE.items():
        a = np.asarray(render(pdf, first + 10, 3)).astype(int)   # 3.4 기본·튜닝·앙상블 최종 선택
        H, W, _ = a.shape
        bar = (abs(a[..., 0] - 76) < 22) & (abs(a[..., 1] - 120) < 22) & (abs(a[..., 2] - 168) < 22)
        cols = bar.sum(0) > 20
        runs, s = [], None
        for x in range(W):
            if cols[x] and s is None:
                s = x
            if not cols[x] and s is not None:
                if x - s > 8:
                    runs.append((s, x))
                s = None
        tops, bottoms = [], []
        for s_, e in runs:
            ys = np.where(bar[:, (s_ + e) // 2])[0]
            tops.append(ys.min()); bottoms.append(ys.max())
        base = np.median(bottoms) + .5
        gx = [(runs[i][1] + runs[i + 1][0]) // 2 for i in range(len(runs) - 1)]
        g = (abs(a[:, gx, 0] - 204) < 4) & (abs(a[:, gx, 2] - 204) < 4)
        grid = []
        for y in [y for y in range(H) if g[y].mean() > .6 and y < base - 5]:
            if not grid or y - grid[-1][-1] > 2:
                grid.append([y])
            else:
                grid[-1].append(y)
        spacing = float(np.median(np.diff(sorted(np.mean(r) for r in grid))))
        step = .1 if ship == "컨테이너선" else .2   # 그림의 y축 눈금 간격(도판 확인)
        vals = [round(float((base - t) / spacing * step), 3) for t in tops]
        n = len(vals)
        w = np.array([2 ** ((i - (n - 1)) * 3 / 12) for i in range(n)]); w /= w.sum()
        worst = sorted(vals, reverse=True)[:max(1, int(np.ceil(n * .2)))]
        out[ship] = {"rmsse": vals, "weights": [round(float(x), 4) for x in w],
                     "weighted": round(float((w * np.array(vals)).sum()), 3),
                     "mean": round(float(np.mean(vals)), 3), "cvar20": round(float(np.mean(worst)), 3),
                     "best": int(np.argmin(vals)), "worst": int(np.argmax(vals))}
    return out


def windows() -> dict:
    """Rolling 창 위치: 도판 판독 결과 모든 선종의 마지막 Validation이 2025-06에 끝나고,
    Train(48개월, 케미컬 36개월) → 2개월 정답 확보 공백 → Validation 12개월, 3개월씩 이동."""
    counts = {"컨테이너선": 12, "벌크선": 12, "유조선": 22, "가스 운반선": 18, "케미컬 탱커": 16}
    last_val_end = 2025 * 12 + 5   # 2025-06 (0-based month index)
    ym = lambda m: f"{m // 12}-{m % 12 + 1:02d}"
    out = {}
    for ship, n in counts.items():
        tr = TRAIN_MONTHS.get(ship, 48)
        rows = []
        for k in range(n):
            shift = 3 * (n - 1 - k)
            ve = last_val_end - shift; vs = ve - 11; te = vs - 3; ts = te - tr + 1
            rows.append({"train": [ym(ts), ym(te)], "val": [ym(vs), ym(ve)]})
        out[ship] = {"train": tr, "val": 12, "gap": 2, "step": 3, "windows": rows}
    return out


def freight_scan() -> dict:
    """컨테이너선 운임의 시차·대칭 변화율 탐색: D월 입력 → D+3 수주와의 Spearman ρ.
    2025년 이후는 보지 않는다(2015-01~2024-12 기준월 120개). 설명용 탐색이며 모형 선택이 아니다."""
    df = master("컨테이너선")
    fr = df["컨테이너운임_극동북유럽(USD/FEU)"].astype(float)
    target = df["수주용량"].astype(float).shift(-3)
    keep = [m for m in df.index if m <= "2024-12"]
    sym = lambda x, k: (x - x.shift(k)) / ((x.abs() + x.shift(k).abs()) / 2) * 100
    rows = [("수준값", fr)] + [(f"대칭변화율 {k}개월", sym(fr, k)) for k in (3, 6, 9, 12)]
    lags = [0, 1, 2, 3, 6, 9, 12]
    grid = []
    for name, ser in rows:
        vals = []
        for lag in lags:
            d = pd.concat([ser.shift(lag), target], axis=1).loc[keep].dropna()
            vals.append(round(float(d.iloc[:, 0].corr(d.iloc[:, 1], method="spearman")), 3))
        grid.append({"name": name, "rho": vals})
    return {"lags": lags, "rows": grid, "n": len(keep)}


def covers() -> dict:
    """참고 논문·사례조사 표지: 로컬 PDF는 첫 쪽을 그리고, 링크만 있는 자료는 제목 표지로 둔다."""
    refs = [("Wada et al. 2018", "A system dynamics model for shipbuilding demand forecasting", "J. Marine Sci. Tech.", "Wada et al. (2018).pdf"),
            ("Wada et al. 2022", "Shipbuilding capacity optimization using shipbuilding demand forecasting model", "J. Marine Sci. Tech.", "Wada et al. (2022).pdf"),
            ("Han et al. 2024", "Forecasting shipbuilding demand using shipping market modeling: LNGC", "IJNAOE", "Han et al. (2024).pdf"),
            ("Sakalayen et al. 2021", "An econophysics approach to forecast bulk shipbuilding orderbook", "Maritime Business Review", "Sakalayen et al. (2021).pdf"),
            ("Cheng et al. 2024", "Ship order book forecasting by an ensemble deep RVFL network", "Eng. Appl. of AI", None),
            ("Gao et al. 2022", "Newbuilding ship price forecasting by parsimonious intelligent model search", "Expert Syst. Appl.", "Gao et al. (2022).pdf"),
            ("Georgoulas et al. 2026", "How do geopolitical risks affect ship investment decisions?", "Transport Transitions", "Georgoulas et al. (2026).pdf"),
            ("Tsioumas et al. 2021", "Capturing the impact of economic forces on the dry bulk freight market", "Maritime Transport Research", "Tsioumas et al. (2021).pdf"),
            ("Muzhoffar et al. 2022", "Basic ship-planning support system using big data", "JMSE", "Muzhoffar et al. (2022).pdf"),
            ("Mo et al. 2025", "Shipping economic forecasting: recent developments and future directions", "Transport Reviews", "Mo et al. (2025).pdf"),
            ("유승우 2018", "현대미포조선: 화학의 다운사이클 수혜 폭식 가능", "증권사 기업 분석 리포트", "(유승우, 2018).pdf")]
    cases = [("KMI 2020", "시계열 분석을 통한 해운시장 분석 및 예측", "한국해양수산개발원", "국내사례_KMI_시계열분석_해운시장예측_2020.pdf"),
             ("KMI 2022", "AI·빅데이터 기반 컨테이너운임 예측모형", "경제·인문사회연구회", None),
             ("KMI", "해운시장 종합정보망 구축 3단계", "실제 정보시스템", None),
             ("해양수산 빅데이터 플랫폼", "조선해운 전주기 데이터 센터", "국내 데이터 플랫폼", None),
             ("HD한국조선해양 2024", "디지털 트윈 야드·AI 연결 예측", "지속가능경영보고서", "국내사례_HD한국조선해양_디지털전환_2024.pdf"),
             ("Clarksons", "Shipping Intelligence Network", "상용 플랫폼", None),
             ("Baltic Exchange", "Data Services · 해운 벤치마크", "운임 지수", None),
             ("Veson · VesselsValue", "Oceanbolt · Shipfix", "상용 플랫폼", "해외사례_Veson_VesselsValue_소개자료.pdf"),
             ("Drewry", "Maritime Research · Container Dashboard", "상용 전망 서비스", None),
             ("Muzhoffar et al. 2022", "Ship-Planning Support System", "연구 프로토타입", None)]
    (OUT / "img" / "cover").mkdir(parents=True, exist_ok=True)
    out = {}
    for kind, items, folder in (("refs", refs, TEAM / "references"), ("cases", cases, TEAM / "case_study")):
        rows = []
        for k, (who, title, venue, pdf_name) in enumerate(items):
            img = None
            if pdf_name and (folder / pdf_name).exists():
                try:
                    page = pdfium.PdfDocument(str(folder / pdf_name))[0].render(scale=1.2).to_pil().convert("RGB")
                    page.thumbnail((300, 420))
                    img = f"story/img/cover/{kind}{k}.webp"
                    page.save(ROOT / "serving" / "static" / img, "WEBP", quality=72)
                except Exception as e:  # noqa: BLE001 — 표지 하나 실패해도 제목 표지로 대체
                    print("표지 실패:", pdf_name, e)
            rows.append({"who": who, "title": title, "venue": venue, "img": img})
        out[kind] = rows
    return out


def regimes(report: Path | None) -> dict | None:
    """군집분석 전체과정 보고서(10/08, 카톡 공유 HTML)의 내장 차트 데이터를 그대로 옮긴다.
    variant: macro(선종+공통 거시, C1 평상·C2 거시 충격) · spec(선종 고유) · v2(최종 국면). 값은 바꾸지 않는다."""
    if not report or not report.exists():
        return None
    import html as H
    import re
    s = report.read_text(encoding="utf-8", errors="ignore")
    names = {0: "벌크선", 1: "유조선", 2: "컨테이너선", 3: "가스 운반선", 4: "케미컬 탱커"}
    out = {}
    for kind in ("combo", "scat"):
        pat = r'id="combo-(macro|spec|v2)-(\d)(-scat)?"[^>]*?data-' + kind + r"""=(?P<q>["'])(.*?)(?P=q)"""
        for m in re.finditer(pat, s, flags=re.S):
            var, k = m.group(1), int(m.group(2))
            d = json.loads(H.unescape(m.group(5)))
            out.setdefault(var, {}).setdefault(names[k], {})[kind] = d
    return out


def holdout(pdf) -> dict:
    """4.1 Test 평가와 운영 예측 시계열 위 패널을 픽셀로 읽어 월별 값으로 복원(근사).
    x: 연 격자 간격 = 12개월, 검정선 끝 = 2026-07 / y: 검정선 픽셀과 마스터 실제값의 선형 회귀(상관 0.95~0.999)."""
    col = {"val": (68, 132, 196), "test": (222, 170, 40), "fc": (214, 40, 40)}
    tol = {"val": 45, "test": 45, "fc": 50}
    allm = pd.period_range("2014-01", "2026-12", freq="M").astype(str).tolist()
    out = {}
    for ship, first in FIRST_PAGE.items():
        im = np.asarray(render(pdf, first + 14, 4.2)).astype(int)
        H, W, _ = im.shape
        y0 = int(H * .18); sub = im[y0:int(H * .45), :int(W * .5)]
        bg = (abs(sub[..., 0] - 231) < 5) & (abs(sub[..., 1] - 240) < 5) & (abs(sub[..., 2] - 249) < 5)
        cs = np.where(bg.sum(0) > 40)[0]; rs = np.where(bg.sum(1) > 300)[0]
        a = im[y0 + rs[0] + 2:y0 + rs[-1] - 1, cs[0]:int(W * .5)]
        masks = {k: (abs(a[..., 0] - c[0]) < tol[k]) & (abs(a[..., 1] - c[1]) < tol[k]) & (abs(a[..., 2] - c[2]) < tol[k]) for k, c in col.items()}
        dark = a.max(-1) < 60
        dark[:, :4] = False
        x1 = np.where(dark.sum(0) > 0)[0].max()                      # 검정선 끝 = 2026-07
        g = a.sum(-1)
        gl = np.where(((g > 680) & (g < 712) & (a[..., 2] - a[..., 0] > 6)).sum(0) > a.shape[0] * .5)[0]
        gl = [v for k, v in enumerate(gl) if k == 0 or v - gl[k - 1] > 3]
        pm = float(np.median(np.diff(gl))) / 12
        x_of = lambda m: x1 - (pd.Period("2026-07", "M") - pd.Period(m, "M")).n * pm

        def ys(m, x):
            if x < 0 or x >= m.shape[1]:
                return np.nan
            r = np.where(m[:, int(round(x))])[0]
            return r.mean() if len(r) else np.nan
        act = master(ship)["수주용량"].astype(float)
        act = act[act.index <= "2026-07"]
        yb = np.array([ys(dark, x_of(m)) for m in act.index])
        ok = ~np.isnan(yb) & ~np.isnan(act.values)
        A = np.vstack([yb[ok], np.ones(ok.sum())]).T
        coef, *_ = np.linalg.lstsq(A, act.values[ok], rcond=None)
        r = float(np.corrcoef(A @ coef, act.values[ok])[0, 1])
        res = {"months": allm, "actual": [None if pd.isna(v) else float(v) for v in act.reindex(allm).values], "fitR": round(r, 4)}
        for k, m in masks.items():
            v = [ys(m, x_of(mm)) for mm in allm]
            res[k] = [None if np.isnan(y) else round(max(0.0, float(coef[0] * y + coef[1])), 1) for y in v]
        # 구간: Test는 마지막 12개월(2025-08~2026-07), D+3 전망은 2026-08~10 (2026-07은 연결점)
        i0, i1 = allm.index("2025-08"), allm.index("2026-07")
        res["val"] = [None if i >= i0 else v for i, v in enumerate(res["val"])]
        res["fc"] = [v if allm.index("2026-08") <= i <= allm.index("2026-10") else None for i, v in enumerate(res["fc"])]
        res["test"] = [v if i0 <= i <= i1 else None for i, v in enumerate(res["test"])]
        print(f"{ship}: 4.1 판독 상관 {r:.3f}")
        out[ship] = res
    return out


def explored() -> dict:
    """자산 장 흐름 글자용: 실제로 모으거나 검토한 변수·원천 시리즈 이름(마스터 열 + 후보 기록 + 원천 파일 머리글)."""
    raw = TEAM / "data" / "raw"
    names = {}
    def add(n, src):
        n = str(n).strip()
        if n and n.lower() != "nan" and len(n) < 60 and not n.startswith(("var_", "Unnamed")):
            names.setdefault(n, src)
    for line in (TEAM / "data" / "마스터테이블_후보_포함제외_기록.txt").read_text(encoding="utf-8").splitlines():
        t = line.strip()
        if t.startswith("· ") and len(t) < 42 and ":" not in t and not t.rstrip(").").endswith(("다", "음", "함")) and t.count(" ") <= 4 and "," not in t:
            add(t[2:], "후보 기록")
    for f in sorted((raw / "xsi_c_csv_20261002").glob("XSI-C_*_운임.csv")):
        add(f.stem.replace("_", " "), "XSI-C")
    for f in sorted((raw / "물동량").glob("*.csv")):
        if "_2026" not in f.stem:
            add(f.stem, "물동량")
    try:
        pk = pd.read_excel(raw / "세계은행_원자재가격_PinkSheet_월별.xlsx", "Monthly Prices", header=None, nrows=6)
        for v in pk.iloc[4, 1:].tolist():
            add(str(v).replace(" **", "").replace(" *", ""), "World Bank Pink Sheet")
    except Exception as e:  # 원천 파일이 없으면 건너뜀
        print("Pink Sheet 건너뜀:", e)
    try:
        g = pd.read_excel(raw / "위험지수_모든컬럼.xlsx", nrows=1)
        for c in g.columns[1:]:
            add(c, "GPR")
    except Exception as e:
        print("GPR 건너뜀:", e)
    print(f"흐름 글자 이름 {len(names)}개")
    return {"names": list(names.keys())}


def rolling_png(path: Path) -> dict:
    """카톡 '롤링 학습검증.png'(컨테이너선 · D+6 · Train 48 · 19창 + 최종 Test) 위 패널 선을 판독해 월별 값과 창별 WAPE(근사)를 만든다.
    x·y 보정: 검정 실제선과 마스터 실제값의 상관을 최대화(≈0.998). 아래 패널 막대 위치로 창 구간을 확인(Validation 2019-10부터 3개월 간격)."""
    from PIL import Image
    if not path.exists():
        print("롤링 그림 없음:", path)
        return {}
    im = np.asarray(Image.open(path).convert("RGB")).astype(int)
    a = im[333:516]
    def mask(c, tol):
        return (abs(a[..., 0] - c[0]) < tol) & (abs(a[..., 1] - c[1]) < tol) & (abs(a[..., 2] - c[2]) < tol)
    M = {"actual": a.max(-1) < 70, "val": mask((31, 119, 180), 40), "test": mask((218, 165, 32), 40), "fc": mask((200, 30, 40), 45)}
    act = master("컨테이너선")["수주용량"].astype(float)
    act = act[act.index <= "2026-08"]
    months = pd.period_range("2013-01", "2027-01", freq="M").astype(str).tolist()
    def ys(m, x):
        x = int(round(x))
        if x < 0 or x >= m.shape[1]:
            return np.nan
        r = np.where(m[:, x])[0]
        return r.mean() if len(r) else np.nan
    best = None
    for x0 in np.arange(130, 148, .5):
        for pm in np.arange(8.80, 9.00, .01):
            yb = np.array([ys(M["actual"], x0 + months.index(mm) * pm) for mm in act.index])
            ok = ~np.isnan(yb) & ~np.isnan(act.values)
            if ok.sum() < 100:
                continue
            r = abs(np.corrcoef(yb[ok], act.values[ok])[0, 1])
            if best is None or r > best[0]:
                best = (r, x0, pm)
    r, x0, pm = best
    yb = np.array([ys(M["actual"], x0 + months.index(mm) * pm) for mm in act.index])
    ok = ~np.isnan(yb) & ~np.isnan(act.values)
    A = np.vstack([yb[ok], np.ones(ok.sum())]).T
    coef, *_ = np.linalg.lstsq(A, act.values[ok], rcond=None)
    out = {"months": months, "actual": [None if pd.isna(v) else float(v) for v in act.reindex(months).values], "fitR": round(float(r), 4)}
    for k in ("val", "test", "fc"):
        vals = []
        for i in range(len(months)):
            y = ys(M[k], x0 + i * pm)
            vals.append(None if np.isnan(y) else float(round(max(0., coef[0] * y + coef[1]))))
        out[k] = vals
    idx = {m: i for i, m in enumerate(months)}
    def score(ms, key):
        pr = [(out[key][idx[m]], out["actual"][idx[m]]) for m in ms if out[key][idx[m]] is not None and out["actual"][idx[m]] is not None]
        if not pr:
            return None
        e = [p - y for p, y in pr]; ys_ = [y for _, y in pr]
        wape = 100 * sum(abs(v) for v in e) / sum(ys_)
        smape = 100 * float(np.mean([0 if (abs(p) + abs(y)) == 0 else 2 * abs(p - y) / (abs(p) + abs(y)) for p, y in pr]))
        rmse = float(np.sqrt(np.mean(np.square(e))))
        return {"wape": round(wape, 1), "smape": round(smape, 1), "rmse": round(rmse), "n": len(pr)}
    wins = []
    v0 = pd.Period("2019-10", "M")
    for k in range(19):
        vs = v0 + 3 * k
        ms = pd.period_range(vs, vs + 11, freq="M").astype(str).tolist()
        wins.append({"train": [str(vs - 53), str(vs - 6)], "val": [str(vs), str(vs + 11)], **score(ms, "val")})
    test = {"train": ["2021-04", "2025-03"], "val": ["2025-09", "2026-08"], **score(pd.period_range("2025-09", "2026-08", freq="M").astype(str).tolist(), "test")}
    allv = score(pd.period_range("2019-10", "2025-03", freq="M").astype(str).tolist(), "val")
    # 조장 기준(10/12): 창마다 12개월을 3개월씩 묶은 '분기 누적' sMAPE → Score = Mean + 1.0 × Std (창 간)
    def qsmape(ms, key):
        vals = []
        for q in range(0, len(ms), 3):
            blk = ms[q:q + 3]
            pr = [(out[key][idx[m]], out["actual"][idx[m]]) for m in blk if out[key][idx[m]] is not None and out["actual"][idx[m]] is not None]
            if len(pr) < 3:
                continue
            P_, A_ = sum(p for p, _ in pr), sum(a for _, a in pr)
            vals.append(0.0 if P_ + A_ == 0 else 200 * abs(P_ - A_) / (abs(P_) + abs(A_)))
        return round(float(np.mean(vals)), 1) if vals else None
    for x in wins:
        x["qsmape"] = qsmape(pd.period_range(x["val"][0], x["val"][1], freq="M").astype(str).tolist(), "val")
    test["qsmape"] = qsmape(pd.period_range("2025-09", "2026-08", freq="M").astype(str).tolist(), "test")
    qv = [x["qsmape"] for x in wins if x["qsmape"] is not None]
    # 조장 공지(10/12 11:51): 표준편차 ddof=0 · Score = Mean + λ₁·Std + λ₂·Peak Penalty (기본 λ₁=λ₂=1.0)
    score = {"mean": round(float(np.mean(qv)), 1), "std": round(float(np.std(qv, ddof=0)), 1)}
    score["peak"] = peak_penalty(out, wins)
    score["score_ms"] = round(score["mean"] + 1.0 * score["std"], 1)
    score["score"] = round(score["score_ms"] + 1.0 * score["peak"]["penalty"], 1)
    qa = qv + ([test["qsmape"]] if test["qsmape"] is not None else [])
    score["all_mean"], score["all_std"], score["n_val"], score["n_all"] = round(float(np.mean(qa)), 1), round(float(np.std(qa, ddof=0)), 1), len(qv), len(qa)
    print(f"분기 누적 sMAPE: 검증 창 {len(qv)}개 Mean {score['mean']} Std {score['std']} Peak {score['peak']['penalty']} → Score {score['score']} · 검증+Test Mean±Std {score['all_mean']}±{score['all_std']} · Test {test['qsmape']}")
    w = sorted(x["wape"] for x in wins)
    cvar = round(float(np.mean(w[-int(np.ceil(len(w) * .2)):])), 1)
    print(f"롤링 그림 판독 상관 {r:.4f} · 검증 전체 WAPE {allv['wape']} sMAPE {allv['smape']} · 창 WAPE CVaR20 {cvar} · Test WAPE {test['wape']}")
    out.update({"windows": wins, "testWin": test, "overall": allv, "cvar20": cvar, "score": score})
    return out


def peak_penalty(out: dict, wins: list) -> dict:
    """조장 공지(10/12) 피크 벌점 — 전체 Validation OOF(월별 검증 예측을 이은 선)에서 실제·예측 피크를 찾아 ±3개월 일대일 매칭.
    선행 1개월당 1%p · 후행 1개월당 2%p · 미탐지 8%p · 가짜 피크 8%p → 합계 ÷ (실제 피크 수 + 가짜 피크 수), 피크가 없으면 0.
    피크 기준은 첫 창 Train 실제값 분포로 미리 정함(높이 = 75백분위, 돌출도 = 표준편차의 0.5배 — 팀 노트북 확정 전 가정)."""
    from scipy.signal import find_peaks
    months = out["months"]; idx = {m: i for i, m in enumerate(months)}
    tr = pd.period_range(wins[0]["train"][0], wins[0]["train"][1], freq="M").astype(str).tolist()
    ta = np.array([out["actual"][idx[m]] for m in tr if m in idx and out["actual"][idx[m]] is not None], float)
    h, prom = float(np.quantile(ta, .75)), float(np.std(ta) * .5)
    vm = [m for m in months if out["val"][idx[m]] is not None and out["actual"][idx[m]] is not None]
    A = np.array([out["actual"][idx[m]] for m in vm], float); P = np.array([out["val"][idx[m]] for m in vm], float)
    pa, _ = find_peaks(A, height=h, prominence=prom); pp, _ = find_peaks(P, height=h, prominence=prom)
    pairs = sorted(((abs(int(q) - int(a)), int(a), int(q)) for a in pa for q in pp if abs(int(q) - int(a)) <= 3))
    ua, up, match = set(), set(), []
    for d, a, q in pairs:
        if a in ua or q in up:
            continue
        ua.add(a); up.add(q); match.append((a, q))
    pen, rows = 0.0, []
    for a, q in match:
        d = q - a; c = (2.0 * d) if d > 0 else (1.0 * -d)
        pen += c; rows.append({"a": vm[a], "p": vm[q], "d": d, "c": c})
    miss = [vm[a] for a in pa if int(a) not in ua]; false = [vm[q] for q in pp if int(q) not in up]
    pen += 8.0 * (len(miss) + len(false))
    n = len(pa) + len(false)
    return {"penalty": round(pen / n, 2) if n else 0.0, "sum": round(pen, 1), "n_actual": int(len(pa)), "n_pred": int(len(pp)),
            "miss": miss, "false": false, "match": rows, "height": round(h), "prom": round(prom),
            "actualPeaks": [vm[a] for a in pa], "predPeaks": [vm[q] for q in pp], "months": [vm[0], vm[-1]]}



def topn(pdf) -> dict:
    """3.2 Top-N 변수군과 기본 모형 비교: 막대 높이를 최저 막대 대비 비율로 읽는다(눈금 간격과 무관). 금색 = 강건성 우선 선택."""
    out = {}
    for ship, first in FIRST_PAGE.items():
        a = np.asarray(render(pdf, first + 9, 3)).astype(int)
        H, W, _ = a.shape
        blue = (abs(a[..., 0] - 76) < 24) & (abs(a[..., 1] - 120) < 24) & (abs(a[..., 2] - 168) < 24)
        gold = (abs(a[..., 0] - 212) < 26) & (abs(a[..., 1] - 160) < 30) & (abs(a[..., 2] - 30) < 40)
        bar = blue | gold
        cols = bar.sum(0) > 20
        runs, st = [], None
        for x in range(W):
            if cols[x] and st is None:
                st = x
            if not cols[x] and st is not None:
                if x - st > 8:
                    runs.append((st, x))
                st = None
        hs, chosen = [], None
        for k, (s_, e) in enumerate(runs):
            ys = np.where(bar[:, (s_ + e) // 2])[0]
            hs.append(ys.max() - ys.min())
            if gold[:, (s_ + e) // 2].sum() > 20:
                chosen = k
        mn = min(hs)
        n = len(hs)
        labels = [f"상위 {8 + k}개" for k in range(n - 1)] + ["전체 통과"]
        out[ship] = {"rel": [round(float(h / mn), 4) for h in hs], "labels": labels, "chosen": chosen}
        print(f"{ship}: Top-N 막대 {n}개 · 선택 {labels[chosen] if chosen is not None else '?'}")
    return out


def trim_weak(paths: dict) -> None:
    """약신호 막대 그림에서 빈 세로 띠(흰 열이 30px 넘게 이어지는 구간)를 12px로 줄인다."""
    from PIL import Image
    for ship, d in paths.items():
        src = OUT.parent / d["weak"]
        im = Image.open(src).convert("RGB"); a = np.asarray(im).astype(int)
        white = (a.min(-1) > 238).all(0)
        keep, run = [], []
        for x, w in enumerate(white):
            if w:
                run.append(x)
            else:
                if len(run) > 30:
                    keep += run[:6] + run[-6:]
                else:
                    keep += run
                run = []
                keep.append(x)
        keep += run[:6]
        b = a[:, keep]
        rows = ~(b.min(-1) > 238).all(1)
        ys = np.where(rows)[0]
        b = b[max(0, ys.min() - 6):ys.max() + 6]
        name = src.name.replace("_weak", "_weakt")
        Image.fromarray(b.astype("uint8")).save(src.parent / name, "WEBP", quality=85, method=6)
        d["weakt"] = f"story/img/{name}"
        # 0% 행을 잘라 낸 요약판 — 필터2 마지막 단계(아래 절반)에 쓴다
        from trim_weakc import trim_one
        cname = name.replace("_weakt", "_weakc")
        r = trim_one(src.parent / name, src.parent / cname)
        d["weakc"] = f"story/img/{cname}"
        d["weakZero"] = r["zero"]
        d["weakShown"] = r["shown"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pdf", required=True)
    ap.add_argument("--cluster-report", type=Path, default=Path.home() / "Documents" / "카카오톡 받은 파일" / "군집분석_전체과정_보고서.html")
    args = ap.parse_args()
    pdf = pdfium.PdfDocument(args.pdf)
    data = {
        "ships": SHIPS, "unit": UNIT, "reducedN": REDUCED_N,
        "features": {s: feature_block(s) for s in SHIPS},
        "cluster": clusters(),
        "figs": (lambda f: (trim_weak(f), f)[1])(crop_figures(pdf)),
        "topn": topn(pdf),
        "robust": robustness(pdf),
        "holdout": holdout(pdf),
        "explored": explored(),
        "rollpng": rolling_png(Path.home() / "Documents" / "카카오톡 받은 파일" / "롤링 학습검증.png"),
        "windows": windows(),
        # 민규 10/07 노트북 Test 월별 WAPE (#선박수주예측팀 10/07 16:33 글, 아카이브 A19)
        "wapeReported": {"컨테이너선": 53.09, "벌크선": 74.51, "유조선": 76.04},
        "freightScan": freight_scan(),
        "regimes": regimes(args.cluster_report),
        "covers": covers(),
        # 1.2 초기 피라미드 변수 수: 도판 맨 아랫줄 셀 수(픽셀). 축소 피라미드로 대조하면 컨테이너·벌크는 정확, 나머지는 ±2
        "initialN": {"컨테이너선": 48, "벌크선": 42, "유조선": 41, "가스 운반선": 49, "케미컬 탱커": 42},
        "initialExact": ["컨테이너선", "벌크선"],
        "collab": {"commits": 55, "archivePosts": 25, "teamFeed": 45, "driveFiles": 422},
        "source": "팀 마스터 테이블(10/06) · 정훈 군집 분석(10/07) · UI팀 분석 파이프라인 PDF(10/09 저장 출력, D+3 회고 실험)",
    }
    (OUT / "data.js").write_text("window.STORY=" + json.dumps(data, ensure_ascii=False, separators=(",", ":")) + ";\n",
                                 encoding="utf-8")
    for s, r in data["robust"].items():
        print(f"{s}: 창 {len(r['rmsse'])}개 · 가중 RMSSE {r['weighted']} · 평균 {r['mean']} · CVaR(최악 20%) {r['cvar20']}")
    print("저장:", OUT / "data.js")


if __name__ == "__main__":
    main()
