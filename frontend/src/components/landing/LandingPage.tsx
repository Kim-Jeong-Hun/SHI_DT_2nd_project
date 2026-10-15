import {
  ArrowRight,
  Check,
  Database,
  LineChart,
  LockKeyhole,
  Radar,
  Sparkles,
  UserPlus,
} from "lucide-react";
import { useEffect, useRef, useState, type FormEvent } from "react";
import "../../styles/landing.css";
import { annualDisplayPrice, displayPriceDisclaimer } from "../../data/displayPricing";
import heroVideoEn from "../../assets/landing/ship-signal-intro-en.mp4";
import heroVideoKo from "../../assets/landing/ship-signal-intro-ko.mp4";
import AppBrand from "../common/AppBrand";
import { LanguageSwitcher, useI18n, type Language } from "../../i18n";

type LandingPageProps = {
  error?: string;
  onRetry?: () => void;
  onAuthenticated?: (user: { id: string; email: string | null; displayName: string; avatarUrl: string | null; subscriptionStatus: "Y" | "N"; subscriptionPlan: string | null; emailOptIn: "Y" | "N"; marketingOptIn: "Y" | "N" }) => void;
};

const forecasts = [
  { name: "컨테이너선", value: 86.7, unit: "TEU", trend: "C+3 전망" },
  { name: "유조선", value: 1011.9, unit: "DWT", trend: "C+3 전망" },
  { name: "벌크선", value: 823.7, unit: "DWT", trend: "C+3 전망" },
  { name: "가스 운반선", value: 620, unit: "CBM", trend: "C+3 전망" },
  { name: "케미컬 탱커", value: 30.6, unit: "DWT", trend: "C+3 전망" },
];

function ForecastCountUp({ end, unit, delay }: { end: number; unit: string; delay: number }) {
  const numberRef = useRef<HTMLElement>(null);
  const [value, setValue] = useState(0);

  useEffect(() => {
    const number = numberRef.current;
    if (!number) return;

    let animationFrame = 0;
    let delayTimer = 0;
    let hasStarted = false;
    const startAnimation = () => {
      if (hasStarted) return;
      hasStarted = true;

      if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        setValue(end);
        return;
      }

      delayTimer = window.setTimeout(() => {
        const startedAt = performance.now();
        const duration = 2600;
        const tick = (now: number) => {
          const cycleProgress = Math.max(0, ((now - startedAt) % duration) / duration);
          const oscillatingProgress = 1 - Math.abs(2 * cycleProgress - 1);
          setValue(Math.round(end * oscillatingProgress * 10) / 10);
          animationFrame = requestAnimationFrame(tick);
        };
        animationFrame = requestAnimationFrame(tick);
      }, delay);
    };

    const observer = new IntersectionObserver((entries) => {
      if (entries[0]?.isIntersecting) {
        startAnimation();
        observer.disconnect();
      }
    }, { threshold: 0.45 });

    observer.observe(number);
    return () => {
      observer.disconnect();
      window.clearTimeout(delayTimer);
      cancelAnimationFrame(animationFrame);
    };
  }, [delay, end]);

  const formattedValue = value.toLocaleString("ko-KR", { minimumFractionDigits: 1, maximumFractionDigits: 1 });

  return (
    <strong ref={numberRef} aria-label={`${unit} 예측 스냅샷 애니메이션`}>
      <span className="strip-value-number">{formattedValue}</span><span className="strip-value-scale">만</span> <small>{unit}</small>
    </strong>
  );
}

const features = [
  {
    icon: Radar,
    label: "MARKET SIGNAL",
    title: "변화 신호를 먼저 포착하세요",
    description: "수주량과 운임의 움직임을 함께 비교해 시장의 방향과 변곡점을 빠르게 확인합니다.",
  },
  {
    icon: LineChart,
    label: "C+3 FORECAST",
    title: "다음 분기를 수치로 준비하세요",
    description: "선종별 시계열과 C+3 누적 수주용량 예측으로 다음 의사결정의 기준을 세웁니다.",
  },
  {
    icon: Database,
    label: "ONE WORKSPACE",
    title: "흩어진 지표를 한 화면에서",
    description: "월간 변화 히트맵부터 분기별 수주와 운임까지 같은 흐름 안에서 탐색합니다.",
  },
];

