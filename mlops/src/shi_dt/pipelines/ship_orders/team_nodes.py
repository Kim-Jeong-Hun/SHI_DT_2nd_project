"""팀 파이프라인(ship_orders_forecasting)을 Kedro 노드 단위로 펼친다 — 계산은 팀 코드 그대로, 단계만 드러낸다.

이전에는 scripts/분석/2026_독립검증.py 를 subprocess 한 번으로 돌려 Kedro 화면에 노드 2개만 보였다.
여기서는 그 스크립트의 main() 이 하던 순서를 노드로 나눈다(같은 함수 · 같은 인자 · 같은 순서 → 같은 보고서).

  ship_orders_preprocess (원자료가 있는 팀 Drive 사본에서만 실행 — Docker 이미지에는 원자료가 없다)
    원자료 확인 → 수주실적 기사보완 → 결측보완 → 선종별 가공 · 외부지표 9종 전처리 → 선종별 마스터 테이블
  ship_orders (Docker 빌드 · Airflow 에서 실행)
    공통 입력 적재 → 선종 5개 × [평가 프레임 → 변수·모형 고정 선택 → 2026 월별 평가 · 수주 공표일 → 기준일 입력표
                     → 1·3·6개월 직접 선행예측(프레임 → 선택 → 2026 평가 · 2026-09-30 운영 예측)] → 보고서 → MLflow 기록
"""
from __future__ import annotations

import io
import json
import os
import sys
from contextlib import redirect_stdout
from functools import lru_cache
from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path

import pandas as pd

ROOT = Path(os.environ.get("SHI_PROJECT_DIR", Path(__file__).resolve().parents[4]))
REPO = Path(os.environ.get("SHIP_ORDERS_REPO", ROOT.parent / "ship-order-drive"))

# Kedro 노드 · 데이터셋 이름은 영문(Kedro-Viz 표시 · 네임스페이스 규칙), 화면 설명은 한글 주석
SHIP_KEYS = {"벌크선": "bulk", "케미컬 탱커": "chemical", "컨테이너선": "container", "가스 운반선": "gas", "유조선": "oil"}
HORIZONS = (1, 3, 6)
PREPROCESS = {   # 스크립트 이름 → 출력 데이터셋 (팀 scripts/전처리)
    "국제원자재가_전처리": "processed_commodities",
    "운임_현존선복량_전처리": "processed_freight_fleet",
    "신조선가_전처리": "processed_newbuilding_price",
    "지정학위험지수_전처리": "processed_geopolitical_risk",
    "무역정책불확실성지수_전처리": "processed_trade_policy_uncertainty",
    "싱가포르벙커유판매량_전처리": "processed_bunker_sales",
    "선박용벙커유_전처리": "processed_bunker_price",
    "공개글로벌월별지표_전처리": "processed_global_monthly",
    "물동량_전처리": "processed_cargo_volumes",
}


@lru_cache(maxsize=None)
def _team():
    """팀 평가 스크립트를 모듈로 불러온다(실행하지 않고 함수만)."""
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    path = REPO / "scripts" / "분석" / "2026_독립검증.py"
    spec = spec_from_file_location("ship_orders_team_eval", path)
    mod = module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _legacy(name: str):
    if str(REPO / "src") not in sys.path:
        sys.path.insert(0, str(REPO / "src"))
    from ship_orders_forecasting.legacy import legacy_module
    return legacy_module(name)


def _run_script_main(name: str) -> str:
    """팀 전처리 스크립트의 main() 을 인자 없이 실행(스크립트 단독 실행과 같음)하고 출력 요약을 돌려준다."""
    mod = _legacy(name)
    argv, sys.argv = sys.argv, [name]
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            mod.main()
    finally:
        sys.argv = argv
    return buf.getvalue()[-2000:]


# ---------------- 전처리 (원자료 → processed → master) ----------------
def check_raw() -> tuple:
    raw = REPO / "data" / "raw"
    if not (raw / "수주실적.csv").is_file():
        raise FileNotFoundError(f"원자료 없음: {raw} — 전처리는 팀 Drive 전체 사본에서만 실행합니다")
    return tuple(str(raw) for _ in range(2))   # 수주 원자료 · 외부지표 원자료 폴더


def order_article_fill(raw_orders: str) -> str:
    return _run_script_main("수주실적_기사보완")


def order_zero_fill(_after_article: str) -> str:
    return _run_script_main("수주실적_결측보완")


def order_processed(_after_zero: str) -> str:
    return _run_script_main("수주실적_전처리")


def _preprocess_node(name: str):
    def run(raw_external: str) -> str:
        return _run_script_main(name)
    run.__name__ = f"preprocess_{PREPROCESS[name]}"
    return run


def build_master(*_processed: str) -> str:
    return _run_script_main("마스터테이블_생성")


