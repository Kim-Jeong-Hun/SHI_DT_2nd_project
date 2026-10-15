import { Ship } from "lucide-react";
import "../../styles/app-brand.css";

type AppBrandProps = { href?: string; onClick?: () => void; light?: boolean };

export default function AppBrand({ href, onClick, light = false }: AppBrandProps) {
  const content = <><span className="app-brand-mark"><Ship size={21} strokeWidth={2.2} /></span><span className="app-brand-copy"><strong>선(船)견지명</strong><small>ORDER MARKET INTELLIGENCE</small></span></>;
  const className = `app-brand${light ? " app-brand-light" : ""}`;
  if (href) return <a className={className} href={href} aria-label="선견지명 홈">{content}</a>;
  return <button className={className} type="button" onClick={onClick} aria-label="메인 대시보드로 이동">{content}</button>;
}
