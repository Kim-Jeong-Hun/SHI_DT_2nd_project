import { useEffect, useRef, useState } from "react";
import {
  ArrowDown,
  ArrowRight,
  BarChart3,
  BriefcaseBusiness,
  ClipboardCheck,
  Factory,
  Newspaper,
  PanelLeftOpen,
  Pause,
  Play,
} from "lucide-react";
import EChartsReact from "../common/LocalizedECharts";
import { NOTEBOOK_FORECASTS, NOTEBOOK_VESSEL_IDS } from "../../data/notebookForecasts";
import type { NotebookVesselId } from "../../data/notebookForecasts";
import "../../styles/about-page.css";

const analysisSteps = [
  {
    number: "01",
    label: "수집·검증",
    title: "다섯 선종의 월별 데이터를 한곳에",
    copy: "가스 운반선, 벌크선, 유조선, 컨테이너선, 케미컬 탱커의 마스터 CSV를 월 단위로 수집합니다. 중복 월, 필수 항목, 음수 수주량과 선종별 단위를 확인해 분석 가능한 원본을 만듭니다. 월별 자료를 다시 합치고 단위를 확인하는 반복 작업을 줄여 핵심 변화 분석에 집중합니다.",
    note: "스키마 · 중복 · 단위 검증",
    image: "/images/about/Why Do Professionals Rely on Excel & Google Sheets_.jpeg",
    imageAlt: "여러 스프레드시트 데이터를 함께 검토하는 분석가들",
  },
  {
    number: "02",
    label: "정규화·특성화",
    title: "선종마다 다른 발주 신호를 설계합니다",
    copy: "CBM·DWT·TEU의 원 단위와 원본 열을 보존하고, 각 선종의 운임·선복·선령·거시 변수를 발주와 연결되는 방식으로 따로 구성합니다. 실제 정보 공개 시차와 수주 정보의 가용 근거를 반영하며, 각 선종의 단위를 존중하면서 동일한 분석 절차를 적용해 보고와 회의의 비교 기준을 맞춥니다.",
    note: "선종별 신호 설계 · 정보 시차 통제 · 원본 추적",
    image: "/images/about/Data Monitoring Center.jpeg",
    imageAlt: "다양한 데이터 흐름을 모니터링하는 분석 환경",
  },
  {
    number: "03",
    label: "시장 국면",
    title: "숫자의 움직임을 시장 국면으로",
    copy: "선종별 핵심 변수의 유사한 움직임을 묶어 시장 국면을 구분합니다. 수주, 운임, 거시 변수와 국면 변화를 함께 보며 단일 지표만으로 놓치기 쉬운 이상 신호를 조기에 확인하고, 현재와 과거의 시장 환경이 어떤 패턴에 가까운지 비교합니다.",
    note: "선종별 군집 · 월별 국면 라벨",
    image: "/images/about/Global financial data visualization with market trends and world map_.jpeg",
    imageAlt: "세계 지도 위에 표현된 글로벌 시장 흐름",
  },
  {
    number: "04",
    label: "수주 전망",
    title: "시간 순서를 지킨 롤링 검증으로",
    copy: "미래 정보를 섞지 않고 과거 구간으로 학습한 뒤 다음 구간을 반복 검증합니다. 선종 특성에 맞춘 GBM 또는 결합 모델로 향후 3개월의 방향과 변동 범위를 살펴보며, 단기 전망을 확정값이 아닌 시나리오 신호로 활용해 현업 경험과 함께 검토합니다.",
    note: "48·60개월 학습 · C+3 전망",
    image: "/images/about/Stock Market Analysis with Data Overlay.jpeg",
    imageAlt: "시계열 그래프의 변화를 분석하는 화면",
  },
  {
    number: "05",
    label: "해석·활용",
    title: "예측값을 업무의 언어로",
    copy: "수주 흐름, 시장 국면, 주요 변수를 한 화면에서 연결하고 산업 뉴스로 배경을 보완합니다. 결과를 정답이 아니라 영업·생산·조달 논의를 시작하는 공통 근거로 사용합니다.",
    note: "대시보드 · 뉴스 · 의사결정 지원",
    image: "/images/about/The Role of Corporate Finance in Growth.jpeg",
    imageAlt: "데이터 화면을 보며 의사결정을 논의하는 회의",
  },
];

