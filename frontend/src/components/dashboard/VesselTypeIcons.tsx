type VesselIconProps = {
  size?: number;
  className?: string;
};

const common = (size: number, className?: string) => ({
  width: size,
  height: size,
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: 1.7,
  strokeLinecap: "round" as const,
  strokeLinejoin: "round" as const,
  className,
  "aria-hidden": true,
});

export function TankerDrumIcon({ size = 22, className }: VesselIconProps) {
  return <svg {...common(size, className)}>
    <path d="M5.1 4.4h13.8v15.2H5.1Z" fill="#202225" stroke="#090a0b" />
    <ellipse cx="12" cy="4.4" rx="6.9" ry="2" fill="#111315" stroke="#090a0b" />
    <ellipse cx="12" cy="19.6" rx="6.9" ry="2" fill="#181a1d" stroke="#090a0b" />
    <path d="M5.1 8.2c1.8.7 4.2 1 6.9 1s5.1-.3 6.9-1M5.1 15.7c1.8.7 4.2 1 6.9 1s5.1-.3 6.9-1" stroke="#fff" strokeWidth="1.35" />
    <path d="M7 5.4v13" stroke="#686c70" strokeOpacity=".5" />
  </svg>;
}

export function ShippingContainerIcon({ size = 22, className }: VesselIconProps) {
  return <svg {...common(size, className)}>
    <path d="m2.2 7.2 3.7-3h15.9l-3.7 3Z" fill="#f2c540" stroke="#17366e" />
    <path d="M2.2 7.2h15.9v12.6H2.2Z" fill="#315aa8" stroke="#17366e" />
    <path d="m18.1 7.2 3.7-3v12.6l-3.7 3Z" fill="#1d4388" stroke="#17366e" />
    <path d="M4.7 8.3v10.4M7.3 8.3v10.4M9.9 8.3v10.4M12.5 8.3v10.4M15.1 8.3v10.4" stroke="#7190ca" />
    <path d="M19.25 6.25v12.1M20.65 5.15v12.1M18.7 12.2l2.5-2M18.7 15.2l2.5-2" stroke="#d8e1f2" strokeWidth=".9" />
    <path d="M2.2 9.1h15.9M3.7 19.8v1.2M16.6 19.8V21" stroke="#17366e" />
  </svg>;
}

export function ChemicalHazardIcon({ size = 22, className }: VesselIconProps) {
  return <svg {...common(size, className)}>
    <circle cx="12" cy="12" r="11.8" fill="#1a171b" stroke="#fff" strokeWidth=".15" />
    <circle cx="12" cy="12" r="10.75" fill="#fffd38" stroke="none" />
    <path d="M7.1 3.48A9.83 9.83 0 0 0 2.19 12H12L7.1 3.48Z" fill="#1a171b" stroke="none" />
    <path d="M16.9 3.48A9.83 9.83 0 0 1 21.81 12H12l4.9-8.52Z" fill="#1a171b" stroke="none" />
    <path d="M7.11 20.48a9.84 9.84 0 0 0 9.78.02L12 12l-4.89 8.48Z" fill="#1a171b" stroke="none" />
    <circle cx="12" cy="11.97" r="2.99" fill="#fffd38" stroke="none" />
    <circle cx="12" cy="11.97" r="1.91" fill="#1a171b" stroke="none" />
  </svg>;
}

export function LngCarrierIcon({ size = 22, className }: VesselIconProps) {
  return <svg {...common(size, className)}>
    <path d="M3.2 19v-8.5a8.8 6.8 0 0 1 17.6 0V19Z" fill="#e8edf1" stroke="#77818d" />
    <path d="M4.1 10.3h15.8M5.5 6.9h13M6.8 5.1h10.4" stroke="#fff" strokeOpacity=".95" />
    <path d="M1.5 19h21v2H1.5Z" fill="#d9b635" stroke="#8c7520" />
    <path d="M19 19V5.7h2V19M19 8.2h2M19 11h2M19 13.8h2M19 16.6h2" stroke="#7c8792" strokeWidth=".8" />
    <text x="11.3" y="15.1" fill="#d84a4a" stroke="none" fontSize="5" fontWeight="800" letterSpacing=".2" textAnchor="middle">LNG</text>
  </svg>;
}

export function IronOreIcon({ size = 22, className }: VesselIconProps) {
  return <svg {...common(size, className)}>
    <path d="m2.4 15.8 2.3-6.2 4.1-1.8 3.3-4.5 5.3 1.8 4.2 6-2.2 7.2-10.5 2.4-5.7-1.8Z" fill="#5a5652" stroke="#353331" />
    <path d="m4.7 9.6 4.1-1.8 3.3-4.5 1.5 6.2-4.2 3.1Z" fill="#8b8379" stroke="none" />
    <path d="m13.6 9.5 3.8-4.4 4.2 6-5.3 1.2Z" fill="#6f6963" stroke="none" />
    <path d="m3.2 18.9 6.2-6.3 2.9 4.4-3.4 3.7Z" fill="#464340" stroke="none" />
    <path d="m12.3 17 4-4.7 3.1 6-6.1 1.4Z" fill="#78716a" stroke="none" />
    <path d="m9.4 12.6 4.2-3.1 2.7 2.8-4 4.7Z" fill="#9a9288" stroke="none" />
    <path d="m4.7 9.6 4.7 3 2.7-9.3M13.6 9.5l2.7 2.8 5.3-1.2M9.4 12.6 8.9 20.7M12.3 17l1 2.7" stroke="#b3aba1" strokeWidth=".65" strokeOpacity=".7" />
  </svg>;
}
