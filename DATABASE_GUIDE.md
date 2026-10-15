# 데이터베이스 구조 안내

이 리포지토리는 PostgreSQL을 사용한다. 실제 웹 서비스가 사용하는 백엔드 스키마와 MLOps 환경에서 제안된 범용 운영 스키마가 함께 존재하며, 현재 Express API의 기준은 `backend/sql` 아래의 마이그레이션이다.

## 전체 구성

```text
PostgreSQL
├─ 선박·시장 데이터
│  ├─ vessel_types
│  ├─ monthly_orders
│  ├─ vessel_monthly_master
│  ├─ vessel_monthly_features
│  └─ vessel_monthly_source_rows
├─ 군집 분석 결과
│  ├─ cluster_models
│  ├─ cluster_monthly_assignments
│  └─ cluster_monthly_metrics
├─ 사용자·인증
│  ├─ app_users
│  ├─ oauth_accounts
│  ├─ auth_sessions
│  └─ oauth_login_attempts
└─ newsroom 스키마
   └─ articles
```

## 선박·시장 데이터

### `vessel_types`

선종 ID와 표시 이름을 저장하는 기준 테이블이다.

| ID | 선종 |
| --- | --- |
| `container` | 컨테이너선 |
| `tanker` | 유조선 |
| `bulk` | 벌크선 |
| `gas` | 가스 운반선 |
| `chemical` | 케미컬 탱커 |

### `vessel_monthly_master`

선종별 월간 마스터 데이터를 저장한다. 주요 값은 기준월, 수주용량, 단위, 정보 공개 시차, 출처 파일, 적재 시각이다. 수주용량 단위는 선종에 따라 `CBM`, `DWT`, `TEU`를 사용한다.

기본키는 `(vessel_type_id, period)`이므로 선종별로 한 달에 하나의 마스터 행만 존재한다.

### `vessel_monthly_features`

마스터 CSV의 수치형 변수를 `선종 + 기준월 + 변수명 + 값` 형태로 저장한다. 새로운 수치형 변수가 추가돼도 테이블 컬럼을 변경할 필요가 없다. 특정 월의 전체 변수를 반환할 때는 API에서 JSON 객체로 집계한다.

### `vessel_monthly_source_rows`

원본 CSV의 각 행을 JSONB로 보존한다. 정규화한 수치 데이터뿐 아니라 텍스트 라벨을 포함한 원본 값 전체를 추적할 수 있다.

```text
vessel_monthly_master
 ├─ vessel_monthly_features
 └─ vessel_monthly_source_rows
```

마스터 행이 삭제되면 연결된 변수와 원본 행도 `ON DELETE CASCADE`로 삭제된다.

### `monthly_orders`

과거에 사용하던 CGT 기반 월간 수주 데이터다. 현재 마스터 데이터의 `CBM`, `DWT`, `TEU`와는 환산 기준 없이 합칠 수 없으므로 별도로 유지한다.

## 군집 분석 결과

군집 분석 결과는 다음 세 테이블로 구성된다.

- `cluster_models`: 모델 키, 분석 방법, 군집 수, 전체 설정 JSON
- `cluster_monthly_assignments`: 선종·모델별 월간 군집 번호
- `cluster_monthly_metrics`: 월별 군집 결과에 연결된 세부 수치

```text
cluster_models
  └─ cluster_monthly_assignments
       └─ cluster_monthly_metrics
```

현재 적재 스크립트는 `regime_v2_final` 모델 키를 사용한다. 테이블과 적재 기능은 존재하지만 이를 직접 조회하는 Express API는 아직 없다.

## 사용자와 인증

### `app_users`

UUID 사용자 ID, 이메일, 표시 이름, 프로필 이미지, 비밀번호 해시, 구독 플랜, 이메일·마케팅 수신 동의와 로그인 시각을 저장한다. 일반 비밀번호는 `scrypt`로 해시한다.

### `oauth_accounts`

Google의 사용자 식별자와 내부 사용자를 연결한다.

### `auth_sessions`

로그인 세션을 저장한다. 브라우저에 전달한 실제 세션 토큰은 저장하지 않고 SHA-256 해시와 만료 시각만 저장한다. 사용자가 삭제되면 세션도 연쇄 삭제된다.

### `oauth_login_attempts`

Google OAuth 로그인 과정의 state, PKCE 검증값과 로그인 유지 여부를 임시 저장한다. 로그인 시도는 10분 후 만료된다.

