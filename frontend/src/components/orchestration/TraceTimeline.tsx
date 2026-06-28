import { motion } from "motion/react";
import type { TraceItem } from "../../types/models";
import { CritiqueRound } from "./CritiqueRound";
import { PlanView } from "./PlanView";
import styles from "./orchestration.module.css";

type LineItem = Exclude<TraceItem, { kind: "plan" } | { kind: "critique" }>;

function Line({ item, spinning }: { item: LineItem; spinning?: boolean }) {
  let role = "planner";
  let text = "";
  let tone: "error" | undefined;
  if (item.kind === "thinking") {
    role = item.role;
    text = item.text;
  } else if (item.kind === "dispatch") {
    role = item.role;
    text = `Asking ${item.role}…`;
  } else if (item.kind === "result") {
    role = item.role;
    text = `${item.role} replied`;
  } else {
    role = item.role;
    tone = item.tone;
    text =
      item.phase === "query"
        ? `${item.agent} searching: “${item.text}”`
        : item.phase === "results"
          ? `${item.agent}: ${item.text}`
          : `${item.agent} search failed — ${item.text}`;
  }
  return (
    <div className={`${styles.line} ${tone === "error" ? styles.err : ""}`}>
      <span className={styles.lineDot} style={{ background: `var(--r-${role})` }} />
      <span className={styles.lineText}>{text}</span>
      {spinning && <span className={styles.spin} />}
    </div>
  );
}

// The rich orchestration timeline: plan/critique render as cards, the rest as lines.
export function TraceTimeline({ items, live }: { items: TraceItem[]; live?: boolean }) {
  return (
    <div className={styles.timeline}>
      {items.map((item, i) => {
        const node =
          item.kind === "plan" ? (
            <PlanView item={item} />
          ) : item.kind === "critique" ? (
            <CritiqueRound item={item} />
          ) : (
            <Line item={item} spinning={live && i === items.length - 1} />
          );
        return (
          <motion.div key={item.id} layout initial={{ opacity: 0, x: -8 }} animate={{ opacity: 1, x: 0 }}>
            {node}
          </motion.div>
        );
      })}
    </div>
  );
}
