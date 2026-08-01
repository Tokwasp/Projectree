import { Html } from "@react-three/drei";
import { useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import * as THREE from "three";
import {
  EDGE_COLOR,
  LABEL_FADE_DISTANCE,
  NODE_VISUALS,
  SPACE,
  UI_FONT,
  type FlatTreeNode,
  type OrbitControlsRef,
  type TreeEdge,
  type TreeNodeInput,
} from "./config";
import {
  nodeVertexShader,
  planetFragmentShader,
  starFragmentShader,
  starfieldFragmentShader,
  starfieldVertexShader,
} from "./shaders";
import { buildTree, useTreeRuntime, type TreeRuntime } from "./treeEngine";

const PLANET_TYPES = ["category", "decision", "task", "issue"] as const;

interface TreeSceneProps {
  data: TreeNodeInput;
  controlsRef: OrbitControlsRef;
}

export function TreeScene({ data, controlsRef }: TreeSceneProps) {
  const flat = useMemo(() => buildTree(data), [data]);
  const runtime = useTreeRuntime(flat);

  return (
    <>
      <StarfieldBackdrop />
      <TreeEdges edges={flat.edges} runtime={runtime} />
      <RootNode id={flat.rootId} runtime={runtime} controlsRef={controlsRef} />
      {PLANET_TYPES.map((type) =>
        flat.byType[type].length > 0 ? (
          <PlanetNodes key={type} nodes={flat.byType[type]} runtime={runtime} />
        ) : null,
      )}
      {flat.order.map((node) => (
        <NodeLabel key={node.id} node={node} runtime={runtime} />
      ))}
    </>
  );
}

function createStarfieldGeometry(): THREE.BufferGeometry {
  const positions = new Float32Array(SPACE.STAR_COUNT * 3);
  const sizes = new Float32Array(SPACE.STAR_COUNT);
  const phases = new Float32Array(SPACE.STAR_COUNT);
  const speeds = new Float32Array(SPACE.STAR_COUNT);

  for (let i = 0; i < SPACE.STAR_COUNT; i++) {
    const radius = THREE.MathUtils.lerp(
      SPACE.STAR_INNER_RADIUS,
      SPACE.STAR_OUTER_RADIUS,
      Math.cbrt(Math.random()),
    );
    const theta = Math.random() * Math.PI * 2;
    const phi = Math.acos(THREE.MathUtils.lerp(-1, 1, Math.random()));

    positions[i * 3] = radius * Math.sin(phi) * Math.cos(theta);
    positions[i * 3 + 1] = radius * Math.sin(phi) * Math.sin(theta);
    positions[i * 3 + 2] = radius * Math.cos(phi);

    sizes[i] = THREE.MathUtils.lerp(0.6, 2.2, Math.random());
    phases[i] = Math.random() * Math.PI * 2;
    speeds[i] = THREE.MathUtils.lerp(0.4, 1.6, Math.random());
  }

  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  geometry.setAttribute("aSize", new THREE.BufferAttribute(sizes, 1));
  geometry.setAttribute("aPhase", new THREE.BufferAttribute(phases, 1));
  geometry.setAttribute("aSpeed", new THREE.BufferAttribute(speeds, 1));
  return geometry;
}

function StarfieldBackdrop() {
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const [geometry] = useState(createStarfieldGeometry);
  const uniforms = useMemo(() => ({ uTime: { value: 0 } }), []);

  useFrame((_, delta) => {
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  });

  return (
    <points geometry={geometry} frustumCulled={false}>
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={starfieldVertexShader}
        fragmentShader={starfieldFragmentShader}
        transparent
        depthWrite={false}
        blending={THREE.AdditiveBlending}
      />
    </points>
  );
}

function TreeEdges({
  edges,
  runtime,
}: {
  edges: TreeEdge[];
  runtime: TreeRuntime;
}) {
  const geometry = useMemo(() => {
    const geo = new THREE.BufferGeometry();
    geo.setAttribute(
      "position",
      new THREE.BufferAttribute(new Float32Array(edges.length * 6), 3),
    );
    return geo;
  }, [edges]);

  useFrame(() => {
    const positionAttr = geometry.getAttribute(
      "position",
    ) as THREE.BufferAttribute;
    const array = positionAttr.array as Float32Array;

    for (let i = 0; i < edges.length; i++) {
      const parentState = runtime.nodeStates.get(edges[i].parentId);
      const childState = runtime.nodeStates.get(edges[i].childId);
      if (!parentState || !childState) continue;

      const offset = i * 6;
      array[offset] = parentState.current.x;
      array[offset + 1] = parentState.current.y;
      array[offset + 2] = parentState.current.z;
      array[offset + 3] = childState.current.x;
      array[offset + 4] = childState.current.y;
      array[offset + 5] = childState.current.z;
    }
    positionAttr.needsUpdate = true;
  }, 1);

  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial
        color={EDGE_COLOR}
        transparent
        opacity={0.55}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
        depthWrite={false}
      />
    </lineSegments>
  );
}

