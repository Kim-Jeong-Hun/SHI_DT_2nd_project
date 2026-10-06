"""과거 단일 코드셀 구조를 옮길 때 사용한 일회성 이행 스크립트.

현행 기능별 분리 노트북에는 적용하지 않는다. 이 스크립트를 다시 실행하면
현재의 시차·누적 창·평가 규칙을 덮어쓸 수 있으므로 명시적으로 거부한다.
"""

from __future__ import annotations

import re
import runpy
from pathlib import Path

import nbformat


ROOT = Path(__file__).resolve().parents[2]
NOTEBOOK_DIR = ROOT / "scripts" / "분석"
NOTEBOOKS = sorted(NOTEBOOK_DIR.glob("수주예측(*).ipynb"))
MASTER_RULES = runpy.run_path(str(ROOT / "scripts" / "전처리" / "마스터테이블_생성.py"))
GLOBAL_FEATURE_GROUPS = {
    "컨테이너처리량원본피처": MASTER_RULES["CONTAINER_INDEX_COLUMNS"],
    "세계거시원본피처": MASTER_RULES["GLOBAL_ECONOMY_COLUMNS"],
    "공급망원본피처": MASTER_RULES["SUPPLY_CHAIN_COLUMNS"],
}
SHIP_CARGO_VOLUME_FEATURES = {
    "벌크선": [
        "세계 철광석 수입량(백만톤)",
        "호주 석탄 수출량(백만톤)",
    ],
    "케미컬 탱커": [
        "세계 대두유 수입량(백만톤)",
        "세계 팜유 수입량(백만톤)",
    ],
    "컨테이너선": [
        "세계 면화 수입량(백만톤)",
        "세계 천연고무 수입량(백만톤)",
        "세계 천연고무 TSR20 수입량(백만톤)",
    ],
    "가스 운반선": [
        "세계 LNG 수입량(십억m³)",
        "일본 LNG 수입량(백만톤)",
    ],
    "유조선": [
        "세계 원유 수입량(백만배럴)",
    ],
}


HEATMAP_BLOCK = r'''# 종속변수를 마지막에 배치해 회전 그림의 오른쪽 사선 띠로 강조합니다.
상관열 = [*원본피처, 종속변수]
상관관계 = 자료[상관열].corr()
표표시(상관관계, '{:.2f}')

# Matplotlib 다각형으로 직접 그립니다. 회색 명암은 |r|, 컬러는 부호가 있는 r입니다.
import runpy
회전그림도구 = runpy.run_path(str(프로젝트폴더 / 'scripts' / '분석' / '상관관계_회전히트맵.py'))
fig, 축 = 회전그림도구['draw_rotated_correlation'](
    상관관계, target=종속변수,
    title=f'{선종} 변수 상관관계 히트맵 (45° 회전, 중복 제외)',
)
plt.show()'''