# ---------------- 평가 · 운영 예측 (팀 2026_독립검증.py main() 순서 그대로) ----------------
def load_sources() -> dict:
    return _team().inputs()


def load_raw_orders() -> pd.DataFrame:
    t = _team()
    return pd.read_csv(t.RULES.RAW_ORDERS_PATH, encoding="utf-8-sig", dtype=str, keep_default_na=False)


def _per_type(ship_type: str):
    t = _team

    def evaluation_frame(sources: dict):
        print(f"{ship_type}: 2026 이전 변수·모형 선택 중", flush=True)
        frame, external = t().evaluation_frame(ship_type, sources)
        return frame, external

    def frozen_choice(frame, external):
        return t().frozen_choice(ship_type, frame, external)

    def holdout_2026(frame, choice):
        return t().holdout(frame, choice)

    def publication(raw_orders):
        return t().publication_dates(raw_orders, t().RULES.RAW_VESSEL_TYPES[ship_type])

    def asof_inputs(frame, external, sources, published):
        asof = t().asof_input_table(ship_type, frame, external, sources, published)
        return json.loads(asof.to_json(orient="records", force_ascii=False))

    def assemble(choice, candidates, test, *direct):
        print(f"{ship_type}: {test['평가월수']}개월 | sMAPE {test['월별sMAPE']:.1%} | 기준선 {test['기준선sMAPE']:.1%}", flush=True)
        return {"선종": ship_type, "단위": t().RULES.TARGET_UNITS[ship_type], "선택": choice, "개발후보": candidates,
                "2026평가": test, "직접선행예측": list(direct)}

    fns = {"evaluation_frame": evaluation_frame, "frozen_choice": frozen_choice, "holdout_2026": holdout_2026,
           "publication_dates": publication, "asof_inputs": asof_inputs, "assemble_result": assemble}
    for h in HORIZONS:
        def d_frame(frame, published, h=h):
            print(f"{ship_type}: {h}개월 직접 선행예측 검증 중", flush=True)
            return t().direct_frame(frame, published, h, point_lags=True)

        def d_select(direct, published, h=h):
            return t().select_direct(direct, published, h, point_lags=True)

        def d_eval(direct, published, choice_cands, h=h):
            choice, cands = choice_cands
            return {"선행개월": h, "선택": choice, "개발후보": cands,
                    "2026평가": t().test_direct(direct, published, choice),
                    "2026-09-30_실제운영예측": t().future_direct(direct, published, choice)}
        def op_model(direct, published, choice_cands, h=h):
            return operational_model(ship_type, h, direct, published, choice_cands)
        fns[f"direct_frame_h{h}"], fns[f"direct_select_h{h}"], fns[f"direct_eval_h{h}"] = d_frame, d_select, d_eval
        fns[f"operational_model_h{h}"] = op_model
    for k, f in fns.items():
        f.__name__ = k
    return fns


def assemble_report(*parts) -> dict:
    """선종별 결과 · 기준일 입력표를 팀 스크립트와 같은 형식의 보고서로 묶어 저장한다."""
    t = _team()
    n = len(SHIP_KEYS)
    results, asof_lists = list(parts[:n]), parts[n:]
    asof_tables = [row for rows in asof_lists for row in rows]
    order = {s: i for i, s in enumerate(t.RULES.SHIP_TYPES)}
    results.sort(key=lambda r: order[r["선종"]])
    report = {
        "평가기간": "2026-01~2026-08",
        "방법": "2025년까지 이용 가능한 수주 라벨로 2022~2025 연도별 fold 선택; "
                "선택된 변수·모형을 고정하고 2026년은 월별 재학습만 수행",
        "물동량": "2026 잠정 글로벌 합계는 개발·보류구간 모두 피처에서 제외",
        "제약": "외부지표의 당시 발표 빈티지는 복원하지 못한 후향적 평가. "
                "2026-01은 수주 월보 게시일 미상인 t-3 근사이므로 게시일확인월 점수를 별도 표기. "
                "컨테이너선 단일월 시차 설계는 2026년 결과를 이미 확인한 뒤 변경했으므로 "
                "새 설계의 2026년 점수는 독립 테스트가 아닌 개발 진단.",
        "기준일입력": asof_tables,
        "선행예측방법": "1·3·6개월 모델은 목표월에서 각각 1·3·6개월 전 월말에 게시된 수주 이력만 입력. "
                    "과거 미상 게시일은 t-3 근사로 명시하며, 실제 2026-09-30 예측에는 게시일 확인 수주만 사용. "
                    "컨테이너선은 누적합 대신 최신 확정월 기준 1·2·3번째 단일 월 값을 후보로 사용. "
                    "2026년 1~8월 라벨은 코드의 변수·모형 재선택에 사용하지 않음.",
        "결과": results,
    }
    t.OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    t.OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return report


