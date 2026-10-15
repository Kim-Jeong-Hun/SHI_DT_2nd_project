import { useEffect, useMemo, useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import type { EChartsType } from "echarts";
import { AlertCircle, BookOpen, CheckCircle2, DatabaseZap, Download, LoaderCircle, Play, RotateCcw, SlidersHorizontal } from "lucide-react";
import "../../styles/custom-forecast.css";
import DataDictionary from "./DataDictionary";

type VesselId = "container" | "tanker" | "bulk" | "gas" | "chemical";
interface InputSource {
  id: string; label: string; unit: string; features: string[];
  latestMonth: string; latestValue: number; maxLag: number; observations: Record<string, number>;
}
interface ScenarioConfig {
  vesselId: VesselId; vessel: string; unit: string; source: string;
  model: string; strategy: string; leadMonths: number; featureCount: number;
  features: string[]; inputSources: InputSource[]; defaultObservationMonth: string;
}
interface ScenarioResult {
  vessel: string; unit: string; model: string; strategy: string; leadMonths: number;
  actuals: { month: string; value: number }[];
  forecasts: { originMonth: string; month: string; baseline: number; scenario: number; change: number; affected: boolean }[];
  affectedForecasts: { originMonth: string; month: string; baseline: number; scenario: number; change: number; affected: boolean }[];
  assumption: string; unchanged: boolean;
}

const vessels: { id: VesselId; label: string; ready: boolean }[] = [
  { id: "container", label: "컨테이너선", ready: true }, { id: "tanker", label: "유조선", ready: true },
  { id: "gas", label: "가스 운반선", ready: true }, { id: "chemical", label: "케미컬 탱커", ready: true },
  { id: "bulk", label: "벌크선", ready: true },
];
const pipelineByVessel: Record<VesselId, Pick<ScenarioConfig, "vessel" | "unit" | "model" | "strategy" | "leadMonths" | "featureCount">> = {
  container: { vessel: "컨테이너선", unit: "TEU", model: "Tweedie Regression + XGBoost 동일가중 앙상블", strategy: "Adaptive 24·36·48·60개월 · Uniform · VIF 10", leadMonths: 6, featureCount: 10 },
  tanker: { vessel: "유조선", unit: "DWT", model: "Quantile Regression", strategy: "Sliding 60개월 · Uniform · VIF 10", leadMonths: 6, featureCount: 20 },
  bulk: { vessel: "벌크선", unit: "DWT", model: "PLS Regression", strategy: "Sliding 24개월 · Uniform · VIF 10", leadMonths: 6, featureCount: 14 },
  gas: { vessel: "가스 운반선", unit: "CBM", model: "Huber Regression", strategy: "Sliding 36개월 · Uniform · VIF 10", leadMonths: 6, featureCount: 6 },
  chemical: { vessel: "케미컬 탱커", unit: "DWT", model: "XGBoost", strategy: "Adaptive 24·36·48개월 · Uniform · VIF 10", leadMonths: 6, featureCount: 16 },
};
const formatted = (value: number, digits = 1) => value.toLocaleString("ko-KR", { maximumFractionDigits: digits });
const escapeHtml = (value: unknown) => String(value ?? "").replace(/[&<>"']/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
})[character] ?? character);

