import base64
import json
import os
import pathlib
import re
import sys
import types

os.environ.setdefault("OMP_NUM_THREADS", "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS", "1")
os.environ.setdefault("LOKY_MAX_CPU_COUNT", "1")

import numpy as np
import pandas as pd


TARGET = "수주용량"
LEAD_MONTHS = 6
VESSELS = {
    "container": {
        "name": "컨테이너선", "unit": "TEU", "model": "Tweedie Regression + XGBoost 동일가중 앙상블",
        "strategy": "Adaptive 24·36·48·60개월 · Uniform · VIF 10", "window": 60,
        "specification": {"kind": "ensemble", "members": [
            {"base": "Tweedie Regression", "params": {}}, {"base": "XGBoost", "params": {}},
        ], "weights": [0.5, 0.5]},
        "features": [
            "군비증강(%)_추가2개월전", "공급망압력(표준편차)_변화량5대9개월",
            "말라카 GPR(%)_변화량8대9개월", "핵위협(%)_추가5개월전", "세계 GPR(지수)_추가2개월전",
            "미국 TPU·Caldara(지수)_추가1개월전", "컨테이너 운임·통합지수 변화량(3달 전-4달 전)",
            "컨테이너 운임·북유럽→극동·XSI-C(USD/FEU)_추가3개월전",
            "수에즈 컨테이너선 통과횟수(회)_추가1개월전", "면화 A지수(USD/kg)_변화량8대9개월",
        ],
    },
    "tanker": {
        "name": "유조선", "unit": "DWT", "model": "Quantile Regression",
        "strategy": "Sliding 60개월 · Uniform · VIF 10", "window": 60,
        "specification": "Quantile Regression",
        "features": [
            "세계 GPR(지수)_추가2개월전", "행동 GPRA(지수)_추가9개월전", "전쟁·평화위협(%)_추가9개월전",
            "미국수입_원유_톤마일대리지표(tonne-NM)_추가1개월전", "말라카 GPR(%)_추가1개월전",
            "중국 TPU(지수)_추가4개월전", "미국 TPU·EPUTRADE(지수)_추가4개월전", "인도량(DWT)_추가3개월전",
            "테러위협(%)_변화량2대7개월", "싱가포르 벙커유 판매(천톤)", "테러행위(%)_변화량2대6개월",
            "month_sin", "미국수입_석유제품_톤마일대리지표_YoY(%)_변화량0대1개월",
            "미국 무역가중 달러지수(2006-01=100)_추가6개월전", "직전3개월누적수주량",
            "WTI 가격(USD/bbl)_변화량0대7개월", "수에즈 GPR(%)_추가2개월전", "수주잔량(DWT)_추가1개월전",
            "신조선가(백만 USD)_추가3개월전", "군비증강(%)",
        ],
    },
    "bulk": {
        "name": "벌크선", "unit": "DWT", "model": "PLS Regression",
        "strategy": "Sliding 24개월 · Uniform · VIF 10", "window": 24,
        "specification": "PLS Regression",
        "features": [
            "수주용량_확보월", "테러행위(%)_추가4개월전",
            "미국수입_벌크화물_톤마일대리지표(tonne-NM)_추가5개월전",
            "수에즈 전체선박 순톤수(천 SCNT)_추가1개월전", "말라카 GPR(%)_변화량8대9개월",
            "인도량(DWT)_추가1개월전", "원유 평균 가격(USD/bbl)_변화량5대6개월",
            "핵위협(%)_변화량0대5개월", "테러위협(%)_추가7개월전",
            "비료 가격지수(2010=100)_변화량0대1개월", "벌크선 운임·BDI(점수)_추가3개월전",
            "GPR 3개월변화(차)_변화량2대5개월", "세계 GPR(지수)", "군비증강(%)",
        ],
    },
    "gas": {
        "name": "가스 운반선", "unit": "CBM", "model": "Huber Regression",
        "strategy": "Sliding 36개월 · Uniform · VIF 10", "window": 36,
        "specification": "Huber Regression",
        "features": [
            "수주용량_확보월2개월전", "GPR 3개월변화(차)_변화량1대9개월", "테러위협(%)_추가2개월전",
            "수에즈 전체선박 통과횟수(회)_추가3개월전", "엔달러 환율(JPY/USD)_변화량0대3개월",
            "가스 리그(사우디 제외·기)_추가1개월전",
        ],
    },
    "chemical": {
        "name": "케미컬 탱커", "unit": "DWT", "model": "XGBoost",
        "strategy": "Adaptive 24·36·48개월 · Uniform · VIF 10", "window": 48, "specification": "XGBoost",
        "features": [
            "전쟁·평화위협(%)_추가8개월전", "수에즈 GPR(%)", "원달러 환율(KRW/USD)_추가7개월전",
            "팜유 가격(USD/mt)_추가9개월전", "케미컬 운임·휴스턴~극동(USD/톤)", "행동 GPRA(지수)",
            "천연가스 가격지수(2010=100)_추가9개월전", "수에즈 전체선박 순톤수(천 SCNT)", "month_cos",
            "핵위협(%)_변화량2대8개월", "테러행위(%)_변화량0대7개월", "세계 GPR(지수)_추가6개월전",
            "중국 TPU(지수)_변화량2대7개월", "미국 TPU·EPUTRADE(지수)_추가9개월전",
            "수주용량_확보월", "세계 실질수출(백만 2010USD, SA)_추가9개월전",
        ],
    },
}