const plans = [
  {
    name: "Explore",
    eyebrow: "시장 흐름을 확인하는 시작점",
    price: "무료로 시작",
    description: "핵심 시장 개요와 서비스 구성을 먼저 살펴보세요.",
    benefits: ["시장 개요 대시보드", "5개 선종 통합 보기", "월간 시장 지표"],
    featured: false,
  },
  {
    name: "Professional",
    eyebrow: "예측이 필요한 실무자를 위해",
    price: `연 ${annualDisplayPrice.professional}`,
    description: "수주 전망과 운임 데이터를 업무에 지속적으로 활용하세요.",
    benefits: ["선종별 C+3 수주용량 예측", "수주·운임 비교 차트", "월간 변화 히트맵", "데이터 CSV 내보내기"],
    featured: true,
  },
  {
    name: "Enterprise",
    eyebrow: "조직 단위 활용을 위한 구성",
    price: `연 ${annualDisplayPrice.enterprise}`,
    description: "팀의 분석 목적과 활용 범위에 맞춰 도입을 상담하세요.",
    benefits: ["조직 단위 도입 상담", "데이터 활용 범위 협의", "운영 지원 협의"],
    featured: false,
  },
];

const authHref = "/api/auth/google";

function GoogleLogo() {
  return (
    <svg className="google-logo" viewBox="0 0 18 18" aria-hidden="true">
      <path fill="#4285F4" d="M17.64 9.205c0-.638-.057-1.252-.164-1.841H9v3.482h4.844a4.14 4.14 0 0 1-1.797 2.715v2.258h2.909c1.703-1.568 2.684-3.878 2.684-6.614Z" />
      <path fill="#34A853" d="M9 18c2.43 0 4.468-.806 5.956-2.181l-2.909-2.258c-.806.54-1.836.859-3.047.859-2.344 0-4.328-1.585-5.037-3.714H.956v2.332A8.999 8.999 0 0 0 9 18Z" />
      <path fill="#FBBC05" d="M3.963 10.706A5.41 5.41 0 0 1 3.682 9c0-.592.102-1.168.281-1.706V4.962H.956A9 9 0 0 0 0 9c0 1.452.347 2.827.956 4.038l3.007-2.332Z" />
      <path fill="#EA4335" d="M9 3.58c1.321 0 2.508.454 3.441 1.346l2.581-2.581C13.464.892 11.426 0 9 0A8.999 8.999 0 0 0 .956 4.962l3.007 2.332C4.672 5.165 6.656 3.58 9 3.58Z" />
    </svg>
  );
}

function LandingHeroVideo({ language }: { language: Language }) {
  const videoSrc = language === "en" ? heroVideoEn : heroVideoKo;
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const video = videoRef.current;
    if (!video) return;
    video.load();
    void video.play().catch(() => undefined);
  }, [videoSrc]);

  return (
    <figure className="landing-hero-video">
      <video
        ref={videoRef}
        key={videoSrc}
        autoPlay
        controls
        loop
        muted
        playsInline
        preload="metadata"
        aria-label="선견지명 서비스 소개 영상"
      >
        <source src={videoSrc} type="video/mp4" />
        브라우저에서 영상을 재생할 수 없습니다.
      </video>
    </figure>
  );
}

