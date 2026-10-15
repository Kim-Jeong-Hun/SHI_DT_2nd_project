import type { VesselId } from "./mockMarket";

export type NotebookVesselId = VesselId;

export interface ForecastDriver {
  label: string;
  share: number;
}

export interface NotebookForecast {
  vesselId: NotebookVesselId;
  vesselName: string;
  unit: "DWT" | "TEU" | "CBM";
  color: string;
  monthly: readonly { month: string; value: number }[];
  q3: number;
  q4: number;
  quarterChange: number;
  peakMonth: string;
  model: string;
  strategy: string;
  featureCount: number;
  validationMae: number;
  testMae: number;
  testRelativeError: number;
  peakTimingError: number;
  conformalRadius90: number;
  conformalCalibrationSize: number;
  drivers: readonly ForecastDriver[];
  signal: string;
  action: string;
}

// 90% three-month block-conformal radius: group the saved rolling-origin
// Validation and Test absolute errors into non-overlapping three-month blocks,
// take each block maximum, then select ceil((n + 1) × 0.9)-th ordered score.
// The portfolio radius retains its existing 39-common-month calibration.
export const PORTFOLIO_CONFORMAL_90 = { radius: 31.6614139278166, calibrationSize: 39 } as const;

export const NOTEBOOK_FORECASTS: Record<NotebookVesselId, NotebookForecast> = {
  tanker: {
    vesselId: "tanker", vesselName: "유조선", unit: "DWT", color: "#f59e0b",
    monthly: [
      { month: "2026-07", value: 6_887_673 }, { month: "2026-08", value: 5_162_121.8 },
      { month: "2026-09", value: 5_565_243.9 }, { month: "2026-10", value: 7_932_270.7 },
      { month: "2026-11", value: 3_905_281.8 }, { month: "2026-12", value: 7_222_775.3 },
    ],
    q3: 17_615_038.7, q4: 19_060_327.8, quarterChange: 8.2, peakMonth: "10월",
    model: "Quantile Regression", strategy: "Sliding 60개월 · Uniform · VIF 10",
    featureCount: 20, validationMae: 1_651_039.99, testMae: 5_346_151.1,
    testRelativeError: 47.39, peakTimingError: 0.76,
    conformalRadius90: 5_926_307.29, conformalCalibrationSize: 25,
    drivers: [
      { label: "WTI 가격 변화 · 0→7개월", share: 17.658 }, { label: "신조선가 · 3개월 전", share: 11.146 },
      { label: "행동 GPRA · 9개월 전", share: 10.811 }, { label: "미국 원유 수입 톤마일 · 1개월 전", share: 10.147 },
    ],
    signal: "4분기 누적 수주용량은 3분기보다 8.2% 증가하고 10월에 고점을 형성할 전망입니다.",
    action: "10월 집중 이후 11월 조정과 12월 반등을 함께 고려해 슬롯과 기자재 투입을 단계적으로 배분해야 합니다.",
  },
  container: {
    vesselId: "container", vesselName: "컨테이너선", unit: "TEU", color: "#3b82f6",
    monthly: [
      { month: "2026-07", value: 215_865.9 }, { month: "2026-08", value: 188_242.4 },
      { month: "2026-09", value: 417_651.2 }, { month: "2026-10", value: 214_383.3 },
      { month: "2026-11", value: 697_579.1 }, { month: "2026-12", value: 513_137.1 },
    ],
    q3: 821_759.5, q4: 1_425_099.5, quarterChange: 73.4, peakMonth: "11월",
    model: "Tweedie Regression + XGBoost 동일가중 앙상블", strategy: "Adaptive 24·36·48·60개월 · Uniform · VIF 10",
    featureCount: 10, validationMae: 294_511.97, testMae: 164_830.83,
    testRelativeError: 18.4, peakTimingError: 0.71,
    conformalRadius90: 440_355.88, conformalCalibrationSize: 25,
    drivers: [
      { label: "핵위협 · 5개월 전", share: 21.461 }, { label: "북유럽→극동 컨테이너 운임 · 3개월 전", share: 15.164 },
      { label: "공급망 압력 변화 · 5→9개월", share: 14.689 }, { label: "미국 TPU·Caldara · 1개월 전", share: 9.906 },
    ],
    signal: "4분기 누적 수주용량은 3분기보다 73.4% 증가하고 11월에 고점을 형성할 전망입니다.",
    action: "11월 수요 집중 가능성을 영업 파이프라인과 대조하고 12월 조정까지 포함해 슬롯을 배분해야 합니다.",
  },
  chemical: {
    vesselId: "chemical", vesselName: "케미컬 탱커", unit: "DWT", color: "#8b5cf6",
    monthly: [
      { month: "2026-07", value: 362_575 }, { month: "2026-08", value: 338_177.8 },
      { month: "2026-09", value: 371_781.9 }, { month: "2026-10", value: 597_456.9 },
      { month: "2026-11", value: 389_675.2 }, { month: "2026-12", value: 476_303.8 },
    ],
    q3: 1_072_534.7, q4: 1_463_435.9, quarterChange: 36.4, peakMonth: "10월",
    model: "XGBoost", strategy: "Adaptive 24·36·48개월 · Uniform · VIF 10",
    featureCount: 16, validationMae: 374_156.54, testMae: 294_277.88,
    testRelativeError: 25.76, peakTimingError: 0.92,
    conformalRadius90: 427_731.03, conformalCalibrationSize: 21,
    drivers: [
      { label: "전쟁·평화위협 · 8개월 전", share: 29.201 }, { label: "중국 TPU 변화 · 2→7개월", share: 13.568 },
      { label: "원달러 환율 · 7개월 전", share: 11.611 }, { label: "세계 실질수출 · 9개월 전", share: 6.072 },
    ],
    signal: "4분기 누적 수주용량은 3분기보다 36.4% 증가하고 10월에 고점을 형성할 전망입니다.",
    action: "10월 급증 뒤 11월 조정 가능성을 반영하고 지정학·환율 신호를 가격 조건과 함께 점검해야 합니다.",
  },
  gas: {
    vesselId: "gas", vesselName: "가스 운반선", unit: "CBM", color: "#14b8a6",
    monthly: [
      { month: "2026-07", value: 933_421.7 }, { month: "2026-08", value: 907_717.4 },
      { month: "2026-09", value: 886_132 }, { month: "2026-10", value: 937_319.3 },
      { month: "2026-11", value: 972_129.6 }, { month: "2026-12", value: 606_032.4 },
    ],
    q3: 2_727_271.1, q4: 2_515_481.3, quarterChange: -7.8, peakMonth: "11월",
    model: "Huber Regression", strategy: "Sliding 36개월 · Uniform · VIF 10",
    featureCount: 6, validationMae: 1_469_521.91, testMae: 2_736_566.51,
    testRelativeError: 69.02, peakTimingError: 0.41,
    conformalRadius90: 3_584_071.46, conformalCalibrationSize: 25,
    drivers: [
      { label: "가스 리그 · 1개월 전", share: 31.242 }, { label: "수에즈 전체선박 통과횟수 · 3개월 전", share: 23.475 },
      { label: "수주용량 · 확보월 2개월 전", share: 16.598 }, { label: "GPR 3개월 변화 · 1→9개월", share: 16.014 },
    ],
    signal: "4분기 누적 수주용량은 3분기보다 7.8% 감소하고 11월 이후 둔화될 전망입니다.",
    action: "11월 단기 고점 이후 하락 가능성을 반영하고 가스 리그와 수에즈 운항량을 확인하며 설비 투입 속도를 조절해야 합니다.",
  },
  bulk: {
    vesselId: "bulk", vesselName: "벌크선", unit: "DWT", color: "#64748b",
    monthly: [
      { month: "2026-07", value: 3_546_298 }, { month: "2026-08", value: 5_718_193.7 },
      { month: "2026-09", value: 13_103_346.3 }, { month: "2026-10", value: 9_788_658.7 },
      { month: "2026-11", value: 9_233_087.6 }, { month: "2026-12", value: 11_186_555.2 },
    ],
    q3: 22_367_838, q4: 30_208_301.5, quarterChange: 35.1, peakMonth: "9월",
    model: "PLS Regression", strategy: "Sliding 24개월 · Uniform · VIF 10",
    featureCount: 14, validationMae: 1_484_652.75, testMae: 3_169_833.06,
    testRelativeError: 42.16, peakTimingError: 0.76,
    conformalRadius90: 3_950_400, conformalCalibrationSize: 25,
    drivers: [
      { label: "수에즈 전체선박 순톤수 · 1개월 전", share: 15.43 }, { label: "비료 가격지수 변화 · 0→1개월", share: 10.358 },
      { label: "핵위협 변화 · 0→5개월", share: 8.655 }, { label: "벌크선 운임 BDI · 3개월 전", share: 8.199 },
    ],
    signal: "4분기 누적 수주용량은 3분기보다 35.1% 증가하고 12월에 재상승할 전망입니다.",
    action: "9월 급증 이후 10~11월 조정을 거쳐 12월 반등하는 흐름을 전제로 도크와 원자재 조달 일정을 점검해야 합니다.",
  },
};

export const NOTEBOOK_VESSEL_IDS = Object.keys(NOTEBOOK_FORECASTS) as NotebookVesselId[];

export function isNotebookVessel(id: VesselId): id is NotebookVesselId {
  return id in NOTEBOOK_FORECASTS;
}
