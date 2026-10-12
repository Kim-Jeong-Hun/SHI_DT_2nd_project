# Render 웹 서비스 — 인프라 아키텍처(Kedro · MLflow · FastAPI)를 한 컨테이너로
#   빌드: 팀 파이프라인을 Kedro(ship_orders)로 실제 실행해 운영 보고서를 만든다
#   실행: deploy/render/start.sh — ROLE=web: FastAPI / ROLE=mlflow: Kedro 기록 → MLflow 서버 → 읽기 전용 입구
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    SHI_PROJECT_DIR=/app SHIP_ORDERS_REPO=/app/team PYTHONPATH=/app/src \
    MLFLOW_DISABLE_AGENT_HINT=1 KEDRO_DISABLE_TELEMETRY=true DO_NOT_TRACK=1
WORKDIR /app
COPY requirements.txt /app/requirements.txt
COPY deploy/render/requirements.txt /app/deploy/render/requirements.txt
RUN cd /app/deploy/render && pip install --no-cache-dir -r requirements.txt
# Kedro 프로젝트 (설정 · 파이프라인 · 서빙 화면)
COPY pyproject.toml /app/
COPY conf /app/conf
COPY src /app/src
COPY serving/static/ship.html serving/static/ship_console.html serving/static/ship_reel.html serving/static/ship_ops.html serving/static/airflow.html /app/deploy/render/static/
COPY deploy/render/web.py deploy/render/mlflow_proxy.py deploy/render/start.sh deploy/render/kedro_viz_static.py /app/deploy/render/
# 팀 파이프라인(ship-order-drive) 중 실행에 필요한 파일만
COPY deploy/render/team /app/team
RUN mkdir -p conf/local data/01_raw/ship mlartifacts && kedro run --pipeline=ship_orders \
    && test -s data/01_raw/ship/2026_독립검증.json \
    && SHI_PIPELINES=ship kedro viz build && python deploy/render/kedro_viz_static.py build deploy/render/static/kedro \
    && useradd -m web && chown -R web /app && chmod +x deploy/render/start.sh
USER web
EXPOSE 10000
CMD ["/app/deploy/render/start.sh"]
