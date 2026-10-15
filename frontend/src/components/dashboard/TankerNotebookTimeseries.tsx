import { useMemo } from "react";
import EChartsReact from "../common/LocalizedECharts";
import timeseries from "../../data/tankerNotebookTimeseries.json";

const ACTUAL = "실제 (사후 확인분 포함 · 2026-08까지)";
const BUFFER = "시차 완충 예측 · 평가 제외";
const VALIDATION = "Rolling Validation 예측";
const TEST = "최종 Test 예측 · 3개월";
const FORECAST = "Test 이후 전망";

const formatDwt = (value: number) => `${Math.round(value).toLocaleString("ko-KR")} DWT`;

export default function TankerNotebookTimeseries({ darkMode }: { darkMode: boolean }) {
  const option = useMemo(() => {
    const text = darkMode ? "#cbd5e1" : "#475569";
    const muted = darkMode ? "#94a3b8" : "#64748b";
    const gridLine = darkMode ? "#334155" : "#e5e7eb";
    const actualColor = darkMode ? "#f1f5f9" : "#30343b";
    const validationData = timeseries.predictions
      .filter((point) => point.phase === "validation")
      .map((point) => [point.month, point.value] as [string, number]);
    const bufferData = timeseries.buffer.map((point) => [point.month, point.value] as [string, number]);
    const testData = timeseries.predictions
      .filter((point) => point.phase === "test")
      .map((point) => [point.month, point.value] as [string, number]);
    const forecastData = timeseries.forecasts.map((point) => [point.month, point.value] as [string, number]);
    const continueFrom = (previous: [string, number][], current: [string, number][]) =>
      previous.length && current.length ? [previous[previous.length - 1], ...current] : current;
    const connectedBuffer = continueFrom(validationData, bufferData);
    const connectedTest = continueFrom(bufferData, testData);
    const connectedForecast = continueFrom(testData, forecastData);
    return {
      animationDuration: 450,
      backgroundColor: "transparent",
      title: {
        text: "유조선 월별 수주용량 실적과 전망",
        left: "center",
        top: 2,
        textStyle: { color: text, fontSize: 15, fontWeight: 600 },
      },
      legend: {
        top: 31,
        left: "center",
        data: [ACTUAL, BUFFER, VALIDATION, TEST, FORECAST],
        textStyle: { color: muted, fontSize: 11 },
        itemWidth: 22,
        itemHeight: 3,
      },
      grid: { left: 76, right: 28, top: 74, bottom: 58 },
      tooltip: {
        trigger: "axis",
        confine: true,
        backgroundColor: darkMode ? "#0f172a" : "#fff",
        borderColor: gridLine,
        textStyle: { color: darkMode ? "#f8fafc" : "#1e293b" },
        formatter: (params: Array<{ axisValueLabel: string; marker: string; seriesName: string; value: [string, number] }>) => {
          const visible = params.filter((item) => typeof item.value?.[1] === "number");
          if (!visible.length) return "";
          return `<b>${visible[0].axisValueLabel}</b><br/>${visible.map((item) => `${item.marker} ${item.seriesName}: <b>${formatDwt(item.value[1])}</b>`).join("<br/>")}`;
        },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, start: 0, end: 100, minSpan: 8 },
        {
          type: "slider", xAxisIndex: 0, start: 0, end: 100, minSpan: 8,
          bottom: 10, height: 18, showDetail: false, showDataShadow: false,
          backgroundColor: darkMode ? "#0f172a" : "#f1f5f9", borderColor: gridLine,
          fillerColor: darkMode ? "rgba(59,130,246,.25)" : "rgba(59,130,246,.14)",
        },
      ],
      xAxis: {
        type: "time",
        min: "2014-01-01",
        max: "2026-12-31",
        axisLine: { lineStyle: { color: gridLine } },
        axisTick: { show: false },
        splitLine: { show: true, lineStyle: { color: gridLine } },
        axisLabel: {
          color: muted,
          fontSize: 10,
          formatter: (value: number) => String(new Date(value).getUTCFullYear()),
        },
      },
      yAxis: {
        type: "value", name: "수주용량 (DWT)", min: 0,
        nameTextStyle: { color: muted, fontSize: 11 },
        axisLabel: { color: muted, fontSize: 10, formatter: (value: number) => value.toLocaleString("ko-KR") },
        splitLine: { lineStyle: { color: gridLine } },
      },
      series: [
        {
          name: ACTUAL, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: timeseries.actuals.map((point) => [point.month, point.value]),
          showSymbol: false, lineStyle: { color: actualColor, width: 2 }, itemStyle: { color: actualColor }, z: 5,
          markArea: {
            silent: true,
            data: [
              [{ xAxis: "2014-01", itemStyle: { color: darkMode ? "rgba(148,163,184,.08)" : "rgba(148,163,184,.16)" } }, { xAxis: "2014-09" }],
              [{ xAxis: "2014-09", itemStyle: { color: darkMode ? "rgba(96,165,250,.05)" : "rgba(191,219,254,.28)" } }, { xAxis: "2019-11" }],
              [{ xAxis: "2019-11", itemStyle: { color: darkMode ? "rgba(59,130,246,.10)" : "rgba(147,197,253,.32)" } }, { xAxis: "2025-11" }],
              [{ xAxis: "2025-11", itemStyle: { color: darkMode ? "rgba(245,158,11,.10)" : "rgba(253,230,138,.30)" } }, { xAxis: "2026-04" }],
              [{ xAxis: "2026-04", itemStyle: { color: darkMode ? "rgba(244,63,94,.11)" : "rgba(253,164,175,.30)" } }, { xAxis: "2026-12-31" }],
            ],
          },
        },
        {
          name: BUFFER, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: connectedBuffer,
          showSymbol: false, connectNulls: true, lineStyle: { color: "#9b958b", width: 2 }, itemStyle: { color: "#9b958b" }, z: 6,
        },
        {
          name: VALIDATION, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: validationData,
          showSymbol: false, lineStyle: { color: "#3785c1", width: 2 }, itemStyle: { color: "#3785c1" }, z: 7,
        },
        {
          name: TEST, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: connectedTest,
          showSymbol: false, lineStyle: { color: "#dfa900", width: 2.5 }, itemStyle: { color: "#dfa900" }, z: 8,
        },
        {
          name: FORECAST, type: "line", xAxisIndex: 0, yAxisIndex: 0,
          data: connectedForecast,
          showSymbol: false, lineStyle: { color: "#df3444", width: 2.5 }, itemStyle: { color: "#df3444" }, z: 9,
        },
      ],
    };
  }, [darkMode]);

  return <EChartsReact option={option} notMerge lazyUpdate style={{ height: 470, width: "100%" }} />;
}
