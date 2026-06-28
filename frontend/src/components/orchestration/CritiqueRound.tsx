import type { CSSProperties } from "react";
import type { TraceItem } from "../../types/models";
import styles from "./orchestration.module.css";

// Renders a planner pushback (critique.round): it distrusts a result and is verifying.
export function CritiqueRound({ item }: { item: Extract<TraceItem, { kind: "critique" }> }) {
  const accent = { "--kc": `var(--r-${item.to ?? "qa"})` } as CSSProperties;
  return (
    <div className={`${styles.card} ${styles.critique}`} style={accent}>
      <div className={styles.cardHead}>
        <span className={styles.icon}>⟳</span>
        Critique round {item.round} ·{" "}
        {item.action === "verify" ? "verifying" : "re-checking"}
        {item.to ? ` with ${item.to}` : ""}
      </div>
      <div className={styles.concern}>{item.concern}</div>
    </div>
  );
}
