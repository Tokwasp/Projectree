/**
 * 별(root, 일반 Mesh)과 행성(decision/task/issue, InstancedMesh)이 함께 쓰는 정점 셰이더.
 * `USE_INSTANCING`은 InstancedMesh에 붙었을 때만 three.js가 정의하므로,
 * 호출부에서 분기하지 않고 한 소스로 둘 다 처리된다.
 */
export const nodeVertexShader = /* glsl */ `
  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  void main() {
    vLocalPos = position;

    #ifdef USE_INSTANCING
      vec4 worldPos = instanceMatrix * vec4(position, 1.0);
      vec3 worldNormal = normalize(mat3(instanceMatrix) * normal);
    #else
      vec4 worldPos = vec4(position, 1.0);
      vec3 worldNormal = normalize(normal);
    #endif

    vWorldNormal = worldNormal;
    vWorldPos = worldPos.xyz;

    vec4 mvPosition = modelViewMatrix * worldPos;
    gl_Position = projectionMatrix * mvPosition;
  }
`;

const noiseFn = /* glsl */ `
  float hash(vec3 p) {
    return fract(sin(dot(p, vec3(12.9898, 78.233, 45.164))) * 43758.5453);
  }

  float noise(vec3 p) {
    vec3 i = floor(p);
    vec3 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    float n000 = hash(i);
    float n100 = hash(i + vec3(1.0, 0.0, 0.0));
    float n010 = hash(i + vec3(0.0, 1.0, 0.0));
    float n110 = hash(i + vec3(1.0, 1.0, 0.0));
    float n001 = hash(i + vec3(0.0, 0.0, 1.0));
    float n101 = hash(i + vec3(1.0, 0.0, 1.0));
    float n011 = hash(i + vec3(0.0, 1.0, 1.0));
    float n111 = hash(i + vec3(1.0, 1.0, 1.0));
    return mix(
      mix(mix(n000, n100, f.x), mix(n010, n110, f.x), f.y),
      mix(mix(n001, n101, f.x), mix(n011, n111, f.x), f.y),
      f.z
    );
  }
`;

/** 두 톤의 띠 + 프레넬 대기 림 — 작게 빛나는 행성처럼 보인다. */
export const planetFragmentShader = /* glsl */ `
  uniform vec3 uBaseColor;
  uniform vec3 uBandColor;
  uniform vec3 uGlowColor;
  uniform float uTime;

  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  ${noiseFn}

  void main() {
    vec3 normal = normalize(vWorldNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPos);

    vec3 spinPos = vLocalPos;
    float angle = uTime * 0.15;
    spinPos.xz = mat2(cos(angle), -sin(angle), sin(angle), cos(angle)) * spinPos.xz;

    float bandNoise = noise(spinPos * 2.5);
    float bands = sin(spinPos.y * 4.0 + bandNoise * 2.2) * 0.5 + 0.5;
    vec3 surfaceColor = mix(uBaseColor, uBandColor, bands * 0.5 + bandNoise * 0.15);

    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 2.5);
    vec3 color = surfaceColor + uGlowColor * fresnel * 1.3;

    gl_FragColor = vec4(color, 1.0);
  }
`;

/** 일렁이는 코어 + 넓은 코로나 — 작은 항성처럼 보인다. */
export const starFragmentShader = /* glsl */ `
  uniform vec3 uBaseColor;
  uniform vec3 uBandColor;
  uniform vec3 uGlowColor;
  uniform float uTime;

  varying vec3 vLocalPos;
  varying vec3 vWorldNormal;
  varying vec3 vWorldPos;

  ${noiseFn}

  void main() {
    vec3 normal = normalize(vWorldNormal);
    vec3 viewDir = normalize(cameraPosition - vWorldPos);

    float flicker = noise(vLocalPos * 3.0 + vec3(0.0, 0.0, uTime * 0.7));
    float surfaceGlow = 0.8 + 0.45 * flicker;
    vec3 core = mix(uBaseColor, uBandColor, flicker * 0.4) * surfaceGlow;

    float fresnel = pow(1.0 - max(dot(normal, viewDir), 0.0), 1.8);
    vec3 color = core + uGlowColor * fresnel * 2.1;

    gl_FragColor = vec4(color, 1.0);
  }
`;

export const starfieldVertexShader = /* glsl */ `
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

export const starfieldFragmentShader = /* glsl */ `
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
