"""Ship Pulse 운영 파이프라인 — 서비스(김정훈 님 대시보드)와 같은 모델 · 같은 데이터로 재학습한다.

기준은 대시보드다.
  · 모델 사양 · 학습 코드 · 최신 마스터 데이터 = 서비스 런타임(mlops/deploy/render/custom_forecast.py · custom_runtime)
  · 공식 전망값 = 대시보드 데이터셋(frontend/src/data/notebookForecasts.ts → reference.json)
파이프라인은 그 모델로 Test 24개월을 다시 평가하고, 최신 데이터로 최종 모델을 재학습해 MLflow 에 등록한다.
산출물은 용도별로 나눈다.
  · retrained_forecasts.json  이 파이프라인이 재학습해 만든 전망(파이프라인의 공식 출력)
  · dashboard_reference.json  대시보드 기준값 사본(비교용 입력 · 모델 출력 아님)
  · comparison.json           둘의 월별 차이
과거 시점(Test · 7~12월 재현)은 기준월까지의 자료와 목표값만 학습한다 — 기준월 뒤 수주 실적은 쓰지 않는다.
"""
from __future__ import annotations

import importlib.util
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
LEAD = 6   # 서비스 런타임과 같다: 관측월 기준 6개월 뒤 수주(D+6)
VESSELS = 5


def _runtime_dir() -> Path:
    for d in (os.environ.get("SHIP_PULSE_RUNTIME_DIR"), ROOT / "deploy" / "render", ROOT / "vendor" / "ship_pulse_service"):
        if d and (Path(d) / "custom_forecast.py").exists() and (Path(d) / "custom_runtime").exists():
            return Path(d)
    raise FileNotFoundError("서비스 런타임(custom_forecast.py · custom_runtime)을 찾지 못했어요 — SHIP_PULSE_RUNTIME_DIR 지정")


