import { motion } from "motion/react";
import type { CSSProperties } from "react";
import { springy } from "../../motion/springs";
import { useStore } from "../../store/store";
import type { ActivityItem } from "../../types/models";
import { RichText } from "../rich/RichText";
import styles from "./activity.module.css";

function ActivityEvent({ e }: { e: ActivityItem }) {
  const kindStyle = { "--kc": `var(--r-${e.role})` } as CSSProperties;
  return (
    <motion.div
      className={styles.evt}
      layout
      initial={{ opacity: 0, y: 8, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={springy}
    >
      <div className={styles.head}>
        <span className={styles.from}>{e.from}</span>
        {e.to && (
          <>
            <span className={styles.arr}>→</span>
            <span className={styles.from}>{e.to}</span>
          </>
        )}
        <span className={styles.kind} style={kindStyle}>
          {e.label}
        </span>
      </div>
      {e.results && e.results.length > 0 ? (
        <div className={styles.body}>
          <div>{e.body}</div>
          <ol className={styles.results}>
            {e.results.map((r, i) => (
              <li key={i}>
                <a href={r.url} target="_blank" rel="noopener noreferrer">
                  {r.title}
                </a>
              </li>
            ))}
          </ol>
        </div>
      ) : (
        e.body && (
          <div className={styles.body}>
            <RichText content={e.body} compact />
          </div>
        )
      )}
    </motion.div>
  );
}

export function ActivityPanel({ onClose }: { onClose: () => void }) {
  const activity = useStore((s) => s.activity);
  return (
    <aside className={styles.activity}>
      <div className={styles.inner}>
        <div className={styles.headerBar}>
          <h3>Inter-agent activity</h3>
          <button className={styles.close} onClick={onClose} aria-label="Close activity">
            ✕
          </button>
        </div>
        <div className={styles.feed}>
          {activity.length === 0 ? (
            <div className={styles.empty}>
              No agent traffic yet. Dispatches, results and searches appear here.
            </div>
          ) : (
            activity.map((e) => <ActivityEvent key={e.id} e={e} />)
          )}
        </div>
      </div>
    </aside>
  );
}
