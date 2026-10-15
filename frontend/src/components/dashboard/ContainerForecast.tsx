import EChartsReact from "../common/LocalizedECharts";
import { ArrowDownRight, ArrowUpRight } from "lucide-react";
import type { VesselId } from "../../data/mockMarket";
import { NOTEBOOK_FORECASTS, isNotebookVessel } from "../../data/notebookForecasts";
import { NOTEBOOK_VESSEL_IDS } from "../../data/notebookForecasts";
import { useI18n } from "../../i18n";

const number = (value: number, maximumFractionDigits = 0) =>
  value.toLocaleString("ko-KR", { maximumFractionDigits });

function compact(value: number, unit: string, language: "ko" | "en" = "ko") {
  if (language === "en") {
    if (value >= 1_000_000) return `${number(value / 1_000_000, 1)}M ${unit}`;
    if (value >= 1_000) return `${number(value / 1_000, 1)}K ${unit}`;
  }
  if (value >= 10_000) return `${number(value / 10_000, 1)}만 ${unit}`;
  return `${number(value, 1)} ${unit}`;
}

export function PortfolioForecast({ darkMode }: { darkMode: boolean }) {
  const { language } = useI18n();
  const forecasts = NOTEBOOK_VESSEL_IDS.map((id) => NOTEBOOK_FORECASTS[id]);
  const text = darkMode ? "#cbd5e1" : "#64748b";
  const grid = darkMode ? "#334155" : "#e8edf4";
  const option = {
    animationDuration: 750,
    grid: { left: 92, right: 36, top: 18, bottom: 32 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: darkMode ? "#0f172a" : "#fff", borderColor: grid, textStyle: { color: darkMode ? "#f1f5f9" : "#1e293b" }, formatter: (params: Array<{ dataIndex: number; value: number; marker: string }>) => `${params[0]?.marker ?? ""}${forecasts[params[0]?.dataIndex ?? 0].vesselName}<br/><b>${params[0]?.value > 0 ? "+" : ""}${params[0]?.value.toFixed(1)}%</b>` },
    xAxis: { type: "value", axisLabel: { color: text, formatter: (value: number) => `${value}%` }, splitLine: { lineStyle: { color: grid, type: "dashed" } } },
    yAxis: { type: "category", inverse: true, data: forecasts.map(({ vesselName }) => vesselName), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: text, fontSize: 12 } },
    series: [{ type: "bar", barWidth: 24, label: { show: true, position: "right", formatter: ({ value }: { value: number }) => `${value > 0 ? "+" : ""}${value.toFixed(1)}%`, color: text, fontWeight: 600 }, data: forecasts.map(({ quarterChange, color }) => ({ value: quarterChange, itemStyle: { color: quarterChange >= 0 ? color : "#f43f5e", borderRadius: quarterChange >= 0 ? [0, 6, 6, 0] : [6, 0, 0, 6] } })) }],
    media: [{
      query: { maxWidth: 560 },
      option: {
        grid: { left: 72, right: 34, top: 12, bottom: 28 },
        xAxis: { axisLabel: { fontSize: 9 } },
        yAxis: { axisLabel: { fontSize: 10 } },
        series: [{ barWidth: 18, label: { fontSize: 9 } }],
      },
    }],
  };

  return (
    <section className="analysis-panel container-forecast-panel rounded-2xl border border-slate-200/85 bg-white p-5 shadow-[0_4px_24px_rgba(21,44,79,0.035)]">
      <div>
        <div className="flex items-center gap-2"><h2 className="text-base font-semibold text-slate-900">분기 수주 전망</h2></div>
        <p className="mt-1 text-xs text-slate-500">2026년 6월 데이터 마감 · 5개 최종 모델 연결</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        {forecasts.map((forecast) => (
          <div key={forecast.vesselId} className="rounded-xl border border-slate-200 bg-slate-50 p-4">
            <div className="flex items-start justify-between gap-3"><p className="text-sm font-semibold text-slate-800">{forecast.vesselName}</p><span className={`text-lg font-bold ${forecast.quarterChange >= 0 ? "text-emerald-600" : "text-rose-600"}`}>{forecast.quarterChange > 0 ? "+" : ""}{forecast.quarterChange.toFixed(1)}%</span></div>
            <p className="mt-3 text-xs text-slate-500">4분기 누적 전망</p>
            <p className="mt-1 text-lg font-semibold text-slate-900">{compact(forecast.q4, forecast.unit, language)}</p>
            <p className="mt-2 text-[11px] text-slate-500">고점 {forecast.peakMonth} · Test 오차 {forecast.testRelativeError.toFixed(1)}%</p>
          </div>
        ))}
      </div>
      <div className="min-h-[280px] flex-1 rounded-xl border border-slate-100 bg-white p-2"><EChartsReact option={option} notMerge style={{ height: "100%", minHeight: 280, width: "100%" }} /></div>
    </section>
  );
}