EVALUATION_CELL = r'''# 외부지표는 공표시점에 따라 허용된 1·2·3·6개월 시차 중 하나만 선택합니다.
# 월말까지 직접 계산 가능한 가격·운임은 1·2·3·6개월, 다음 달 이후 공표되는
# 월간 자료는 2·3·6개월만 후보로 둡니다. 2025년 자료는 시차 선택에 사용하지 않습니다.
신조선가원본피처 = globals().get('신조선가원본피처', [])
운임원본피처 = globals().get('운임원본피처', [])
선복량원본피처 = globals().get('선복량원본피처', [])
분기원본피처 = globals().get('분기원본피처', [])
물동량원본피처 = globals().get('물동량원본피처', [])
컨테이너처리량원본피처 = globals().get('컨테이너처리량원본피처', [])
세계거시원본피처 = globals().get('세계거시원본피처', [])
공급망원본피처 = globals().get('공급망원본피처', [])
외부원본피처 = [
    *원자재원본피처, *벙커유원본피처, *신조선가원본피처,
    *운임원본피처, *선복량원본피처, *분기원본피처,
    *물동량원본피처, *컨테이너처리량원본피처,
    *세계거시원본피처, *공급망원본피처, *위험원본피처, *무역정책원본피처,
]

월말산출가능피처 = set([*원자재원본피처, *운임원본피처])
공표시점반영완료피처 = set([*선복량원본피처, *분기원본피처])
시차후보월수 = {
    피처: ((1, 2, 3, 6) if 피처 in 월말산출가능피처 | 공표시점반영완료피처 else (2, 3, 6))
    for 피처 in 외부원본피처
}
시차정책표 = pd.DataFrame([{
    '원본피처': 피처,
    '허용시차': ', '.join(f'{시차}개월' for 시차 in 시차후보월수[피처]),
    '근거': (
        '월말까지 산출 가능' if 피처 in 월말산출가능피처
        else 'master에서 공표가능월 반영 완료' if 피처 in 공표시점반영완료피처
        else '다음 달 이후 공표 가능'
    ),
} for 피처 in 외부원본피처])
print('피처별 시차 후보 정책')
display(시차정책표)

예상월수 = len(pd.period_range(자료.index.min(), 자료.index.max(), freq='M'))
if len(자료) != 예상월수:
    raise ValueError('월별 기준월에 누락이 있어 시차 정렬을 확인해야 합니다.')

시차후보피처 = {}
for 피처 in 외부원본피처:
    시차후보피처[피처] = []
    for 시차 in 시차후보월수[피처]:
        시차피처 = f'{피처}_{시차}개월전'
        자료[시차피처] = 자료[피처].shift(시차)
        시차후보피처[피처].append(시차피처)


def smape(실제, 예측):
    실제 = np.asarray(실제, dtype=float)
    예측 = np.asarray(예측, dtype=float)
    분모 = np.abs(실제) + np.abs(예측)
    return float(np.mean(np.divide(
        2 * np.abs(실제 - 예측), 분모,
        out=np.zeros_like(분모, dtype=float), where=분모 != 0,
    )))


def 지표계산(실제, 예측):
    return {
        'sMAPE': smape(실제, 예측),
        'MAE': mean_absolute_error(실제, 예측),
        'RMSE': np.sqrt(mean_squared_error(실제, 예측)),
        'R2': r2_score(실제, 예측),
    }


모형종류목록 = ['1차 선형회귀', '2차 다항 Ridge', '랜덤 포레스트']


def 모형생성(모형종류):
    if 모형종류 == '1차 선형회귀':
        return make_pipeline(StandardScaler(), LinearRegression())
    if 모형종류 == '2차 다항 Ridge':
        return make_pipeline(
            PolynomialFeatures(degree=2, include_bias=False),
            StandardScaler(),
            Ridge(alpha=10.0),
        )
    if 모형종류 == '랜덤 포레스트':
        return RandomForestRegressor(
            n_estimators=60, min_samples_leaf=3, max_features=1.0,
            random_state=난수시드, n_jobs=1,
        )
    raise ValueError(f'지원하지 않는 모형: {모형종류}')


def 분할생성(대상월목록, 피처목록, 공통자료=None):
    """예측월 t마다 t-2까지의 확정 수주만 학습에 사용한다."""
    필요컬럼 = [종속변수, *피처목록]
    if 공통자료 is None:
        기준자료 = 자료[필요컬럼].dropna().copy()
    else:
        누락 = set(필요컬럼).difference(공통자료.columns)
        if 누락:
            raise KeyError(f'공통 비교자료 누락 컬럼: {sorted(누락)}')
        기준자료 = 공통자료[필요컬럼].dropna().copy()
    결과 = []
    for 시점 in 대상월목록:
        if 시점 not in 기준자료.index:
            continue
        학습종료 = 시점 - pd.DateOffset(months=2)
        학습 = 기준자료.loc[기준자료.index <= 학습종료]
        if len(학습) < 48:
            continue
        결과.append((시점, 학습, 기준자료.loc[[시점]]))
    return 결과


def 모형평가(모형종류, 피처목록, 분할=None):
    # 개발 검증, 과거 그래프, 2025 테스트에 동일한 월별 재학습 함수를 씁니다.
    if 분할 is None:
        분할 = 분할생성(검증월목록, 피처목록)
    if not 분할:
        raise ValueError(f'{모형종류} 평가에 사용할 월별 분할이 없습니다.')
    예측모음 = []
    for _, 학습, 검증 in 분할:
        모형 = 모형생성(모형종류)
        모형.fit(학습[피처목록], 학습[종속변수])
        예측 = np.clip(모형.predict(검증[피처목록]), 0, None)
        예측모음.append(pd.DataFrame({
            '실제': 검증[종속변수], '예측': 예측,
        }, index=검증.index))
    전체 = pd.concat(예측모음).sort_index()
    return 지표계산(전체['실제'], 전체['예측']), 전체, pd.DataFrame()


# 피처마다 후보 시차가 모두 관측된 같은 행만 사용해 시차 간 표본 차이를 없앱니다.
# 시차 선택 모형은 고정하고, 2개월 전 수주용량을 함께 넣어 단변량 착시를 줄입니다.
시차선정모형 = '2차 다항 Ridge'
시차비교결과 = []
선택시차월수 = {}
for 피처 in 외부원본피처:
    후보열 = 시차후보피처[피처]
    공통열 = [종속변수, *후보열, *과거수주피처]
    공통자료 = 자료[공통열].dropna().copy()
    잠정검증월 = 공통자료.index[
        (공통자료.index.year >= 2022) & (공통자료.index.year <= 2024)
    ]
    기준비교피처 = [후보열[0], *과거수주피처]
    기준비교분할 = 분할생성(
        잠정검증월, 기준비교피처, 공통자료=공통자료
    )
    공통검증월 = pd.DatetimeIndex([시점 for 시점, _, _ in 기준비교분할])
    if 공통검증월.empty:
        raise ValueError(f'{피처} 시차 검증월이 없습니다.')
    피처결과 = []
    for 시차, 시차피처 in zip(시차후보월수[피처], 후보열):
        비교피처 = [시차피처, *과거수주피처]
        비교분할 = 분할생성(공통검증월, 비교피처, 공통자료=공통자료)
        if len(비교분할) != len(공통검증월):
            raise ValueError(f'{피처} {시차}개월 시차의 공통 검증월이 일치하지 않습니다.')
        지표, _, _ = 모형평가(시차선정모형, 비교피처, 비교분할)
        행 = {
            '원본피처': 피처, '시차개월': 시차,
            '검증관측월': len(비교분할), **지표,
        }
        시차비교결과.append(행)
        피처결과.append(행)
    최선 = min(피처결과, key=lambda 행: (행['sMAPE'], 행['RMSE'], 행['시차개월']))
    선택시차월수[피처] = 최선['시차개월']

시차비교표 = pd.DataFrame(시차비교결과)
시차비교표['선택'] = 시차비교표.apply(
    lambda 행: 행['시차개월'] == 선택시차월수[행['원본피처']], axis=1
)
print(f'피처별 시차 비교 ({시차선정모형}, 2022~2024 개발 검증만 사용)')
표표시(시차비교표, {
    'sMAPE': '{:.1%}', 'MAE': '{:,.0f}', 'RMSE': '{:,.0f}', 'R2': '{:.3f}',
})

외부지표피처 = [
    f'{피처}_{선택시차월수[피처]}개월전' for 피처 in 외부원본피처
]
원본피처 = [*외부지표피처, *과거수주피처]
print('선택된 피처별 시차')
display(pd.DataFrame({
    '원본피처': 외부원본피처,
    '선택시차개월': [선택시차월수[피처] for 피처 in 외부원본피처],
    '모델입력피처': 외부지표피처,
}))

# 선택 사항: 특정 변수를 강제로 제외할 때만 수정합니다. 기본값은 자동 선택입니다.
제외피처 = []
알수없는피처 = set(제외피처).difference(원본피처)
if 알수없는피처 or len(제외피처) != len(set(제외피처)):
    raise ValueError(f'제외피처 목록을 확인하세요: {제외피처}')
사용피처 = [피처 for 피처 in 원본피처 if 피처 not in 제외피처]
if not 사용피처:
    raise ValueError('적어도 하나의 설명변수는 남겨야 합니다.')

모델자료 = 자료[[종속변수, *원본피처]].dropna().copy()
보류시작 = pd.Timestamp('2025-01-01')
개발자료 = 모델자료.loc[모델자료.index < 보류시작]
보류자료 = 모델자료.loc[모델자료.index >= 보류시작]
if len(개발자료) < 60 or 보류자료.empty:
    raise ValueError('개발 또는 2025년 보류 구간의 관측치가 부족합니다.')

잠정검증월목록 = 개발자료.index[
    (개발자료.index.year >= 2022) & (개발자료.index.year <= 2024)
]
분할목록 = 분할생성(잠정검증월목록, 원본피처)
검증월목록 = pd.DatetimeIndex([시점 for 시점, _, _ in 분할목록])
if len(검증월목록) < 24:
    raise ValueError('2022~2024년 검증월 중 최소 48개 학습행을 확보한 월이 24개 미만입니다.')
분할현황 = pd.DataFrame([{
    '검증연도': 시점.year,
    '검증월': 시점.strftime('%Y-%m'),
    '학습관측월': len(학습),
    '학습종료월': 학습.index.max().strftime('%Y-%m'),
} for 시점, 학습, _ in 분할목록])
display(분할현황.groupby('검증연도', as_index=False).agg(
    검증관측월=('검증월', 'count'),
    최초학습관측월=('학습관측월', 'min'),
    최종학습관측월=('학습관측월', 'max'),
    최종학습종료월=('학습종료월', 'max'),
))


def 평균기준값평가():
    기준분할 = 분할생성(검증월목록, [])
    예측모음 = []
    for _, 학습, 검증 in 기준분할:
        예측모음.append(pd.DataFrame({
            '실제': 검증[종속변수],
            '예측': np.repeat(학습[종속변수].mean(), len(검증)),
        }, index=검증.index))
    전체 = pd.concat(예측모음).sort_index()
    return 지표계산(전체['실제'], 전체['예측']), 전체


시장신규원본피처 = [*운임원본피처, *선복량원본피처, *물동량원본피처,
             *컨테이너처리량원본피처, *세계거시원본피처, *공급망원본피처]
시장신규피처 = [
    f'{피처}_{선택시차월수[피처]}개월전' for 피처 in 시장신규원본피처
]
기존피처 = [피처 for 피처 in 외부지표피처 if 피처 not in 시장신규피처]
기준지표, 기준예측 = 평균기준값평가()
비교결과 = [{'변수집합': '기준값', '모형': '훈련구간 평균',
         '피처수': 0, **기준지표, '검증관측월': len(기준예측)}]
전체변수결과 = {}
현재변수결과 = {}
for 모형종류 in 모형종류목록:
    기존지표, 기존예측, _ = 모형평가(모형종류, 기존피처)
    비교결과.append({'변수집합': '기존 외부지표', '모형': 모형종류,
             '피처수': len(기존피처), **기존지표, '검증관측월': len(기존예측)})
    기존전체지표, 기존전체예측, _ = 모형평가(모형종류, [*기존피처, *과거수주피처])
    비교결과.append({'변수집합': '기존 전체', '모형': 모형종류,
             '피처수': len(기존피처) + len(과거수주피처), **기존전체지표, '검증관측월': len(기존전체예측)})
    전체지표, 전체예측, _ = 모형평가(모형종류, 원본피처)
    전체변수결과[모형종류] = (전체지표, 전체예측)
    비교결과.append({'변수집합': '전체', '모형': 모형종류,
             '피처수': len(원본피처), **전체지표, '검증관측월': len(전체예측)})
    if 제외피처:
        현재지표, 현재예측, _ = 모형평가(모형종류, 사용피처)
        비교결과.append({'변수집합': '제외 후', '모형': 모형종류,
                 '피처수': len(사용피처), **현재지표, '검증관측월': len(현재예측)})
    else:
        현재지표, 현재예측, _ = 모형평가(모형종류, 원본피처)
    현재변수결과[모형종류] = (현재지표, 현재예측)

비교표 = pd.DataFrame(비교결과)
표표시(비교표, {
    'sMAPE': '{:.1%}', 'MAE': '{:,.0f}', 'RMSE': '{:,.0f}', 'R2': '{:.3f}',
})
'''


