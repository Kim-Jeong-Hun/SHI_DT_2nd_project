export const TANKER_NOTEBOOK_FORECAST = {
  notebook: "유조선_(λ1：1, λ2：8)_전체전략_4등_Ridge + XGBoost_Sliding_(Train：60개월)_(ValTest：3개월)_(로그감쇠：on).ipynb",
  result: "동일 노트북의 저장 결과 JSON",
  model: "Ridge + XGBoost",
  strategy: "Sliding · Train 60개월 · Val/Test 3개월 · 로그감쇠 on",
  lambda: "λ1=1, λ2=8",
  validationTestSmape: 60.893686488320384,
  validationTestStd: 45.62580010471329,
  forecasts: [
    { month: "2026-09", dataCutoff: "2026-03", value: 6345458.752153551 },
    { month: "2026-10", dataCutoff: "2026-04", value: 4546959.465764081 },
    { month: "2026-11", dataCutoff: "2026-05", value: 4746444.801602159 },
    { month: "2026-12", dataCutoff: "2026-06", value: 6259956.919594981 },
  ],
} as const;
