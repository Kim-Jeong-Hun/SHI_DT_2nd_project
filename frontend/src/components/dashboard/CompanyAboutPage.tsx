import { useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowDown, BarChart3, Database, Radar, Ship, X } from "lucide-react";
import * as THREE from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import "../../styles/company-about-page.css";

const sections = [
  ["company-intro", "서비스 소개"],
  ["company-history", "분석 흐름"],
  ["company-network", "시장 범위"],
  ["company-story", "브랜드 스토리"],
  ["company-ci", "CI"],
  ["company-milestones", "제품 원칙"],
] as const;

const history = [
  { year: "01", title: "신호를 모으다", text: "수주량, 운임, 거시경제와 선종 고유 지표를 월 단위로 연결해 시장을 같은 시간축에서 바라봅니다." },
  { year: "02", title: "맥락을 비교하다", text: "전체 시장에서 선종별 흐름까지 내려가며 변화의 크기와 방향, 전환 시점을 일관된 기준으로 비교합니다." },
  { year: "03", title: "범위로 전망하다", text: "하나의 숫자만 제시하지 않고 기본 전망과 90% 예측 범위를 함께 보여 불확실성을 판단에 포함합니다." },
  { year: "04", title: "행동으로 연결하다", text: "예상 고점과 저점, 주요 변수와 시나리오를 영업·생산·조달 계획에 활용할 수 있는 언어로 전달합니다." },
];

const regions = [
  { name: "ASIA", latitude: 32, longitude: 110, title: "아시아 시장 신호", text: "주요 조선 생산 거점과 컨테이너·벌크 수요의 변화를 함께 관찰합니다." },
  { name: "EUROPE", latitude: 50, longitude: 15, title: "유럽 시장 신호", text: "해운 금융, 친환경 규제와 주요 운임 지표가 발주 환경에 미치는 흐름을 살핍니다." },
  { name: "AMERICAS", latitude: 38, longitude: -100, title: "미주 시장 신호", text: "에너지와 원자재 교역, 톤마일 변화가 선종별 수요로 이어지는 경로를 확인합니다." },
];

const milestones = [
  { phase: "PRINCIPLE 01", title: "Clarity", text: "복잡한 지표를 한 번에 이해할 수 있는 구조로 보여줍니다." },
  { phase: "PRINCIPLE 02", title: "Context", text: "숫자만이 아니라 변화의 배경과 비교 기준을 함께 제공합니다." },
  { phase: "PRINCIPLE 03", title: "Confidence", text: "불확실성을 숨기지 않고 예측 범위와 함께 전달합니다." },
  { phase: "PRINCIPLE 04", title: "Action", text: "분석 결과를 다음 영업·생산 판단으로 연결합니다." },
];

