/**
 * Legacy comparison series used only by secondary prototype views.
 * The main overview and order forecast use executed-notebook results.
 */
export const MONTHS = ["1월", "2월", "3월", "4월", "5월", "6월", "7월", "8월", "9월"] as const;

export type VesselId = "container" | "tanker" | "bulk" | "gas" | "chemical";
export type VesselSelectionId = VesselId | "all";
export interface VesselMarketData {
  id: VesselId;
  label: string;
  shortLabel: string;
  color: string;
  previous: number[]; // 2025 Jan–Sep, in 만 CGT
  current: number[];  // 2026 Jan–Sep, in 만 CGT
}

export const VESSELS: VesselMarketData[] = [
  {
    id: "container", label: "컨테이너선", shortLabel: "컨테이너선", color: "#3b82f6",
    previous: [48, 52, 55, 62, 58, 61, 68, 64, 59],
    current: [60, 63, 71, 80, 74, 86, 82, 70, 64],
  },
  {
    id: "tanker", label: "유조선", shortLabel: "유조선", color: "#f59e0b",
    previous: [58, 57, 63, 68, 65, 69, 70, 75, 77],
    current: [66, 69, 72, 76, 79, 81, 75, 73, 72],
  },
  {
    id: "bulk", label: "벌크선", shortLabel: "벌크선", color: "#64748b",
    previous: [35, 34, 38, 40, 36, 41, 45, 47, 43],
    current: [32, 34, 36, 35, 37, 39, 42, 40, 38],
  },
  {
    id: "gas", label: "가스 운반선", shortLabel: "가스 운반선", color: "#14b8a6",
    previous: [43, 38, 46, 49, 50, 47, 55, 54, 51],
    current: [50, 48, 45, 58, 61, 64, 68, 70, 75],
  },
  {
    id: "chemical", label: "케미컬 탱커", shortLabel: "케미컬 탱커", color: "#8b5cf6",
    previous: [22, 24, 23, 26, 28, 27, 29, 28, 31],
    current: [25, 28, 27, 32, 30, 29, 31, 33, 35],
  },
];

export const sum = (items: readonly number[]): number => items.reduce((acc, num) => acc + num, 0);
export const ALL_VESSELS: VesselMarketData = {
  id: "container",
  label: "전체 선종",
  shortLabel: "전체 선종",
  color: "#173d70",
  previous: MONTHS.map((_, monthIndex) => sum(VESSELS.map((vessel) => vessel.previous[monthIndex]))),
  current: MONTHS.map((_, monthIndex) => sum(VESSELS.map((vessel) => vessel.current[monthIndex]))),
};
export const changePct = (current: number, previous: number): number =>
  previous === 0 ? 0 : ((current - previous) / previous) * 100;
export const signedPct = (pct: number): string => `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
export const cumulative = (values: readonly number[]): number[] =>
  values.reduce<number[]>((output, value) => [...output, (output.at(-1) ?? 0) + value], []);

/** Flat demo projection: each Q4 month equals the Q3 monthly average. */
export const forecastNextQuarter = (vessel: VesselMarketData): number[] =>
  Array(3).fill(sum(vessel.current.slice(6, 9)) / 3);

export function getMetrics(vessel: VesselMarketData) {
  const yearTotal = sum(vessel.current);
  const priorTotal = sum(vessel.previous);
  const previousQuarter = sum(vessel.current.slice(3, 6)); // Apr–Jun 2026
  const recentQuarter = sum(vessel.current.slice(6, 9));  // Jul–Sep 2026
  const selectedVesselTotal = VESSELS.reduce((total, item) => total + sum(item.current), 0);
  const best = Math.max(...vessel.current);

  return {
    yearTotal,
    yoy: changePct(yearTotal, priorTotal),
    quarterChange: changePct(recentQuarter, previousQuarter),
    share: (yearTotal / selectedVesselTotal) * 100,
    peakMonth: MONTHS[vessel.current.indexOf(best)],
    peakValue: best,
  };
}

/** Percent difference between the same month in 2026 vs. 2025. */
export function monthlyYoY(vessel: VesselMarketData): number[] {
  return vessel.current.map((value, index) => changePct(value, vessel.previous[index]));
}
