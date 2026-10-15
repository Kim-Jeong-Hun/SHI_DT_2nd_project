import { useEffect, useMemo, useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import {
  Activity, ArrowDownRight, ArrowUpRight, BarChart3,
  ChevronDown, Download, FileText, Globe2, Info, LayoutDashboard, Lock, Moon, Newspaper, Settings2, Ship, SlidersHorizontal,
  TrendingDown, TrendingUp, UserRound, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  ALL_VESSELS, MONTHS, VESSELS, cumulative, forecastNextQuarter,
  getMetrics, signedPct, sum,
} from "../../data/mockMarket";
import type { VesselMarketData } from "../../data/mockMarket";
import { TANKER_NOTEBOOK_FORECAST } from "../../data/tankerNotebookForecast";
import { NOTEBOOK_FORECASTS, NOTEBOOK_VESSEL_IDS, isNotebookVessel } from "../../data/notebookForecasts";
import type { NotebookForecast } from "../../data/notebookForecasts";
import ReportRegimeCharts from "./ReportRegimeCharts";
import VesselOrderForecast, { PortfolioOrderForecast } from "./OrderForecast";
import Newsroom from "./Newsroom";
import DetailsPage from "./DetailsPage";
import AboutPage from "./AboutPage";
import CustomForecast from "./CustomForecast";
import DashboardOverview from "./DashboardOverview";
import ShipPulseComparison from "./ShipPulseComparison";
import TankerNotebookTimeseries from "./TankerNotebookTimeseries";
import { useDashboardStore } from "../../store/useDashboardStore";
import "../../styles/market-dashboard.css";
import MyPage from "../account/MyPage";
import SubscriptionPage from "../subscription/SubscriptionPage";
import type { AuthUser } from "../../App";
import AppBrand from "../common/AppBrand";
import { useI18n } from "../../i18n";

const dateLabel = "2026년 6월 데이터 마감";
const panelClass = "rounded-2xl border border-slate-200/85 bg-white shadow-[0_4px_24px_rgba(21,44,79,0.035)]";
const chartColors = {
  light: { text: "#8290a4", muted: "#64748b", grid: "#edf1f6", axis: "#e2e8f0", previous: "#b8c4d6", cellBorder: "#fff", tooltip: "#11223e" },
  dark: { text: "#94a3b8", muted: "#cbd5e1", grid: "#334155", axis: "#475569", previous: "#94a3b8", cellBorder: "#1e293b", tooltip: "#0f172a" },
} as const;

const formatted = (amount: number) => amount.toLocaleString("ko-KR", { maximumFractionDigits: 1 });
const compactCapacity = (amount: number, unit: string, language: "ko" | "en" = "ko") => language === "en"
  ? amount >= 1_000_000 ? `${formatted(amount / 1_000_000)}M ${unit}` : amount >= 1_000 ? `${formatted(amount / 1_000)}K ${unit}` : `${formatted(amount)} ${unit}`
  : amount >= 10_000 ? `${formatted(amount / 10_000)}만 ${unit}` : `${formatted(amount)} ${unit}`;
const planNames: Record<string, string> = {
  explore: "Explore",
  professional: "Professional",
  enterprise: "Enterprise",
};
const planLevel: Record<string, number> = { explore: 1, professional: 2, enterprise: 3 };
const pctColor = (value: number) => value >= 0 ? "text-emerald-600" : "text-rose-600";
const polarity = (value: number) => value >= 0 ? ArrowUpRight : ArrowDownRight;
const dashboardSections = [
  { id: "dashboard-overview", label: "시장 개요", icon: LayoutDashboard },
  { id: "order-forecast", label: "분기 수주 전망", icon: TrendingUp },
  { id: "freight-analysis", label: "과거 수주·운임 시장 국면", icon: Activity },
  { id: "monthly-heatmap", label: "월별 수주 전망", icon: BarChart3 },
  { id: "custom-forecast", label: "사용자 지정 예측", icon: SlidersHorizontal },
] as const;

function MetricCard({ title, value, change, helper, icon: Icon }: {
  title: string;
  value: string;
  change?: number;
  helper: string;
  icon: typeof Activity;
}) {
  const Direction = change === undefined ? null : polarity(change);
  return (
    <Card className={`${panelClass} py-0 gap-0`}>
      <CardContent className="px-5 py-3 md:px-6">
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs font-semibold tracking-wide text-slate-500">{title}</span>
          <span className="rounded-lg bg-slate-100 p-2 text-slate-500"><Icon className="h-4 w-4" /></span>
        </div>
        <div className="mt-2 flex items-end gap-2">
          <span className="text-[clamp(1.4rem,2vw,2rem)] leading-tight font-semibold tracking-[-0.045em] text-slate-900">{value}</span>
          {change !== undefined && Direction && <Direction className={`mb-1 h-4 w-4 ${pctColor(change)}`} />}
        </div>
        <p className="mt-1.5 text-xs leading-5 text-slate-500">{helper}</p>
      </CardContent>
    </Card>
  );
}

function MarketAnalysis({ vessel, view }: { vessel: VesselMarketData; view: "forecast" | "freight" }) {
  const darkMode = useDashboardStore((state) => state.darkMode);
  const isTankerNotebook = view === "forecast" && vessel.id === "tanker";
  const [tankerActuals, setTankerActuals] = useState<(number | null)[] | null>(null);
  const [tankerDataError, setTankerDataError] = useState("");

  useEffect(() => {
    if (!isTankerNotebook) {
      setTankerActuals(null);
      setTankerDataError("");
      return;
    }

    const controller = new AbortController();
    fetch("/api/v1/master-data?vesselId=tanker&from=2026-01&to=2026-09", {
      credentials: "same-origin",
      signal: controller.signal,
    })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "유조선 마스터 데이터를 불러오지 못했습니다.");
        const months: (number | null)[] = Array(9).fill(null);
        for (const row of data.rows as { period: string; orderCapacity: string | null }[]) {
          const monthIndex = Number(row.period.slice(5, 7)) - 1;
          if (monthIndex >= 0 && monthIndex < months.length && row.orderCapacity !== null) {
            months[monthIndex] = Number(row.orderCapacity);
          }
        }
        setTankerActuals(months);
      })
      .catch((error: Error) => {
        if (error.name !== "AbortError") setTankerDataError(error.message);
      });
    return () => controller.abort();
  }, [isTankerNotebook]);

  const chartOption = useMemo(() => {
    const actual = isTankerNotebook && tankerActuals
      ? (() => {
        let running = 0;
        return tankerActuals.map((value) => {
          if (value === null) return null;
          running += value;
          return running / 10000;
        });
      })()
      : cumulative(vessel.current);
    const tankerBase = isTankerNotebook && tankerActuals ? tankerActuals.reduce<number>((sum, value) => sum + (value ?? 0), 0) : 0;
    const tankerForecastCumulative = isTankerNotebook ? (() => {
      let running = tankerBase;
      const values: (number | null)[] = Array(12).fill(null);
      values[7] = running / 10000;
      for (const forecast of TANKER_NOTEBOOK_FORECAST.forecasts) {
        const monthIndex = Number(forecast.month.slice(5, 7)) - 1;
        if (monthIndex > 7 && monthIndex < values.length) {
          running += forecast.value;
          values[monthIndex] = running / 10000;
        }
      }
      return values;
    })() : null;
    const actualSeries = isTankerNotebook
      ? [...(actual as (number | null)[]), null, null, null]
      : [...(actual as number[]), null, null, null];
    const projected = isTankerNotebook
      ? null
      : cumulative([...vessel.current, ...forecastNextQuarter(vessel)]);
    const colors = chartColors[darkMode ? "dark" : "light"];

    return {
      animationDuration: 450,
      color: [vessel.color, "#f59e0b"],
      grid: { left: 46, right: 18, top: 45, bottom: 72 },
      tooltip: {
        trigger: "axis",
        backgroundColor: colors.tooltip,
        borderWidth: 0,
        textStyle: { color: "#fff" },
        formatter: (params: Array<{ axisValue: string; marker: string; seriesName: string; value: number }>) =>
          `<div style="font-weight:600;margin-bottom:5px">${params[0]?.axisValue ?? ""}</div>` +
          params.filter((p) => p.value != null).map((p) => `${p.marker} ${p.seriesName}: <b>${formatted(p.value)} 만 ${isTankerNotebook ? "DWT" : "CGT"}</b>`).join("<br/>"),
      },
      legend: {
        top: 4, right: 42, icon: "roundRect", itemWidth: 15, itemHeight: 7,
        textStyle: { color: colors.muted, fontSize: 11 },
        data: isTankerNotebook ? ["실제 누적 (1~8월)", "노트북 예측 누적 (9~12월)"] : ["1~9월 가상값", "4분기 예측"],
      },
      toolbox: {
        top: 0, right: 0, itemSize: 16,
        iconStyle: { borderColor: colors.text },
        feature: { restore: { title: "전체 보기" } },
      },
      dataZoom: [
        { type: "inside", xAxisIndex: 0, start: 0, end: 100, minSpan: 20, zoomOnMouseWheel: true, moveOnMouseWheel: false },
        {
          type: "slider", xAxisIndex: 0, start: 0, end: 100, minSpan: 20,
          bottom: 8, height: 20, showDataShadow: false, showDetail: false, brushSelect: false,
          backgroundColor: darkMode ? "#0f172a" : "#f1f5f9",
          fillerColor: darkMode ? "rgba(59,130,246,0.25)" : "rgba(59,130,246,0.14)",
          borderColor: colors.axis, handleStyle: { color: vessel.color, borderColor: vessel.color },
          textStyle: { color: colors.text },
        },
      ],
      xAxis: {
        type: "category", data: isTankerNotebook ? Array.from({ length: 12 }, (_, index) => `${index + 1}월`) : [...MONTHS, "10월", "11월", "12월"], boundaryGap: false,
        axisLine: { lineStyle: { color: colors.axis } }, axisTick: { show: false },
        axisLabel: { color: colors.text, margin: 16, fontSize: 11 },
      },
      yAxis: {
        type: "value", name: isTankerNotebook ? "누적 만 DWT" : "누적 만 CGT", nameTextStyle: { color: colors.text, align: "left" },
        axisLine: { show: false }, axisTick: { show: false },
        splitLine: { lineStyle: { color: colors.grid } },
        axisLabel: { color: colors.text, fontSize: 11 },
      },
      series: [
        {
          name: isTankerNotebook ? "실제 누적 (1~8월)" : "1~9월 가상값", type: "line", smooth: 0.32, data: actualSeries,
          symbol: "circle", symbolSize: 7, showSymbol: false,
          lineStyle: { width: 3 },
          itemStyle: { color: vessel.color, borderColor: "#fff", borderWidth: 2 },
          areaStyle: { color: vessel.color, opacity: 0.085 },
          emphasis: { focus: "series", scale: 1.6 },
        },
        {
          name: isTankerNotebook ? "노트북 예측 누적 (9~12월)" : "4분기 예측", type: "line", smooth: 0.32, data: isTankerNotebook ? tankerForecastCumulative : [...Array(8).fill(null), ...(projected as number[]).slice(8)],
          symbol: "circle", showSymbol: false,
          lineStyle: { width: 2, type: "dashed" },
          itemStyle: { color: "#f59e0b" },
        },
      ],
    };
  }, [vessel, darkMode, isTankerNotebook, tankerActuals]);
  const forecastTotal = isTankerNotebook
    ? sum(TANKER_NOTEBOOK_FORECAST.forecasts.filter(({ month }) => month >= "2026-10").map(({ value }) => value))
    : sum(forecastNextQuarter(vessel));
  const tankerYearEndTotal = isTankerNotebook && tankerActuals
    ? tankerActuals.reduce<number>((total, value) => total + (value ?? 0), 0) + sum(TANKER_NOTEBOOK_FORECAST.forecasts.map(({ value }) => value))
    : 0;

  return (
    <section className={`${panelClass} analysis-panel min-w-0 p-5 md:p-6`}>
      <div>
        <p className="text-base font-semibold text-slate-900">{view === "freight" ? "과거 수주·운임 시장 국면" : "분기 수주 전망"}</p>
        <p className="mt-1 text-xs text-slate-500">{vessel.label} · {view === "freight" ? "군집분석 보고서 3절 · 1차 군집" : "수주예측 분석 파이프라인 · D+3 운영 예측"}</p>
      </div>
      <div id="analysis-chart-panel">
        {view === "forecast" ? (
          <>
            {isTankerNotebook
              ? <div className="mt-3 min-w-0 rounded-xl border border-slate-100 bg-white p-2"><TankerNotebookTimeseries darkMode={darkMode} /></div>
              : <EChartsReact option={chartOption} notMerge lazyUpdate style={{ height: "var(--analysis-chart-height, 325px)", width: "100%" }} />}
            {!isTankerNotebook && <p className="mb-2 text-[11px] text-slate-500">4분기 예상 추가 수주량 {formatted(forecastTotal)}만 CGT · 연말 예상 누적 {formatted(sum(vessel.current) + forecastTotal)}만 CGT · 휠 또는 아래 범위 막대로 확대·축소</p>}
            {isTankerNotebook && tankerActuals && <p className="mt-2 mb-2 text-[11px] text-slate-500">4분기 예상 추가 수주용량 {formatted(forecastTotal / 10000)}만 DWT · 연말 예상 누적 {formatted(tankerYearEndTotal / 10000)}만 DWT</p>}
            {isTankerNotebook && !tankerActuals && tankerDataError && <p className="mb-2 text-[11px] text-rose-600">실제 수주 데이터 요약을 불러오지 못했습니다: {tankerDataError}</p>}
          </>
        ) : (
          <ReportRegimeCharts key={vessel.id} vesselId={vessel.id} vesselLabel={vessel.label} darkMode={darkMode} />
        )}
      </div>
      {view === "forecast" && isTankerNotebook && <div className="flex items-start gap-2 rounded-lg border border-amber-100 bg-amber-50 px-3 py-2 text-xs text-amber-900">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        {TANKER_NOTEBOOK_FORECAST.model} · {TANKER_NOTEBOOK_FORECAST.strategy} · {TANKER_NOTEBOOK_FORECAST.lambda}. 보고서의 Validation+Test 분기 누적 sMAPE {TANKER_NOTEBOOK_FORECAST.validationTestSmape.toFixed(1)}% (표준편차 {TANKER_NOTEBOOK_FORECAST.validationTestStd.toFixed(1)}%p); 참고용 전망이며 정확도 한계가 큽니다.
      </div>}
      {view === "forecast" && !isTankerNotebook && <div className="flex items-center gap-2 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2 text-xs text-slate-500">
        <Info className="h-3.5 w-3.5 shrink-0" />
        데모 예측: 4분기 각 월에 최근 3개월 평균 발주량 적용. 실제 전망치가 아님.
      </div>}
    </section>
  );
}