function reportChart(result: ScenarioResult) {
  const width = 920;
  const height = 340;
  const padding = { top: 32, right: 34, bottom: 54, left: 86 };
  const months = [...new Set([...result.actuals.map((item) => item.month), ...result.forecasts.map((item) => item.month)])].sort();
  const actualByMonth = new Map(result.actuals.map((item) => [item.month, item.value]));
  const forecastByMonth = new Map(result.forecasts.map((item) => [item.month, item]));
  const lastActual = result.actuals.at(-1);
  const values = [
    ...result.actuals.map((item) => item.value),
    ...result.forecasts.flatMap((item) => [item.baseline, item.scenario]),
  ];
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const margin = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.04, 1);
  const min = Math.max(0, rawMin - margin);
  const max = rawMax + margin;
  const plotWidth = width - padding.left - padding.right;
  const plotHeight = height - padding.top - padding.bottom;
  const x = (index: number) => padding.left + (months.length === 1 ? plotWidth / 2 : index / (months.length - 1) * plotWidth);
  const y = (value: number) => padding.top + (max - value) / Math.max(max - min, 1) * plotHeight;
  const pathFor = (valueAt: (month: string) => number | undefined) => {
    let drawing = false;
    return months.map((item, index) => {
      const value = valueAt(item);
      if (value === undefined) { drawing = false; return ""; }
      const command = drawing ? "L" : "M";
      drawing = true;
      return `${command}${x(index).toFixed(1)},${y(value).toFixed(1)}`;
    }).filter(Boolean).join(" ");
  };
  const forecastValue = (month: string, key: "baseline" | "scenario") => forecastByMonth.get(month)?.[key]
    ?? (month === lastActual?.month ? lastActual.value : undefined);
  const grid = Array.from({ length: 5 }, (_, index) => {
    const ratio = index / 4;
    const lineY = padding.top + ratio * plotHeight;
    const label = max - ratio * (max - min);
    return `<line x1="${padding.left}" y1="${lineY}" x2="${width - padding.right}" y2="${lineY}" stroke="#e2e8f0" stroke-dasharray="4 5"/><text x="${padding.left - 12}" y="${lineY + 4}" text-anchor="end">${escapeHtml(formatted(label, 0))}</text>`;
  }).join("");
  const labels = months.map((item, index) => `<text x="${x(index)}" y="${height - 22}" text-anchor="middle">${escapeHtml(item)}</text>`).join("");
  const affected = new Set(result.affectedForecasts.map((item) => item.month));
  const points = result.forecasts.map((item) => {
    const index = months.indexOf(item.month);
    return `<circle cx="${x(index)}" cy="${y(item.scenario)}" r="${affected.has(item.month) ? 5 : 3.5}" fill="#176f9b" stroke="#fff" stroke-width="2"/>`;
  }).join("");

  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(result.vessel)} 기준 전망과 수정 전망 비교" xmlns="http://www.w3.org/2000/svg">
    <style>text{fill:#64748b;font:11px Arial,sans-serif}</style>
    ${grid}${labels}
    <path d="${pathFor((item) => actualByMonth.get(item))}" fill="none" stroke="#0f6f98" stroke-width="3"/>
    <path d="${pathFor((item) => forecastValue(item, "baseline"))}" fill="none" stroke="#94a3b8" stroke-width="2.5" stroke-dasharray="8 6"/>
    <path d="${pathFor((item) => forecastValue(item, "scenario"))}" fill="none" stroke="#176f9b" stroke-width="3.5"/>
    ${points}
    <text x="${padding.left}" y="18" fill="#475569">수주용량 (${escapeHtml(result.unit)})</text>
  </svg>`;
}

function createForecastReport(result: ScenarioResult, config: ScenarioConfig, observationMonth: string, inputs: Record<string, string>) {
  const primary = result.affectedForecasts.reduce<ScenarioResult["forecasts"][number] | undefined>((best, item) => !best || Math.abs(item.change) > Math.abs(best.change) ? item : best, undefined);
  const primaryChange = primary?.change ?? 0;
  const changeRate = primary?.baseline ? primaryChange / primary.baseline * 100 : 0;
  const directionClass = primaryChange > 0 ? "up" : primaryChange < 0 ? "down" : "flat";
  const generatedAt = new Date().toLocaleString("ko-KR", { dateStyle: "long", timeStyle: "short" });
  const forecastRows = result.forecasts.map((item) => `<tr><td>${escapeHtml(item.month)}</td><td>${escapeHtml(formatted(item.baseline))} ${escapeHtml(result.unit)}</td><td>${escapeHtml(formatted(item.scenario))} ${escapeHtml(result.unit)}</td><td class="${item.change > 0 ? "up" : item.change < 0 ? "down" : "flat"}">${item.change > 0 ? "+" : ""}${escapeHtml(formatted(item.change))}</td><td>${item.affected ? "반영" : "변동 없음"}</td></tr>`).join("");
  const inputRows = config.inputSources.map((item) => {
    const known = item.observations[observationMonth] as number | undefined;
    const supplied = inputs[item.id];
    const value = known ?? (supplied === undefined || supplied.trim() === "" ? "-" : Number(supplied));
    return `<tr><td>${escapeHtml(item.label)}</td><td>${escapeHtml(value === "-" ? value : formatted(value))}</td><td>${escapeHtml(item.unit)}</td><td>${known === undefined ? "사용자 입력" : "기존 데이터"}</td></tr>`;
  }).join("");

  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>SHIPULSE · ${escapeHtml(result.vessel)} 사용자 지정 예측</title>
<style>
*{box-sizing:border-box}body{margin:0;background:#f4f7fb;color:#17243a;font-family:Arial,"Noto Sans KR",sans-serif}main{width:min(1100px,calc(100% - 32px));margin:36px auto}.report{overflow:hidden;border:1px solid #dce3ea;border-radius:20px;background:#fff;box-shadow:0 18px 50px #17243a12}.hero{padding:34px 38px;background:#102b4e;color:#fff}.brand{font-size:12px;font-weight:800;letter-spacing:.18em;color:#7dd3fc}.hero h1{margin:12px 0 6px;font-size:30px}.hero p{margin:0;color:#bfdbfe}.meta,.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:1px;background:#e2e8f0}.meta div,.metrics div{padding:18px 20px;background:#fff}.meta span,.metrics span{display:block;color:#64748b;font-size:11px}.meta b,.metrics b{display:block;margin-top:7px;font-size:15px}.metrics b{font-size:21px}.up{color:#dc2626!important}.down{color:#2563eb!important}.flat{color:#64748b!important}.section{padding:28px 38px;border-top:1px solid #e8edf2}.section h2{margin:0 0 16px;font-size:18px}.legend{display:flex;gap:18px;margin:0 0 12px;color:#64748b;font-size:12px}.legend i{display:inline-block;width:18px;height:3px;margin-right:6px;vertical-align:middle}.chart{width:100%;overflow:auto;border:1px solid #edf1f5;border-radius:14px;padding:10px}.chart svg{display:block;min-width:760px;width:100%;height:auto}table{width:100%;border-collapse:collapse;font-size:12px}th,td{padding:12px 10px;border-bottom:1px solid #e8edf2;text-align:left}th{background:#f8fafc;color:#64748b}.note{padding:18px 38px;background:#f8fafc;color:#64748b;font-size:11px;line-height:1.7}@media(max-width:720px){.meta,.metrics{grid-template-columns:repeat(2,1fr)}.hero,.section{padding:24px}.hero h1{font-size:24px}}@media print{body{background:#fff}main{width:100%;margin:0}.report{border:0;box-shadow:none}.section{break-inside:avoid}}
</style></head><body><main><article class="report">
<header class="hero"><div class="brand">SHIPULSE · CUSTOM FORECAST</div><h1>${escapeHtml(result.vessel)} 사용자 지정 예측 결과</h1><p>${escapeHtml(observationMonth)} 시장 정보를 반영한 수주용량 전망 보고서</p></header>
<section class="meta"><div><span>저장 시각</span><b>${escapeHtml(generatedAt)}</b></div><div><span>예측 단위</span><b>${escapeHtml(result.unit)}</b></div><div><span>모델</span><b>${escapeHtml(result.model)}</b></div><div><span>반영 규칙</span><b>관측월 → D+${escapeHtml(result.leadMonths)}</b></div></section>
<section class="metrics"><div><span>전망 변화</span><b class="${directionClass}">${primary?.change && primary.change > 0 ? "+" : ""}${escapeHtml(formatted(primary?.change ?? 0))} · ${changeRate > 0 ? "+" : ""}${escapeHtml(changeRate.toFixed(1))}%</b></div><div><span>기준 전망</span><b>${escapeHtml(formatted(primary?.baseline ?? 0))} ${escapeHtml(result.unit)}</b></div><div><span>수정 전망</span><b class="${directionClass}">${escapeHtml(formatted(primary?.scenario ?? 0))} ${escapeHtml(result.unit)}</b></div><div><span>가장 큰 변경점</span><b>${escapeHtml(primary?.month ?? "-")}</b></div></section>
<section class="section"><h2>전망 비교</h2><div class="legend"><span><i style="background:#0f6f98"></i>실제 데이터</span><span><i style="background:#94a3b8"></i>기준 전망</span><span><i style="background:#176f9b"></i>새 정보 반영 전망</span></div><div class="chart">${reportChart(result)}</div></section>
<section class="section"><h2>월별 예측 결과</h2><table><thead><tr><th>예측월</th><th>기준 전망</th><th>수정 전망</th><th>변화량</th><th>반영 여부</th></tr></thead><tbody>${forecastRows}</tbody></table></section>
<section class="section"><h2>${escapeHtml(observationMonth)} 입력 정보</h2><table><thead><tr><th>지표</th><th>값</th><th>단위</th><th>출처</th></tr></thead><tbody>${inputRows}</tbody></table></section>
<section class="section"><h2>분석 조건</h2><p>${escapeHtml(result.assumption)}</p><p>${escapeHtml(result.strategy)}</p></section>
<footer class="note">본 결과는 과거 데이터와 검증된 모델을 기반으로 한 의사결정 보조 정보입니다. 계약, 투자, 생산 또는 조달 판단에는 최신 시장 정보와 현업 검토를 함께 반영해야 합니다.</footer>
</article></main></body></html>`;
}