function SignupPage({ onBack, onLogin, onAuthenticated }: Pick<LandingPageProps, "onAuthenticated"> & { onBack: () => void; onLogin: () => void }) {
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    const data = new FormData(event.currentTarget);
    const password = String(data.get("password") ?? "");
    const confirmPassword = String(data.get("confirmPassword") ?? "");
    if (password !== confirmPassword) {
      setFormError("비밀번호가 서로 일치하지 않습니다.");
      return;
    }

    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/register", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          displayName: String(data.get("displayName") ?? ""),
          email: String(data.get("email") ?? ""),
          password,
          emailOptIn: data.get("emailOptIn") === "on",
          marketingOptIn: data.get("marketingOptIn") === "on",
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "회원가입을 완료하지 못했습니다.");
      onAuthenticated?.(result.user);
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : "회원가입을 완료하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="signup-shell">
      <nav className="signup-nav">
        <AppBrand href="#top" />
        <div className="flex items-center gap-3"><LanguageSwitcher compact /><button type="button" onClick={onBack}>홈으로 돌아가기</button></div>
      </nav>
      <div className="signup-layout">
        <section className="signup-intro">
          <div className="hero-eyebrow"><Sparkles size={15} /> START YOUR MARKET VIEW</div>
          <h1>다음 분기를 읽는<br />나만의 대시보드.</h1>
          <p>계정을 만들고 5개 선종의 수주 전망, 운임 변화와 시장 신호를<br />한 곳에서 확인하세요.</p>
          <div className="signup-benefits">
            <span><Check size={17} /> 선종별 C+3 수주용량 예측</span>
            <span><Check size={17} /> 월간 변화 히트맵</span>
            <span><Check size={17} /> 수주와 운임 비교 분석</span>
          </div>
        </section>
        <section className="signup-card">
          <div className="signup-card-heading">
            <span><UserPlus size={19} /></span>
            <div><h2>회원가입</h2><p>기본 정보를 입력해 계정을 만들어 주세요.</p></div>
          </div>
          <form onSubmit={submit}>
            <label>이름<input name="displayName" type="text" autoComplete="name" minLength={2} maxLength={50} placeholder="이름을 입력하세요" required /></label>
            <label>이메일<input name="email" type="email" autoComplete="email" placeholder="name@company.com" required /></label>
            <div className="signup-passwords">
              <label>비밀번호<input name="password" type="password" autoComplete="new-password" minLength={8} maxLength={128} placeholder="8자 이상" required /></label>
              <label>비밀번호 확인<input name="confirmPassword" type="password" autoComplete="new-password" minLength={8} maxLength={128} placeholder="다시 입력" required /></label>
            </div>
            <label className="signup-agree"><input type="checkbox" required /><span>만 14세 이상이며 서비스 이용을 위한 계정 생성에 동의합니다.</span></label>
            <div className="signup-options">
              <label className="signup-agree"><input name="emailOptIn" type="checkbox" defaultChecked /><span><b>[선택]</b> 시장 리포트와 서비스 주요 알림을 이메일로 받습니다.</span></label>
              <label className="signup-agree"><input name="marketingOptIn" type="checkbox" /><span><b>[선택]</b> 이벤트, 혜택 등 광고성 정보 이메일 수신에 동의합니다.</span></label>
            </div>
            {formError && <p className="signup-form-error" role="alert">{formError}</p>}
            <button className="signup-submit" type="submit" disabled={submitting}>{submitting ? "계정 생성 중..." : "회원가입하고 시작하기"}<ArrowRight size={17} /></button>
          </form>
          <div className="signup-divider"><span>또는</span></div>
          <a className="signup-google" href={authHref}><GoogleLogo /> Google 계정으로 계속하기</a>
          <p className="signup-login-link">이미 계정이 있으신가요? <button type="button" onClick={onLogin}>로그인</button></p>
        </section>
      </div>
    </main>
  );
}

