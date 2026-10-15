import { memo, useCallback, useEffect, useMemo, useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import { Activity, Pause, Play } from "lucide-react";
import { NOTEBOOK_FORECASTS, NOTEBOOK_VESSEL_IDS, PORTFOLIO_INTERVAL_95 } from "../../data/notebookForecasts";
import type { ForecastDriver, NotebookForecast, NotebookVesselId } from "../../data/notebookForecasts";
import { useI18n } from "../../i18n";

type ActualPoint = { month: string; value: number };
type MasterDataResponse = { rows: Array<{ period: string; orderCapacity: string | null }> };
type ActualsByVessel = Partial<Record<NotebookVesselId, ActualPoint[]>>;

const NOTEBOOK_START_MONTH = "2026-07";
const PENDING_MONTH = "2026-09";
const CURRENT_MONTH = "2026-10";
const OUTLOOK_START_MONTH = "2026-10";
const FORECAST_START_MONTH = "2026-11";
const FORECAST_MARKER_MONTH = "2026-08";
const FORECAST_END_MONTH = "2026-12";
const MARKET_BRIEF_IMAGES: Record<NotebookVesselId, string> = {
  container: "/images/market-brief/container.jpg",
  tanker: "/images/market-brief/tanker.jpg",
  bulk: "/images/market-brief/bulk.jpg",
  gas: "/images/market-brief/gas.jpg",
  chemical: "/images/market-brief/chemical.jpg",
};
const MARKET_BRIEF_IMAGE_POSITIONS: Record<NotebookVesselId, string> = {
  container: "center 28%",
  tanker: "center 56%",
  bulk: "center 60%",
  gas: "center 50%",
  chemical: "center 55%",
};
const notebookPoints = (forecast: NotebookForecast) => forecast.monthly.filter((point) => point.month >= NOTEBOOK_START_MONTH && point.month <= FORECAST_END_MONTH);
const outlookPoints = (forecast: NotebookForecast) => forecast.monthly.filter((point) => point.month >= OUTLOOK_START_MONTH && point.month <= FORECAST_END_MONTH);
const futurePoints = (forecast: NotebookForecast) => forecast.monthly.filter((point) => point.month >= FORECAST_START_MONTH && point.month <= FORECAST_END_MONTH);
const currentPoint = (forecast: NotebookForecast) => forecast.monthly.find((point) => point.month === CURRENT_MONTH);
type ChartPoint = { month: string; value: number };
type TurningPointMarker = { name: string; labels: string[]; coord: [string, number]; value: number; symbol: "circle"; symbolSize: number; itemStyle: { color: string; borderColor: string; borderWidth: number } };
const MAJOR_REVERSAL_THRESHOLD = 0.35;
const MAJOR_PROMINENCE_THRESHOLD = 0.2;
const turningPointMarkers = (points: readonly ChartPoint[]) => {
  const high = points.reduce((best, point) => point.value > best.value ? point : best);
  const low = points.reduce((best, point) => point.value < best.value ? point : best);
  const valueRange = Math.max(high.value - low.value, 1);
  return points.flatMap((point, index) => {
    const previous = points[index - 1];
    const next = points[index + 1];
    if (!previous || !next) return [];
    const isLow = point.value < previous.value && point.value < next.value;
    const isHigh = point.value > previous.value && point.value > next.value;
    if (!isLow && !isHigh) return [];
    const adjacentProminence = Math.min(Math.abs(point.value - previous.value), Math.abs(next.value - point.value));
    const previousChange = Math.abs(point.value - previous.value) / Math.max(previous.value, 1);
    const nextChange = Math.abs(next.value - point.value) / Math.max(point.value, 1);
    const isMajorReversal = previousChange >= MAJOR_REVERSAL_THRESHOLD
      && nextChange >= MAJOR_REVERSAL_THRESHOLD
      && adjacentProminence / valueRange >= MAJOR_PROMINENCE_THRESHOLD;
    if (!isMajorReversal) return [];
    const labels: string[] = [];
    if (point === high) labels.push("예상 고점");
    if (point === low) labels.push("예상 저점");
    if (isLow) labels.push("상승 전환");
    if (isHigh) labels.push("하락 전환");
    if (!labels.length) return [];
    return [{
      name: labels.join(" · "),
      labels,
      coord: [point.month, point.value],
      value: point.value,
      symbol: "circle" as const,
      symbolSize: point === high || point === low ? 11 : 8,
      itemStyle: { color: point === high ? "#ef4444" : point === low ? "#2563eb" : "#7c3aed", borderColor: "#fff", borderWidth: 2 },
    }];
  }) as TurningPointMarker[];
};
const turningPointTooltip = (markers: readonly TurningPointMarker[], month: string) => {
  const marker = markers.find((item) => item.coord[0] === month);
  return marker?.labels.map((label) => `<b style="color:${label === "예상 고점" ? "#f87171" : label === "예상 저점" ? "#60a5fa" : "#c4b5fd"}">${label}</b>`) ?? [];
};
const periodChange = (forecast: NotebookForecast) => {
  const points = outlookPoints(forecast);
  return (points.at(-1)!.value / Math.max(points[0].value, 1) - 1) * 100;
};
const periodPeak = (forecast: NotebookForecast) => outlookPoints(forecast).reduce((best, point) => point.value > best.value ? point : best);

const formatCompact = (value: number) => value >= 1_000_000
  ? `${(value / 1_000_000).toFixed(1)}M`
  : value >= 1_000 ? `${(value / 1_000).toFixed(0)}K` : value.toFixed(0);
const signed = (value: number) => `${value > 0 ? "+" : ""}${value.toFixed(1)}%`;
const formatCapacity = (value: number, unit: string) => `${formatCompact(value)} ${unit}`;
const COMMON_DRIVER_GROUPS = [
  { label: "시장 가격·투자 여건", matches: ["가격", "환율", "신조선가", "리그"] },
  { label: "지정학 리스크", matches: ["위협", "GPR"] },
  { label: "운임·물류 흐름", matches: ["운임", "수에즈"] },
  { label: "교역·수요 흐름", matches: ["TPU", "수출", "수입", "공급망"] },
  { label: "과거 수주 흐름", matches: ["수주용량"] },
] as const;
const COMMON_DRIVERS: readonly ForecastDriver[] = COMMON_DRIVER_GROUPS.map((group) => ({
  label: group.label,
  share: NOTEBOOK_VESSEL_IDS.reduce((sum, id) => sum + NOTEBOOK_FORECASTS[id].drivers
    .filter((driver) => group.matches.some((keyword) => driver.label.includes(keyword)))
    .reduce((subtotal, driver) => subtotal + driver.share, 0), 0) / NOTEBOOK_VESSEL_IDS.length,
})).filter((driver) => driver.share > 0).sort((a, b) => b.share - a.share);
const quarterBoundaryLines = (months: readonly string[], darkMode = false) => months.flatMap((month, index) => {
  const monthNumber = Number(month.slice(5, 7));
  if (index === 0 || ![1, 4, 7, 10].includes(monthNumber)) return [];
  const quarter = Math.floor((monthNumber - 1) / 3) + 1;
  return [{
    xAxis: month,
    label: { show: true, formatter: `${month.slice(0, 4)} Q${quarter}`, position: "insideEndTop", color: darkMode ? "#94a3b8" : "#8796a9", fontSize: 9, padding: [0, 0, 4, 0] },
    lineStyle: { color: darkMode ? "#475569" : "#cbd5e1", width: 1, type: "dashed", opacity: 0.9 },
  }];
});
const confidenceTooltip = (lower: number, upper: number, unit = "", calibrationSize?: number, title = "95% 예측구간", detail?: string) => {
  const format = (value: number) => value.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
  return `<div style="margin-top:9px;padding:9px 10px;border:1px solid rgba(147,197,253,.55);border-radius:8px;background:rgba(59,130,246,.22)">
    <div style="margin-bottom:2px;color:#dbeafe;font-size:11px;font-weight:700;letter-spacing:.02em">${title}</div>
    <div style="margin-bottom:7px;color:#93c5fd;font-size:9px">${detail ?? `순차 검증 오차${calibrationSize ? ` · n=${calibrationSize}` : " · 선종별 보정"}`}</div>
    <div style="display:flex;align-items:center;gap:9px;color:#fff;white-space:nowrap">
      <span><span style="display:block;margin-bottom:2px;color:#93c5fd;font-size:9px;font-weight:700">하한</span><b style="font-size:13px">${format(lower)}</b></span>
      <span style="color:#93c5fd;font-size:13px">—</span>
      <span><span style="display:block;margin-bottom:2px;color:#93c5fd;font-size:9px;font-weight:700">상한</span><b style="font-size:13px">${format(upper)}${unit ? ` ${unit}` : ""}</b></span>
    </div>
  </div>`;
};

const ForecastTimeseries = memo(function ForecastTimeseries({ forecast, actuals, loading, darkMode }: { forecast: NotebookForecast; actuals: ActualPoint[]; loading: boolean; darkMode: boolean }) {
  const current = currentPoint(forecast);
  const future = futurePoints(forecast);
  const projected = [...(current ? [current] : []), ...future];
  const pendingMonths = actuals.some((item) => item.month === PENDING_MONTH) ? [] : [PENDING_MONTH];
  const historyPadding = [...actuals.map(() => null), ...pendingMonths.map(() => null)];
  const months = [...actuals.map((item) => item.month), ...pendingMonths, ...projected.map((item) => item.month)];
  const lastActual = actuals.at(-1)?.value ?? null;
  const actualData = [...actuals.map((item) => item.value), ...pendingMonths.map(() => null), ...projected.map(() => null)];
  const currentEstimateData = current
    ? [...actuals.slice(0, -1).map(() => null), lastActual, ...pendingMonths.map(() => null), current.value, ...future.map(() => null)]
    : months.map(() => null);
  const forecastData = [...historyPadding, ...(current ? [current.value] : []), ...future.map((item) => item.value)];
  const turningMarkers = turningPointMarkers([...actuals, ...projected]);
  const forecastStartPoint = [...actuals, ...projected].find((point) => point.month === FORECAST_MARKER_MONTH);
  const intervalLabel = "95% 예측구간";
  const intervals = new Map(forecast.predictionIntervals95.map((interval) => [interval.month, interval]));
  const confidenceAnchor = [...actuals.map(() => null), ...pendingMonths.map(() => null)];
  const confidenceLower = [
    ...confidenceAnchor,
    ...(current ? [current.value] : []),
    ...future.map((item) => intervals.get(item.month)?.lower ?? null),
  ];
  const confidenceBand = [
    ...confidenceAnchor,
    ...(current ? [0] : []),
    ...future.map((item) => {
      const interval = intervals.get(item.month);
      return interval ? interval.upper - interval.lower : null;
    }),
  ];
  const chartTheme = darkMode
    ? { text: "#cbd5e1", muted: "#94a3b8", axis: "#475569", grid: "#334155", actual: "#93c5fd", pointBorder: "#1e293b" }
    : { text: "#64748b", muted: "#718096", axis: "#dbe4ef", grid: "#e7edf5", actual: "#102e58", pointBorder: "#fff" };
  const option = {
    animationDuration: 650,
    grid: { left: 68, right: 28, top: 52, bottom: 42 },
    legend: { top: 5, left: 55, itemWidth: 22, itemHeight: 4, itemGap: 18, textStyle: { color: chartTheme.text, fontSize: 10 }, data: ["실적", "현재월 추정", "11~12월 전망", intervalLabel] },
    tooltip: {
      trigger: "axis", confine: true, axisPointer: { type: "line", lineStyle: { color: "#8aa4c1", type: "dashed" } }, backgroundColor: "#102747", borderWidth: 0, padding: [12, 14], textStyle: { color: "#fff", fontSize: 12 }, extraCssText: "box-shadow:0 12px 30px rgba(15,34,58,.24);border-radius:10px;",
      formatter: (params: Array<{ axisValue: string; seriesName: string; data: number | null; color: string }>) => {
        const month = params[0]?.axisValue ?? "";
        const lines = [...turningPointTooltip(turningMarkers, month), `<b>${month}</b>`];
        const actual = params.find((item) => item.seriesName === "실적" && Number.isFinite(Number(item.data)));
        if (actual) {
          const index = actuals.findIndex((item) => item.month === month);
          const previous = index > 0 ? actuals[index - 1].value : undefined;
          const change = previous ? (Number(actual.data) - previous) / previous * 100 : undefined;
          lines.push(`실적&nbsp;&nbsp;<b>${Number(actual.data).toLocaleString("ko-KR", { maximumFractionDigits: 1 })} ${forecast.unit}</b>${change === undefined ? "" : ` <span style="color:${change >= 0 ? "#86efac" : "#fda4af"}">(${signed(change)})</span>`}`);
        }
        const predicted = projected.find((item) => item.month === month);
        if (predicted) {
          const index = projected.indexOf(predicted);
          const previous = index > 0 ? projected[index - 1].value : undefined;
          const change = previous ? (predicted.value - previous) / previous * 100 : undefined;
          lines.push(`${month === CURRENT_MONTH ? "현재월 추정" : "잔여 전망"}&nbsp;&nbsp;<b>${predicted.value.toLocaleString("ko-KR", { maximumFractionDigits: 1 })} ${forecast.unit}</b>${change === undefined ? "" : ` <span style="color:${change >= 0 ? "#86efac" : "#fda4af"}">(${signed(change)})</span>`}`);
          const interval = intervals.get(month);
          if (interval && month !== CURRENT_MONTH) lines.push(confidenceTooltip(interval.lower, interval.upper, forecast.unit, interval.calibrationSize, intervalLabel,
            `인접 3개월 Validation 원잔차 · n=${interval.calibrationSize}`));
        }
        if (month === PENDING_MONTH) lines.push("수주 실적 집계 대기");
        return lines.join("<br/>");
      },
    },
    xAxis: { type: "category", data: months, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: chartTheme.axis } }, axisLabel: { color: chartTheme.muted, fontSize: 10, margin: 12, interval: 0, hideOverlap: false, formatter: (value: string, index: number) => index % 3 === 0 ? value.replace("-", ".") : "" } },
    yAxis: { type: "value", scale: true, max: ({ max, min }: { max: number; min: number }) => max + Math.max((max - min) * 0.2, Math.abs(max) * 0.08), name: `수주용량 (${forecast.unit})`, nameGap: 15, nameTextStyle: { color: chartTheme.text, align: "right", fontSize: 10 }, axisLabel: { color: chartTheme.muted, fontSize: 10, formatter: formatCompact }, splitNumber: 4, splitLine: { lineStyle: { color: chartTheme.grid, type: "dashed" } } },
    series: [
      { name: "실적", type: "line", symbol: "none", smooth: 0.18, data: actualData, lineStyle: { color: chartTheme.actual, width: 2.4 }, emphasis: { focus: "series" }, z: 4 },
      { name: "현재월 추정", type: "line", symbol: "none", connectNulls: true, data: currentEstimateData, lineStyle: { color: "#f59e0b", width: 2.4 }, markPoint: { silent: true, label: { show: false }, data: forecastStartPoint ? [{ coord: [forecastStartPoint.month, forecastStartPoint.value], symbol: "circle", symbolSize: 9, itemStyle: { color: "#f59e0b", borderColor: chartTheme.pointBorder, borderWidth: 2 } }] : [] }, z: 6 },
      { name: "신뢰 범위 하한", type: "line", stack: "confidence", symbol: "none", smooth: 0.2, connectNulls: true, data: confidenceLower, lineStyle: { color: "#93c5fd", width: 1, type: "dashed", opacity: .8 }, areaStyle: { opacity: 0 }, tooltip: { show: false }, silent: true, z: 1 },
      { name: intervalLabel, type: "line", stack: "confidence", symbol: "none", smooth: 0.2, connectNulls: true, data: confidenceBand, lineStyle: { color: "#93c5fd", width: 1, type: "dashed", opacity: .8 }, areaStyle: { color: "rgba(59,130,246,.23)" }, tooltip: { show: false }, silent: true, z: 1 },
      { name: "11~12월 전망", type: "line", symbol: "none", smooth: 0.2, connectNulls: false, data: forecastData, lineStyle: { color: "#2476ed", width: 2.6, type: "dashed" }, emphasis: { focus: "series" }, markArea: { silent: true, itemStyle: { color: "rgba(59,130,246,.035)" }, data: [[{ xAxis: FORECAST_MARKER_MONTH }, { xAxis: FORECAST_END_MONTH }]] }, markPoint: { silent: true, label: { show: false }, data: turningMarkers }, z: 5 },
      { name: "기간 구분선", type: "line", animation: false, symbol: "none", data: months.map(() => null), lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true, markLine: { animation: false, symbol: "none", silent: true, data: [...quarterBoundaryLines(months, darkMode), { xAxis: FORECAST_MARKER_MONTH, label: { show: true, formatter: "미래 전망 시작", color: "#fff", backgroundColor: "#2878ed", borderRadius: 4, padding: [4, 7] }, lineStyle: { color: "#2878ed", type: "dashed" } }] }, z: 7 },
    ],
    media: [{
      query: { maxWidth: 560 },
      option: {
        grid: { left: 50, right: 12, top: 76, bottom: 38 },
        legend: { type: "scroll", top: 4, left: 8, right: 8, itemWidth: 16, itemGap: 10, textStyle: { color: chartTheme.text, fontSize: 9 } },
        xAxis: { axisLabel: { fontSize: 9, margin: 10 } },
        yAxis: { name: "", axisLabel: { fontSize: 9 }, splitNumber: 3 },
      },
    }],
  };
  return <div className="overview-chart-body">{loading ? <div className="overview-chart-placeholder">수주 데이터를 불러오는 중입니다.</div> : actuals.length ? <EChartsReact option={option} notMerge lazyUpdate /> : <div className="overview-chart-placeholder">연결된 수주 데이터가 없습니다.</div>}</div>;
});

const PortfolioForecastTimeseries = memo(function PortfolioForecastTimeseries({ forecasts, actualsByVessel, loading }: { forecasts: NotebookForecast[]; actualsByVessel: ActualsByVessel; loading: boolean }) {
  const baselines = new Map<NotebookVesselId, number>();
  forecasts.forEach((forecast) => {
    const recent = (actualsByVessel[forecast.vesselId] ?? []).slice(-12);
    const baseline = recent.reduce((sum, point) => sum + point.value, 0) / recent.length;
    if (Number.isFinite(baseline) && baseline > 0) baselines.set(forecast.vesselId, baseline);
  });
  const actualMonths = [...new Set(forecasts.flatMap((forecast) => (actualsByVessel[forecast.vesselId] ?? []).map((point) => point.month)))].sort();
  const actualIndexes = actualMonths.flatMap((month) => {
    const values = forecasts.flatMap((forecast) => {
      const baseline = baselines.get(forecast.vesselId);
      const point = actualsByVessel[forecast.vesselId]?.find((item) => item.month === month);
      return baseline && point ? [point.value / baseline * 100] : [];
    });
    return values.length === forecasts.length ? [{ month, value: values.reduce((sum, value) => sum + value, 0) / values.length }] : [];
  });
  const buildProjectedIndex = (month: string) => {
    const normalized = forecasts.flatMap((forecast) => {
      const baseline = baselines.get(forecast.vesselId);
      if (!baseline) return [];
      const point = forecast.monthly.find((item) => item.month === month);
      return point ? [point.value / baseline * 100] : [];
    });
    const value = normalized.reduce((sum, item) => sum + item, 0) / normalized.length;
    return {
      month,
      value,
      lower: Math.max(0, value - PORTFOLIO_INTERVAL_95.radius),
      upper: value + PORTFOLIO_INTERVAL_95.radius,
    };
  };
  const projectedMonths = [CURRENT_MONTH, ...futurePoints(forecasts[0]).map((point) => point.month)];
  const projectedIndexes = projectedMonths.map(buildProjectedIndex);
  const currentIndex = projectedIndexes.find((point) => point.month === CURRENT_MONTH);
  const forecastIndexes = projectedIndexes.filter((point) => point.month >= FORECAST_START_MONTH);
  const pendingMonths = actualIndexes.some((point) => point.month === PENDING_MONTH) ? [] : [PENDING_MONTH];
  const historyPadding = [...actualIndexes.map(() => null), ...pendingMonths.map(() => null)];
  const months = [...actualIndexes.map((point) => point.month), ...pendingMonths, ...projectedIndexes.map((point) => point.month)];
  const lastActual = actualIndexes.at(-1)?.value ?? null;
  const actualData = [...actualIndexes.map((point) => point.value), ...pendingMonths.map(() => null), ...projectedIndexes.map(() => null)];
  const currentEstimateData = currentIndex
    ? [...actualIndexes.slice(0, -1).map(() => null), lastActual, ...pendingMonths.map(() => null), currentIndex.value, ...forecastIndexes.map(() => null)]
    : months.map(() => null);
  const forecastData = [...historyPadding, ...(currentIndex ? [currentIndex.value] : []), ...forecastIndexes.map((point) => point.value)];
  const turningMarkers = turningPointMarkers([...actualIndexes, ...projectedIndexes]);
  const forecastStartPoint = [...actualIndexes, ...projectedIndexes].find((point) => point.month === FORECAST_MARKER_MONTH);
  const confidenceLower = [...historyPadding, ...(currentIndex ? [currentIndex.value] : []), ...forecastIndexes.map((point) => point.lower)];
  const confidenceBand = [...historyPadding, ...(currentIndex ? [0] : []), ...forecastIndexes.map((point) => point.upper - point.lower)];
  const option = {
    animationDuration: 650,
    grid: { left: 68, right: 28, top: 52, bottom: 42 },
    legend: { top: 5, left: 55, itemWidth: 22, itemHeight: 4, itemGap: 18, textStyle: { color: "#64748b", fontSize: 10 }, data: ["종합 실적지수", "종합 현재월 추정", "종합 11~12월 전망", "95% 예측구간"] },
    tooltip: {
      trigger: "axis", confine: true, axisPointer: { type: "line", lineStyle: { color: "#8aa4c1", type: "dashed" } }, backgroundColor: "#102747", borderWidth: 0, padding: [12, 14], textStyle: { color: "#fff", fontSize: 12 }, extraCssText: "box-shadow:0 12px 30px rgba(15,34,58,.24);border-radius:10px;",
      formatter: (params: Array<{ axisValue: string }>) => {
        const month = params[0]?.axisValue ?? "";
        const actual = actualIndexes.find((point) => point.month === month);
        const predicted = projectedIndexes.find((point) => point.month === month);
        const lines = [...turningPointTooltip(turningMarkers, month), `<b>${month}</b>`];
        if (actual) lines.push(`종합 실적지수&nbsp;&nbsp;<b>${actual.value.toFixed(1)}</b>`);
        if (predicted) lines.push(`${month === CURRENT_MONTH ? "종합 현재월 추정" : "종합 잔여 전망"}&nbsp;&nbsp;<b>${predicted.value.toFixed(1)}</b>${month === CURRENT_MONTH ? "" : confidenceTooltip(predicted.lower, predicted.upper, "", PORTFOLIO_INTERVAL_95.calibrationSize, "95% 예측구간")}`);
        if (month === PENDING_MONTH) lines.push("수주 실적 집계 대기");
        return lines.join("<br/>");
      },
    },
    xAxis: { type: "category", data: months, boundaryGap: false, axisTick: { show: false }, axisLine: { lineStyle: { color: "#dbe4ef" } }, axisLabel: { color: "#718096", fontSize: 10, margin: 12, interval: 0, hideOverlap: false, formatter: (value: string, index: number) => index % 3 === 0 ? value.replace("-", ".") : "" } },
    yAxis: { type: "value", scale: true, max: 210, interval: 30, name: "종합 수주지수", nameGap: 15, nameTextStyle: { color: "#64748b", align: "right", fontSize: 10 }, axisLabel: { color: "#718096", fontSize: 10, formatter: (value: number) => value.toFixed(0) }, splitNumber: 4, splitLine: { lineStyle: { color: "#e7edf5", type: "dashed" } } },
    series: [
      { name: "종합 실적지수", type: "line", symbol: "none", smooth: 0.18, data: actualData, lineStyle: { color: "#102e58", width: 2.4 }, emphasis: { focus: "series" }, z: 4 },
      { name: "종합 현재월 추정", type: "line", symbol: "none", connectNulls: true, data: currentEstimateData, lineStyle: { color: "#f59e0b", width: 2.4 }, markPoint: { silent: true, label: { show: false }, data: forecastStartPoint ? [{ coord: [forecastStartPoint.month, forecastStartPoint.value], symbol: "circle", symbolSize: 9, itemStyle: { color: "#f59e0b", borderColor: "#fff", borderWidth: 2 } }] : [] }, z: 6 },
      { name: "신뢰 범위 하한", type: "line", stack: "portfolio-confidence", symbol: "none", smooth: 0.2, data: confidenceLower, lineStyle: { color: "#93c5fd", width: 1, type: "dashed", opacity: .8 }, areaStyle: { opacity: 0 }, tooltip: { show: false }, silent: true, z: 1 },
      { name: "95% 예측구간", type: "line", stack: "portfolio-confidence", symbol: "none", smooth: 0.2, data: confidenceBand, lineStyle: { color: "#93c5fd", width: 1, type: "dashed", opacity: .8 }, areaStyle: { color: "rgba(59,130,246,.23)" }, tooltip: { show: false }, silent: true, z: 1 },
      { name: "종합 11~12월 전망", type: "line", symbol: "none", smooth: 0.2, data: forecastData, lineStyle: { color: "#2476ed", width: 2.6, type: "dashed" }, markArea: { silent: true, itemStyle: { color: "rgba(59,130,246,.035)" }, data: [[{ xAxis: FORECAST_MARKER_MONTH }, { xAxis: FORECAST_END_MONTH }]] }, markPoint: { silent: true, label: { show: false }, data: turningMarkers }, z: 5 },
      { name: "기간 구분선", type: "line", animation: false, symbol: "none", data: months.map(() => null), lineStyle: { opacity: 0 }, tooltip: { show: false }, silent: true, markLine: { animation: false, symbol: "none", silent: true, data: [{ yAxis: 100, label: { show: false }, lineStyle: { color: "#94a3b8", type: "dotted" } }, ...quarterBoundaryLines(months), { xAxis: FORECAST_MARKER_MONTH, label: { show: true, formatter: "미래 전망 시작", color: "#fff", backgroundColor: "#2878ed", borderRadius: 4, padding: [4, 7] }, lineStyle: { color: "#2878ed", type: "dashed" } }] }, z: 7 },
    ],
    media: [{
      query: { maxWidth: 560 },
      option: {
        grid: { left: 46, right: 12, top: 76, bottom: 38 },
        legend: { type: "scroll", top: 4, left: 8, right: 8, itemWidth: 16, itemGap: 10, textStyle: { color: "#64748b", fontSize: 9 } },
        xAxis: { axisLabel: { fontSize: 9, margin: 10 } },
        yAxis: { name: "", axisLabel: { fontSize: 9 }, splitNumber: 3 },
      },
    }],
  };
  return <div className="overview-chart-body">{loading ? <div className="overview-chart-placeholder">전체 선종 수주 데이터를 불러오는 중입니다.</div> : actualIndexes.length && forecastIndexes.length ? <EChartsReact option={option} notMerge lazyUpdate /> : <div className="overview-chart-placeholder">종합지수를 계산할 수주 데이터가 부족합니다.</div>}</div>;
});

const ForecastHeatmap = memo(function ForecastHeatmap({ forecasts, onSelect }: { forecasts: NotebookForecast[]; onSelect?: (id: NotebookVesselId) => void }) {
  const months = notebookPoints(forecasts[0]).map((item) => Number(item.month.slice(5)) + "월");
  const palette = ["#e7f0fb", "#c9dff5", "#91bee9", "#4c94db", "#1769bf"];
  const values: Array<{ value: [number, number, number, number]; itemStyle: { color: string }; label: { color: string; formatter?: string } }> = forecasts.flatMap((forecast, vesselIndex) => {
    const points = notebookPoints(forecast);
    const rowValues = points.map((point) => point.value);
    const minimum = Math.min(...rowValues);
    const maximum = Math.max(...rowValues);
    return points.map((point, monthIndex) => {
      const ratio = maximum === minimum ? 0.5 : (point.value - minimum) / (maximum - minimum);
      const colorIndex = Math.min(palette.length - 1, Math.floor(ratio * palette.length));
      return { value: [monthIndex, vesselIndex, ratio, point.value], itemStyle: { color: palette[colorIndex] }, label: { color: colorIndex >= 3 ? "#fff" : "#24415f" } };
    });
  });
  const option = {
    animationDuration: 450,
    grid: { left: forecasts.length > 1 ? 88 : 68, right: 8, top: 27, bottom: 8 },
    tooltip: { backgroundColor: "#102747", borderWidth: 0, textStyle: { color: "#fff" }, formatter: (params: { value: [number, number, number, number] }) => { const item = forecasts[params.value[1]]; return `${item.vesselName} · ${months[params.value[0]]}<br/>예측 수주용량 <b>${params.value[3].toLocaleString("ko-KR", { maximumFractionDigits: 1 })} ${item.unit}</b>`; } },
    xAxis: { type: "category", position: "top", data: months, axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#52637a", fontSize: 12, fontWeight: 700 } },
    yAxis: { type: "category", inverse: true, data: forecasts.map((item) => item.vesselName), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: "#31465f", fontSize: 12, fontWeight: 700 } },
    visualMap: { show: false, min: 0, max: 1, dimension: 2, inRange: { color: palette } },
    series: [{ type: "heatmap", data: values, label: { show: true, fontSize: 11, fontWeight: 750, formatter: (params: { value: [number, number, number, number] }) => formatCompact(params.value[3]) }, itemStyle: { borderColor: "#fff", borderWidth: 4, borderRadius: 4 }, emphasis: { itemStyle: { shadowBlur: 8, shadowColor: "rgba(15,38,70,.18)" } } }],
    media: [{
      query: { maxWidth: 560 },
      option: {
        grid: { left: forecasts.length > 1 ? 62 : 50, right: 4, top: 25, bottom: 4 },
        xAxis: { axisLabel: { fontSize: 10 } },
        yAxis: { axisLabel: { fontSize: 10 } },
        series: [{ label: { fontSize: 9 }, itemStyle: { borderWidth: 2 } }],
      },
    }],
  };
  return <div className="overview-heatmap-body"><EChartsReact option={option} notMerge lazyUpdate onEvents={{ click: (params: { value?: [number, number, number, number] }) => { const item = params.value ? forecasts[params.value[1]] : undefined; if (item && onSelect) onSelect(item.vesselId); } }} /><div className="overview-heatmap-legend"><span>선종별 최소</span><i /><b /><span>선종별 최대</span></div></div>;
});

function DriverBars({ source, limit = 5 }: { source: readonly ForecastDriver[]; limit?: number }) {
  const drivers = source.slice(0, limit);
  return <div className="driver-list">{drivers.map((driver, index) => <div className="driver-row" key={driver.label}>
    <span>{driver.label}</span><i><b style={{ width: `${Math.max(18, driver.share / drivers[0].share * 100)}%`, background: index === 0 ? "#176ed1" : "#4b91e8" }} /></i><strong>{driver.share.toFixed(2)}%</strong>
  </div>)}</div>;
}

export default function DashboardOverview({ vesselId, darkMode }: { vesselId?: NotebookVesselId; darkMode: boolean }) {
  const { language, t } = useI18n();
  const portfolio = vesselId === undefined;
  const [selectedId, setSelectedId] = useState<NotebookVesselId>(vesselId ?? "tanker");
  const [selectedDriverId, setSelectedDriverId] = useState<NotebookVesselId | "common">(vesselId ?? "tanker");
  const [chartId, setChartId] = useState<NotebookVesselId | "aggregate">(vesselId ?? "aggregate");
  const [actualsByVessel, setActualsByVessel] = useState<ActualsByVessel>({});
  const [activeBrief, setActiveBrief] = useState(0);
  const [isBriefPlaying, setIsBriefPlaying] = useState(true);
  const forecast = NOTEBOOK_FORECASTS[selectedId];
  const forecasts = useMemo(() => NOTEBOOK_VESSEL_IDS.map((id) => NOTEBOOK_FORECASTS[id]), []);
  const selectHeatmapVessel = useCallback((id: NotebookVesselId) => {
    setSelectedId(id);
    setSelectedDriverId(id);
    setChartId(id);
  }, []);
  const chartVesselId = chartId === "aggregate" ? undefined : chartId;
  const chartForecast = chartVesselId ? NOTEBOOK_FORECASTS[chartVesselId] : undefined;
  const actuals = chartVesselId ? actualsByVessel[chartVesselId] ?? [] : [];
  const loading = portfolio
    ? NOTEBOOK_VESSEL_IDS.some((id) => actualsByVessel[id] === undefined)
    : actualsByVessel[selectedId] === undefined;
  const strongestChange = forecasts.reduce((strongest, item) => Math.abs(periodChange(item)) > Math.abs(periodChange(strongest)) ? item : strongest);
  const strongestMomentum = forecasts.reduce((best, item) => periodChange(item) > periodChange(best) ? item : best);
  const weakestMomentum = forecasts.reduce((weakest, item) => periodChange(item) < periodChange(weakest) ? item : weakest);
  const risingVesselCount = forecasts.filter((item) => item.quarterChange > 0).length;
  const fallingVesselCount = forecasts.filter((item) => item.quarterChange < 0).length;
  const peakMonthCounts = forecasts.reduce<Record<string, number>>((counts, item) => {
    const month = periodPeak(item).month.slice(5);
    counts[month] = (counts[month] ?? 0) + 1;
    return counts;
  }, {});
  const peakConcentration = Math.max(...Object.values(peakMonthCounts));
  const peakConcentrationMonths = Object.entries(peakMonthCounts)
    .filter(([, count]) => count === peakConcentration)
    .map(([month]) => `${Number(month)}월`);
  const peakConcentrationLabel = peakConcentrationMonths.join("·");
  const peakConcentratedVesselCount = peakConcentration * peakConcentrationMonths.length;
  const q4Points = outlookPoints(forecast);
  const q4Total = forecast.q4;
  const q4MonthlyAverage = q4Total / Math.max(q4Points.length, 1);
  const forecastHigh = periodPeak(forecast);
  const forecastLow = q4Points.reduce((lowest, item) => item.value < lowest.value ? item : lowest);
  const forecastStart = q4Points[0];
  const forecastEnd = q4Points.at(-1) ?? forecastStart;
  const forecastEndChange = (forecastEnd.value / Math.max(forecastStart.value, 1) - 1) * 100;
  const q4Intervals = forecast.predictionIntervals95.filter((interval) => interval.month >= "2026-10");
  const possibleLow = Math.min(...q4Intervals.map((interval) => interval.lower));
  const possibleHigh = Math.max(...q4Intervals.map((interval) => interval.upper));
  const koreanMarketBriefs = portfolio ? [
    {
      headline: <>4분기 월간 변화가 가장 큰 선종은 <em>{strongestChange.vesselName} {signed(periodChange(strongestChange))}</em>입니다.</>,
      detail: <>연말 계획에서는 <strong>{periodPeak(strongestChange).month.slice(5)}월 고점 이후 흐름</strong>을 우선 확인하세요.</>,
    },
    {
      headline: <>4분기 예상 고점은 선종별로 <em>10~12월에 분산</em>됩니다.</>,
      detail: <><strong>{forecasts.map((item) => `${item.vesselName} ${periodPeak(item).month.slice(5)}월`).join(" · ")}</strong> 순으로 수요 집중 시점이 다릅니다.</>,
    },
    {
      headline: <>선종별 예상 저점도 서로 달라 <em>대응 시점을 나눠야 합니다.</em></>,
      detail: <><strong>{forecasts.map((item) => `${item.vesselName} ${outlookPoints(item).reduce((low, point) => point.value < low.value ? point : low).month.slice(5)}월`).join(" · ")}</strong></>,
    },
    {
      headline: <>연말까지 가장 강한 흐름은 <em>{strongestMomentum.vesselName}</em>입니다.</>,
      detail: <>10월 대비 12월 전망이 <strong>{signed(periodChange(strongestMomentum))}</strong>로, 영업 기회와 생산 여력을 함께 점검할 시점입니다.</>,
    },
    {
      headline: <>가장 보수적으로 계획할 선종은 <em>{weakestMomentum.vesselName}</em>입니다.</>,
      detail: <>10월 대비 12월 전망이 <strong>{signed(periodChange(weakestMomentum))}</strong>로, 생산·조달 계획에는 하향 시나리오가 필요합니다.</>,
    },
  ] : [
    {
      headline: <>{forecast.vesselName}의 10월 대비 12월 전망은 <em>{signed(forecastEndChange)}</em>입니다.</>,
      detail: <>4분기 월간 흐름은 <strong>{forecastEndChange >= 0 ? "상승" : "하락"}</strong>이며, 고점은 <strong>{forecastHigh.month.slice(5)}월</strong>로 예상됩니다.</>,
    },
    {
      headline: <>{forecast.vesselName}의 4분기 예상 고점은 <em>{forecastHigh.month.slice(5)}월</em>입니다.</>,
      detail: <>월간 수주는 최대 <strong>{formatCapacity(forecastHigh.value, forecast.unit)}</strong>로 전망됩니다.</>,
    },
    {
      headline: <>{forecast.vesselName}의 예상 저점은 <em>{forecastLow.month.slice(5)}월</em>입니다.</>,
      detail: <>월간 수주는 최저 <strong>{formatCapacity(forecastLow.value, forecast.unit)}</strong>로 전망됩니다.</>,
    },
    {
      headline: <>{forecast.vesselName}의 4분기 누적 전망은 <em>{formatCapacity(q4Total, forecast.unit)}</em>입니다.</>,
      detail: <>월평균 <strong>{formatCapacity(q4MonthlyAverage, forecast.unit)}</strong> 수준으로 영업·생산 계획을 점검하세요.</>,
    },
    {
      headline: <>{forecastEndChange >= 0 ? "연말로 갈수록 수주 기회 확대가 예상됩니다." : "연말로 갈수록 수주 속도 조정이 예상됩니다."}</>,
      detail: <>{forecastEndChange >= 0 ? <><strong>고객 접점과 생산 여력</strong>을 선제적으로 확보하세요.</> : <><strong>수주·조달 일정을 보수적으로</strong> 운영하고 반등 시점을 확인하세요.</>}</>,
    },
    {
      headline: <>시장 변화에 따라 월간 수주는 <em>{formatCapacity(possibleLow, forecast.unit)}~{formatCapacity(possibleHigh, forecast.unit)}</em> 범위까지 움직일 수 있습니다.</>,
      detail: <>계약·생산 일정은 <strong>기본 전망과 상·하향 시나리오</strong>를 함께 준비하세요.</>,
    },
  ];
  const englishMarketBriefs = portfolio ? [
    {
      headline: <>The largest Q4 monthly change is <em>{t(strongestChange.vesselName)} {signed(periodChange(strongestChange))}</em>.</>,
      detail: <>Prioritize the path after its <strong>{t(`${periodPeak(strongestChange).month.slice(5)}월`)} peak</strong> in year-end planning.</>,
    },
    {
      headline: <>Q4 forecast peaks are <em>spread across October–December</em> by vessel type.</>,
      detail: <><strong>{forecasts.map((item) => `${t(item.vesselName)} ${t(`${periodPeak(item).month.slice(5)}월`)}`).join(" · ")}</strong> show different demand-concentration windows.</>,
    },
    {
      headline: <>Expected troughs also differ, so <em>response timing should be staggered.</em></>,
      detail: <><strong>{forecasts.map((item) => `${t(item.vesselName)} ${t(`${outlookPoints(item).reduce((low, point) => point.value < low.value ? point : low).month.slice(5)}월`)}`).join(" · ")}</strong></>,
    },
    {
      headline: <><em>{t(strongestMomentum.vesselName)}</em> has the strongest year-end momentum.</>,
      detail: <>Its December outlook is <strong>{signed(periodChange(strongestMomentum))}</strong> versus October; review sales opportunities and production capacity together.</>,
    },
    {
      headline: <><em>{t(weakestMomentum.vesselName)}</em> calls for the most conservative planning.</>,
      detail: <>Its December outlook is <strong>{signed(periodChange(weakestMomentum))}</strong> versus October, so production and procurement need a downside scenario.</>,
    },
  ] : [
    {
      headline: <>{t(forecast.vesselName)} December orders are <em>{signed(forecastEndChange)}</em> versus October.</>,
      detail: <>The Q4 monthly path is <strong>{forecastEndChange >= 0 ? "up" : "down"}</strong>, with a peak in <strong>{t(`${forecastHigh.month.slice(5)}월`)}</strong>.</>,
    },
    {
      headline: <>{t(forecast.vesselName)} is expected to reach its Q4 peak in <em>{t(`${forecastHigh.month.slice(5)}월`)}</em>.</>,
      detail: <>Monthly orders are forecast to reach up to <strong>{formatCapacity(forecastHigh.value, forecast.unit)}</strong>.</>,
    },
    {
      headline: <>{t(forecast.vesselName)} is expected to bottom in <em>{t(`${forecastLow.month.slice(5)}월`)}</em>.</>,
      detail: <>Monthly orders are forecast to bottom at <strong>{formatCapacity(forecastLow.value, forecast.unit)}</strong>.</>,
    },
    {
      headline: <>{t(forecast.vesselName)} Q4 orders are forecast at <em>{formatCapacity(q4Total, forecast.unit)}</em>.</>,
      detail: <>Use the monthly average of <strong>{formatCapacity(q4MonthlyAverage, forecast.unit)}</strong> to review sales and production plans.</>,
    },
    {
      headline: <>{forecastEndChange >= 0 ? "Order opportunities are expected to expand toward year-end." : "Order momentum is expected to moderate toward year-end."}</>,
      detail: <>{forecastEndChange >= 0 ? <><strong>Secure customer touchpoints and production capacity</strong> early.</> : <><strong>Plan orders and procurement conservatively</strong> while monitoring the next rebound.</>}</>,
    },
    {
      headline: <>Monthly orders could move within <em>{formatCapacity(possibleLow, forecast.unit)}–{formatCapacity(possibleHigh, forecast.unit)}</em> as market conditions change.</>,
      detail: <>Prepare <strong>base, upside and downside scenarios</strong> for contract and production schedules.</>,
    },
  ];
  const marketBriefs = language === "en" ? englishMarketBriefs : koreanMarketBriefs;
  const displayedBrief = marketBriefs[activeBrief % marketBriefs.length];

  useEffect(() => {
    setActiveBrief(0);
  }, [portfolio, selectedId]);

  useEffect(() => {
    if (!isBriefPlaying || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => setActiveBrief((current) => (current + 1) % marketBriefs.length), 6000);
    return () => window.clearInterval(timer);
  }, [isBriefPlaying, marketBriefs.length]);

  useEffect(() => {
    const controller = new AbortController();
    const ids = portfolio ? NOTEBOOK_VESSEL_IDS : [vesselId ?? "tanker"];
    setActualsByVessel({});
    Promise.all(ids.map((id) => fetch(`/api/v1/master-data?vesselId=${id}&from=2024-01&to=2026-08`, { credentials: "same-origin", signal: controller.signal })
      .then((response) => response.ok ? response.json() as Promise<MasterDataResponse> : Promise.reject())
      .then((payload) => [id, payload.rows.flatMap((row) => {
        if (row.orderCapacity === null || row.orderCapacity.trim() === "") return [];
        const value = Number(row.orderCapacity);
        return Number.isFinite(value) ? [{ month: row.period, value }] : [];
      })] as const)
      .catch(() => [id, []] as const)))
      .then((entries) => { if (!controller.signal.aborted) setActualsByVessel(Object.fromEntries(entries)); });
    return () => controller.abort();
  }, [portfolio, vesselId]);

  return <section id="dashboard-overview" className={`overview-redesign dashboard-view dashboard-section-target${portfolio ? "" : " overview-vessel-view"}`}>
    <section
      className={`overview-market-brief${portfolio ? "" : " overview-market-brief-vessel"}`}
      style={portfolio ? undefined : {
        backgroundImage: `linear-gradient(90deg, rgba(7,37,70,.96) 0%, rgba(12,48,84,.76) 42%, rgba(11,38,69,.22) 100%), url("${MARKET_BRIEF_IMAGES[forecast.vesselId]}")`,
        backgroundPosition: `center, ${MARKET_BRIEF_IMAGE_POSITIONS[forecast.vesselId]}`,
      }}
    >
      <div className="overview-brief-copy">
        <div className="overview-eyebrow"><Activity size={16} /> MARKET BRIEF</div>
        <div className="overview-brief-slide" key={`${language}-${selectedId}-${activeBrief}`} aria-live="off" data-no-translate>
          <h1>{displayedBrief.headline}</h1>
          <h2>{displayedBrief.detail}</h2>
        </div>
      </div>
      <div className="overview-brief-metrics" aria-label="4분기 전망 요약">
        {portfolio ? <>
          <div><span>전분기 대비 수주 방향</span><strong>상승 {risingVesselCount} · 하락 {fallingVesselCount}</strong><small>5개 선종 공통 비교</small></div>
          <div><span>예상 고점 집중 시기</span><strong>{peakConcentrationLabel}</strong><small>{peakConcentratedVesselCount}개 선종 집중</small></div>
        </> : <>
          <div><span>4분기 누적 전망</span><strong>{formatCapacity(q4Total, forecast.unit)}</strong><small>{forecast.vesselName}</small></div>
          <div><span>4분기 월평균 전망</span><strong>{formatCapacity(q4MonthlyAverage, forecast.unit)}</strong><small>{forecast.vesselName}</small></div>
        </>}
      </div>
      <div className="overview-brief-controls" aria-label="시장 인사이트 전환">
        <div role="group" aria-label="시장 인사이트 선택">
          {marketBriefs.map((_, index) => <button key={index} type="button" aria-label={`${index + 1}번 인사이트`} aria-current={activeBrief === index ? "true" : undefined} onClick={() => setActiveBrief(index)} />)}
        </div>
        <button className="overview-brief-playback" type="button" aria-label={isBriefPlaying ? "인사이트 자동 전환 일시정지" : "인사이트 자동 전환 재생"} onClick={() => setIsBriefPlaying((current) => !current)}>
          {isBriefPlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
        </button>
      </div>
    </section>

    <div className="overview-core-grid">
      <section className="overview-panel overview-timeseries-panel">
        <header><div><h3>{portfolio ? "선종별 실적 및 연말까지 수주 전망" : `${forecast.vesselName} 실적 및 연말까지 수주 전망`}</h3></div>{portfolio ? <nav><button type="button" className={chartId === "aggregate" ? "is-active" : ""} onClick={() => setChartId("aggregate")}>전체 종합</button>{forecasts.map((item) => <button key={item.vesselId} type="button" className={chartId === item.vesselId ? "is-active" : ""} onClick={() => { setChartId(item.vesselId); setSelectedId(item.vesselId); setSelectedDriverId(item.vesselId); }}>{item.vesselName}</button>)}</nav> : <span>{forecast.unit}</span>}</header>
        {portfolio && chartId === "aggregate" ? <PortfolioForecastTimeseries forecasts={forecasts} actualsByVessel={actualsByVessel} loading={loading} /> : <ForecastTimeseries forecast={chartForecast ?? forecast} actuals={actuals} loading={loading} darkMode={darkMode} />}
      </section>
      {portfolio ? <section className="overview-panel overview-heatmap-panel">
        <header><h3>선종별 7~12월 월별 수주 전망</h3></header>
        <ForecastHeatmap forecasts={forecasts} onSelect={selectHeatmapVessel} />
      </section> : <section className="overview-panel overview-driver-panel overview-core-driver-panel"><header><h3>수주 전망 주요 기여 변수</h3><span>{forecast.vesselName}</span></header><DriverBars source={forecast.drivers} limit={8} /></section>}
    </div>

    {portfolio && <div className="overview-analysis-grid">
      <section className="overview-panel overview-driver-panel"><header><h3>수주 전망 주요 기여 변수</h3><select className="overview-vessel-select" aria-label="기여 변수 선종 선택" value={selectedDriverId} onChange={(event) => {
        const value = event.target.value as NotebookVesselId | "common";
        setSelectedDriverId(value);
        if (value !== "common") setSelectedId(value);
      }}><option value="common">공통변수</option>{forecasts.map((item) => <option key={item.vesselId} value={item.vesselId}>{item.vesselName}</option>)}</select></header><DriverBars source={selectedDriverId === "common" ? COMMON_DRIVERS : NOTEBOOK_FORECASTS[selectedDriverId].drivers} /></section>
    </div>}
  </section>;
}