function ForecastWorkspace() {
  const [vesselId, setVesselId] = useState<VesselId>("container");
  const [config, setConfig] = useState<ScenarioConfig | null>(null);
  const [month, setMonth] = useState("");
  const [values, setValues] = useState<Record<string, string>>({});
  const [result, setResult] = useState<ScenarioResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true); setConfig(null); setResult(null); setError("");
    fetch(`/api/v1/custom-forecast/config?vesselId=${vesselId}`, { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        const data = await response.json();
        if (!response.ok) throw new Error(data.error || "최종 모델 정보를 불러오지 못했습니다.");
        return data as ScenarioConfig;
      })
      .then((data) => {
        if (!Array.isArray(data.inputSources)) throw new Error("시나리오 예측 서버를 다시 시작해 주세요.");
        setConfig(data);
        setMonth(data.defaultObservationMonth);
        setValues({});
      })
      .catch((caught: Error) => { if (caught.name !== "AbortError") setError(caught.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [vesselId]);

  const knownSources = config?.inputSources.filter((item) => item.observations[month] !== undefined) ?? [];
  const missingSources = config?.inputSources.filter((item) => item.observations[month] === undefined) ?? [];
  const completedInputs = missingSources.filter((item) => typeof values[item.id] === "string" && values[item.id].trim() !== "").length;
  const inputComplete = missingSources.length > 0 && completedInputs === missingSources.length;
  const pipeline = config ?? pipelineByVessel[vesselId];
  const changeVessel = (nextVesselId: VesselId) => {
    setLoading(true); setConfig(null); setMonth(""); setValues({}); setResult(null); setError("");
    setVesselId(nextVesselId);
  };
  const reset = () => {
    if (!config) return;
    setMonth(config.defaultObservationMonth); setValues({}); setResult(null); setError("");
  };
  const runForecast = async () => {
    if (!config || !month || !inputComplete) return;
    setRunning(true); setResult(null); setError("");
    try {
      const response = await fetch("/api/v1/custom-forecast/run", {
        method: "POST", credentials: "same-origin", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ vesselId, observationMonth: month, values: Object.fromEntries(missingSources.map((item) => [item.id, Number(values[item.id])])) }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.error || "시나리오 예측에 실패했습니다.");
      setResult(data);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "시나리오 예측에 실패했습니다.");
    } finally { setRunning(false); }
  };

  const chartOption = useMemo(() => {
    if (!result) return null;
    const affected = new Set(result.affectedForecasts.map((item) => item.month));
    const months = [...new Set([...result.actuals.map((item) => item.month), ...result.forecasts.map((item) => item.month)])].sort();
    const actualByMonth = new Map(result.actuals.map((item) => [item.month, item.value]));
    const forecastByMonth = new Map(result.forecasts.map((item) => [item.month, item]));
    const lastActual = result.actuals.at(-1);
    const firstForecastMonth = result.forecasts[0]?.month;
    const revisionChange = result.affectedForecasts.at(-1)?.change ?? 0;
    const revisionColor = revisionChange > 0 ? "#dc2626" : revisionChange < 0 ? "#2563eb" : "#64748b";
    const revisionArea = revisionChange > 0 ? "rgba(220,38,38,.08)" : revisionChange < 0 ? "rgba(37,99,235,.08)" : "rgba(100,116,139,.07)";
    return {
      animationDuration: 900,
      grid: { left: 78, right: 34, top: 64, bottom: 56 },
      legend: { top: 15, data: ["실제 데이터", "기준 전망", "새 정보 반영 전망"] },
      tooltip: { show: true, showContent: true, trigger: "axis", triggerOn: "mousemove", alwaysShowContent: false, hideDelay: 0, enterable: false, confine: true, axisPointer: { type: "line", snap: false, triggerTooltip: true, lineStyle: { color: "#94a3b8", type: "dashed" } }, valueFormatter: (item: number | null | undefined) => item == null ? "-" : `${formatted(item)} ${result.unit}` },
      xAxis: { type: "category", boundaryGap: false, data: months, axisTick: { show: false }, axisLabel: { color: "#64748b" } },
      yAxis: { type: "value", name: result.unit, scale: true, axisLabel: { color: "#64748b" }, splitLine: { lineStyle: { color: "#e8edf2", type: "dashed" } } },
      series: [
        { name: "실제 데이터", type: "line", triggerEvent: "line", data: months.map((month) => actualByMonth.get(month) ?? null), showSymbol: false, connectNulls: false, lineStyle: { color: "#176f9b", width: 3 }, itemStyle: { color: "#176f9b" } },
        { name: "기준 전망", type: "line", triggerEvent: "line", data: months.map((month) => forecastByMonth.get(month)?.baseline ?? (month === lastActual?.month ? lastActual.value : null)), showSymbol: false, connectNulls: false, lineStyle: { color: "#94a3b8", width: 2, type: "dashed" }, itemStyle: { color: "#94a3b8" } },
        { name: "새 정보 반영 전망", type: "line", triggerEvent: "line", data: months.map((month) => forecastByMonth.get(month)?.scenario ?? (month === lastActual?.month ? lastActual.value : null)), connectNulls: false, symbol: "circle", symbolSize: (_value: unknown, params: { name: string }) => params.name === lastActual?.month ? 0 : affected.has(params.name) ? 9 : 5, lineStyle: { color: revisionColor, width: 3 }, itemStyle: { color: revisionColor }, areaStyle: { color: revisionArea }, markLine: firstForecastMonth ? { silent: true, symbol: ["none", "none"], lineStyle: { color: "#dc2626", width: 2, type: "dashed" }, label: { formatter: "예측 시작", color: "#dc2626", fontWeight: 700 }, data: [{ xAxis: firstForecastMonth }] } : undefined },
      ],
    };
  }, [result]);

  const chartEvents = useMemo(() => ({
    mousemove: (params: { seriesIndex?: number; seriesType?: string; dataIndex?: number; event?: { offsetX?: number } }, chart: EChartsType) => {
      if (params.seriesType !== "line" || params.dataIndex != null) return;
      const mouseX = params.event?.offsetX;
      const option = chart.getOption() as { xAxis?: { data?: string[] }[] };
      const months = option.xAxis?.[0]?.data ?? [];
      if (mouseX == null || months.length === 0) return;
      let nearest = 0;
      for (let index = 1; index < months.length; index++) {
        const pixel = chart.convertToPixel({ xAxisIndex: 0 }, months[index]) as number;
        const nearestPixel = chart.convertToPixel({ xAxisIndex: 0 }, months[nearest]) as number;
        if (Math.abs(pixel - mouseX) < Math.abs(nearestPixel - mouseX)) nearest = index;
      }
      chart.dispatchAction({ type: "showTip", seriesIndex: params.seriesIndex ?? 0, dataIndex: nearest });
    },
    globalout: (_params: unknown, chart: EChartsType) => chart.dispatchAction({ type: "hideTip" }),
  }), []);

  const primary = result?.affectedForecasts.reduce((best, item) => Math.abs(item.change) > Math.abs(best.change) ? item : best, result.affectedForecasts[0]);
  const changeRate = primary && primary.baseline ? primary.change / primary.baseline * 100 : 0;
  const changeClass = primary ? primary.change > 0 ? "is-up" : primary.change < 0 ? "is-down" : "is-flat" : "";
  const saveForecastResult = () => {
    if (!result || !config) return;
    const report = createForecastReport(result, config, month, values);
    const url = URL.createObjectURL(new Blob(["\uFEFF", report], { type: "text/html;charset=utf-8" }));
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `ship-signal_custom-forecast_${vesselId}_${month}_${new Date().toISOString().slice(0, 10)}.html`;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    window.setTimeout(() => URL.revokeObjectURL(url), 0);
  };

  return <section className="custom-forecast-page" aria-labelledby="custom-forecast-title">
    <header className="custom-forecast-header"><div><div className="custom-forecast-kicker"><DatabaseZap size={15} /> SCENARIO UPDATE</div><h1 id="custom-forecast-title">사용자 지정 예측</h1><p>선택한 월의 시장 정보가 완성되면, 검증이 끝난 최종 모델이 수주 전망을 다시 계산합니다.</p></div><span className="custom-forecast-status is-connected"><i /> 최종 모델 연결</span></header>
    <div className="custom-forecast-notice" role="status"><AlertCircle size={18} /><p><strong>한 달의 입력 정보가 모두 갖춰져야 전망을 업데이트할 수 있습니다.</strong><span>이미 확보한 값은 그대로 사용하고, 비어 있는 원천지표를 모두 입력한 뒤 시차 피처와 D+{config?.leadMonths ?? 6} 전망을 다시 계산합니다.</span></p></div>

    <div className="custom-forecast-layout custom-scenario-layout">
      <div className="custom-forecast-config">
        <section className="custom-config-card"><div className="custom-config-heading"><span>01</span><div className="custom-heading-title"><h2>선종 선택</h2><span className="custom-help-tip" tabIndex={0} aria-label="벌크선은 분석 노트북이 추가된 뒤 활성화됩니다.">!<span className="custom-help-copy" role="tooltip">벌크선은 분석 노트북이 추가된 뒤 활성화됩니다.</span></span></div></div>
          <label className="custom-field"><span>선종</span><select value={vesselId} onChange={(event) => changeVessel(event.target.value as VesselId)}>{vessels.map((item) => <option key={item.id} value={item.id} disabled={!item.ready}>{item.label}</option>)}</select></label>
        </section>

        <section className="custom-config-card"><div className="custom-config-heading"><span>02</span><div className="custom-heading-title"><h2>파이프라인</h2><span className="custom-help-tip" tabIndex={0} aria-label="사용자는 모델이나 피처 조합을 변경하지 않습니다.">!<span className="custom-help-copy" role="tooltip">사용자는 모델이나 피처 조합을 변경하지 않습니다.</span></span></div></div>
          <dl className="custom-pipeline-grid"><div><dt>최종 모델</dt><dd>{pipeline.model}</dd></div><div><dt>학습 전략</dt><dd>{pipeline.strategy}</dd></div><div><dt>예측 대상</dt><dd>수주용량 ({pipeline.unit})</dd></div><div><dt>확정 피처</dt><dd>{pipeline.featureCount}개 · D+{pipeline.leadMonths}</dd></div></dl>
        </section>
      </div>

      <div className="custom-input-column">
        <section className="custom-config-card"><div className="custom-config-heading"><span>03</span><div className="custom-heading-title"><h2>월별 입력 정보 완성</h2><span className="custom-help-tip" tabIndex={0} aria-label="선택한 월에 비어 있는 모델 원천지표를 모두 입력하세요.">!<span className="custom-help-copy" role="tooltip">선택한 월에 비어 있는 모델 원천지표를 모두 입력하세요.</span></span></div></div>
          <label className="custom-field custom-month-field"><span>정보 기준월</span><input type="month" value={month} disabled={loading} onChange={(event) => { setMonth(event.target.value); setValues({}); setResult(null); setError(""); }} /></label>
          {loading ? <p className="custom-loading-month" role="status"><LoaderCircle size={14} />선택한 선종의 월별 입력 정보를 불러오고 있습니다.</p> : <>
            <div className="custom-input-progress"><span>전체 <b>{config?.inputSources.length ?? 0}</b></span><span className="is-known">확보 <b>{knownSources.length}</b></span><span className="is-missing">입력 필요 <b>{missingSources.length}</b></span><span>입력 완료 <b>{completedInputs}/{missingSources.length}</b></span></div>
            <div className="custom-monthly-input-list">
              {config?.inputSources.map((item) => {
                const known = item.observations[month];
                return <label key={item.id} className={`custom-monthly-input ${known !== undefined ? "is-known" : "is-required"}`}><span className="custom-monthly-label"><b>{item.label}</b><small>{item.unit} · 최종 파생 피처 {item.features.length}개</small></span>{known !== undefined ? <span className="custom-known-value"><CheckCircle2 size={14} />{formatted(known)} <small>{item.unit}</small></span> : <input type="number" step="any" value={values[item.id] ?? ""} onChange={(event) => setValues((current) => ({ ...current, [item.id]: event.target.value }))} placeholder={`최근 ${formatted(item.latestValue)}`} aria-label={`${month} ${item.label}`} />}</label>;
              })}
            </div>
            {config && month && missingSources.length === 0 && <p className="custom-complete-month"><CheckCircle2 size={14} />{month}은 필요한 정보가 이미 모두 확보되어 있습니다.</p>}
          </>}
        </section>
        <div className="custom-config-actions"><button type="button" className="custom-reset-button" onClick={reset} disabled={running || !config}><RotateCcw size={15} />초기화</button><button type="button" className="custom-run-button is-ready" onClick={runForecast} disabled={running || loading || !inputComplete}><Play size={14} />{running ? "전망 업데이트 중…" : loading ? "입력 정보 불러오는 중…" : inputComplete ? "완성된 정보로 업데이트" : `${missingSources.length - completedInputs}개 정보 더 필요`}</button></div>
        {error && <p className="custom-run-error" role="alert">{error}</p>}
      </div>

      <aside className="custom-forecast-preview custom-regression-preview custom-scenario-preview" aria-busy={running}>
        <div className="custom-preview-head"><span>FORECAST REVISION</span><span className={`custom-preview-waiting ${result ? "is-complete" : ""}`}>{running ? "UPDATING" : result ? "UPDATED" : "READY"}</span></div>
        {result && <div className="custom-preview-save-actions"><button type="button" className="custom-save-button" onClick={saveForecastResult}><Download size={15} />결과 HTML 저장</button></div>}
        {result && chartOption && primary ? <div className="custom-scenario-result"><div className="custom-scenario-metrics"><div className={changeClass}><span>전망 변화</span><b>{primary.change > 0 ? "+" : ""}{formatted(primary.change)} · {changeRate > 0 ? "+" : ""}{changeRate.toFixed(1)}%</b></div><div><span>기준 전망</span><b>{formatted(primary.baseline)} {result.unit}</b></div><div className={changeClass}><span>수정 전망</span><b>{formatted(primary.scenario)} {result.unit}</b></div><div><span>가장 큰 변경점</span><b>{primary.month}</b></div></div><div className="custom-regression-chart custom-scenario-chart"><EChartsReact option={chartOption} onEvents={chartEvents} notMerge style={{ width: "100%", height: "100%" }} /></div></div> : <div className="custom-preview-chart"><div className="custom-chart-grid"><i /><i /><i /><i /></div><div className="custom-chart-placeholder"><span /><span /><span /><span /><span /><span /><span /></div><div className="custom-chart-legend"><span><i />기준 전망</span><span><i />수정 전망</span></div></div>}
        <div className="custom-preview-empty"><strong>{running ? "완성된 월별 정보로 전망을 다시 계산하고 있습니다." : result ? `${result.vessel} 전망 업데이트 완료` : loading ? "최종 모델을 불러오고 있습니다." : inputComplete ? "월별 입력 정보가 완성되었습니다." : `${month || "선택한 월"}의 비어 있는 정보 ${missingSources.length - completedInputs}개를 입력하세요.`}</strong>{!result && <p>모든 필수 원천지표가 확보된 뒤에만 기준 전망과 수정 전망을 비교합니다.</p>}</div>
        <dl className="custom-config-summary"><div><dt>선종</dt><dd>{pipeline.vessel}</dd></div><div><dt>예측 대상</dt><dd>수주용량 ({pipeline.unit})</dd></div><div><dt>반영 규칙</dt><dd>관측월 → 파생 피처 → D+{pipeline.leadMonths}</dd></div><div><dt>모델</dt><dd>{pipeline.model}</dd></div></dl>
      </aside>
    </div>
  </section>;
}

export default function CustomForecast() {
  const [subPage, setSubPage] = useState<"workspace" | "dictionary">("workspace");
  return <><nav className="custom-forecast-subnav" role="tablist" aria-label="사용자 지정 예측 하위 메뉴"><button type="button" role="tab" aria-selected={subPage === "workspace"} onClick={() => setSubPage("workspace")}><SlidersHorizontal size={15} />시나리오 예측</button><button type="button" role="tab" aria-selected={subPage === "dictionary"} onClick={() => setSubPage("dictionary")}><BookOpen size={15} />데이터 설명</button></nav>{subPage === "workspace" ? <ForecastWorkspace /> : <DataDictionary />}</>;
}