const cycleCases = [
  {
    number: "01",
    year: "2009",
    title: "호황 지속을 전제로 확장",
    outlook: "발주 전망 4,000만 DWT",
    outcome: "실제 1,000만 DWT 미만",
    impact: <>신설 중소·중견 조선소가 무너졌고, C&중공업은 워크아웃에 들어갔습니다. 성동조선에는 <strong>채권단 자금 4조 원이 투입</strong>된 뒤 <strong>법정관리</strong>가 이어졌습니다.</>,
    signal: "2008년 10월부터 수주가 사실상 멈췄고, 2009년 4월 월간 발주는 전년 대비 97% 감소했습니다.",
    decision: "도크 증설과 저가 벌크선 수주를 더 일찍 멈출 수 있었습니다.",
  },
  {
    number: "02",
    year: "2021",
    title: "회복기에 불황 가격으로 수주",
    outlook: "발주 전망 3,000만 CGT",
    outcome: "실제 4,573만 CGT",
    impact: <>저가 수주에 후판 가격 급등이 겹치며 국내 빅3 조선사는 2021년 상반기에만 <strong>약 3조 원의 적자</strong>를 기록했습니다.</>,
    signal: "2월 중순 이미 120척이 발주됐고, 상반기 발주량은 연간 전망의 80%인 2,402만 CGT에 도달했습니다.",
    decision: "선가를 높이고 후판 가격 상승분을 계약에 반영할 수 있었습니다.",
  },
  {
    number: "03",
    year: "2016 → 2022",
    title: "불황 지속을 전제로 인력 감축",
    outlook: "수주 절벽 장기화 가정",
    outcome: "2021년 수주 급증",
    impact: <>종사자는 <strong>20만 3천 명에서 9만 2천 명으로 감소</strong>했고, 2022년에는 <strong>약 9,500명이 부족</strong>했습니다. <strong>파업 손실 약 8,000억 원</strong>과 <strong>선박 6척의 인도 지연</strong>도 발생했습니다.</>,
    signal: "2021년 1분기부터 발주가 빠르게 늘었지만 외국인 인력 약 2,000명이 투입된 시점은 2023년 2월이었습니다.",
    decision: "2021년 2분기부터 채용과 외국인 인력 확보 절차를 시작할 수 있었습니다.",
  },
  {
    number: "04",
    year: "2026",
    title: "연간 전망을 9개월 만에 초과",
    outlook: "발주 전망 3,500만 CGT",
    outcome: "9월까지 5,970만 CGT",
    impact: <>연간 전망을 기준으로 계획했다면 <strong className="is-risk">인력과 도크가 부족</strong>하고, <strong className="is-risk">상승기에도 선가를 낮게 제시할 위험</strong>이 커집니다.</>,
    signal: "연말이 오기 전에 실제 발주량이 연간 전망을 크게 넘어섰습니다.",
    decision: "2027년 인도분의 인력·도크를 확보하고 높아진 선가 협상력을 활용할 수 있습니다.",
  },
];

const detailNavigation = [
  { id: "details-top", label: "소개" },
  { id: "details-intro", label: "분석 가치" },
  { id: "details-method", label: "분석 과정" },
  { id: "details-work", label: "활용 업무" },
  { id: "details-context", label: "시장 맥락" },
  { id: "details-faq", label: "FAQ" },
];

const capabilities = [
  {
    icon: BarChart3,
    eyebrow: "MARKET MONITORING",
    title: "시장 변화 감지",
    text: "최근 수주량과 변수의 움직임, 현재 국면을 함께 보며 평소와 다른 변화를 빠르게 찾습니다.",
  },
  {
    icon: BriefcaseBusiness,
    eyebrow: "SALES PLANNING",
    title: "영업 우선순위",
    text: "선종별 흐름과 단기 전망을 비교해 고객 접점과 제안 활동의 우선순위를 논의합니다.",
  },
  {
    icon: Factory,
    eyebrow: "OPERATIONS",
    title: "생산·조달 시나리오",
    text: "향후 수주 가능성을 하나의 선행 신호로 활용해 인력, 도크, 기자재 계획의 시나리오를 검토합니다.",
  },
  {
    icon: ClipboardCheck,
    eyebrow: "REPORTING",
    title: "보고와 리서치",
    text: "동일한 데이터 기준으로 시장 설명을 정리해 정기 보고와 부서 간 커뮤니케이션의 일관성을 높입니다.",
  },
];

