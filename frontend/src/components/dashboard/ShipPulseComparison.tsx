import { BarChart3, ShieldCheck } from "lucide-react";

export default function ShipPulseComparison() {
  return (
    <main className="mx-auto w-full max-w-[1536px] px-3 py-4 md:px-5 md:py-5">
      <section className="mb-4 flex flex-wrap items-center justify-between gap-4 rounded-2xl border border-slate-200/85 bg-white px-5 py-4 shadow-[0_4px_24px_rgba(21,44,79,0.035)] md:px-6">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-blue-50 text-blue-700">
            <BarChart3 className="h-5 w-5" />
          </span>
          <div>
            <div className="flex flex-wrap items-center gap-2">
              <h1 className="text-xl font-bold tracking-[-0.04em] text-slate-900 md:text-2xl">ShipPulse 지표 비교</h1>
              <span className="rounded-full bg-slate-900 px-2.5 py-1 text-[10px] font-bold tracking-[0.12em] text-white">ENTERPRISE</span>
            </div>
            <p className="mt-1.5 text-sm leading-6 text-slate-500">선종별 수주용량과 시장 지표를 같은 시계열에서 비교하고 자료 공개 시차를 점검합니다.</p>
          </div>
        </div>
        <span className="flex items-center gap-2 text-xs font-semibold text-emerald-700"><ShieldCheck className="h-4 w-4" />Enterprise 전용 보안 화면</span>
      </section>

      <section className="overflow-hidden rounded-2xl border border-slate-200/85 bg-white shadow-[0_4px_24px_rgba(21,44,79,0.035)]">
        <iframe
          title="ShipPulse 지표 비교"
          src="/api/v1/ship-pulse"
          sandbox="allow-scripts allow-same-origin allow-downloads allow-popups"
          className="h-[calc(100vh-190px)] min-h-[760px] w-full border-0 bg-slate-50"
        />
      </section>
    </main>
  );
}