TIME_SERIES_BLOCK = r'''# 실제값은 검은색으로 유지하고 예측선을 역할별로 분리합니다.
# 학습구간 선도 그 시점까지의 과거만 사용한 워크포워드 참고 예측이며 인샘플 적합선이 아닙니다.
과거분할 = 분할생성(개발자료.index, 최종피처)
_, 과거순차, _ = 모형평가(최종모형, 최종피처, 과거분할)
검증시작 = pd.Timestamp('2022-01-01')
학습구간예측 = 과거순차.loc[과거순차.index < 검증시작]
검증구간예측 = 과거순차.loc[
    (과거순차.index >= 검증시작) & (과거순차.index < 보류시작)
]
print(
    f'과거 월별 순차예측(참고): {len(과거순차)}개월, '
    f'{과거순차.index.min():%Y-%m}~{과거순차.index.max():%Y-%m}'
)

fig, 축 = plt.subplots(figsize=(14, 4.5))
그래프시작 = 과거순차.index.min()
그래프종료 = 보류순차.index.max() + pd.offsets.MonthBegin(1)
실제선 = 자료.loc[그래프시작:보류순차.index.max(), 종속변수]

# 배경색은 데이터의 역할, 선색은 실제·예측의 종류를 나타냅니다.
축.axvspan(그래프시작, 검증시작, color='#B0B0B0', alpha=0.10, zorder=0)
축.axvspan(검증시작, 보류시작, color='#4C78A8', alpha=0.07, zorder=0)
축.axvspan(보류시작, 그래프종료, color='#E45756', alpha=0.07, zorder=0)
축.axvline(검증시작, color='#4C78A8', linestyle='--', linewidth=1)
축.axvline(보류시작, color='#E45756', linestyle='--', linewidth=1)

축.plot(실제선.index, 실제선, label='실제', color='#222222', linewidth=1.8, zorder=4)
if not 학습구간예측.empty:
    축.plot(
        학습구간예측.index, 학습구간예측['예측'],
        label='학습구간 워크포워드 예측(참고)',
        color='#7F7F7F', linestyle='--', linewidth=1.4, zorder=3,
    )
if not 검증구간예측.empty:
    축.plot(
        검증구간예측.index, 검증구간예측['예측'],
        label='2022~2024 검증 예측',
        color='#377EB8', linewidth=1.6, zorder=3,
    )
축.plot(
    보류순차.index, 보류순차['예측'],
    label='2025 테스트 예측',
    color='#E45756', linewidth=1.8, zorder=3,
)

def 구간이름표시(시작, 종료, 이름, 색상):
    중간 = 시작 + (종료 - 시작) / 2
    축.text(
        중간, 0.98, 이름,
        transform=축.get_xaxis_transform(),
        ha='center', va='top', color=색상, fontsize=9, fontweight='bold',
    )


구간이름표시(그래프시작, 검증시작, '학습·참고구간', '#666666')
구간이름표시(검증시작, 보류시작, '개발 검증구간', '#285F8F')
구간이름표시(보류시작, 그래프종료, '2025 테스트구간', '#B53B3A')
축.set_title(f'{선종} 다음 달 수주용량 월별 실제와 예측: {최종모형}')
축.set_ylabel(종속변수)
축.legend(loc='upper left')
축.tick_params(axis='x', rotation=30)
plt.tight_layout()
plt.show()'''