def load_data(project_root, vessel_id):
    if vessel_id not in VESSELS:
        raise ValueError("지원하지 않는 선종입니다.")
    meta = VESSELS[vessel_id]
    path = project_root / "data" / "master" / f"마스터테이블({meta['name']}).csv"
    frame = pd.read_csv(path, encoding="utf-8-sig")
    frame["기준월"] = pd.to_datetime(frame["기준월"], format="%Y-%m")
    return frame.sort_values("기준월").set_index("기준월"), meta, path.name


def feature_rule(feature):
    change = re.fullmatch(r"(.+)_변화량(\d+)대(\d+)개월", feature)
    if change:
        return change.group(1), "change", int(change.group(2)), int(change.group(3))
    lag = re.fullmatch(r"(.+)_추가(\d+)개월전", feature)
    if lag:
        return lag.group(1), "lag", int(lag.group(2)), None
    return feature, "direct", 0, None


def source_unit(source):
    match = re.search(r"\(([^()]*)\)$", source)
    return match.group(1) if match else "지수"


def input_sources(frame, features):
    grouped = {}
    for feature in features:
        source, _kind, first, second = feature_rule(feature)
        if source.startswith(TARGET) or source == "직전3개월누적수주량" or source not in frame.columns:
            continue
        entry = grouped.setdefault(source, {"id": source, "label": source, "unit": source_unit(source), "features": [], "maxLag": 0})
        entry["features"].append(feature)
        entry["maxLag"] = max(entry["maxLag"], first, second or 0)
    result = []
    for source, entry in grouped.items():
        values = pd.to_numeric(frame[source], errors="coerce").dropna()
        if values.empty:
            continue
        entry["latestMonth"] = values.index[-1].strftime("%Y-%m")
        entry["latestValue"] = float(values.iloc[-1])
        entry["observations"] = {month.strftime("%Y-%m"): float(value) for month, value in values.items()}
        result.append(entry)
    return result


def config(project_root, vessel_id):
    frame, meta, source = load_data(project_root, vessel_id)
    sources = input_sources(frame, meta["features"])
    latest = max(pd.Timestamp(item["latestMonth"]) for item in sources)
    return {
        "vesselId": vessel_id, "vessel": meta["name"], "unit": meta["unit"], "source": source,
        "model": meta["model"], "strategy": meta["strategy"], "leadMonths": LEAD_MONTHS,
        "featureCount": len(meta["features"]), "features": meta["features"], "inputSources": sources,
        "defaultObservationMonth": (latest + pd.DateOffset(months=1)).strftime("%Y-%m"),
    }


