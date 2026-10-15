import { useEffect, useState } from "react";
import { Anchor, ArrowLeft, ArrowRight, Boxes, CalendarDays, ExternalLink, ImageOff, Pause, Play, Ship, TrendingUp } from "lucide-react";
import type { LucideIcon } from "lucide-react";
import EChartsReact from "../common/LocalizedECharts";

type NewsCategory = "조선" | "해운" | "물류";
type NewsStory = {
  id: number;
  sourceName: string;
  category: NewsCategory;
  title: string;
  articleUrl: string;
  publishedAt: string;
  imageUrl: string | null;
  imageAlt: string | null;
};

type NewsroomResponse = { featured: NewsStory[]; articles: NewsStory[] };

const categoryVisuals: Record<NewsCategory, { icon: LucideIcon; tone: string; label: string }> = {
  조선: { icon: Ship, tone: "from-sky-950 via-blue-900 to-cyan-700", label: "SHIPBUILDING" },
  해운: { icon: Anchor, tone: "from-indigo-950 via-indigo-800 to-blue-600", label: "SHIPPING" },
  물류: { icon: Boxes, tone: "from-slate-900 via-slate-800 to-teal-700", label: "LOGISTICS" },
};

const formatDate = (value: string) => new Intl.DateTimeFormat("ko-KR", { year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(value));

function StoryArtwork({ icon: Icon, tone, label, imageUrl, imageAlt }: { icon: LucideIcon; tone: string; label?: string; imageUrl: string | null; imageAlt: string | null }) {
  return (
    <div className={`relative isolate flex h-full min-h-44 items-center justify-center overflow-hidden bg-gradient-to-br ${tone}`}>
      {imageUrl && <img src={imageUrl} alt={imageAlt ?? ""} loading="lazy" referrerPolicy="no-referrer" className="absolute inset-0 h-full w-full object-cover" onError={(event) => { event.currentTarget.style.display = "none"; }} />}
      {imageUrl && <div className="absolute inset-0 bg-gradient-to-t from-slate-950/55 via-slate-950/5 to-transparent" />}
      <div className="absolute -right-8 -bottom-16 h-48 w-48 rounded-full border border-white/10" />
      <div className="absolute -right-1 -bottom-9 h-32 w-32 rounded-full border border-white/15" />
      <div className="absolute top-5 left-6 h-px w-14 bg-white/25" />
      <Icon aria-hidden="true" className="relative h-14 w-14 text-white/75 drop-shadow-lg" strokeWidth={1.15} />
      {label && <span className="absolute top-5 left-6 text-[10px] font-semibold tracking-[0.22em] text-white/65">{label}</span>}
      <span className="absolute right-5 bottom-4 text-[10px] font-medium tracking-[0.18em] text-white/55">INDUSTRY BRIEF</span>
    </div>
  );
}

const yearlyNewsYears = [2026, 2025, 2024, 2023, 2022];
const yearlyNewsVessels = ["컨테이너선", "유조선", "벌크선", "가스 운반선", "케미컬 탱커"] as const;
type YearlyNewsVessel = (typeof yearlyNewsVessels)[number];
type YearlyNewsItem = { source: string; title: string; month: string; publishedAt: string; articleUrl: string };
type YearlyOrderPoint = { month: number; value: number };
type TurningPoint = YearlyOrderPoint & { kind: "고점" | "저점"; score: number };
type MasterDataResponse = { rows: Array<{ period: string; orderCapacity: string | null }> };

const yearlyVesselMeta: Record<YearlyNewsVessel, { id: string; unit: "DWT" | "TEU" | "CBM"; color: string }> = {
  컨테이너선: { id: "container", unit: "TEU", color: "#2563eb" },
  유조선: { id: "tanker", unit: "DWT", color: "#f59e0b" },
  벌크선: { id: "bulk", unit: "DWT", color: "#64748b" },
  "가스 운반선": { id: "gas", unit: "CBM", color: "#14b8a6" },
  "케미컬 탱커": { id: "chemical", unit: "DWT", color: "#8b5cf6" },
};

const formatCompactOrder = (value: number) => value >= 1_000_000
  ? `${(value / 1_000_000).toFixed(1)}M`
  : value >= 1_000 ? `${(value / 1_000).toFixed(0)}K` : value.toFixed(0);

const findMajorTurningPoints = (points: readonly YearlyOrderPoint[]): TurningPoint[] => {
  const candidates = points.slice(1, -1).map((point, index) => {
    const previous = points[index];
    const next = points[index + 2];
    const incoming = point.value - previous.value;
    const outgoing = next.value - point.value;
    const isTurningPoint = incoming !== 0 && outgoing !== 0 && Math.sign(incoming) !== Math.sign(outgoing);
    return isTurningPoint ? {
      ...point,
      kind: incoming > 0 ? "고점" as const : "저점" as const,
      score: Math.min(Math.abs(incoming), Math.abs(outgoing)),
    } : null;
  }).filter((point): point is TurningPoint => point !== null);

  if (candidates.length < 2) {
    points.slice(1, -1).forEach((point, index) => {
      if (candidates.some((candidate) => candidate.month === point.month)) return;
      const previous = points[index];
      const next = points[index + 2];
      candidates.push({
        ...point,
        kind: point.value >= (previous.value + next.value) / 2 ? "고점" : "저점",
        score: Math.abs(point.value * 2 - previous.value - next.value),
      });
    });
  }

  return candidates.sort((a, b) => b.score - a.score).slice(0, 2).sort((a, b) => a.month - b.month);
};

const articleImageUrl = (articleUrl: string) => {
  const query = new URLSearchParams({
    url: articleUrl,
    "meta.image": "true",
    filter: "image.url",
    ping: "false",
    prerender: "false",
    javascript: "false",
    embed: "image.url",
  });

  return `https://api.microlink.io?${query.toString()}`;
};

const yearlyNewsArchive: Record<number, Record<YearlyNewsVessel, YearlyNewsItem[]>> = {
  2022: {
    컨테이너선: [
      { source: "S&P Global", title: "컨테이너 현물 운임, 장기계약 운임 아래로 하락", month: "9월", publishedAt: "2022. 09. 02.", articleUrl: "https://www.spglobal.com/commodity-insights/en/news-research/latest-news/shipping/090222-container-freight-spot-market-continues-to-sit-below-contracted-rates" },
      { source: "FreightWaves", title: "컨테이너 호황 종료와 운임 급락, 2022년 해운시장 결산", month: "12월", publishedAt: "2022. 12. 30.", articleUrl: "https://www.freightwaves.com/news/2022s-top-shipping-stories-container-boom-ends-war-fuels-tankers" },
    ],
    유조선: [
      { source: "S&P Global", title: "에너지 위기로 석유제품선 운임 수익 세 배 증가", month: "7월", publishedAt: "2022. 07. 27.", articleUrl: "https://www.spglobal.com/energy/en/news-research/latest-news/shipping/072722-ardmore-mr-freight-earnings-triple-as-energy-crisis-deepens-product-tanker-dislocations" },
      { source: "Reuters · Euronews", title: "러시아산 원유 제재가 유조선 운임을 끌어올리다", month: "11월", publishedAt: "2022. 11. 28.", articleUrl: "https://www.euronews.com/next/2022/11/28/shipping-oil-tankers" },
    ],
    벌크선: [
      { source: "Axios", title: "러시아·우크라이나, 흑해 곡물 수출 재개 협정 체결", month: "7월", publishedAt: "2022. 07. 22.", articleUrl: "https://www.axios.com/2022/07/22/russia-ukraine-grain-export-deal-black-sea-blockade" },
      { source: "The Washington Post", title: "우크라이나 오데사에서 첫 곡물선 출항", month: "8월", publishedAt: "2022. 08. 01.", articleUrl: "https://www.washingtonpost.com/world/2022/08/01/ukraine-grain-deal-odessa-shipments-resume/" },
    ],
    "가스 운반선": [
      { source: "Qatar Tribune", title: "카타르에너지, LNG 운반선 최대 100척 확보 계획", month: "9월", publishedAt: "2022. 09. 24.", articleUrl: "https://www.qatar-tribune.com/article/21422/business/qatar-may-order-up-to-100-lng-carriers-to-support-nf-expansion-project-kaabi" },
      { source: "FreightWaves", title: "유럽 에너지 위기로 LNG선 현물 운임 사상 최고", month: "12월", publishedAt: "2022. 12. 30.", articleUrl: "https://www.freightwaves.com/news/2022s-top-shipping-stories-container-boom-ends-war-fuels-tankers" },
    ],
    "케미컬 탱커": [
      { source: "S&P Global", title: "제품·케미컬 탱커 공급 부족으로 운임 수익 급등", month: "7월", publishedAt: "2022. 07. 27.", articleUrl: "https://www.spglobal.com/energy/en/news-research/latest-news/shipping/072722-ardmore-mr-freight-earnings-triple-as-energy-crisis-deepens-product-tanker-dislocations" },
      { source: "Maritime London", title: "2022년 해운 운임지수 사상 최고, 케미컬 탱커도 강세", month: "12월", publishedAt: "2022. 12. 30.", articleUrl: "https://www.maritimelondon.com/news/clarksea-index-hit-record-annual-average-for-2022" },
    ],
  },
  2023: {
    컨테이너선: [
      { source: "FreightWaves", title: "전쟁·가뭄·우회가 뒤흔든 2023년 컨테이너 해운", month: "12월", publishedAt: "2023. 12. 19.", articleUrl: "https://www.freightwaves.com/news/top-ocean-shipping-stories-of-2023-war-drought-and-detours" },
      { source: "The Washington Post", title: "홍해 공격으로 주요 선사들이 아프리카 우회 시작", month: "12월", publishedAt: "2023. 12. 21.", articleUrl: "https://www.washingtonpost.com/world/2023/12/21/red-sea-shipping-houthi-suez/" },
    ],
    유조선: [
      { source: "The Guardian", title: "러시아산 원유를 운송하는 그림자 유조선단 확대", month: "8월", publishedAt: "2023. 08. 19.", articleUrl: "https://www.theguardian.com/business/2023/aug/19/the-dark-fleet-of-tankers-shipping-russian-oil-in-the-shadows" },
      { source: "Axios", title: "미국, 러시아 원유 가격상한 회피 그림자 선단 겨냥", month: "12월", publishedAt: "2023. 12. 06.", articleUrl: "https://www.axios.com/2023/12/06/us-russia-shadow-fleet-oil-prices" },
    ],
    벌크선: [
      { source: "AP", title: "극심한 가뭄으로 파나마 운하 일일 통항량 축소", month: "9월", publishedAt: "2023. 09. 30.", articleUrl: "https://apnews.com/article/061ce1797cb9b0fb8ea7ab44ba04bdf1" },
      { source: "FreightWaves", title: "파나마 운하 위기로 미국 곡물선이 수에즈로 우회", month: "11월", publishedAt: "2023. 11. 09.", articleUrl: "https://www.freightwaves.com/news/panama-canal-crisis-forces-us-farm-exports-to-detour-through-suez" },
    ],
    "가스 운반선": [
      { source: "QatarEnergy", title: "카타르 노스필드 사우스 LNG 확장사업 EPC 계약", month: "5월", publishedAt: "2023. 05. 16.", articleUrl: "https://www.qatarenergy.qa/en/MediaCenter/Pages/newsdetails.aspx?ItemId=3757" },
      { source: "The Motorship", title: "카타르에너지, 두 번째 LNG선 대규모 발주 시작", month: "9월", publishedAt: "2023. 09. 28.", articleUrl: "https://www.motorship.com/general-news/qatarenergy-signals-beginning-of-second-round-of-lng-orders/1487828.article" },
    ],
    "케미컬 탱커": [
      { source: "Offshore Energy", title: "시리우스, 메탄올 대응 석유·케미컬 탱커 발주", month: "9월", publishedAt: "2023. 09. 07.", articleUrl: "https://www.offshore-energy.biz/2023/09/07/sirius-shipping-orders-22-methanol-ready-oil-chemical-tankers" },
      { source: "AP", title: "홍해에서 노르웨이 국적 석유·케미컬 탱커 피격", month: "12월", publishedAt: "2023. 12. 12.", articleUrl: "https://apnews.com/article/946b40e6393af6216c0b6ef734311be9" },
    ],
  },
  2024: {
    컨테이너선: [
      { source: "U.S. EIA", title: "홍해 공격으로 항해거리와 컨테이너·에너지 운임 상승", month: "1월", publishedAt: "2024. 01. 25.", articleUrl: "https://www.eia.gov/TodayinEnergy/detail.php?id=61363" },
      { source: "UNCTAD", title: "홍해·수에즈·파나마 병목이 세계 해운을 재편", month: "10월", publishedAt: "2024. 10. 22.", articleUrl: "https://unctad.org/system/files/official-document/rmt2024_en.pdf" },
    ],
    유조선: [
      { source: "U.S. EIA", title: "홍해 우회로 석유제품선 운임과 톤마일 증가", month: "1월", publishedAt: "2024. 01. 25.", articleUrl: "https://www.eia.gov/TodayinEnergy/detail.php?id=61363" },
      { source: "Argus Media", title: "홍해에서 원유 유조선 연쇄 공격, 시장 위험 확대", month: "9월", publishedAt: "2024. 09. 03.", articleUrl: "https://www.argusmedia.com/-/media/project/argusmedia/mainsite/english/images/downloadable-content/argus-tanker-freight-20240903.pdf" },
    ],
    벌크선: [
      { source: "UNCTAD", title: "주요 해상 병목과 원자재 운송망의 구조적 위험", month: "10월", publishedAt: "2024. 10. 22.", articleUrl: "https://unctad.org/system/files/official-document/rmt2024_en.pdf" },
      { source: "Clarksons Research", title: "시만두 철광석 프로젝트가 벌크선 수요 변수로 부상", month: "11월", publishedAt: "2024. 11. 12.", articleUrl: "https://drybulkterminals.org/wp-content/uploads/2024/11/16.-Clarksons-Research-David-Whittaker.pdf" },
    ],
    "가스 운반선": [
      { source: "AP", title: "홍해 사태로 카타르 LNG 화물도 희망봉 우회", month: "1월", publishedAt: "2024. 01. 24.", articleUrl: "https://apnews.com/article/ef0b83ef2a7ca8c727288b50037287e5" },
      { source: "Rigzone", title: "카타르에너지 LNG선 건조 물량 100척 돌파", month: "4월", publishedAt: "2024. 04. 02.", articleUrl: "https://www.rigzone.com/news/qatarenergy_now_has_over_100_lng_ships_under_construction-02-apr-2024-176267-article/" },
    ],
    "케미컬 탱커": [
      { source: "ICIS", title: "홍해 불안 속 액체화학제품 운임과 물류 변동 확대", month: "5월", publishedAt: "2024. 05. 17.", articleUrl: "https://www.icis.com/explore/resources/news/2024/05/17/11000362/logistics-container-rates-continue-to-surge-liquid-chem-tanker-rates-mostly-lower" },
      { source: "AP", title: "홍해에서 라이베리아 국적 케미컬 탱커 피격", month: "10월", publishedAt: "2024. 10. 10.", articleUrl: "https://apnews.com/article/961fbf91e97e071011ad3bea9077511a" },
    ],
  },
  2025: {
    컨테이너선: [
      { source: "Supply Chain Dive", title: "미국, 중국 관련 선박에 대한 항만 수수료 확정", month: "4월", publishedAt: "2025. 04. 18.", articleUrl: "https://www.supplychaindive.com/news/us-proceeds-china-linked-ship-fees/745731/" },
      { source: "FreightWaves", title: "태평양 컨테이너 운임, 홍해 위기 이전 수준으로 하락", month: "8월", publishedAt: "2025. 08. 22.", articleUrl: "https://www.freightwaves.com/news/trans-pacific-container-rates-fall-to-pre-red-sea-crisis-levels" },
    ],
    유조선: [
      { source: "The Washington Post", title: "미국, 러시아 석유기업과 유조선 183척 대규모 제재", month: "1월", publishedAt: "2025. 01. 10.", articleUrl: "https://www.washingtonpost.com/national-security/2025/01/10/russia-oil-sanctions-shadow-ships-biden/" },
      { source: "AP", title: "EU·영국, 러시아 그림자 선단 약 200척 추가 제재", month: "5월", publishedAt: "2025. 05. 20.", articleUrl: "https://apnews.com/article/02d78e4aeda205391f72dfccdc005561" },
    ],
    벌크선: [
      { source: "Lloyd's List", title: "철광석 선적 7% 감소가 벌크선 운임 압박", month: "2월", publishedAt: "2025. 02. 20.", articleUrl: "https://www.lloydslist.com/-/media/lloyds-list/daily-pdf/2025/02-february/dailypdf200225v2.pdf" },
      { source: "Argus Media", title: "석탄 물동량 감소로 세계 벌크 교역 위축 전망", month: "6월", publishedAt: "2025. 06. 06.", articleUrl: "https://www.argusmedia.com/en/news-and-insights/latest-market-news/2689055-global-dry-bulk-trade-to-contract-in-2025-star-bulk" },
    ],
    "가스 운반선": [
      { source: "S&P Global", title: "LNG선 운임, 선복 과잉으로 사상 최저 수준", month: "1월", publishedAt: "2025. 01. 23.", articleUrl: "https://www.spglobal.com/energy/en/news-research/latest-news/shipping/012325-lng-freight-rates-witness-historic-lows-as-market-tackles-drastic-downturn" },
      { source: "Journal of Petroleum Technology", title: "화물보다 빠르게 늘어난 LNG선, 공급과잉 심화", month: "4월", publishedAt: "2025. 04. 01.", articleUrl: "https://jpt.spe.org/too-many-boats-not-enough-cargoes-lng-carrier-oversupply-drives-rates-to-historic-lows-restricted" },
    ],
    "케미컬 탱커": [
      { source: "Offshore Energy", title: "중국 조선소들, 스테인리스 케미컬 탱커 수주 확대", month: "2월", publishedAt: "2025. 02. 18.", articleUrl: "https://www.offshore-energy.biz/chinese-shipyards-win-orders-for-stainless-steel-chemical-tankers/" },
      { source: "Scorpio Tankers", title: "케미컬 탱커 발주잔량 증가와 선복 압력 확대", month: "4월", publishedAt: "2025. 04. 04.", articleUrl: "https://www.scorpiotankers.com/wp-content/uploads/2025/04/STNG-2024-20-F-vF.pdf" },
    ],
  },
  2026: {
    컨테이너선: [
      { source: "AP", title: "후티 반군, 홍해 관문에서 사우디 연계 선박 봉쇄 위협", month: "7월", publishedAt: "2026. 07. 20.", articleUrl: "https://apnews.com/article/fd7c4a3911f7eee18251483fc8af768c" },
      { source: "FreightWaves", title: "홍해 항로 복귀 움직임 속 위험과 운임 하락 압력 공존", month: "9월", publishedAt: "2026. 09. 15.", articleUrl: "https://www.freightwaves.com/news/houthi-gains-deepen-risk-as-carriers-restore-red-sea-services" },
    ],
    유조선: [
      { source: "IMO", title: "호르무즈 해협 유조선 공격과 선원 피해 공식 규탄", month: "6월", publishedAt: "2026. 06. 11.", articleUrl: "https://www.imo.org/en/mediacentre/pressbriefings/pages/imo-statement-on-settebello-attack.aspx" },
      { source: "Reuters · Al-Monitor", title: "호르무즈 유조선 통항 사실상 중단", month: "7월", publishedAt: "2026. 07. 09.", articleUrl: "https://www.al-monitor.com/originals/2026/07/oil-tanker-traffic-through-hormuz-near-standstill-attacks-strain-iran-truce" },
    ],
    벌크선: [
      { source: "Pacific Basin", title: "공급 증가가 수요를 앞서는 2026년 벌크선 시장 전망", month: "3월", publishedAt: "2026. 03. 19.", articleUrl: "https://www.hkexnews.hk/listedco/listconews/sehk/2026/0319/2026031900586.pdf" },
      { source: "Vessel Hunter", title: "COSCO, 뉴캐슬막스 벌크선 15척 발주 승인", month: "8월", publishedAt: "2026. 08. 01.", articleUrl: "https://vesselhunter.io/news/topic/dry-bulk" },
    ],
    "가스 운반선": [
      { source: "ADNOC L&S", title: "차세대 LNG 운반선 여섯 번째 선박 인도", month: "4월", publishedAt: "2026. 04. 27.", articleUrl: "https://adnocls.ae/en/news-and-media/press-releases/2026/al-taweelah-delivery-of-sixth-next-generation-lng-carrier" },
      { source: "MarineLink", title: "SK해운, 아시아 최대 LNG선 운영사로 재편", month: "8월", publishedAt: "2026. 08. 12.", articleUrl: "https://ws19.marinelink.com/news/maritime/lng-carriers" },
    ],
    "케미컬 탱커": [
      { source: "Riviera Maritime", title: "에스베르거, 친환경 케미컬 탱커 발주를 8척으로 확대", month: "7월", publishedAt: "2026. 07. 21.", articleUrl: "https://www.rivieramm.com/news-content-hub/leading-european-parcel-tanker-operator-expands-newbuild-programme-at-chinese-shipyard-89449" },
      { source: "New-Ships", title: "난징성항, 스테인리스 케미컬 탱커 6척 발주", month: "9월", publishedAt: "2026. 09. 08.", articleUrl: "https://www.new-ships.com/ns/news/6252" },
    ],
  },
};

function YearlyNewsArchive() {
  const [selectedYear, setSelectedYear] = useState(yearlyNewsYears[0]);
  const [selectedVessel, setSelectedVessel] = useState<YearlyNewsVessel>(yearlyNewsVessels[0]);
  const [ordersResult, setOrdersResult] = useState<{ key: string; points: YearlyOrderPoint[]; error: string }>({ key: "", points: [], error: "" });
  const vesselMeta = yearlyVesselMeta[selectedVessel];
  const ordersKey = `${selectedYear}-${vesselMeta.id}`;
  const orderPoints = ordersResult.key === ordersKey ? ordersResult.points : [];
  const ordersLoading = ordersResult.key !== ordersKey;
  const ordersError = ordersResult.key === ordersKey ? ordersResult.error : "";
  const turningPoints = findMajorTurningPoints(orderPoints);
  const selectedNews = yearlyNewsArchive[selectedYear][selectedVessel].map((news) => ({
    ...news,
    imageUrl: articleImageUrl(news.articleUrl),
  }));
  const remainingNews = [...selectedNews];
  const connectedNews = turningPoints.map((turningPoint) => {
    const closestIndex = remainingNews.reduce((bestIndex, news, index) => {
      const newsMonth = Number.parseInt(news.month, 10);
      const bestMonth = Number.parseInt(remainingNews[bestIndex].month, 10);
      return Math.abs(newsMonth - turningPoint.month) < Math.abs(bestMonth - turningPoint.month) ? index : bestIndex;
    }, 0);
    return { ...remainingNews.splice(closestIndex, 1)[0], turningPoint };
  });
  const displayedNews = connectedNews.length === selectedNews.length
    ? connectedNews
    : selectedNews.map((news) => ({ ...news, turningPoint: null }));
  const monthlyValues = Array.from({ length: 12 }, (_, index) => orderPoints.find((point) => point.month === index + 1)?.value ?? null);
  const chartOption = {
    animationDuration: 500,
    grid: { left: 66, right: 20, top: 34, bottom: 34 },
    tooltip: {
      trigger: "axis",
      confine: true,
      backgroundColor: "#102747",
      borderWidth: 0,
      textStyle: { color: "#fff", fontSize: 11 },
      formatter: (params: Array<{ axisValue: string; data: number | null }>) => {
        const value = params.find((item) => Number.isFinite(Number(item.data)))?.data;
        return `<b>${selectedYear}년 ${params[0]?.axisValue ?? ""}</b><br/>수주용량&nbsp;&nbsp;<b>${value === null || value === undefined ? "집계 전" : `${Number(value).toLocaleString("ko-KR")} ${vesselMeta.unit}`}</b>`;
      },
    },
    xAxis: {
      type: "category",
      data: Array.from({ length: 12 }, (_, index) => `${index + 1}월`),
      boundaryGap: false,
      axisTick: { show: false },
      axisLine: { lineStyle: { color: "#dbe4ef" } },
      axisLabel: { color: "#718096", fontSize: 10 },
    },
    yAxis: {
      type: "value",
      min: 0,
      name: vesselMeta.unit,
      nameTextStyle: { color: "#94a3b8", fontSize: 10 },
      axisLabel: { color: "#718096", fontSize: 10, formatter: formatCompactOrder },
      splitNumber: 4,
      splitLine: { lineStyle: { color: "#e7edf5", type: "dashed" } },
    },
    series: [{
      name: "월별 수주용량",
      type: "line",
      data: monthlyValues,
      connectNulls: false,
      smooth: 0.2,
      symbol: "circle",
      symbolSize: 5,
      lineStyle: { color: vesselMeta.color, width: 2.5 },
      itemStyle: { color: vesselMeta.color, borderColor: "#fff", borderWidth: 2 },
      areaStyle: { color: `${vesselMeta.color}1f` },
      markPoint: {
        symbol: "circle",
        symbolSize: 15,
        label: { show: false },
        data: turningPoints.map((point) => ({
          name: `${point.month}월 ${point.kind}`,
          coord: [`${point.month}월`, point.value],
          value: point.value,
          itemStyle: { color: point.kind === "고점" ? "#ef4444" : "#2563eb", borderColor: "#fff", borderWidth: 3 },
        })),
      },
    }],
  };

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/v1/master-data?vesselId=${vesselMeta.id}&from=${selectedYear}-01&to=${selectedYear}-12`, { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`수주 데이터를 불러오지 못했습니다. (HTTP ${response.status})`);
        return response.json() as Promise<MasterDataResponse>;
      })
      .then((payload) => {
        const points = payload.rows.flatMap((row) => {
          const value = row.orderCapacity === null ? Number.NaN : Number(row.orderCapacity);
          const month = Number(row.period.slice(5, 7));
          return Number.isFinite(value) && month >= 1 && month <= 12 ? [{ month, value }] : [];
        }).sort((a, b) => a.month - b.month);
        setOrdersResult({ key: ordersKey, points, error: "" });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) {
          setOrdersResult({ key: ordersKey, points: [], error: error instanceof Error ? error.message : "수주 데이터를 불러오지 못했습니다." });
        }
      });
    return () => controller.abort();
  }, [ordersKey, selectedYear, vesselMeta.id]);

  return (
    <section id="yearly-news-panel" role="tabpanel" aria-labelledby="yearly-news-tab" className="mt-6">
      <h2 className="sr-only">연도별 주요 뉴스</h2>
      <div className="flex flex-col gap-4 rounded-2xl border border-slate-200 bg-white p-5 md:flex-row md:items-center md:justify-between md:px-6">
        <p className="max-w-2xl text-sm leading-6 text-slate-500">시장 그래프의 변화가 컸던 시점과 당시의 주요 산업 뉴스를 함께 살펴보는 공간입니다.</p>
        <span className="inline-flex w-fit items-center gap-2 rounded-full bg-blue-50 px-3 py-2 text-xs font-semibold text-blue-700"><TrendingUp className="h-3.5 w-3.5" /> 변곡점 중심 아카이브</span>
      </div>

      <div className="mt-6 flex gap-2 overflow-x-auto pb-2 [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="tablist" aria-label="주요 뉴스 연도 선택">
        {yearlyNewsYears.map((year) => (
          <button
            key={year}
            type="button"
            role="tab"
            aria-selected={selectedYear === year}
            onClick={() => setSelectedYear(year)}
            className={`min-w-24 rounded-xl border px-5 py-3 text-sm font-bold transition-colors ${selectedYear === year ? "border-blue-700 bg-blue-700 text-white" : "border-slate-200 bg-white text-slate-500 hover:border-blue-300 hover:text-blue-700"}`}
          >{year}</button>
        ))}
      </div>

      <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-4 md:p-5">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div>
            <p className="text-[10px] font-semibold tracking-[0.14em] text-slate-400">VESSEL TYPE</p>
            <h3 className="mt-1 text-sm font-bold text-slate-800">선종별 주요 뉴스</h3>
          </div>
          <span className="text-[11px] text-slate-400">선종을 선택해 변곡 이력을 확인하세요</span>
        </div>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-5" role="tablist" aria-label="주요 뉴스 선종 선택">
          {yearlyNewsVessels.map((vessel) => (
            <button
              key={vessel}
              type="button"
              role="tab"
              aria-selected={selectedVessel === vessel}
              onClick={() => setSelectedVessel(vessel)}
              className={`rounded-xl border px-3 py-3 text-sm font-semibold transition-colors ${selectedVessel === vessel ? "border-blue-600 bg-blue-600 text-white shadow-sm" : "border-slate-200 bg-slate-50 text-slate-600 hover:border-blue-200 hover:bg-blue-50 hover:text-blue-700"}`}
            >
              {vessel}
            </button>
          ))}
        </div>
      </div>

      <div className="mt-4 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-slate-200 px-5 py-4 md:px-7">
          <div className="flex items-center gap-3">
            <span className="grid h-9 w-9 place-items-center rounded-xl bg-blue-50 text-blue-700"><CalendarDays className="h-4 w-4" /></span>
            <div><strong className="block text-sm text-slate-900">{selectedYear}년 {selectedVessel} 시장 변곡 타임라인</strong><span className="mt-1 block text-[11px] text-slate-400">시장 변곡 시점과 당시의 주요 원문 기사를 함께 확인하세요</span></div>
          </div>
          <span className="rounded-full border border-blue-200 bg-blue-50 px-3 py-1.5 text-[10px] font-semibold text-blue-600">ORIGINAL ARTICLES</span>
        </div>

        <div className="grid lg:grid-cols-[minmax(0,1.25fr)_minmax(320px,.75fr)]">
          <article className="border-b border-slate-200 p-5 md:p-7 lg:border-r lg:border-b-0">
            <div className="flex items-center justify-between gap-4">
              <div><p className="text-[10px] font-semibold tracking-[0.14em] text-slate-400">YEARLY MARKET CURVE</p><h3 className="mt-1 text-base font-bold text-slate-800">{selectedVessel} 연간 지표 흐름</h3></div>
              <span className="text-[11px] text-slate-400">1월 — 12월</span>
            </div>
            <div className="relative mt-5 min-h-72 overflow-hidden rounded-xl border border-slate-200 bg-slate-50 px-3 pt-3 pb-4" aria-label={`${selectedYear}년 ${selectedVessel} 월별 수주 그래프`}>
              {ordersLoading ? <div className="grid h-56 place-items-center text-sm text-slate-400">연간 수주 데이터를 불러오는 중입니다.</div>
                : ordersError ? <div role="alert" className="grid h-56 place-items-center px-6 text-center text-sm text-rose-600">{ordersError}</div>
                  : orderPoints.length ? <>
                    <EChartsReact option={chartOption} notMerge lazyUpdate style={{ height: 220, width: "100%" }} />
                    <div className="grid grid-cols-2 gap-3 px-2">
                      {turningPoints.map((point) => <span key={point.month} className="rounded-lg border border-slate-200 bg-white px-3 py-2 text-center text-[10px] font-semibold text-slate-600 shadow-sm"><b className={point.kind === "고점" ? "text-red-500" : "text-blue-600"}>{point.month}월</b> 변곡 시점</span>)}
                    </div>
                  </> : <div className="grid h-56 place-items-center text-sm text-slate-400">선택한 기간의 수주 데이터가 없습니다.</div>}
            </div>
          </article>

          <aside className="p-5 md:p-7" aria-label={`${selectedYear}년 ${selectedVessel} 변곡점 관련 뉴스`}>
            <div className="flex items-center justify-between"><div><p className="text-[10px] font-semibold tracking-[0.14em] text-slate-400">CONNECTED STORIES</p><h3 className="mt-1 text-base font-bold text-slate-800">{selectedVessel} 변곡점 관련 뉴스</h3></div><span className="text-[11px] text-slate-400">{selectedNews.length}건</span></div>
            <div className="mt-5 grid gap-3">
              {displayedNews.map((news) => (
                <a
                  key={news.title}
                  href={news.articleUrl}
                  target="_blank"
                  rel="noreferrer"
                  aria-label={`${news.title} 원문 기사 열기`}
                  className="group grid grid-cols-[92px_minmax(0,1fr)] gap-3 rounded-xl border border-slate-200 bg-slate-50 p-3 transition-all hover:-translate-y-0.5 hover:border-blue-300 hover:bg-blue-50/40 hover:shadow-sm"
                >
                  <div className="relative min-h-24 overflow-hidden rounded-lg bg-gradient-to-br from-slate-800 via-slate-700 to-blue-900">
                    <div className="absolute inset-0 flex flex-col items-center justify-center gap-1.5 px-2 text-center text-white/65">
                      <ImageOff className="h-5 w-5" aria-hidden="true" />
                      <span className="text-[9px] font-medium">원문 이미지 없음</span>
                    </div>
                    <img
                      src={news.imageUrl}
                      alt={`${news.title} 기사 썸네일`}
                      loading="eager"
                      fetchPriority="high"
                      decoding="async"
                      referrerPolicy="no-referrer"
                      className="absolute inset-0 h-full w-full object-cover opacity-0 transition-[opacity,transform] duration-300 group-hover:scale-105"
                      onLoad={(event) => {
                        event.currentTarget.classList.remove("opacity-0");
                      }}
                      onError={(event) => {
                        event.currentTarget.remove();
                      }}
                    />
                    <div className="absolute inset-0 bg-gradient-to-t from-slate-950/45 to-transparent" />
                    <span className="absolute bottom-2 left-2 text-[8px] font-bold tracking-[0.12em] text-white/90">{news.turningPoint ? `${news.turningPoint.month}월 변곡 연결` : news.month}</span>
                  </div>
                  <div className="min-w-0 py-0.5">
                    <div className="flex items-start justify-between gap-2">
                      <span className="text-[10px] font-medium text-blue-600">{news.source}</span>
                      <ExternalLink className="h-3.5 w-3.5 shrink-0 text-slate-300 transition-colors group-hover:text-blue-600" aria-hidden="true" />
                    </div>
                    <h4 className="mt-2 text-sm font-bold leading-5 text-slate-800 transition-colors group-hover:text-blue-700">{news.title}</h4>
                    <time className="mt-2 block text-[10px] text-slate-400">{news.publishedAt}</time>
                  </div>
                </a>
              ))}
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}

export default function Newsroom() {
  const [featuredStories, setFeaturedStories] = useState<NewsStory[]>([]);
  const [latestStories, setLatestStories] = useState<NewsStory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState<"전체" | NewsCategory>("전체");
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [activeStory, setActiveStory] = useState(0);
  const [isPlaying, setIsPlaying] = useState(true);
  const [newsView, setNewsView] = useState<"latest" | "yearly">("latest");
  const displayedFeaturedStories = selectedCategory === "전체"
    ? featuredStories
    : featuredStories.filter((story) => story.category === selectedCategory);
  const displayedLatestStories = selectedCategory === "전체"
    ? latestStories
    : latestStories.filter((story) => story.category === selectedCategory);

  useEffect(() => {
    const controller = new AbortController();
    fetch("/api/v1/newsroom", { credentials: "same-origin", signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`뉴스 데이터를 불러오지 못했습니다. (HTTP ${response.status})`);
        return response.json() as Promise<NewsroomResponse>;
      })
      .then((data) => {
        setFeaturedStories(data.featured);
        setLatestStories(data.articles);
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setLoadError(error instanceof Error ? error.message : "뉴스 데이터를 불러오지 못했습니다.");
      })
      .finally(() => {
        if (!controller.signal.aborted) setIsLoading(false);
      });
    return () => controller.abort();
  }, []);

  useEffect(() => {
    if (!isPlaying || displayedFeaturedStories.length < 2) return;
    const timer = window.setInterval(() => {
      setActiveStory((current) => (current + 1) % displayedFeaturedStories.length);
    }, 6000);
    return () => window.clearInterval(timer);
  }, [isPlaying, displayedFeaturedStories.length]);

  const showPreviousStory = () => setActiveStory((current) => (current - 1 + displayedFeaturedStories.length) % displayedFeaturedStories.length);
  const showNextStory = () => setActiveStory((current) => (current + 1) % displayedFeaturedStories.length);

  return (
    <main className="mx-auto w-full max-w-[1360px] px-4 py-8 md:px-8 md:py-12">
      <section aria-labelledby="newsroom-heading">
        <div className="mb-7 flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold tracking-[0.2em] text-blue-700">SHIPULSE · INDUSTRY NEWS</p>
            <h1 id="newsroom-heading" className="mt-2 text-3xl font-bold tracking-[-0.04em] text-slate-900 md:text-4xl">뉴스룸</h1>
            <p className="mt-2 text-sm text-slate-500">조선·해운·물류 산업의 흐름을 전합니다.</p>
          </div>
        </div>

        {isLoading && <div className="rounded-2xl border border-slate-200 bg-white px-6 py-14 text-center text-sm text-slate-500">최신 기사를 불러오고 있습니다.</div>}
        {loadError && <div role="alert" className="rounded-2xl border border-rose-200 bg-rose-50 px-6 py-8 text-center text-sm text-rose-700">{loadError}</div>}
        {!isLoading && !loadError && featuredStories.length === 0 && latestStories.length === 0 && (
          <div className="rounded-2xl border border-slate-200 bg-white px-6 py-12 text-center">
            <p className="text-sm font-semibold text-slate-700">아직 저장된 뉴스가 없습니다.</p>
            <p className="mt-2 text-xs text-slate-500">백엔드에서 데이터베이스 마이그레이션과 뉴스 동기화를 실행해 주세요.</p>
          </div>
        )}

        {displayedFeaturedStories.length > 0 && (
        <>
        <div
          aria-label="주요 뉴스 슬라이드"
          aria-roledescription="carousel"
          className="relative overflow-hidden rounded-2xl"
          onKeyDown={(event) => {
            if (event.key === "ArrowLeft") showPreviousStory();
            if (event.key === "ArrowRight") showNextStory();
          }}
        >
          <div className="flex transition-transform duration-500 ease-out" style={{ transform: `translateX(-${activeStory * 100}%)` }}>
            {displayedFeaturedStories.map((story, index) => {
              const visual = categoryVisuals[story.category];
              return (
              <article
                key={story.title}
                aria-label={`${index + 1} / ${displayedFeaturedStories.length}`}
                aria-roledescription="slide"
                aria-hidden={activeStory !== index}
                className="group grid w-full shrink-0 overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm md:grid-cols-2"
              >
                <div className="h-56 md:h-[360px]">
                  <StoryArtwork icon={visual.icon} tone={visual.tone} label={visual.label} imageUrl={story.imageUrl} imageAlt={story.imageAlt} />
                </div>
                <div className="flex flex-col justify-center p-6 md:p-10 lg:p-14">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="font-semibold text-blue-700">{story.category}</span>
                    <span className="max-w-40 truncate text-slate-500">{story.sourceName}</span>
                    <time className="ml-auto text-[11px] text-slate-400">{formatDate(story.publishedAt)}</time>
                  </div>
                  <a href={story.articleUrl} target="_blank" rel="noreferrer" lang="ko" data-no-translate className="mt-4 text-2xl font-bold leading-snug tracking-[-0.04em] text-slate-900 transition-colors hover:text-blue-800 md:text-3xl lg:text-4xl">{story.title}</a>
                  <a href={story.articleUrl} target="_blank" rel="noreferrer" className="mt-6 inline-flex items-center gap-2 text-sm font-semibold text-blue-700">원문 보기 <ArrowRight aria-hidden="true" className="h-4 w-4" /></a>
                </div>
              </article>
              );
            })}
          </div>
          {displayedFeaturedStories.length > 1 && <>
            <button type="button" aria-label="이전 뉴스" onClick={showPreviousStory} className="absolute top-1/2 left-3 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/70 bg-white/90 text-slate-700 shadow-md transition hover:bg-white md:left-5">
              <ArrowLeft aria-hidden="true" className="h-4 w-4" />
            </button>
            <button type="button" aria-label="다음 뉴스" onClick={showNextStory} className="absolute top-1/2 right-3 flex h-10 w-10 -translate-y-1/2 items-center justify-center rounded-full border border-white/70 bg-white/90 text-slate-700 shadow-md transition hover:bg-white md:right-5">
              <ArrowRight aria-hidden="true" className="h-4 w-4" />
            </button>
          </>}
        </div>
        {displayedFeaturedStories.length > 1 && (
        <div className="mt-4 flex items-center justify-center gap-3">
          <div className="flex items-center gap-2" role="group" aria-label="주요 뉴스 선택">
            {displayedFeaturedStories.map((story, index) => (
              <button
                key={story.title}
                type="button"
                aria-label={`${index + 1}번 뉴스: ${story.title}`}
                data-no-translate
                aria-current={activeStory === index ? "true" : undefined}
                onClick={() => setActiveStory(index)}
                className={`h-2 rounded-full transition-all ${activeStory === index ? "w-7 bg-blue-700" : "w-2 bg-slate-300 hover:bg-slate-400"}`}
              />
            ))}
          </div>
          <button
            type="button"
            aria-label={isPlaying ? "슬라이드 일시정지" : "슬라이드 재생"}
            onClick={() => setIsPlaying(!isPlaying)}
            className="flex h-8 w-8 items-center justify-center rounded-full text-slate-500 transition hover:bg-slate-100 hover:text-slate-800"
          >
            {isPlaying ? <Pause aria-hidden="true" className="h-3.5 w-3.5" /> : <Play aria-hidden="true" className="h-3.5 w-3.5" />}
          </button>
        </div>
        )}
        </>
        )}
      </section>

      <div className="mt-12 border-b border-slate-200 md:mt-16">
        <div className="flex gap-7 overflow-x-auto [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" role="tablist" aria-label="뉴스룸 콘텐츠 전환">
          <button
            id="yearly-news-tab"
            type="button"
            role="tab"
            aria-selected={newsView === "yearly"}
            aria-controls="yearly-news-panel"
            onClick={() => setNewsView("yearly")}
            className={`relative shrink-0 pb-4 text-left transition-colors ${newsView === "yearly" ? "text-blue-700" : "text-slate-400 hover:text-slate-700"}`}
          >
            <span className="block text-[10px] font-semibold tracking-[0.16em]">MARKET TURNING POINTS</span>
            <strong className="mt-1 block text-lg font-bold tracking-[-0.03em] md:text-xl">연도별 주요 뉴스</strong>
            {newsView === "yearly" && <i className="absolute right-0 bottom-[-1px] left-0 h-0.5 bg-blue-700" />}
          </button>
          <button
            id="latest-news-tab"
            type="button"
            role="tab"
            aria-selected={newsView === "latest"}
            aria-controls="latest-news-panel"
            onClick={() => setNewsView("latest")}
            className={`relative shrink-0 pb-4 text-left transition-colors ${newsView === "latest" ? "text-blue-700" : "text-slate-400 hover:text-slate-700"}`}
          >
            <span className="block text-[10px] font-semibold tracking-[0.16em]">LATEST STORIES</span>
            <strong className="mt-1 block text-lg font-bold tracking-[-0.03em] md:text-xl">조선·해운·물류 최신 소식</strong>
            {newsView === "latest" && <i className="absolute right-0 bottom-[-1px] left-0 h-0.5 bg-blue-700" />}
          </button>
        </div>
      </div>

      {newsView === "latest" ? <section id="latest-news-panel" role="tabpanel" aria-labelledby="latest-news-tab" className="mt-6">
        <h2 id="latest-news-heading" className="sr-only">{selectedCategory === "전체" ? "조선·해운·물류 최신 소식" : `${selectedCategory} 최신 소식`}</h2>
        <div className="mb-5 flex justify-end"><span className="text-xs text-slate-400">최근 수집 기사 {displayedLatestStories.length + displayedFeaturedStories.length}개</span></div>
        <div className="mb-6 flex flex-wrap gap-2" role="group" aria-label="뉴스 카테고리 필터">
          {(["전체", "조선", "해운", "물류"] as const).map((category) => (
            <button
              key={category}
              type="button"
              aria-pressed={selectedCategory === category}
              onClick={() => { setSelectedCategory(category); setActiveStory(0); }}
              className={`rounded-full border px-4 py-2 text-sm font-semibold transition-colors ${selectedCategory === category ? "border-blue-700 bg-blue-700 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-blue-300 hover:text-blue-700"}`}
            >{category}</button>
          ))}
        </div>
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          {displayedLatestStories.map((story) => {
            const visual = categoryVisuals[story.category];
            return (
            <article key={story.id} className="group overflow-hidden rounded-2xl border border-slate-200 bg-white transition-shadow hover:shadow-md">
              <a href={story.articleUrl} target="_blank" rel="noreferrer" aria-label={`원문 보기: ${story.title}`} className="block h-40">
                <StoryArtwork icon={visual.icon} tone={visual.tone} imageUrl={story.imageUrl} imageAlt={story.imageAlt} />
              </a>
              <div className="px-4 pt-6 pb-4 md:px-5 md:pt-7 md:pb-5">
                <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                  <span className="text-xs font-semibold text-blue-700">{story.category}</span>
                  <span className="max-w-36 truncate text-xs font-medium text-slate-500">{story.sourceName}</span>
                </div>
                <h3 lang="ko" data-no-translate className="mt-3 min-h-14 text-base font-bold leading-6 tracking-[-0.02em] text-slate-900 group-hover:text-blue-800"><a href={story.articleUrl} target="_blank" rel="noreferrer">{story.title}</a></h3>
                <time className="mt-3 block text-[11px] text-slate-400">{formatDate(story.publishedAt)}</time>
              </div>
            </article>
            );
          })}
        </div>
        {!isLoading && !loadError && selectedCategory !== "전체" && displayedFeaturedStories.length === 0 && displayedLatestStories.length === 0 && (
          <p className="rounded-xl border border-slate-200 bg-white p-8 text-center text-sm text-slate-500">이 카테고리에는 아직 수집된 기사가 없습니다.</p>
        )}
      </section> : <YearlyNewsArchive />}
    </main>
  );
}
