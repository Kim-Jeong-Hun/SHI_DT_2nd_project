"""Airflow 실행 현황 → Neon PostgreSQL 스냅샷 (통합 관제 /ship/ops 의 '워크플로' 탭이 읽는다)

Airflow 본체는 무료 512MB 웹에 올릴 수 없어 로컬 WSL 에서만 돈다. 대신 상태가 바뀔 때마다
로컬 메타 DB(Docker PostgreSQL, DB명 airflow)에서 DAG · 태스크 연결 · 최근 실행을 읽어
대상 DB 의 airflow_status.snapshot 한 줄(JSON)로 덮어쓴다. 웹은 그 한 줄만 읽는다(읽기 전용).

  원천: AIRFLOW__DATABASE__SQL_ALCHEMY_CONN (airflow.env)
  대상: AIRFLOW_STATUS_DB_URL — 환경 변수 또는 프로젝트 .env (Neon 접속 주소, 저장소에 넣지 않음)

공개 화면에 나가므로 명령어 · 경로 · 사용자 이름은 담지 않고 ID · 상태 · 시각만 담는다.
직접 실행: python airflow/plugins/shi_status_sync.py   (airflow.env 를 source 한 셸에서)
"""
import json
import logging
import os
import re
import zlib
from datetime import datetime, timezone
from pathlib import Path

import psycopg2

log = logging.getLogger(__name__)
RUNS_PER_DAG = 12
PROJECT_DIR = Path(os.environ.get("SHI_PROJECT_DIR", Path(__file__).resolve().parents[2]))

DDL = """
CREATE SCHEMA IF NOT EXISTS airflow_status;
CREATE TABLE IF NOT EXISTS airflow_status.snapshot (
  id smallint PRIMARY KEY,
  synced_at timestamptz NOT NULL,
  payload jsonb NOT NULL
);
"""


def _dsn(url: str) -> str:
    return re.sub(r"^postgres(ql)?(\+\w+)?://", "postgresql://", url)


def _dotenv() -> dict:
    env = PROJECT_DIR / ".env"
    if not env.exists():
        return {}
    return dict(line.split("=", 1) for line in env.read_text(encoding="utf-8").splitlines()
                if "=" in line and not line.lstrip().startswith("#"))


def target_url() -> str | None:
    return os.environ.get("AIRFLOW_STATUS_DB_URL") or _dotenv().get("AIRFLOW_STATUS_DB_URL", "").strip() or None


def source_url() -> str | None:
    """Airflow 3 태스크 프로세스는 SQL_ALCHEMY_CONN 을 'airflow-db-not-allowed:///' 로 막아 두므로, 그때는 .env 로 같은 주소를 만든다"""
    conn = os.environ.get("AIRFLOW__DATABASE__SQL_ALCHEMY_CONN", "")
    if conn.startswith("postgres"):
        return conn
    e = _dotenv()
    if all(k in e for k in ("POSTGRES_USER", "POSTGRES_PASSWORD", "AIRFLOW_DB")):
        return f"postgresql://{e['POSTGRES_USER']}:{e['POSTGRES_PASSWORD']}@localhost:5432/{e['AIRFLOW_DB']}"
    return None


def _iso(t):
    return t.astimezone(timezone.utc).isoformat() if t else None


def _tasks(data: dict) -> list[dict]:
    """직렬화된 DAG 에서 태스크와 선행 관계만 뽑아 위상 순서로 정렬"""
    raw = [t.get("__var", t) for t in data["dag"]["tasks"]]
    up = {t["task_id"]: [] for t in raw}
    for t in raw:
        for d in t.get("downstream_task_ids") or []:
            up.setdefault(d, []).append(t["task_id"])
    kind = {t["task_id"]: t.get("task_type") or t.get("_task_type") for t in raw}
    order, seen = [], set()

    def visit(tid):
        if tid in seen:
            return
        seen.add(tid)
        for u in sorted(up[tid]):
            visit(u)
        order.append(tid)

    for tid in sorted(up):
        visit(tid)
    return [{"id": t, "type": kind.get(t), "upstream": sorted(up[t])} for t in order]