export default function ContainerForecast({ darkMode, vesselId }: { darkMode: boolean; vesselId: VesselId }) {
  const { language } = useI18n();
  if (!isNotebookVessel(vesselId)) return null;
  const forecast = NOTEBOOK_FORECASTS[vesselId];
  const Direction = forecast.quarterChange >= 0 ? ArrowUpRight : ArrowDownRight;
  const text = darkMode ? "#cbd5e1" : "#64748b";
  const grid = darkMode ? "#334155" : "#e8edf4";
  const months = forecast.monthly.map(({ month }) => `${Number(month.slice(5))}월`);
  const monthlyValues = forecast.monthly.map(({ value }) => value / 10_000);
  const currentMonthIndex = forecast.monthly.findIndex(({ month }) => month === "2026-10");
  const intervals = new Map(forecast.predictionIntervals95.map((interval) => [interval.month, interval]));
  const confidenceLower = monthlyValues.map((value, index) => {
    if (index < currentMonthIndex) return null;
    if (index === currentMonthIndex) return value;
    const interval = intervals.get(forecast.monthly[index].month);
    return interval ? interval.lower / 10_000 : null;
  });
  const confidenceBand = monthlyValues.map((_value, index) => {
    if (index < currentMonthIndex) return null;
    if (index === currentMonthIndex) return 0;
    const interval = intervals.get(forecast.monthly[index].month);
    return interval ? (interval.upper - interval.lower) / 10_000 : null;
  });
  const highIndex = monthlyValues.indexOf(Math.max(...monthlyValues));
  const lowIndex = monthlyValues.indexOf(Math.min(...monthlyValues));
  const materialSwing = (monthlyValues[highIndex] - monthlyValues[lowIndex]) / Math.max(monthlyValues[lowIndex], 1) >= 0.25;
  const currentTurningPoint = materialSwing
    ? currentMonthIndex === highIndex ? { name: "예상 고점", color: "#ef4444" }
      : currentMonthIndex === lowIndex ? { name: "예상 저점", color: "#2563eb" }
        : null
    : null;
  const currentPointColor = currentTurningPoint ? {
    type: "linear", x: 0, y: 0, x2: 1, y2: 0,
    colorStops: [
      { offset: 0, color: currentTurningPoint.color },
      { offset: 0.5, color: currentTurningPoint.color },
      { offset: 0.5, color: "#f59e0b" },
      { offset: 1, color: "#f59e0b" },
    ],
  } : "#f59e0b";
  const turningPoints = materialSwing ? [
    { coord: [months[highIndex], monthlyValues[highIndex]], name: "예상 고점", symbol: "circle", symbolSize: 11, itemStyle: { color: "#ef4444", borderColor: "#fff", borderWidth: 2 } },
    { coord: [months[lowIndex], monthlyValues[lowIndex]], name: "예상 저점", symbol: "circle", symbolSize: 11, itemStyle: { color: "#2563eb", borderColor: "#fff", borderWidth: 2 } },
  ].filter((point) => point.coord[0] !== months[currentMonthIndex]) : [];
  const option = {
    animationDuration: 850,
    grid: { left: 70, right: 30, top: 58, bottom: 45 },
    legend: { top: 8, left: "center", itemWidth: 22, itemHeight: 4, itemGap: 18, textStyle: { color: text, fontSize: 10 }, data: ["7~10월 추정", "11~12월 전망", "95% 예측구간"] },
    tooltip: {
      trigger: "axis", confine: true, axisPointer: { type: "line", lineStyle: { color: "#94a3b8", type: "dashed" } },
      backgroundColor: darkMode ? "#0f172a" : "#fff", borderColor: grid,
      textStyle: { color: darkMode ? "#f1f5f9" : "#1e293b" },
      formatter: (params: Array<{ dataIndex: number }>) => {
        const index = params[0]?.dataIndex ?? 0;
        const point = forecast.monthly[index];
        const previous = forecast.monthly[index - 1];
        const change = previous ? (point.value / previous.value - 1) * 100 : undefined;
        const interval = intervals.get(point.month);
        const pointLabels = [
          index === highIndex && materialSwing ? `<b style="color:#ef4444">예상 고점</b>` : "",
          index === lowIndex && materialSwing ? `<b style="color:#2563eb">예상 저점</b>` : "",
          index === currentMonthIndex ? `<b style="color:#f59e0b">현재월 추정</b>` : "",
        ].filter(Boolean).join(" · ");
        const pointLabel = pointLabels ? `${pointLabels}<br/>` : "";
        const status = index === currentMonthIndex ? "현재월 추정" : index > currentMonthIndex ? "잔여 전망" : `${index < 3 ? "3분기" : "4분기"} 전망`;
        return `${pointLabel}<b>${point.month}</b> · ${status}<br/>월별 전망&nbsp;&nbsp;<b>${number(point.value, 1)} ${forecast.unit}</b>${change === undefined ? "" : `<br/>전월 대비&nbsp;&nbsp;<b style="color:${change >= 0 ? "#16a34a" : "#e11d48"}">${change > 0 ? "+" : ""}${change.toFixed(1)}%</b>`}${interval ? `<br/><span style="color:#64748b">95% 범위&nbsp;&nbsp;${number(interval.lower, 1)}–${number(interval.upper, 1)} ${forecast.unit} · n=${interval.calibrationSize}</span>` : ""}`;
      },
    },
    xAxis: {
      type: "category", boundaryGap: false,
      data: months,
      axisLine: { lineStyle: { color: grid } }, axisTick: { show: false },
      axisLabel: { color: text, fontSize: 12, margin: 14 },
    },
    yAxis: {
      type: "value", name: language === "en" ? `×10K ${forecast.unit}` : `만 ${forecast.unit}`,
      nameTextStyle: { color: text, padding: [0, 0, 8, 0] },
      axisLabel: { color: text }, splitLine: { lineStyle: { color: grid, type: "dashed" } },
    },
    series: [
      { name: "예측구간 하한", type: "line", stack: "quarter-confidence", symbol: "none", data: confidenceLower, lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, tooltip: { show: false }, silent: true, z: 1 },
      { name: "95% 예측구간", type: "line", stack: "quarter-confidence", symbol: "none", data: confidenceBand, lineStyle: { color: "#93c5fd", width: 1, type: "dashed", opacity: .65 }, areaStyle: { color: "rgba(59,130,246,.2)" }, tooltip: { show: false }, silent: true, z: 1 },
      {
        name: "7~10월 추정", type: "line", smooth: 0.24, symbol: "none",
        data: monthlyValues.map((value, index) => index <= currentMonthIndex ? value : null),
        lineStyle: { color: darkMode ? "#94a3b8" : "#64748b", width: 2.5 },
        markArea: { silent: true, data: [
          [{ name: "Q3", xAxis: "7월", itemStyle: { color: darkMode ? "rgba(148,163,184,.06)" : "rgba(148,163,184,.055)" } }, { xAxis: "9월" }],
          [{ name: "Q4", xAxis: "10월", itemStyle: { color: darkMode ? "rgba(59,130,246,.1)" : "rgba(59,130,246,.06)" } }, { xAxis: "12월" }],
        ] },
        markPoint: { silent: true, label: { show: false }, data: [
          ...turningPoints,
          { coord: [months[currentMonthIndex], monthlyValues[currentMonthIndex]], name: currentTurningPoint ? `현재월 추정 · ${currentTurningPoint.name}` : "현재월 추정", symbol: "circle", symbolSize: 11, itemStyle: { color: currentPointColor, borderColor: "#fff", borderWidth: 2 } },
        ] },
        markLine: { symbol: "none", silent: true, data: [{ xAxis: "10월", label: { formatter: "현재월", color: text, position: "insideEndTop" }, lineStyle: { color: "#f59e0b", width: 1.2, type: "dashed" } }] },
        z: 4,
      },
      {
        name: "11~12월 전망", type: "line", smooth: 0.24, symbol: "none",
        data: monthlyValues.map((value, index) => index >= currentMonthIndex ? value : null),
        lineStyle: { color: forecast.color, width: 3, type: "dashed" },
        z: 5,
      },
    ],
    media: [{
      query: { maxWidth: 560 },
      option: {
        grid: { left: 48, right: 12, top: 76, bottom: 38 },
        legend: { type: "scroll", top: 4, left: 8, right: 8, itemWidth: 16, itemGap: 10, textStyle: { color: text, fontSize: 9 } },
        xAxis: { axisLabel: { fontSize: 10, margin: 10 } },
        yAxis: { name: "", axisLabel: { fontSize: 9 }, splitNumber: 3 },
      },
    }],
  };

  return (
    <section className="analysis-panel container-forecast-panel rounded-2xl border border-slate-200/85 bg-white p-5 shadow-[0_4px_24px_rgba(21,44,79,0.035)]">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-semibold text-slate-900">분기 수주 전망</h2>
          </div>
          <p className="mt-1 text-xs text-slate-500">{forecast.vesselName} · 2026년 6월 데이터 마감 · 2026년 7~12월 전망</p>
        </div>
        <span className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs font-medium text-slate-600">{forecast.model}</span>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-500">3분기 누적 전망</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{compact(forecast.q3, forecast.unit, language)}</p>
        </div>
        <div className="rounded-xl border border-blue-200 bg-blue-50/50 px-4 py-3">
          <p className="text-xs text-slate-500">4분기 누적 전망</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{compact(forecast.q4, forecast.unit, language)}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-500">분기 변화</p>
          <p className={`mt-1 flex items-center gap-1 text-xl font-semibold ${forecast.quarterChange >= 0 ? "text-emerald-600" : "text-rose-600"}`}>
            {forecast.quarterChange > 0 ? "+" : ""}{forecast.quarterChange.toFixed(1)}% <Direction className="h-4 w-4" />
          </p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-slate-50 px-4 py-3">
          <p className="text-xs text-slate-500">예상 고점</p>
          <p className="mt-1 text-xl font-semibold text-slate-900">{forecast.peakMonth}</p>
          <p className="mt-1 text-[11px] text-slate-500">고점 시차 오차 {forecast.peakTimingError.toFixed(2)}개월</p>
        </div>
      </div>

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[minmax(0,1.65fr)_minmax(270px,.7fr)]">
        <div className="min-h-[260px] rounded-xl border border-slate-100 bg-white p-2" role="img" aria-label={`${forecast.vesselName} 2026년 7월부터 12월까지 월별 수주용량 전망`}>
          <EChartsReact option={option} notMerge style={{ height: "100%", minHeight: 260, width: "100%" }} />
        </div>
        <div className="flex flex-col gap-3">
          <div className="rounded-xl bg-slate-900 p-4 text-white">
            <p className="text-[11px] font-bold tracking-[.14em] text-sky-300">FORECAST SIGNAL</p>
            <p className="mt-2 text-sm font-semibold leading-6">{forecast.signal}</p>
            <p className="mt-2 text-xs leading-5 text-slate-300">{forecast.action}</p>
          </div>
          <div className="rounded-xl border border-slate-200 p-4">
            <p className="text-xs font-semibold text-slate-700">주요 예측 동인 · SHAP 비중</p>
            <div className="mt-3 space-y-2.5">
              {forecast.drivers.map((driver) => (
                <div key={driver.label}>
                  <div className="mb-1 flex justify-between gap-3 text-[11px] text-slate-500"><span>{driver.label}</span><b>{driver.share.toFixed(1)}%</b></div>
                  <div className="h-1.5 overflow-hidden rounded-full bg-slate-100"><div className="h-full rounded-full" style={{ width: `${driver.share}%`, backgroundColor: forecast.color }} /></div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

    </section>
  );
}
