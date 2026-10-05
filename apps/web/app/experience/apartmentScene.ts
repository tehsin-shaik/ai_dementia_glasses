import * as THREE from "three";

import { KEYS_POSITION, type Vec3, type Viewpoint } from "./steps";

export type ApartmentScene = {
  moveTo: (view: Viewpoint, immediate?: boolean) => void;
  showKeysMarker: (label: string | null) => void;
  dispose: () => void;
};

const WALL_HEIGHT = 2.7;
const WALK_SPEED = 1.3;

function easeInOut(t: number): number {
  return t < 0.5 ? 2 * t * t : 1 - (-2 * t + 2) ** 2 / 2;
}

function vec(value: Vec3): THREE.Vector3 {
  return new THREE.Vector3(...value);
}

function woodTexture(): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 512;
  canvas.height = 512;
  const context = canvas.getContext("2d");
  if (context) {
    const plank = 64;
    for (let row = 0; row < canvas.height / plank; row += 1) {
      const offset = (row % 2) * 160;
      for (let x = -offset; x < canvas.width; x += 320) {
        const shade = 150 + ((row * 37 + x) % 40);
        context.fillStyle = `rgb(${shade + 40}, ${shade}, ${shade - 50})`;
        context.fillRect(x, row * plank, 320, plank);
        context.strokeStyle = "rgba(60, 40, 20, 0.35)";
        context.strokeRect(x + 0.5, row * plank + 0.5, 320, plank);
      }
      for (let line = 0; line < 6; line += 1) {
        context.strokeStyle = "rgba(90, 60, 30, 0.12)";
        context.beginPath();
        const y = row * plank + 8 + line * 9;
        context.moveTo(0, y);
        context.bezierCurveTo(170, y + 4, 340, y - 4, 512, y + 2);
        context.stroke();
      }
    }
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.wrapS = THREE.RepeatWrapping;
  texture.wrapT = THREE.RepeatWrapping;
  texture.repeat.set(4, 3);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

function labelTexture(text: string): THREE.CanvasTexture {
  const canvas = document.createElement("canvas");
  canvas.width = 640;
  canvas.height = 128;
  const context = canvas.getContext("2d");
  if (context) {
    context.fillStyle = "rgba(10, 24, 28, 0.82)";
    context.beginPath();
    context.roundRect(4, 4, 632, 120, 56);
    context.fill();
    context.strokeStyle = "rgba(125, 230, 214, 0.9)";
    context.lineWidth = 4;
    context.stroke();
    context.fillStyle = "#e9fffb";
    context.font = "600 46px system-ui, -apple-system, 'Segoe UI', sans-serif";
    context.textAlign = "center";
    context.textBaseline = "middle";
    context.fillText(text, 320, 66);
  }
  const texture = new THREE.CanvasTexture(canvas);
  texture.colorSpace = THREE.SRGBColorSpace;
  return texture;
}

/**
 * Build the procedural apartment used by the first-person walk-through and
 * start rendering it into the canvas. Throws when WebGL is unavailable.
 */
export function createApartmentScene(canvas: HTMLCanvasElement, initialView: Viewpoint): ApartmentScene {
  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  renderer.toneMapping = THREE.ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.05;
  renderer.shadowMap.enabled = true;
  renderer.shadowMap.type = THREE.PCFShadowMap;

  const scene = new THREE.Scene();
  scene.background = new THREE.Color("#cfe3ea");
  const camera = new THREE.PerspectiveCamera(68, 1, 0.05, 60);

  const disposables: { dispose: () => void }[] = [];
  const track = <T extends { dispose: () => void }>(item: T): T => {
    disposables.push(item);
    return item;
  };
  const material = (color: string, options: THREE.MeshStandardMaterialParameters = {}) =>
    track(new THREE.MeshStandardMaterial({ color, roughness: 0.75, ...options }));

  function box(
    size: Vec3,
    position: Vec3,
    surface: THREE.Material,
    parent: THREE.Object3D = scene,
  ): THREE.Mesh {
    const mesh = new THREE.Mesh(track(new THREE.BoxGeometry(...size)), surface);
    mesh.position.set(...position);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }

  function cylinder(
    radiusTop: number,
    radiusBottom: number,
    height: number,
    position: Vec3,
    surface: THREE.Material,
    parent: THREE.Object3D = scene,
  ): THREE.Mesh {
    const mesh = new THREE.Mesh(track(new THREE.CylinderGeometry(radiusTop, radiusBottom, height, 28)), surface);
    mesh.position.set(...position);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    parent.add(mesh);
    return mesh;
  }

  // Lighting: soft daylight from the living-room window plus a warm lamp.
  scene.add(new THREE.HemisphereLight("#fff6e8", "#8a7a68", 1.4));
  const sun = new THREE.DirectionalLight("#fff1d6", 2.4);
  sun.position.set(-9, 7, 4);
  sun.target.position.set(0, 0, 0);
  sun.castShadow = true;
  sun.shadow.mapSize.set(2048, 2048);
  sun.shadow.camera.left = -8;
  sun.shadow.camera.right = 8;
  sun.shadow.camera.top = 6;
  sun.shadow.camera.bottom = -6;
  sun.shadow.bias = -0.0005;
  scene.add(sun, sun.target);

  // Floor, ceiling and walls of a 12 m x 8 m open-plan flat.
  const wood = track(woodTexture());
  const floor = new THREE.Mesh(
    track(new THREE.PlaneGeometry(12, 8)),
    material("#ffffff", { map: wood, roughness: 0.6 }),
  );
  floor.rotation.x = -Math.PI / 2;
  floor.receiveShadow = true;
  scene.add(floor);
  const ceiling = new THREE.Mesh(track(new THREE.PlaneGeometry(12, 8)), material("#f7f3ec"));
  ceiling.rotation.x = Math.PI / 2;
  ceiling.position.y = WALL_HEIGHT;
  scene.add(ceiling);

  const wall = material("#efe6d8");
  const accentWall = material("#c9ddd5");
  box([12, WALL_HEIGHT, 0.1], [0, WALL_HEIGHT / 2, -4], wall);
  box([12, WALL_HEIGHT, 0.1], [0, WALL_HEIGHT / 2, 4], wall);
  box([0.1, WALL_HEIGHT, 8], [6, WALL_HEIGHT / 2, 0], accentWall);
  // Window wall with an opening on the living-room side.
  box([0.1, WALL_HEIGHT, 3.6], [-6, WALL_HEIGHT / 2, -2.2], wall);
  box([0.1, 0.9, 4.4], [-6, 0.45, 1.8], wall);
  box([0.1, 0.5, 4.4], [-6, WALL_HEIGHT - 0.25, 1.8], wall);
  const sky = new THREE.Mesh(
    track(new THREE.PlaneGeometry(4.4, 1.3)),
    track(new THREE.MeshBasicMaterial({ color: "#bfe4f6" })),
  );
  sky.rotation.y = Math.PI / 2;
  sky.position.set(-6.2, 1.55, 1.8);
  scene.add(sky);
  const frame = material("#ffffff");
  box([0.14, 1.36, 0.06], [-6, 1.55, 1.8], frame);
  box([0.14, 0.06, 4.4], [-6, 1.55, 1.8], frame);
  // Partial wall separating the hallway from the kitchen.
  box([0.12, WALL_HEIGHT, 2.2], [1.6, WALL_HEIGHT / 2, -2.9], wall);
  box([0.12, WALL_HEIGHT, 1.6], [1.6, WALL_HEIGHT / 2, 3.2], wall);

  // Kitchen along the back wall.
  const cabinet = material("#f4f1ea", { roughness: 0.5 });
  const worktop = material("#d8d2c7", { roughness: 0.35 });
  box([3.6, 0.88, 0.62], [-3.5, 0.44, -3.6], cabinet);
  box([3.7, 0.05, 0.68], [-3.5, 0.905, -3.58], worktop);
  box([3.6, 0.7, 0.36], [-3.5, 2.0, -3.78], cabinet);
  for (let index = 0; index < 4; index += 1) {
    box([0.12, 0.02, 0.02], [-4.8 + index * 0.9, 0.78, -3.28], material("#9aa3a6", { metalness: 0.8 }));
  }
  box([0.8, 1.9, 0.7], [-5.5, 0.95, -3.55], material("#dfe4e6", { metalness: 0.3, roughness: 0.3 }));
  box([0.03, 0.5, 0.03], [-5.18, 1.3, -3.18], material("#8d969a", { metalness: 0.9 }));
  box([0.8, 0.02, 0.5], [-3.9, 0.94, -3.58], material("#2b2f33", { roughness: 0.3 }));

  // Kettle and mug for the tea moment.
  const kettleBody = material("#c86d58", { roughness: 0.3, metalness: 0.2 });
  cylinder(0.09, 0.12, 0.2, [-3.75, 1.04, -3.55], kettleBody);
  cylinder(0.03, 0.03, 0.03, [-3.75, 1.155, -3.55], material("#2a2a2a"));
  const handle = new THREE.Mesh(track(new THREE.TorusGeometry(0.07, 0.012, 10, 24, Math.PI)), kettleBody);
  handle.position.set(-3.75, 1.14, -3.55);
  scene.add(handle);
  const spout = cylinder(0.012, 0.025, 0.12, [-3.62, 1.06, -3.55], kettleBody);
  spout.rotation.z = -0.9;
  cylinder(0.04, 0.035, 0.09, [-3.35, 0.975, -3.45], material("#f6f6f2", { roughness: 0.4 }));
  cylinder(0.034, 0.034, 0.005, [-3.35, 1.015, -3.45], material("#9a5a2c", { roughness: 0.2 }));

  // Alex's keys on the counter.
  const keys = new THREE.Group();
  const metal = material("#c9b46a", { metalness: 0.9, roughness: 0.25 });
  const ring = new THREE.Mesh(track(new THREE.TorusGeometry(0.025, 0.004, 8, 24)), metal);
  ring.rotation.x = Math.PI / 2;
  keys.add(ring);
  const keyA = box([0.065, 0.004, 0.018], [0.05, 0, 0.004], metal, keys);
  keyA.rotation.y = 0.3;
  const keyB = box([0.06, 0.004, 0.016], [0.035, 0, -0.035], material("#b8bec2", { metalness: 0.9 }), keys);
  keyB.rotation.y = -0.8;
  box([0.03, 0.012, 0.045], [-0.04, 0.002, 0.01], material("#1d7770", { roughness: 0.5 }), keys);
  keys.position.set(...KEYS_POSITION);
  keys.scale.setScalar(1.5);
  scene.add(keys);

  // Living room: sofa, coffee table with an open book, rug, lamp and plant.
  const fabric = material("#5d7f8c", { roughness: 0.95 });
  box([2.4, 0.42, 0.95], [-3.4, 0.21, 3.35], fabric);
  box([2.4, 0.55, 0.22], [-3.4, 0.7, 3.75], fabric);
  box([0.22, 0.6, 0.95], [-4.5, 0.4, 3.35], fabric);
  box([0.22, 0.6, 0.95], [-2.3, 0.4, 3.35], fabric);
  const rug = new THREE.Mesh(track(new THREE.PlaneGeometry(3.2, 2.2)), material("#d9b99b", { roughness: 1 }));
  rug.rotation.x = -Math.PI / 2;
  rug.position.set(-3.4, 0.005, 2.3);
  rug.receiveShadow = true;
  scene.add(rug);
  const tableWood = material("#8b5e3c", { roughness: 0.55 });
  box([1.2, 0.05, 0.65], [-3.4, 0.42, 1.95], tableWood);
  for (const [x, z] of [[-3.95, 1.7], [-2.85, 1.7], [-3.95, 2.2], [-2.85, 2.2]]) {
    cylinder(0.025, 0.025, 0.4, [x, 0.2, z], tableWood);
  }
  const page = material("#fbf7ee", { roughness: 0.9 });
  const leftPage = box([0.18, 0.012, 0.25], [-3.5, 0.455, 1.92], page);
  leftPage.rotation.z = 0.08;
  const rightPage = box([0.18, 0.012, 0.25], [-3.31, 0.455, 1.92], page);
  rightPage.rotation.z = -0.08;
  box([0.4, 0.008, 0.27], [-3.405, 0.447, 1.92], material("#7a2f2f"));
  cylinder(0.04, 0.035, 0.09, [-3.0, 0.49, 2.05], material("#f6f6f2", { roughness: 0.4 }));
  cylinder(0.12, 0.15, 0.04, [-1.8, 0.02, 3.55], material("#333333"));
  cylinder(0.015, 0.015, 1.5, [-1.8, 0.77, 3.55], material("#333333", { metalness: 0.6 }));
  cylinder(0.14, 0.24, 0.3, [-1.8, 1.6, 3.55], material("#f3e3c3", { emissive: "#ffcf8a", emissiveIntensity: 0.6 }));
  const lamp = new THREE.PointLight("#ffd29a", 3, 6, 1.6);
  lamp.position.set(-1.8, 1.5, 3.45);
  scene.add(lamp);
  cylinder(0.18, 0.14, 0.35, [-5.5, 0.175, 3.5], material("#c86d58"));
  const leaves = new THREE.Mesh(track(new THREE.IcosahedronGeometry(0.38, 1)), material("#4f8a4a", { flatShading: true }));
  leaves.position.set(-5.5, 0.7, 3.5);
  leaves.castShadow = true;
  scene.add(leaves);
  box([1.4, 0.9, 0.05], [-3.4, 1.65, 3.96], material("#e9d9b0", { emissive: "#3b2c12", emissiveIntensity: 0.05 }));

  // Hallway: front door, console table with an empty bowl, coat hooks.
  const door = material("#355c58", { roughness: 0.5 });
  box([0.08, 2.1, 1.0], [5.95, 1.05, 0], door);
  box([0.1, 2.2, 0.08], [5.95, 1.1, -0.54], frame);
  box([0.1, 2.2, 0.08], [5.95, 1.1, 0.54], frame);
  box([0.1, 0.08, 1.16], [5.95, 2.2, 0], frame);
  const knob = new THREE.Mesh(track(new THREE.SphereGeometry(0.035, 16, 16)), material("#d4b25c", { metalness: 0.9, roughness: 0.2 }));
  knob.position.set(5.88, 1.0, -0.35);
  scene.add(knob);
  box([0.4, 0.04, 0.9], [5.6, 0.8, 1.15], tableWood);
  box([0.36, 0.78, 0.04], [5.6, 0.39, 0.74], tableWood);
  box([0.36, 0.78, 0.04], [5.6, 0.39, 1.56], tableWood);
  const bowl = new THREE.Mesh(
    track(new THREE.SphereGeometry(0.11, 24, 12, 0, Math.PI * 2, Math.PI / 2, Math.PI / 2)),
    material("#e7e2d6", { side: THREE.DoubleSide, roughness: 0.4 }),
  );
  bowl.position.set(5.58, 0.93, 1.05);
  scene.add(bowl);
  box([0.04, 0.04, 0.8], [5.92, 1.7, -1.6], tableWood);
  box([0.06, 0.7, 0.3], [5.85, 1.35, -1.75], material("#a0522d", { roughness: 0.9 }));
  box([0.5, 0.9, 0.04], [5.9, 1.55, 1.15], material("#e8f1f4", { metalness: 0.2, roughness: 0.15 }));

  // "Last recorded" marker over the keys, drawn on top of walls like a HUD overlay.
  const markerGroup = new THREE.Group();
  markerGroup.position.copy(vec(KEYS_POSITION));
  const markerRing = new THREE.Mesh(
    track(new THREE.RingGeometry(0.09, 0.12, 40)),
    track(new THREE.MeshBasicMaterial({ color: "#7de6d6", transparent: true, depthTest: false, side: THREE.DoubleSide })),
  );
  markerRing.rotation.x = -Math.PI / 2;
  markerRing.position.y = 0.01;
  markerRing.renderOrder = 10;
  markerGroup.add(markerRing);
  const spriteMaterial = track(new THREE.SpriteMaterial({ depthTest: false, transparent: true, sizeAttenuation: false }));
  const sprite = new THREE.Sprite(spriteMaterial);
  sprite.scale.set(0.3, 0.06, 1);
  sprite.position.y = 0.25;
  sprite.renderOrder = 11;
  markerGroup.add(sprite);
  markerGroup.visible = false;
  scene.add(markerGroup);
  let markerTexture: THREE.CanvasTexture | null = null;

  // First-person camera movement between viewpoints.
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const position = vec(initialView.position);
  const target = vec(initialView.target);
  let walk: {
    fromPosition: THREE.Vector3;
    toPosition: THREE.Vector3;
    fromTarget: THREE.Vector3;
    toTarget: THREE.Vector3;
    start: number;
    duration: number;
    distance: number;
  } | null = null;

  function moveTo(view: Viewpoint, immediate = false) {
    const toPosition = vec(view.position);
    const toTarget = vec(view.target);
    if (immediate || reduceMotion) {
      walk = null;
      position.copy(toPosition);
      target.copy(toTarget);
      return;
    }
    const distance = position.distanceTo(toPosition);
    const turn = target.clone().sub(position).normalize().angleTo(toTarget.clone().sub(toPosition).normalize());
    walk = {
      fromPosition: position.clone(),
      toPosition,
      fromTarget: target.clone(),
      toTarget,
      start: performance.now(),
      duration: Math.min(4200, Math.max(900, (distance / WALK_SPEED) * 1000, turn * 700)),
      distance,
    };
  }

  function showKeysMarker(label: string | null) {
    markerTexture?.dispose();
    markerTexture = null;
    if (label === null) {
      markerGroup.visible = false;
      return;
    }
    markerTexture = labelTexture(label);
    spriteMaterial.map = markerTexture;
    spriteMaterial.needsUpdate = true;
    markerGroup.visible = true;
  }

  function resize() {
    const width = canvas.clientWidth;
    const height = canvas.clientHeight;
    if (width === 0 || height === 0) {
      return;
    }
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }
  const observer = new ResizeObserver(resize);
  observer.observe(canvas);
  resize();

  let frameId = 0;
  function render(now: number) {
    let bob = 0;
    if (walk) {
      const progress = Math.min(1, (now - walk.start) / walk.duration);
      const eased = easeInOut(progress);
      position.lerpVectors(walk.fromPosition, walk.toPosition, eased);
      target.lerpVectors(walk.fromTarget, walk.toTarget, eased);
      bob = Math.sin(progress * walk.distance * Math.PI * 2.2) * 0.025 * Math.sin(progress * Math.PI);
      if (progress >= 1) {
        walk = null;
      }
    }
    camera.position.set(position.x, position.y + bob, position.z);
    camera.lookAt(target);
    if (markerGroup.visible) {
      const pulse = 1 + Math.sin(now / 320) * 0.18;
      markerRing.scale.set(pulse, pulse, pulse);
    }
    renderer.render(scene, camera);
    frameId = window.requestAnimationFrame(render);
  }
  frameId = window.requestAnimationFrame(render);

  return {
    moveTo,
    showKeysMarker,
    dispose: () => {
      window.cancelAnimationFrame(frameId);
      observer.disconnect();
      markerTexture?.dispose();
      disposables.forEach((item) => item.dispose());
      renderer.dispose();
    },
  };
}
