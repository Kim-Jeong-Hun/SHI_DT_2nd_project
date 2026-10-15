# SHI_DT_2nd_project

삼성중공업 스마트조선소 AI 전문가 양성과정의 선박 수주 예측 프로젝트입니다.

## 저장소 구성

- `scripts/`: 데이터 수집·전처리·분석 스크립트와 선종별 분석 노트북
- `src/ship_orders_forecasting/`: 공통 전처리·검증·예측 패키지
- `tests/`: 누수 방지, 마스터 재현성, 예측 규칙 검증 테스트
- `pyproject.toml`: Python 패키지 및 의존성 설정

원자료, 가공 데이터, 문헌, 분석 결과와 백업은 용량과 이용 조건을 고려해 저장소에 포함하지 않습니다.

## 테스트

```powershell
python -m unittest discover -s tests -p "test_*.py" -v
```

## 구성

- `mlops/`: 선박 수주 예측 운영 파이프라인 (Kedro · MLflow · Airflow)
- `frontend/`: React 대시보드. 현재는 가상 데이터를 표시합니다.
- `backend/`: Express API와 PostgreSQL 스키마. 로컬 PostgreSQL 또는 Supabase PostgreSQL에 연결할 수 있습니다. 설치와 실행 방법은 [backend/README.md](backend/README.md)를 참고하세요.
