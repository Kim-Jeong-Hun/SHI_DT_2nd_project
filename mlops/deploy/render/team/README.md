# 팀 파이프라인 사본 (Render 빌드용)

원본: 팀 Drive 'Ship orders forcasting'(ship-order-drive). Render 이미지 빌드 때 Kedro `ship_orders` 파이프라인이
`scripts/분석/2026_독립검증.py` 를 실행해 운영 보고서를 만들도록 **실행에 필요한 파일만** 복사했다(2026-10-07).

- 코드: `src/ship_orders_forecasting/`, `scripts/전처리/*.py`(legacy_module 로 불러옴), `scripts/분석/2026_독립검증.py`
- 데이터: 스크립트 실행 중 실제로 열린 파일만(파일 열기 감사 훅으로 추적, 17개 · 약 0.5MB) — `data/raw/수주실적.csv`, `data/processed/…`
- 갱신: 팀 원본이 바뀌면 이 폴더를 다시 복사해 커밋한다. 결과 보고서는 `reports/` 에 생긴다(커밋하지 않음).
