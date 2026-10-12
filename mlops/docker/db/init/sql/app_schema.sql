-- =====================================================================
-- 미니프로젝트2 서비스 DB 스키마 (PostgreSQL 15+)
-- 작성: 최현서 (인프라) · 2026-09-30 · 상태: 제안 (팀 합의 전)
--
-- 설계 원칙
--   1. 주제와 무관한 공통 뼈대: 사용자 / 모델 버전 / 예측 요청·결과 / 피드백 / 감사 로그
--   2. 주제별 입력·출력은 JSONB 로 저장 → 주제가 바뀌어도 스키마 변경 없음
--   3. 모델 버전을 모든 예측에 기록 → "어떤 모델이 이 답을 냈나" 추적 (재현성)
--   4. 공간 데이터가 필요한 주제(해상 조난)만 PostGIS 확장 사용 (선택 블록)
-- =====================================================================

CREATE SCHEMA IF NOT EXISTS app;
SET search_path TO app, public;

-- 사용자 (개요서: 서비스 사용자 등록 정보)
CREATE TABLE IF NOT EXISTS users (
    user_id       BIGSERIAL PRIMARY KEY,
    email         TEXT        NOT NULL UNIQUE,
    display_name  TEXT        NOT NULL,
    role          TEXT        NOT NULL DEFAULT 'user' CHECK (role IN ('user', 'admin')),
    password_hash TEXT        NOT NULL,                 -- bcrypt 등 해시만 저장, 평문 금지
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 모델 버전 레지스트리 (MLflow 없이도 "어떤 모델이 배포됐나" 관리)
CREATE TABLE IF NOT EXISTS model_versions (
    model_id      SERIAL PRIMARY KEY,
    topic         TEXT        NOT NULL,                 -- 예: 'nsr', 'welding', 'paint'
    name          TEXT        NOT NULL,                 -- 예: 'nsr_hgb_lead30'
    version       TEXT        NOT NULL,                 -- 예: '2026-10-05.1'
    artifact_path TEXT        NOT NULL,                 -- joblib 파일 경로/URL
    sha256        CHAR(64)    NOT NULL,                 -- 아티팩트 무결성 확인
    metrics       JSONB       NOT NULL DEFAULT '{}',    -- 예: {"MAE": 0.119, "lead_days": 30}
    is_active     BOOLEAN     NOT NULL DEFAULT FALSE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (topic, name, version)
);
-- 주제별 활성 모델은 하나만
CREATE UNIQUE INDEX IF NOT EXISTS ux_model_active_per_topic
    ON model_versions (topic) WHERE is_active;

-- 예측 요청과 결과 (서비스 로그의 핵심)
CREATE TABLE IF NOT EXISTS predictions (
    prediction_id BIGSERIAL PRIMARY KEY,
    user_id       BIGINT      REFERENCES users (user_id) ON DELETE SET NULL,
    model_id      INT         NOT NULL REFERENCES model_versions (model_id),
    input         JSONB       NOT NULL,                 -- 예: {"current": 210, "voltage": 25, "speed": 5.2}
    output        JSONB       NOT NULL,                 -- 예: {"defect_prob": 0.83, "recommend": {...}}
    latency_ms    INT         CHECK (latency_ms >= 0),
    status        TEXT        NOT NULL DEFAULT 'ok' CHECK (status IN ('ok', 'invalid_input', 'error')),
    error_message TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_pred_created   ON predictions (created_at DESC);
CREATE INDEX IF NOT EXISTS ix_pred_model     ON predictions (model_id, created_at DESC);
CREATE INDEX IF NOT EXISTS ix_pred_input_gin ON predictions USING GIN (input jsonb_path_ops);

-- 사용자 피드백 (예측이 맞았는지 → 추후 재학습·오류 분석 근거)
CREATE TABLE IF NOT EXISTS feedback (
    feedback_id   BIGSERIAL PRIMARY KEY,
    prediction_id BIGINT      NOT NULL REFERENCES predictions (prediction_id) ON DELETE CASCADE,
    user_id       BIGINT      REFERENCES users (user_id) ON DELETE SET NULL,
    is_correct    BOOLEAN,
    actual_label  TEXT,
    comment       TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_feedback_pred ON feedback (prediction_id);

-- 감사 로그 (로그인, 모델 활성화 변경 등 관리 행위)
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id   BIGSERIAL PRIMARY KEY,
    user_id    BIGINT      REFERENCES users (user_id) ON DELETE SET NULL,
    action     TEXT        NOT NULL,
    detail     JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- 대시보드용 뷰: 모델별 일별 요청 수·평균 지연·오류율
CREATE OR REPLACE VIEW v_daily_model_usage AS
SELECT m.topic,
       m.name,
       m.version,
       date_trunc('day', p.created_at)                    AS day,
       count(*)                                           AS requests,
       round(avg(p.latency_ms))                           AS avg_latency_ms,
       round(avg((p.status <> 'ok')::int)::numeric, 4)    AS error_rate
FROM predictions p
JOIN model_versions m USING (model_id)
GROUP BY m.topic, m.name, m.version, date_trunc('day', p.created_at);

-- 대시보드용 뷰: 피드백 기반 모델 정확도 (운영 중 성능 추적)
CREATE OR REPLACE VIEW v_model_feedback_accuracy AS
SELECT m.topic,
       m.name,
       m.version,
       count(f.feedback_id)                               AS n_feedback,
       round(avg(f.is_correct::int)::numeric, 4)          AS accuracy
FROM feedback f
JOIN predictions p USING (prediction_id)
JOIN model_versions m USING (model_id)
WHERE f.is_correct IS NOT NULL
GROUP BY m.topic, m.name, m.version;

-- =====================================================================
-- [선택] 공간 데이터 주제용 (시트 순번 2 해상 조난사고)
--   - 클라우드타입 PostgreSQL 템플릿에서 PostGIS 확장 사용 가능 여부는 배포 전 확인 필요
--   - 확장이 없으면 이 블록은 건너뛰고 위도·경도 NUMERIC 컬럼으로 대체
-- =====================================================================
-- CREATE EXTENSION IF NOT EXISTS postgis;
-- CREATE TABLE IF NOT EXISTS incidents (
--     incident_id   BIGSERIAL PRIMARY KEY,
--     occurred_at   TIMESTAMPTZ NOT NULL,
--     incident_type TEXT        NOT NULL,
--     weather       TEXT,
--     cause         TEXT,
--     geom          geography(Point, 4326) NOT NULL
-- );
-- CREATE INDEX IF NOT EXISTS ix_incidents_geom ON incidents USING GIST (geom);
-- -- 예: 입력 좌표 반경 20km 안의 과거 사고 유형 분포
-- -- SELECT incident_type, count(*) FROM incidents
-- --  WHERE ST_DWithin(geom, ST_MakePoint(:lon, :lat)::geography, 20000)
-- --  GROUP BY incident_type ORDER BY 2 DESC;

-- =====================================================================
-- 관제 로그 (ops) — 관제 화면 이벤트를 운항 빅데이터로 적재
--   흐름: 관제 화면 → 서빙 API POST /ops/events → ① 공유 볼륨 원본 data/01_raw/ops_logs/*.jsonl (추가만)
--                                               ② 이 테이블 (조회·집계)
--   Kedro ops_logs 파이프라인이 원본을 구간·일 단위 병목 표와 항차 결과 표로 만들어 재학습 특성으로 쓴다.
--   스키마 버전: ops.control_events/v1 (src/shi_dt/ops_log.py 와 1:1)
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS ops;

CREATE TABLE IF NOT EXISTS ops.control_events (
    event_id    BIGSERIAL PRIMARY KEY,
    session     TEXT        NOT NULL,                     -- 관제 화면 세션 (브라우저 1회 접속)
    source      TEXT        NOT NULL DEFAULT 'control-ui',
    ts_wall     TIMESTAMPTZ NOT NULL,                     -- 이벤트가 생긴 실제 시각
    ts_sim      TIMESTAMPTZ,                              -- 관제 화면 속 운항 시각 (해빙 관측일 기준)
    type        TEXT        NOT NULL CHECK (type IN ('DEPART','ENTER_SEGMENT','ESCORT_REQUEST','ESCORT_JOIN','ESCORT_END',
                                                     'HOLD','RESUME','ARRIVE','ABORT','ICE_ALERT','OPERATOR_VIEW','OPERATOR_PLAN')),
    vessel      TEXT,
    voyage      INT,
    ship_type   TEXT,
    ice_class   TEXT,                                     -- 예: 'Arc4', 'Ice1~3'
    route       TEXT        CHECK (route IN ('NSR','NWP','TSR','') OR route IS NULL),
    direction   TEXT,                                     -- 'EB' 동행 / 'WB' 서행
    segment     TEXT,                                     -- 예: '카라해', '동시베리아해'
    km          REAL,                                     -- 항로 누적 거리
    x_km        REAL,                                     -- NSIDC 극좌표(EPSG:3411) km
    y_km        REAL,
    sic         REAL        CHECK (sic IS NULL OR sic BETWEEN 0 AND 100),   -- 항로 폭 75 km 안 해빙 농도 %
    status      TEXT,
    detail      TEXT,
    payload     JSONB       NOT NULL DEFAULT '{}',
    ingested_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ux_control_event UNIQUE (session, ts_wall, type, voyage, km)   -- 재전송·재적재 시 중복 방지
);
CREATE INDEX IF NOT EXISTS ix_ops_sim_brin ON ops.control_events USING BRIN (ts_sim);   -- 시계열 대량 적재에 가벼운 인덱스
CREATE INDEX IF NOT EXISTS ix_ops_route_seg ON ops.control_events (route, segment, type);
CREATE INDEX IF NOT EXISTS ix_ops_class ON ops.control_events (ice_class, type);

-- 구간별 병목: 일·해역·등급별 호위 요청·대기 횟수와 평균 해빙
CREATE OR REPLACE VIEW ops.v_segment_bottleneck AS
SELECT date_trunc('day', ts_sim)                               AS sim_day,
       route, segment, ice_class,
       count(*) FILTER (WHERE type = 'ESCORT_REQUEST')         AS escort_requests,
       count(*) FILTER (WHERE type = 'HOLD')                   AS holds,
       round(avg(sic)::numeric, 1)                             AS mean_sic
FROM ops.control_events
WHERE type IN ('ESCORT_REQUEST', 'HOLD', 'ENTER_SEGMENT')
GROUP BY 1, 2, 3, 4;

-- 항차 결과: 출항~도착 소요일 (세션·항차 단위)
CREATE OR REPLACE VIEW ops.v_voyage_outcome AS
SELECT session, voyage, max(vessel) AS vessel, max(ice_class) AS ice_class, max(route) AS route, max(direction) AS direction,
       min(ts_sim) FILTER (WHERE type = 'DEPART')                               AS departed,
       max(ts_sim) FILTER (WHERE type = 'ARRIVE')                               AS arrived,
       extract(epoch FROM max(ts_sim) FILTER (WHERE type = 'ARRIVE')
                        - min(ts_sim) FILTER (WHERE type = 'DEPART')) / 86400.0  AS days,
       count(*) FILTER (WHERE type = 'ESCORT_REQUEST')                          AS escort_requests,
       count(*) FILTER (WHERE type = 'HOLD')                                    AS holds
FROM ops.control_events
WHERE voyage IS NOT NULL
GROUP BY session, voyage;
