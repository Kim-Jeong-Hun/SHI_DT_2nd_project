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

Kedro 에는 선박 수주 파이프라인 5개(`ship_orders` · `ship_orders_preprocess` · `ship_orders_track` · `ship_pulse` · `ship_pulse_track`)가 등록돼 있습니다. 이 저장소는 선박 수주 예측 프로젝트만 다룹니다.
분석 코드(`scripts/` · `src/`)는 저장소 루트에 있어 따로 지정하지 않아도 찾습니다. Drive 사본을 쓰려면 `SHIP_ORDERS_REPO` 로 지정합니다.

## Ship Pulse 재학습 파이프라인 (`ship_pulse`)

기준은 서비스(대시보드)다. 서비스 런타임 `deploy/render/custom_forecast.py` · `custom_runtime/`(최종 변수 · 모형 · 학습 창 · 최신 마스터)을 **고치지 않고 그대로 불러** 같은 모델로 재학습한다.

1. `kedro run --pipeline=ship_pulse` — 선종 5개 × (서비스 런타임 데이터 → Test 24개월 평가(ASE) → 7~12월 재예측 · 최종 모델 저장). 과거 기준월의 예측(Test · 7~12월 재현)은 **기준월까지의 자료와 목표값만** 학습한다 — 기준월 뒤 수주 실적은 쓰지 않는다. 최신 기준월 최종 모델만 지금까지 확정된 실적 전체로 학습한다.
2. 결과: `data/07_model_output/ship_pulse/` — 용도별로 나눈다.
   - `retrained_forecasts.json`: 이 파이프라인이 재학습해 만든 전망(공식 출력)
   - `dashboard_reference.json`: 대시보드 기준값 사본(`frontend/src/data/notebookForecasts.ts` → `reference.json`, 비교용 입력 · 모델 출력 아님)
   - `comparison.json`: 둘의 월별 차이(%) · `results.json`: 선종별 상세(Test 표 · 지표)
3. `MLFLOW_TRACKING_URI`가 있으면 실험 `ship_pulse`에 기록하고 서비스 최종 모델을 `ship_pulse_<선종>`으로 등록(alias `production`).
   - 등록 모델 버전마다 결과 지문 `results_sha`(results.json 기준)와 `parent_run_id` 태그를 남긴다.
   - 다섯 모델이 모두 등록된 뒤에만 alias 를 한꺼번에 옮긴다. 중간에 실패하면 `production` 은 예전 모델 그대로이고 작업은 실패한다(실행은 FAILED).
   - 같은 결과로 다시 돌리면, `FINISHED` 실행이 있고 다섯 alias 가 모두 지금 지문의 모델을 가리킬 때만 건너뛴다. 아니면(실패한 실행 · 빠진 alias · 다른 결과의 alias) 처음부터 다시 등록해 복구한다.
   - `scripts/mlflow_registry_check.py` 는 다섯 alias 가 있고 지금 results.json 지문의 모델인지 확인해, 아니면 종료 코드 1.
4. 재학습 값은 대시보드 값과 다르다(대시보드 값을 복사하지 않는다). 차이는 `comparison.json` 에서 본다. 가스 운반선 VECM 은 statsmodels 가 있어야 노트북과 같은 경로로 계산된다(없으면 런타임 대체 경로).
5. 테스트: `python -m pytest tests -q` (mlops 폴더) — 시점 누수(기준월 뒤 목표값을 바꿔도 예측 불변), 선종 5개 출력, 재학습/기준 출력 분리, MLflow 등록 · alias 실패, 같은 결과 재시도 복구, 예전 결과 alias 로 통과하지 않음. PR 마다 GitHub Actions `MLOps tests` 가 돌린다.

### Docker 없이 로컬에서 Airflow → Kedro → MLflow 확인 (`shi_ship_pulse_local`)

1. 서비스 런타임(`deploy/render/custom_runtime/data/master`)의 마스터 5개를 그대로 쓴다(따로 둘 필요 없음).
2. WSL Airflow 환경에서 `SHI_PROJECT_DIR=/mnt/c/.../SHI_DT_2nd_project/mlops`, `AIRFLOW__CORE__DAGS_FOLDER=$SHI_PROJECT_DIR/airflow/dags` 로 맞춘다.
3. `airflow dags test shi_ship_pulse_local` — 마스터 확인 → `kedro run --pipeline=ship_pulse`(Windows Python) → 결과 점검(대시보드와 차이 %) → MLflow 등록 확인.
4. MLflow 화면: `mlflow ui --backend-store-uri sqlite:///data/09_tracking/mlflow.db --port 5001` (mlops 폴더에서). Kedro 구조: `kedro viz run --pipeline=ship_pulse`.