def update_scope(text: str) -> str:
    text = re.sub(
        r"^- 설명변수:.*$",
        "- 설명변수: 외부지표의 공표시점별 1·2·3·6개월 후보 중 개발 검증에서 선택한 값과 2개월 전 수주용량",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"^- 개발 검증:.*$",
        "- 개발 검증: 2022~2024년 중 최소 48개 학습행을 확보한 월마다 직전 확정자료로 재학습",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        r"예측 기준은 월말에 다음 달 수주용량를 예측하는 것입니다\..*?2025년 점수는 탐색적 테스트로 해석합니다\.",
        "예측 기준은 월말에 다음 달 수주용량을 예측하는 것입니다. 월말까지 직접 산출 가능한 가격·운임은 1·2·3·6개월, 다음 달 이후 공표되는 지표는 2·3·6개월을 후보로 둡니다. 분기·연간 자료는 master에서 공표 가능 시점부터 전방 채운 뒤 1·2·3·6개월을 비교합니다. 피처별 시차는 2022~2024년 월별 검증만으로 하나를 선택하며 2025년 자료는 사용하지 않습니다. 수주 원자료는 발표 지연 때문에 2개월 전 수주용량을 고정 사용합니다. 현재 파일은 당시의 원자료 빈티지까지 복원하지 못하므로 2025년 점수는 탐색적 테스트로 해석합니다.",
        text,
        flags=re.DOTALL,
    )
    text = text.replace(
        "원자료의 과거 수정 빈티지와 정확한 공표 시각은 확인되지 않아 2개월 시차로 사용합니다.",
        "원자료의 과거 수정 빈티지와 정확한 공표 시각은 확인되지 않아 2·3·6개월 시차만 비교합니다.",
    )
    return text


