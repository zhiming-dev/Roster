import { AnimatePresence, motion } from "motion/react";
import { bouncy } from "../../motion/springs";
import { useStore } from "../../store/store";
import styles from "./orchestration.module.css";

// Renders the planner's mid-task question (clarification.requested) just above the
// composer. The run is suspended; the next message the principal sends is routed back
// as the answer and resumes the same run (US4 / spec 001).
export function ClarificationPrompt() {
  const question = useStore((s) => s.clarification);
  const emoji = useStore((s) => s.agents.planner?.emoji);
  return (
    <AnimatePresence>
      {question && (
        <motion.div
          className={styles.clarify}
          initial={{ opacity: 0, y: 12, scale: 0.97 }}
          animate={{ opacity: 1, y: 0, scale: 1 }}
          exit={{ opacity: 0, y: 8, scale: 0.98 }}
          transition={bouncy}
          role="status"
          aria-live="polite"
        >
          <span className={styles.clarifyAvatar} aria-hidden="true">
            {emoji ?? "🧭"}
          </span>
          <div className={styles.clarifyBody}>
            <div className={styles.clarifyHead}>The planner needs a detail</div>
            <div className={styles.clarifyQuestion}>{question}</div>
            <div className={styles.clarifyHint}>Answer below to continue the run.</div>
          </div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
