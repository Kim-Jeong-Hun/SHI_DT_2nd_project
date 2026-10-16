"""Ship Pulse 파이프라인 회귀 테스트 — PR #13 리뷰 항목.

  1. 시점 누수: 과거 기준월 예측은 기준월 뒤 목표값(수주 실적)을 바꿔도 변하지 않아야 한다
  2. 선종 5개 출력: 파이프라인 · 내보내기가 5개 선종을 모두 다룬다
  3. 재학습 결과와 대시보드 기준값은 서로 다른 파일 · 다른 값이다
  4. MLflow 등록 · alias 실패는 작업 실패가 된다(삼키지 않는다)
서비스 런타임(deploy/render)은 읽기만 한다.
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

MLOPS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(MLOPS / "src"))
sys.path.insert(0, str(MLOPS / "scripts"))

from shi_dt.pipelines.ship_pulse import service_nodes as N  # noqa: E402
from shi_dt.pipelines.ship_pulse import spec as SP  # noqa: E402

VIDS = list(SP.SHIPS)


# ---------- 1. 시점 누수 ----------
@pytest.mark.parametrize("vid", ["bulk", "gas"])
def test_past_origin_ignores_later_targets(vid):
    C, root = N._runtime()
    svc = N.load_service(vid)
    o = pd.Timestamp("2024-01-01")
    _, p0, _ = N._fit(C, root, svc["meta"], N._asof(C, svc, o), o, asof=True)

    bent = dict(svc)
    fr = svc["frame"].copy()
    after = fr.index > o
    fr.loc[after, C.TARGET] = pd.to_numeric(fr.loc[after, C.TARGET], errors="coerce") * 7 + 12345   # 기준월 뒤 실적을 크게 바꾼다
    bent["frame"] = fr
    _, p1, _ = N._fit(C, root, svc["meta"], N._asof(C, bent, o), o, asof=True)
    assert p1 == pytest.approx(p0, rel=0, abs=1e-9)


def test_asof_frame_ends_at_origin():
    C, _ = N._runtime()
    svc = N.load_service("bulk")
    o = pd.Timestamp("2025-03-01")
    der = N._asof(C, svc, o)
    assert der.index.max() == o
    assert pd.to_numeric(der[C.TARGET], errors="coerce").dropna().index.max() <= o


# ---------- 2 · 3. 선종 5개 · 출력 분리 ----------
def _fake(vid, scale=1.0):
    ref = SP.REFERENCE["vessels"][vid]
    months = [m["month"] for m in ref["monthly"]]
    re_ = {m: 1000.0 * scale + i for i, m in enumerate(months)}
    dash = {m["month"]: float(m["value"]) for m in ref["monthly"]}
    return {"vesselId": vid, "vesselName": ref["vesselName"], "unit": ref["unit"], "model": "m", "strategy": "s",
            "features": ["a"], "masterFile": "x.csv", "lastActual": "2026-06",
            "test": {"table": [], "metrics": {"ase": 1.0, "ase_std": 0.0, "score": 1.0, "mae": 1.0, "rmse": 1.0, "relative_error": 1.0, "months": 24}},
            "forecast": {"retrained": re_, "dashboard": dash, "trainRange": ["2015-01", "2025-12"], "latestOrigin": "2026-06",
                         "nextTarget": "2026-12", "nextForecast": 5.0,
                         "gapPct": {m: round((re_[m] / dash[m] - 1) * 100, 1) if dash[m] else None for m in months}},
            "dashboard": {k: ref[k] for k in ("q3", "q4", "quarterChange", "peakMonth", "testMae", "testRelativeError", "predictionIntervals95")}}


def test_pipeline_covers_five_vessels():
    from shi_dt.pipelines.ship_pulse.pipeline import create_pipeline
    outs = create_pipeline().all_outputs()
    assert {f"sp_{v}_result" for v in VIDS} <= outs
    assert len(VIDS) == N.VESSELS == 5


def test_export_separates_retrained_and_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "OUT", tmp_path)
    (tmp_path / "notebook_forecasts.json").write_text("{}", encoding="utf-8")   # 예전 이름은 지워져야 한다
    N.export_results(*[_fake(v) for v in VIDS])
    re_ = json.loads((tmp_path / "retrained_forecasts.json").read_text(encoding="utf-8"))
    ref = json.loads((tmp_path / "dashboard_reference.json").read_text(encoding="utf-8"))
    assert not (tmp_path / "notebook_forecasts.json").exists()
    assert set(re_["vessels"]) == set(VIDS) == set(ref["vessels"])
    assert ref["vessels"] == SP.REFERENCE["vessels"]
    for v in VIDS:
        got = [m["value"] for m in re_["vessels"][v]["monthly"]]
        assert got == [1000.0 + i for i in range(len(got))]            # 재학습 값 그대로
        assert got != [m["value"] for m in SP.REFERENCE["vessels"][v]["monthly"]]   # 대시보드 값 복사가 아니다
        assert re_["vessels"][v]["q4"] == pytest.approx(sum(got[3:]))


def test_export_requires_all_vessels(tmp_path, monkeypatch):
    monkeypatch.setattr(N, "OUT", tmp_path)
    with pytest.raises(ValueError):
        N.export_results(*[_fake(v) for v in VIDS[:4]])


# ---------- 4. MLflow 등록 · alias ----------
@pytest.fixture
def mlflow_env(tmp_path, monkeypatch):
    import joblib
    from sklearn.linear_model import LinearRegression

    out, models = tmp_path / "out", tmp_path / "models"
    models.mkdir()
    monkeypatch.setattr(N, "OUT", out)
    monkeypatch.setattr(N, "MODELS", models)
    N.export_results(*[_fake(v) for v in VIDS])
    for v in VIDS:
        joblib.dump({"model": LinearRegression().fit(np.arange(6).reshape(-1, 1), np.arange(6.0))}, models / f"{v}.joblib")
    uri = "sqlite:///" + (tmp_path / "mlflow.db").as_posix()
    monkeypatch.setenv("MLFLOW_TRACKING_URI", uri)
    monkeypatch.setenv("MLFLOW_SHIP_PULSE_EXPERIMENT", "ship_pulse")
    monkeypatch.setattr(N, "_modeling", lambda root: None)
    monkeypatch.setattr(N, "_runtime", lambda: (None, tmp_path))
    import mlflow
    mlflow.set_tracking_uri(uri)
    return uri


def _alias_shas(client):
    out = {}
    for v in VIDS:
        mv = client.get_model_version_by_alias(f"ship_pulse_{v}", "production")
        out[v] = client.get_model_version(f"ship_pulse_{v}", mv.version).tags.get("results_sha")
    return out


def test_mlflow_registers_five_with_alias(mlflow_env):
    from mlflow import MlflowClient

    import mlflow_registry_check as RC
    r = N.track_mlflow()
    assert len(r["registered"]) == 5
    c = MlflowClient()
    assert set(_alias_shas(c).values()) == {N.results_digest()}   # 다섯 alias 모두 이번 결과의 모델
    assert N.verify_registry(c, digest=N.results_digest()) == []
    assert RC.main(c) == 0
    assert N.track_mlflow()["mlflow"] == "already logged"          # 같은 결과 · 등록 정상이면 건너뛴다
    c.delete_registered_model_alias("ship_pulse_gas", "production")   # alias 하나가 빠지면 확인 단계가 실패하고
    assert RC.main(c) == 1
    assert N.track_mlflow()["mlflow"] == "logged"                   # 같은 결과로 다시 돌리면 복구된다
    assert set(_alias_shas(c).values()) == {N.results_digest()}
    assert RC.main(c) == 0


def test_failed_alias_then_same_digest_retry_recovers(mlflow_env, monkeypatch):
    import mlflow
    from mlflow import MlflowClient

    real = MlflowClient.set_registered_model_alias

    def flaky(self, name, alias, version):
        if name == "ship_pulse_gas":
            raise RuntimeError("alias 실패")
        return real(self, name, alias, version)
    monkeypatch.setattr(MlflowClient, "set_registered_model_alias", flaky)
    with pytest.raises(RuntimeError):
        N.track_mlflow()
    exp = mlflow.get_experiment_by_name("ship_pulse")
    runs = mlflow.search_runs([exp.experiment_id], filter_string=f"tags.results_sha = '{N.results_digest()}'")
    assert set(runs["status"]) == {"FAILED"}                        # 실패한 실행은 완료로 남지 않는다
    monkeypatch.setattr(MlflowClient, "set_registered_model_alias", real)
    r = N.track_mlflow()                                            # 같은 digest 로 재시도
    assert r["mlflow"] == "logged"
    assert set(_alias_shas(MlflowClient()).values()) == {N.results_digest()}


def test_stale_aliases_do_not_pass_for_new_results(mlflow_env, monkeypatch):
    import mlflow.sklearn as msk
    from mlflow import MlflowClient

    import mlflow_registry_check as RC
    N.track_mlflow()                                                # 예전 결과로 다섯 alias 를 만들어 둔다
    old = N.results_digest()
    N.export_results(*[_fake(v, scale=2.0) for v in VIDS])          # 새 결과(지문이 바뀜)
    assert N.results_digest() != old

    def boom(*a, **k):
        raise RuntimeError("log_model 실패")
    monkeypatch.setattr(msk, "log_model", boom)
    with pytest.raises(RuntimeError):
        N.track_mlflow()
    c = MlflowClient()
    assert set(_alias_shas(c).values()) == {old}                    # alias 는 예전 모델 그대로(부분 전환 없음)
    assert N.verify_registry(c, digest=N.results_digest())          # alias 가 있어도 이번 결과가 아니면 문제
    assert RC.main(c) == 1


def test_mlflow_log_failure_fails_task(mlflow_env, monkeypatch):
    import mlflow.sklearn as msk

    def boom(*a, **k):
        raise RuntimeError("log_model 실패")
    monkeypatch.setattr(msk, "log_model", boom)
    with pytest.raises(RuntimeError):
        N.track_mlflow()


def test_mlflow_alias_failure_fails_task(mlflow_env, monkeypatch):
    from mlflow import MlflowClient

    def boom(self, *a, **k):
        raise RuntimeError("alias 실패")
    monkeypatch.setattr(MlflowClient, "set_registered_model_alias", boom)
    with pytest.raises(RuntimeError):
        N.track_mlflow()
