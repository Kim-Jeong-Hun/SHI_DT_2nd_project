import { useState } from "react";
import { ArrowLeft, ArrowRight, BarChart3, Building2, Check, LineChart, LogOut, Sparkles } from "lucide-react";
import type { AuthUser } from "../../App";
import "../../styles/subscription.css";
import { annualDisplayPrice, displayPriceDisclaimer } from "../../data/displayPricing";
import AppBrand from "../common/AppBrand";
import { LanguageSwitcher } from "../../i18n";

type PlanId = "explore" | "professional" | "enterprise";
const isPlanId = (plan: string | null): plan is PlanId => plan === "explore" || plan === "professional" || plan === "enterprise";

const plans: Array<{
  id: PlanId;
  name: string;
  label: string;
  description: string;
  price?: string;
  icon: typeof LineChart;
  benefits: string[];
  recommended?: boolean;
}> = [
  {
    id: "explore",
    name: "Explore",
    label: "시장 탐색",
    description: "핵심 시장 흐름을 가볍게 확인하는 시작 플랜",
    icon: BarChart3,
    benefits: ["시장 개요 대시보드", "5개 선종 통합 보기", "월간 시장 지표"],
  },
  {
    id: "professional",
    name: "Professional",
    label: "예측 분석",
    description: "수주 전망과 운임을 지속적으로 분석하는 실무 플랜",
    price: annualDisplayPrice.professional,
    icon: LineChart,
    benefits: ["선종별 C+3 수주용량 예측", "수주·운임 비교 차트", "월간 변화 히트맵", "CSV 데이터 내보내기"],
    recommended: true,
  },
  {
    id: "enterprise",
    name: "Enterprise",
    label: "조직 활용",
    description: "조직의 분석 목적에 맞춰 활용 범위를 넓히는 플랜",
    price: annualDisplayPrice.enterprise,
    icon: Building2,
    benefits: ["Professional 모든 기능", "사용자 지정 예측", "예측 데이터 설명", "조직 단위 활용", "데이터 활용 범위 협의"],
  },
];

export default function SubscriptionPage({ user, onSubscribed, onLogout, mode = "onboarding", onBack }: {
  user: AuthUser;
  onSubscribed: (user: AuthUser) => void;
  onLogout: () => void;
  mode?: "onboarding" | "change";
  onBack?: () => void;
}) {
  const currentPlan = isPlanId(user.subscriptionPlan) ? user.subscriptionPlan : null;
  const changing = mode === "change";
  const [selected, setSelected] = useState<PlanId>(changing && currentPlan ? currentPlan : "professional");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState("");
  const currentPlanSelected = changing && selected === currentPlan;

  const subscribe = async () => {
    setSubmitting(true);
    setError("");
    try {
      const response = await fetch("/api/auth/subscription", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ plan: selected }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "구독 플랜을 저장하지 못했습니다.");
      onSubscribed(result.user);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "구독 플랜을 저장하지 못했습니다.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <main className="subscription-shell">
      <header className="subscription-nav">
        <AppBrand onClick={onBack} />
        <div className="subscription-user"><LanguageSwitcher compact /><span>{user.displayName}</span>{changing && onBack ? <button type="button" onClick={onBack}><ArrowLeft size={15} /> 마이페이지로 돌아가기</button> : <button type="button" onClick={onLogout}><LogOut size={15} /> 로그아웃</button>}</div>
      </header>

      <section className="subscription-content">
        {!changing && <div className="subscription-progress" aria-label="가입 진행 단계">
          <span className="complete"><i>1</i> 계정 생성</span><b /><span className="active"><i>2</i> 플랜 선택</span><b /><span><i>3</i> 대시보드</span>
        </div>}
        <div className="subscription-heading">
          <div className="subscription-kicker"><Sparkles size={15} /> CHOOSE YOUR MARKET VIEW</div>
          <h1>{changing ? <>플랜을 비교하고<br />구독을 변경하세요.</> : <>분석 목적에 맞는<br />구독 플랜을 선택하세요.</>}</h1>
          <p>{changing ? "현재 이용 범위와 필요한 기능을 비교한 뒤 플랜을 변경할 수 있습니다." : "선택한 플랜은 계정에 저장되며, 완료 후 바로 대시보드로 이동합니다."}</p>
          <small className="subscription-price-disclaimer">{displayPriceDisclaimer}</small>
        </div>

        <div className="subscription-plans">
          {plans.map(({ id, name, label, description, price, icon: Icon, benefits, recommended }) => (
            <button
              type="button"
              key={id}
              className={`subscription-plan${selected === id ? " selected" : ""}${changing && currentPlan === id ? " current" : ""}`}
              aria-pressed={selected === id}
              onClick={() => setSelected(id)}
            >
              {recommended && <span className="plan-recommended">추천 플랜</span>}
              {changing && currentPlan === id && <span className="plan-current">현재 플랜</span>}
              <div className="plan-radio"><i /></div>
              <div className="plan-icon"><Icon size={21} /></div>
              <small>{label}</small>
              <h2>{name}</h2>
              {price && <strong className="plan-display-price">{price}<span> / 연 · 표시용</span></strong>}
              <p>{description}</p>
              <ul>{benefits.map((benefit) => <li key={benefit}><Check size={16} />{benefit}</li>)}</ul>
            </button>
          ))}
        </div>

        {error && <p className="subscription-error" role="alert">{error}</p>}
        <div className="subscription-action">
          <p>{changing ? "변경한 플랜은 저장 즉시 계정에 반영됩니다." : "베타 운영 기간에는 결제 없이 선택한 플랜으로 시작합니다."}</p>
          <button type="button" onClick={currentPlanSelected ? onBack : subscribe} disabled={submitting || (currentPlanSelected && !onBack)}>{submitting ? "플랜 변경 중..." : currentPlanSelected ? "마이페이지로 돌아가기" : changing ? "선택한 플랜으로 변경" : "선택한 플랜으로 시작"}{currentPlanSelected ? <ArrowLeft size={18} /> : <ArrowRight size={18} />}</button>
        </div>
      </section>
    </main>
  );
}