def update_load_data(text: str, ship_type: str) -> str:
    features = SHIP_CARGO_VOLUME_FEATURES[ship_type]
    definition = f"물동량원본피처 = {features!r}"
    if re.search(r"^물동량원본피처 = .*$", text, flags=re.MULTILINE):
        text = re.sub(
            r"^물동량원본피처 = .*$",
            definition,
            text,
            count=1,
            flags=re.MULTILINE,
        )
    else:
        text, replacements = re.subn(
            r"^(원자재원본피처 = .*?)$",
            r"\1\n" + definition,
            text,
            count=1,
            flags=re.MULTILINE,
        )
        if replacements != 1:
            raise ValueError(f"{ship_type} 초기 설정에서 원자재 피처를 찾지 못했습니다.")

    for variable, columns in GLOBAL_FEATURE_GROUPS.items():
        definition = f"{variable} = {columns!r}"
        if re.search(rf"^{variable} = .*?$", text, flags=re.MULTILINE):
            text = re.sub(
                rf"^{variable} = .*?$", definition, text,
                count=1, flags=re.MULTILINE,
            )
        else:
            text, replacements = re.subn(
                r"^(과거수주피처 = .*?)$",
                definition + r"\n\1", text, count=1, flags=re.MULTILINE,
            )
            if replacements != 1:
                raise ValueError(f"{ship_type} 초기 설정에서 과거 수주 피처를 찾지 못했습니다.")

    text, replacements = re.subn(
        r"^원본피처 = \[(.*?)\]$",
        lambda match: (
            match.group(0)
            if "*물동량원본피처" in match.group(1)
            else f"원본피처 = [{match.group(1).replace('*원자재원본피처,', '*원자재원본피처, *물동량원본피처,', 1)}]"
        ),
        text,
        count=1,
        flags=re.MULTILINE,
    )
    if replacements != 1:
        raise ValueError(f"{ship_type} 초기 설정에서 원본피처 목록을 찾지 못했습니다.")
    for variable in GLOBAL_FEATURE_GROUPS:
        token = f"*{variable}"
        combined = re.search(r"^원본피처 = \[(.*?)\]$", text, flags=re.MULTILINE)
        if combined is None:
            raise ValueError(f"{ship_type} 초기 설정에서 원본피처 목록을 찾지 못했습니다.")
        if token not in combined.group(1):
            text = text.replace(
                "*과거수주피처]", f"{token}, *과거수주피처]", 1
            )
    return text


