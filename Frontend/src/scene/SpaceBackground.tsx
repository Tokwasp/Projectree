import { useFrame } from "@react-three/fiber";
import { useMemo, useRef } from "react";
import * as THREE from "three";

const STAR_COUNT = 6000;
const INNER_RADIUS = 60;
const OUTER_RADIUS = 400;

const vertexShader = /* glsl */ `
  attribute float aSize;
  attribute float aPhase;
  attribute float aSpeed;
  varying float vPhase;
  varying float vSpeed;
  void main() {
    vPhase = aPhase;
    vSpeed = aSpeed;
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_Position = projectionMatrix * mvPosition;
    gl_PointSize = aSize * (300.0 / -mvPosition.z);
  }
`;

const fragmentShader = /* glsl */ `
  uniform float uTime;
  varying float vPhase;
  varying float vSpeed;
  void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = length(centered);
    if (dist > 0.5) discard;
    float circle = smoothstep(0.5, 0.0, dist);
    float twinkle = 0.5 + 0.5 * sin(uTime * vSpeed + vPhase);
    float alpha = circle * mix(0.35, 1.0, twinkle);
    vec3 color = mix(vec3(0.75, 0.82, 1.0), vec3(1.0), twinkle);
    gl_FragColor = vec4(color, alpha);
  }
`;

/** Thousands of twinkling points on a spherical shell around the origin.
 * Twinkling and size falloff run entirely in the shader — the only per-frame
 * JS cost is updating a single `uTime` uniform. */
export function SpaceBackground() {
  const materialRef = useRef<THREE.ShaderMaterial>(null);

  const geometry = useMemo(() => {
    const positions = new Float32Array(STAR_COUNT * 3);
    const sizes = new Float32Array(STAR_COUNT);
    const phases = new Float32Array(STAR_COUNT);
    const speeds = new Float32Array(STAR_COUNT);

    for (let i = 0; i < STAR_COUNT; i++) {
      const radius = THREE.MathUtils.lerp(INNER_RADIUS, OUTER_RADIUS, Math.cbrt(Math.random()));
      const theta = Math.random() * Math.PI * 2;
      const phi = Math.acos(THREE.MathUtils.lerp(-1, 1, Math.random()));

      positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
      positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
      positions[i * 3 + 2] = radius * Math.cos(phi);

      sizes[i] = THREE.MathUtils.lerp(0.6, 2.2, Math.random());
      phases[i] = Math.random() * Math.PI * 2;
      speeds[i] = THREE.MathUtils.lerp(0.4, 1.6, Math.random());
    }

    const geo = new THREE.BufferGeometry();
    geo.setAttribute("position", new THREE.BufferAttribute(positions, 3));
    geo.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
    geo.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
    geo.setAttribute("aSpeed", new THREE.BufferAttribute(speeds, 1));
    return geo;
  }, []);

  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame((_, delta) => {
    if (materialRef.current) {
      materialRef.current.uniforms.uTime.value += delta;
    }
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={vertexShader}
        fragmentShader={fragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}
