"""선박 수주 예측 — 팀 파이프라인(ship_orders_forecasting)을 Kedro 노드로 펼쳐 실행하고 운영 보고서를 갱신한다.
팀 저장소(Drive 'Ship orders forcasting' = SHIP_ORDERS_REPO)의 함수를 그대로 부른다(team_nodes.py — 계산 변경 없음).
  ship_orders_preprocess  원자료 → processed → 선종별 마스터 (Drive 전체 사본에서만)
  ship_orders             공통 입력 → 선종 5개 × (평가 프레임 → 고정 선택 → 2026 평가 · 기준일 입력표 · 1·3·6개월 직접 선행예측)
                          → 보고서 → data/01_raw/ship 복사 → MLflow 기록
결과 reports/2026_독립검증.json 과 선종별 수주 이력을 공유 볼륨 data/01_raw/ship 으로 복사한다.
서빙 API(/ship/forecast)는 파일 수정 시각을 보고 다음 요청부터 새 보고서를 읽는다(재시작 불필요).
"""
import json
import os
import shutil
import time
from datetime import datetime, timezone
import subprocess
import sys
from pathlib import Path

from kedro.pipeline import Pipeline, node

ROOT = Path(os.environ.get("SHI_PROJECT_DIR", Path(__file__).resolve().parents[4]))
# 팀 저장소에서는 분석 코드가 저장소 루트(scripts · src)에 있다 — 없으면 예전처럼 Drive 사본(ship-order-drive)
_ROOT_REPO = ROOT.parent if (ROOT.parent / "scripts" / "분석" / "2026_독립검증.py").exists() else ROOT.parent / "ship-order-drive"
REPO = Path(os.environ.get("SHIP_ORDERS_REPO", _ROOT_REPO))
OUT = ROOT / "data" / "01_raw" / "ship"
_T0 = time.perf_counter()   # 프로세스 시작 기준 소요 시간(run_meta)


def publish_report(report: dict) -> dict:
    """팀 보고서와 선종별 수주 이력을 서빙 공유 경로(data/01_raw/ship)로 내보낸다 — /ship API 가 읽는 파일."""
    (OUT / "processed").mkdir(parents=True, exist_ok=True)
    shutil.copy2(REPO / "reports" / "2026_독립검증.json", OUT / "2026_독립검증.json")
    copied = []
    for f in (REPO / "data" / "processed").glob("*/수주실적(*).csv"):
        shutil.copy2(f, OUT / "processed" / f.name)
        copied.append(f.name)
    started = os.environ.get("SHI_RUN_STARTED") or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    meta = {"파이프라인": "ship_orders", "노드": "publish_report", "시작": started,
            "종료": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
            "소요초": round(time.perf_counter() - _T0, 1),
            "스크립트": "Kedro 노드 분해(team_nodes.py) — 팀 scripts/분석/2026_독립검증.py 와 같은 함수 · 순서", "이력파일": copied,
            "선종수": len(report.get("결과", []))}
    (OUT / "run_meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")   # 관제 콘솔 시스템 헬스 표시용
    return {"report": str(OUT / "2026_독립검증.json"), "history_files": copied}


def track_report(_report=None, _models=None) -> dict:
    """운영 보고서를 MLflow 실험 'ship_orders' 에 기록한다 — 선종별 선택 모형·검증 오차·2026 독립 평가.

    MLFLOW_TRACKING_URI 가 없으면 건너뛴다(로컬 Airflow 실행은 기존처럼 보고서만 갱신).
    같은 보고서(SHA-256)로 이미 기록한 실행이 있으면 다시 기록하지 않는다 — 서버 재시작마다 중복 실행이 쌓이지 않게.
    """
    uri = os.environ.get("MLFLOW_TRACKING_URI")
    if not uri:
        return {"mlflow": "skipped (MLFLOW_TRACKING_URI 없음)"}
    import hashlib

    import mlflow

    path = OUT / "2026_독립검증.json"
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()[:16]
    rep = json.loads(raw.decode("utf-8"))
    meta_path = OUT / "run_meta.json"
    run_meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    mlflow.set_tracking_uri(uri)
    exp = mlflow.set_experiment(os.environ.get("MLFLOW_SHIP_EXPERIMENT", "ship_orders"))
    hit = mlflow.search_runs([exp.experiment_id], filter_string=f"tags.report_sha = '{digest}'", max_results=1)
    if len(hit):
        run_id = hit.iloc[0]["run_id"]
        return {"mlflow": "already logged", "run_id": run_id, "models": log_models(mlflow, exp.experiment_id, run_id, rep, digest)}
    num = lambda v: isinstance(v, (int, float)) and v == v
    with mlflow.start_run(run_name=f"ship_orders · {rep.get('평가기간', '')}") as run:
        mlflow.set_tags({"report_sha": digest, "pipeline": "ship_orders", "평가기간": str(rep.get("평가기간", "")),
                         "kedro_run_start": str(run_meta.get("시작", "")), "kedro_run_seconds": str(run_meta.get("소요초", ""))})
        for r in rep.get("결과", []):
            s, sel, ev = r["선종"], r.get("선택", {}), r.get("2026평가", {})
            key = {"컨테이너선": "container", "케미컬 탱커": "chemical", "유조선": "oil", "벌크선": "bulk", "가스 운반선": "gas"}.get(s, s)
            mlflow.log_params({f"{key}.model": str(sel.get("모형", ""))[:250], f"{key}.feature_set": str(sel.get("변수집합", ""))[:250],
                               f"{key}.n_features": len(sel.get("피처목록", []) or []), f"{key}.unit": r.get("단위", "")})
            m = {f"{key}.cv_smape": sel.get("평균sMAPE"), f"{key}.cv_smape_std": sel.get("sMAPE표준편차"), f"{key}.cv_rmse": sel.get("평균RMSE"),
                 f"{key}.test2026_smape": ev.get("월별sMAPE"), f"{key}.test2026_baseline_smape": ev.get("기준선sMAPE"),
                 f"{key}.test2026_rmse": ev.get("월별RMSE"), f"{key}.test2026_mae": ev.get("월별MAE")}
            mlflow.log_metrics({k: float(v) for k, v in m.items() if num(v)})
        mlflow.log_dict(rep, "report/2026_독립검증.json")
        run_id = run.info.run_id
    return {"mlflow": "logged", "run_id": run_id, "models": log_models(mlflow, exp.experiment_id, run_id, rep, digest)}


