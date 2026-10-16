export function descriptionOf(name: string) {
  const exact: Record<string, string> = {
    "기준월": "해당 관측값이 속하는 연도와 월입니다.",
    "수주용량": "해당 월에 새로 발주된 선박의 총 수주용량으로, 예측의 핵심 목표 변수입니다.",
    "수주용량단위": "선종별 수주용량 단위입니다. 컨테이너선은 TEU, 가스 운반선은 CBM, 그 외 선종은 DWT를 사용합니다.",
    "수주정보시차(개월)": "수주 정보가 실제 분석 시점에 공개되기까지 걸리는 개월 수입니다.",
    "수주정보가용근거": "해당 수주값을 특정 시점에 사용할 수 있다고 판단한 근거입니다.",
    "직전3개월누적수주량": "기준월 직전 3개월의 수주용량을 합산한 단기 수요 흐름 지표입니다.",
    "month": "계절성을 학습하기 위해 숫자 1~12로 표현한 월입니다.",
    "month_sin": "12개월 주기의 순환성을 자연스럽게 표현한 월의 사인 변환값입니다.",
    "month_cos": "12개월 주기의 순환성을 자연스럽게 표현한 월의 코사인 변환값입니다.",
    "인도량_구분": "인도량 값의 관측 또는 처리 상태를 구분하는 품질 관리 변수입니다.",
    "인도량_결측처리방법": "인도량 결측값에 적용한 보완 방식을 기록한 변수입니다.",
    "중국 금속컨테이너 생산량 값구분": "중국 금속컨테이너 생산량 값의 관측 또는 처리 상태를 나타냅니다.",
    "세계 GPR(지수)": "전 세계 지정학적 위험 수준을 측정한 GPR 지수입니다.",
    "위협 GPRT(지수)": "지정학적 위협 관련 기사 빈도를 바탕으로 산출한 위험 지수입니다.",
    "행동 GPRA(지수)": "실제로 발생한 지정학적 행동·사건 관련 기사 기반 지수입니다.",
    "GPRT-GPRA(차)": "지정학적 위협 지수와 실제 행동 지수의 차이입니다.",
    "GPR 월변화(차)": "세계 GPR 지수의 전월 대비 증감분입니다.",
    "GPR 3개월변화(차)": "세계 GPR 지수의 3개월 전 대비 증감분입니다.",
    "미국 TPU·EPUTRADE(지수)": "미국의 무역정책 불확실성을 뉴스 기반으로 측정한 EPU Trade 지수입니다.",
    "미국 TPU·Caldara(지수)": "Caldara 연구 방식으로 측정한 미국 무역정책 불확실성 지수입니다.",
    "중국 TPU(지수)": "중국의 무역정책 불확실성 수준을 나타내는 지수입니다.",
  };
  if (exact[name]) return exact[name];
  const lag = name.match(/수주용량 (\d+)개월 전/);
  if (lag) return `기준월보다 ${lag[1]}개월 앞선 시점의 수주용량입니다. 최근 수주 흐름의 시차 효과를 반영합니다.`;
  const confirmed = name.match(/수주용량_최근확정(\d+)개월차/);
  if (confirmed) return `분석 시점에서 확인 가능한 최근 확정 수주값을 ${confirmed[1]}개월차 기준으로 정렬한 파생 변수입니다.`;
  const change = name.match(/(.+) 변화량\((.+)\)/);
  if (change) return `${change[1]}의 ${change[2]} 차이를 나타내는 파생 변수입니다.`;
  if (name.includes("_YoY(%)")) return `${name.split("_YoY")[0].replaceAll("_", " ")}의 전년 동월 대비 증감률입니다.`;
  if (name.startsWith("인도량")) return "해당 월에 인도되어 시장에 투입된 선박의 총 용량입니다.";
  if (name.startsWith("수주잔량")) return "아직 인도되지 않고 조선소가 보유한 계약 물량의 총 용량입니다.";
  if (name.includes("톤마일대리지표")) return "화물량과 운송거리를 결합해 해상 운송 수요를 근사한 톤마일 지표입니다.";
  if (name.includes("수에즈") && name.includes("통과횟수")) return "수에즈 운하를 통과한 선박의 월간 횟수로 주요 항로의 통행량을 보여줍니다.";
  if (name.includes("수에즈") && name.includes("순톤수")) return "수에즈 운하 통과 선박의 월간 순톤수 합계입니다.";
  if (name.includes("환율")) return "표시된 두 통화 간 월간 환율입니다.";
  if (name.includes("운임") || name.includes("용선료")) return "표시된 선종·항로의 월간 운송 또는 용선 가격 지표입니다.";
  if (name.includes("가격") || name.includes("가격지수")) return "표시된 원자재·에너지·자산의 월간 가격 또는 가격지수입니다.";
  if (name.includes("현존선복량")) return "해당 시점에 시장에서 운항 가능한 선박 용량의 총합입니다.";
  if (name.includes("리그")) return "석유 또는 가스 개발 활동에 투입된 가동 리그 수입니다.";
  if (name.includes("세계 실질수출")) return "물가 영향을 제거하고 계절 조정한 세계 상품 수출 규모입니다.";
  if (name.includes("세계 실질수입")) return "물가 영향을 제거하고 계절 조정한 세계 상품 수입 규모입니다.";
  if (name.includes("세계 산업생산")) return "세계 산업 부문의 실질 생산 활동 수준입니다.";
  if (name.includes("달러지수")) return "미국 달러의 가치를 주요 교역 상대국 통화로 가중해 나타낸 지수입니다.";
  if (name.includes("GPR(%)") || /전쟁|군비|핵위협|테러/.test(name)) return "전체 지정학적 위험 기사에서 해당 주제가 차지하는 비중입니다.";
  if (name.includes("컨테이너 처리량")) return "전 세계 주요 항만의 컨테이너 처리 활동을 지수화한 값입니다.";
  if (name.includes("수출량") || name.includes("수출(")) return "표시된 품목 또는 산업의 월간 수출 규모입니다.";
  if (name.includes("생산량")) return "표시된 산업 품목의 월간 생산 규모입니다.";
  if (name.includes("공급망압력")) return "글로벌 공급망의 지연과 비용 압력을 표준화해 나타낸 지표입니다.";
  if (name.includes("영업현금흐름률")) return "기업의 최근 12개월 영업활동 현금 창출 수준을 비율로 나타낸 값입니다.";
  if (name.includes("탄소가격")) return "탄소배출권 1톤당 시장 가격입니다.";
  if (name.includes("벙커유 판매")) return "싱가포르에서 판매된 선박용 연료의 월간 물량입니다.";
  return "선박 수요와 시장 환경의 변화를 설명하기 위해 수집한 월간 입력 변수입니다.";
}
