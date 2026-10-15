# mlops — 선박 수주 예측 운영 파이프라인 (Kedro · MLflow · Airflow)

팀 분석 코드(수주예측)를 매달 다시 돌려 운영 보고서와 서빙을 갱신하는 인프라 부분입니다. 담당: 최현서.

## 흐름

```
Airflow(WSL) ── shi_ship_order_pipeline (매월 5일 06:00)
  ├─ docker_containers_up : docker compose up -d --wait
  ├─ kedro_ship_orders    : docker exec shi-app kedro run --pipeline=ship_orders
  │     공통 입력 → 선종 5 × (평가 프레임 → 고정 선택 → 2026 평가 · 1·3·6개월 선행예측 · 운영 모델)
  │     → 보고서 → 운영 모델 저장 → MLflow 실행·모델 기록
  └─ check_serving_api    : /ship/meta 응답 확인
Airflow 리스너 플러그인 → 실행 상태를 Postgres(Neon)로 동기화 → 웹 관제 '워크플로' 탭
```

## 폴더

| 경로 | 내용 |
|---|---|
| `src/shi_dt/pipelines/ship_orders/` | Kedro 파이프라인 (팀 `2026_독립검증.py` 를 노드로 분해) |
| `src/shi_dt/ship/` | 서빙용 예측 조회 서비스 |
| `conf/base/` | Kedro 설정 |
| `airflow/dags/shi_ship_order_pipeline.py` | 월간 DAG |
| `airflow/plugins/` | 실행 상태를 DB로 보내는 리스너 (관제 화면용) |
| `airflow/install_airflow_wsl.sh` | WSL2 에 Airflow standalone 설치 |
| `docker-compose.yml`, `docker/` | app(Kedro·MLflow·서빙) + db(PostgreSQL) 컨테이너 |
| `deploy/render/` | Render 배포본 (FastAPI `web.py`, MLflow 프록시, Kedro-Viz 정적 페이지, 팀 코드 사본 `team/`) |
| `serving/static/` | 서빙 화면 (3D 관제 · 관제 콘솔 · 통합 관제 · 발표 릴 · 워크플로) |

## 데이터 준비

데이터는 저장소에 넣지 않습니다(원본: 팀 구글 드라이브 `Ship orders forcasting`).
파이프라인은 `SHIP_ORDERS_REPO`(기본 `deploy/render/team`) 아래 `data/raw/수주실적.csv` · `data/processed/…` 를 읽으므로,
실행 전에 드라이브의 `data/` 폴더를 `deploy/render/team/data/` 로 복사합니다.

## 실행

```bash
cp .env.example .env            # 값 바꾸기 (.env 는 커밋 금지)
docker compose up -d --build    # app :5000 MLflow UI · :8000 서빙
docker exec shi-app kedro run --pipeline=ship_orders
```

Airflow 는 WSL 에서 `airflow/install_airflow_wsl.sh` 로 설치하고, DAG 가 이 폴더를 찾도록 `SHI_PROJECT_DIR` 을 이 `mlops` 폴더 경로로 지정합니다.
관제 탭으로 상태를 보내려면 `AIRFLOW_STATUS_DB_URL` 을 환경 변수로만 넣습니다(저장소에 값 넣지 않음).

Kedro 에는 선박 수주 파이프라인 3개(`ship_orders` · `ship_orders_preprocess` · `ship_orders_track`)만 등록돼 있습니다. 이 저장소는 선박 수주 예측 프로젝트만 다룹니다.

## Ship Pulse 재학습 파이프라인 (`ship_pulse`)

Ship Pulse(shipulse.vercel.app)의 선종별 최종 설정(`frontend/src/data/notebookForecasts.ts`)으로 다시 학습하고 MLflow에 등록한다.

1. 마스터 테이블 5개를 `data/01_raw/ship_pulse/master/`에 둔다(Drive `Ship orders forcasting/data/master`). 다른 곳이면 `SHIP_PULSE_MASTER_DIR`.
2. `kedro run --pipeline=ship_pulse` — 선종 5개 × (CCF 수준·변화량 시차 → 약한 변수·VIF 10·퍼뮤테이션 Top-N → 롤링 검증 3개월 × 17창 → Test 24개월 → 다음 분기 예측 · 90% 블록 conformal).
3. 결과: `data/07_model_output/ship_pulse/` — `results.json`, Ship Pulse 형식 `notebook_forecasts.json`, 팀 값 대조 `comparison.json`.
4. `MLFLOW_TRACKING_URI`가 있으면 실험 `ship_pulse`에 기록하고 모델 `ship_pulse_<선종>`을 등록(alias `production`).

지표는 팀 결정대로 ASE(3개월 누적 오차의 절댓값)를 쓴다. 노트북 원본(`수주예측(선종)_WAPE_3M`)의 세부 변수 가공·튜닝이 없어서 숫자는 팀 값과 다를 수 있고, `comparison.json`에 차이를 남긴다.
