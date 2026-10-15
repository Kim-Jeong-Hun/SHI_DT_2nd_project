declare module "three";

declare module "three/examples/jsm/controls/OrbitControls.js" {
  export class OrbitControls {
    constructor(camera: unknown, domElement: HTMLElement);
    autoRotate: boolean;
    enableDamping: boolean;
    dampingFactor: number;
    enablePan: boolean;
    enableZoom: boolean;
    rotateSpeed: number;
    minPolarAngle: number;
    maxPolarAngle: number;
    update(): void;
    dispose(): void;
  }
}