def add_derived_features(frame, features):
    output = frame.copy()
    target = pd.to_numeric(output[TARGET], errors="coerce")
    output["직전3개월누적수주량"] = target.shift(1).rolling(3, min_periods=3).sum()
    for feature in features:
        if feature in output.columns:
            output[feature] = pd.to_numeric(output[feature], errors="coerce")
            continue
        if feature == "수주용량_확보월":
            output[feature] = target
            continue
        if feature.startswith("수주용량_확보월"):
            lag = int(re.search(r"(\d+)개월전$", feature).group(1))
            output[feature] = target.shift(lag)
            continue
        source, kind, first, second = feature_rule(feature)
        values = pd.to_numeric(output[source], errors="coerce")
        if kind == "change":
            output[feature] = values.shift(first) - values.shift(second)
        elif kind == "lag":
            output[feature] = values.shift(first)
        else:
            output[feature] = values
    output[features] = output[features].ffill()
    return output


def extend_raw(frame, through):
    full_index = pd.date_range(frame.index.min(), through, freq="MS")
    output = frame.reindex(full_index).apply(pd.to_numeric, errors="coerce")
    feature_columns = [column for column in output.columns if column != TARGET]
    output[feature_columns] = output[feature_columns].ffill()
    return output


def enable_vecm_fallback_when_statsmodels_is_missing():
    try:
        __import__("statsmodels.tsa.vector_ar.vecm")
        return
    except ModuleNotFoundError:
        pass

    class MissingVecm:
        def __init__(self, *args, **kwargs):
            pass

        def fit(self):
            raise np.linalg.LinAlgError("statsmodels unavailable; use the notebook's regularized VECM fallback")

    modules = {
        "statsmodels": types.ModuleType("statsmodels"),
        "statsmodels.tsa": types.ModuleType("statsmodels.tsa"),
        "statsmodels.tsa.vector_ar": types.ModuleType("statsmodels.tsa.vector_ar"),
        "statsmodels.tsa.vector_ar.vecm": types.ModuleType("statsmodels.tsa.vector_ar.vecm"),
    }
    modules["statsmodels.tsa.vector_ar.vecm"].VECM = MissingVecm
    for name, module in modules.items():
        sys.modules.setdefault(name, module)


def fit_and_predict(project_root, meta, derived, origin):
    project_src = str(project_root / "src")
    if project_src not in sys.path:
        sys.path.insert(0, project_src)
    if meta["name"] == "가스 운반선":
        enable_vecm_fallback_when_statsmodels_is_missing()
    from ship_orders_forecasting.modeling import model_for

    features = meta["features"]
    target = pd.to_numeric(derived[TARGET], errors="coerce").shift(-LEAD_MONTHS)
    training = derived[features].copy()
    training["__target"] = target
    last_known_target = pd.to_numeric(derived[TARGET], errors="coerce").dropna().index[-1]
    training = training.loc[training.index + pd.DateOffset(months=LEAD_MONTHS) <= last_known_target].dropna()
    if meta["window"]:
        training = training.tail(meta["window"])
    if len(training) < 24:
        raise ValueError("최종 모델을 재학습할 수 있는 완전한 시계열이 부족합니다.")

    x = training[features].astype(float)
    steps = origin.to_period("M").ordinal - x.index[-1].to_period("M").ordinal
    if steps > 0:
        path = derived.loc[x.index[-1] + pd.DateOffset(months=1):origin, features].to_numpy(dtype=float)
        x.attrs["forecast_steps"] = steps
        x.attrs["known_future_exog"] = path
    estimator = model_for(meta["specification"], 42).fit(x, training["__target"].astype(float))
    row = derived.loc[[origin], features].astype(float)
    return max(0.0, float(estimator.predict(row)[0]))