```text
app_users
 ├─ oauth_accounts
 └─ auth_sessions

oauth_login_attempts  ← OAuth 로그인 시도 상태
```

## 뉴스룸

뉴스 데이터는 별도의 `newsroom` PostgreSQL 스키마에 저장한다. `newsroom.articles`에는 언론사, 카테고리, 제목, 원문 URL, 발행 시각, 이미지 정보와 피드 URL이 들어간다.

원문 URL에는 유니크 제약이 있어 동일 기사의 중복 적재를 방지한다. API는 최근 180일 이내 기사 중 최대 80건을 조회한다.

## 데이터 적재 흐름

```text
5개 선종 CSV
   ↓ backend/scripts/import-master.js
입력값·월·단위 검증
   ↓ 하나의 트랜잭션
vessel_monthly_master
vessel_monthly_features
vessel_monthly_source_rows
```

적재 스크립트는 필수 파일과 헤더, 중복 월, 숫자 형식, 음수 수주용량, 선종별 단위와 정보 공개 시차를 검사한다. 오류가 발생하면 트랜잭션 전체를 롤백한다. `/api/v1/master-data`는 마스터, 원본 JSON, 수치형 변수를 조인해 프론트엔드에 반환한다.

군집 결과는 `backend/scripts/import-clusters.js`가 별도 CSV와 JSON 설정을 읽어 적재한다.

## 마이그레이션

`backend/scripts/migrate.js`는 `backend/sql`의 `001`부터 `011`까지 모든 SQL 파일을 한 트랜잭션에서 순서대로 실행한다. 대부분 `IF NOT EXISTS`를 사용하므로 반복 실행할 수 있다.

일반적인 마이그레이션 도구처럼 적용 이력을 기록하는 `schema_migrations` 테이블은 없다. 마이그레이션 수가 늘어나면 적용 버전 추적을 추가하는 편이 안전하다.

## API와 데이터베이스 연결

Express는 `pg.Pool`과 `DATABASE_URL`을 사용한다. 주요 조회 경로는 다음과 같다.

- `GET /api/ready`: `SELECT 1`로 연결 상태 확인
- `GET /api/v1/vessels`: 선종 목록
- `GET /api/v1/master-data`: 선종별 마스터·원본·변수 데이터
- `GET /api/v1/market/orders`: 연도별 CGT 수주 데이터
- `GET /api/v1/newsroom`: 최근 뉴스
- `/api/auth/*`: 계정, OAuth, 세션, 구독 정보

## MLOps 데이터베이스와의 차이

`mlops/docker-compose.yml`은 하나의 PostgreSQL 컨테이너에 다음 세 데이터베이스를 만든다.

- `shi_app`: 서비스 운영 데이터
- `mlflow`: MLflow 실험 및 모델 레지스트리
- `airflow`: Airflow 메타데이터

`mlops/docker/db/init/sql/app_schema.sql`은 `app.users`, `model_versions`, `predictions`, `feedback`, `audit_log` 같은 범용 MLOps 운영 테이블을 정의한다. 이 파일에는 제안 상태라고 명시되어 있으며 현재 Express 백엔드는 이 테이블을 조회하지 않는다.

따라서 현재는 다음 두 구조가 완전히 통합되지 않은 상태다.

1. `backend/sql`: 실제 웹 서비스의 시장 데이터, 인증, 뉴스 스키마
2. `mlops/docker/db/init/sql/app_schema.sql`: 모델 버전과 예측 이력 관리를 위한 범용 제안 스키마

현재 사용자 지정 예측은 외부 예측 서비스로 전달되며 실행 결과를 MLOps의 `predictions` 테이블에 기록하는 연결은 구현되어 있지 않다. 현 운영 데이터베이스의 주요 역할은 시장 데이터 제공, 인증·구독 관리와 뉴스 저장이다.

## 관련 파일

- `backend/sql/`: 운영 스키마 마이그레이션
- `backend/scripts/migrate.js`: 마이그레이션 실행기
- `backend/scripts/import-master.js`: 선종별 마스터 CSV 적재
- `backend/scripts/import-clusters.js`: 군집 결과 적재
- `backend/scripts/sync-newsroom.js`: 뉴스 동기화
- `backend/src/app.js`: 데이터 조회 API
- `backend/src/auth.js`: 사용자·세션 처리
- `mlops/docker-compose.yml`: 로컬 MLOps 데이터베이스 구성
- `mlops/docker/db/init/sql/app_schema.sql`: 범용 MLOps 운영 스키마 제안