const frequentlyAskedQuestions = [
  {
    question: "어떤 데이터를 분석하나요?",
    answer: "가스 운반선, 벌크선, 유조선, 컨테이너선, 케미컬 탱커의 월별 마스터 데이터를 사용합니다. 수주용량과 함께 운임, 거시경제, 선종 고유 지표를 원본 열 이름 그대로 보존해 분석합니다.",
  },
  {
    question: "서로 다른 선종의 수주량을 바로 비교해도 되나요?",
    answer: "아닙니다. 선종별 수주용량은 CBM, DWT, TEU처럼 단위가 다르므로 단순 합산하거나 크기만 직접 비교하지 않습니다. 각 선종 안에서의 변화와 표준화된 시장 신호를 중심으로 해석합니다.",
  },
  {
    question: "미래 데이터가 예측에 섞이지 않도록 어떻게 관리하나요?",
    answer: "각 변수의 정보 이용 가능 시차를 기록하고, 시간 순서를 지키는 롤링 검증을 사용합니다. 과거 구간으로 학습한 모델이 그다음 구간을 예측하도록 반복해 실제 사용 시점에 가까운 조건으로 확인합니다.",
  },
  {
    question: "시장 국면은 호황과 불황을 뜻하나요?",
    answer: "반드시 그렇지는 않습니다. 국면은 여러 지표가 비슷하게 움직인 기간을 데이터 기반으로 묶은 결과입니다. 각 국면의 수주, 운임, 거시 변수 특성을 함께 살펴본 뒤 업무 맥락에 맞게 해석해야 합니다.",
  },
  {
    question: "예측 결과를 계약이나 투자 판단에 바로 사용해도 되나요?",
    answer: "예측은 확정값이 아니라 과거 데이터에서 관측된 패턴을 바탕으로 한 의사결정 보조 신호입니다. 개별 계약, 가격, 정책 변화 같은 정성 정보와 현업 판단을 함께 반영해야 합니다.",
  },
  {
    question: "새로운 CSV를 넣으면 기존 데이터가 중복되나요?",
    answer: "같은 선종과 기준월의 데이터는 갱신되며 중복 생성되지 않습니다. 가져오기 과정은 원본 행과 수치 특성을 함께 새로 반영하고, 오류가 있으면 전체 작업을 되돌리도록 구성되어 있습니다.",
  },
];

function CountUpMetric({ end, suffix, minimumDigits = 1 }: { end: number; suffix?: string; minimumDigits?: number }) {
  const animationFrame = useRef(0);
  const metricRef = useRef<HTMLElement>(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const metric = metricRef.current;
    if (!metric) return;
    const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const play = () => {
      cancelAnimationFrame(animationFrame.current);
      if (reduceMotion) {
        setValue(end);
        return;
      }
      setValue(0);
      const startedAt = performance.now();
      const duration = 450;
      const tick = (now: number) => {
        const progress = Math.min((now - startedAt) / duration, 1);
        const easedProgress = 1 - Math.pow(1 - progress, 3);
        setValue(Math.round(end * easedProgress));
        if (progress < 1) animationFrame.current = requestAnimationFrame(tick);
      };
      animationFrame.current = requestAnimationFrame(tick);
    };

    const observer = new IntersectionObserver(([entry]) => {
      if (entry.isIntersecting) play();
      else {
        cancelAnimationFrame(animationFrame.current);
        setValue(0);
      }
    }, { threshold: 0.35 });
    observer.observe(metric);
    return () => {
      observer.disconnect();
      cancelAnimationFrame(animationFrame.current);
    };
  }, [end]);

  const formattedValue = value.toLocaleString("ko-KR", { minimumIntegerDigits: minimumDigits });
  const formattedEnd = end.toLocaleString("ko-KR", { minimumIntegerDigits: minimumDigits });

  return (
    <strong ref={metricRef} aria-label={`${formattedEnd}${suffix ?? ""}`}>
      <span className="details-count-number" aria-hidden="true">{formattedValue}</span>
      {suffix && <span className="details-count-unit" aria-hidden="true">{suffix}</span>}
    </strong>
  );
}

