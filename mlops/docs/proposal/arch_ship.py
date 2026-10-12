# build_proposal.py 가 exec 로 불러 쓰는 설계도 3장 (서버 아키텍처 · 머신러닝 프로세스 · 판정 로직 순서도)
#  기준: Downloads/서버 아키텍처.png, docker 프로세스 아키텍처.png — 구성 요소는 그대로, 내용은 우리 구현(저장소)으로


def label(s, x, y, w, h, title, sub=None, fill=WHITE, line=LINE, tcol=INK, ts=12.5, ss=10, lw=1.0, scol=GRAY, rad=0.08):
    rect(s, x, y, w, h, fill, line, MSO_SHAPE.ROUNDED_RECTANGLE, lw, rad)
    if sub:
        tb(s, x + 0.05, y + h / 2 - 0.28, w - 0.1, 0.3, title, ts, F_SEMI, color=tcol, align=PP_ALIGN.CENTER)
        tb(s, x + 0.05, y + h / 2 + 0.03, w - 0.1, 0.3, sub, ss, color=scol, align=PP_ALIGN.CENTER)
    else:
        tb(s, x + 0.05, y + h / 2 - 0.15, w - 0.1, 0.3, title, ts, F_SEMI, color=tcol, align=PP_ALIGN.CENTER)


def dline(s, x1, y1, x2, y2, color=BLUEB, wt=1.25, dash=None, head=True):
    c = s.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = color; c.line.width = Pt(wt)
    if dash:
        c.line.dash_style = dash
    if head:
        ln = c.line._get_or_add_ln(); te = etree.SubElement(ln, qn("a:tailEnd")); te.set("type", "triangle"); te.set("w", "med"); te.set("len", "med")


def diamond(s, cx, cy, w, h, text, size=10):
    rect(s, cx - w / 2, cy - h / 2, w, h, WHITE, BLUE, MSO_SHAPE.DIAMOND, 1.25)
    tb(s, cx - w / 2 + 0.15, cy - 0.2, w - 0.3, 0.4, text, size, F_SEMI, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE, spacing=1.05, after=0)


RED = RGBColor(0xB3, 0x26, 0x1E)

# ============================================================ A. 서버 아키텍처
s = page("05", "서비스 개발 계획", "서버 아키텍처", "WSL2의 Airflow가 Docker 컨테이너 2개를 제어하는, 이미 구축한 구조를 수주 예측 파이프라인에 그대로 씁니다.")
rect(s, 0.6, 2.2, 12.13, 4.45, None, GRAYL, MSO_SHAPE.ROUNDED_RECTANGLE, 1.0, 0.02)
tb(s, 0.8, 2.3, 5, 0.3, [[("Windows PC", {"size": 12.5, "font": F_SEMI}), ("   호스트 환경", {"size": 10.5, "color": GRAY})]])
# WSL2 · Airflow
rect(s, 0.8, 2.7, 3.55, 3.8, BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.03)
tb(s, 0.98, 2.8, 3.2, 0.3, [[("WSL2", {"size": 12, "font": F_SEMI}), ("   Linux 서버", {"size": 10, "color": GRAY})]])
rect(s, 0.98, 3.2, 3.2, 3.15, WHITE, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25, 0.04)
tb(s, 1.13, 3.3, 2.9, 0.3, "Apache Airflow", 13, F_SEMI, color=BLUE)
tb(s, 1.13, 3.6, 2.9, 0.25, "워크플로 오케스트레이션 · DAG 3개", 9.5, color=GRAY)
for i, (d, sch) in enumerate([("shi_ship_order_pipeline", "월 1회 · 수주 월보 게시 후 재학습"), ("shi_ship_data_refresh", "월 1회 · 공개 지표 갱신 · 시차 점검"), ("shi_ops_log_etl", "매일 · 예측 로그 적재")]):
    y = 3.92 + i * 0.6
    rect(s, 1.13, y, 2.9, 0.52, BLUEL if i == 0 else BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.12)
    tb(s, 1.25, y + 0.04, 2.7, 0.25, d, 10.5, F_SEMI, color=BLUE if i == 0 else INK)
    tb(s, 1.25, y + 0.27, 2.7, 0.22, sch, 9, color=GRAY)
