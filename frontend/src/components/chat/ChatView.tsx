import { AnimatePresence, motion } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { bouncy } from "../../motion/springs";
import { useStore } from "../../store/store";
import type { ChatMessage } from "../../types/models";
import { TraceTimeline } from "../orchestration/TraceTimeline";
import styles from "./chat.module.css";

const SUGGESTIONS = [
  "Analyze today's NASDAQ — 10/30/200-day report",
  "Research how the US indexes did today",
  "Review the diff on my feature branch",
];

const enter = {
  layout: true,
  initial: { opacity: 0, y: 14, scale: 0.96 },
  animate: { opacity: 1, y: 0, scale: 1 },
  transition: bouncy,
};

function MessageBubble({ m }: { m: ChatMessage }) {
  const [open, setOpen] = useState(false);
  const emoji = useStore((s) => s.agents[m.author]?.emoji);
  if (m.side === "user") {
    return (
      <motion.div className={`${styles.row} ${styles.user}`} {...enter}>
        <div className={styles.bubbleUser}>{m.content}</div>
      </motion.div>
    );
  }
  const trace = m.trace ?? [];
  return (
    <motion.div className={`${styles.row} ${styles.agent}`} {...enter}>
      <div className={styles.wrap}>
        <div className={styles.who}>
          <span className={styles.avatar}>{emoji ?? "🤖"}</span>
          {m.author}
        </div>
        <div className={`${styles.bubbleAgent} ${m.error ? styles.error : ""}`}>{m.content}</div>
        {trace.length > 0 && (
          <div className={styles.trace}>
            <button className={styles.traceToggle} onClick={() => setOpen((o) => !o)}>
              {open ? "▾" : "▸"} Process · {trace.length} step{trace.length > 1 ? "s" : ""}
            </button>
            {open && (
              <div className={styles.traceBody}>
                <TraceTimeline items={trace} />
              </div>
            )}
          </div>
        )}
      </div>
    </motion.div>
  );
}

function Typing() {
  return (
    <div className={`${styles.row} ${styles.agent}`}>
      <div className={styles.wrap}>
        <div className={styles.who}>
          <span className={styles.dot} style={{ background: "var(--r-planner)" }} />
          planner
        </div>
        <div className={`${styles.bubbleAgent} ${styles.typing}`}>
          <span className={styles.tdot} />
          <span className={styles.tdot} />
          <span className={styles.tdot} />
        </div>
      </div>
    </div>
  );
}

function ProgressCard() {
  const progress = useStore((s) => s.progress);
  if (progress.length === 0) return <Typing />;
  return (
    <motion.div
      className={`${styles.row} ${styles.agent}`}
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.96 }}
    >
      <div className={styles.wrap}>
        <div className={styles.who}>
          <span className={styles.dot} style={{ background: "var(--r-planner)" }} />
          working…
        </div>
        <div className={styles.progress}>
          <TraceTimeline items={progress.slice(-8)} live />
        </div>
      </div>
    </motion.div>
  );
}

function Empty() {
  const setDraft = useStore((s) => s.setDraft);
  return (
    <div className={styles.empty}>
      <div className={styles.glyph}>✦</div>
      <h2>What should the team build?</h2>
      <p>Talk to the Planner — it decomposes your goal and dispatches the specialists.</p>
      <div className={styles.suggest}>
        {SUGGESTIONS.map((s) => (
          <button key={s} onClick={() => setDraft(s)}>
            {s}
          </button>
        ))}
      </div>
    </div>
  );
}

export function ChatView() {
  const messages = useStore((s) => s.messages);
  const typing = useStore((s) => s.typing);
  const progress = useStore((s) => s.progress);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, typing, progress]);

  return (
    <div className={styles.scroll} ref={scrollRef}>
      <div className={styles.rail}>
        {messages.length === 0 && !typing ? (
          <Empty />
        ) : (
          <>
            {messages.map((m) => (
              <MessageBubble key={m.id} m={m} />
            ))}
            <AnimatePresence>{typing && <ProgressCard key="progress" />}</AnimatePresence>
          </>
        )}
      </div>
    </div>
  );
}