const formatValidationValue = (value: number, unit: string) => {
  const compact = value >= 1_000_000 ? `${(value / 1_000_000).toFixed(1)}M` : `${Math.round(value / 1_000)}K`;
  return `${compact} ${unit}`;
};

function ValidationPerformance({ vesselId, onChange }: { vesselId: NotebookVesselId; onChange: (id: NotebookVesselId) => void }) {
  const forecast = NOTEBOOK_FORECASTS[vesselId];
  const positive = forecast.quarterChange >= 0;

  return (
    <div className="details-validation">
      <div className="details-validation-head">
        <div><p>MODEL VALIDATION</p><h4>예측 모델 검증 성능</h4></div>
        <div className="details-validation-tabs" role="tablist" aria-label="선종별 예측 모델 검증 성능">
          {NOTEBOOK_VESSEL_IDS.map((id) => <button key={id} type="button" role="tab" aria-selected={id === vesselId} onClick={() => onChange(id)}>{NOTEBOOK_FORECASTS[id].vesselName}</button>)}
        </div>
      </div>
      <p className="details-validation-model">{forecast.model}</p>
      <div className="details-validation-metrics">
        <div><span>Test 상대오차</span><strong>{forecast.testRelativeError.toFixed(1)}%</strong></div>
        <div><span>Validation QAE</span><strong>{formatValidationValue(forecast.validationMae, forecast.unit)}</strong></div>
        <div><span>고점 오차</span><strong>{forecast.peakTimingError.toFixed(2)}개월</strong></div>
      </div>
      <EChartsReact className="details-validation-chart" option={{
        animationDuration: 550,
        grid: { left: 2, right: 2, top: 8, bottom: 2 },
        xAxis: { type: "category", show: false, data: forecast.monthly.map((item) => item.month) },
        yAxis: { type: "value", show: false, scale: true },
        series: [{
          type: "line",
          smooth: 0.25,
          symbol: "none",
          data: forecast.monthly.map((item) => item.value),
          lineStyle: { color: positive ? "#078477" : "#d95454", width: 2.4 },
          areaStyle: { color: positive ? "rgba(7,132,119,.14)" : "rgba(217,84,84,.13)" },
        }],
      }} notMerge lazyUpdate />
    </div>
  );
}