tb(s, 1.13, 5.78, 2.9, 0.5, ["① docker compose up --wait", "② docker exec shi-app kedro run"], 9.5, F_MED, color=GRAY, spacing=1.1, after=1)
# Docker Desktop
rect(s, 4.85, 2.7, 7.7, 3.8, BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.03)
tb(s, 5.03, 2.8, 6, 0.3, [[("Docker Desktop", {"size": 12, "font": F_SEMI}), ("   컨테이너 2개 + 공유 볼륨", {"size": 10, "color": GRAY})]])
rect(s, 5.03, 3.2, 3.85, 2.35, WHITE, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25, 0.04)
tb(s, 5.18, 3.3, 3.6, 0.3, [[("Ubuntu 컨테이너", {"size": 13, "font": F_SEMI, "color": BLUE}), ("   shi-app", {"size": 10, "color": GRAY})]])
for i, (a, b) in enumerate([("Python 3.12", "pandas · scikit-learn"), ("Kedro", "ship_orders · ops_logs"), ("MLflow  :5000", "실험 추적 · 모델 등록"), ("FastAPI  :8000", "/ship/forecast 외")]):
    x = 5.18 + (i % 2) * 1.8; y = 3.7 + (i // 2) * 0.9
    rect(s, x, y, 1.7, 0.78, BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.1)
    tb(s, x + 0.12, y + 0.1, 1.5, 0.3, a, 11, F_SEMI)
    tb(s, x + 0.12, y + 0.42, 1.5, 0.3, b, 8.5, color=GRAY)
rect(s, 9.55, 3.2, 2.85, 2.35, WHITE, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25, 0.04)
tb(s, 9.7, 3.3, 2.6, 0.3, [[("DB 컨테이너", {"size": 13, "font": F_SEMI, "color": BLUE}), ("   shi-db", {"size": 10, "color": GRAY})]])
tb(s, 9.7, 3.6, 2.6, 0.25, "PostgreSQL 16  :5432", 9.5, color=GRAY)
for i, t in enumerate(["app · 예측 로그 · 모델 버전", "ops · 관제 이벤트", "MLflow 메타데이터", "Airflow 메타데이터"]):
    y = 3.92 + i * 0.4
    rect(s, 9.7, y, 2.55, 0.32, BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.2)
    tb(s, 9.7, y + 0.05, 2.55, 0.25, t, 9.5, F_MED, align=PP_ALIGN.CENTER)
dline(s, 8.9, 4.1, 9.52, 4.1, BLUE, 1.5)
tb(s, 8.88, 3.83, 0.7, 0.25, "DB 연결", 8.5, F_MED, color=BLUE, align=PP_ALIGN.CENTER)
dline(s, 8.9, 4.95, 9.52, 4.95, BLUEB, 1.25, 7)
tb(s, 8.88, 5.0, 0.7, 0.4, ["MLflow", "기록"], 8.5, F_MED, color=BLUEB, align=PP_ALIGN.CENTER, spacing=1.0, after=0)
# 공유 볼륨
rect(s, 5.03, 5.68, 7.37, 0.7, WHITE, LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.0, 0.1)
tb(s, 5.18, 5.74, 3.0, 0.3, "공유 볼륨  ./data", 11, F_SEMI)
for i, t in enumerate(["01_raw 원천", "03_primary 전처리", "06_models 모델", "mlflow 아티팩트", "08 리포트 · 로그"]):
    chip(s, 5.18 + i * 1.44, 5.98, 1.36, t, BLUEL, BLUE, 8.5)
# WSL → Docker
dline(s, 4.18, 3.62, 5.0, 3.62, BLUE, 1.5)
tb(s, 4.2, 3.32, 0.8, 0.28, "컨테이너 관리", 8.5, F_MED, color=BLUE, align=PP_ALIGN.CENTER)
dline(s, 4.18, 4.55, 5.0, 4.55, BLUEB, 1.5, 4)
tb(s, 4.2, 4.6, 0.8, 0.28, "kedro run", 8.5, F_MED, color=BLUEB, align=PP_ALIGN.CENTER)
for i, (t, col, dash) in enumerate([("주요 제어 · DB 연결", BLUE, None), ("Kedro 명령 실행 (Airflow → Kedro)", BLUEB, 4), ("데이터 저장 (MLflow → DB)", BLUEB, 7)]):
    x = [5.0, 6.95, 9.85][i]
    dline(s, x, 2.43, x + 0.4, 2.43, col, 1.5, dash, False)
    tb(s, x + 0.48, 2.33, 2.6, 0.25, t, 9, F_MED, color=GRAY)

# ============================================================ B. 머신러닝 프로세스
s = page("05", "서비스 개발 계획", "머신러닝 프로세스", "Airflow가 Kedro 파이프라인을 실행하고, scikit-learn으로 학습·평가한 모델을 MLflow에 등록하면 예측 API가 그 모델을 불러 씁니다.")
steps5 = [("1", "Airflow", "월 1회 재학습 실행", "shi_ship_order_pipeline"), ("2", "Kedro", "파이프라인 · 데이터 카탈로그", "kedro run --pipeline=ship_orders"),
          ("3", "scikit-learn", "전처리 → 학습 → 평가", "선형 · Ridge · RF · 부스팅"), ("4", "MLflow", "실험 기록 · 모델 등록", "ship_order_{선종}"), ("5", "DB · 공유 볼륨", "메타데이터 · 모델 파일", "PostgreSQL · ./data")]
for i, (n, a, b, c_) in enumerate(steps5):
    x = 0.6 + i * 2.47
    rect(s, x, 2.25, 2.25, 1.3, BLUEL if i in (2, 3) else BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.08)
    rect(s, x + 0.15, 2.4, 0.38, 0.38, BLUE, None, MSO_SHAPE.OVAL)
    tb(s, x + 0.15, 2.45, 0.38, 0.3, n, 11.5, F_SEMI, color=WHITE, align=PP_ALIGN.CENTER)
    tb(s, x + 0.62, 2.43, 1.55, 0.35, a, 13, F_SEMI, color=BLUE if i in (2, 3) else INK)
    tb(s, x + 0.15, 2.88, 2.0, 0.28, b, 10.5, F_MED)
    tb(s, x + 0.15, 3.16, 2.0, 0.28, c_, 9, color=GRAY)
    if i:
        arrow(s, x - 0.2, 2.9, x - 0.03, 2.9, BLUE, 1.5)
tb(s, 0.6, 3.78, 11, 0.3, [[("3단계 상세  ", {"size": 12.5, "font": F_SEMI}), ("학습과 서빙이 같은 시차 규칙 · 마스터 생성 코드를 씁니다", {"size": 11, "color": GRAY})]])
pipe = [("데이터 수집", "공개 원천 · 월보"), ("검증", "단위 · 키 · 음수 · 출처"), ("전처리", "raw → processed"), ("시차 · 마스터", "공표 시차 1·2·3·6개월"), ("학습", "변수 후진 제거 · 모델 비교"), ("평가", "검증 2022–25 · 2026 독립"), ("모델 저장", "선종별 · 레지스트리")]
for i, (a, b) in enumerate(pipe):
    x = 0.6 + i * 1.75
    main = i in (2, 3)
    rect(s, x, 4.22, 1.55, 0.95, BLUEL if main else WHITE, BLUE if main else LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25 if main else 1.0, 0.1)
    tb(s, x, 4.35, 1.55, 0.3, a, 11.5, F_SEMI, color=BLUE if main else INK, align=PP_ALIGN.CENTER)
    tb(s, x + 0.05, 4.67, 1.45, 0.4, b, 9, color=GRAY, align=PP_ALIGN.CENTER)
    if i:
        arrow(s, x - 0.18, 4.69, x - 0.02, 4.69, GRAYL, 1.25)
# 서빙
rect(s, 0.6, 5.55, 6.6, 1.0, WHITE, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25, 0.1)
tb(s, 0.8, 5.63, 6.2, 0.3, "추론 · 서빙 API   /ship/forecast", 12, F_SEMI, color=BLUE)
tb(s, 0.8, 5.95, 6.2, 0.55, "선종 · 기준월 입력 → 그때 공표된 값으로 피처 구성 → 등록된 선종 모델 → 예측 · 범위. 모델이 바뀌면 다음 요청부터 반영.", 9.5, color=GRAY, spacing=1.15)
dline(s, 4.27, 5.19, 4.27, 5.52, BLUE, 1.25, 4)
tb(s, 4.35, 5.22, 2.2, 0.25, "같은 전처리 함수 호출", 8.5, F_MED, color=BLUE)
dline(s, 11.37, 5.19, 11.37, 5.35, BLUE, 1.25, None, False); dline(s, 11.37, 5.35, 7.0, 5.35, BLUE, 1.25, None, False); dline(s, 7.0, 5.35, 7.0, 5.52, BLUE, 1.25)
tb(s, 8.6, 5.38, 1.5, 0.22, "모델 로드", 8.5, F_MED, color=BLUE)
tb(s, 7.6, 5.55, 5, 0.25, "결과물", 10.5, F_SEMI, color=GRAY)
for i, (a, b) in enumerate([("실험 기록", "MLflow"), ("등록된 모델", "ship_order_{선종}"), ("대시보드", "변수 계층 · 예측 화면"), ("재현 가능한 파이프라인", "Kedro + 코드")]):
    x = 7.6 + (i % 2) * 2.6; y = 5.85 + (i // 2) * 0.38
    tb(s, x, y, 2.55, 0.3, [[(a + "  ", {"size": 10.5, "font": F_SEMI}), (b, {"size": 9, "color": GRAY})]])


# ============================================================ C. 예측 흐름 순서도
s = page("05", "서비스 개발 계획", "예측 흐름 순서도", "/ship/forecast 한 번의 요청이 시점 확인 → 피처 구성 → 모델 선택 → 예측 · 범위 → 화면 · 로그로 끝납니다.")
label(s, 0.6, 2.25, 2.3, 0.75, "사용자 입력", "선종 · 기준월 · 예측 범위", BLUE, None, WHITE, 12.5, 9.5, scol=BLUEM)
diamond(s, 1.75, 3.65, 2.3, 0.95, "입력이 올바른가?")
label(s, 0.6, 4.65, 2.3, 0.75, "기준일 확정", "게시일 확인된 수주만", ts=12, ss=9.5)
label(s, 0.6, 5.85, 2.3, 0.65, "400 오류 반환", "허용 선종 5종 안내", WHITE, LINE, GRAY, 11, 9)
arrow(s, 1.75, 3.03, 1.75, 3.15, GRAYL, 1.25)
arrow(s, 1.75, 4.14, 1.75, 4.62, GRAYL, 1.25)
tb(s, 1.85, 4.25, 0.5, 0.25, "예", 9.5, F_MED, color=BLUE)
dline(s, 0.6, 3.65, 0.42, 3.65, GRAYL, 1.25, None, False); dline(s, 0.42, 3.65, 0.42, 6.17, GRAYL, 1.25, None, False); dline(s, 0.42, 6.17, 0.58, 6.17, GRAYL, 1.25)
tb(s, 0.12, 3.33, 0.6, 0.25, "아니오", 9, F_MED, color=GRAY, align=PP_ALIGN.CENTER)
arrow(s, 2.92, 5.02, 3.42, 5.02, GRAYL, 1.25)
rect(s, 3.45, 2.2, 5.35, 4.35, BGS, None, MSO_SHAPE.ROUNDED_RECTANGLE, radius=0.04)
tb(s, 3.6, 2.28, 5, 0.25, "선종 모델 예측 (ML)", 10.5, F_SEMI, color=BLUE)
flow = [("피처 구성", "변수마다 선택된 시차로, 기준일에 공표된 값만"), ("결측 점검", "공표 전 지표는 직전 값 · 없으면 기준선"), ("모델 선택", "선종별 등록 모델 · 기준선보다 나쁘면 기준선"),
        ("예측 · 범위", "+1·3·6개월 값 · 과거 순차 오차 분위로 범위"), ("누적 · 근거", "분기 · 반기 합계 · 변수 기여 방향")]
for i, (a1, b1) in enumerate(flow):
    y = 2.6 + i * 0.78
    rect(s, 3.65, y, 4.95, 0.66, WHITE, LINE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.0, 0.12)
    tb(s, 3.8, y + 0.07, 1.4, 0.3, a1, 11, F_SEMI, color=BLUE)
    tb(s, 5.15, y + 0.08, 3.35, 0.5, b1, 9.5, color=INK, spacing=1.1)
    if i:
        arrow(s, 6.1, y - 0.11, 6.1, y - 0.01, GRAYL, 1.0)
arrow(s, 8.82, 4.4, 9.28, 4.4, GRAYL, 1.25)
rect(s, 9.3, 2.2, 3.43, 3.25, WHITE, BLUE, MSO_SHAPE.ROUNDED_RECTANGLE, 1.25, 0.05)
tb(s, 9.48, 2.32, 3.1, 0.3, "결과 표시 규칙", 12.5, F_SEMI, color=BLUE)
for i, (cnd, res, col) in enumerate([("모델이 기준선보다 나음 (검증)", "모델 예측 + 범위", OK), ("기준선과 비슷하거나 나쁨", "기준선 값 우선 표시", WARN),
                                     ("필수 지표 미공표", "직전 값 사용 · 표시", GRAY), ("피크 이벤트 감지", "+ 이벤트 메모", BLUE)]):
    y = 2.75 + i * 0.66
    tb(s, 9.48, y, 3.1, 0.25, cnd, 9.5, color=GRAY)
    tb(s, 9.48, y + 0.25, 3.1, 0.3, res, 11.5, F_SEMI, color=col)
label(s, 9.3, 5.65, 3.43, 0.85, "결과 화면 · 로그 기록", "/ship 화면 · app.predictions", BLUE, None, WHITE, 12, 9, scol=BLUEM)
arrow(s, 11.0, 5.47, 11.0, 5.63, GRAYL, 1.25)
