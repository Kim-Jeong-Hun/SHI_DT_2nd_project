"""MLflow 화면 서비스(ship-order-mlflow) — MLflow 앱을 한 프로세스 안에 올리고 조회만 통과시킨다.

무료 플랜 512MB 에서 `mlflow server`(CLI 부모 + uvicorn 자식 + 따로 둔 프록시)는 세 프로세스라 메모리가 넘쳐,
MLflow 의 FastAPI 앱을 직접 불러와 읽기 전용 미들웨어로 감싼 단일 uvicorn 프로세스로 띄운다.
조회(GET · 검색 POST · GraphQL query)만 통과, 기록·삭제는 403.
실행 전 환경변수: MLFLOW_TRACKING_URI(= Neon PostgreSQL, start.sh 가 만든다)
"""
import os
import re
import uuid

os.environ.setdefault("_MLFLOW_SERVER_FILE_STORE", os.environ.get("MLFLOW_TRACKING_URI", "sqlite:///mlflow.db"))
os.environ.setdefault("_MLFLOW_SERVER_ARTIFACT_ROOT", os.environ.get("MLFLOW_ARTIFACT_ROOT", "/app/mlartifacts"))
os.environ.setdefault("_MLFLOW_STATIC_PREFIX", "/mlflow")
os.environ.setdefault("_MLFLOW_SGI_NAME", "uvicorn")
os.environ.setdefault("_MLFLOW_SERVER_BOOT_ID", uuid.uuid4().hex)
# MLflow 3 보안 미들웨어는 기본이 localhost 전용 — 공개 주소(Render)를 허용 목록에 넣는다
os.environ.setdefault("MLFLOW_SERVER_ALLOWED_HOSTS", ",".join(filter(None, [
    os.environ.get("RENDER_EXTERNAL_HOSTNAME"), "ship-order-mlflow.onrender.com", "localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"])))

# MLflow 3 보안 미들웨어는 다른 Origin 의 POST(검색 포함)를 막는다 — 자기 자신 · 통합 관제 출처를 허용
os.environ.setdefault("MLFLOW_SERVER_CORS_ALLOWED_ORIGINS", ",".join(filter(None, [
    f"https://{os.environ['RENDER_EXTERNAL_HOSTNAME']}" if os.environ.get("RENDER_EXTERNAL_HOSTNAME") else None,
    "https://ship-order-mlflow.onrender.com", "https://ship-order-forecast.onrender.com",
    "http://localhost:5000", "http://127.0.0.1:5000"])))
# 통합 관제(ship-order-forecast /ship/ops)가 iframe 으로 띄울 수 있게 — X-Frame-Options 대신 CSP frame-ancestors 로 허용 출처만
os.environ.setdefault("MLFLOW_SERVER_X_FRAME_OPTIONS", "NONE")
FRAME_ANCESTORS = ("frame-ancestors 'self' " + os.environ.get("MLFLOW_FRAME_ANCESTORS",
                   "https://ship-order-forecast.onrender.com http://localhost:* http://127.0.0.1:*")).encode()

from mlflow.server.fastapi_app import app as _mlflow  # noqa: E402  (환경변수를 먼저 정해야 한다)

# 조회 POST 는 '마지막 경로 조각'으로 판정한다 — logged-models/search 처럼 경로 중간의 단어(logged)가 쓰기로 오인되지 않게
READ_LAST = re.compile(r"^(search|search-[a-z-]+|get|get-[a-z-]+|batch-get|list|list-[a-z-]+)$", re.I)
WRITE = re.compile(r"(create|delete|update|set-tag|log-batch|log-metric|log-param|log-model|log-inputs|log-outputs|rename|restore|transition|upload)", re.I)


async def _send_text(send, status, text, location=None):
    headers = [(b"content-type", b"text/plain; charset=utf-8")] + ([(b"location", location.encode())] if location else [])
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": text.encode()})


async def app(scope, receive, send):
    if scope["type"] != "http":
        return await _mlflow(scope, receive, send)

    async def send_csp(msg):
        if msg["type"] == "http.response.start":
            msg = {**msg, "headers": list(msg.get("headers", [])) + [(b"content-security-policy", FRAME_ANCESTORS)]}
        await send(msg)
    return await _guard(scope, receive, send_csp)


async def _guard(scope, receive, send):
    path, m = scope["path"], scope["method"]
    if path in ("/", "/mlflow"):
        return await _send_text(send, 307, "", "/mlflow/#/experiments")
    if path == "/health":
        return await _send_text(send, 200, '{"ok":true}')
    if m in ("GET", "HEAD"):
        return await _mlflow(scope, receive, send)
    if m != "POST":
        return await _send_text(send, 403, "공개 MLflow 화면은 조회만 허용합니다")
    # 본문을 읽어 판정한 뒤 그대로 다시 흘려보낸다
    body, more = b"", True
    while more:
        msg = await receive()
        body += msg.get("body", b"")
        more = msg.get("more_body", False)
    gql_read = path.rstrip("/").endswith("graphql") and not re.search(rb"mutation", body)   # 화면 조회용 GraphQL query 만
    last = path.rstrip("/").rsplit("/", 1)[-1]
    if not gql_read and (not READ_LAST.match(last) or WRITE.search(last)):
        return await _send_text(send, 403, "공개 MLflow 화면은 조회만 허용합니다")
    sent = False

    async def replay():
        nonlocal sent
        if sent:
            return await receive()
        sent = True
        return {"type": "http.request", "body": body, "more_body": False}
    return await _mlflow(scope, replay, send)
