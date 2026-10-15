import { useEffect, useState } from "react";
import MarketDashboard from "./components/dashboard/MarketDashboard";
import LandingPage from "./components/landing/LandingPage";
import SubscriptionPage from "./components/subscription/SubscriptionPage";
import { useDashboardStore } from "./store/useDashboardStore";

export type AuthUser = {
  id: string;
  email: string | null;
  displayName: string;
  avatarUrl: string | null;
  subscriptionStatus: "Y" | "N";
  subscriptionPlan: string | null;
  emailOptIn: "Y" | "N";
  marketingOptIn: "Y" | "N";
};

function initialAuthError() {
  const reason = new URL(window.location.href).searchParams.get("auth_error");
  if (!reason) return "";
  if (reason === "not_configured" || reason === "oauth_configuration") {
    return "Google 로그인 설정을 확인하고 있습니다. 잠시 후 다시 시도해 주세요.";
  }
  return "Google 로그인을 완료하지 못했습니다. 다시 시도해 주세요.";
}

export default function App() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(initialAuthError);
  const enterDashboard = (nextUser: AuthUser) => {
    useDashboardStore.getState().setVesselId("all");
    setUser(nextUser);
  };

  const loadUser = async (signal?: AbortSignal) => {
    try {
      const response = await fetch("/api/auth/me", { credentials: "same-origin", signal });
      if (response.status === 401) {
        setUser(null);
      } else if (response.ok) {
        const data: { user: AuthUser } = await response.json();
        enterDashboard(data.user);
        setError("");
      } else {
        throw new Error("인증 서버에 연결하지 못했습니다.");
      }
    } catch (cause) {
      if (signal?.aborted) return;
      setError(cause instanceof Error ? cause.message : "로그인 상태를 확인하지 못했습니다.");
    } finally {
      if (!signal?.aborted) setLoading(false);
    }
  };

  useEffect(() => {
    const controller = new AbortController();
    const url = new URL(window.location.href);
    if (url.searchParams.has("auth_error")) {
      url.searchParams.delete("auth_error");
      window.history.replaceState({}, "", url);
    }
    void loadUser(controller.signal);
    return () => controller.abort();
  }, []);

  const logout = async () => {
    try {
      const response = await fetch("/api/auth/logout", {
        method: "POST",
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("로그아웃에 실패했습니다.");
      setUser(null);
      setError("");
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "로그아웃에 실패했습니다.");
    }
  };

  if (loading) return <div className="grid min-h-screen place-items-center bg-[#f5f7fb] text-slate-600">로그인 상태 확인 중...</div>;
  if (user && user.subscriptionStatus !== "Y") return <SubscriptionPage user={user} onSubscribed={enterDashboard} onLogout={logout} />;
  if (user) return <MarketDashboard user={user} onUserUpdated={setUser} onLogout={logout} authError={error} />;

  return <LandingPage error={error} onRetry={() => { setLoading(true); void loadUser(); }} onAuthenticated={enterDashboard} />;
}
