import { useMemo, useState, type CSSProperties } from "react";
import { BookOpen, Database, Search } from "lucide-react";
import dictionary from "../../data/vesselDataDictionary.json";
import "../../styles/data-dictionary.css";

type VesselKey = keyof typeof dictionary;
type DictionaryTab = "common" | VesselKey;
type Category = "기본 정보" | "수주·공급" | "교역·물동량" | "가격·운임" | "거시경제" | "지정학·정책" | "파생 변수" | "데이터 품질";

const vesselOrder: VesselKey[] = ["container", "tanker", "bulk", "gas", "chemical"];
const vesselColors: Record<VesselKey, string> = {
  container: "#2563eb",
  tanker: "#dc3c52",
  bulk: "#d18b00",
  gas: "#7c5ce0",
  chemical: "#07826e",
};

const normalizeColumn = (name: string) => name.replace(/\((DWT|TEU|CBM)\)/g, "(CAPACITY)");
const columnVesselCounts = vesselOrder.reduce((counts, id) => {
  new Set(dictionary[id].columns.map(normalizeColumn)).forEach((name) => counts.set(name, (counts.get(name) ?? 0) + 1));
  return counts;
}, new Map<string, number>());
const commonColumns = [...new Set(vesselOrder.flatMap((id) => dictionary[id].columns.map(normalizeColumn)))]
  .filter((name) => (columnVesselCounts.get(name) ?? 0) > 1)
  .map((name) => name.replace("(CAPACITY)", "(선종별 단위)"));
const vesselOnlyColumns = Object.fromEntries(vesselOrder.map((id) => [
  id,
  dictionary[id].columns.filter((name) => columnVesselCounts.get(normalizeColumn(name)) === 1),
])) as Record<VesselKey, string[]>;

function categoryOf(name: string): Category {
  if (/기준월|수주용량단위|수주정보시차|수주정보가용근거/.test(name)) return "기본 정보";
  if (/최근확정|개월 전|직전3개월|month(_sin|_cos)?$|변화량/.test(name)) return "파생 변수";
  if (/구분|결측처리방법|값구분/.test(name)) return "데이터 품질";
  if (/GPR|전쟁|군비|핵위협|테러|TPU/.test(name)) return "지정학·정책";
  if (/환율|달러지수|세계 실질|산업생산|공급망압력|영업현금흐름률|탄소가격/.test(name)) return "거시경제";
  if (/운임|용선료|신조선가|가격|벙커유/.test(name)) return "가격·운임";
  if (/톤마일|수에즈|수입|수출|컨테이너 처리량|생산량|LNG 수출량/.test(name)) return "교역·물동량";
  return "수주·공급";
}
function descriptionOf(name: string) {
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

function unitOf(name: string) {
  const unit = name.match(/\(([^)]+)\)(?!.*\()/)?.[1];
  if (!unit) return name.includes("(%)") ? "%" : "지수·구분값";
  return unit;
}

export default function DataDictionary() {
  const [vessel, setVessel] = useState<DictionaryTab>("common");
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState<"전체" | Category>("전체");
  const columns = vessel === "common" ? commonColumns : vesselOnlyColumns[vessel];
  const activeLabel = vessel === "common" ? "공통변수" : dictionary[vessel].label;
  const activeColor = vessel === "common" ? "#94a3b8" : vesselColors[vessel];
  const categories = useMemo(() => Array.from(new Set(columns.map(categoryOf))) as Category[], [columns]);
  const visible = columns.filter((name) => {
    const description = descriptionOf(name);
    return (category === "전체" || categoryOf(name) === category) &&
      (!query.trim() || `${name} ${description}`.toLowerCase().includes(query.trim().toLowerCase()));
  });

  return (
    <section className="data-dictionary-page" aria-labelledby="data-dictionary-title">
      <header className="data-dictionary-header">
        <div><span><BookOpen size={15} /> DATA GUIDE</span><h2 id="data-dictionary-title">예측 데이터 설명</h2><p>선종별 원천 데이터의 변수와 분석에서 사용되는 의미를 확인할 수 있습니다.</p></div>
        <div className="data-dictionary-count"><Database size={18} /><span><b>{columns.length}</b>개 변수</span></div>
      </header>
      <div className="data-dictionary-vessels" role="tablist" aria-label="선종 선택">
        <button type="button" role="tab" aria-selected={vessel === "common"} onClick={() => { setVessel("common"); setCategory("전체"); }}>공통변수<span>{commonColumns.length}</span></button>
        {vesselOrder.map((id) => <button key={id} type="button" role="tab" aria-selected={vessel === id} onClick={() => { setVessel(id); setCategory("전체"); }}>{dictionary[id].label}<span>{vesselOnlyColumns[id].length}</span></button>)}
      </div>
      <div className="data-dictionary-tools">
        <label><Search size={16} /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="변수명 또는 설명 검색" /></label>
        <div className="data-dictionary-categories"><button type="button" className={category === "전체" ? "is-active" : ""} onClick={() => setCategory("전체")}>전체</button>{categories.map((item) => <button key={item} type="button" className={category === item ? "is-active" : ""} onClick={() => setCategory(item)}>{item}</button>)}</div>
      </div>
      <div className="data-dictionary-summary"><strong>{activeLabel}</strong><span>검색 결과 {visible.length}개</span></div>
      {vessel !== "common" && <div className="data-dictionary-legend"><i style={{ background: vesselColors[vessel] }} /><span><b>{dictionary[vessel].label}에서만 사용하는 변수</b>입니다.</span></div>}
      <div className="data-dictionary-table-wrap">
        <table><thead><tr><th>변수명</th><th>분류</th><th>단위</th><th>의미</th></tr></thead><tbody>{visible.map((name) => {
          const vesselOnly = vessel !== "common" && columnVesselCounts.get(normalizeColumn(name)) === 1;
          return <tr key={name} className={vesselOnly ? "is-vessel-only" : undefined} style={vesselOnly ? { "--vessel-color": activeColor } as CSSProperties : undefined}><td><code>{name}</code>{vesselOnly && <small>{activeLabel} 전용</small>}</td><td><span className="data-category-badge">{categoryOf(name)}</span></td><td>{unitOf(name)}</td><td>{descriptionOf(name)}</td></tr>;
        })}</tbody></table>
        {!visible.length && <div className="data-dictionary-empty">검색 조건에 맞는 변수가 없습니다.</div>}
      </div>
      <p className="data-dictionary-footnote">설명은 현재 CSV 헤더와 단위를 기준으로 정리했습니다. 최종 데이터 사전과 산식이 제공되면 정의·출처·갱신 주기를 추가할 수 있습니다.</p>
    </section>
  );
}
