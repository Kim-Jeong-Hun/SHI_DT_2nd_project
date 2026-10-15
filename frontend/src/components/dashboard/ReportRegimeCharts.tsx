import { useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import type { EChartsType } from "echarts";
import reportCharts from "../../data/reportFirstCharts.json";
import type { VesselId } from "../../data/mockMarket";

interface Regime { c: number; label: string }
interface QuarterSegment { c: number; raw: number; idx: number; share: number }
interface Quarter {
  label: string; year: number; months: number; monthList: number[];
  total: number; totalIdx: number; segs: QuarterSegment[]; freightIdx: number;
}
interface FreightPoint { x: number; v: number; raw: number; d: string }
interface ComboData {
  title: string; subtitle: string; unit: string; freightName: string; freightUnit: string;
  regimes: Regime[]; quarters: Quarter[]; line: FreightPoint[];
}
interface ScatterPoint { x: number; y: number; c: number; d: string }
interface Centroid { c: number; x: number; y: number; n: number }
interface ScatterData {
  title: string; note: string; xName: string; yName: string; xUnit: string; yUnit: string;
  regimes: Regime[]; points: ScatterPoint[]; centroids: Centroid[];
}
interface ChartPair { combo: ComboData; scatter: ScatterData }
interface VesselCharts { macro: ChartPair; specific: ChartPair }

const vessels = reportCharts.vessels as Record<VesselId, VesselCharts>;
const lightRegimeColors = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300"];
const darkRegimeColors = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"];
const formatNumber = (value: number) => value.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
const escapeHtml = (value: string) => value.replace(/[&<>"']/g, (char) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[char] ?? char);

function chartStyle(darkMode: boolean) {
  return {
    text: darkMode ? "#cbd5e1" : "#64748b",
    grid: darkMode ? "#334155" : "#e4e3dd",
    surface: darkMode ? "#1e293b" : "#fff",
    tooltip: darkMode ? "#0f172a" : "#fff",
    ink: darkMode ? "#f8fafc" : "#1f2937",
    colors: darkMode ? darkRegimeColors : lightRegimeColors,
  };
}

function tooltipRow(label: string, value: string, unit: string, darkMode: boolean) {
  const muted = darkMode ? "#94a3b8" : "#64748b";
  const ink = darkMode ? "#f8fafc" : "#1f2937";
  return `<div style="display:flex;justify-content:space-between;align-items:baseline;gap:16px;margin-top:7px;line-height:1.4">` +
    `<span style="color:${muted};font-size:12px;flex-shrink:0">${escapeHtml(label)}</span>` +
    `<span style="color:${ink};font-size:13px;font-weight:700;text-align:right;white-space:nowrap">${escapeHtml(value)}` +
    (unit ? ` <small style="font-size:11px;font-weight:400;color:${muted}">${escapeHtml(unit)}</small>` : "") +
    `</span></div>`;
}

function tooltipCard(title: string, kind: string, body: string, detail: string, darkMode: boolean) {
  const ink = darkMode ? "#f8fafc" : "#1f2937";
  const muted = darkMode ? "#94a3b8" : "#64748b";
  const border = darkMode ? "#334155" : "#e2e8f0";
  return `<div style="width:260px;padding:12px 14px;font-family:inherit;white-space:normal;box-sizing:border-box">` +
    `<div style="color:${muted};font-size:11px;font-weight:600;letter-spacing:.02em">${escapeHtml(kind)}</div>` +
    `<div style="color:${ink};font-size:14px;font-weight:700;line-height:1.4;margin-top:2px">${escapeHtml(title)}</div>` +
    `<div style="border-top:1px solid ${border};margin-top:9px;padding-top:3px">${body}</div>` +
    (detail ? `<div style="border-top:1px solid ${border};color:${muted};font-size:11px;line-height:1.5;margin-top:10px;padding-top:8px;overflow-wrap:anywhere">${escapeHtml(detail)}</div>` : "") +
    `</div>`;
}

function comboOption(combo: ComboData, darkMode: boolean) {
  const style = chartStyle(darkMode);
  return {
    animation: true,
    animationDuration: 900,
    animationDurationUpdate: 450,
    animationEasing: "cubicOut",
    animationDelay: (index: number) => index * 18,
    animationDelayUpdate: (index: number) => index * 10,
    grid: { left: 54, right: 18, top: 42, bottom: 86 },
    tooltip: {
      trigger: "item", backgroundColor: style.tooltip, borderColor: style.grid,
      textStyle: { color: style.ink }, confine: true, padding: 0,
      extraCssText: "border-radius:12px;box-shadow:0 10px 28px rgba(15,23,42,.18)",
      formatter: (params: { seriesType: string; dataIndex: number }) => {
        if (params.seriesType === "line") {
          const point = combo.line[params.dataIndex];
          if (!point) return "";
          const body = tooltipRow("운임", formatNumber(point.raw), combo.freightUnit, darkMode) +
            tooltipRow("평균=100 지수", formatNumber(point.v), "", darkMode);
          return tooltipCard(point.d, "월별 운임", body, combo.freightName, darkMode);
        }
        const quarter = combo.quarters[params.dataIndex];
        if (!quarter) return "";
        const regimeRows = quarter.segs.filter((segment) => segment.raw > 0).map((segment) => {
          const label = combo.regimes.find((regime) => regime.c === segment.c)?.label ?? `C${segment.c}`;
          const color = style.colors[segment.c - 1];
          return `<div style="margin-top:9px;font-size:11px;line-height:1.4">` +
            `<div style="display:flex;align-items:baseline;gap:6px;color:${style.ink}"><i style="display:inline-block;width:8px;height:8px;flex-shrink:0;border-radius:2px;background:${color}"></i>${escapeHtml(label)}</div>` +
            `<div style="color:${style.text};padding-left:14px;margin-top:2px">${formatNumber(segment.raw)} ${escapeHtml(combo.unit)} · ${formatNumber(segment.share * 100)}%</div></div>`;
        }).join("");
        const body = tooltipRow("전체 수주량", formatNumber(quarter.total), combo.unit, darkMode) +
          tooltipRow("평균=100 지수", formatNumber(quarter.totalIdx), "", darkMode) +
          (regimeRows ? `<div style="border-top:1px solid ${style.grid};margin-top:10px;padding-top:8px;color:${style.text};font-size:11px;font-weight:600">국면별 수주</div>${regimeRows}` : "");
        return tooltipCard(quarter.label, "분기 수주", body, quarter.months < 3 ? "일부 달만 포함된 분기" : "", darkMode);
      },
    },
    xAxis: [
      {
        type: "category", data: combo.quarters.map((quarter) => quarter.label), boundaryGap: true,
        axisLine: { lineStyle: { color: style.grid } }, axisTick: { show: false },
        axisLabel: { color: style.text, fontSize: 11, interval: 0,
          formatter: (_: string, index: number) => index === 0 || combo.quarters[index - 1].year !== combo.quarters[index].year ? String(combo.quarters[index].year) : "" },
      },
      { type: "value", min: -0.5, max: combo.quarters.length - 0.5, show: false },
    ],
    yAxis: {
      type: "value", name: "전체 평균=100", nameTextStyle: { color: style.text },
      splitLine: { lineStyle: { color: style.grid } },
      axisLabel: { color: style.text, fontSize: 11 },
    },
    dataZoom: [
      { type: "inside", xAxisIndex: [0, 1], start: 0, end: 100, minSpan: 12, filterMode: "none" },
      { type: "slider", xAxisIndex: [0, 1], start: 0, end: 100, minSpan: 12,
        filterMode: "none",
        bottom: 10, height: 18, showDataShadow: false, showDetail: false,
        backgroundColor: darkMode ? "#0f172a" : "#f1f5f9", borderColor: style.grid,
        fillerColor: darkMode ? "rgba(59,130,246,.25)" : "rgba(59,130,246,.14)" },
    ],
    series: [
      ...combo.regimes.map((regime) => ({
        name: regime.label, type: "bar", stack: "orders", barMaxWidth: 18,
        animationDelay: (index: number) => index * 18,
        itemStyle: { color: style.colors[regime.c - 1] },
        data: combo.quarters.map((quarter) => {
          const segment = quarter.segs.find((item) => item.c === regime.c);
          return { value: segment?.idx ?? 0,
            itemStyle: quarter.months < 3 ? { decal: { symbol: "rect", symbolSize: 1, dashArrayX: [2, 2], dashArrayY: [3, 2], color: "rgba(255,255,255,.55)" } } : undefined };
        }),
      })),
      {
        name: combo.freightName, type: "line", xAxisIndex: 1, symbol: "circle", showSymbol: true,
        animationDelay: (index: number) => index * 18,
        symbolSize: 12, triggerEvent: "line",
        lineStyle: { color: style.ink, width: 2.4 },
        itemStyle: { color: "rgba(0,0,0,0)" },
        emphasis: { scale: false, itemStyle: { color: style.ink } }, z: 10,
        data: combo.line.map((point) => [point.x, point.v]),
      },
    ],
  };
}

function lineHoverEvents(combo: ComboData) {
  const lineSeriesIndex = combo.regimes.length;
  return {
    mousemove: (params: { seriesIndex?: number; seriesType?: string; dataIndex?: number; event?: { offsetX?: number } }, chart: EChartsType) => {
      if (params.seriesIndex !== lineSeriesIndex || params.seriesType !== "line" || params.dataIndex != null) return;
      const mouseX = params.event?.offsetX;
      if (mouseX == null) return;
      const dataX = chart.convertFromPixel({ xAxisIndex: 1 }, mouseX) as number;
      if (!Number.isFinite(dataX)) return;
      let nearest = 0;
      for (let i = 1; i < combo.line.length; i++) {
        if (Math.abs(combo.line[i].x - dataX) < Math.abs(combo.line[nearest].x - dataX)) nearest = i;
      }
      chart.dispatchAction({ type: "showTip", seriesIndex: lineSeriesIndex, dataIndex: nearest });
    },
  };
}

function scatterOption(scatter: ScatterData, darkMode: boolean) {
  const style = chartStyle(darkMode);
  return {
    animation: true,
    animationDuration: 650,
    animationDurationUpdate: 350,
    animationEasing: "cubicOut",
    grid: { left: 55, right: 18, top: 20, bottom: 52 },
    tooltip: {
      trigger: "item", backgroundColor: style.tooltip, borderColor: style.grid,
      textStyle: { color: style.ink }, confine: true, padding: 0,
      extraCssText: "border-radius:12px;box-shadow:0 10px 28px rgba(15,23,42,.18)",
      formatter: (params: { seriesName: string; data: { name: string; value: number[]; count?: number } }) => {
        const body = tooltipRow(scatter.xName, formatNumber(params.data.value[0]), scatter.xUnit, darkMode) +
          tooltipRow(scatter.yName, formatNumber(params.data.value[1]), scatter.yUnit, darkMode);
        return tooltipCard(params.data.name, params.data.count ? "국면 대표값" : "월별 관측값", body,
          `${params.seriesName}${params.data.count ? ` · ${params.data.count}개월` : ""}`, darkMode);
      },
    },
    xAxis: {
      type: "value", name: scatter.xUnit, nameLocation: "end", nameTextStyle: { color: style.text },
      splitLine: { lineStyle: { color: style.grid } }, axisLabel: { color: style.text, fontSize: 11 },
    },
    yAxis: {
      type: "value", name: scatter.yUnit, nameTextStyle: { color: style.text },
      splitLine: { lineStyle: { color: style.grid } }, axisLabel: { color: style.text, fontSize: 11 },
    },
    series: [
      ...scatter.regimes.map((regime) => ({
        name: regime.label, type: "scatter", symbolSize: 6,
        animationDelay: () => (regime.c - 1) * 90,
        itemStyle: { color: style.colors[regime.c - 1], opacity: 0.72 },
        data: scatter.points.filter((point) => point.c === regime.c)
          .map((point) => ({ name: point.d, value: [point.x, point.y] })),
      })),
      ...scatter.regimes.map((regime) => ({
        name: `${regime.label} 대표값`, type: "scatter", symbol: "diamond", symbolSize: 17, z: 10,
        animationDelay: () => 450 + (regime.c - 1) * 90,
        itemStyle: { color: style.colors[regime.c - 1], borderColor: style.surface, borderWidth: 2 },
        data: scatter.centroids.filter((point) => point.c === regime.c)
          .map((point) => ({ name: "국면 대표값(중앙값)", value: [point.x, point.y], count: point.n })),
      })),
    ],
  };
}

function RegimeRow({ pair, darkMode }: { pair: ChartPair; darkMode: boolean }) {
  const colors = chartStyle(darkMode).colors;
  return (
    <div className="mt-3 report-regime-row">
      <div className="mt-2 grid gap-3 lg:grid-cols-[minmax(0,2fr)_minmax(0,1fr)]">
        <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <h4 className="text-xs font-semibold text-slate-800">수주·운임 추이</h4>
          <EChartsReact className="mt-2" option={comboOption(pair.combo, darkMode)} onEvents={lineHoverEvents(pair.combo)} notMerge lazyUpdate style={{ height: "var(--report-chart-height, 310px)", width: "100%" }} />
        </div>
        <div className="min-w-0 rounded-xl border border-slate-200 bg-slate-50 p-3">
          <h4 className="text-xs font-semibold text-slate-800">시장 국면 분포</h4>
          <p className="mt-1 text-[11px] leading-4 text-slate-500">운임 변화율 × {pair.scatter.yName}</p>
          <EChartsReact option={scatterOption(pair.scatter, darkMode)} notMerge lazyUpdate style={{ height: "var(--report-chart-height, 310px)", width: "100%" }} />
        </div>
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11px] text-slate-500">
        {pair.combo.regimes.map((regime) => (
          <span key={regime.c} className="inline-flex items-center gap-1.5">
            <i className="h-2.5 w-2.5 shrink-0 rounded-sm" style={{ backgroundColor: colors[regime.c - 1] }} />{regime.label}
          </span>
        ))}
      </div>
    </div>
  );
}

export default function ReportRegimeCharts({ vesselId, vesselLabel, darkMode }: { vesselId: VesselId; vesselLabel: string; darkMode: boolean }) {
  const charts = vessels[vesselId];
  const [activeRegime, setActiveRegime] = useState<"macro" | "specific">("macro");
  const activePair = activeRegime === "macro" ? charts.macro : charts.specific;
  return (
    <div aria-label={`${vesselLabel} 수주와 운임`} className="report-regime-tabs">
      <div role="tablist" aria-label="수주와 운임 변수 유형" className="mt-4 flex gap-1 rounded-lg bg-slate-100 p-1">
        {([ ["macro", "공통 거시 변수"], ["specific", "선종 고유 변수"] ] as const).map(([regime, label]) => (
          <button key={regime} id={`regime-tab-${regime}`} type="button" role="tab"
            aria-selected={activeRegime === regime} aria-controls="regime-panel"
            onClick={() => setActiveRegime(regime)}
            className={`flex-1 rounded-md px-3 py-2 text-xs font-semibold transition ${activeRegime === regime ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-900"}`}
          >{label}</button>
        ))}
      </div>
      <div id="regime-panel" role="tabpanel" aria-labelledby={`regime-tab-${activeRegime}`}>
        <RegimeRow key={activeRegime} pair={activePair} darkMode={darkMode} />
      </div>
      <p className="mt-3 text-[11px] text-slate-500">자료: 군집분석 전체과정 보고서 3절 · 원본 분기 수주량과 월별 운임을 평균=100 지수로 표시</p>
    </div>
  );
}