def _runtime():
    d = _runtime_dir()
    spec = importlib.util.spec_from_file_location("ship_pulse_service_runtime", d / "custom_forecast.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, (d / "custom_runtime").resolve()


def _modeling(root: Path):
    """서비스 런타임의 ship_orders_forecasting 을 다른 이름(sp_service_sof)으로 불러온다.
    같은 이름의 예전 패키지(Drive 사본)가 먼저 잡히는 충돌을 막고, 저장된 모델을 다시 읽을 때도 같은 이름을 쓴다."""
    import sys
    if "sp_service_sof.modeling" not in sys.modules:
        pkg = root / "src" / "ship_orders_forecasting"
        spec = importlib.util.spec_from_file_location("sp_service_sof", pkg / "__init__.py", submodule_search_locations=[str(pkg)])
        mod = importlib.util.module_from_spec(spec)
        sys.modules["sp_service_sof"] = mod
        spec.loader.exec_module(mod)
        importlib.import_module("sp_service_sof.modeling")
    return sys.modules["sp_service_sof.modeling"]


def _fit(C, root, meta, derived, origin, asof):
    """서비스 런타임 fit_and_predict 와 같은 방식. asof=True 면 목표월이 기준월 이하인 행만 학습한다(과거 시점 평가 · 재현)."""
    if meta["name"] == "가스 운반선":
        C.enable_vecm_fallback_when_statsmodels_is_missing()
    model_for = _modeling(root).model_for

    f = meta["features"]
    y = pd.to_numeric(derived[C.TARGET], errors="coerce")
    tr = derived[f].copy()
    tr["__t"] = y.shift(-LEAD)
    last = y.dropna().index[-1]
    if asof:
        last = min(last, origin)
    tr = tr.loc[tr.index + pd.DateOffset(months=LEAD) <= last].dropna()
    if meta["window"]:
        tr = tr.tail(meta["window"])
    if len(tr) < 24:
        raise ValueError(f"{meta['name']} {origin:%Y-%m}: 학습 시계열 부족")
    x = tr[f].astype(float)
    steps = origin.to_period("M").ordinal - x.index[-1].to_period("M").ordinal
    if steps > 0:
        x.attrs["forecast_steps"] = steps
        x.attrs["known_future_exog"] = derived.loc[x.index[-1] + pd.DateOffset(months=1):origin, f].to_numpy(dtype=float)
    est = model_for(meta["specification"], 42).fit(x, tr["__t"].astype(float))
    return est, max(0.0, float(est.predict(derived.loc[[origin], f].astype(float))[0])), (str(x.index[0])[:7], str(x.index[-1])[:7])


def _asof(C, svc, origin):
    """기준월까지의 자료만 남긴 파생 피처 — 그 시점에 알 수 있던 정보 조건.
    예전에는 기준월+2개월까지 남겨, 그때 아직 공표되지 않은 수주 실적이 학습에 섞였다(PR #13 리뷰 P1)."""
    fr = svc["frame"].loc[:origin]
    return C.add_derived_features(C.extend_raw(fr, origin), svc["meta"]["features"])


def load_service(vid: str) -> dict:
    C, root = _runtime()
    frame, meta, src = C.load_data(root, vid)
    last = pd.to_numeric(frame[C.TARGET], errors="coerce").dropna().index[-1]
    derived = C.add_derived_features(C.extend_raw(frame, frame.index.max()), meta["features"])
    return {"vid": vid, "meta": meta, "source": src, "frame": frame, "derived": derived, "lastActual": last}


def _metrics(df: pd.DataFrame) -> dict:
    d = df.dropna(subset=["실제"])
    e = d["예측"] - d["실제"]
    blk = d.groupby("창").agg(p=("예측", "sum"), a=("실제", "sum"))
    ase = (blk["p"] - blk["a"]).abs()
    return {"ase": float(ase.mean()), "ase_std": float(ase.std()), "score": float(ase.mean() + ase.std()),
            "mae": float(e.abs().mean()), "rmse": float(np.sqrt((e ** 2).mean())),
            "relative_error": float(e.abs().sum() / max(d["실제"].abs().sum(), 1e-9) * 100), "months": int(len(d))}


def test_service(svc: dict) -> dict:
    """Test 24개월(조장 기준 구간): 목표월마다 6개월 전 기준월에서, 기준월까지의 자료 · 목표값만으로 서비스 모델을 학습해 예측."""
    C, root = _runtime()
    meta, der = svc["meta"], svc["derived"]
    a, b = pd.Timestamp(SP.TEST[0] + "-01"), pd.Timestamp(SP.TEST[1] + "-01")
    rows = []
    for k, t in enumerate(pd.date_range(a, b, freq="MS")):
        o = t - pd.DateOffset(months=LEAD)
        _, p, _ = _fit(C, root, meta, _asof(C, svc, o), o, asof=True)
        y = pd.to_numeric(der[C.TARGET], errors="coerce").get(t, np.nan)
        rows.append({"구간": "Test", "창": k // 3 + 1, "월": f"{t:%Y-%m}", "기준월": f"{o:%Y-%m}", "실제": float(y), "예측": p})
    df = pd.DataFrame(rows)
    return {"table": df.to_dict("records"), "metrics": _metrics(df)}


def forecast_service(svc: dict) -> dict:
    """7~12월을 각 기준월(목표월 6개월 전) 시점 정보만으로 다시 예측하고, 최신 기준월 최종 모델을 저장.
    최종 모델은 지금 확정된 실적 전체로 학습한다(운영 전망 — 학습에 쓰는 실적은 모두 이미 공표된 값)."""
    import joblib
    C, root = _runtime()
    meta, der, vid = svc["meta"], svc["derived"], svc["vid"]
    ref = SP.REFERENCE["vessels"][vid]
    months = [m["month"] for m in ref["monthly"]]
    re_ = {}
    for m in months:
        o = pd.Timestamp(m + "-01") - pd.DateOffset(months=LEAD)
        _, p, _ = _fit(C, root, meta, _asof(C, svc, o), o, asof=True)
        re_[m] = p
    o_last = der.index.max()
    est, nxt, rng = _fit(C, root, meta, der, o_last, asof=False)
    MODELS.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model": est, "features": meta["features"], "train": list(rng), "origin": f"{o_last:%Y-%m}"}, MODELS / f"{vid}.joblib")
    dash = {m["month"]: float(m["value"]) for m in ref["monthly"]}
    return {"retrained": re_, "dashboard": dash, "trainRange": list(rng), "latestOrigin": f"{o_last:%Y-%m}",
            "nextTarget": f"{o_last + pd.DateOffset(months=LEAD):%Y-%m}", "nextForecast": nxt,
            "gapPct": {m: round((re_[m] / dash[m] - 1) * 100, 1) if dash[m] else None for m in months}}


def assemble(vid: str, svc: dict, test: dict, fc: dict) -> dict:
    ref = SP.REFERENCE["vessels"][vid]
    return {"vesselId": vid, "vesselName": ref["vesselName"], "unit": ref["unit"], "model": svc["meta"]["model"],
            "strategy": svc["meta"]["strategy"], "features": svc["meta"]["features"], "masterFile": svc["source"],
            "lastActual": f"{svc['lastActual']:%Y-%m}", "test": test, "forecast": fc,
            "dashboard": {k: ref[k] for k in ("q3", "q4", "quarterChange", "peakMonth", "testMae", "testRelativeError", "predictionIntervals95")}}


def retrained_forecasts(full: dict) -> dict:
    """재학습 결과만 모은 공식 출력 — 대시보드 기준값은 넣지 않는다."""
    out = {}
    for vid, v in full.items():
        f = v["forecast"]
        mon = f["retrained"]
        ms = sorted(mon)
        out[vid] = {"vesselName": v["vesselName"], "unit": v["unit"], "model": v["model"], "strategy": v["strategy"],
                    "monthly": [{"month": m, "value": float(mon[m])} for m in ms],
                    "q3": float(sum(mon[m] for m in ms[:3])), "q4": float(sum(mon[m] for m in ms[3:])),
                    "latestOrigin": f["latestOrigin"], "nextTarget": f["nextTarget"], "nextForecast": float(f["nextForecast"]),
                    "test": v["test"]["metrics"]}
    return {"source": "kedro ship_pulse 재학습(서비스 런타임 모델 · 기준월 시점 정보)", "vessels": out}


def export_results(*vessels: dict) -> dict:
    """재학습 결과(retrained_forecasts.json)와 대시보드 기준값 사본(dashboard_reference.json)을 따로 쓰고, 차이는 comparison.json 에."""
    full = {v["vesselId"]: v for v in vessels}
    if len(full) != VESSELS:
        raise ValueError(f"선종 {VESSELS}개가 모두 있어야 해요: {sorted(full)}")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "notebook_forecasts.json").unlink(missing_ok=True)   # 예전 이름(대시보드 값 복사본) — 재학습 결과로 오해되지 않게 지운다
    (OUT / "results.json").write_text(json.dumps(full, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    (OUT / "retrained_forecasts.json").write_text(json.dumps(retrained_forecasts(full), ensure_ascii=False, indent=1), encoding="utf-8")
    ref = {"source": SP.REFERENCE["source"], "note": "대시보드 기준값 사본 · 비교용 입력(모델 출력 아님)", "vessels": SP.REFERENCE["vessels"]}
    (OUT / "dashboard_reference.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1), encoding="utf-8")
    cmp_ = [{"선종": v["vesselName"], "월": m, "대시보드": round(v["forecast"]["dashboard"][m], 1), "재학습": round(v["forecast"]["retrained"][m], 1),
             "차이(%)": v["forecast"]["gapPct"][m]} for v in full.values() for m in v["forecast"]["dashboard"]]
    (OUT / "comparison.json").write_text(json.dumps(cmp_, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"results": str(OUT / "results.json"), "retrained": str(OUT / "retrained_forecasts.json"), "vessels": list(full)}


def verify_registry(client, vessels=None) -> list:
    """선종별 등록 모델 ship_pulse_<선종> 에 alias production 이 있고 그 버전이 실제로 있는지 본다. 문제 목록을 돌려준다."""
    probs = []
    for vid in vessels or list(SP.SHIPS):
        name = f"ship_pulse_{vid}"
        try:
            mv = client.get_model_version_by_alias(name, "production")
            client.get_model_version(name, mv.version)
        except Exception as e:   # 모델이 없거나 alias 가 없으면 MlflowException
            probs.append(f"{name}: production alias 없음 ({type(e).__name__})")
    return probs


def track_mlflow(_export=None) -> dict:
    """실험 ship_pulse 에 기록하고 서비스 최종 모델을 ship_pulse_<선종> 으로 등록(alias production). URI 없으면 건너뜀."""
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        return {"mlflow": "skipped (MLFLOW_TRACKING_URI 없음)"}
    import hashlib

    import joblib
    import mlflow
    import mlflow.sklearn as msk
    from mlflow import MlflowClient

    _modeling(_runtime()[1])   # 저장 모델(sp_service_sof 클래스)을 읽기 전에 런타임 패키지 등록
    raw = (OUT / "results.json").read_bytes()
    digest = hashlib.sha256(raw + b"service-v1").hexdigest()[:16]
    full = json.loads(raw.decode("utf-8"))
    mlflow.set_tracking_uri(uri)
    exp = mlflow.set_experiment(os.environ.get("MLFLOW_SHIP_PULSE_EXPERIMENT", "ship_pulse"))
    client, registered = MlflowClient(), []
    if len(mlflow.search_runs([exp.experiment_id], filter_string=f"tags.results_sha = '{digest}'", max_results=1)):
        probs = verify_registry(client, list(full))
        if probs:   # 같은 결과가 이미 기록돼 있어도 등록이 빠졌으면 실패로 본다
            raise RuntimeError("MLflow 등록 확인 실패: " + "; ".join(probs))
        return {"mlflow": "already logged", "sha": digest}
    with mlflow.start_run(run_name="Ship Pulse 운영 재학습 · 서비스 모델") as parent:
        mlflow.set_tags({"results_sha": digest, "pipeline": "ship_pulse", "basis": "서비스 런타임 + 대시보드 데이터셋", "reference": SP.REFERENCE["source"]})
        mlflow.log_params({"vessels": ",".join(full), "lead_months": LEAD, "test": "~".join(SP.TEST), "seed": 42})
        for fn in ("retrained_forecasts.json", "comparison.json", "dashboard_reference.json"):
            mlflow.log_artifact(str(OUT / fn))
        mlflow.log_metrics({f"{vid}.{k}": float(x) for vid, v in full.items()
                            for k, x in (("test_ase", v["test"]["metrics"]["ase"]), ("dashboard_q4", v["dashboard"]["q4"]),
                                         ("retrained_q4", sum(list(v["forecast"]["retrained"].values())[3:]))) if x == x})
        for vid, v in full.items():
            with mlflow.start_run(run_name=v["vesselName"], nested=True):
                mlflow.set_tags({"pipeline": "ship_pulse", "vessel": vid})
                mlflow.log_params({"model": v["model"], "strategy": v["strategy"], "n_features": len(v["features"]),
                                   "features": " | ".join(v["features"])[:6000], "master": v["masterFile"], "last_actual": v["lastActual"],
                                   "train_range": "~".join(v["forecast"]["trainRange"]), "latest_origin": v["forecast"]["latestOrigin"]})
                f = v["forecast"]
                m = {f"test_{k}": x for k, x in v["test"]["metrics"].items()}
                m |= {"dashboard_q4": v["dashboard"]["q4"], "dashboard_test_relative_error": v["dashboard"]["testRelativeError"],
                      "retrained_q4": sum(list(f["retrained"].values())[3:]), "next_forecast": f["nextForecast"]}
                m |= {f"gap_pct_{k.replace('-', '_')}": x for k, x in f["gapPct"].items() if x is not None}
                mlflow.log_metrics({k: float(x) for k, x in m.items() if isinstance(x, (int, float)) and x == x})
                mlflow.log_dict(v, f"{vid}/result.json")
                # 모델 로깅 · 등록 · alias 실패는 삼키지 않는다 — Kedro 노드와 Airflow 작업이 실패해야 한다
                info = msk.log_model(joblib.load(MODELS / f"{vid}.joblib")["model"], name=f"ship_pulse_{vid}",
                                     serialization_format="cloudpickle", registered_model_name=f"ship_pulse_{vid}")
                if info.registered_model_version is None:
                    raise RuntimeError(f"ship_pulse_{vid}: 등록 버전이 없어요")
                mlflow.log_metrics({"test_ase": float(v["test"]["metrics"]["ase"]), "next_forecast": float(f["nextForecast"])}, model_id=info.model_id)
                client.set_registered_model_alias(f"ship_pulse_{vid}", "production", info.registered_model_version)
                registered.append(f"ship_pulse_{vid} v{info.registered_model_version}")
    probs = verify_registry(client, list(full))
    if probs:
        raise RuntimeError("MLflow 등록 확인 실패: " + "; ".join(probs))
    return {"mlflow": "logged", "run_id": parent.info.run_id, "registered": registered}
