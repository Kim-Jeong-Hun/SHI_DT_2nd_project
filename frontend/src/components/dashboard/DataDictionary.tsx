import { useMemo, useState, type CSSProperties } from "react";
import { BookOpen, Database, Search } from "lucide-react";
import dictionary from "../../data/vesselDataDictionary.json";
import { descriptionOf } from "../../data/dataDictionaryDescriptions";
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
