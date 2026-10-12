"""Render 웹 서빙(가벼운 이미지) — 선박 수주 예측 화면 + 예측 API만.

전체 앱(serving/app.py)은 북극항로 모델·Kedro·MLflow·PostgreSQL 로그까지 묶여 있어 무료 플랜(512MB)에 무겁다.
여기서는 같은 shi_dt.ship.service 로직과 같은 정적 화면을 그대로 쓰고, 데이터는 이미지에 넣은 보고서 스냅샷을 읽는다.
  /            → /ship/ops 로 이동
  /ship/ops    통합 관제 — 3D 전경 · 관제 콘솔 · Airflow 워크플로 · Kedro 파이프라인 · MLflow 실험 기록 · 발표 릴을 한 페이지에서 전환
  /kedro/      Kedro-Viz 파이프라인 화면 (빌드 때 kedro viz build 로 만든 정적 파일 — 실행 중 메모리 0)
  /ship        3D 수주 관제          /ship/console  관제 콘솔        /ship/reel  발표 스크롤 페이지
  /ship/meta   선종별 모델·평가      /ship/forecast?ship=…&horizon=1|3|6   /health
  /mlflow/     MLflow 화면 → 별도 서비스 ship-order-mlflow(읽기 전용)로 이동
  /airflow     워크플로 화면 — 로컬 WSL Airflow 가 Neon 에 남긴 실행 현황 스냅샷(/airflow/status)을 읽기 전용으로 표시
"""
import os
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from shi_dt.ship import service as SHIP

STATIC = Path(__file__).resolve().parent / "static"
if not STATIC.exists():   # 로컬 시험: 이미지 밖에서는 serving/static 을 그대로 쓴다
    STATIC = Path(__file__).resolve().parents[2] / "serving" / "static"
app = FastAPI(title="선(船)견지명 · 선박 수주 예측", docs_url="/docs")


def page(name: str) -> HTMLResponse:
    return HTMLResponse((STATIC / name).read_text(encoding="utf-8"), headers={"Cache-Control": "no-cache"})


@app.get("/health")
def health():
    return {"ok": True, "report": SHIP.REPORT.exists()}


@app.get("/")
def root():
    return RedirectResponse("/ship/ops")


@app.get("/ship/ops", response_class=HTMLResponse)
def ship_ops():
    return page("ship_ops.html")


KEDRO_VIZ = STATIC / "kedro"
if KEDRO_VIZ.exists():
    @app.get("/kedro", include_in_schema=False)
    def kedro_root():
        return RedirectResponse("/kedro/")
    app.mount("/kedro", StaticFiles(directory=KEDRO_VIZ, html=True), name="kedro")


@app.get("/ship", response_class=HTMLResponse)
def ship_page():
    return page("ship.html")


@app.get("/ship/console", response_class=HTMLResponse)
def ship_console():
    return page("ship_console.html")


@app.get("/ship/reel", response_class=HTMLResponse)
def ship_reel():
    return page("ship_reel.html")


@app.get("/ship/meta")
def ship_meta():
    return SHIP.meta()


@app.get("/ship/forecast")
def ship_forecast(ship: str = Query(..., description="선종: 컨테이너선 · 케미컬 탱커 · 유조선 · 벌크선 · 가스 운반선"),
                  horizon: int = Query(3, description="선행 개월: 1 · 3 · 6")):
    try:
        return SHIP.forecast(ship, horizon)
    except KeyError:
        raise HTTPException(400, f"선종은 {', '.join(SHIP.SHIPS)} 중 하나여야 합니다")
    except ValueError:
        raise HTTPException(400, "horizon은 1, 3, 6 중 하나여야 합니다")


# ---- MLflow 화면: 메모리(무료 512MB) 때문에 별도 서비스 ship-order-mlflow 가 띄운다 → 그쪽으로 이동 ----
MLFLOW_PUBLIC = os.environ.get("MLFLOW_PUBLIC_URL", "https://ship-order-mlflow.onrender.com")


@app.get("/mlflow")
@app.get("/mlflow/{path:path}")
def mlflow_redirect(path: str = ""):
    return RedirectResponse(f"{MLFLOW_PUBLIC.rstrip('/')}/mlflow/{path}")


# ---- 워크플로(Airflow) 화면: Airflow 본체는 로컬 WSL 에서만 돈다(512MB 초과) ----
# 로컬 리스너 플러그인(airflow/plugins/shi_status_sync.py)이 상태가 바뀔 때마다 Neon 에 스냅샷 한 줄을 쓰고, 여기서는 읽기만 한다
AIRFLOW_STATUS_DB = os.environ.get("AIRFLOW_STATUS_DB_URL")
_airflow_cache: dict = {"at": 0.0, "body": None}


@app.get("/airflow", response_class=HTMLResponse)
def airflow_page():
    return page("airflow.html")


@app.get("/airflow/status")
def airflow_status():
    if not AIRFLOW_STATUS_DB:
        return {"ok": False, "reason": "not_configured"}
    now = time.monotonic()
    if _airflow_cache["body"] is None or now - _airflow_cache["at"] > 20:   # Neon 왕복을 20초에 한 번으로
        import psycopg
        try:
            with psycopg.connect(AIRFLOW_STATUS_DB, connect_timeout=10) as c:
                row = c.execute("SELECT payload FROM airflow_status.snapshot WHERE id=1").fetchone()
            _airflow_cache["body"] = {"ok": True, **row[0]} if row else {"ok": False, "reason": "no_snapshot"}
        except psycopg.Error:
            if _airflow_cache["body"] is None:
                return {"ok": False, "reason": "db_unavailable"}
        _airflow_cache["at"] = now
    return _airflow_cache["body"]
