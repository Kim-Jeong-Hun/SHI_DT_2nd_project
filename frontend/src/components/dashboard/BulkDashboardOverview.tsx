import { useEffect, useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import { Activity, BarChart3, CircleHelp, Database } from "lucide-react";

type BulkPoint = { month: string; value: number; unit: string };
type MasterDataResponse = { rows: Array<{ period: string; orderCapacity: string | null; unit: string }> };

const compact = (value: number) => value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M` : value >= 1_000 ? `${(value / 1_000).toFixed(0)}K` : value.toFixed(0);
export default function BulkDashboardOverview() {
  const [points, setPoints] = useState<BulkPoint[]>();
  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/master-data?vesselId=bulk", { credentials: "same-origin", signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<MasterDataResponse> : Promise.reject())
      .then((payload) => setPoints(payload.rows.flatMap((row) => {
        if (row.orderCapacity === null || row.orderCapacity.trim() === "") return [];
        const value = Number(row.orderCapacity);
        return Number.isFinite(value) ? [{ month: row.period, value, unit: row.unit }] : [];
      })))
      .catch(() => { if (!controller.signal.aborted) setPoints([]); });
    return () => controller.abort();
  }, []);

  const recent = points?.slice(-30) ?? [];
  const latestSix = points?.slice(-6) ?? [];
  const latest = points?.at(-1);
  const unit = latest?.unit ?? "DWT";

  const chartOption = {
    animationDuration: 600,
    grid: { left: 60, right: 22, top: 26, bottom: 35 },
    tooltip: { trigger: "axis", backgroundColor: "#102747", borderWidth: 0, textStyle: { color: "#fff" }, valueFormatter: (value: unknown) => `${Number(value).toLocaleString("ko-KR", { maximumFractionDigits: 1 })} ${unit}` },
    xAxis: { type: "category", data: recent.map((point) => point.month), boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: "#dbe4ef" } }, axisLabel: { color: "#718096", fontSize: 10, formatter: (value: string, index: number) => index % 5 === 0 ? value.replace("-", ".") : "" } },
    yAxis: { type: "value", scale: true, name: unit, nameTextStyle: { color: "#64748b" }, axisLabel: { color: "#718096", fontSize: 10, formatter: compact }, splitLine: { lineStyle: { color: "#e7edf5", type: "dashed" } } },
    series: [{ name: "실제 실적", type: "line", symbol: "none", smooth: .2, data: recent.map((point) => point.value), lineStyle: { color: "#173f70", width: 2.2 }, areaStyle: { color: "rgba(59,130,246,.08)" } }],
  };

  return <section id="dashboard-overview" className="overview-redesign dashboard-view dashboard-section-target">
    <section className="overview-market-brief"><div className="overview-brief-copy"><div className="overview-eyebrow"><Activity size={16} /> MARKET BRIEF</div><h1>벌크선의 <mark>최근 수주 흐름</mark>을 확인하세요.</h1><h2>최근 6개월 실적과 고점 구간을 바탕으로 영업·생산 대응 시점을 점검할 수 있습니다.</h2><p>{latest ? `${latest.month}까지의 실제 수주 실적을 반영했습니다.` : "최신 수주 실적을 불러오고 있습니다."}</p></div></section>
    <div className="overview-core-grid">
      <section className="overview-panel overview-timeseries-panel"><header><h3>벌크선 실제 수주 실적 <CircleHelp size={14} /></h3><span>{unit}</span></header><div className="overview-chart-body">{points === undefined ? <div className="overview-chart-placeholder">실제 수주 데이터를 불러오는 중입니다.</div> : recent.length ? <EChartsReact option={chartOption} notMerge lazyUpdate /> : <div className="overview-chart-placeholder">연결된 실제 수주 데이터가 없습니다.</div>}</div></section>
      <section className="overview-panel overview-heatmap-panel"><header><h3>최근 6개월 실제 수주용량 <CircleHelp size={14} /></h3><span>예측값 아님</span></header><div className="bulk-month-grid">{latestSix.map((point) => <div key={point.month}><span>{point.month.slice(5)}월</span><strong>{compact(point.value)}</strong><small>{point.unit}</small></div>)}</div></section>
    </div>
    <div className="overview-analysis-grid">
      <section className="overview-panel bulk-unavailable-panel"><header><h3>수주 전망 주요 기여 변수</h3><span>미연결</span></header><div><Database size={25} /><strong>예측 노트북 준비 중</strong><p>벌크선 모델이 제공되면 SHAP 기여 변수를 표시합니다.</p></div></section>
      <section className="overview-panel bulk-unavailable-panel"><header><h3>예측 모델 검증 성능</h3><span>미연결</span></header><div><BarChart3 size={25} /><strong>검증 결과 없음</strong><p>임의의 정확도나 예측값은 표시하지 않습니다.</p></div></section>
    </div>
  </section>;
}
