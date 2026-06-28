import { motion } from "motion/react";
import { deleteConversation, newChat, openConversation } from "../store/actions";
import { useStore } from "../store/store";
import type { ConversationSummary } from "../types/models";
import { ThemeToggle } from "./ThemeToggle";
import styles from "./Sidebar.module.css";

function timeAgo(ts?: number): string {
  if (!ts) return "";
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 60) return "just now";
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 604800) return `${Math.floor(s / 86400)}d ago`;
  return new Date(ts * 1000).toLocaleDateString();
}

function ConversationItem({ c, active }: { c: ConversationSummary; active: boolean }) {
  return (
    <div
      className={`${styles.conv} ${active ? styles.convActive : ""}`}
      onClick={() => openConversation(c.id)}
    >
      <div className={styles.title}>{c.title || "New conversation"}</div>
      <div className={styles.meta}>
        {c.messages} msg · {timeAgo(c.updated_at)}
      </div>
      <button
        className={styles.del}
        title="Delete"
        aria-label="Delete conversation"
        onClick={(e) => {
          e.stopPropagation();
          if (confirm("Delete this conversation? This cannot be undone.")) {
            void deleteConversation(c.id);
          }
        }}
      >
        ✕
      </button>
    </div>
  );
}

export function Sidebar() {
  const conversations = useStore((s) => s.conversations);
  const activeConvId = useStore((s) => s.activeConvId);
  const runId = useStore((s) => s.runId);
  const queue = useStore((s) => s.queue);
  const agents = useStore((s) => s.agents);

  // Live queue counts derived from agent statuses (matches the legacy dashboard).
  const busy = Object.values(agents).filter(
    (a) => a.status === "thinking" || a.status === "searching",
  ).length;
  const waiting = Object.values(agents).filter((a) => a.status === "queued").length;
  const max = queue?.max_concurrency ?? 1;

  return (
    <aside className={styles.sidebar}>
      <div className={styles.brand}>
        <div className={styles.logo}>R</div>
        <div>
          <strong>Roster</strong>
          <small>multi-agent runtime</small>
        </div>
      </div>

      <motion.button
        className={styles.newchat}
        whileHover={{ y: -2, scale: 1.02 }}
        whileTap={{ scale: 0.95 }}
        onClick={() => void newChat()}
      >
        ＋ New chat
      </motion.button>

      <div className={styles.label}>History</div>
      <div className={styles.list}>
        {conversations.length === 0 ? (
          <div className={styles.empty}>No conversations yet.</div>
        ) : (
          conversations.map((c) => (
            <ConversationItem key={c.id} c={c} active={c.id === activeConvId} />
          ))
        )}
      </div>

      <div className={styles.footer}>
        <span className={styles.runid} title={runId ?? ""}>
          run: {runId ?? "—"}
        </span>
        <span className={styles.chip}>
          queue {busy}·{waiting} / {max}
        </span>
        <ThemeToggle />
      </div>
    </aside>
  );
}