function LoginPage({ onBack, onSignup, onAuthenticated }: Pick<LandingPageProps, "onAuthenticated"> & { onBack: () => void; onSignup: () => void }) {
  const [formError, setFormError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [rememberMe, setRememberMe] = useState(false);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setFormError("");
    const data = new FormData(event.currentTarget);
    setSubmitting(true);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: String(data.get("email") ?? ""), password: String(data.get("password") ?? ""), rememberMe }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "로그인하지 못했습니다.");
      onAuthenticated?.(result.user);
    } catch (cause) {
      setFormError(cause instanceof Error ? cause.message : "로그인하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="signup-shell">
      <nav className="signup-nav"><AppBrand href="#top" /><div className="flex items-center gap-3"><LanguageSwitcher compact /><button type="button" onClick={onBack}>홈으로 돌아가기</button></div></nav>
      <div className="signup-layout login-layout">
        <section className="signup-intro">
          <div className="hero-eyebrow"><Sparkles size={15} /> WELCOME BACK</div>
          <h1><span>시장의 다음 흐름을</span><br />계속 확인하세요.</h1>
          <p>다시 방문해주셔서 감사합니다.<br />선종별 수주 전망과 관련 데이터를 확인해보세요.</p>
        </section>
        <section className="signup-card login-card">
          <div className="signup-card-heading"><span><LockKeyhole size={19} /></span><div><h2>로그인</h2><p>가입한 이메일과 비밀번호를 입력하세요.</p></div></div>
          <form onSubmit={submit}>
            <label>이메일<input name="email" type="email" autoComplete="email" placeholder="name@company.com" required /></label>
            <label>비밀번호<input name="password" type="password" autoComplete="current-password" placeholder="비밀번호를 입력하세요" required /></label>
            <label className="signup-agree login-remember"><input type="checkbox" checked={rememberMe} onChange={(event) => setRememberMe(event.target.checked)} /><span>로그인 상태 유지</span></label>
            {formError && <p className="signup-form-error" role="alert">{formError}</p>}
            <button className="signup-submit" type="submit" disabled={submitting}>{submitting ? "로그인 중..." : "로그인"}<ArrowRight size={17} /></button>
          </form>
          <div className="signup-divider"><span>또는</span></div>
          <a className="signup-google" href={`${authHref}?remember=${rememberMe ? "1" : "0"}`}><GoogleLogo /> Google 계정으로 계속하기</a>
          <p className="signup-login-link">아직 계정이 없으신가요? <button type="button" onClick={onSignup}>회원가입</button></p>
        </section>
      </div>
    </main>
  );
}