def build(cur, override: dict | None = None) -> dict:
    cur.execute("""SELECT dag_id, description, is_paused, timetable_summary, timetable_description,
                          next_dagrun, has_import_errors
                     FROM dag WHERE NOT is_stale ORDER BY dag_id""")
    dags = []
    for dag_id, desc, paused, sched, sched_desc, nxt, import_err in cur.fetchall():
        cur.execute("""SELECT data, data_compressed FROM serialized_dag
                        WHERE dag_id=%s ORDER BY created_at DESC LIMIT 1""", (dag_id,))
        row = cur.fetchone()
        data = None
        if row:
            data = row[0] if row[0] is not None else json.loads(zlib.decompress(bytes(row[1])))
        cur.execute("""SELECT run_id, run_type, state, triggered_by, queued_at, start_date, end_date
                         FROM dag_run WHERE dag_id=%s
                        ORDER BY COALESCE(run_after, logical_date, queued_at) DESC LIMIT %s""", (dag_id, RUNS_PER_DAG))
        runs = [{"run_id": r[0], "type": r[1], "state": (override or {}).get((dag_id, r[0]), r[2]), "by": r[3],
                 "queued": _iso(r[4]), "start": _iso(r[5]), "end": _iso(r[6]), "tasks": {}} for r in cur.fetchall()]
        if runs:
            cur.execute("""SELECT run_id, task_id, state, try_number, start_date, end_date, duration
                             FROM task_instance WHERE dag_id=%s AND run_id = ANY(%s) AND map_index=-1""",
                        (dag_id, [r["run_id"] for r in runs]))
            by_run = {r["run_id"]: r for r in runs}
            for run_id, task_id, state, tries, s, e, dur in cur.fetchall():
                state = (override or {}).get((dag_id, run_id, task_id), state)
                by_run[run_id]["tasks"][task_id] = {"state": state, "try": tries, "start": _iso(s),
                                                    "end": _iso(e), "sec": round(dur, 1) if dur else None}
        dags.append({"dag_id": dag_id, "description": desc, "paused": paused, "schedule": sched,
                     "schedule_text": sched_desc, "next_run": _iso(nxt), "import_error": import_err,
                     "tags": sorted((data or {}).get("dag", {}).get("tags") or []),
                     "tasks": _tasks(data) if data else [], "runs": runs})
    return {"synced_at": datetime.now(timezone.utc).isoformat(), "source": "local-wsl-airflow", "dags": dags}


def sync(override: dict | None = None) -> bool:
    """스냅샷을 만들어 대상 DB 에 덮어쓴다. 실패해도 예외를 밖으로 내지 않는다(태스크를 깨뜨리지 않게).
    override: 이벤트 시점에 아직 커밋 전인 상태 — {(dag_id, run_id): 실행 상태, (dag_id, run_id, task_id): 태스크 상태}"""
    url = target_url()
    src = source_url()
    if not url or not src:
        log.info("shi_status_sync: 대상(AIRFLOW_STATUS_DB_URL) 또는 원천 DB 설정이 없어 건너뜀")
        return False
    try:
        with psycopg2.connect(_dsn(src), connect_timeout=5) as s, s.cursor() as cur:
            payload = build(cur, override)
        with psycopg2.connect(_dsn(url), connect_timeout=10) as t, t.cursor() as cur:
            cur.execute(DDL)
            cur.execute("""INSERT INTO airflow_status.snapshot (id, synced_at, payload) VALUES (1, now(), %s)
                           ON CONFLICT (id) DO UPDATE SET synced_at=EXCLUDED.synced_at, payload=EXCLUDED.payload""",
                        (json.dumps(payload, ensure_ascii=False),))
        return True
    except Exception as e:   # noqa: BLE001 — 관제 동기화 실패가 파이프라인을 멈추면 안 된다
        log.warning("shi_status_sync 실패: %s", e)
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("synced" if sync() else "skipped/failed")