# ---------------- 운영 모델 (MLflow Models 화면용) ----------------
MODELS_DIR = ROOT / "data" / "06_models" / "ship"


def operational_model(ship_type: str, horizon: int, direct: pd.DataFrame, published: pd.Series, choice_cands) -> dict:
    """팀 future_direct() 가 2026-09-30 운영 예측 때 학습하는 모델을 그대로 다시 학습해 돌려준다(예측값이 보고서와 같아야 함).

    future_direct 는 예측값만 남기고 학습한 모델 객체는 버리므로, 같은 학습 행 · 피처 · 모형 · 시드로 다시 맞춘다.
    """
    _team()
    of = sys.modules["ship_orders_forecasting.operational_forecast"]
    from ship_orders_forecasting.modeling import TARGET, model_for
    choice = choice_cands[0]
    origin = pd.Timestamp("2026-09-30")
    target = (origin.to_period("M") + horizon).to_timestamp()
    base = {"선종": ship_type, "선행개월": horizon, "목표월": target.strftime("%Y-%m"), "예측기준일": "2026-09-30",
            "선택피처": choice.get("피처"), "선택모형": choice.get("모형")}
    history = of.order_history(direct, published, origin, allow_undated_history=False)
    ranked = choice.get("운영대체우선순위", [{"피처": choice["피처"], "모형": choice["모형"]}])
    for cand in ranked:
        feature = cand["피처"]
        if pd.isna(direct.at[target, feature]) or not direct.at[target, f"{feature}_게시일확인"]:
            continue
        train = direct.loc[direct.index.isin(history.index) & (direct.index < target), [TARGET, feature]].dropna()
        if len(train) < of.MIN_TRAIN:
            continue
        out = {**base, "운영피처": feature, "운영모형": cand["모형"], "학습관측월": len(train),
               "학습시작월": train.index.min().strftime("%Y-%m"), "학습종료월": train.index.max().strftime("%Y-%m")}
        x_target = direct.loc[[target], [feature]]
        if cand["모형"] == of.BASELINE_MODEL:
            return {**out, "estimator": None, "예측": float(direct.at[target, of.BASELINE]), "입력": x_target}
        est = model_for(cand["모형"], 42)
        est.fit(train[[feature]], train[TARGET])
        return {**out, "estimator": est, "예측": max(0.0, float(est.predict(x_target)[0])), "입력": x_target,
                "학습입력예시": train[[feature]].tail(3)}
    return {**base, "estimator": None, "예측": None, "상태": "게시일확인 입력 또는 학습행 부족"}


def save_models(report: dict, *models: dict) -> dict:
    """운영 모델 15개(선종 5 × 1·3·6개월)를 MLflow 모델 형식으로 저장 — MLflow 서비스 시작 때 Models 화면에 기록된다.

    보고서의 운영 예측값과 다시 학습한 모델의 예측값이 다르면 멈춘다(팀 계산과 어긋나는 모델은 올리지 않음).
    """
    import shutil

    import mlflow.sklearn
    import sklearn
    want = {(r["선종"], d["선행개월"]): d["2026-09-30_실제운영예측"].get("예측")
            for r in report["결과"] for d in r["직접선행예측"]}
    if MODELS_DIR.exists():
        shutil.rmtree(MODELS_DIR)
    MODELS_DIR.mkdir(parents=True)
    index = []
    for m in models:
        key = f"{SHIP_KEYS[m['선종']]}_h{m['선행개월']}"
        exp = want.get((m["선종"], m["선행개월"]))
        same = (exp is None and m["예측"] is None) or (exp is not None and m["예측"] is not None and abs(exp - m["예측"]) <= 1e-6 * max(1.0, abs(exp)))
        if not same:
            raise ValueError(f"{key}: 보고서 운영 예측 {exp} ≠ 재학습 모델 예측 {m['예측']}")
        meta = {k: v for k, v in m.items() if k not in ("estimator", "입력", "학습입력예시")}
        meta["이름"] = key
        meta["보고서와_예측일치"] = True
        if m.get("estimator") is not None:
            mlflow.sklearn.save_model(m["estimator"], str(MODELS_DIR / key), input_example=m["학습입력예시"],
                                      pip_requirements=[f"scikit-learn=={sklearn.__version__}"],
                                      skops_trusted_types=["sklearn.tree._tree.Tree"])   # 랜덤 포레스트 내부 트리 — 팀 model_for() 가 만드는 표준 sklearn 타입
            meta["모델저장"] = True
        else:
            meta["모델저장"] = False   # 기준선(최근 평균) 선택 · 입력 부족 → 학습 모델 없음
        index.append(meta)
    (MODELS_DIR / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    return {"models": len(index), "saved": sum(i["모델저장"] for i in index), "dir": str(MODELS_DIR)}