MODELS_DIR = ROOT / "data" / "06_models" / "ship"


def log_models(mlflow, experiment_id: str, report_run_id: str, rep: dict, digest: str) -> str:
    """빌드 때 저장한 운영 모델(data/06_models/ship, 선종 5 × 1·3·6개월)을 MLflow Models 화면에 올린다.

    보고서 실행과 분리한 '운영 모델' 실행 하나에 모델 15개를 기록한다(모델마다 자기 지표만 보이게).
    같은 보고서로 이미 올렸으면 다시 올리지 않고, 무료 플랜 재시작으로 지워진 모델 파일만 원래 위치에 복원한다.
    """
    import shutil

    from mlflow.utils.file_utils import local_file_uri_to_path

    idx_path = MODELS_DIR / "index.json"
    if not idx_path.exists():
        return "no saved models"
    index = json.loads(idx_path.read_text(encoding="utf-8"))
    hit = mlflow.search_runs([experiment_id], filter_string=f"tags.models_for_report = '{digest}'", max_results=1)
    if len(hit):
        run_id = hit.iloc[0]["run_id"]
        have = mlflow.search_logged_models(experiment_ids=[experiment_id], filter_string=f"source_run_id='{run_id}'", output_format="list")
        restored = 0
        for m in have:
            dst = Path(local_file_uri_to_path(str(m.artifact_location)))
            if (MODELS_DIR / m.name).exists() and not (dst / "MLmodel").exists():
                shutil.copytree(MODELS_DIR / m.name, dst, dirs_exist_ok=True)
                restored += 1
        return f"already logged {len(have)}, restored {restored}"
    test = {(r["선종"], d["선행개월"]): d.get("2026평가", {}) for r in rep.get("결과", []) for d in r.get("직접선행예측", [])}
    names = {"월별sMAPE": "test2026_smape", "월별RMSE": "test2026_rmse", "게시일확인월sMAPE": "test2026_smape_verified_months"}
    import mlflow.sklearn as msk
    logged = 0
    with mlflow.start_run(run_name="운영 모델 · 예측기준일 2026-09-30") as run:
        mlflow.set_tags({"models_for_report": digest, "report_run_id": report_run_id, "pipeline": "ship_orders",
                         "kedro_node": "save_operational_models"})
        for meta in index:
            if not meta.get("모델저장"):
                continue
            info = msk.log_model(msk.load_model(str(MODELS_DIR / meta["이름"])),   # 저장 때 MLmodel 에 기록한 신뢰 타입으로 읽힌다
                                 name=meta["이름"], pip_requirements=str(MODELS_DIR / meta["이름"] / "requirements.txt"),
                                 skops_trusted_types=["sklearn.tree._tree.Tree"],
                                 params={"ship_type": meta["선종"], "horizon_months": meta["선행개월"], "feature": meta.get("운영피처"),
                                         "model": meta.get("운영모형"), "train_months": meta.get("학습관측월"),
                                         "train_range": f"{meta.get('학습시작월')}~{meta.get('학습종료월')}",
                                         "forecast_origin": meta["예측기준일"], "target_month": meta["목표월"]},
                                 tags={"pipeline": "ship_orders", "ship_type": meta["선종"]})
            ev = test.get((meta["선종"], meta["선행개월"]), {})
            ms = {names[k]: float(ev[k]) for k in names if isinstance(ev.get(k), (int, float)) and ev[k] == ev[k]}
            ms["forecast_2026_09_30"] = float(meta["예측"])
            mlflow.log_metrics(ms, model_id=info.model_id)
            logged += 1
    return f"logged {logged} (run {run.info.run_id})"


