import { useEffect, useMemo, useState } from "react";
import EChartsReact from "../common/LocalizedECharts";
import type { EChartsType } from "echarts";
import { AlertCircle, BookOpen, CheckCircle2, DatabaseZap, LoaderCircle, Play, RotateCcw, SlidersHorizontal } from "lucide-react";
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
