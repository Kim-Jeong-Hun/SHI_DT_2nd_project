"""Ship Pulse 운영 파이프라인 노드 — 팀 서비스의 선종별 최종 설정으로 다시 학습 · 검증 · 예측한다.

순서(선종마다): 마스터 테이블 → CCF 시차 변수 → 변수 거르기(약한 변수 · VIF 10 · 퍼뮤테이션 Top-N)
→ 롤링 검증(검증 3개월 × 17창, Sliding · Expanding · Adaptive) → Test 24개월 → 다음 분기 예측 · 90% 구간.
결측은 앞 값으로만 잇는다(뒤 값을 당겨 쓰지 않음). 모든 변수는 목표월보다 3개월 이상 앞선 값이다.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import numpy as np
import pandas as pd

from . import spec as SP

ROOT = Path(os.environ.get("SHI_PROJECT_DIR", Path(__file__).resolve().parents[4]))
OUT = ROOT / "data" / "07_model_output" / "ship_pulse"
MODELS = ROOT / "data" / "06_models" / "ship_pulse"
META_COLS = {"기준월", "수주용량", "수주용량단위", "수주정보시차(개월)", "수주정보가용근거"}
P = lambda s: pd.Period(s, "M")


def _master_dir() -> Path:
    for d in (os.environ.get("SHIP_PULSE_MASTER_DIR"), ROOT / "data" / "01_raw" / "ship_pulse" / "master",
              Path(os.environ.get("SHIP_ORDERS_REPO", "/nonexistent")) / "ship_pulse_master",   # Render 이미지(/app/team)
              ROOT / "deploy" / "render" / "team" / "ship_pulse_master"):
        if d and Path(d).exists():
            return Path(d)
    raise FileNotFoundError("Ship Pulse 마스터 테이블 폴더가 없습니다 — SHIP_PULSE_MASTER_DIR 를 지정하세요")


# ───────── 1. 입력 ─────────
def load_master(vid: str) -> pd.DataFrame:
    name = SP.SHIPS[vid]["name"]
    df = pd.read_csv(_master_dir() / f"마스터테이블({name}).csv")
    df.index = pd.PeriodIndex(df["기준월"], freq="M")
    num = df.drop(columns=[c for c in df.columns if c in META_COLS]).apply(pd.to_numeric, errors="coerce")
    num = num.loc[:, num.notna().mean() >= 0.8]                   # 대부분 비어 있는 열은 쓰지 않는다
    out = num.ffill()                                             # 앞 값으로만 잇는다(미래 값 사용 없음)
    out.insert(0, "y", pd.to_numeric(df["수주용량"], errors="coerce"))
    return out


# ───────── 2. CCF: 변수마다 3~9개월 전 중 상관이 가장 큰 시차 하나 ─────────
def lag_features(master: pd.DataFrame) -> dict:
    """변수마다 (1) 수준: 3~9개월 전 중 하나, (2) 변화량: a개월 전 − b개월 전(a=3~6, b=a+1~a+6) 중 하나를 고른다(Test 이전 Spearman)."""
    idx = pd.period_range(master.index.min(), master.index.max() + SP.HORIZON, freq="M")   # 예측할 달 행을 미리 만든다
    master = master.reindex(idx)
    y = master["y"]
    fit = (master.index <= P(SP.TEST[0]) - 1) & y.notna().to_numpy()
    yf = y[fit]
    cols, info = {}, []

    def score(x):
        x = x[fit]
        m = x.notna().to_numpy()
        if m.sum() < 24 or x[m].std() == 0:
            return -1
        return abs(x[m].corr(yf[m], method="spearman"))

    for c in master.columns[1:]:
        lv = max(((score(master[c].shift(L)), L) for L in range(SP.HORIZON, SP.HORIZON + SP.MAX_EXTRA_LAG + 1)))
        if lv[0] > 0:
            key = f"{c} · {lv[1]}개월 전"
            cols[key] = master[c].shift(lv[1]); info.append({"변수": key, "원변수": c, "시차": lv[1], "rho": round(float(lv[0]), 3)})
        ch = max(((score(master[c].shift(a) - master[c].shift(b)), a, b) for a in range(SP.HORIZON, SP.HORIZON + 4)
                  for b in range(a + 1, a + 7)))
        if ch[0] > 0:
            key = f"{c} 변화 · {ch[1]}→{ch[2]}개월"
            cols[key] = master[c].shift(ch[1]) - master[c].shift(ch[2]); info.append({"변수": key, "원변수": c, "시차": f"{ch[1]}→{ch[2]}", "rho": round(float(ch[0]), 3)})
    X = pd.DataFrame(cols, index=master.index)
    return {"X": X, "y": y, "ccf": info}


# ───────── 3. 변수 거르기 ─────────
def _vif_filter(X: pd.DataFrame) -> list[str]:
    keep = list(X.columns)
    Z = (X - X.mean()) / X.std(ddof=0).replace(0, 1)
    while len(keep) > 2:
        v = []
        for c in keep:
            o = [k for k in keep if k != c]
            A = np.c_[np.ones(len(Z)), Z[o].to_numpy()]
            coef, *_ = np.linalg.lstsq(A, Z[c].to_numpy(), rcond=None)
            res = Z[c].to_numpy() - A @ coef
            r2 = 1 - res.var() / max(Z[c].var(ddof=0), 1e-12)
            v.append(1 / max(1 - r2, 1e-9))
        i = int(np.argmax(v))
        if v[i] <= SP.VIF_MAX:
            break
        keep.pop(i)
    return keep


def select_features(lagged: dict, vid: str) -> dict:
    from sklearn.feature_selection import mutual_info_regression
    from sklearn.inspection import permutation_importance

    X, y = lagged["X"], lagged["y"]
    pre = (X.index <= P(SP.TEST[0]) - 1) & X.notna().all(axis=1).to_numpy() & y.notna().to_numpy()
    Xp, yp = X[pre], y[pre]
    steps = {"CCF": X.shape[1]}
    # 3-1 약한 변수: Pearson · Spearman · 상호정보량이 함께 하위 30%인 창이 2/3 넘으면 제거
    ends = [P(SP.LAST_VAL_START) - SP.TRAIN_GAP - 3 * k for k in range(6)]
    weak = pd.Series(0, index=X.columns)
    for e in ends:
        w = Xp[(Xp.index <= e) & (Xp.index > e - 48)]
        if len(w) < 24:
            continue
        yw = yp.loc[w.index]
        a = w.corrwith(yw).abs().rank(pct=True)
        b = w.corrwith(yw, method="spearman").abs().rank(pct=True)
        c = pd.Series(mutual_info_regression(w.fillna(0), yw, random_state=0), index=w.columns).rank(pct=True)
        weak += ((a <= .3) & (b <= .3) & (c <= .3)).astype(int)
    keep = [c for c in X.columns if weak[c] <= SP.WEAK_SHARE * len(ends)]
    steps["선형·단조"] = len(keep)
    # 3-2 다중공선성: VIF 10 이하가 될 때까지 가장 큰 것부터 제거
    keep = _vif_filter(Xp[keep])
    steps["VIF"] = len(keep)
    # 3-3 퍼뮤테이션 중요도 Top-N (최종 모형으로, Test 직전 12개월에서)
    cut = P(SP.TEST[0]) - 13
    tr, ho = Xp.index <= cut, Xp.index > cut
    est = make_model(SP.SHIPS[vid]["model"]).fit(Xp.loc[tr, keep], yp[tr])
    pi = permutation_importance(est, Xp.loc[ho, keep], yp[ho], n_repeats=20, random_state=0, scoring="neg_mean_absolute_error")
    imp = pd.Series(pi.importances_mean, index=keep).sort_values(ascending=False)
    top = list(imp.index[: SP.SHIPS[vid]["n_features"]])
    steps["Top-N"] = len(top)
    pos = imp[top].clip(lower=0)
    share = (pos / pos.sum() * 100).round(2) if pos.sum() > 0 else pos
    return {"features": top, "steps": steps, "importance": [[k, float(share[k])] for k in top]}


# ───────── 4. 모형 ─────────
from sklearn.base import BaseEstimator, RegressorMixin, clone


class _Avg(RegressorMixin, BaseEstimator):
    """두 모형 동일가중 평균(Tweedie 회귀 + XGBoost) — sklearn 호환."""

    def __init__(self, a=None, b=None):
        self.a, self.b = a, b

    def fit(self, X, y):
        self.a_, self.b_ = clone(self.a).fit(X, y), clone(self.b).fit(X, y)
        return self

    def predict(self, X):
        return (np.asarray(self.a_.predict(X)).ravel() + np.asarray(self.b_.predict(X)).ravel()) / 2


class _Flat(RegressorMixin, BaseEstimator):
    """PLS 처럼 2차원 예측을 내는 모형을 1차원으로."""

    def __init__(self, m=None):
        self.m = m

    def fit(self, X, y):
        self.m_ = clone(self.m).fit(X, y)
        return self

    def predict(self, X):
        return np.asarray(self.m_.predict(X)).ravel()


def make_model(kind: str):
    from sklearn.cross_decomposition import PLSRegression
    from sklearn.linear_model import HuberRegressor, QuantileRegressor, TweedieRegressor
    from sklearn.pipeline import make_pipeline
    from sklearn.preprocessing import StandardScaler
    from xgboost import XGBRegressor

    xgb = lambda: XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
                               min_child_weight=2, random_state=0, n_jobs=1, verbosity=0)
    if kind == "tweedie_xgb":
        return _Avg(make_pipeline(StandardScaler(), TweedieRegressor(power=1.5, link="log", alpha=1.0, max_iter=3000)), xgb())
    if kind == "xgboost":
        return xgb()
    if kind == "pls":
        return _Flat(make_pipeline(StandardScaler(), PLSRegression(n_components=2)))
    if kind == "quantile":
        return make_pipeline(StandardScaler(), QuantileRegressor(quantile=0.5, alpha=0.0, solver="highs"))
    if kind == "huber":
        return make_pipeline(StandardScaler(), HuberRegressor(max_iter=2000))
    raise ValueError(kind)


# ───────── 5. 창 굴리기 ─────────
def _fit_predict(kind, X, y, ts, te, months):
    m = (X.index >= ts) & (X.index <= te) & y.notna().to_numpy() & X.notna().all(axis=1).to_numpy()
    if m.sum() < 12:
        return None, None
    est = make_model(kind).fit(X[m], y[m])
    Xq = X.loc[months]
    return est, np.clip(est.predict(Xq), 0, None)


def _train_len(vid, X, y, vs, first):
    """학습 길이: Sliding 은 고정, Adaptive 는 직전 3개월(이미 아는 구간) 성적이 가장 좋은 길이."""
    kind, (s, L) = SP.SHIPS[vid]["model"], SP.SHIPS[vid]["strategy"]
    if s == "S":
        return L
    if s == "E":
        return None
    te = vs - SP.TRAIN_GAP
    inner = pd.period_range(te - 2, te, freq="M")
    best = None
    for Lk in L:
        _, p = _fit_predict(kind, X, y, max(te - 3 - Lk + 1, first), te - 3, inner)
        if p is None:
            continue
        e = np.nanmean(np.abs(p - y.loc[inner].to_numpy()))
        if best is None or e < best[0]:
            best = (e, Lk)
    return best[1] if best else L[-1]


def _windows(vid, X, y, starts, label):
    kind = SP.SHIPS[vid]["model"]
    first = X.dropna().index.min()
    rows, ests = [], None
    for k, vs in enumerate(starts):
        te = vs - SP.TRAIN_GAP
        L = _train_len(vid, X, y, vs, first)
        ts = first if L is None else max(te - L + 1, first)
        months = pd.period_range(vs, vs + SP.VAL_MONTHS - 1, freq="M")
        ests, p = _fit_predict(kind, X, y, ts, te, months)
        for mth, pv in zip(months, p):
            rows.append({"구간": label, "창": k + 1, "학습시작": str(ts), "학습끝": str(te), "학습개월": int((te - ts).n + 1),
                         "월": str(mth), "실제": float(y.get(mth, np.nan)), "예측": float(pv)})
    return pd.DataFrame(rows)


def _metrics(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["실제"])
    e = d["예측"] - d["실제"]
    blk = d.groupby("창").agg(p=("예측", "sum"), a=("실제", "sum"))
    qerr = (blk["p"] - blk["a"]).abs() / blk["a"].replace(0, np.nan)
    pk = d.groupby("창").apply(lambda g: abs(int(np.argmax(g["예측"].to_numpy())) - int(np.argmax(g["실제"].to_numpy()))), include_groups=False)
    ase = (blk["p"] - blk["a"]).abs()                              # ASE: 창(3개월)마다 |Σ(실제−예측)| — 팀 최종 지표
    return {"ase": float(ase.mean()), "ase_std": float(ase.std()), "score": float(ase.mean() + ase.std()),
            "mae": float(e.abs().mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "relative_error": float(e.abs().sum() / max(d["실제"].abs().sum(), 1e-9) * 100),
            "quarter_error": float(qerr.mean() * 100), "quarter_error_std": float(qerr.std() * 100),
            "peak_timing_error": float(pk.mean()), "months": int(len(d))}


def rolling_validation(lagged: dict, selected: dict, vid: str) -> dict:
    X, y = lagged["X"][selected["features"]], lagged["y"]
    N = SP.SHIPS[vid]["windows"]
    starts = [P(SP.LAST_VAL_START) - SP.VAL_MONTHS * (N - 1 - k) for k in range(N)]
    df = _windows(vid, X, y, starts, "Validation")
    return {"table": df.to_dict("records"), "metrics": _metrics(df)}


def test_evaluation(lagged: dict, selected: dict, vid: str) -> dict:
    X, y = lagged["X"][selected["features"]], lagged["y"]
    a, b = P(SP.TEST[0]), P(SP.TEST[1])
    starts = [a + 3 * k for k in range(((b - a).n + 1) // 3)]
    df = _windows(vid, X, y, starts, "Test")
    base = df.assign(예측=[float(y.get(P(r) - 6, np.nan)) for r in df["월"]])   # 기준선: 예측 시점에 알던 6개월 전 실적
    return {"table": df.to_dict("records"), "metrics": _metrics(df), "baseline": _metrics(base.dropna(subset=["예측"]))}


# ───────── 6. 다음 분기 예측 · 90% 구간 ─────────
def forecast(lagged: dict, selected: dict, val: dict, test: dict, vid: str) -> dict:
    X, y = lagged["X"][selected["features"]], lagged["y"]
    kind = SP.SHIPS[vid]["model"]
    last = y.dropna().index.max()                                  # 마지막으로 공표된 수주 실적 월
    first = X.dropna().index.min()
    vs = last + 1 + SP.TRAIN_GAP - 1
    L = _train_len(vid, X, y, vs + 1, first)
    ts = first if L is None else max(last - L + 1, first)
    horizon = pd.period_range(last + 1, X.dropna().index.max(), freq="M")
    est, p = _fit_predict(kind, X, y, ts, last, horizon)
    MODELS.mkdir(parents=True, exist_ok=True)
    import joblib
    joblib.dump({"model": est, "features": selected["features"], "train": [str(ts), str(last)]}, MODELS / f"{vid}.joblib")
    pred = dict(zip(map(str, horizon), map(float, p)))
    year = str(last.year if last.month < 10 else last.year)
    months = [f"{year}-{m:02d}" for m in range(7, 13)]
    monthly = [{"month": m, "value": float(y.get(P(m))) if pd.notna(y.get(P(m), np.nan)) else pred.get(m), "kind": "실적" if pd.notna(y.get(P(m), np.nan)) else "예측"}
               for m in months]
    q3 = sum(v["value"] or 0 for v in monthly[:3]); q4 = sum(v["value"] or 0 for v in monthly[3:])
    q4m = monthly[3:]
    peak = max(q4m, key=lambda v: v["value"] or -1)["month"]
    # 90% 블록 conformal: 검증 · Test 절대오차를 겹치지 않는 3개월 묶음의 최댓값으로 → ceil((n+1)·0.9) 번째
    errs = pd.DataFrame(val["table"] + test["table"]).dropna(subset=["실제"])
    errs["abs"] = (errs["예측"] - errs["실제"]).abs()
    scores = np.sort(errs.groupby(["구간", "창"])["abs"].max().to_numpy())
    r = scores[min(len(scores) - 1, math.ceil((len(scores) + 1) * 0.9) - 1)] if len(scores) else float("nan")
    return {"vesselId": vid, "lastActual": str(last), "trainRange": [str(ts), str(last)], "trainMonths": int((last - ts).n + 1),
            "monthly": monthly, "q3": q3, "q4": q4, "quarterChange": round((q4 / q3 - 1) * 100, 1) if q3 else None,
            "peakMonth": f"{int(peak[5:])}월", "conformalRadius90": float(r), "conformalCalibrationSize": int(len(scores))}


def assemble_vessel(vid: str, lagged: dict, selected: dict, val: dict, test: dict, fc: dict) -> dict:
    ref = SP.REFERENCE["vessels"][vid]
    s = SP.SHIPS[vid]
    return {"vesselId": vid, "vesselName": s["name"], "unit": s["unit"], "model": s["model"],
            "strategy": s["strategy"][0] + " " + (",".join(map(str, s["strategy"][1])) if isinstance(s["strategy"][1], list) else str(s["strategy"][1])),
            "ccf": lagged["ccf"], "selection": selected, "validation": val, "test": test, "forecast": fc,
            "reference": {k: ref[k] for k in ("model", "strategy", "featureCount", "q3", "q4", "quarterChange", "peakMonth",
                                             "validationMae", "testMae", "testRelativeError", "peakTimingError", "conformalRadius90")}}


# ───────── 7. 내보내기 · MLflow ─────────
def export_results(*vessels: dict) -> dict:
    """선종 결과를 한 파일로 — Ship Pulse notebookForecasts 형식(서비스가 그대로 읽을 수 있게)과 팀 값 대조표."""
    OUT.mkdir(parents=True, exist_ok=True)
    full = {v["vesselId"]: v for v in vessels}
    (OUT / "results.json").write_text(json.dumps(full, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    nb = {}
    for vid, v in full.items():
        f, t = v["forecast"], v["test"]["metrics"]
        nb[vid] = {"vesselId": vid, "vesselName": v["vesselName"], "unit": v["unit"],
                   "monthly": [{"month": m["month"], "value": round(m["value"] or 0, 1)} for m in f["monthly"]],
                   "q3": round(f["q3"], 1), "q4": round(f["q4"], 1), "quarterChange": f["quarterChange"], "peakMonth": f["peakMonth"],
                   "model": v["reference"]["model"], "strategy": v["reference"]["strategy"], "featureCount": len(v["selection"]["features"]),
                   "validationMae": round(v["validation"]["metrics"]["mae"], 2), "testMae": round(t["mae"], 2),
                   "testRelativeError": round(t["relative_error"], 2), "peakTimingError": round(t["peak_timing_error"], 2),
                   "conformalRadius90": round(f["conformalRadius90"], 2), "conformalCalibrationSize": f["conformalCalibrationSize"],
                   "drivers": [{"label": k, "share": s} for k, s in v["selection"]["importance"][:4]]}
    (OUT / "notebook_forecasts.json").write_text(json.dumps(nb, ensure_ascii=False, indent=1), encoding="utf-8")
    cmp_ = [{"선종": v["vesselName"], "재현_TestMAE": round(v["test"]["metrics"]["mae"], 1), "팀_TestMAE": v["reference"]["testMae"],
             "재현_Test상대오차": round(v["test"]["metrics"]["relative_error"], 1), "팀_Test상대오차": v["reference"]["testRelativeError"],
             "재현_4분기": round(v["forecast"]["q4"], 1), "팀_4분기": v["reference"]["q4"]} for v in full.values()]
    (OUT / "comparison.json").write_text(json.dumps(cmp_, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"results": str(OUT / "results.json"), "vessels": list(full)}


def track_mlflow(_export=None) -> dict:
    """results.json · 저장 모델을 MLflow 실험 'ship_pulse' 에 기록하고 선종별 모델을 등록(alias production)한다.

    MLFLOW_TRACKING_URI 가 없으면 건너뛴다. 같은 결과(SHA-256)는 다시 기록하지 않는다.
    """
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        return {"mlflow": "skipped (MLFLOW_TRACKING_URI 없음)"}
    import hashlib

    import joblib
    import mlflow
    from mlflow import MlflowClient

    raw = (OUT / "results.json").read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    full = json.loads(raw.decode("utf-8"))
    mlflow.set_tracking_uri(uri)
    exp = mlflow.set_experiment(os.environ.get("MLFLOW_SHIP_PULSE_EXPERIMENT", "ship_pulse"))
    if len(mlflow.search_runs([exp.experiment_id], filter_string=f"tags.results_sha = '{digest}'", max_results=1)):
        return {"mlflow": "already logged", "sha": digest}
    client, registered = MlflowClient(), []
    with mlflow.start_run(run_name="Ship Pulse 운영 재학습") as parent:
        mlflow.set_tags({"results_sha": digest, "pipeline": "ship_pulse", "reference": SP.REFERENCE["source"]})
        mlflow.log_dict(json.loads((OUT / "comparison.json").read_text(encoding="utf-8")), "comparison.json")
        for vid, v in full.items():
            with mlflow.start_run(run_name=v["vesselName"], nested=True):
                mlflow.set_tags({"pipeline": "ship_pulse", "vessel": vid})
                mlflow.log_params({"model": v["model"], "strategy": v["strategy"], "n_features": len(v["selection"]["features"]),
                                   "horizon": SP.HORIZON, "val_months": SP.VAL_MONTHS, "windows": SP.SHIPS[vid]["windows"],
                                   "test": "~".join(SP.TEST), "train_range": "~".join(v["forecast"]["trainRange"]),
                                   "features": " | ".join(v["selection"]["features"])[:6000]})
                m = {f"val_{k}": x for k, x in v["validation"]["metrics"].items()}
                m |= {f"test_{k}": x for k, x in v["test"]["metrics"].items()}
                m |= {f"baseline_{k}": x for k, x in v["test"]["baseline"].items()}
                f = v["forecast"]
                m |= {"q3": f["q3"], "q4": f["q4"], "q4_change_pct": f["quarterChange"] or 0, "conformal_radius_90": f["conformalRadius90"],
                      "ref_test_relative_error": v["reference"]["testRelativeError"], "ref_q4": v["reference"]["q4"]}
                mlflow.log_metrics({k: float(x) for k, x in m.items() if isinstance(x, (int, float)) and x == x})
                mlflow.log_dict(v, f"{vid}/result.json")
                bundle = joblib.load(MODELS / f"{vid}.joblib")
                import mlflow.sklearn as msk
                info = msk.log_model(bundle["model"], name=f"ship_pulse_{vid}", serialization_format="cloudpickle",
                                     registered_model_name=f"ship_pulse_{vid}")
                try:
                    client.set_registered_model_alias(f"ship_pulse_{vid}", "production", info.registered_model_version)
                except Exception:
                    pass
                registered.append(f"ship_pulse_{vid} v{info.registered_model_version}")
    return {"mlflow": "logged", "run_id": parent.info.run_id, "registered": registered}