function PlanetNodes({
  nodes,
  runtime,
}: {
  nodes: FlatTreeNode[];
  runtime: TreeRuntime;
}) {
  const meshRef = useRef<THREE.InstancedMesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const dummy = useMemo(() => new THREE.Object3D(), []);
  const visual = NODE_VISUALS[nodes[0].type];
  const uniforms = useMemo(
    () => ({
      uBaseColor: { value: new THREE.Color(visual.baseColor) },
      uBandColor: { value: new THREE.Color(visual.bandColor) },
      uGlowColor: { value: new THREE.Color(visual.glowColor) },
      uTime: { value: 0 },
    }),
    [visual],
  );

  useFrame((_, delta) => {
    const mesh = meshRef.current;
    if (mesh) {
      for (let i = 0; i < nodes.length; i++) {
        const state = runtime.nodeStates.get(nodes[i].id);
        if (!state) continue;
        dummy.position.copy(state.current);
        dummy.updateMatrix();
        mesh.setMatrixAt(i, dummy.matrix);
      }
      mesh.instanceMatrix.needsUpdate = true;
    }
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  }, 1);

  return (
    <instancedMesh ref={meshRef} args={[undefined, undefined, nodes.length]}>
      <sphereGeometry args={[visual.radius, 32, 32]} />
      <shaderMaterial
        ref={materialRef}
        uniforms={uniforms}
        vertexShader={nodeVertexShader}
        fragmentShader={planetFragmentShader}
        toneMapped={false}
      />
    </instancedMesh>
  );
}