def run(project_root, params):
    vessel_id = params.get("vesselId")
    frame, meta, source_file = load_data(project_root, vessel_id)
    sources = input_sources(frame, meta["features"])
    allowed = {item["id"] for item in sources}
    observation_month = params.get("observationMonth")
    values = params.get("values") or {}
    if not isinstance(values, dict) or not re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", str(observation_month)):
        raise ValueError("관측월과 월별 피처 값을 확인해 주세요.")
    observed = pd.Timestamp(f"{observation_month}-01")
    unknown = set(values).difference(allowed)
    if unknown:
        raise ValueError("최종 모델에 연결되지 않은 피처가 포함되어 있습니다.")

    normalized = []
    missing = []
    for item in sources:
        feature = item["id"]
        existing = pd.to_numeric(pd.Series([frame.at[observed, feature] if observed in frame.index else np.nan]), errors="coerce").iloc[0]
        if pd.notna(existing):
            continue
        try:
            value = float(values.get(feature))
        except (TypeError, ValueError):
            missing.append(feature)
            continue
        if not np.isfinite(value):
            missing.append(feature)
            continue
        normalized.append((feature, observed, value))
    if missing:
        preview = ", ".join(missing[:3])
        suffix = f" 외 {len(missing) - 3}개" if len(missing) > 3 else ""
        raise ValueError(f"{observation_month}의 비어 있는 피처를 모두 입력해 주세요: {preview}{suffix}")
    if not normalized:
        raise ValueError(f"{observation_month}은 이미 필요한 시장 정보가 모두 확보되어 있습니다.")

    baseline_raw = extend_raw(frame, observed)
    scenario_raw = baseline_raw.copy()
    for feature, month, value in normalized:
        scenario_raw.loc[month, feature] = value

    baseline = add_derived_features(baseline_raw, meta["features"])
    scenario = add_derived_features(scenario_raw, meta["features"])
    changed = (scenario[meta["features"]] - baseline[meta["features"]]).abs().gt(1e-12)
    unchanged = not bool(changed.loc[observed].any())

    # The trained pipeline predicts exactly D+6 from an observation month. Keep
    # a short lead-in for visual continuity, but never synthesize later origins.
    chart_start = max(frame.index.min(), observed - pd.DateOffset(months=2))
    chart_end = observed
    rows = []
    for origin in pd.date_range(chart_start, chart_end, freq="MS"):
        base_value = fit_and_predict(project_root, meta, baseline, origin)
        affected = origin == observed
        scenario_value = fit_and_predict(project_root, meta, scenario, origin) if affected else base_value
        rows.append({
            "originMonth": origin.strftime("%Y-%m"), "month": (origin + pd.DateOffset(months=LEAD_MONTHS)).strftime("%Y-%m"),
            "baseline": base_value, "scenario": scenario_value, "change": scenario_value - base_value, "affected": affected,
        })
    actuals = pd.to_numeric(frame.loc[:observed, TARGET], errors="coerce").dropna().tail(12)
    return {
        "vesselId": vessel_id, "vessel": meta["name"], "unit": meta["unit"], "source": source_file,
        "model": meta["model"], "strategy": meta["strategy"], "leadMonths": LEAD_MONTHS,
        "actuals": [{"month": month.strftime("%Y-%m"), "value": float(value)} for month, value in actuals.items()],
        "forecasts": rows, "affectedForecasts": [item for item in rows if item["affected"]],
        "observationMonth": observation_month,
        "overrides": [{"feature": f, "month": m.strftime("%Y-%m"), "value": v} for f, m, v in normalized],
        "unchanged": unchanged,
        "assumption": (f"{observation_month}의 입력값이 기존 기준과 같아 전망 수치가 유지되었습니다."
                       if unchanged else
                       f"{observation_month}의 모델 입력 원천지표를 모두 확보한 뒤 최종 파생 피처와 D+6 전망을 다시 계산했습니다."),
    }


def main():
    os.environ["PATH"] = str(pathlib.Path(sys.executable).parent) + os.pathsep + os.environ.get("PATH", "")
    project_root = pathlib.Path(sys.argv[1]).resolve()
    action = sys.argv[2]
    payload = json.loads(base64.b64decode(sys.argv[3]).decode("utf-8"))
    value = config(project_root, payload["vesselId"]) if action == "config" else run(project_root, payload)
    print("__FORECAST_JSON__" + json.dumps(value, ensure_ascii=False, allow_nan=False))


if __name__ == "__main__":
    main()