export default function AboutPage({ onExplore, onOpenNewsroom }: { onExplore: () => void; onOpenNewsroom: () => void }) {
  const [activeStep, setActiveStep] = useState(0);
  const [activeCase, setActiveCase] = useState(0);
  const [isCasePlaying, setIsCasePlaying] = useState(true);
  const [isNavigationOpen, setIsNavigationOpen] = useState(true);
  const [activeSection, setActiveSection] = useState("details-top");
  const [validationVessel, setValidationVessel] = useState<NotebookVesselId>("tanker");
  const step = analysisSteps[activeStep];
  const selectedCase = cycleCases[activeCase];

  useEffect(() => {
    if (!isCasePlaying || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setTimeout(() => {
      setActiveCase((current) => (current + 1) % cycleCases.length);
    }, 6000);
    return () => window.clearTimeout(timer);
  }, [activeCase, isCasePlaying]);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const visibleSection = entries.find((entry) => entry.isIntersecting);
      if (visibleSection) setActiveSection(visibleSection.target.id);
    }, { rootMargin: "-42% 0px -48% 0px", threshold: 0 });
    detailNavigation.forEach(({ id }) => {
      const section = document.getElementById(id);
      if (section) observer.observe(section);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <main className="details-page">
      {isNavigationOpen ? (
        <nav className="details-floating-nav" aria-label="Details 페이지 섹션 이동">
          <button className="details-floating-nav-close" type="button" aria-label="섹션 내비게이션 닫기" onClick={() => setIsNavigationOpen(false)}>
            <span aria-hidden="true">×</span>
          </button>
          {detailNavigation.map((item) => (
            <a key={item.id} href={`#${item.id}`} aria-current={activeSection === item.id ? "location" : undefined} onClick={(event) => {
              event.preventDefault();
              document.getElementById(item.id)?.scrollIntoView({ behavior: "smooth" });
            }}>
              <b>{item.label}</b>
            </a>
          ))}
        </nav>
      ) : (
        <button className="details-floating-nav-open" type="button" aria-label="섹션 내비게이션 열기" onClick={() => setIsNavigationOpen(true)}>
          <PanelLeftOpen aria-hidden="true" />
        </button>
      )}

      <section id="details-top" className="details-hero">
        <img src="/images/about/maritime-panorama.png" alt="항만과 선박이 이어지는 해양 산업 전경" />
        <div className="details-hero-shade" />
        <div className="details-hero-copy">
          <div className="details-hero-message">
            <p className="details-eyebrow">SHIPULSE · DATA METHODOLOGY</p>
            <h1>데이터 분석과<br /><em>조선 시장의 미래</em></h1>
            <p>Data Analysis팀이 공유하는 조선/해양/물류 인사이트와 판단 기준</p>
          </div>
        </div>
        <button type="button" aria-label="분석 소개로 이동" onClick={() => document.getElementById("details-intro")?.scrollIntoView({ behavior: "smooth" })}>
          <ArrowDown />
        </button>
      </section>

      <section id="details-intro" className="details-intro-combined">
        <div className="details-intro">
          <div className="details-intro-heading">
            <p className="details-eyebrow">01 · WHY TIMING MATTERS</p>
            <h2><span>늦은 판단이</span><br />남긴 대가</h2>
          </div>
          <div className="details-intro-copy">
            <p className="details-intro-description">조선업계는 바다처럼 급변하며 손실은 천문학적인 단위로 이루어집니다.<br />깨달았을 때는 이미 늦은 경우가 많았습니다.</p>
          </div>
          <div className="details-cycle-evidence">
            <div className="details-cycle-summary" aria-label="사례 핵심 수치">
              <p><strong>−75% ~ +71%</strong><span>연간 전망 오차</span></p>
              <p><strong>6~9개월</strong><span>전망 반영 지연</span></p>
              <p><strong>3.8조 원</strong><span>사례에 나타난 손실</span></p>
            </div>
            <div className="details-cycle-picker">
              <div className="details-cycle-tabs" role="tablist" aria-label="조선 사이클 오판 사례">
                {cycleCases.map((item, index) => (
                  <button key={item.number} type="button" role="tab" aria-label={`사례 ${item.number}: ${item.year} ${item.title}`} aria-selected={activeCase === index} aria-controls="details-cycle-panel" onClick={() => setActiveCase(index)} />
                ))}
              </div>
              <button className="details-cycle-playback" type="button" aria-label={isCasePlaying ? "사례 자동 전환 일시정지" : "사례 자동 전환 재생"} onClick={() => setIsCasePlaying((current) => !current)}>
                {isCasePlaying ? <Pause aria-hidden="true" /> : <Play aria-hidden="true" />}
              </button>
            </div>
            <article id="details-cycle-panel" className="details-cycle-card" role="tabpanel" key={selectedCase.number}>
              <div className="details-cycle-card-head">
                <div><span>CASE {selectedCase.number}</span><h4>{selectedCase.title}</h4></div>
                <b>{selectedCase.year}</b>
              </div>
              <div className="details-cycle-card-body">
                <div className="details-cycle-forecast">
                  <span>전망과 실제</span>
                  <div className="details-cycle-comparison">
                    <p><span>당시 전망</span><strong>{selectedCase.outlook}</strong></p>
                    <p><span>실제 결과</span><strong>{selectedCase.outcome}</strong></p>
                  </div>
                </div>
                <div className="details-cycle-impact"><span>발생한 비용</span><p>{selectedCase.impact}</p></div>
                <div className="details-cycle-response"><span>분기 신호였다면</span><p>{selectedCase.signal}</p><strong>{selectedCase.decision}</strong></div>
              </div>
            </article>
          </div>
        </div>

      </section>

      <section id="details-method" className={`details-method is-compact${activeStep === 0 ? " is-collection" : ""}`}>
        <div className="details-method-heading">
          <p className="details-eyebrow">02 · HOW WE ANALYZE</p>
          <h2><span>분석 속도와</span><br /><span>판단의 일관성을</span><br /><span>높입니다.</span></h2>
          <p>원본 데이터에서 업무의 신호까지, 각 단계를 선택해 SHIPULSE의 분석 흐름과 효과를 살펴보세요.</p>
          <div className="details-method-tabs" role="tablist" aria-label="데이터 분석 단계">
            {analysisSteps.map((item, index) => (
              <button key={item.number} type="button" role="tab" aria-selected={activeStep === index} aria-controls="details-method-panel" onClick={() => setActiveStep(index)}>
                <span>{item.number}</span>{item.label}<ArrowRight />
              </button>
            ))}
          </div>
        </div>
        <article id="details-method-panel" className={`details-method-panel${activeStep === 0 || activeStep === 3 ? " has-supporting-data" : ""}`} role="tabpanel" key={step.number}>
          <div className="details-method-image">
            <img src={step.image} alt={step.imageAlt} />
            <span>{step.number} / ANALYSIS PROCESS</span>
          </div>
          <div className="details-method-copy"><p>{step.number} — {step.label}</p><h3>{step.title}</h3><span>{step.copy}</span><small>{step.note}</small></div>
          {activeStep === 3 && <ValidationPerformance vesselId={validationVessel} onChange={setValidationVessel} />}
          {activeStep === 0 && (
            <div className="details-collection-metrics" aria-label="수집·검증 데이터 분석 범위">
              <div><CountUpMetric end={5} minimumDigits={2} /><span>분석 선종</span><small>가스 · 벌크 · 유조 · 컨테이너 · 케미컬</small></div>
              <div><CountUpMetric end={825} suffix="건" /><span>월별 마스터 레코드</span><small>선종별 165개월</small></div>
              <div><CountUpMetric end={43134} suffix="개" /><span>수치 특성값</span><small>원본 열 이름과 값 보존</small></div>
              <div><CountUpMetric end={634} suffix="건" /><span>시장 국면 라벨</span><small>선종별 최종 분석 결과</small></div>
            </div>
          )}
        </article>
      </section>

      <section id="details-work" className="details-capabilities">
        <div className="details-section-heading"><p className="details-eyebrow">03 · WHERE IT WORKS</p><h2><span>이런 업무에</span><br /><span>활용할 수 있습니다.</span></h2></div>
        <div className="details-capability-grid">{capabilities.map(({ icon: Icon, eyebrow, title, text }) => <article key={eyebrow}><Icon /><p>{eyebrow}</p><h3>{title}</h3><span>{text}</span></article>)}</div>
      </section>

      <section id="details-context" className="details-context">
        <img src="/images/about/Claves de la protección de datos digitales (1).jpeg" alt="다양한 산업 소식을 한곳에서 살펴보는 미디어 월" />
        <div>
          <Newspaper />
          <p className="details-eyebrow">04 · DATA + CONTEXT</p>
          <h2>숫자만으로 설명되지 않는 변화는<br />산업 뉴스로 맥락을 보완합니다.</h2>
          <p>모델이 보여주는 패턴과 실제 시장 사건을 함께 검토하면, 변화의 원인을 더 구체적인 가설로 발전시킬 수 있습니다.</p>
          <button className="details-context-link" type="button" onClick={onOpenNewsroom}>뉴스룸 이동하기 <ArrowRight /></button>
        </div>
      </section>

      <section id="details-faq" className="details-faq" aria-labelledby="details-faq-title">
        <div className="details-faq-heading">
          <p className="details-eyebrow">05 · FREQUENTLY ASKED QUESTIONS</p>
          <h2 id="details-faq-title">자주 묻는 질문</h2>
          <p>데이터 기준과 결과 해석에 필요한 핵심 내용을 정리했습니다.</p>
        </div>
        <div className="details-faq-list">
          {frequentlyAskedQuestions.map((item, index) => (
            <details key={item.question} open={index === 0}>
              <summary><span>{String(index + 1).padStart(2, "0")}</span>{item.question}</summary>
              <p>{item.answer}</p>
            </details>
          ))}
        </div>
      </section>

      <section className="details-cta">
        <div><p className="details-eyebrow">EXPLORE THE SIGNAL</p><h2>설명에서 끝내지 않고<br />데이터로 확인해보세요.</h2><p>선종별 시장 국면과 수주 전망을 대시보드에서 직접 비교할 수 있습니다.</p><button type="button" onClick={onExplore}>대시보드로 이동 <ArrowRight /></button><small>분석 및 예측 결과는 과거 데이터에 기반한 의사결정 지원 정보입니다. 개별 계약, 사업 또는 투자 판단에는 최신 시장 정보와 현업 검토를 함께 반영해야 합니다.</small></div>
      </section>
    </main>
  );
}
