const displayUsdKrwRate = 1341.36;

const roundedKrw = (usd: number) =>
  Math.round((usd * displayUsdKrwRate) / 1000) * 1000;

const formatKrw = (amount: number) =>
  `₩${new Intl.NumberFormat("ko-KR").format(amount)}`;

export const annualDisplayPrice = {
  professional: formatKrw(roundedKrw(1_000)),
  enterprise: formatKrw(roundedKrw(10_000)),
};

export const displayPriceDisclaimer =
  "USD/KRW 1,341.36 기준(2026.10.13), 화면 표시용 환산 가격이며 실제 결제 금액이 아닙니다.";
