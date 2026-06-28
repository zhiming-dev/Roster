import { useEffect, useMemo, useRef, useState } from "react";
import { deriveLineage, useStore } from "../../store/store";
import type { LineageNode } from "../../types/models";
import { AgentNode } from "./AgentNode";
import styles from "./lineage.module.css";

type Pos = Record<string, { x: number; y: number }>;

const FLASH_MS = 3600;

// Port of the legacy dashboard's layoutLineage: you on the left, planner mid-left,
// specialists fanned across the right with alternating vertical offsets.
function layout(nodes: LineageNode[], W: number, H: number): Pos {
  const pos: Pos = {};
  if (!W || !H) return pos;
  const keys = nodes.map((n) => n.key);
  const padTop = 50;
  const padBot = 16;
  const avail = Math.max(60, H - padTop - padBot);
  const midY = padTop + avail / 2;
  const amp = avail / 2 - 6;

  pos["you"] = { x: Math.max(54, W * 0.08), y: midY };
  const hasPlanner = keys.includes("planner");
  if (hasPlanner) pos["planner"] = { x: Math.max(160, W * 0.26), y: midY };

  const specs = keys.filter((k) => k !== "you" && k !== "planner");
  const x0 = W * (hasPlanner ? 0.5 : 0.34);
  const x1 = W - Math.max(80, W * 0.09);
  specs.forEach((k, i) => {
    const t = specs.length <= 1 ? 0.5 : i / (specs.length - 1);
    const x = x0 + (x1 - x0) * t;
    const off = specs.length > 1 ? (i % 2 === 0 ? -1 : 1) : 0;
    pos[k] = { x, y: midY + off * amp };
  });
  return pos;
}

export function LineageGraph() {
  const agents = useStore((s) => s.agents);
  const activeEdges = useStore((s) => s.activeEdges);
  const { nodes, edges } = useMemo(() => deriveLineage(agents), [agents]);

  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ w: 0, h: 0 });
  const [, setTick] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setSize({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Re-render once after a flash window so active edges settle back to idle.
  useEffect(() => {
    const now = Date.now();
    if (Object.values(activeEdges).some((ts) => now - ts < FLASH_MS)) {
      const t = setTimeout(() => setTick((n) => n + 1), FLASH_MS + 50);
      return () => clearTimeout(t);
    }
  }, [activeEdges]);

  const pos = useMemo(() => layout(nodes, size.w, size.h), [nodes, size]);
  const now = Date.now();

  return (
    <div className={styles.lineage} ref={ref}>
      <div className={styles.cap}>Agent lineage</div>
      <svg className={styles.edges} width={size.w} height={size.h}>
        {edges.map((e) => {
          const a = pos[e.from];
          const b = pos[e.to];
          if (!a || !b) return null;
          const active = !!activeEdges[e.id] && now - activeEdges[e.id] < FLASH_MS;
          const dx = Math.max(40, Math.abs(b.x - a.x) * 0.5);
          const d = `M ${a.x} ${a.y} C ${a.x + dx} ${a.y}, ${b.x - dx} ${b.y}, ${b.x} ${b.y}`;
          return (
            <path key={e.id} d={d} className={`${styles.edge} ${active ? styles.active : ""}`} />
          );
        })}
      </svg>
      {nodes.map((n) => {
        const p = pos[n.key];
        if (!p) return null;
        return <AgentNode key={n.key} node={n} x={p.x} y={p.y} />;
      })}
    </div>
  );
}
