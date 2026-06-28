import { motion } from "motion/react";
import type { CSSProperties } from "react";
import { bouncy } from "../../motion/springs";
import type { LineageNode } from "../../types/models";
import styles from "./lineage.module.css";

export function AgentNode({ node, x, y }: { node: LineageNode; x: number; y: number }) {
  const busy =
    node.status === "thinking" || node.status === "searching" || node.status === "queued";
  // Motion owns the full transform (including the -50% centering) so it can spring
  // the scale without fighting a CSS translate.
  const style = {
    left: x,
    top: y,
    "--role": node.color ?? `var(--r-${node.role})`,
  } as CSSProperties;
  return (
    <motion.div
      className={`${styles.node} ${node.you ? styles.you : ""}`}
      data-st={node.status}
      style={style}
      initial={{ x: "-50%", y: "-50%", scale: 0.4, opacity: 0 }}
      animate={{ x: "-50%", y: "-50%", scale: busy ? [1, 1.05, 1] : 1, opacity: 1 }}
      transition={
        busy
          ? { scale: { repeat: Infinity, duration: 1.6, ease: "easeInOut" }, default: bouncy }
          : bouncy
      }
    >
      <div className={styles.bubble}>
        <span className={styles.avatar}>{node.emoji}</span>
        <span className={styles.dot} />
        <span className={styles.nm}>{node.name}</span>
      </div>
      <span className={styles.st}>{node.status !== "idle" ? node.status : ""}</span>
    </motion.div>
  );
}