def update_notebook(path: Path) -> None:
    notebook = nbformat.read(path, as_version=4)
    cells = {cell.get("id"): cell for cell in notebook.cells}
    if "model-policy" in cells:
        raise RuntimeError(
            f"{path.name}: 현행 기능별 분리 노트북에는 이 이행 스크립트를 사용할 수 없습니다."
        )
    required = {"scope", "load-data", "data-check", "evaluate-raw-features", "holdout-evaluation"}
    missing = required.difference(cells)
    if missing:
        raise KeyError(f"{path.name} 필수 셀 ID 누락: {sorted(missing)}")

    ship_type = path.stem.removeprefix("수주예측(").removesuffix(")")
    if ship_type not in SHIP_CARGO_VOLUME_FEATURES:
        raise KeyError(f"노트북 이름에서 선종을 확인할 수 없습니다: {path.name}")

    cells["scope"].source = update_scope(cells["scope"].source)
    cells["load-data"].source = update_load_data(cells["load-data"].source, ship_type)
    data_check, replacements = re.subn(
        r"상관열 =.*?(?=\n박스플롯자료 =)",
        HEATMAP_BLOCK + "\n",
        cells["data-check"].source,
        count=1,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise ValueError(f"{path.name} 히트맵 블록을 찾지 못했습니다.")
    cells["data-check"].source = data_check
    cells["evaluate-raw-features"].source = EVALUATION_CELL
    holdout = cells["holdout-evaluation"].source
    holdout = holdout.replace(
        "분할생성(보류자료.index)", "분할생성(보류자료.index, 최종피처)"
    ).replace(
        "분할생성(개발자료.index)", "분할생성(개발자료.index, 최종피처)"
    )
    holdout, replacements = re.subn(
        r"# (?:긴 선은 각 월의 이전 자료만으로 만든 순차 예측입니다|실제값은 검은색으로 유지하고 예측선을 역할별로 분리합니다)\..*?(?=\n# 중요도는)",
        TIME_SERIES_BLOCK,
        holdout,
        count=1,
        flags=re.DOTALL,
    )
    if replacements != 1:
        raise ValueError(f"{path.name} 시계열 그래프 블록을 찾지 못했습니다.")
    cells["holdout-evaluation"].source = holdout

    for cell in notebook.cells:
        if cell.cell_type == "code":
            cell.outputs = []
            cell.execution_count = None
    nbformat.write(notebook, path)
    print(f"수정: {path.name}")


def main() -> None:
    if len(NOTEBOOKS) != 5:
        raise RuntimeError(f"대상 노트북은 5개여야 합니다: {[path.name for path in NOTEBOOKS]}")
    for notebook in NOTEBOOKS:
        update_notebook(notebook)


if __name__ == "__main__":
    main()
