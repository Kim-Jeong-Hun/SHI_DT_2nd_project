import { useState } from "react";
import { ArrowLeft, ArrowRight, Bell, Check, CreditCard, LogOut, Mail, ShieldCheck, UserRound } from "lucide-react";
import type { AuthUser } from "../../App";
import AppBrand from "../common/AppBrand";
import { LanguageSwitcher } from "../../i18n";
import "../../styles/my-page.css";

const planNames: Record<string, string> = {
  explore: "Explore",
  professional: "Professional",
  enterprise: "Enterprise",
};

export default function MyPage({ user, darkMode = false, onBack, onUserUpdated, onLogout, onChangePlan }: {
  user: AuthUser;
  darkMode?: boolean;
  onBack: () => void;
  onUserUpdated: (user: AuthUser) => void;
  onLogout: () => void;
  onChangePlan: () => void;
}) {
  const [emailOptIn, setEmailOptIn] = useState(user.emailOptIn === "Y");
  const [marketingOptIn, setMarketingOptIn] = useState(user.marketingOptIn === "Y");
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const savePreferences = async () => {
    setSaving(true);
    setMessage("");
    setError("");
    try {
      const response = await fetch("/api/auth/profile/preferences", {
        method: "PATCH",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ emailOptIn, marketingOptIn }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.error || "수신 설정을 저장하지 못했습니다.");
      onUserUpdated(result.user);
      setMessage("수신 설정이 저장되었습니다.");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "수신 설정을 저장하지 못했습니다.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <main className={`mypage-shell${darkMode ? " mypage-dark" : ""}`}>
      <header className="mypage-nav">
        <AppBrand onClick={onBack} />
        <div className="flex items-center gap-3"><LanguageSwitcher compact /><button className="mypage-back" type="button" onClick={onBack}><ArrowLeft size={16} /> 대시보드로 돌아가기</button></div>
      </header>

      <div className="mypage-layout">
        <aside className="mypage-sidebar">
          <div className="mypage-avatar">{user.avatarUrl ? <img src={user.avatarUrl} alt="" /> : <UserRound size={28} />}</div>
          <strong>{user.displayName}</strong>
          <span>{user.email ?? "이메일 정보 없음"}</span>
          <nav aria-label="마이페이지 메뉴">
            <a href="#account" className="active"><UserRound size={17} /> 계정 정보</a>
            <a href="#subscription"><CreditCard size={17} /> 구독 정보</a>
            <a href="#notifications"><Bell size={17} /> 수신 설정</a>
          </nav>
          <button className="mypage-logout" type="button" onClick={onLogout}><LogOut size={16} /> 로그아웃</button>
        </aside>

        <section className="mypage-content">
          <div className="mypage-heading"><span>MY ACCOUNT</span><h1>마이페이지</h1><p>계정과 구독 정보, 이메일 수신 설정을 관리할 수 있습니다.</p></div>

          <article id="account" className="mypage-card">
            <div className="mypage-card-title"><span><UserRound size={19} /></span><div><h2>계정 정보</h2><p>서비스에서 사용 중인 기본 정보입니다.</p></div></div>
            <dl className="mypage-info-grid">
              <div><dt>이름</dt><dd>{user.displayName}</dd></div>
              <div><dt>이메일</dt><dd>{user.email ?? "등록되지 않음"}</dd></div>
            </dl>
          </article>

          <article id="subscription" className="mypage-card">
            <div className="mypage-card-title"><span><CreditCard size={19} /></span><div><h2>구독 정보</h2><p>현재 계정에 적용된 이용 플랜입니다.</p></div></div>
            <div className="mypage-plan">
              <div><small>CURRENT PLAN</small><strong>{user.subscriptionPlan ? planNames[user.subscriptionPlan] ?? user.subscriptionPlan : "선택된 플랜 없음"}</strong></div>
              <span className={user.subscriptionStatus === "Y" ? "active" : "inactive"}><i />{user.subscriptionStatus === "Y" ? "구독 중" : "미구독"}</span>
            </div>
            <div className="mypage-plan-manage">
              <p>플랜별 기능과 이용 범위를 비교한 뒤 구독을 변경할 수 있습니다.</p>
              <button type="button" onClick={onChangePlan}>플랜 비교 및 변경 <ArrowRight size={16} /></button>
            </div>
          </article>

          <article id="notifications" className="mypage-card">
            <div className="mypage-card-title"><span><Mail size={19} /></span><div><h2>이메일 수신 설정</h2><p>원하는 정보만 선택해서 받아보세요.</p></div></div>
            <div className="mypage-preference-list">
              <label>
                <span><b>시장 리포트 및 서비스 알림</b><small>주요 시장 리포트와 서비스 운영 관련 이메일을 받습니다.</small></span>
                <input type="checkbox" checked={emailOptIn} onChange={(event) => setEmailOptIn(event.target.checked)} /><i />
              </label>
              <label>
                <span><b>광고성 정보 수신</b><small>이벤트, 혜택과 새로운 상품 안내 이메일을 받습니다.</small></span>
                <input type="checkbox" checked={marketingOptIn} onChange={(event) => setMarketingOptIn(event.target.checked)} /><i />
              </label>
            </div>
            <div className="mypage-save-row">
              <div>{message && <span className="mypage-success"><Check size={15} />{message}</span>}{error && <span className="mypage-error">{error}</span>}</div>
              <button type="button" onClick={savePreferences} disabled={saving}>{saving ? "저장 중..." : "설정 저장"}</button>
            </div>
          </article>

          <div className="mypage-security"><ShieldCheck size={18} /><span>계정 및 세션 정보는 안전하게 암호화되어 관리됩니다.</span></div>
        </section>
      </div>
    </main>
  );
}