function NotebookInsightPanel({ forecast }: { forecast?: NotebookForecast }) {
  const forecasts = NOTEBOOK_VESSEL_IDS.map((id) => NOTEBOOK_FORECASTS[id]);
  if (!forecast) {
    return (
      <section id="signal-interpretation" className={`${panelClass} p-4 dashboard-section-target`} aria-labelledby="interpretation-heading">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div>
            <h2 id="interpretation-heading" className="text-base font-semibold text-slate-900">선종별 다음 분기 신호</h2>
            <p className="mt-1 text-xs text-slate-500">단위가 다른 선종은 합산하지 않고 분기 변화율로 비교합니다.</p>
          </div>
          <Badge variant="outline" className="border-blue-200 bg-blue-50 text-blue-700">실행 노트북 5종</Badge>
        </div>
        <div className="mt-3 grid gap-3 md:grid-cols-2 xl:grid-cols-4">
          {forecasts.map((item) => (
            <div key={item.vesselId} className="rounded-xl border border-slate-100 bg-slate-50 p-3">
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-semibold text-slate-700">{item.vesselName}</span>
                <span className={`text-base font-bold ${pctColor(item.quarterChange)}`}>{item.quarterChange > 0 ? "+" : ""}{item.quarterChange.toFixed(1)}%</span>
              </div>
              <p className="mt-2 text-xs leading-5 text-slate-500">{item.signal}</p>
              <p className="mt-2 text-[11px] font-medium text-slate-600">고점 {item.peakMonth} · Test 오차 {item.testRelativeError.toFixed(1)}%</p>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section id="signal-interpretation" className={`${panelClass} p-4 dashboard-section-target`} aria-labelledby="interpretation-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="interpretation-heading" className="text-base font-semibold text-slate-900">예측 신호와 판단 기준</h2>
          <p className="mt-1 text-xs text-slate-500">{forecast.vesselName} · 분기 전망과 모델 설명값을 비즈니스 관점으로 정리</p>
        </div>
        <Badge variant="outline" className="border-indigo-100 bg-indigo-50 text-indigo-600">SHAP 기반 설명</Badge>
      </div>
      <div className="mt-3 flex items-center gap-2 rounded-xl bg-slate-900 px-3 py-2.5 text-sm font-semibold text-white">
        <Activity className="h-4 w-4 text-sky-300" />{forecast.signal}
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-[1.15fr_.85fr]">
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700">권고 해석</p>
          <p className="mt-1.5 text-xs leading-5 text-slate-500">{forecast.action}</p>
        </div>
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3">
          <p className="text-xs font-semibold text-slate-700">핵심 동인</p>
          <p className="mt-1.5 text-xs leading-5 text-slate-500">{forecast.drivers.slice(0, 3).map(({ label, share }) => `${label} ${share.toFixed(1)}%`).join(" · ")}</p>
        </div>
      </div>
      <p className="mt-3 flex gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />SHAP 비중은 예측 기여도이며 인과효과가 아닙니다. Test 상대오차 {forecast.testRelativeError.toFixed(1)}%를 감안해 단일 숫자가 아닌 방향 신호로 활용하세요.
      </p>
    </section>
  );
}

function BulkInsightPanel({ vessel }: { vessel: VesselMarketData }) {
  const { yoy, quarterChange, peakMonth, peakValue } = getMetrics(vessel);
  return (
    <section id="signal-interpretation" className={`${panelClass} p-4 dashboard-section-target`} aria-labelledby="bulk-interpretation-heading">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h2 id="bulk-interpretation-heading" className="text-base font-semibold text-slate-900">변화 신호 해석</h2>
          <p className="mt-1 text-xs text-slate-500">벌크선 · 기존 시장 데이터에서 추출한 핵심 관찰</p>
        </div>
        <Badge variant="outline" className="border-slate-200 bg-slate-50 text-slate-600">노트북 미적용</Badge>
      </div>
      <div className="mt-3 grid gap-3 md:grid-cols-3">
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3"><p className="text-xs text-slate-500">전년 동기 대비</p><p className={`mt-1 text-lg font-semibold ${pctColor(yoy)}`}>{signedPct(yoy)}</p></div>
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3"><p className="text-xs text-slate-500">최근 3개월 변화</p><p className={`mt-1 text-lg font-semibold ${pctColor(quarterChange)}`}>{signedPct(quarterChange)}</p></div>
        <div className="rounded-xl border border-slate-100 bg-slate-50 p-3"><p className="text-xs text-slate-500">올해 최고 월</p><p className="mt-1 text-lg font-semibold text-slate-900">{peakMonth} · {formatted(peakValue)}만 CGT</p></div>
      </div>
      <p className="mt-3 flex gap-1.5 rounded-lg bg-amber-50 px-3 py-2 text-[11px] leading-5 text-amber-800"><Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />벌크선에는 이번 수주예측 노트북 결과를 적용하지 않았습니다.</p>
    </section>
  );
}

function ComparisonBars() {
  const { language } = useI18n();
  const vesselId = useDashboardStore((state) => state.vesselId);
  const darkMode = useDashboardStore((state) => state.darkMode);
  const colors = chartColors[darkMode ? "dark" : "light"];
  const totals = [...VESSELS].map((v) => ({ ...v, total: sum(v.current) }))
    .sort((a, b) => b.total - a.total);
  const totalOrders = totals.reduce((total, vessel) => total + vessel.total, 0);
  const leader = totals[0];
  const runnerUp = totals[1];
  const leaderShare = totalOrders ? (leader.total / totalOrders) * 100 : 0;
  const topThreeShare = totalOrders ? (totals.slice(0, 3).reduce((total, vessel) => total + vessel.total, 0) / totalOrders) * 100 : 0;
  const leaderGap = leader.total - runnerUp.total;
  const chartOption = {
    animationDuration: 450,
    grid: { left: 105, right: 45, top: 10, bottom: 28 },
    tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, backgroundColor: colors.tooltip, textStyle: { color: "#fff" }, valueFormatter: (value: number) => `${formatted(value)} 만 CGT` },
    xAxis: {
      type: "value", axisLine: { show: false }, axisTick: { show: false },
      splitLine: { lineStyle: { color: colors.grid } }, axisLabel: { color: colors.text, fontSize: 11 },
    },
    yAxis: {
      type: "category", inverse: true, data: totals.map((v) => v.label),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: colors.muted, fontSize: 12 },
    },
    series: [{
      type: "bar", barWidth: 17, label: { show: true, position: "right", color: colors.muted, formatter: (params: { value: number }) => formatted(params.value) },
      data: totals.map((v) => ({ value: v.total, itemStyle: { color: v.color, opacity: vesselId === "all" || v.id === vesselId ? 1 : 0.65, borderRadius: [0, 5, 5, 0] } })),
    }],
  };

  return (
    <section className={`${panelClass} flex flex-col p-5 md:p-6`}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold text-slate-900">선종별 누적 발주 비교</h2>
          <p className="mt-1 text-xs text-slate-500">2026년 1~9월 누적 · 단위: 만 CGT</p>
        </div>
        <BarChart3 className="h-5 w-5 text-slate-400" />
      </div>
      <EChartsReact option={chartOption} notMerge lazyUpdate style={{ height: 300, width: "100%" }} />
      <div className="mt-auto border-t border-slate-100 pt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <strong className="text-xs font-semibold text-slate-800">{language === "en" ? "Cumulative order insight" : "누적 발주 핵심 인사이트"}</strong>
          <span className="text-[10px] text-slate-400">2026.01–09</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl bg-slate-50 px-3 py-3"><span className="text-[10px] text-slate-500">{language === "en" ? "Order leader" : "누적 발주 1위"}</span><strong className="mt-1 block text-sm text-slate-900">{leader.label}</strong></div>
          <div className="rounded-xl bg-slate-50 px-3 py-3"><span className="text-[10px] text-slate-500">{language === "en" ? "Leader share" : "1위 선종 비중"}</span><strong className="mt-1 block text-sm text-blue-700">{leaderShare.toFixed(1)}%</strong></div>
          <div className="rounded-xl bg-slate-50 px-3 py-3"><span className="text-[10px] text-slate-500">{language === "en" ? "Top 3 concentration" : "상위 3개 집중도"}</span><strong className="mt-1 block text-sm text-slate-900">{topThreeShare.toFixed(1)}%</strong></div>
        </div>
        <p className="mt-3 text-[11px] leading-5 text-slate-500">{language === "en" ? `${leader.label} leads the runner-up by ${formatted(leaderGap)} ten-thousand CGT.` : `${leader.label}이 2위보다 ${formatted(leaderGap)}만 CGT 앞서 있습니다.`}</p>
      </div>
    </section>
  );
}

function Heatmap() {
  const { language } = useI18n();
  const vesselId = useDashboardStore((state) => state.vesselId);
  const setVesselId = useDashboardStore((state) => state.setVesselId);
  const darkMode = useDashboardStore((state) => state.darkMode);
  const colors = chartColors[darkMode ? "dark" : "light"];
  const forecasts = NOTEBOOK_VESSEL_IDS.map((id) => NOTEBOOK_FORECASTS[id]);
  const months = forecasts[0].monthly.map(({ month }) => `${Number(month.slice(5))}월`);
  const outlookChanges = forecasts.map((forecast) => {
    const firstValue = forecast.monthly[0]?.value ?? 0;
    const lastValue = forecast.monthly.at(-1)?.value ?? firstValue;
    return { vesselName: forecast.vesselName, change: firstValue ? ((lastValue - firstValue) / firstValue) * 100 : 0 };
  });
  const risingCount = outlookChanges.filter(({ change }) => change > 0).length;
  const fallingCount = outlookChanges.filter(({ change }) => change < 0).length;
  const strongestRise = outlookChanges.reduce((best, item) => item.change > best.change ? item : best);
  const steepestDrop = outlookChanges.reduce((worst, item) => item.change < worst.change ? item : worst);
  const palette = darkMode
    ? ["#172a45", "#1e416d", "#255b93", "#2d78bf", "#60a5fa"]
    : ["#e7f0fb", "#c9dff5", "#91bee9", "#4c94db", "#1769bf"];
  const values: Array<{
    value: [number, number, number, number];
    itemStyle: { color: string; borderColor: string; borderWidth: number };
    label: { color: string; formatter?: string };
  }> = forecasts.flatMap((forecast, vesselIndex) => {
    const rowValues = forecast.monthly.map(({ value }) => value);
    const minimum = Math.min(...rowValues);
    const maximum = Math.max(...rowValues);
    return forecast.monthly.map(({ value }, monthIndex) => {
      const ratio = maximum === minimum ? 0.5 : (value - minimum) / (maximum - minimum);
      const colorIndex = Math.min(palette.length - 1, Math.floor(ratio * palette.length));
      return {
        value: [monthIndex, vesselIndex, ratio, value],
        itemStyle: {
          color: palette[colorIndex],
          borderColor: forecast.vesselId === vesselId ? "#60a5fa" : colors.cellBorder,
          borderWidth: forecast.vesselId === vesselId ? 2 : 4,
        },
        label: { color: colorIndex >= 3 ? "#fff" : darkMode ? "#dbeafe" : "#24415f" },
      };
    });
  });
  const chartOption = {
    animationDuration: 350,
    grid: { left: 105, right: 12, top: 18, bottom: 30 },
    visualMap: { show: false, min: 0, max: 1, dimension: 2, inRange: { color: palette } },
    tooltip: {
      backgroundColor: colors.tooltip,
      textStyle: { color: "#fff" },
      formatter: (params: { value: [number, number, number, number] }) => {
        const [monthIndex, vesselIndex, , value] = params.value;
        const forecast = forecasts[vesselIndex];
        return `${forecast.vesselName} · ${months[monthIndex]}<br/>예측 수주용량 <b>${formatted(value)} ${forecast.unit}</b>`;
      },
    },
    xAxis: {
      type: "category", data: months, position: "top",
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: colors.text, fontSize: 11 }, splitArea: { show: false },
    },
    yAxis: {
      type: "category", inverse: true, data: forecasts.map(({ vesselName }) => vesselName),
      axisLine: { show: false }, axisTick: { show: false },
      axisLabel: { color: colors.muted, fontSize: 12 }, splitArea: { show: false },
    },
    series: [{
      type: "heatmap",
      label: { show: true, formatter: (params: { value: [number, number, number, number] }) => {
        const forecast = forecasts[params.value[1]];
        return compactCapacity(params.value[3], forecast.unit, language);
      }, fontSize: 10, fontWeight: 600 },
      data: values,
    }],
  };
  return (
    <section id="monthly-heatmap" className={`${panelClass} flex min-w-0 flex-col p-5 md:p-6 dashboard-section-target`}>
      <h2 className="text-base font-semibold text-slate-900">월별 수주 전망</h2>
      <p className="mt-1 text-xs text-slate-500">색상은 각 선종의 7~12월 안에서만 비교 · 셀 선택 시 선종 전환</p>
      <div className="mt-5 overflow-x-auto">
        <div className="min-w-[540px]">
          <EChartsReact option={chartOption} notMerge lazyUpdate style={{ height: 285, width: "100%" }}
            onEvents={{ click: (params: { value?: [number, number, number, number] }) => {
              const forecast = params.value ? forecasts[params.value[1]] : undefined;
              if (forecast) setVesselId(forecast.vesselId);
            } }} />
        </div>
      </div>
      <div className="mt-5 flex justify-end gap-4 text-[11px] text-slate-500">
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-blue-100" />선종별 최소</span>
        <span className="flex items-center gap-1.5"><i className="h-2.5 w-2.5 rounded-sm bg-blue-600" />선종별 최대</span>
      </div>
      <div className="mt-auto border-t border-slate-100 pt-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <strong className="text-xs font-semibold text-slate-800">{language === "en" ? "Monthly outlook insight" : "월별 전망 핵심 인사이트"}</strong>
          <span className="text-[10px] text-slate-400">7→12월</span>
        </div>
        <div className="grid grid-cols-3 gap-2">
          <div className="rounded-xl bg-slate-50 px-3 py-3"><span className="text-[10px] text-slate-500">{language === "en" ? "Direction" : "전망 방향"}</span><strong className="mt-1 block text-sm text-slate-900">{language === "en" ? `${risingCount} up · ${fallingCount} down` : `상승 ${risingCount} · 하락 ${fallingCount}`}</strong></div>
          <div className="rounded-xl bg-emerald-50 px-3 py-3"><span className="text-[10px] text-emerald-700">{language === "en" ? "Strongest rise" : "상승 폭 최대"}</span><strong className="mt-1 block text-sm text-emerald-700">{strongestRise.vesselName} {signedPct(strongestRise.change)}</strong></div>
          <div className="rounded-xl bg-rose-50 px-3 py-3"><span className="text-[10px] text-rose-700">{language === "en" ? "Steepest drop" : "하락 폭 최대"}</span><strong className="mt-1 block text-sm text-rose-700">{steepestDrop.vesselName} {signedPct(steepestDrop.change)}</strong></div>
        </div>
        <p className="mt-3 text-[11px] leading-5 text-slate-500">{language === "en" ? "Changes compare each vessel type's July and December forecasts." : "변화율은 각 선종의 7월 전망과 12월 전망을 비교한 값입니다."}</p>
      </div>
    </section>
  );
}

const csvCell = (value: unknown) => `"${String(value ?? "").replaceAll('"', '""')}"`;

async function exportCsv(vessel: VesselMarketData, isAllVessels: boolean) {
  const vessels = isAllVessels ? VESSELS : [vessel];
  const datasets = await Promise.all(vessels.map(async (item) => {
    const response = await fetch(`/api/v1/master-data?vesselId=${item.id}`, { credentials: "same-origin" });
    if (!response.ok) throw new Error("원본 마스터 데이터를 불러오지 못했습니다.");
    const payload = await response.json() as { rows: { sourceRow: Record<string, unknown> | null }[] };
    return payload.rows.flatMap<Record<string, unknown>>((row) => row.sourceRow
      ? [{ ...(isAllVessels ? { 선종: item.label } : {}), ...row.sourceRow }]
      : []);
  }));
  const records = datasets.flat();
  if (records.length === 0) throw new Error("내보낼 원본 마스터 데이터가 없습니다.");
  const headers = [...new Set(records.flatMap((record) => Object.keys(record)))];
  const rows = [headers, ...records.map((record) => headers.map((header) => record[header]))];
  const csv = "\uFEFF" + rows.map((row) => row.map(csvCell).join(",")).join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `master_data_${isAllVessels ? "all" : vessel.id}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function MarketDashboard({ user, onUserUpdated, onLogout, authError }: { user: AuthUser; onUserUpdated: (user: AuthUser) => void; onLogout: () => void; authError: string }) {
  const { language, setLanguage } = useI18n();
  const vesselId = useDashboardStore((state) => state.vesselId);
  const setVesselId = useDashboardStore((state) => state.setVesselId);
  const darkMode = useDashboardStore((state) => state.darkMode);
  const setDarkMode = useDashboardStore((state) => state.setDarkMode);
  const [showActionMenu, setShowActionMenu] = useState(false);
  const [showMoreMenu, setShowMoreMenu] = useState(false);
  const [showSettings, setShowSettings] = useState(false);
  const [showLanguageSettings, setShowLanguageSettings] = useState(false);
  const [showMyPage, setShowMyPage] = useState(false);
  const [showPlanComparison, setShowPlanComparison] = useState(false);
  const [csvExporting, setCsvExporting] = useState(false);
  const [csvExportError, setCsvExportError] = useState("");
  const [activePage, setActivePage] = useState<"dashboard" | "newsroom" | "about" | "details" | "ship-pulse">("dashboard");
  const [activeSection, setActiveSection] = useState<string>(dashboardSections[0].id);
  const isAllVessels = vesselId === "all";
  const currentPlanLevel = planLevel[user.subscriptionPlan ?? ""] ?? 0;
  const hasProfessionalAccess = currentPlanLevel >= planLevel.professional;
  const hasEnterpriseAccess = currentPlanLevel >= planLevel.enterprise;
  const vessel = isAllVessels ? ALL_VESSELS : VESSELS.find((item) => item.id === vesselId) ?? VESSELS[0];
  const selectVessel = (id: typeof vesselId) => {
    setVesselId(id);
    setActivePage("dashboard");
    if (id === "all" && activeSection === "freight-analysis") setActiveSection("order-forecast");
    if (id !== "all" && (activeSection === "monthly-heatmap" || activeSection === "custom-forecast")) setActiveSection("dashboard-overview");
  };
  const notebookForecast = !isAllVessels && isNotebookVessel(vessel.id) ? NOTEBOOK_FORECASTS[vessel.id] : undefined;
  const bulkMetrics = !isAllVessels && vessel.id === "bulk" ? getMetrics(vessel) : undefined;
  const handleCsvExport = async () => {
    setShowActionMenu(false);
    if (!hasProfessionalAccess) {
      setShowPlanComparison(true);
      return;
    }
    setCsvExporting(true);
    setCsvExportError("");
    try {
      await exportCsv(vessel, isAllVessels);
    } catch (error) {
      setCsvExportError(error instanceof Error ? error.message : "CSV 내보내기에 실패했습니다.");
    } finally {
      setCsvExporting(false);
    }
  };

  if (showPlanComparison) return <SubscriptionPage user={user} mode="change" onBack={() => setShowPlanComparison(false)} onSubscribed={(updatedUser) => { onUserUpdated(updatedUser); setVesselId("all"); setActivePage("dashboard"); setActiveSection("dashboard-overview"); setShowMyPage(false); setShowPlanComparison(false); window.scrollTo(0, 0); }} onLogout={onLogout} />;
  if (showMyPage) return <MyPage user={user} darkMode={darkMode} onBack={() => { setShowMyPage(false); if ((activeSection === "custom-forecast" && !hasEnterpriseAccess) || (activeSection !== "dashboard-overview" && !hasProfessionalAccess)) setActiveSection("dashboard-overview"); }} onChangePlan={() => setShowPlanComparison(true)} onUserUpdated={onUserUpdated} onLogout={onLogout} />;

  return (
    <div className={`market-dashboard min-h-screen bg-[#f5f7fb] text-slate-900 ${darkMode ? "dashboard-dark dark" : ""}`}>
      <header className="sticky top-0 z-20 border-b border-slate-200/90 bg-white/95 backdrop-blur">
        <div className="mx-auto flex w-full max-w-[1536px] flex-wrap items-center gap-x-6 gap-y-3 px-4 py-3 md:px-5 lg:flex-nowrap lg:py-0">
          <div className="flex shrink-0 items-center lg:h-[70px]"><AppBrand onClick={() => { setActivePage("dashboard"); setActiveSection("dashboard-overview"); window.scrollTo(0, 0); }} /></div>

          <div className="order-3 flex w-full min-w-0 flex-1 items-center lg:order-2">
            <div className="min-w-0 flex-1 overflow-x-auto lg:overflow-visible">
              <div className="relative flex w-max items-center lg:mx-auto">
                <nav aria-label="선종별 모니터 전환" className="flex gap-1">
                  <button
                    type="button" onClick={() => selectVessel("all")}
                    className={`whitespace-nowrap border-b-[3px] px-3 py-[18px] text-[13px] font-semibold transition-colors lg:px-4 ${isAllVessels ? "border-blue-600 text-[#173d70]" : "border-transparent text-slate-500 hover:text-slate-900"}`}
                    aria-current={isAllVessels ? "page" : undefined}
                  >종합 분석</button>
                  {VESSELS.map((item) => (
                    <button
                      type="button" key={item.id} onClick={() => selectVessel(item.id)}
                      className={`whitespace-nowrap border-b-[3px] px-3 py-[18px] text-[13px] font-semibold transition-colors lg:px-4 ${vesselId === item.id ? "border-blue-600 text-[#173d70]" : "border-transparent text-slate-500 hover:text-slate-900"}`}
                      aria-current={vesselId === item.id ? "page" : undefined}
                    >{item.label}</button>
                  ))}
                </nav>
                <nav aria-label="보조 콘텐츠" className="relative ml-8 shrink-0 lg:absolute lg:top-1/2 lg:left-full lg:-translate-y-1/2" onBlur={(event) => {
                  if (!event.currentTarget.contains(event.relatedTarget as Node)) setShowMoreMenu(false);
                }}>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    aria-expanded={showMoreMenu}
                    aria-controls="dashboard-more-menu"
                    onClick={() => setShowMoreMenu((current) => !current)}
                    className={`gap-1.5 shadow-sm ${activePage !== "dashboard" ? "border-blue-200 bg-blue-50 text-blue-700" : showMoreMenu ? "border-slate-300 bg-slate-200 text-slate-800 dark:border-slate-600 dark:bg-slate-700 dark:text-slate-100" : "border-slate-300 bg-slate-100 text-slate-700 hover:bg-slate-200 dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 dark:hover:bg-slate-700"}`}
                  >
                    더보기
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showMoreMenu ? "rotate-180" : ""}`} />
                  </Button>
                  {showMoreMenu && (
                    <div id="dashboard-more-menu" className="fixed top-32 right-4 z-30 w-56 rounded-xl border border-slate-200 bg-white p-1.5 shadow-xl lg:absolute lg:top-12 lg:-right-20" onKeyDown={(event) => {
                      if (event.key === "Escape") setShowMoreMenu(false);
                    }}>
                      {([
                        { page: "ship-pulse" as const, label: "ShipPulse 지표 비교", icon: BarChart3, enterpriseOnly: true },
                        { page: "newsroom" as const, label: "뉴스룸", icon: Newspaper },
                        { page: "details" as const, label: "Details", icon: FileText },
                        { page: "about" as const, label: "About Us", icon: Info },
                      ]).map(({ page, label, icon: Icon, enterpriseOnly = false }) => {
                        const locked = enterpriseOnly && !hasEnterpriseAccess;
                        return (
                        <button
                          key={page}
                          type="button"
                          aria-current={activePage === page ? "page" : undefined}
                          aria-label={locked ? `${label} · Enterprise 플랜 필요` : label}
                          className={`flex w-full items-center gap-2.5 rounded-lg px-3 py-2.5 text-left text-sm font-semibold transition-colors ${activePage === page ? "bg-blue-50 text-blue-700" : "text-slate-600 hover:bg-slate-100 hover:text-slate-900"}`}
                          onClick={() => {
                            if (locked) {
                              setShowMoreMenu(false);
                              setShowPlanComparison(true);
                              return;
                            }
                            setActivePage(page);
                            setShowMoreMenu(false);
                            window.scrollTo(0, 0);
                          }}
                        >
                          <Icon className="h-4 w-4" />
                          {page === "ship-pulse" ? <span className="leading-5"><span className="block">ShipPulse</span><span className="block">지표 비교</span></span> : label}
                          {locked && <Lock className="ml-auto h-3.5 w-3.5 text-slate-400" />}
                        </button>
                        );
                      })}
                    </div>
                  )}
                </nav>
              </div>
            </div>
            <div className="hidden w-[85px] shrink-0 lg:block" aria-hidden="true" />
          </div>

          <div className="order-2 ml-auto flex shrink-0 items-center gap-2 lg:order-3">
            <span className="hidden max-w-32 truncate text-xs font-semibold text-slate-700 sm:inline" title={user.email ?? user.displayName}>{user.displayName}님</span>
            <div className="relative">
              <Button
                variant="outline"
                size="sm"
                className="gap-2 border-slate-200 text-slate-600"
                aria-expanded={showActionMenu}
                aria-controls="dashboard-action-menu"
                onClick={() => {
                  if (showActionMenu) {
                    setShowSettings(false);
                    setShowLanguageSettings(false);
                  }
                  setShowActionMenu(!showActionMenu);
                }}
              >
                <Settings2 className="h-4 w-4" />메뉴
                <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showActionMenu ? "rotate-180" : ""}`} />
              </Button>
              {showActionMenu && (
                <div
                  id="dashboard-action-menu"
                  aria-label="대시보드 메뉴"
                  className="absolute top-12 right-0 z-30 w-[260px] rounded-xl border border-slate-200 bg-white p-2 shadow-xl"
                  onKeyDown={(event) => {
                    if (event.key === "Escape") {
                      setShowActionMenu(false);
                      setShowSettings(false);
                      setShowLanguageSettings(false);
                    }
                  }}
                >
                  <div className="flex items-center justify-between px-2 py-1.5">
                    <span className="text-xs font-semibold text-slate-500">빠른 메뉴</span>
                    <button type="button" aria-label="메뉴 닫기" className="rounded-md p-1 text-slate-400 hover:bg-slate-100" onClick={() => { setShowActionMenu(false); setShowSettings(false); setShowLanguageSettings(false); }}><X size={15} /></button>
                  </div>
                  <button type="button" disabled={csvExporting} className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100 disabled:cursor-wait disabled:opacity-60" onClick={handleCsvExport}>
                    <Download className="h-4 w-4 text-slate-500" />{csvExporting ? "CSV 준비 중" : "CSV 내보내기"}{!hasProfessionalAccess && <Lock className="ml-auto h-3.5 w-3.5 text-slate-400" />}
                  </button>
                  <button type="button" aria-expanded={showSettings} aria-controls="dashboard-display-settings" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100" onClick={() => { setShowSettings(!showSettings); setShowLanguageSettings(false); }}>
                    <Settings2 className="h-4 w-4 text-slate-500" />화면 설정
                    <ChevronDown className={`ml-auto h-3.5 w-3.5 transition-transform ${showSettings ? "rotate-180" : ""}`} />
                  </button>
                  {showSettings && (
                    <div id="dashboard-display-settings" className="mx-2 mb-1 rounded-lg bg-slate-50 px-3 py-2.5">
                      <button type="button" onClick={() => setDarkMode(!darkMode)} aria-pressed={darkMode} className="flex w-full items-center justify-between text-left text-xs text-slate-600">
                        <span className="flex items-center gap-2"><Moon className="h-4 w-4" />다크 테마</span>
                        <span className={`flex h-5 w-9 items-center rounded-full px-1 transition ${darkMode ? "bg-blue-600" : "bg-slate-200"}`}><i className={`theme-switch-knob h-3 w-3 rounded-full bg-white transition ${darkMode ? "translate-x-4" : ""}`} /></span>
                      </button>
                    </div>
                  )}
                  <button type="button" aria-expanded={showLanguageSettings} aria-controls="dashboard-language-settings" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100" onClick={() => { setShowLanguageSettings(!showLanguageSettings); setShowSettings(false); }}>
                    <Globe2 className="h-4 w-4 text-slate-500" />언어 설정
                    <span className="ml-auto text-[11px] font-medium text-slate-400" data-no-translate>{language === "ko" ? "한국어" : "English"}</span>
                    <ChevronDown className={`h-3.5 w-3.5 transition-transform ${showLanguageSettings ? "rotate-180" : ""}`} />
                  </button>
                  {showLanguageSettings && (
                    <div id="dashboard-language-settings" className="mx-2 mb-1 grid grid-cols-2 gap-1 rounded-lg bg-slate-50 p-1.5" data-no-translate>
                      <button type="button" lang="ko" aria-pressed={language === "ko"} onClick={() => setLanguage("ko")} className={`rounded-md px-3 py-2 text-center text-xs font-semibold transition-colors ${language === "ko" ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:bg-white/70 hover:text-slate-800"}`}>한국어</button>
                      <button type="button" lang="en" aria-pressed={language === "en"} onClick={() => setLanguage("en")} className={`rounded-md px-3 py-2 text-center text-xs font-semibold transition-colors ${language === "en" ? "bg-white text-blue-700 shadow-sm" : "text-slate-500 hover:bg-white/70 hover:text-slate-800"}`}>English</button>
                    </div>
                  )}
                  <button type="button" className="flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm text-slate-700 hover:bg-slate-100" onClick={() => { setShowActionMenu(false); setShowMyPage(true); }}>
                    <UserRound className="h-4 w-4 text-slate-500" />마이페이지
                  </button>
                </div>
              )}
            </div>
            <Button variant="outline" size="sm" className="border-slate-200 text-slate-600" onClick={onLogout}>로그아웃</Button>
          </div>
        </div>
      </header>

      {authError && <div role="alert" className="mx-auto max-w-[1360px] px-4 pt-3 text-sm text-red-700 md:px-8">{authError}</div>}
      {csvExportError && <div role="alert" className="mx-auto max-w-[1360px] px-4 pt-3 text-sm text-red-700 md:px-8">{csvExportError}</div>}

      {activePage === "ship-pulse" ? <ShipPulseComparison /> : activePage === "newsroom" ? <Newsroom /> : activePage === "about" ? <AboutPage /> : activePage === "details" ? <DetailsPage onExplore={() => { setActivePage("dashboard"); setActiveSection("dashboard-overview"); window.scrollTo(0, 0); }} onOpenNewsroom={() => { setActivePage("newsroom"); window.scrollTo(0, 0); }} /> : <main className={`dashboard-compact dashboard-layout mx-auto max-w-[1536px] px-3 pt-3 md:px-3 ${activeSection === "dashboard-overview" ? "pb-3" : "pb-0"}`}>
        <aside className={`${panelClass} dashboard-sidebar p-3`} aria-label="대시보드 섹션 이동">
          <div className="dashboard-sidebar-heading">
            <span>분석 대시보드</span>
          </div>
          <nav className="dashboard-section-nav" aria-label="대시보드 섹션">
            {dashboardSections.filter(({ id }) => !(isAllVessels && id === "freight-analysis") && (isAllVessels || (id !== "monthly-heatmap" && id !== "custom-forecast"))).map(({ id, label, icon: Icon }) => {
              const locked = id === "custom-forecast" ? !hasEnterpriseAccess : id !== "dashboard-overview" && !hasProfessionalAccess;
              return <button
                key={id}
                type="button"
                aria-current={activeSection === id ? "page" : undefined}
                aria-label={locked ? `${label} · 상위 플랜 필요` : label}
                className={`dashboard-section-button ${activeSection === id ? "is-active" : ""}${locked ? " is-locked" : ""}`}
                onClick={() => {
                  if (locked) {
                    setShowPlanComparison(true);
                    return;
                  }
                  setActiveSection(id);
                  window.scrollTo(0, 0);
                }}
              >
                <span className="dashboard-nav-icon"><Icon className="h-4 w-4 shrink-0" /></span>
                <span className="dashboard-nav-label">{label}</span>
                {locked && <Lock className="ml-auto h-3.5 w-3.5 shrink-0" />}
              </button>
            })}
          </nav>
          <div className="dashboard-sidebar-context">
            <span>CURRENT PLAN</span>
            <strong>{user.subscriptionPlan ? planNames[user.subscriptionPlan] ?? user.subscriptionPlan : "선택된 플랜 없음"}</strong>
          </div>
          <a className="dashboard-sidebar-promo" href="https://www.joongang.co.kr/article/25183169" target="_blank" rel="noopener noreferrer" aria-label="데이터로 보는 조선업 다음 10년 칼럼 열기"><strong>데이터로 보는<br />조선업 다음 10년</strong><span>더 넓은 기회를 만나보세요.</span><i><ChevronDown className="-rotate-90" size={16} /></i></a>
        </aside>
        <div className={`dashboard-main-content ${activeSection === "order-forecast" || activeSection === "custom-forecast" || activeSection === "freight-analysis" ? "is-analysis-view" : ""}`}>
        {activeSection === "dashboard-overview" && (isAllVessels ? <DashboardOverview darkMode={darkMode} /> : isNotebookVessel(vessel.id) ? <DashboardOverview key={vessel.id} vesselId={vessel.id} darkMode={darkMode} /> : <section id="dashboard-overview" className="overview-screen dashboard-view dashboard-section-target">
        <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
          <LayoutDashboard className="h-3.5 w-3.5" />시장 모니터링 <span className="text-slate-300">/</span> <span className="font-medium text-slate-700">{vessel.label}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-end justify-between gap-4">
          <div>
            <div className="flex flex-wrap items-center gap-2.5">
              <h1 className="text-[26px] font-bold tracking-[-0.05em] text-slate-900 md:text-[31px]">{vessel.label} 수주 시장</h1>
              {bulkMetrics
                ? <Badge variant="outline" className="border-slate-200 bg-slate-50 px-2.5 py-1 text-slate-600">기존 데이터 · 노트북 미적용</Badge>
                : <Badge variant="outline" className="border-blue-200 bg-blue-50 px-2.5 py-1 text-blue-700">{isAllVessels ? "실행 노트북 5종 비교" : "실행 노트북 결과"}</Badge>}
            </div>
            <p className="mt-2 text-sm text-slate-500">{bulkMetrics ? "벌크선 수주 변화와 기존 시장 지표 모니터링" : "검증된 다섯 선종 모델의 다음 분기 수주 신호와 판단 근거"}</p>
          </div>
          <div className="flex items-center gap-2 text-xs font-medium text-slate-500"><span className="h-2 w-2 rounded-full bg-emerald-500" />{bulkMetrics ? "2026년 9월 기준" : dateLabel}<ChevronDown className="h-4 w-4" /></div>
        </div>

        <section className="mt-3 overflow-hidden rounded-2xl bg-[#142f55] px-5 py-3 text-white shadow-[0_8px_22px_rgba(22,49,85,0.10)] md:px-7">
          <div className="flex flex-wrap items-start gap-6 md:items-center md:justify-between">
            <div className="max-w-3xl">
              <div className="flex items-center gap-2 text-[11px] font-bold tracking-[0.16em] text-blue-200"><Activity className="h-4 w-4" /> MARKET BRIEF</div>
              <h2 className="mt-2.5 text-lg font-semibold leading-relaxed tracking-[-0.025em] md:text-[21px]">
                {notebookForecast ? <>
                  {notebookForecast.vesselName} 4분기 누적 전망은 3분기 대비 <span className={notebookForecast.quarterChange >= 0 ? "text-sky-300" : "text-amber-300"}>{notebookForecast.quarterChange > 0 ? "+" : ""}{notebookForecast.quarterChange.toFixed(1)}%</span>.
                  <br className="hidden md:block" /> {notebookForecast.signal}
                </> : bulkMetrics ? <>
                  벌크선 1~9월 누적 발주량은 전년 동기 대비 <span className={bulkMetrics.yoy >= 0 ? "text-sky-300" : "text-amber-300"}>{Math.abs(bulkMetrics.yoy).toFixed(1)}% {bulkMetrics.yoy >= 0 ? "증가" : "감소"}</span>.
                  <br className="hidden md:block" /> 최근 3개월은 직전 3개월 대비 {Math.abs(bulkMetrics.quarterChange).toFixed(1)}% {bulkMetrics.quarterChange >= 0 ? "증가" : "감소"}했습니다.
                </> : <>
                  4개 선종 중 <span className="text-sky-300">3개 선종은 증가</span>, 가스 운반선은 <span className="text-amber-300">-24.6% 둔화</span> 신호입니다.
                  <br className="hidden md:block" /> 서로 다른 용량 단위는 합산하지 않고 분기 방향과 고점 시점을 비교합니다.
                </>}
              </h2>
              <p className="mt-2 text-xs text-blue-100/70">{bulkMetrics ? "누적 발주량과 최근 3개월의 변화 폭을 함께 보고 영업·생산 대응 시점을 점검하세요." : "선종별 고점과 연말 방향을 비교해 영업 우선순위와 생산 계획을 점검하세요."}</p>
            </div>
          </div>
        </section>

        <div className="dashboard-block mt-5 grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {notebookForecast ? <>
            <MetricCard title="3분기 누적 전망" value={compactCapacity(notebookForecast.q3, notebookForecast.unit, language)} icon={Ship} helper="2026년 7~9월 모델 전망 합계" />
            <MetricCard title="4분기 누적 전망" value={compactCapacity(notebookForecast.q4, notebookForecast.unit, language)} icon={TrendingUp} helper="2026년 10~12월 모델 전망 합계" />
            <MetricCard title="분기 전망 변화" value={`${notebookForecast.quarterChange > 0 ? "+" : ""}${notebookForecast.quarterChange.toFixed(1)}%`} change={notebookForecast.quarterChange} icon={TrendingDown} helper="4분기 전망 vs 3분기 전망" />
            <MetricCard title="Test 상대오차" value={`${notebookForecast.testRelativeError.toFixed(1)}%`} icon={BarChart3} helper={`고점 시차 절대오차 ${notebookForecast.peakTimingError.toFixed(2)}개월`} />
          </> : bulkMetrics ? <>
            <MetricCard title="올해 누적 발주량" value={`${formatted(bulkMetrics.yearTotal)} 만 CGT`} icon={Ship} helper="2026년 1~9월 누적" />
            <MetricCard title="전년 동기 대비" value={signedPct(bulkMetrics.yoy)} change={bulkMetrics.yoy} icon={TrendingUp} helper="2025년 1~9월 대비" />
            <MetricCard title="최근 3개월 변화" value={signedPct(bulkMetrics.quarterChange)} change={bulkMetrics.quarterChange} icon={TrendingDown} helper="2026년 7~9월 vs 4~6월" />
            <MetricCard title="최고 발주 월" value={bulkMetrics.peakMonth} icon={BarChart3} helper={`${formatted(bulkMetrics.peakValue)}만 CGT`} />
          </> : <>
            <MetricCard title="분석 선종" value="4개" icon={Ship} helper="벌크선을 제외한 실행 노트북" />
            <MetricCard title="상승 신호" value="3개" change={1} icon={TrendingUp} helper="유조선 · 컨테이너선 · 케미컬 탱커" />
            <MetricCard title="둔화 신호" value="1개" change={-1} icon={TrendingDown} helper="가스 운반선 · 전분기 대비 -24.6%" />
            <MetricCard title="예측 구간" value="6개월" icon={BarChart3} helper="2026년 7~12월 월별 전망" />
          </>}
        </div>

        <div className="dashboard-block mt-4">
          {bulkMetrics ? <BulkInsightPanel vessel={vessel} /> : <NotebookInsightPanel forecast={notebookForecast} />}
        </div>
        </section>)}
        {hasProfessionalAccess && activeSection === "order-forecast" && <div id="order-forecast" className="dashboard-block analysis-screen dashboard-view dashboard-section-target">
          {!isAllVessels
            ? isNotebookVessel(vessel.id)
              ? <VesselOrderForecast darkMode={darkMode} vesselId={vessel.id} />
              : <MarketAnalysis vessel={vessel} view="forecast" />
            : <PortfolioOrderForecast darkMode={darkMode} />}
        </div>}
        {hasEnterpriseAccess && isAllVessels && activeSection === "custom-forecast" && <div id="custom-forecast" className="dashboard-block analysis-screen dashboard-view dashboard-section-target">
          <CustomForecast />
        </div>}
        {hasProfessionalAccess && activeSection === "freight-analysis" && !isAllVessels && <div id="freight-analysis" className="dashboard-block analysis-screen dashboard-view dashboard-section-target">
          <MarketAnalysis vessel={vessel} view="freight" />
        </div>}
        {hasProfessionalAccess && isAllVessels && activeSection === "monthly-heatmap" && <div className="dashboard-block dashboard-view grid grid-cols-1 items-stretch gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
          <Heatmap />
          <ComparisonBars />
        </div>}
        </div>
      </main>}
    </div>
  );
}