function createRegionLabel(text: string) {
  const canvas = document.createElement("canvas");
  canvas.width = 320;
  canvas.height = 80;
  const context = canvas.getContext("2d");
  if (context) {
    context.beginPath();
    context.roundRect(8, 8, 304, 64, 18);
    context.fillStyle = "rgba(7, 27, 50, .92)";
    context.fill();
    context.lineWidth = 2;
    context.strokeStyle = "rgba(255, 176, 32, .9)";
    context.stroke();
    context.font = "800 22px Arial";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillStyle = "#ffffff";
    context.fillText(text, 160, 40);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, transparent: true, depthTest: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(.64, .16, 1);
  return sprite;
}

function createRegionFlag() {
  const canvas = document.createElement("canvas");
  canvas.width = 96;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  if (context) {
    context.lineCap = "round";
    context.lineJoin = "round";
    context.strokeStyle = "#102a43";
    context.lineWidth = 7;
    context.beginPath();
    context.moveTo(26, 112);
    context.lineTo(26, 18);
    context.stroke();
    context.fillStyle = "#ffffff";
    context.beginPath();
    context.moveTo(30, 22);
    context.lineTo(80, 36);
    context.lineTo(30, 56);
    context.closePath();
    context.fill();
    context.lineWidth = 5;
    context.stroke();
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  const material = new THREE.SpriteMaterial({ map: texture, color: 0xffb020, transparent: true, depthTest: true, depthWrite: false });
  const sprite = new THREE.Sprite(material);
  sprite.scale.set(.09, .12, 1);
  return sprite;
}

function createRegionConnection(start: (typeof regions)[number], end: (typeof regions)[number]) {
  const radius = 1.048;
  const startPosition = regionPosition(start.latitude, start.longitude, radius).normalize();
  const endPosition = regionPosition(end.latitude, end.longitude, radius).normalize();
  const points = Array.from({ length: 65 }, (_, index) => startPosition.clone()
    .lerp(endPosition, index / 64)
    .normalize()
    .multiplyScalar(radius));
  const geometry = new THREE.BufferGeometry().setFromPoints(points);
  const material = new THREE.LineDashedMaterial({ color: 0xfacc15, dashSize: .035, gapSize: .025, transparent: true, opacity: .92, depthTest: true, depthWrite: false });
  const line = new THREE.Line(geometry, material);
  line.computeLineDistances();
  return line;
}
function regionPosition(latitude: number, longitude: number, radius: number) {
  const lat = THREE.MathUtils.degToRad(latitude);
  // Align geographic longitudes with the equirectangular texture's prime-meridian offset.
  const lng = THREE.MathUtils.degToRad(longitude + 190);
  return new THREE.Vector3(
    -radius * Math.cos(lat) * Math.cos(lng),
    radius * Math.sin(lat),
    radius * Math.cos(lat) * Math.sin(lng),
  );
}

function InteractiveGlobe({ activeRegion, onSelect }: { activeRegion: number | null; onSelect: (index: number) => void }) {
  const mountRef = useRef<HTMLDivElement>(null);
  const markerRefs = useRef<ReturnType<typeof createRegionFlag>[]>([]);

  useEffect(() => {
    markerRefs.current.forEach((marker, index) => {
      const material = marker.material;
      material.color.set(index === activeRegion ? "#ff4d6d" : "#ffb020");
    });
  }, [activeRegion]);

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(36, 1, .1, 100);
    camera.position.set(0, .12, 3.35);

    const renderer = new THREE.WebGLRenderer({ alpha: true, antialias: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    mount.appendChild(renderer.domElement);

    const controls = new OrbitControls(camera, renderer.domElement);
    controls.autoRotate = false;
    controls.enableDamping = true;
    controls.dampingFactor = .075;
    controls.enablePan = false;
    controls.enableZoom = false;
    controls.rotateSpeed = .55;
    controls.minPolarAngle = .35;
    controls.maxPolarAngle = Math.PI - .35;

    scene.add(new THREE.AmbientLight(0xb9dedc, 1.15));
    const sunlight = new THREE.DirectionalLight(0xffffff, 2.45);
    sunlight.position.set(-3, 3, 4);
    scene.add(sunlight);

    const globe = new THREE.Group();
    scene.add(globe);
    const earthGeometry = new THREE.SphereGeometry(1, 96, 96);
    const earthMaterial = new THREE.MeshStandardMaterial({ color: 0xffffff, roughness: .78, metalness: .04 });
    const earth = new THREE.Mesh(earthGeometry, earthMaterial);
    globe.add(earth);

    const loader = new THREE.TextureLoader();
    loader.load("/images/about/globe-earth-texture-v2.png", (texture: any) => {
      texture.colorSpace = THREE.SRGBColorSpace;
      texture.anisotropy = renderer.capabilities.getMaxAnisotropy();
      earthMaterial.map = texture;
      earthMaterial.needsUpdate = true;
    });

    const atmosphere = new THREE.Mesh(
      new THREE.SphereGeometry(1.035, 64, 64),
      new THREE.MeshBasicMaterial({ color: 0x67dcca, transparent: true, opacity: .13, side: THREE.BackSide }),
    );
    globe.add(atmosphere);

    regions.forEach((region, index) => {
      globe.add(createRegionConnection(region, regions[(index + 1) % regions.length]));
    });

    const labels: ReturnType<typeof createRegionLabel>[] = [];
    const markers = regions.map((region, index) => {
      const markerGroup = new THREE.Group();
      markerGroup.position.copy(regionPosition(region.latitude, region.longitude, 1.035));
      const marker = createRegionFlag();
      const label = createRegionLabel(region.name);
      label.userData.regionIndex = index;
      label.position.set(0, .17, 0);
      labels.push(label);
      markerGroup.add(marker, label);
      globe.add(markerGroup);
      return marker;
    });
    markerRefs.current = markers;

    const raycaster = new THREE.Raycaster();
    const pointer = new THREE.Vector2();
    let pointerStart = { x: 0, y: 0 };
    const handlePointerDown = (event: PointerEvent) => {
      pointerStart = { x: event.clientX, y: event.clientY };
      mount.classList.add("is-dragging");
    };
    const handlePointerUp = (event: PointerEvent) => {
      mount.classList.remove("is-dragging");
      if (Math.hypot(event.clientX - pointerStart.x, event.clientY - pointerStart.y) > 6) return;
      const bounds = renderer.domElement.getBoundingClientRect();
      pointer.x = ((event.clientX - bounds.left) / bounds.width) * 2 - 1;
      pointer.y = -((event.clientY - bounds.top) / bounds.height) * 2 + 1;
      raycaster.setFromCamera(pointer, camera);
      const hit = raycaster.intersectObjects([earth, ...labels], false)[0];
      if (hit?.object.userData.regionIndex !== undefined) onSelect(hit.object.userData.regionIndex as number);
    };
    const handlePointerCancel = () => mount.classList.remove("is-dragging");
    renderer.domElement.addEventListener("pointerdown", handlePointerDown);
    renderer.domElement.addEventListener("pointerup", handlePointerUp);
    renderer.domElement.addEventListener("pointercancel", handlePointerCancel);

    const resize = () => {
      const size = Math.max(260, Math.min(mount.clientWidth, mount.clientHeight));
      renderer.setSize(size, size, false);
      camera.aspect = 1;
      camera.updateProjectionMatrix();
    };
    const resizeObserver = new ResizeObserver(resize);
    resizeObserver.observe(mount);
    resize();

    renderer.setAnimationLoop(() => {
      controls.update();
      renderer.render(scene, camera);
    });

    return () => {
      resizeObserver.disconnect();
      renderer.setAnimationLoop(null);
      renderer.domElement.removeEventListener("pointerdown", handlePointerDown);
      renderer.domElement.removeEventListener("pointerup", handlePointerUp);
      renderer.domElement.removeEventListener("pointercancel", handlePointerCancel);
      controls.dispose();
      scene.traverse((object: any) => {
        if (object instanceof THREE.Mesh || object instanceof THREE.Line) {
          object.geometry.dispose();
          const materials = Array.isArray(object.material) ? object.material : [object.material];
          materials.forEach((material: any) => material.dispose());
        }
        if (object instanceof THREE.Sprite) {
          object.material.map?.dispose();
          object.material.dispose();
        }
      });
      renderer.dispose();
      renderer.domElement.remove();
      markerRefs.current = [];
    };
  }, [onSelect]);

  return (
    <div className="company-about-map" aria-label="드래그해서 회전할 수 있는 3D 지구 기반 글로벌 시장 범위">
      <div ref={mountRef} className="company-about-globe-canvas" />
    </div>
  );
}

export default function CompanyAboutPage() {
  const [activeHistory, setActiveHistory] = useState(0);
  const [activeRegion, setActiveRegion] = useState<number | null>(null);
  const [activeSection, setActiveSection] = useState("company-intro");

  useEffect(() => {
    const targets = document.querySelectorAll<HTMLElement>(".company-about-page [data-reveal]");
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      targets.forEach((target) => target.classList.add("is-visible"));
      return;
    }
    const observer = new IntersectionObserver((entries) => {
      entries.forEach((entry) => {
        if (entry.isIntersecting) {
          entry.target.classList.add("is-visible");
          observer.unobserve(entry.target);
        }
      });
    }, { threshold: 0.14 });
    targets.forEach((target) => observer.observe(target));
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const observer = new IntersectionObserver((entries) => {
      const visible = entries.filter((entry) => entry.isIntersecting).sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
      if (visible?.target.id) setActiveSection(visible.target.id);
    }, { rootMargin: "-28% 0px -58%", threshold: [0, 0.15, 0.4] });
    sections.forEach(([id]) => {
      const target = document.getElementById(id);
      if (target) observer.observe(target);
    });
    return () => observer.disconnect();
  }, []);

  return (
    <main className="company-about-page">
      <section className="company-about-hero">
        <img src="/images/about/about-hero-v2.png" alt="새벽 항만에서 운항을 준비하는 컨테이너선과 상선들" />
        <div className="company-about-shade" />
        <div className="company-about-hero-copy">
          <p>ABOUT SHIPULSE</p>
          <h1>시장의 신호를 읽고,<br /><em>내일의 기준</em>을 만듭니다.</h1>
          <span>조선·해운 산업의 복잡한 데이터를 더 명확한 판단으로 연결합니다.</span>
          <div className="company-about-hero-facts" aria-label="서비스 핵심 범위">
            <div><strong>05</strong><span>분석 선종</span></div>
            <div><strong>06</strong><span>월 전망 범위</span></div>
            <div><strong>90%</strong><span>예측 범위</span></div>
          </div>
        </div>
        <a className="company-about-scroll" href="#company-intro"><span>SCROLL</span><ArrowDown aria-hidden="true" /></a>
      </section>

      <nav className="company-about-index" aria-label="회사 소개 섹션">
        {sections.map(([id, label], index) => <a key={id} href={`#${id}`} aria-current={activeSection === id ? "true" : undefined}><span>0{index + 1}</span>{label}</a>)}
      </nav>

      <section id="company-intro" className="company-about-intro company-about-section">
        <div className="company-about-heading" data-reveal><p>01 · WHO WE ARE</p><h2>복잡한 시장을<br />한눈에 보이게</h2></div>
        <div className="company-about-intro-body" data-reveal>
          <p className="company-about-lead">SHIPULSE는 조선·해운 시장의 수주, 운임, 거시 지표와 산업 정보를 연결하는 시장 인텔리전스 서비스입니다.</p>
          <p>전체 시장을 살펴본 뒤 관심 선종으로 내려가고, 주요 변수와 예측 범위를 확인해 시나리오를 비교하는 과정을 하나의 분석 흐름으로 제공합니다.</p>
          <div className="company-about-capabilities">
            {[
              [Database, "CONNECTED DATA", "분산된 시장 데이터를 같은 기준으로 연결"],
              [Radar, "EARLY SIGNAL", "변화가 커지기 전 의미 있는 신호를 탐색"],
              [BarChart3, "CLEAR DECISION", "분석 결과를 이해하기 쉬운 판단 정보로 전환"],
            ].map(([Icon, label, text], index) => <article key={String(label)} style={{ "--delay": `${index * 110}ms` } as CSSProperties}><Icon aria-hidden="true" /><span>{String(label)}</span><p>{String(text)}</p></article>)}
          </div>
          <div className="company-about-value-chain" aria-label="분석 가치 흐름">
            {["시장 관측", "선종별 해석", "예측 범위", "의사결정"].map((label, index) => (
              <div key={label}><span>0{index + 1}</span><b>{label}</b></div>
            ))}
          </div>
        </div>
      </section>

      <section id="company-history" className="company-about-history company-about-section">
        <div className="company-about-heading company-about-heading-light" data-reveal><p>02 · HOW IT WORKS</p><h2>관측에서 실행까지<br />이어지는 분석</h2><span>각 단계는 시장을 더 빠르게 읽고 일관되게 판단하기 위한 하나의 흐름으로 연결됩니다.</span></div>
        <div className="company-about-history-stage" data-reveal>
          <div className="company-about-history-years" role="tablist" aria-label="연혁 단계">
            {history.map((item, index) => <button key={item.year} type="button" role="tab" aria-selected={activeHistory === index} onClick={() => setActiveHistory(index)}><span>{item.year}</span><b>{item.title}</b></button>)}
          </div>
          <div className="company-about-history-progress"><span style={{ width: `${((activeHistory + 1) / history.length) * 100}%` }} /></div>
          <article key={activeHistory} className="company-about-history-detail"><span>STEP {history[activeHistory].year}</span><h3>{history[activeHistory].title}</h3><p>{history[activeHistory].text}</p></article>
        </div>
      </section>

      <section id="company-network" className="company-about-network company-about-section">
        <div className="company-about-heading" data-reveal><p>03 · MARKET COVERAGE</p><h2><span>세계의 흐름을</span><br /><span>하나의 시장으로</span></h2><span>지역별 교역과 산업 신호를 선종별 수주 전망의 맥락으로 연결합니다.</span></div>
        <div className="company-about-network-stage" data-reveal>
          <p className="company-about-globe-help">※ DRAG TO EXPLORE · SELECT A LABEL</p>
          <InteractiveGlobe activeRegion={activeRegion} onSelect={setActiveRegion} />
          {activeRegion !== null && <article key={activeRegion} className="company-about-region-card"><button type="button" className="company-about-region-close" onClick={() => setActiveRegion(null)} aria-label="지역 시장 신호 닫기"><X aria-hidden="true" /></button><span>0{activeRegion + 1} / 03</span><h3>{regions[activeRegion].title}</h3><p>{regions[activeRegion].text}</p><small>지역 신호는 선종별 수주·운임·거시 지표와 함께 해석합니다.</small></article>}
          <div className="company-about-coverage-strip" aria-label="시장 분석 범위">
            <div><strong>05</strong><span>VESSEL TYPES</span></div>
            <div><strong>03</strong><span>MARKET REGIONS</span></div>
            <div><strong>01M</strong><span>OBSERVATION UNIT</span></div>
          </div>
        </div>
      </section>

      <section id="company-story" className="company-about-story company-about-section">
        <div className="company-about-story-image" data-reveal><img src="/images/about/about-story-v2.png" alt="항만을 출항하며 새로운 항로로 나아가는 컨테이너선" /><span>FROM OCEAN TO INSIGHT</span></div>
        <div className="company-about-story-copy" data-reveal>
          <p>04 · BRAND STORY</p><h2>선박의 움직임에서<br />시장의 신호를 찾다</h2>
          <blockquote>“SHIP은 산업의 현장을,<br />SIGNAL은 변화의 단서를 의미합니다.”</blockquote>
          <p>우리는 수많은 숫자 사이에서 시장의 방향을 보여주는 신호를 발견합니다. 데이터가 단순한 기록에 머물지 않고 다음 행동을 위한 언어가 되도록 만드는 것이 브랜드가 추구하는 이야기입니다.</p>
          <div className="company-about-story-tags" aria-label="브랜드 핵심 가치"><span>MARKET CONTEXT</span><span>FORECAST RANGE</span><span>DECISION SIGNAL</span></div>
        </div>
      </section>

      <section id="company-ci" className="company-about-ci company-about-section">
        <div className="company-about-heading" data-reveal><p>05 · CORPORATE IDENTITY</p><h2><span>데이터와 항해가 만나는</span><br /><span>하나의 상징</span></h2><span>깊은 바다의 신뢰감과 변화를 포착하는 신호의 선명함을<br />하나의 시각 언어로 담았습니다.</span></div>
        <div className="company-about-ci-stage" data-reveal>
          <div className="company-about-ci-primary"><div className="company-about-logo-symbol"><Ship aria-hidden="true" /></div><div><strong>선(船)견지명</strong><span>SHIP ORDER MARKET INTELLIGENCE</span></div></div>
          <div className="company-about-ci-rule"><span>CONCEPT</span><h3>Signal on the Sea</h3><p>수평선을 닮은 안정적인 구조와 앞으로 나아가는 선박의 방향성을 결합합니다.</p></div>
          <div className="company-about-color-system"><div><i /><span>DEEP OCEAN<br /><b>#071B32</b></span></div><div><i /><span>SIGNAL TEAL<br /><b>#07826E</b></span></div><div><i /><span>HORIZON<br /><b>#F3F6F7</b></span></div></div>
        </div>
      </section>

      <section id="company-milestones" className="company-about-milestones company-about-section">
        <div className="company-about-heading company-about-heading-light" data-reveal><p>06 · PRODUCT PRINCIPLES</p><h2>좋은 판단을 만드는<br />네 가지 원칙</h2><span>정보의 양보다 이해와 실행의 품질을 높이는 경험을 설계합니다.</span></div>
        <div className="company-about-milestone-list">
          {milestones.map((item, index) => <article key={item.phase} data-reveal style={{ "--delay": `${index * 100}ms` } as CSSProperties}><span>{item.phase}</span><h3>{item.title}</h3><p>{item.text}</p></article>)}
        </div>
        <div className="company-about-closing" data-reveal><span>SHIPULSE</span><p>시장에 더 가까이,<br />미래에 한 걸음 먼저.</p></div>
      </section>
    </main>
  );
}