def create_pipeline() -> Pipeline:
    """평가 · 운영 예측 — 팀 2026_독립검증.py main() 을 노드로 펼친 것(선종 5개 × 단계, 1·3·6개월 직접 선행예측)."""
    from . import team_nodes as T
    nodes = [node(T.load_sources, None, "ship_sources", name="load_common_sources"),
             node(T.load_raw_orders, None, "raw_orders", name="load_raw_orders")]
    results, asofs, pipes, models = [], [], [], []
    for ship_type in T._team().RULES.SHIP_TYPES:             # 팀 스크립트와 같은 선종 순서
        k = T.SHIP_KEYS[ship_type]; f = T._per_type(ship_type)
        sub = [
            node(f["evaluation_frame"], "ship_sources", ["frame", "external"], name="evaluation_frame"),
            node(f["frozen_choice"], ["frame", "external"], ["choice", "candidates"], name="frozen_choice"),
            node(f["holdout_2026"], ["frame", "choice"], "test_2026", name="holdout_2026"),
            node(f["publication_dates"], "raw_orders", "published", name="publication_dates"),
            node(f["asof_inputs"], ["frame", "external", "ship_sources", "published"], "asof_inputs", name="asof_inputs"),
        ]
        direct = []
        for h in T.HORIZONS:
            sub += [
                node(f[f"direct_frame_h{h}"], ["frame", "published"], f"direct_frame_h{h}", name=f"direct_frame_h{h}"),
                node(f[f"direct_select_h{h}"], [f"direct_frame_h{h}", "published"], f"direct_choice_h{h}", name=f"direct_select_h{h}"),
                node(f[f"direct_eval_h{h}"], [f"direct_frame_h{h}", "published", f"direct_choice_h{h}"], f"direct_result_h{h}", name=f"direct_eval_h{h}"),
            ]
            sub.append(node(f[f"operational_model_h{h}"], [f"direct_frame_h{h}", "published", f"direct_choice_h{h}"], f"op_model_h{h}", name=f"operational_model_h{h}"))
            direct.append(f"direct_result_h{h}")
        sub.append(node(f["assemble_result"], ["choice", "candidates", "test_2026"] + direct, "result", name="assemble_result"))
        # 선종별 모듈 파이프라인(네임스페이스) — Kedro-Viz 에서 선종 상자로 접혔다 펼쳐진다
        pipes.append(Pipeline(sub, namespace=k, inputs={"ship_sources", "raw_orders"},
                              outputs={"result": f"{k}_result", "asof_inputs": f"{k}_asof_inputs",
                                       **{f"op_model_h{h}": f"{k}_op_model_h{h}" for h in T.HORIZONS}}))
        results.append(f"{k}_result"); asofs.append(f"{k}_asof_inputs")
        models += [f"{k}_op_model_h{h}" for h in T.HORIZONS]
    nodes += [node(T.assemble_report, results + asofs, "ship_orders_team_report", name="assemble_report"),
              node(publish_report, "ship_orders_team_report", "ship_orders_report", name="publish_report"),
              node(T.save_models, ["ship_orders_team_report"] + models, "ship_models", name="save_operational_models"),
              node(track_report, ["ship_orders_report", "ship_models"], "ship_orders_tracking", name="track_mlflow")]
    return Pipeline(nodes[:2]) + sum(pipes, Pipeline([])) + Pipeline(nodes[2:])


def create_preprocess_pipeline() -> Pipeline:
    """원자료 → processed → 선종별 마스터 테이블 (팀 scripts/전처리, 원자료가 있는 Drive 전체 사본에서만 실행)."""
    from . import team_nodes as T
    nodes = [node(T.check_raw, None, ["raw_orders_file", "raw_external_dir"], name="check_raw_sources"),
             node(T.order_article_fill, "raw_orders_file", "raw_orders_article_filled", name="order_article_fill"),
             node(T.order_zero_fill, "raw_orders_article_filled", "raw_orders_zero_filled", name="order_zero_fill"),
             node(T.order_processed, "raw_orders_zero_filled", "processed_orders_by_type", name="order_processed_by_type")]
    outs = ["processed_orders_by_type"]
    for name, ds in T.PREPROCESS.items():
        nodes.append(node(T._preprocess_node(name), "raw_external_dir", ds, name=f"preprocess_{ds[len('processed_'):]}"))
        outs.append(ds)
    nodes.append(node(T.build_master, outs, "master_tables_by_type", name="build_master_tables"))
    return Pipeline(nodes)


def create_track_pipeline() -> Pipeline:
    """보고서는 그대로 두고 MLflow 기록만 — MLflow 서비스 시작 때 쓴다(빌드 때 만든 보고서를 기록)."""
    return Pipeline([node(track_report, None, "ship_orders_tracking", name="ship_orders_track_only")])