export default function LandingPage({ error, onRetry, onAuthenticated }: LandingPageProps) {
  const { language } = useI18n();
  const [authView, setAuthView] = useState<"home" | "signup" | "login">("home");
  if (authView === "signup") return <SignupPage onBack={() => setAuthView("home")} onLogin={() => setAuthView("login")} onAuthenticated={onAuthenticated} />;
  if (authView === "login") return <LoginPage onBack={() => setAuthView("home")} onSignup={() => setAuthView("signup")} onAuthenticated={onAuthenticated} />;

  return (
    <main id="top" className="landing-shell">
      <nav className="landing-nav" aria-label="주요 메뉴">
        <AppBrand href="#top" />
        <div className="landing-nav-links">
          <a href="#insight">예측 인사이트</a>
          <a href="#product">서비스 소개</a>
          <a href="#pricing">요금제</a>
        </div>
        <div className="landing-nav-actions">
          <LanguageSwitcher compact />
          <button className="nav-start" type="button" onClick={() => setAuthView("signup")}>회원가입 <ArrowRight size={15} /></button>
          <button className="nav-login" type="button" onClick={() => setAuthView("login")}>로그인</button>
        </div>
      </nav>

      {error && (
        <div className="landing-error" role="alert">
          <span>{error}</span>
          {onRetry && <button type="button" onClick={onRetry}>다시 확인</button>}
        </div>
      )}

      <section className="landing-hero">
        <div className="hero-copy">
          <div className="hero-eyebrow"><Sparkles size={15} /> SHIP ORDER MARKET INTELLIGENCE</div>
          <h1>선박 수주 시장의<br /><em>미래</em>를 먼저 읽으세요.</h1>
          <p>수주량, 운임, 거시 지표를 한곳에서 연결하고<br />5개 선종의 다음 분기 수주용량을 예측합니다.</p>
          <div className="hero-actions">
            <a className="primary-cta hero-primary-cta" href={authHref}>선박 수주 시장의 미래 읽기 <ArrowRight size={20} /></a>
          </div>
        </div>
        <div className="hero-visual"><LandingHeroVideo language={language} /></div>
      </section>

      <section className="forecast-strip" aria-label="선종별 다음 분기 예측">
        <div className="strip-label"><span>NEXT QUARTER</span><strong>선종별 예측 스냅샷</strong></div>
        {forecasts.map((item, index) => (
          <div className="strip-item" key={item.name}>
            <span>{item.name}</span>
            <ForecastCountUp end={item.value} unit={item.unit} delay={index * 90} />
            <em>{item.trend}</em>
          </div>
        ))}
      </section>

      <section id="insight" className="landing-section insight-section">
        <div className="section-kicker">FROM DATA TO DECISION</div>
        <div className="section-title-row">
          <h2>숫자를 보는 데서 끝나지 않는<br />시장 해석의 흐름</h2>
          <p>시장 전체를 훑고, 변화 신호를 읽고, 선종별 전망으로 내려가는 분석 경험을 한 화면에 담았습니다.</p>
        </div>
        <div className="feature-grid">
          {features.map(({ icon: Icon, label, title, description }, index) => (
            <article className="feature-card" key={title}>
              <div className="feature-card-top"><span>0{index + 1}</span><Icon size={23} /></div>
              <small>{label}</small>
              <h3>{title}</h3>
              <p>{description}</p>
            </article>
          ))}
        </div>
      </section>

      <section id="product" className="landing-section product-section">
        <div className="product-copy">
          <div className="section-kicker light">ONE MARKET, ONE VIEW</div>
          <h2>필요한 순간에<br />필요한 선종만 깊게.</h2>
          <p>전체 시장에서 시작해 컨테이너선, 유조선, 벌크선, 가스 운반선, 케미컬 탱커로 전환하며 같은 기준으로 비교할 수 있습니다.</p>
          <ul>
            <li><Check size={18} /> 시장 개요와 변화 신호 해석</li>
            <li><Check size={18} /> 다음 분기 누적 수주용량 예측</li>
            <li><Check size={18} /> 선종별·분기별 수주와 운임</li>
            <li><Check size={18} /> 선종별 월간 변화 히트맵</li>
          </ul>
          <a href={authHref}>내 대시보드 시작하기 <ArrowRight size={17} /></a>
        </div>
        <figure className="product-dashboard-preview">
          <div className="product-dashboard-frame" role="img" aria-label="SHIPULSE 실제 대시보드 구성을 재현한 샘플 데이터 목업">
            <header className="product-mock-header">
              <div className="product-mock-brand"><i>船</i><span><b>선(船)견지명</b><small>ORDER MARKET INTELLIGENCE</small></span></div>
              <nav><strong>종합 분석</strong><span>컨테이너선</span><span>유조선</span><span>벌크선</span><span>가스 운반선</span></nav>
              <em>DEMO</em>
            </header>
            <div className="product-mock-body">
              <aside>
                <b>분석 대시보드</b>
                <span className="is-active"><i>▦</i>시장 개요</span>
                <span><i>⌁</i>분기 수주 전망</span>
                <span><i>▥</i>월별 수주 전망</span>
                <small>CURRENT PLAN<strong>Professional</strong></small>
              </aside>
              <div className="product-mock-main">
                <section className="product-mock-brief">
                  <p>⌁ &nbsp; MARKET BRIEF</p>
                  <h3>다음 분기 수주 신호는 <em>완만한 회복</em> 흐름입니다.</h3>
                  <span>선종별 변화를 비교해 대응 우선순위를 확인하세요.</span>
                  <div><small>4분기 누적 전망<b>12.8M DWT</b></small><small>4분기 월평균 전망<b>4.3M DWT</b></small></div>
                </section>
                <div className="product-mock-charts">
                  <article className="product-mock-line-chart">
                    <header><b>선종별 실적 및 연말까지 수주 전망</b><span>전체 종합</span></header>
                    <svg viewBox="0 0 540 170" preserveAspectRatio="none" aria-hidden="true">
                      <g className="mock-grid"><line x1="24" y1="35" x2="522" y2="35"/><line x1="24" y1="75" x2="522" y2="75"/><line x1="24" y1="115" x2="522" y2="115"/><line x1="140" y1="18" x2="140" y2="145"/><line x1="280" y1="18" x2="280" y2="145"/><line x1="420" y1="18" x2="420" y2="145"/></g>
                      <path className="mock-band" d="M300 88 L350 55 L400 74 L455 35 L510 58 L510 110 L455 87 L400 126 L350 103 L300 122 Z"/>
                      <path className="mock-actual" d="M25 118 L72 104 L118 111 L165 73 L212 89 L258 62 L304 91"/>
                      <path className="mock-forecast" d="M304 91 L350 73 L400 98 L455 60 L510 82"/>
                      <circle cx="304" cy="91" r="5" className="mock-current"/>
                    </svg>
                    <footer><span>실적</span><span>현재 시점</span><span>90% 예측 구간</span></footer>
                  </article>
                  <article className="product-mock-heatmap">
                    <header><b>선종별 월별 수주 전망</b><span>7–12월</span></header>
                    <div className="product-mock-months"><span /><b>7월</b><b>8월</b><b>9월</b><b>10월</b><b>11월</b><b>12월</b></div>
                    <div className="product-mock-heat-grid">
                      {["유조선", "컨테이너선", "케미컬 탱커", "가스 운반선", "벌크선"].map((name, row) => <div key={name}><b>{name}</b>{Array.from({ length: 6 }, (_, column) => <i key={column} className={`heat-${(row * 2 + column) % 5}`} />)}</div>)}
                    </div>
                    <footer><span>선종별 최소</span><i /><span>선종별 최대</span></footer>
                  </article>
                </div>
                <div className="product-mock-bars"><b>수주 전망 주요 기여 변수</b><span><i style={{ width: "88%" }} />운임 지수</span><span><i style={{ width: "64%" }} />글로벌 교역량</span><span><i style={{ width: "46%" }} />원자재 가격</span></div>
              </div>
            </div>
          </div>
          <figcaption><span>PRODUCT INTERFACE PREVIEW</span><small>실제 제품 UI 기반 · 소개용 샘플 데이터</small></figcaption>
        </figure>
      </section>

      <section id="pricing" className="landing-section pricing-section">
        <div className="section-kicker">CHOOSE YOUR VIEW</div>
        <div className="pricing-heading">
          <h2>필요한 깊이만큼 시작하세요.</h2>
          <div><p>계정을 만들고 시장 개요를 살펴본 뒤,<br />업무 범위에 맞는 구독을 선택할 수 있습니다.</p><small>{displayPriceDisclaimer}</small></div>
        </div>
        <div className="pricing-grid">
          {plans.map((plan) => (
            <article className={`price-card${plan.featured ? " featured" : ""}`} key={plan.name}>
              {plan.featured && <span className="recommended">가장 많이 선택</span>}
              <small>{plan.eyebrow}</small>
              <h3>{plan.name}</h3>
              <div className="plan-price">{plan.price}</div>
              <p>{plan.description}</p>
              <ul>{plan.benefits.map((benefit) => <li key={benefit}><Check size={16} />{benefit}</li>)}</ul>
              <a href={authHref}>{plan.name === "Enterprise" ? "도입 상담 시작" : "Google로 시작"}<ArrowRight size={16} /></a>
            </article>
          ))}
        </div>
      </section>

      <section className="final-cta">
        <div>
          <span>READY FOR THE NEXT QUARTER?</span>
          <h2>다음 시장 변화가 오기 전에<br />먼저 준비하세요.</h2>
        </div>
        <a href={authHref}>무료 계정 만들기 <ArrowRight size={18} /></a>
      </section>

      <footer className="landing-footer">
        <AppBrand href="#top" light />
        <p>선박 수주 시장을 더 빠르고 명확하게 읽는 데이터 인텔리전스.</p>
        <span>© 2026 선(船)견지명</span>
      </footer>
    </main>
  );
}