function RootNode({
  id,
  runtime,
  controlsRef,
}: {
  id: string;
  runtime: TreeRuntime;
  controlsRef: OrbitControlsRef;
}) {
  const meshRef = useRef<THREE.Mesh>(null);
  const materialRef = useRef<THREE.ShaderMaterial>(null);
  const [dragPlane, setDragPlane] = useState<{
    origin: THREE.Vector3;
    quaternion: THREE.Quaternion;
  } | null>(null);
  const { camera } = useThree();
  const visual = NODE_VISUALS.root;

  const uniforms = useMemo(
    () => ({
      uBaseColor: { value: new THREE.Color(visual.baseColor) },
      uBandColor: { value: new THREE.Color(visual.bandColor) },
      uGlowColor: { value: new THREE.Color(visual.glowColor) },
      uTime: { value: 0 },
    }),
    [visual],
  );

  useFrame((_, delta) => {
    const state = runtime.nodeStates.get(id);
    if (state && meshRef.current) meshRef.current.position.copy(state.current);
    if (materialRef.current) materialRef.current.uniforms.uTime.value += delta;
  }, 1);

  const endDrag = useCallback(() => {
    runtime.endDrag();
    if (controlsRef.current) controlsRef.current.enabled = true;
    setDragPlane(null);
  }, [runtime, controlsRef]);

  useEffect(() => {
    if (!dragPlane) return;
    window.addEventListener("pointerup", endDrag);
    return () => window.removeEventListener("pointerup", endDrag);
  }, [dragPlane, endDrag]);

  const handlePointerDown = (event: ThreeEvent<PointerEvent>) => {
    event.stopPropagation();
    const state = runtime.nodeStates.get(id);
    if (!state) return;
    setDragPlane({
      origin: state.current.clone(),
      quaternion: camera.quaternion.clone(),
    });
    runtime.beginDrag(id);
    if (controlsRef.current) controlsRef.current.enabled = false;
  };

  return (
    <>
      <mesh ref={meshRef} onPointerDown={handlePointerDown}>
        <sphereGeometry args={[visual.radius, 48, 48]} />
        <shaderMaterial
          ref={materialRef}
          uniforms={uniforms}
          vertexShader={nodeVertexShader}
          fragmentShader={starFragmentShader}
          toneMapped={false}
        />
      </mesh>
      {dragPlane && (
        <mesh
          position={dragPlane.origin}
          quaternion={dragPlane.quaternion}
          onPointerMove={(event) => runtime.updateDragPoint(event.point)}
          onPointerUp={endDrag}
          onPointerLeave={endDrag}
        >
          <planeGeometry args={[1000, 1000]} />
          <meshBasicMaterial visible={false} />
        </mesh>
      )}
    </>
  );
}

function NodeLabel({
  node,
  runtime,
}: {
  node: FlatTreeNode;
  runtime: TreeRuntime;
}) {
  const groupRef = useRef<THREE.Group>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);
  const visual = NODE_VISUALS[node.type];
  const fadeRange = LABEL_FADE_DISTANCE[node.type];
  const { camera } = useThree();

  useFrame(() => {
    const state = runtime.nodeStates.get(node.id);
    if (!state || !groupRef.current) return;

    groupRef.current.position.copy(state.current);
    groupRef.current.position.y -= visual.radius + 0.35;

    const distance = camera.position.distanceTo(state.current);
    const opacity =
      1 - THREE.MathUtils.smoothstep(distance, fadeRange.start, fadeRange.end);
    if (wrapperRef.current) {
      wrapperRef.current.style.opacity = opacity.toString();
      wrapperRef.current.style.display = opacity < 0.02 ? "none" : "block";
    }
  }, 1);

  return (
    <group ref={groupRef}>
      <Html
        center
        pointerEvents="none"
        style={{ pointerEvents: "none" }}
        zIndexRange={[10, 0]}
      >
        <div
          ref={wrapperRef}
          style={{
            textAlign: "center",
            pointerEvents: "none",
            userSelect: "none",
            transition: "opacity 0.12s linear",
          }}
        >
          <div
            style={{
              width: 6,
              height: 6,
              margin: "0 auto 4px",
              borderRadius: "50%",
              background: visual.glowColor,
              boxShadow: `0 0 6px 1px ${visual.glowColor}`,
            }}
          />
          <div
            style={{
              display: "inline-block",
              width: "max-content",
              maxWidth: 160,
              padding: "3px 9px",
              borderRadius: 999,
              background: "rgba(6, 8, 20, 0.55)",
              border: `1px solid ${visual.glowColor}66`,
              backdropFilter: "blur(3px)",
              color: "#f2f4ff",
              fontSize: 11,
              fontFamily: UI_FONT,
              letterSpacing: "0.01em",
              lineHeight: 1.35,
              textAlign: "center",
              whiteSpace: "normal",
              wordBreak: "keep-all",
              overflowWrap: "break-word",
              textShadow: `0 0 8px ${visual.glowColor}55`,
            }}
          >
            {node.title}
          </div>
        </div>
      </Html>
    </group>
  );
}
