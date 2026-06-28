import type { TraceItem } from "../../types/models";
import styles from "./orchestration.module.css";

// Renders a planner decomposition (plan.proposed): the sub-tasks it fanned out to.
export function PlanView({ item }: { item: Extract<TraceItem, { kind: "plan" }> }) {
  return (
    <div className={styles.card}>
      <div className={styles.cardHead}>
        <span className={styles.icon}>⌗</span>
        {item.summary ? `Decomposed: ${item.summary}` : `Decomposed into ${item.tasks.length} sub-tasks`}
      </div>
      <div className={styles.tasks}>
        {item.tasks.map((t, i) => (
          <div key={i} className={styles.task}>
            <span className={styles.taskDot} style={{ background: `var(--r-${t.role})` }} />
            <span className={styles.taskRole}>{t.role}</span>
            <span className={styles.taskText}>{t.task}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
